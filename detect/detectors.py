"""Scorers under one interface, so the evaluation runs the same loop over all of them.

Every score is oriented the same way: larger means more suspicious.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest

from detect.config import LEARNING_RATE, MAX_ITER, MAX_SAMPLES, N_ESTIMATORS, RANDOM_STATE


class Detector(Protocol):
    name: str
    uses_labels: bool
    columns: list[str] | None

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> None: ...

    def score(self, features: pd.DataFrame) -> np.ndarray: ...


class RandomScorer:
    """The floor: what a review queue in arbitrary order achieves."""

    name = "random"
    uses_labels = False
    columns = None

    def __init__(self, seed: int = RANDOM_STATE) -> None:
        self._rng = np.random.default_rng(seed)

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> None:
        return None

    def score(self, features: pd.DataFrame) -> np.ndarray:
        return self._rng.random(len(features))


class AmountRanker:
    """Ranking by amount alone, which is the rule a fraud team writes first."""

    name = "amount"
    uses_labels = False
    columns = None

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> None:
        return None

    def score(self, features: pd.DataFrame) -> np.ndarray:
        return features["amount"].to_numpy(dtype=np.float64)


class CustomerDeviationRanker:
    """Ranking by how far the amount sits from the customer's recent average."""

    name = "deviation"
    uses_labels = False
    columns = None

    def __init__(self, window_days: int = 30) -> None:
        self._column = f"amount_over_customer_mean_{window_days}d"

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> None:
        return None

    def score(self, features: pd.DataFrame) -> np.ndarray:
        return features[self._column].to_numpy(dtype=np.float64)


class IsolationForestDetector:
    """Unsupervised, fitted on the training period with its frauds left in."""

    def __init__(
        self,
        columns: list[str],
        suffix: str = "",
        uses_labels: bool = False,
        n_estimators: int = N_ESTIMATORS,
        max_samples: int = MAX_SAMPLES,
    ) -> None:
        self.name = f"isolation_forest{suffix}"
        self.columns = columns
        self.uses_labels = uses_labels
        self.model = IsolationForest(
            n_estimators=n_estimators,
            max_samples=max_samples,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )

    def _matrix(self, features: pd.DataFrame) -> np.ndarray:
        return features[self.columns].to_numpy(dtype=np.float32)

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> None:
        self.model.fit(self._matrix(features))

    def score(self, features: pd.DataFrame) -> np.ndarray:
        # score_samples returns higher values for inliers, so it is negated.
        return -self.model.score_samples(self._matrix(features))


class GradientBoostingDetector:
    """Supervised, so it can use the delayed fraud labels an unsupervised model cannot."""

    def __init__(self, columns: list[str], suffix: str = "") -> None:
        self.name = f"supervised{suffix}"
        self.columns = columns
        self.uses_labels = True
        self.model = HistGradientBoostingClassifier(
            max_iter=MAX_ITER,
            learning_rate=LEARNING_RATE,
            early_stopping=True,
            random_state=RANDOM_STATE,
        )

    def _matrix(self, features: pd.DataFrame) -> np.ndarray:
        return features[self.columns].to_numpy(dtype=np.float32)

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> None:
        self.model.fit(self._matrix(features), labels)

    def score(self, features: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(self._matrix(features))[:, 1]
