from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from detect.detectors import (
    AmountRanker,
    CustomerDeviationRanker,
    IsolationForestDetector,
    RandomScorer,
)
from evaluation.offline import assert_label_free
from features.config import FEATURE_COLUMNS
from features.risk import risk_columns


def matrix(rows: int = 64) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        rng.random((rows, len(FEATURE_COLUMNS))).astype("float32"), columns=FEATURE_COLUMNS
    )


def test_every_scorer_returns_one_score_per_row():
    features = matrix()
    labels = np.zeros(len(features), dtype=int)

    for detector in (
        RandomScorer(),
        AmountRanker(),
        CustomerDeviationRanker(),
        IsolationForestDetector(columns=FEATURE_COLUMNS, max_samples=16, n_estimators=4),
    ):
        detector.fit(features, labels)

        assert detector.score(features).shape == (len(features),)


def test_a_larger_amount_scores_higher():
    features = matrix(2)
    features.loc[0, "amount"] = 10.0
    features.loc[1, "amount"] = 500.0

    scores = AmountRanker().score(features)

    assert scores[1] > scores[0]


def test_the_forest_reads_only_the_columns_it_declares():
    features = matrix()
    detector = IsolationForestDetector(columns=["amount"], max_samples=16, n_estimators=4)
    detector.fit(features, np.zeros(len(features), dtype=int))

    assert detector.model.n_features_in_ == 1


def test_a_label_free_detector_may_not_read_a_risk_column():
    leaking = IsolationForestDetector(columns=[*FEATURE_COLUMNS, risk_columns()[0]])

    with pytest.raises(AssertionError, match="label-derived"):
        assert_label_free(leaking)


def test_the_guard_passes_a_detector_that_stays_label_free():
    # Reaching the next line without raising is the assertion.
    assert_label_free(IsolationForestDetector(columns=FEATURE_COLUMNS))
