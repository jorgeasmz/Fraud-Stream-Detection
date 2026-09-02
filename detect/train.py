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
    decision = {
        "threshold": alert_threshold(scores, days),
        "daily_budget": DAILY_BUDGET,
        "training_days": days,
        "training_rows": int(is_train.sum()),
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
