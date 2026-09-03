"""Replays the stored transactions, releasing each label once its delay is up."""

from __future__ import annotations

import argparse
import logging
import time

import pandas as pd
from redis import Redis
from redis.exceptions import ResponseError

from features.risk import LABEL_DELAY_DAYS
from ingest.source import replay_slice
from stream.config import (
    BACKPRESSURE_POLL_S,
    CONSUMER_GROUP,
    EVENT_MAXLEN,
    EVENT_STREAM,
    MAX_BACKLOG,
    REDIS_URL,
    REPLAY_SPEEDUP,
)
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


def backlog(client: Redis, stream: str = EVENT_STREAM, group: str = CONSUMER_GROUP) -> int | None:
    """Entries the consumer group has not read yet.

    None means the figure is unavailable: the group may not exist yet, and Redis
    reports the lag as unknown once entries have been trimmed or deleted. Reading
    that as zero would turn the throttle off exactly when the stream is full.
    """
    try:
        groups = client.xinfo_groups(stream)
    except ResponseError:
        return None

    for info in groups:
        name = info["name"]
        if (name.decode() if isinstance(name, bytes) else name) != group:
            continue
        lag = info.get("lag")
        return None if lag is None or lag < 0 else int(lag)
    return None


def replay(
    client: Redis,
    events: list[tuple[float, dict]],
    speedup: float = REPLAY_SPEEDUP,
    stream: str = EVENT_STREAM,
    ceiling: int = MAX_BACKLOG,
) -> int:
    started = time.perf_counter()
    origin = events[0][0] if events else 0.0
    stalled = 0.0

    log.info("replaying %d events at %.0fx", len(events), speedup)
    for moment, event in events:
        # Simulated time runs `speedup` times faster than the wall clock.
        due = (moment - origin) / speedup
        behind = due - (time.perf_counter() - started)
        if behind > 0:
            time.sleep(behind)

        # Slowing down is the only alternative to discarding, since the stream is
        # capped and trimming would drop transactions that were never scored.
        while True:
            lag = backlog(client, stream)
            if lag is None or lag <= ceiling:
                break
            time.sleep(BACKPRESSURE_POLL_S)
            stalled += BACKPRESSURE_POLL_S

        client.xadd(stream, event, maxlen=EVENT_MAXLEN, approximate=True)

    if stalled:
        log.info("held back %.0fs waiting for the consumer", stalled)
    return len(events)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="simulated days to replay")
    parser.add_argument("--start", default=None, help="first day, defaults to the test period")
    parser.add_argument("--speedup", type=float, default=REPLAY_SPEEDUP)
    args = parser.parse_args()

    first = pd.Timestamp(args.start) if args.start else pd.Timestamp("2018-07-08")
    table = replay_slice(first, args.days)
    window = table[table.tx_datetime >= first]
    log.info("replaying %d transactions from %s", len(window), first.date())

    client = Redis.from_url(REDIS_URL)
    emitted = replay(client, timeline(window), args.speedup)
    log.info("emitted %d events", emitted)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
