from __future__ import annotations

import fakeredis
import numpy as np
import pandas as pd
import pytest

from features.risk import LABEL_DELAY_DAYS
from stream.config import CONSUMER_GROUP, EVENT_STREAM, KIND_LABEL, KIND_TRANSACTION
from stream.consumer import Scorer, consume, ensure_group
from stream.events import label_event, read_label, read_transaction, transaction_event
from stream.producer import timeline


class ConstantModel:
    def __init__(self, probability: float) -> None:
        self.probability = probability
        self.seen: list[np.ndarray] = []

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        self.seen.append(matrix)
        return np.array([[1 - self.probability, self.probability]])


def row(transaction_id: int = 1, moment: str = "2024-01-01 10:00", amount: float = 42.0):
    frame = pd.DataFrame(
        {
            "transaction_id": [transaction_id],
            "tx_datetime": [pd.Timestamp(moment)],
            "customer_id": [7],
            "terminal_id": [9],
            "amount": [np.float32(amount)],
            "is_fraud": [1],
            "scenario": [2],
        }
    )
    return next(frame.itertuples())


@pytest.fixture
def client():
    return fakeredis.FakeRedis()


def scorer(client, probability: float, threshold: float) -> Scorer:
    from features.config import FEATURE_COLUMNS
    from features.risk import risk_columns

    return Scorer(client, ConstantModel(probability), threshold, [*FEATURE_COLUMNS, *risk_columns()])


def test_an_event_survives_the_round_trip():
    restored = read_transaction(transaction_event(row(amount=42.25)))

    assert restored.transaction_id == 1
    assert restored.customer_id == 7
    assert restored.amount == pytest.approx(42.25, rel=1e-6)
    assert restored.tx_datetime == pd.Timestamp("2024-01-01 10:00").to_pydatetime()


def test_a_label_carries_the_outcome():
    restored = read_label(label_event(row()))

    assert restored.is_fraud == 1


def test_the_timeline_places_a_label_after_the_transaction_it_judges():
    table = pd.DataFrame(
        {
            "transaction_id": [1],
            "tx_datetime": [pd.Timestamp("2024-01-01")],
            "customer_id": [7],
            "terminal_id": [9],
            "amount": [np.float32(10.0)],
            "is_fraud": [0],
            "scenario": [0],
        }
    )

    events = timeline(table)

    assert [event["kind"] for _, event in events] == [KIND_TRANSACTION, KIND_LABEL]
    assert events[1][0] - events[0][0] == LABEL_DELAY_DAYS * 86_400


def test_creating_the_group_twice_is_not_an_error(client):
    ensure_group(client)
    ensure_group(client)

    assert client.xinfo_groups(EVENT_STREAM)[0]["name"] == CONSUMER_GROUP.encode()


def test_a_score_below_the_threshold_raises_no_alert(client):
    assert scorer(client, 0.10, 0.90).handle(transaction_event(row())) is None


def test_a_score_above_the_threshold_carries_its_provenance(client):
    alert = scorer(client, 0.95, 0.90).handle(transaction_event(row()))

    assert alert["transaction_id"] == "1"
    assert float(alert["score"]) == pytest.approx(0.95)
    assert float(alert["latency_ms"]) >= 0.0
    # The label travels with the alert so the demo can report whether it was right.
    assert alert["is_fraud"] == "1"


def test_a_transaction_is_recorded_only_after_it_is_scored(client):
    subject = scorer(client, 0.95, 0.0)

    subject.handle(transaction_event(row(transaction_id=1, moment="2024-01-01 10:00")))
    subject.handle(transaction_event(row(transaction_id=2, moment="2024-01-01 11:00")))

    first, second = subject.model.seen
    position = subject.columns.index("customer_count_1d")
    assert first[0, position] == 0.0
    assert second[0, position] == 1.0


def test_a_label_updates_the_risk_windows_without_alerting(client):
    subject = scorer(client, 0.95, 0.0)

    assert subject.handle(label_event(row())) is None
    assert len(subject.risks._read("terminal", 9)) == 1


def test_an_unknown_kind_is_rejected(client):
    with pytest.raises(ValueError, match="unknown event kind"):
        scorer(client, 0.5, 0.5).handle({"kind": "nonsense"})


def test_consume_acknowledges_everything_it_reads(client):
    ensure_group(client)
    for index in range(3):
        client.xadd(EVENT_STREAM, transaction_event(row(transaction_id=index)))

    handled = consume(client, scorer(client, 0.95, 0.90), "worker", once=True)

    assert handled == 3
    assert client.xpending(EVENT_STREAM, CONSUMER_GROUP)["pending"] == 0
    assert client.xlen("alerts") == 3
