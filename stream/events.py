"""The wire format of the event stream."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from features.online import UNIX_EPOCH, ResolvedLabel, Transaction
from stream.config import KIND_LABEL, KIND_TRANSACTION


def _moment(epoch: float) -> datetime:
    return UNIX_EPOCH + pd.to_timedelta(epoch, unit="s").to_pytimedelta()


def transaction_event(row) -> dict[str, str]:
    return {
        "kind": KIND_TRANSACTION,
        "transaction_id": str(int(row.transaction_id)),
        "epoch": repr(float((row.tx_datetime - pd.Timestamp("1970-01-01")).total_seconds())),
        "customer_id": str(int(row.customer_id)),
        "terminal_id": str(int(row.terminal_id)),
        "amount": repr(float(row.amount)),
        "is_fraud": str(int(row.is_fraud)),
        "scenario": str(int(row.scenario)),
    }


def label_event(row) -> dict[str, str]:
    event = transaction_event(row)
    event["kind"] = KIND_LABEL
    return event


def decode_event(raw: dict) -> dict[str, str]:
    """Stream fields arrive as bytes, because the window state on the same client is binary."""
    return {
        (key.decode() if isinstance(key, bytes) else key): (
            value.decode() if isinstance(value, bytes) else value
        )
        for key, value in raw.items()
    }


def read_transaction(event: dict[str, str]) -> Transaction:
    return Transaction(
        transaction_id=int(event["transaction_id"]),
        tx_datetime=_moment(float(event["epoch"])),
        customer_id=int(event["customer_id"]),
        terminal_id=int(event["terminal_id"]),
        amount=float(event["amount"]),
    )


def read_label(event: dict[str, str]) -> ResolvedLabel:
    return ResolvedLabel(
        transaction_id=int(event["transaction_id"]),
        tx_datetime=_moment(float(event["epoch"])),
        customer_id=int(event["customer_id"]),
        terminal_id=int(event["terminal_id"]),
        is_fraud=int(event["is_fraud"]),
    )
