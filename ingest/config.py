"""Where the simulated transaction log comes from and how it is split."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = Path(os.getenv("RAW_DIR", ROOT / "data" / "raw"))
TABLE_PATH = Path(os.getenv("TABLE_PATH", ROOT / "data" / "transactions.parquet"))

# One pickle per simulated day, published by the Fraud Detection Handbook (ULB).
SOURCE_REPO = "Fraud-Detection-Handbook/simulated-data-raw"
SOURCE_URL = f"https://raw.githubusercontent.com/{SOURCE_REPO}/main/data"

FIRST_DAY = date(2018, 4, 1)
LAST_DAY = date(2018, 9, 30)

# The detector is fitted on the first block, and scored on the last one. The gap
# between them is the delay a real fraud label takes to come back from a dispute.
TRAIN_END = date(2018, 6, 30)
DELAY_DAYS = 7
TEST_START = date(2018, 7, 8)

DOWNLOAD_WORKERS = 8
REQUEST_TIMEOUT = 30
