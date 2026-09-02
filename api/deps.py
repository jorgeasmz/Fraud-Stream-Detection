"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from db.session import session_scope


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session
