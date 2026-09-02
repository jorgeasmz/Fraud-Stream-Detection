"""Computes the feature contract over the whole table, for fitting and scoring."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from features.config import AMOUNT_FLOOR, ENTITIES, FEATURE_COLUMNS, WINDOWS

log = logging.getLogger(__name__)


def _entity_windows(table: pd.DataFrame, entity: str) -> pd.DataFrame:
    """Prior-only rolling count and mean of the amount, per entity and window."""
    key = f"{entity}_id"
    ordered = table.sort_values([key, "tx_datetime"], kind="stable")
    grouped = ordered.set_index("tx_datetime").groupby(key)["amount"]

    columns = {}
    for days in WINDOWS:
        # closed="left" drops the arriving transaction, which a live scorer has not seen.
        rolling = grouped.rolling(f"{days}D", closed="left")
        columns[f"{entity}_count_{days}d"] = rolling.count()
        columns[f"{entity}_mean_{days}d"] = rolling.mean()

    frame = pd.DataFrame(columns)
    frame.index = ordered.index
    return frame.sort_index()


def build_features(table: pd.DataFrame) -> pd.DataFrame:
    features = pd.DataFrame(index=table.index)
    features["amount"] = table["amount"].astype("float32")
    features["hour"] = table["tx_datetime"].dt.hour.astype("float32")
    features["is_weekend"] = (table["tx_datetime"].dt.dayofweek >= 5).astype("float32")

    for entity in ENTITIES:
        windows = _entity_windows(table, entity)
        for column in windows.columns:
            features[column] = windows[column].astype("float32")

    for days in WINDOWS:
        # Without prior history the deviation is undefined; the count column is what
        # tells the detector that, so the ratio reads zero rather than raw.
        has_history = features[f"customer_count_{days}d"] > 0
        mean = features[f"customer_mean_{days}d"]
        ratio = features["amount"] / (mean + AMOUNT_FLOOR)
        features[f"amount_over_customer_mean_{days}d"] = ratio.where(has_history, 0.0).astype(
            "float32"
        )

    # An empty window leaves the count and the mean as NaN, and both read as zero.
    features = features.fillna(0.0)
    return features[FEATURE_COLUMNS]


def split_periods(table: pd.DataFrame, train_end, test_start) -> tuple[np.ndarray, np.ndarray]:
    day = table["tx_datetime"].dt.date
    return (day <= train_end).to_numpy(), (day >= test_start).to_numpy()
