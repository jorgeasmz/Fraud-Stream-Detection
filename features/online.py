"""Computes the feature contract from Redis state, one arriving transaction at a time.

The batch implementation in `offline.py` and this one have to agree exactly, or the
detector is fitted on a quantity the live path never produces. `tests/test_parity.py`
asserts that over a replayed sequence.

Each window is one packed binary string rather than a sorted set. The semantics are
identical; the encoding is what decides whether the state fits the memory a free
key-value instance offers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from redis import Redis

from features.config import AMOUNT_FLOOR, ENTITIES, FEATURE_COLUMNS, WINDOWS
from features.risk import LABEL_DELAY_DAYS, risk_columns

LONGEST_WINDOW_SECONDS = max(WINDOWS) * 86_400

# Timestamps are naive and are read as UTC on both paths, so a runner in a zone with
# daylight saving cannot shift a window boundary.
UNIX_EPOCH = datetime(1970, 1, 1)

# Eight bytes a transaction and five an outcome, against the 33 and 18 a sorted set
# spends on the same pair.
WINDOW_RECORD = np.dtype([("ts", "<u4"), ("amount", "<f4")])
RISK_RECORD = np.dtype([("ts", "<u4"), ("outcome", "u1")])


@dataclass(frozen=True)
class Transaction:
    transaction_id: int
    tx_datetime: datetime
    customer_id: int
    terminal_id: int
    amount: float

    @property
    def epoch(self) -> float:
        return (self.tx_datetime - UNIX_EPOCH).total_seconds()


@dataclass(frozen=True)
class ResolvedLabel:
    """A dispute outcome, which reaches the system after the transaction it judges."""

    transaction_id: int
    tx_datetime: datetime
    customer_id: int
    terminal_id: int
    is_fraud: int

    @property
    def epoch(self) -> float:
        return (self.tx_datetime - UNIX_EPOCH).total_seconds()


def window_key(entity: str, entity_id: int) -> bytes:
    return f"w:{entity}:{entity_id}".encode()


def risk_key(entity: str, entity_id: int) -> bytes:
    return f"r:{entity}:{entity_id}".encode()


def pack_window(records: np.ndarray) -> bytes:
    return records.astype(WINDOW_RECORD, copy=False).tobytes()


def pack_risk(records: np.ndarray) -> bytes:
    return records.astype(RISK_RECORD, copy=False).tobytes()


def _unpack(raw: bytes | None, dtype: np.dtype) -> np.ndarray:
    if not raw:
        return np.empty(0, dtype=dtype)
    return np.frombuffer(raw, dtype=dtype)


class _PackedStore:
    """Common read, trim and write cycle over one packed key per entity."""

    dtype: np.dtype
    span_seconds: int

    def __init__(self, client: Redis) -> None:
        self.client = client

    def _key(self, entity: str, entity_id: int) -> bytes:
        raise NotImplementedError

    def _read(self, entity: str, entity_id: int) -> np.ndarray:
        return _unpack(self.client.get(self._key(entity, entity_id)), self.dtype)

    def _store(self, entity: str, entity_id: int, records: np.ndarray) -> None:
        key = self._key(entity, entity_id)
        pipeline = self.client.pipeline(transaction=False)
        pipeline.set(key, records.tobytes())
        pipeline.expire(key, self.span_seconds)
        pipeline.execute()

    def _append(self, entity: str, entity_id: int, record: tuple, newest: float) -> None:
        """Rewrites the key with the window it should hold, plus the new record."""
        kept = self._read(entity, entity_id)
        floor = newest - self.span_seconds
        kept = kept[kept["ts"] >= floor]
        grown = np.empty(len(kept) + 1, dtype=self.dtype)
        grown[: len(kept)] = kept
        grown[-1] = record
        self._store(entity, entity_id, grown)


class WindowStore(_PackedStore):
    """Per-entity sliding windows of amounts, keyed by entity and ordered by time."""

    dtype = WINDOW_RECORD
    span_seconds = LONGEST_WINDOW_SECONDS

    def _key(self, entity: str, entity_id: int) -> bytes:
        return window_key(entity, entity_id)

    def observe(self, transaction: Transaction) -> None:
        """Records the transaction so the next one in its windows can see it."""
        record = (int(transaction.epoch), np.float32(transaction.amount))
        for entity in ENTITIES:
            self._append(
                entity, getattr(transaction, f"{entity}_id"), record, transaction.epoch
            )

    def features(self, transaction: Transaction) -> dict[str, float]:
        """Reads the windows as they stand, which excludes the arriving transaction."""
        now = transaction.epoch
        row: dict[str, float] = {
            "amount": transaction.amount,
            "hour": float(transaction.tx_datetime.hour),
            "is_weekend": float(transaction.tx_datetime.weekday() >= 5),
        }

        for entity in ENTITIES:
            history = self._read(entity, getattr(transaction, f"{entity}_id"))
            # The batch window is [t - length, t), so anything at the arriving instant is out.
            history = history[history["ts"] < now]
            for days in WINDOWS:
                inside = history["amount"][history["ts"] >= now - days * 86_400]
                count = int(inside.size)
                row[f"{entity}_count_{days}d"] = float(count)
                row[f"{entity}_mean_{days}d"] = float(inside.mean()) if count else 0.0

        for days in WINDOWS:
            # Without prior history the deviation is undefined; the count column is
            # what tells the detector that, so the ratio reads zero rather than raw.
            has_history = row[f"customer_count_{days}d"] > 0
            mean = row[f"customer_mean_{days}d"]
            row[f"amount_over_customer_mean_{days}d"] = (
                transaction.amount / (mean + AMOUNT_FLOOR) if has_history else 0.0
            )

        return {column: row[column] for column in FEATURE_COLUMNS}

    def score_and_record(self, transaction: Transaction) -> dict[str, float]:
        row = self.features(transaction)
        self.observe(transaction)
        return row


class RiskStore(_PackedStore):
    """Per-entity fraud rates over windows that end before the label delay.

    Entries are scored by the time of the transaction they judge, not by the time
    the outcome arrived, so a window means the same thing here as it does in batch.
    """

    dtype = RISK_RECORD

    def __init__(self, client: Redis, delay_days: int = LABEL_DELAY_DAYS) -> None:
        super().__init__(client)
        self.delay_seconds = delay_days * 86_400
        self.span_seconds = self.delay_seconds + LONGEST_WINDOW_SECONDS

    def _key(self, entity: str, entity_id: int) -> bytes:
        return risk_key(entity, entity_id)

    def observe(self, label: ResolvedLabel) -> None:
        record = (int(label.epoch), np.uint8(label.is_fraud))
        for entity in ENTITIES:
            self._append(entity, getattr(label, f"{entity}_id"), record, label.epoch)

    def features(self, transaction: Transaction) -> dict[str, float]:
        newest = transaction.epoch - self.delay_seconds
        row: dict[str, float] = {}

        for entity in ENTITIES:
            history = self._read(entity, getattr(transaction, f"{entity}_id"))
            history = history[history["ts"] < newest]
            for days in WINDOWS:
                inside = history["outcome"][history["ts"] >= newest - days * 86_400]
                count = int(inside.size)
                row[f"{entity}_risk_count_{days}d"] = float(count)
                row[f"{entity}_risk_{days}d"] = float(inside.mean()) if count else 0.0

        return {column: row[column] for column in risk_columns()}
