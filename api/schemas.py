"""What the endpoints return."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: int
    tx_datetime: datetime
    customer_id: int
    terminal_id: int
    amount: float
    score: float
    latency_ms: float
    outcome: int | None
    scenario: int | None


class AlertPage(BaseModel):
    alerts: list[AlertOut]
    next_before: int | None


class Summary(BaseModel):
    alerts: int
    resolved: int
    frauds: int
    precision: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    by_scenario: dict[str, int]
