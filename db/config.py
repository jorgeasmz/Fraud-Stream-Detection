"""Database connection settings."""

from __future__ import annotations

import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://fraud:fraud@localhost:5434/fraud"
)

# Kept small because a free instance caps connections and this service runs one
# consumer alongside the API in the same process.
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "3"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "2"))
