"""Reads the event stream, scores each transaction and emits the alerts."""

from __future__ import annotations

import argparse
import json
import logging
import time

import numpy as np
from redis import Redis
from redis.exceptions import ResponseError

from detect.train import DECISION_PATH, MODEL_PATH
from features.online import RiskStore, WindowStore
from stream.config import (
    ALERT_MAXLEN,
    ALERT_STREAM,
    BLOCK_MS,
    CONSUMER_GROUP,
    EVENT_STREAM,
    KIND_LABEL,
    KIND_TRANSACTION,
    READ_COUNT,
    REDIS_URL,
)
from stream.events import decode_event, read_label, read_transaction

log = logging.getLogger(__name__)


def ensure_group(client: Redis, stream: str = EVENT_STREAM, group: str = CONSUMER_GROUP) -> None:
    try:
        client.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as error:
        # A group that already exists is the normal case on every restart.
        if "BUSYGROUP" not in str(error):
            raise


class Scorer:
    """Holds the window state and the model, and turns one event into an alert or nothing."""

    def __init__(self, client: Redis, model, threshold: float, columns: list[str]) -> None:
        self.client = client
        self.model = model
        self.threshold = threshold
        self.columns = columns
        self.windows = WindowStore(client)
        self.risks = RiskStore(client)

    def _score(self, row: dict[str, float]) -> float:
        matrix = np.array([[row[column] for column in self.columns]], dtype=np.float32)
        return float(self.model.predict_proba(matrix)[0, 1])

    def handle(self, event: dict[str, str]) -> dict | None:
        if event.get("kind") == KIND_LABEL:
            self.risks.observe(read_label(event))
            return None
        if event.get("kind") != KIND_TRANSACTION:
            raise ValueError(f"unknown event kind {event.get('kind')!r}")

        started = time.perf_counter()
        transaction = read_transaction(event)
        row = {**self.windows.features(transaction), **self.risks.features(transaction)}
        score = self._score(row)
        # Recorded after scoring, so the window a transaction is judged against holds
        # only what preceded it.
        self.windows.observe(transaction)
        elapsed_ms = (time.perf_counter() - started) * 1000

        if score < self.threshold:
            return None
        return {
            "transaction_id": str(transaction.transaction_id),
            "epoch": repr(transaction.epoch),
            "customer_id": str(transaction.customer_id),
            "terminal_id": str(transaction.terminal_id),
            "amount": repr(transaction.amount),
            "score": repr(score),
            "latency_ms": repr(elapsed_ms),
            "is_fraud": event.get("is_fraud", "0"),
            "scenario": event.get("scenario", "0"),
        }

    def publish(self, alert: dict) -> None:
        self.client.xadd(ALERT_STREAM, alert, maxlen=ALERT_MAXLEN, approximate=True)


def load_scorer(client: Redis) -> Scorer:
    import joblib

    decision = json.loads(DECISION_PATH.read_text())
    return Scorer(client, joblib.load(MODEL_PATH), decision["threshold"], decision["columns"])


def consume(client: Redis, scorer: Scorer, consumer: str, once: bool = False) -> int:
    ensure_group(client)
    handled = 0

    while True:
        batches = client.xreadgroup(
            CONSUMER_GROUP, consumer, {EVENT_STREAM: ">"}, count=READ_COUNT, block=BLOCK_MS
        )
        if not batches:
            if once:
                return handled
            continue

        for _, messages in batches:
            for message_id, raw in messages:
                alert = scorer.handle(decode_event(raw))
                if alert:
                    scorer.publish(alert)
                client.xack(EVENT_STREAM, CONSUMER_GROUP, message_id)
                handled += 1

        if once:
            return handled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="scorer-1")
    args = parser.parse_args()

    # Binary responses, since the packed window state shares this connection.
    client = Redis.from_url(REDIS_URL)
    log.info("consuming %s as %s", EVENT_STREAM, args.name)
    consume(client, load_scorer(client), args.name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
