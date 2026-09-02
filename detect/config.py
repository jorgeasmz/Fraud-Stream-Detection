"""Detector settings."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", ROOT / "artifacts"))

N_ESTIMATORS = 200
MAX_SAMPLES = 4096
RANDOM_STATE = 42

MAX_ITER = 300
LEARNING_RATE = 0.1
