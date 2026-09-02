"""What the service persists: one row per alert."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, SmallInteger, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Alert(Base):
    """A transaction the detector placed above the operating point.

    `outcome` is the resolved label. A replay knows it because the corpus carries
    it; a live deployment fills it in when the dispute resolves, which is why it
    is nullable rather than part of the insert contract.
    """

    __tablename__ = "alerts"

    # SQLite only auto-increments an INTEGER primary key, so the schema can be
    # created on either engine without changing what Postgres gets.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    transaction_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    tx_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    terminal_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    scenario: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    raised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # The panel pages backwards through the queue, newest first.
        Index("ix_alerts_id_desc", id.desc()),
        Index("ix_alerts_tx_datetime", tx_datetime),
    )
