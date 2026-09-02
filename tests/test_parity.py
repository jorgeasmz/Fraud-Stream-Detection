"""The batch and streaming feature paths have to produce the same numbers."""

from __future__ import annotations

import fakeredis
import numpy as np
import pandas as pd
import pytest

from features.config import FEATURE_COLUMNS
from features.offline import build_features
from features.online import Transaction, WindowStore
from features.risk import build_risk_features, risk_columns


@pytest.fixture
def store():
    return WindowStore(fakeredis.FakeRedis())


def replayed_table(rows: int = 400, seed: int = 7) -> pd.DataFrame:
    """A dense sequence over 45 days, so every window length is exercised."""
    rng = np.random.default_rng(seed)
    minutes = np.sort(rng.integers(0, 45 * 24 * 60, size=rows))
    table = pd.DataFrame(
        {
            "transaction_id": np.arange(rows),
            "tx_datetime": pd.Timestamp("2024-01-01") + pd.to_timedelta(minutes, unit="m"),
            "customer_id": rng.integers(1, 7, size=rows).astype("int32"),
            "terminal_id": rng.integers(1, 6, size=rows).astype("int32"),
            "amount": rng.gamma(2.0, 30.0, size=rows).round(2).astype("float32"),
        }
    )
    # A zero amount is what made the unregularised deviation ratio unbounded.
    table.loc[table.index[5], "amount"] = np.float32(0.0)
    return table


def stream(table: pd.DataFrame, store: WindowStore) -> pd.DataFrame:
    rows = [
        store.score_and_record(
            Transaction(
                transaction_id=int(row.transaction_id),
                tx_datetime=row.tx_datetime.to_pydatetime(),
                customer_id=int(row.customer_id),
                terminal_id=int(row.terminal_id),
                amount=float(row.amount),
            )
        )
        for row in table.itertuples()
    ]
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)


def test_the_streaming_path_reproduces_every_batch_feature(store):
    table = replayed_table()

    expected = build_features(table)
    produced = stream(table, store)

    for column in FEATURE_COLUMNS:
        np.testing.assert_allclose(
            produced[column].to_numpy(dtype=np.float64),
            expected[column].to_numpy(dtype=np.float64),
            rtol=1e-5,
            atol=1e-5,
            err_msg=f"{column} diverges between the batch and streaming paths",
        )


def test_a_window_does_not_see_the_arriving_transaction(store):
    table = replayed_table(rows=40)

    produced = stream(table, store)

    assert produced.loc[0, "customer_count_30d"] == 0.0
    assert produced.loc[0, "customer_mean_30d"] == 0.0


def test_state_is_dropped_once_it_leaves_the_longest_window(store):
    early = Transaction(1, pd.Timestamp("2024-01-01").to_pydatetime(), 1, 1, 50.0)
    late = Transaction(2, pd.Timestamp("2024-03-01").to_pydatetime(), 1, 1, 50.0)

    store.score_and_record(early)
    row = store.score_and_record(late)

    assert row["customer_count_30d"] == 0.0
    # The rewrite drops what left the window, so the key holds only the new record.
    assert len(store._read("customer", 1)) == 1


def test_windows_are_independent_per_entity(store):
    first = Transaction(1, pd.Timestamp("2024-01-01 10:00").to_pydatetime(), 1, 9, 50.0)
    second = Transaction(2, pd.Timestamp("2024-01-01 11:00").to_pydatetime(), 2, 9, 50.0)

    store.score_and_record(first)
    row = store.score_and_record(second)

    assert row["customer_count_1d"] == 0.0
    assert row["terminal_count_1d"] == 1.0


def labelled_table(table: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    labelled = table.copy()
    labelled["is_fraud"] = (rng.random(len(table)) < 0.08).astype("int8")
    labelled["scenario"] = labelled["is_fraud"] * 2
    return labelled


def stream_risk(table: pd.DataFrame, store) -> pd.DataFrame:
    """Replays transactions in time order, releasing each label once its delay is up."""
    from features.online import ResolvedLabel

    pending = list(table.itertuples())
    released = 0
    rows = []

    for row in table.itertuples():
        now = (row.tx_datetime - pd.Timestamp("1970-01-01")).total_seconds()
        while released < len(pending):
            candidate = pending[released]
            resolved = (
                candidate.tx_datetime - pd.Timestamp("1970-01-01")
            ).total_seconds() + store.delay_seconds
            if resolved > now:
                break
            store.observe(
                ResolvedLabel(
                    transaction_id=int(candidate.transaction_id),
                    tx_datetime=candidate.tx_datetime.to_pydatetime(),
                    customer_id=int(candidate.customer_id),
                    terminal_id=int(candidate.terminal_id),
                    is_fraud=int(candidate.is_fraud),
                )
            )
            released += 1

        rows.append(
            store.features(
                Transaction(
                    transaction_id=int(row.transaction_id),
                    tx_datetime=row.tx_datetime.to_pydatetime(),
                    customer_id=int(row.customer_id),
                    terminal_id=int(row.terminal_id),
                    amount=float(row.amount),
                )
            )
        )

    return pd.DataFrame(rows, columns=risk_columns())


def test_the_streaming_path_reproduces_every_delayed_risk_feature():
    from features.online import RiskStore

    table = labelled_table(replayed_table())
    store = RiskStore(fakeredis.FakeRedis())

    expected = build_risk_features(table)
    produced = stream_risk(table, store)

    for column in risk_columns():
        np.testing.assert_allclose(
            produced[column].to_numpy(dtype=np.float64),
            expected[column].to_numpy(dtype=np.float64),
            rtol=1e-5,
            atol=1e-5,
            err_msg=f"{column} diverges between the batch and streaming paths",
        )


def test_a_label_inside_the_delay_is_not_visible_online():
    from features.online import ResolvedLabel, RiskStore

    store = RiskStore(fakeredis.FakeRedis())
    fraud_time = pd.Timestamp("2024-01-01 10:00").to_pydatetime()
    store.observe(ResolvedLabel(1, fraud_time, 1, 9, 1))

    two_days_later = Transaction(2, pd.Timestamp("2024-01-03").to_pydatetime(), 5, 9, 20.0)
    ten_days_later = Transaction(3, pd.Timestamp("2024-01-11").to_pydatetime(), 5, 9, 20.0)

    assert store.features(two_days_later)["terminal_risk_30d"] == 0.0
    assert store.features(ten_days_later)["terminal_risk_30d"] == 1.0
