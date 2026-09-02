"""Fetches the simulated day files and caches them on disk."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests

from ingest.config import (
    DOWNLOAD_WORKERS,
    FIRST_DAY,
    LAST_DAY,
    RAW_DIR,
    REQUEST_TIMEOUT,
    SOURCE_URL,
)

log = logging.getLogger(__name__)


def simulated_days(first: date = FIRST_DAY, last: date = LAST_DAY) -> list[date]:
    span = (last - first).days
    if span < 0:
        raise ValueError(f"{last} precedes {first}")
    return [first + timedelta(days=offset) for offset in range(span + 1)]


def fetch_day(day: date, directory: Path = RAW_DIR) -> Path:
    """Downloads one day unless it is already cached, and returns its path."""
    target = directory / f"{day.isoformat()}.pkl"
    if target.exists() and target.stat().st_size > 0:
        return target

    response = requests.get(f"{SOURCE_URL}/{day.isoformat()}.pkl", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    directory.mkdir(parents=True, exist_ok=True)
    # Written under a temporary name so an interrupted run leaves no partial file.
    staging = target.with_suffix(".partial")
    staging.write_bytes(response.content)
    staging.rename(target)
    return target


def fetch_all(days: list[date] | None = None, directory: Path = RAW_DIR) -> list[Path]:
    days = days or simulated_days()
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        paths = list(pool.map(lambda day: fetch_day(day, directory), days))
    log.info("cached %d days in %s", len(paths), directory)
    return paths


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_all()
