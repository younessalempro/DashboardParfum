"""
models/scrape_job.py
====================
Tracks a single on-demand scrape run.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ScrapeJob(Base):
    __tablename__ = "scrape_job"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        sa.Enum("running", "done", "failed", name="scrape_job_status_enum"),
        nullable=False,
        default="running",
    )
    sites: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=True
    )
    items_added: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    items_updated: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    items_errored: Mapped[int] = mapped_column(sa.Integer, server_default="0")

    # Relationship
    errors: Mapped[list[ScrapeError]] = relationship(  # noqa: F821
        "ScrapeError", back_populates="job", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<ScrapeJob {self.id} status={self.status}>"
