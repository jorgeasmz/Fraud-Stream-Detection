"""Transport settings."""

from __future__ import annotations

import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Transactions and resolved labels share one stream. Their relative order carries
# meaning, and two streams read by one consumer group cannot express it.
EVENT_STREAM = os.getenv("EVENT_STREAM", "events")
ALERT_STREAM = os.getenv("ALERT_STREAM", "alerts")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "scorers")

# The stream is a transport, not the record: alerts are persisted elsewhere, so the
# log is capped rather than kept.
EVENT_MAXLEN = int(os.getenv("EVENT_MAXLEN", "20000"))
ALERT_MAXLEN = int(os.getenv("ALERT_MAXLEN", "500"))

READ_COUNT = int(os.getenv("READ_COUNT", "50"))
BLOCK_MS = int(os.getenv("BLOCK_MS", "2000"))

# Simulated seconds per real second during a replay.
REPLAY_SPEEDUP = float(os.getenv("REPLAY_SPEEDUP", "3600"))

KIND_TRANSACTION = "tx"
KIND_LABEL = "label"
