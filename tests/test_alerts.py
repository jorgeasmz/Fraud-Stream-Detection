from __future__ import annotations

from datetime import datetime

import pytest

from db.alerts import _quantile, from_event


def event(**overrides) -> dict[str, str]:
    base = {
        "transaction_id": "42",
        "epoch": repr(float(datetime(2018, 7, 8, 10, 0).timestamp())),
        "customer_id": "7",
        "terminal_id": "9",
        "amount": "123.45",
        "score": "0.87",
        "latency_ms": "1.5",
        "is_fraud": "1",
        "scenario": "2",
    }
    return {**base, **overrides}


def test_an_alert_event_becomes_a_row():
    row = from_event(
        event(epoch=repr(float((datetime(2018, 7, 8, 10) - datetime(1970, 1, 1)).total_seconds())))
    )

    assert row["transaction_id"] == 42
    assert row["tx_datetime"] == datetime(2018, 7, 8, 10, 0)
    assert row["amount"] == pytest.approx(123.45)
    assert row["outcome"] == 1
    assert row["scenario"] == 2


def test_the_quantile_of_nothing_is_nothing():
    assert _quantile([], 0.5) is None


def test_the_quantile_reads_the_sorted_position():
    values = [float(index) for index in range(1, 101)]

    assert _quantile(values, 0.5) == 51.0
    assert _quantile(values, 0.95) == 96.0
    assert _quantile(values, 1.0) == 100.0


def test_the_model_card_reports_the_recorded_run():
    from detect.publish import build_card

    card = build_card(
        {
            "threshold": 0.01643,
            "daily_budget": 100,
            "training_days": 91,
            "training_rows": 872795,
            "held_out_rows": 813843,
            "held_out_days": 85,
            "card_precision_at_budget": 0.5613,
            "precision_at_budget": 0.6195,
            "scenario_recall": {"1": 0.9161, "2": 0.6643, "3": 0.8191},
            "columns": [f"f{index}" for index in range(30)],
        }
    )

    assert "0.620" in card
    assert "0.561" in card
    assert "30 features per transaction" in card
    # The compromised-terminal recall is quoted in the prose as well as the table.
    assert card.count("0.664") == 2
