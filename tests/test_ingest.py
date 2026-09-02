from __future__ import annotations

import pickle
from datetime import date

import pandas as pd
import pytest

from ingest import download
from ingest.prepare import COLUMNS, build_table, read_day


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_simulated_days_covers_both_ends():
    days = download.simulated_days(date(2018, 4, 1), date(2018, 4, 3))

    assert days == [date(2018, 4, 1), date(2018, 4, 2), date(2018, 4, 3)]


def test_simulated_days_rejects_a_reversed_range():
    with pytest.raises(ValueError):
        download.simulated_days(date(2018, 4, 3), date(2018, 4, 1))


def test_fetch_day_serves_a_cached_file_without_a_request(tmp_path, monkeypatch):
    cached = tmp_path / "2018-04-01.pkl"
    cached.write_bytes(b"already here")

    def explode(*args, **kwargs):
        raise AssertionError("a cached day must not be downloaded again")

    monkeypatch.setattr(download.requests, "get", explode)

    assert download.fetch_day(date(2018, 4, 1), tmp_path) == cached


def test_fetch_day_leaves_no_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(download.requests, "get", lambda *a, **k: FakeResponse(b"payload"))

    path = download.fetch_day(date(2018, 4, 2), tmp_path)

    assert path.read_bytes() == b"payload"
    assert list(tmp_path.glob("*.partial")) == []


def published_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "TRANSACTION_ID": [1],
            "TX_DATETIME": pd.to_datetime(["2018-04-01 10:00"]),
            # The published files store the identifiers as objects.
            "CUSTOMER_ID": pd.Series(["7"], dtype="object"),
            "TERMINAL_ID": pd.Series(["9"], dtype="object"),
            "TX_AMOUNT": [12.5],
            "TX_TIME_SECONDS": pd.Series(["3600"], dtype="object"),
            "TX_TIME_DAYS": pd.Series(["0"], dtype="object"),
            "TX_FRAUD": [0],
            "TX_FRAUD_SCENARIO": [0],
        }
    )


def test_read_day_renames_and_narrows_the_types(tmp_path):
    path = tmp_path / "day.pkl"
    path.write_bytes(pickle.dumps(published_frame()))

    frame = read_day(path)

    assert list(frame.columns) == list(COLUMNS.values())
    assert frame["customer_id"].dtype == "int32"
    assert frame["amount"].dtype == "float32"


def test_read_day_rejects_a_file_missing_a_column(tmp_path):
    path = tmp_path / "day.pkl"
    path.write_bytes(pickle.dumps(published_frame().drop(columns=["TX_FRAUD"])))

    with pytest.raises(ValueError, match="TX_FRAUD"):
        read_day(path)


def test_build_table_orders_by_time_across_files(tmp_path):
    late = published_frame()
    early = published_frame()
    early["TX_DATETIME"] = pd.to_datetime(["2018-04-01 08:00"])
    (tmp_path / "b.pkl").write_bytes(pickle.dumps(late))
    (tmp_path / "a.pkl").write_bytes(pickle.dumps(early))

    table = build_table(tmp_path, tmp_path / "out.parquet")

    assert table["tx_datetime"].is_monotonic_increasing
    assert (tmp_path / "out.parquet").exists()


def test_build_table_reports_an_empty_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_table(tmp_path, tmp_path / "out.parquet")
