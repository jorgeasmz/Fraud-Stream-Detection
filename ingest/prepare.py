"""Turns the cached day files into one time-ordered table."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ingest.config import RAW_DIR, TABLE_PATH
from ingest.download import fetch_all

log = logging.getLogger(__name__)

COLUMNS = {
    "TRANSACTION_ID": "transaction_id",
    "TX_DATETIME": "tx_datetime",
    "CUSTOMER_ID": "customer_id",
    "TERMINAL_ID": "terminal_id",
    "TX_AMOUNT": "amount",
    "TX_FRAUD": "is_fraud",
    "TX_FRAUD_SCENARIO": "scenario",
}

DTYPES = {
    "transaction_id": "int64",
    "customer_id": "int32",
    "terminal_id": "int32",
    "amount": "float32",
    "is_fraud": "int8",
    "scenario": "int8",
}


def read_day(path: Path) -> pd.DataFrame:
    frame = pd.read_pickle(path)
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} is missing {sorted(missing)}")

    frame = frame[list(COLUMNS)].rename(columns=COLUMNS)
    # The published files store the identifiers as objects, which parquet would keep.
    return frame.astype(DTYPES)


def build_table(directory: Path = RAW_DIR, target: Path = TABLE_PATH) -> pd.DataFrame:
    paths = sorted(directory.glob("*.pkl"))
    if not paths:
        raise FileNotFoundError(f"no day files in {directory}; run ingest.download first")

    table = pd.concat((read_day(path) for path in paths), ignore_index=True)
    table = table.sort_values("tx_datetime", kind="stable").reset_index(drop=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(target, index=False)
    log.info(
        "%d transactions, %d frauds (%.3f%%), %s to %s",
        len(table),
        int(table.is_fraud.sum()),
        100 * table.is_fraud.mean(),
        table.tx_datetime.min().date(),
        table.tx_datetime.max().date(),
    )
    return table


def load_table(path: Path = TABLE_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not built; run ingest.prepare first")
    return pd.read_parquet(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_all()
    build_table()
