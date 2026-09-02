from __future__ import annotations

from features.config import FEATURE_COLUMNS
from features.offline import build_features


def test_the_first_transaction_of_a_customer_has_no_history(table_factory):
    table = table_factory([("2024-01-01 10:00", 1, 50, 100.0, 0, 0)])

    features = build_features(table)

    assert features.loc[0, "customer_count_30d"] == 0.0
    assert features.loc[0, "customer_mean_30d"] == 0.0


def test_a_window_excludes_the_arriving_transaction(table_factory):
    table = table_factory(
        [
            ("2024-01-01 10:00", 1, 50, 10.0, 0, 0),
            ("2024-01-01 11:00", 1, 50, 90.0, 0, 0),
        ]
    )

    features = build_features(table)

    # The second row sees only the first, so its mean is 10 rather than 50.
    assert features.loc[1, "customer_count_1d"] == 1.0
    assert features.loc[1, "customer_mean_1d"] == 10.0


def test_a_window_drops_history_older_than_its_length(table_factory):
    table = table_factory(
        [
            ("2024-01-01 10:00", 1, 50, 10.0, 0, 0),
            ("2024-01-05 10:00", 1, 50, 20.0, 0, 0),
        ]
    )

    features = build_features(table)

    assert features.loc[1, "customer_count_1d"] == 0.0
    assert features.loc[1, "customer_count_7d"] == 1.0


def test_windows_are_kept_per_entity(table_factory):
    table = table_factory(
        [
            ("2024-01-01 10:00", 1, 50, 10.0, 0, 0),
            ("2024-01-01 11:00", 2, 50, 20.0, 0, 0),
        ]
    )

    features = build_features(table)

    assert features.loc[1, "customer_count_1d"] == 0.0
    assert features.loc[1, "terminal_count_1d"] == 1.0


def test_the_deviation_ratio_stays_bounded_when_the_history_averages_zero(table_factory):
    table = table_factory(
        [
            ("2024-01-01 10:00", 1, 50, 0.0, 0, 0),
            ("2024-01-01 11:00", 1, 50, 76.5, 0, 0),
        ]
    )

    features = build_features(table)

    assert features.loc[1, "amount_over_customer_mean_1d"] == 76.5


def test_the_frame_carries_the_declared_contract(table_factory):
    table = table_factory([("2024-01-06 10:00", 1, 50, 10.0, 0, 0)])

    features = build_features(table)

    assert list(features.columns) == FEATURE_COLUMNS
    assert features.notna().all().all()
    # 2024-01-06 is a Saturday.
    assert features.loc[0, "is_weekend"] == 1.0
    assert features.loc[0, "hour"] == 10.0
