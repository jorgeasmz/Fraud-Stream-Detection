"""Service settings."""

from __future__ import annotations

import os

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

# The free tier gives one service, so the scorer runs beside the API rather than
# as its own worker. Locally the two are separate processes.
RUN_CONSUMER = os.getenv("RUN_CONSUMER", "0") == "1"
RUN_REPLAY = os.getenv("RUN_REPLAY", "0") == "1"

REPLAY_START = os.getenv("REPLAY_START", "2018-07-08")
REPLAY_DAYS = int(os.getenv("REPLAY_DAYS", "7"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", "50"))
MAX_PAGE_LIMIT = 200
