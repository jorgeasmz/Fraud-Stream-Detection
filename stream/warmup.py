"""Loads the window state that precedes a replay, so scoring does not start blind.

A consumer that begins with an empty Redis scores its first transactions against
no history, which is a property of the restart rather than of the traffic. The
state is built in one pass and written once per entity, rather than replayed
transaction by transaction.
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from redis import Redis

from features.config import ENTITIES
from features.online import (
    LONGEST_WINDOW_SECONDS,
    RISK_RECORD,
    WINDOW_RECORD,
    risk_key,
    window_key,
)
from features.risk import LABEL_DELAY_DAYS
from ingest.source import replay_slice
from stream.config import REDIS_URL

log = logging.getLogger(__name__)

EPOCH = pd.Timestamp("1970-01-01")
WRITE_BATCH = 1_000


def _seconds(moments: pd.Series) -> np.ndarray:
    return ((moments - EPOCH) // pd.Timedelta(seconds=1)).to_numpy(dtype="uint32")


def _packed(frame: pd.DataFrame, entity: str, value: str, dtype: np.dtype) -> dict[bytes, bytes]:
    """One binary value per entity, holding its window in arrival order."""
    ordered = frame.sort_values("tx_datetime", kind="stable")
    seconds = _seconds(ordered["tx_datetime"])
    values = ordered[value].to_numpy()
    keyed = window_key if dtype is WINDOW_RECORD else risk_key

    packed: dict[bytes, bytes] = {}
    for entity_id, positions in ordered.groupby(f"{entity}_id", sort=False).indices.items():
        records = np.empty(len(positions), dtype=dtype)
        records[dtype.names[0]] = seconds[positions]
        records[dtype.names[1]] = values[positions]
        packed[keyed(entity, int(entity_id))] = records.tobytes()
    return packed


def _write(client: Redis, packed: dict[bytes, bytes], ttl: int) -> None:
    items = list(packed.items())
    for start in range(0, len(items), WRITE_BATCH):
        pipeline = client.pipeline(transaction=False)
        for key, value in items[start : start + WRITE_BATCH]:
            pipeline.set(key, value, ex=ttl)
        pipeline.execute()


def warm(client: Redis, table: pd.DataFrame, start: pd.Timestamp) -> dict[str, int]:
    """Fills both stores with what a consumer running since `start` would already hold."""
    window_floor = start - pd.Timedelta(seconds=LONGEST_WINDOW_SECONDS)
    history = table[(table.tx_datetime >= window_floor) & (table.tx_datetime < start)]

    # A label is only in hand once its dispute has resolved.
    label_ceiling = start - pd.Timedelta(days=LABEL_DELAY_DAYS)
    label_floor = label_ceiling - pd.Timedelta(seconds=LONGEST_WINDOW_SECONDS)
    resolved = table[(table.tx_datetime >= label_floor) & (table.tx_datetime < label_ceiling)]

    risk_ttl = LABEL_DELAY_DAYS * 86_400 + LONGEST_WINDOW_SECONDS
    for entity in ENTITIES:
        _write(client, _packed(history, entity, "amount", WINDOW_RECORD), LONGEST_WINDOW_SECONDS)
        _write(client, _packed(resolved, entity, "is_fraud", RISK_RECORD), risk_ttl)

    return {"windows": len(history), "labels": len(resolved)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-07-08")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    start = pd.Timestamp(args.start)
    client = Redis.from_url(REDIS_URL)
    counts = warm(client, replay_slice(start, args.days), start)
    log.info("warmed %d transactions and %d labels", counts["windows"], counts["labels"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
