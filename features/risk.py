"""Features derived from past fraud labels, which only a supervised path may use.

A label arrives when a dispute is resolved, not when the transaction happens, so
every window here ends a fixed number of days before the transaction it describes.
"""

from __future__ import annotations

import pandas as pd

from features.config import ENTITIES, WINDOWS

LABEL_DELAY_DAYS = 7


def risk_columns(delay: int = LABEL_DELAY_DAYS) -> list[str]:
    names: list[str] = []
    for entity in ENTITIES:
        for days in WINDOWS:
            names.append(f"{entity}_risk_{days}d")
            names.append(f"{entity}_risk_count_{days}d")
    return names


def _delayed_risk(table: pd.DataFrame, entity: str, delay: int) -> pd.DataFrame:
    key = f"{entity}_id"
    ordered = table.sort_values([key, "tx_datetime"], kind="stable")
    grouped = ordered.set_index("tx_datetime").groupby(key)["is_fraud"]

    # The window that ends `delay` days back is the difference of two windows that
    # end now. An empty window reads as NaN, which would poison the subtraction.
    blind = grouped.rolling(f"{delay}D", closed="left")
    blind_sum = blind.sum().fillna(0.0)
    blind_count = blind.count().fillna(0.0)

    columns = {}
    for days in WINDOWS:
        wide = grouped.rolling(f"{delay + days}D", closed="left")
        count = wide.count().fillna(0.0) - blind_count
        total = wide.sum().fillna(0.0) - blind_sum
        columns[f"{entity}_risk_count_{days}d"] = count
        columns[f"{entity}_risk_{days}d"] = (total / count.where(count > 0)).fillna(0.0)

    frame = pd.DataFrame(columns)
    frame.index = ordered.index
    return frame.sort_index()


def build_risk_features(table: pd.DataFrame, delay: int = LABEL_DELAY_DAYS) -> pd.DataFrame:
    frames = [_delayed_risk(table, entity, delay) for entity in ENTITIES]
    return pd.concat(frames, axis=1)[risk_columns(delay)].astype("float32")
