"""
models/match_review_queue.py
=============================
Holds fuzzy-matched (score 80–92) listing ↔ canonical_product pairs
that need human review before the link is confirmed.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MatchReviewQueue(Base):
    __tablename__ = "match_review_queue"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("listing.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_canonical_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("canonical_product.id", ondelete="SET NULL"),
        nullable=True,
    )
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum("pending", "approved", "rejected", name="review_status_enum"),
        nullable=False,
        default="pending",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    listing: Mapped[Listing] = relationship(  # noqa: F821
        "Listing", back_populates="review_queue_entries"
    )
    candidate_canonical: Mapped[CanonicalProduct | None] = relationship(  # noqa: F821
        "CanonicalProduct"
    )

    def __repr__(self) -> str:
        return f"<MatchReviewQueue listing={self.listing_id} score={self.score} status={self.status!r}>"
