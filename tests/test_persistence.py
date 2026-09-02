"""Behaviour that depends on PostgreSQL, run in CI against a service container."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from db.alerts import from_event, recent, record, summary
from db.session import engine

pytestmark = pytest.mark.postgres


def event(transaction_id: int, outcome: str = "1") -> dict[str, str]:
    return {
        "transaction_id": str(transaction_id),
        "epoch": repr(float((datetime(2018, 7, 8, 10) - datetime(1970, 1, 1)).total_seconds())),
        "customer_id": "7",
        "terminal_id": "9",
        "amount": "123.45",
        "score": "0.87",
        "latency_ms": "1.5",
        "is_fraud": outcome,
        "scenario": "2",
    }


@pytest.fixture
def session():
    """Everything runs inside one transaction that is rolled back afterwards."""
    connection = engine.connect()
    transaction = connection.begin()
    with Session(bind=connection) as opened:
        yield opened
    transaction.rollback()
    connection.close()


def test_a_redelivered_alert_does_not_duplicate_the_row(session):
    record(session, from_event(event(1)))
    record(session, from_event(event(1)))
    session.flush()

    assert len(recent(session)) == 1


def test_a_second_alert_is_kept(session):
    record(session, from_event(event(1)))
    record(session, from_event(event(2)))
    session.flush()

    assert len(recent(session)) == 2


def test_the_summary_reads_what_was_written(session):
    record(session, from_event(event(1, outcome="1")))
    record(session, from_event(event(2, outcome="0")))
    session.flush()

    report = summary(session)

    assert report["alerts"] == 2
    assert report["precision"] == 0.5
    assert report["by_scenario"] == {"2": 2}
