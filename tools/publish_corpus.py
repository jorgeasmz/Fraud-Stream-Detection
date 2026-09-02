"""Loads the slice a deployment replays into PostgreSQL.

Run once against the target database. The rows are copied rather than inserted,
since the slice is hundreds of thousands of them and this is a migration of data
rather than a request path.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging

import pandas as pd
from sqlalchemy import text

from db.session import engine
from ingest.prepare import load_table
from ingest.source import COLUMNS, slice_bounds

log = logging.getLogger(__name__)


def rows_to_copy(frame: pd.DataFrame) -> io.StringIO:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(frame[COLUMNS].itertuples(index=False, name=None))
    buffer.seek(0)
    return buffer


def publish(start: pd.Timestamp, days: int, replace: bool = True) -> int:
    first, last = slice_bounds(start, days)
    table = load_table()
    window = table[(table.tx_datetime >= first) & (table.tx_datetime < last)]

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            if replace:
                cursor.execute("TRUNCATE transactions")
            with cursor.copy(
                f"COPY transactions ({', '.join(COLUMNS)}) FROM STDIN WITH (FORMAT CSV)"
            ) as copy:
                copy.write(rows_to_copy(window).read())
        raw.commit()
    finally:
        raw.close()

    with engine.connect() as connection:
        stored = connection.execute(text("SELECT count(*) FROM transactions")).scalar_one()
    log.info("%d rows stored, %s to %s", stored, first.date(), last.date())
    return int(stored)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-07-08")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    publish(pd.Timestamp(args.start), args.days)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
