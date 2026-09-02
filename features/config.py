"""The feature contract shared by the batch and the streaming paths."""

from __future__ import annotations

# Window lengths in days, per entity. The longest one decides how much state the
# streaming path has to keep.
WINDOWS = (1, 7, 30)

ENTITIES = ("customer", "terminal")

# The deviation ratio is regularised by one currency unit, so a customer whose prior
# window averages zero does not produce an unbounded feature.
AMOUNT_FLOOR = 1.0


def window_columns() -> list[str]:
    names: list[str] = []
    for entity in ENTITIES:
        for days in WINDOWS:
            names.append(f"{entity}_count_{days}d")
            names.append(f"{entity}_mean_{days}d")
    for days in WINDOWS:
        names.append(f"amount_over_customer_mean_{days}d")
    return names


FEATURE_COLUMNS = ["amount", "hour", "is_weekend", *window_columns()]
