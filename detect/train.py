"""Fits the served detector and writes it beside the operating point it implies."""

from __future__ import annotations

import json
import logging

import joblib
import numpy as np
import pandas as pd

from detect.config import ARTIFACT_DIR
from detect.detectors import GradientBoostingDetector
from evaluation.config import DAILY_BUDGET
from evaluation.metrics import card_precision_at_k, daily_precision_at_k, scenario_recall
from features.config import FEATURE_COLUMNS
from features.offline import build_features, split_periods
from features.risk import build_risk_features, risk_columns
from ingest.config import TEST_START, TRAIN_END
from ingest.prepare import load_table

log = logging.getLogger(__name__)

MODEL_PATH = ARTIFACT_DIR / "detector.joblib"
DECISION_PATH = ARTIFACT_DIR / "decision.json"

SERVED_COLUMNS = [*FEATURE_COLUMNS, *risk_columns()]


def alert_threshold(scores: np.ndarray, days: int, budget: int = DAILY_BUDGET) -> float:
    """The score above which the expected alert rate equals the daily budget.

    A review team is a rate, not a probability, so the operating point is the
    quantile that emits `budget` alerts a day at the training period's volume.
    """
    per_day = len(scores) / days
    share = min(budget / per_day, 1.0)
    return float(np.quantile(scores, 1.0 - share))


def train() -> dict:
    table = load_table()
    features = pd.concat([build_features(table), build_risk_features(table)], axis=1)
    is_train, _ = split_periods(table, TRAIN_END, TEST_START)

    detector = GradientBoostingDetector(columns=SERVED_COLUMNS)
    detector.fit(features[is_train], table.loc[is_train, "is_fraud"].to_numpy())

    scores = detector.score(features[is_train])
    days = table.loc[is_train, "tx_datetime"].dt.date.nunique()

    # The held-out figures are recorded beside the model, so the card that documents
    # it and the run that produced it cannot drift apart.
    _, is_test = split_periods(table, TRAIN_END, TEST_START)
    scored = table.loc[is_test, ["tx_datetime", "customer_id", "is_fraud", "scenario"]].assign(
        score=detector.score(features[is_test])
    )
    threshold = alert_threshold(scores, days)
    # What the operating point actually emits on later data, which is not what
    # ranking a finished day gives and is the figure the deployment reaches.
    fired = scored[scored["score"] >= threshold]
    held_out_days = int(scored["tx_datetime"].dt.date.nunique())

    decision = {
        "threshold": threshold,
        "daily_budget": DAILY_BUDGET,
        "training_days": days,
        "training_rows": int(is_train.sum()),
        "held_out_rows": int(is_test.sum()),
        "held_out_days": held_out_days,
        "alerts_per_day_at_threshold": round(len(fired) / held_out_days, 1),
        "precision_at_threshold": round(float(fired["is_fraud"].mean()), 4),
        "card_precision_at_budget": round(card_precision_at_k(scored, DAILY_BUDGET), 4),
        "precision_at_budget": round(daily_precision_at_k(scored, DAILY_BUDGET), 4),
        "scenario_recall": {
            str(scenario): round(value, 4)
            for scenario, value in scenario_recall(scored, DAILY_BUDGET).items()
        },
        "columns": SERVED_COLUMNS,
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(detector.model, MODEL_PATH)
    DECISION_PATH.write_text(json.dumps(decision, indent=2) + "\n")
    log.info("threshold %.6f over %d days", decision["threshold"], days)
    return decision


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(json.dumps({k: v for k, v in train().items() if k != "columns"}, indent=2))
