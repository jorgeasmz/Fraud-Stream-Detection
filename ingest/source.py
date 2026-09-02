"""Where the transactions a replay needs come from.

Local runs read the parquet the ingestion built. A deployment has no persistent
disk, so it reads the slice that was loaded into PostgreSQL instead.
"""

from __future__ import annotations

import logging

import pandas as pd

from features.config import WINDOWS
from features.risk import LABEL_DELAY_DAYS
from ingest.config import TABLE_PATH

# The warm-up reads back as far as the longest risk window, which ends a delay
# before the transaction it describes.
HISTORY_DAYS = LABEL_DELAY_DAYS + max(WINDOWS)

log = logging.getLogger(__name__)

COLUMNS = ["transaction_id", "tx_datetime", "customer_id", "terminal_id", "amount",
           "is_fraud", "scenario"]

DTYPES = {
    "transaction_id": "int64",
    "customer_id": "int32",
    "terminal_id": "int32",
    "amount": "float32",
    "is_fraud": "int8",
    "scenario": "int8",
}

# The slice is 13 MB once it is a frame, and 456 MB while one query materialises it.
# Streaming it in pieces holds the transient to 187 MB, and is no slower.
READ_CHUNK = 25_000


def slice_bounds(start: pd.Timestamp, days: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Everything the warm-up and the replay together read."""
    return start - pd.Timedelta(days=HISTORY_DAYS), start + pd.Timedelta(days=days)


def from_parquet(first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    # Imported here so a serving image carries neither the reader nor the downloader.
    from ingest.prepare import load_table

    table = load_table()
    return table[(table.tx_datetime >= first) & (table.tx_datetime < last)]


def from_database(first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    from sqlalchemy import text

    from db.session import engine

    query = text(
        f"SELECT {', '.join(COLUMNS)} FROM transactions"
        " WHERE tx_datetime >= :first AND tx_datetime < :last"
        " ORDER BY tx_datetime"
    )
    params = {"first": first, "last": last}

    with engine.connect().execution_options(stream_results=True) as connection:
        pieces = [
            piece.astype(DTYPES)
            for piece in pd.read_sql(query, connection, params=params, chunksize=READ_CHUNK)
        ]
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=COLUMNS)


def load_slice(first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    """Prefers the local file, so a developer with a corpus never queries the database."""
    if TABLE_PATH.exists():
        source = "parquet"
        frame = from_parquet(first, last)
    else:
        source = "database"
        frame = from_database(first, last)

    log.info("%d transactions from %s, %s to %s", len(frame), source, first.date(), last.date())
    return frame[COLUMNS].reset_index(drop=True)


def replay_slice(start: pd.Timestamp, days: int) -> pd.DataFrame:
    """The history the warm-up needs and the window the producer replays, in one read."""
    first, last = slice_bounds(start, days)
    return load_slice(first, last)
