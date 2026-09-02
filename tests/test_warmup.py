"""The bulk load and the event-by-event path have to leave the same state behind."""

from __future__ import annotations

import fakeredis
import numpy as np
import pandas as pd
import pytest

from features.online import ResolvedLabel, RiskStore, Transaction, WindowStore
from stream.warmup import warm
from tests.test_parity import labelled_table, replayed_table


@pytest.fixture
def table():
    return labelled_table(replayed_table(rows=300))


def observed(table: pd.DataFrame, start: pd.Timestamp, client) -> tuple[WindowStore, RiskStore]:
    windows, risks = WindowStore(client), RiskStore(client)
    for row in table[table.tx_datetime < start].itertuples():
        windows.observe(
            Transaction(
                int(row.transaction_id),
                row.tx_datetime.to_pydatetime(),
                int(row.customer_id),
                int(row.terminal_id),
                float(row.amount),
            )
        )
    ceiling = start - pd.Timedelta(days=7)
    for row in table[table.tx_datetime < ceiling].itertuples():
        risks.observe(
            ResolvedLabel(
                int(row.transaction_id),
                row.tx_datetime.to_pydatetime(),
                int(row.customer_id),
                int(row.terminal_id),
                int(row.is_fraud),
            )
        )
    return windows, risks


def test_the_bulk_load_reproduces_the_event_by_event_state(table):
    start = pd.Timestamp("2024-02-05")
    probe = Transaction(9_999, start.to_pydatetime(), 3, 2, 75.0)

    bulk_client = fakeredis.FakeRedis()
    warm(bulk_client, table, start)
    bulk = WindowStore(bulk_client).features(probe) | RiskStore(bulk_client).features(probe)

    windows, risks = observed(table, start, fakeredis.FakeRedis())
    stepwise = windows.features(probe) | risks.features(probe)

    for column, value in stepwise.items():
        assert bulk[column] == pytest.approx(value, rel=1e-6), column


def test_the_bulk_load_holds_back_labels_inside_the_delay(table):
    start = pd.Timestamp("2024-02-05")
    client = fakeredis.FakeRedis()

    warm(client, table, start)

    latest = RiskStore(client)._read("customer", 3)
    ceiling = (start - pd.Timedelta(days=7) - pd.Timestamp("1970-01-01")).total_seconds()
    assert latest.size == 0 or latest["ts"].max() < ceiling


def test_the_bulk_load_writes_nothing_for_an_empty_history():
    client = fakeredis.FakeRedis()

    counts = warm(client, labelled_table(replayed_table(rows=10)), pd.Timestamp("2023-01-01"))

    assert counts == {"windows": 0, "labels": 0}
    assert client.keys("*") == []


def test_packed_records_survive_the_round_trip():
    client = fakeredis.FakeRedis()
    store = WindowStore(client)
    moment = pd.Timestamp("2024-01-01 10:00").to_pydatetime()

    store.observe(Transaction(1, moment, 4, 8, 123.45))
    records = store._read("customer", 4)

    assert records.size == 1
    assert float(records["amount"][0]) == pytest.approx(123.45, rel=1e-6)
    assert int(records["ts"][0]) == int((pd.Timestamp(moment) - pd.Timestamp("1970-01-01")).total_seconds())
    assert np.dtype(records.dtype).itemsize == 8
