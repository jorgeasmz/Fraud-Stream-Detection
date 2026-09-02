"""Reading and writing the alert queue."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import Alert
from features.online import UNIX_EPOCH

# Percentiles are read over the recent tail, since the panel reports the session and
# not the lifetime of the table.
LATENCY_TAIL = 1_000


def from_event(alert: dict[str, str]) -> dict:
    return {
        "transaction_id": int(alert["transaction_id"]),
        "tx_datetime": UNIX_EPOCH + timedelta(seconds=float(alert["epoch"])),
        "customer_id": int(alert["customer_id"]),
        "terminal_id": int(alert["terminal_id"]),
        "amount": float(alert["amount"]),
        "score": float(alert["score"]),
        "latency_ms": float(alert["latency_ms"]),
        "outcome": int(alert["is_fraud"]),
        "scenario": int(alert["scenario"]),
    }


def record(session: Session, alert: dict) -> None:
    """Inserts one alert, ignoring a transaction already in the queue.

    A consumer group delivers at least once, so a redelivered message must not
    raise and must not duplicate the row.
    """
    statement = insert(Alert).values(**alert).on_conflict_do_nothing(
        index_elements=[Alert.transaction_id]
    )
    session.execute(statement)


def recent(session: Session, limit: int = 50, before: int | None = None) -> list[Alert]:
    query = select(Alert).order_by(Alert.id.desc()).limit(limit)
    if before is not None:
        query = query.where(Alert.id < before)
    return list(session.scalars(query))


def _quantile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    return values[min(int(share * len(values)), len(values) - 1)]


def summary(session: Session) -> dict:
    """What the queue looks like: volume, precision so far and the latency spread."""

    total, resolved, caught = session.execute(
        select(
            func.count(Alert.id),
            func.count(Alert.outcome),
            func.coalesce(func.sum(Alert.outcome), 0),
        )
    ).one()

    latencies = sorted(
        session.scalars(select(Alert.latency_ms).order_by(Alert.id.desc()).limit(LATENCY_TAIL))
    )

    by_scenario = dict(
        session.execute(
            select(Alert.scenario, func.count(Alert.id)).group_by(Alert.scenario)
        ).all()
    )

    return {
        "alerts": int(total),
        "resolved": int(resolved),
        "frauds": int(caught),
        "precision": round(caught / resolved, 4) if resolved else None,
        "latency_p50_ms": _quantile(latencies, 0.5),
        "latency_p95_ms": _quantile(latencies, 0.95),
        "by_scenario": {str(k): v for k, v in sorted(by_scenario.items(), key=lambda i: i[0] or 0)},
    }


def latest_moment(session: Session) -> datetime | None:
    return session.scalar(select(func.max(Alert.tx_datetime)))
