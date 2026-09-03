from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.deps import get_session
from api.main import app
from db.models import Alert, Base


def make_alert(index: int, outcome: int | None = 0, scenario: int = 0, latency: float = 1.0):
    return Alert(
        transaction_id=index,
        tx_datetime=datetime(2018, 7, 8, 10, 0),
        customer_id=index,
        terminal_id=index,
        amount=100.0 + index,
        score=0.5,
        latency_ms=latency,
        outcome=outcome,
        scenario=scenario,
    )


@pytest.fixture
def session():
    # The endpoints run in a threadpool, and an in-memory database is bound to the
    # thread that opened it unless one connection is shared.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as opened:
        yield opened


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_root_answers_a_head_probe(client):
    # A platform health check sends HEAD, and a GET-only route answers it with 405.
    assert client.head("/").status_code == 200


def test_the_root_reports_the_service(client):
    body = client.get("/").json()

    assert body["service"] == "fraud-stream-detection"
    assert body["watchers"] == 0


def test_an_empty_queue_pages_to_nothing(client):
    body = client.get("/alerts").json()

    assert body == {"alerts": [], "next_before": None}


def test_alerts_arrive_newest_first(client, session):
    session.add_all(make_alert(index) for index in range(3))
    session.commit()

    body = client.get("/alerts").json()

    assert [alert["transaction_id"] for alert in body["alerts"]] == [2, 1, 0]
    assert body["next_before"] is None


def test_a_full_page_carries_a_cursor_to_the_next(client, session):
    session.add_all(make_alert(index) for index in range(5))
    session.commit()

    first = client.get("/alerts", params={"limit": 2}).json()
    second = client.get("/alerts", params={"limit": 2, "before": first["next_before"]}).json()

    assert [alert["transaction_id"] for alert in first["alerts"]] == [4, 3]
    assert [alert["transaction_id"] for alert in second["alerts"]] == [2, 1]


def test_a_page_beyond_the_cap_is_rejected(client):
    assert client.get("/alerts", params={"limit": 5000}).status_code == 422


def test_stats_on_an_empty_queue_reports_no_precision(client):
    body = client.get("/stats").json()

    assert body["alerts"] == 0
    assert body["precision"] is None
    assert body["latency_p50_ms"] is None


def test_stats_measures_precision_over_resolved_alerts_only(client, session):
    session.add_all(
        [
            make_alert(1, outcome=1, scenario=2),
            make_alert(2, outcome=0, scenario=0),
            make_alert(3, outcome=None, scenario=None),
        ]
    )
    session.commit()

    body = client.get("/stats").json()

    assert body["alerts"] == 3
    assert body["resolved"] == 2
    # The unresolved alert is neither a hit nor a miss.
    assert body["precision"] == 0.5


def test_stats_reports_the_latency_spread(client, session):
    session.add_all(make_alert(index, latency=float(index)) for index in range(1, 101))
    session.commit()

    body = client.get("/stats").json()

    assert body["latency_p50_ms"] == pytest.approx(51.0, abs=1.0)
    assert body["latency_p95_ms"] == pytest.approx(96.0, abs=1.0)


def test_stats_counts_by_scenario(client, session):
    session.add_all([make_alert(1, scenario=2), make_alert(2, scenario=2), make_alert(3)])
    session.commit()

    assert client.get("/stats").json()["by_scenario"] == {"0": 1, "2": 2}


def test_a_browser_from_an_allowed_origin_is_answered(client):
    response = client.options(
        "/alerts",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_the_root_logger_gains_a_handler(monkeypatch):
    import logging

    from api.main import configure_logging

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])

    configure_logging()

    assert root.handlers


def test_a_failing_worker_is_reported_rather_than_swallowed(caplog):
    from api.main import _supervised

    def _run_consumer():
        raise RuntimeError("redis went away")

    with caplog.at_level("ERROR"):
        _supervised(_run_consumer)

    assert "_run_consumer stopped" in caplog.text
    assert "redis went away" in caplog.text
