from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from evaluation.metrics import (
    card_precision_at_k,
    daily_precision_at_k,
    precision_at_k,
    scenario_recall,
)


def frame(rows: list[tuple]) -> pd.DataFrame:
    out = pd.DataFrame(rows, columns=["tx_datetime", "customer_id", "score", "is_fraud", "scenario"])
    out["tx_datetime"] = pd.to_datetime(out["tx_datetime"])
    return out


def test_precision_at_k_reads_the_top_of_the_ranking():
    scores = np.array([0.1, 0.9, 0.8, 0.2])
    labels = np.array([0, 1, 0, 1])

    assert precision_at_k(scores, labels, 1) == 1.0
    assert precision_at_k(scores, labels, 2) == 0.5
    assert precision_at_k(scores, labels, 4) == 0.5


def test_precision_at_k_rejects_a_zero_budget():
    with pytest.raises(ValueError):
        precision_at_k(np.array([1.0]), np.array([1]), 0)


def test_daily_precision_averages_days_rather_than_pooling_them():
    # One perfect day and one empty day average to 0.5, where pooling would give 0.33.
    rows = [
        ("2024-01-01 10:00", 1, 0.9, 1, 1),
        ("2024-01-01 11:00", 2, 0.8, 1, 1),
        ("2024-01-02 10:00", 3, 0.9, 0, 0),
    ]

    assert daily_precision_at_k(frame(rows), 1) == 0.5


def test_card_precision_counts_a_card_once():
    # Three alerts on one compromised card are one investigation, not three hits.
    rows = [
        ("2024-01-01 10:00", 1, 0.9, 1, 3),
        ("2024-01-01 11:00", 1, 0.8, 1, 3),
        ("2024-01-01 12:00", 1, 0.7, 1, 3),
        ("2024-01-01 13:00", 2, 0.6, 0, 0),
    ]

    assert daily_precision_at_k(frame(rows), 2) == 1.0
    assert card_precision_at_k(frame(rows), 2) == 0.5


def test_scenario_recall_is_measured_inside_the_daily_budget():
    rows = [
        ("2024-01-01 10:00", 1, 0.9, 1, 1),
        ("2024-01-01 11:00", 2, 0.1, 1, 2),
        ("2024-01-02 10:00", 3, 0.9, 1, 2),
    ]

    recall = scenario_recall(frame(rows), 1)

    assert recall[1] == 1.0
    # One scenario-2 fraud ranks below the budget, the other is the day's top score.
    assert recall[2] == 0.5


def test_scenario_recall_scores_each_day_independently():
    rows = [
        ("2024-01-01 10:00", 1, 0.10, 1, 1),
        ("2024-01-01 11:00", 2, 0.05, 0, 0),
        ("2024-01-02 10:00", 3, 0.90, 0, 0),
    ]

    # A low absolute score still wins its own day, which a global ranking would miss.
    assert scenario_recall(frame(rows), 1)[1] == 1.0
