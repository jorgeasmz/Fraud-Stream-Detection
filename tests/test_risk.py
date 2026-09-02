from __future__ import annotations

from features.risk import build_risk_features, risk_columns


def test_a_label_inside_the_delay_is_not_visible_yet(table_factory):
    table = table_factory(
        [
            ("2024-01-01 10:00", 1, 50, 10.0, 1, 2),
            ("2024-01-03 10:00", 2, 50, 10.0, 0, 0),
        ]
    )

    risk = build_risk_features(table, delay=7)

    # The fraud is two days old and its dispute has not resolved.
    assert risk.loc[1, "terminal_risk_30d"] == 0.0
    assert risk.loc[1, "terminal_risk_count_30d"] == 0.0


def test_a_label_older_than_the_delay_counts(table_factory):
    table = table_factory(
        [
            ("2024-01-01 10:00", 1, 50, 10.0, 1, 2),
            ("2024-01-10 10:00", 2, 50, 10.0, 0, 0),
        ]
    )

    risk = build_risk_features(table, delay=7)

    assert risk.loc[1, "terminal_risk_count_30d"] == 1.0
    assert risk.loc[1, "terminal_risk_30d"] == 1.0


def test_risk_is_zero_without_history(table_factory):
    table = table_factory([("2024-01-01 10:00", 1, 50, 10.0, 0, 0)])

    risk = build_risk_features(table)

    assert list(risk.columns) == risk_columns()
    assert (risk.loc[0] == 0.0).all()
