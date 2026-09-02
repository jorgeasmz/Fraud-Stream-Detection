"""Fits every detector on the training period and scores the test period."""

from __future__ import annotations

import argparse
import logging
import time

import pandas as pd

from detect.detectors import (
    AmountRanker,
    CustomerDeviationRanker,
    Detector,
    GradientBoostingDetector,
    IsolationForestDetector,
    RandomScorer,
)
from evaluation.config import BUDGET_SWEEP, DAILY_BUDGET
from evaluation.metrics import card_precision_at_k, daily_precision_at_k, scenario_recall
from features.config import FEATURE_COLUMNS
from features.offline import build_features, split_periods
from features.risk import build_risk_features, risk_columns
from ingest.config import TEST_START, TRAIN_END
from ingest.prepare import load_table

log = logging.getLogger(__name__)

DEVIATION_COLUMNS = [c for c in FEATURE_COLUMNS if c.startswith("amount_over")]
AMOUNT_AND_DEVIATION = ["amount", *DEVIATION_COLUMNS]


ALL_COLUMNS = [*FEATURE_COLUMNS, *risk_columns()]


def detectors() -> list[Detector]:
    return [
        RandomScorer(),
        AmountRanker(),
        CustomerDeviationRanker(),
        IsolationForestDetector(columns=FEATURE_COLUMNS, suffix="_18"),
        IsolationForestDetector(columns=AMOUNT_AND_DEVIATION, suffix="_4"),
        GradientBoostingDetector(columns=FEATURE_COLUMNS, suffix="_labelfree"),
        GradientBoostingDetector(columns=ALL_COLUMNS, suffix="_with_risk"),
    ]


def assert_label_free(detector: Detector) -> None:
    """A detector that claims no labels must not read a label-derived column."""
    if detector.uses_labels:
        return
    leaked = sorted(set(detector.columns or []) & set(risk_columns()))
    if leaked:
        raise AssertionError(f"{detector.name} reads label-derived columns {leaked}")


def evaluate(budget: int = DAILY_BUDGET) -> pd.DataFrame:
    table = load_table()
    features = pd.concat([build_features(table), build_risk_features(table)], axis=1)
    is_train, is_test = split_periods(table, TRAIN_END, TEST_START)
    log.info(
        "%d features, train %d rows, test %d rows",
        features.shape[1],
        int(is_train.sum()),
        int(is_test.sum()),
    )

    labels = table["is_fraud"].to_numpy()
    test = table.loc[is_test, ["tx_datetime", "customer_id", "is_fraud", "scenario"]]

    rows = []
    for detector in detectors():
        assert_label_free(detector)
        started = time.perf_counter()
        detector.fit(features[is_train], labels[is_train])
        fit_seconds = time.perf_counter() - started

        started = time.perf_counter()
        scored = test.assign(score=detector.score(features[is_test]))
        score_seconds = time.perf_counter() - started

        row = {
            "detector": detector.name,
            "labels": detector.uses_labels,
            "card_p@100": card_precision_at_k(scored, budget),
            **{f"p@{k}": daily_precision_at_k(scored, k) for k in BUDGET_SWEEP},
            "fit_s": round(fit_seconds, 1),
            "score_s": round(score_seconds, 1),
        }
        row.update({f"recall_s{s}": v for s, v in scenario_recall(scored, budget).items()})
        rows.append(row)
        log.info("%s done", detector.name)

    return pd.DataFrame(rows).set_index("detector")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=DAILY_BUDGET)
    args = parser.parse_args()

    pd.set_option("display.width", 240)
    print(evaluate(args.budget).round(3).to_string())
