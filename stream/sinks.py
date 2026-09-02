"""Where an alert goes once it is raised."""

from __future__ import annotations

import logging
from typing import Protocol

from redis import Redis

from db.alerts import from_event, record
from db.session import session_scope
from stream.config import ALERT_MAXLEN, ALERT_STREAM

log = logging.getLogger(__name__)


class AlertSink(Protocol):
    def __call__(self, alert: dict[str, str]) -> None: ...


class RedisAlertSink:
    """Fans the alert out to whoever is watching, and keeps only a short tail."""

    def __init__(self, client: Redis, stream: str = ALERT_STREAM) -> None:
        self.client = client
        self.stream = stream

    def __call__(self, alert: dict[str, str]) -> None:
        self.client.xadd(self.stream, alert, maxlen=ALERT_MAXLEN, approximate=True)


class DatabaseAlertSink:
    """Persists the alert, which is the record the stream deliberately is not."""

    def __call__(self, alert: dict[str, str]) -> None:
        with session_scope() as session:
            record(session, from_event(alert))
