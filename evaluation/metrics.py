"""Metrics for a detector whose output a fixed-size review team consumes."""

from __future__ import annotations

import numpy as np
import pandas as pd


def precision_at_k(scores: np.ndarray, labels: np.ndarray, k: int) -> float:
    """Share of frauds among the k highest-scoring transactions."""
    if k <= 0:
        raise ValueError("k must be positive")
    top = np.argsort(-scores, kind="stable")[:k]
    return float(labels[top].mean())


def daily_precision_at_k(frame: pd.DataFrame, k: int) -> float:
    """Precision@k applied per day and averaged, which is how a queue is worked."""
    daily = [
        precision_at_k(day["score"].to_numpy(), day["is_fraud"].to_numpy(), min(k, len(day)))
        for _, day in frame.groupby(frame["tx_datetime"].dt.date, sort=True)
    ]
    return float(np.mean(daily)) if daily else 0.0


def card_precision_at_k(frame: pd.DataFrame, k: int) -> float:
    """Share of compromised cards among the k cards a day's alerts point at.

    A team investigates cards, not transactions: several alerts on one card cost
    one investigation, and transaction precision counts them as several hits.
    """
    daily = []
    for _, day in frame.groupby(frame["tx_datetime"].dt.date, sort=True):
        per_card = day.groupby("customer_id").agg(score=("score", "max"), hit=("is_fraud", "max"))
        top = per_card.sort_values("score", ascending=False).head(k)
        if len(top):
            daily.append(float(top["hit"].mean()))
    return float(np.mean(daily)) if daily else 0.0


def scenario_recall(frame: pd.DataFrame, k: int) -> dict[int, float]:
    """Recall per fraud scenario at the daily transaction budget."""
    flagged = np.zeros(len(frame), dtype=bool)
    position = 0
    for _, day in frame.groupby(frame["tx_datetime"].dt.date, sort=True):
        order = np.argsort(-day["score"].to_numpy(), kind="stable")[: min(k, len(day))]
        flagged[position + order] = True
        position += len(day)

    caught = frame.assign(flagged=flagged)
    frauds = caught[caught["is_fraud"] == 1]
    return {
        int(scenario): float(group["flagged"].mean())
        for scenario, group in frauds.groupby("scenario", sort=True)
    }
