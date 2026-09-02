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


# The fitted detector is published as a model repository rather than committed, so
# its version moves independently of the code that serves it.
MODEL_REPO = os.getenv("MODEL_REPO", "jorgeasmz/fraud-stream-detector")
MODEL_FILE = "detector.joblib"
DECISION_FILE = "decision.json"

# A local export takes precedence, so a fresh fit can be served before it is published.
LOCAL_ARTIFACTS = os.getenv("LOCAL_ARTIFACTS", "")
