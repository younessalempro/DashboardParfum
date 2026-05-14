"""
models/scrape_error.py
=======================
Persists individual scrape failures for post-mortem debugging.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ScrapeError(Base):
    __tablename__ = "scrape_error"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("scrape_job.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )

    # Relationship
    job: Mapped[ScrapeJob] = relationship(  # noqa: F821
        "ScrapeJob", back_populates="errors"
    )

    def __repr__(self) -> str:
        return f"<ScrapeError job={self.job_id} site={self.site!r}>"
