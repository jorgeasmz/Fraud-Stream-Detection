from __future__ import annotations

import pandas as pd
import pytest


def make_table(rows: list[tuple]) -> pd.DataFrame:
    """Builds a transaction table from (datetime, customer, terminal, amount, fraud, scenario)."""
    frame = pd.DataFrame(
        rows,
        columns=["tx_datetime", "customer_id", "terminal_id", "amount", "is_fraud", "scenario"],
    )
    frame["tx_datetime"] = pd.to_datetime(frame["tx_datetime"])
    frame["transaction_id"] = range(len(frame))
    return frame.sort_values("tx_datetime", kind="stable").reset_index(drop=True)


@pytest.fixture
def table_factory():
    return make_table
