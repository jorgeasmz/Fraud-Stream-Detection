"""Replays the stored transactions, releasing each label once its delay is up."""

from __future__ import annotations

import argparse
import logging
import time

import pandas as pd
from redis import Redis

from features.risk import LABEL_DELAY_DAYS
from ingest.prepare import load_table
from stream.config import EVENT_MAXLEN, EVENT_STREAM, REDIS_URL, REPLAY_SPEEDUP
from stream.events import label_event, transaction_event

log = logging.getLogger(__name__)

EPOCH = pd.Timestamp("1970-01-01")


def timeline(table: pd.DataFrame, delay_days: int = LABEL_DELAY_DAYS) -> list[tuple[float, dict]]:
    """One ordered sequence, so a label can never precede the transaction it judges."""
    delay = delay_days * 86_400
    events: list[tuple[float, dict]] = []
    for row in table.itertuples():
        moment = float((row.tx_datetime - EPOCH).total_seconds())
        events.append((moment, transaction_event(row)))
        events.append((moment + delay, label_event(row)))
    events.sort(key=lambda item: item[0])
    return events


def replay(
    client: Redis,
    events: list[tuple[float, dict]],
    speedup: float = REPLAY_SPEEDUP,
    stream: str = EVENT_STREAM,
) -> int:
    started = time.perf_counter()
    origin = events[0][0] if events else 0.0

    for moment, event in events:
        # Simulated time runs `speedup` times faster than the wall clock.
        due = (moment - origin) / speedup
        behind = due - (time.perf_counter() - started)
        if behind > 0:
            time.sleep(behind)
        client.xadd(stream, event, maxlen=EVENT_MAXLEN, approximate=True)

    return len(events)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="simulated days to replay")
    parser.add_argument("--start", default=None, help="first day, defaults to the test period")
    parser.add_argument("--speedup", type=float, default=REPLAY_SPEEDUP)
    args = parser.parse_args()

    table = load_table()
    first = pd.Timestamp(args.start) if args.start else pd.Timestamp("2018-07-08")
    window = table[
        (table.tx_datetime >= first) & (table.tx_datetime < first + pd.Timedelta(days=args.days))
    ]
    log.info("replaying %d transactions from %s", len(window), first.date())

    client = Redis.from_url(REDIS_URL)
    emitted = replay(client, timeline(window), args.speedup)
    log.info("emitted %d events", emitted)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
