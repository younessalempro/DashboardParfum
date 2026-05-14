"""
models/listing.py
=================
A site-specific product page.

One canonical product can have 0..N listings (at most one per retail site).
`canonical_product_id` is nullable while awaiting match review.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Listing(Base):
    __tablename__ = "listing"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_product_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("canonical_product.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site: Mapped[str] = mapped_column(
        sa.Enum("primor", "sephora", "nocibe", name="site_enum"),
        nullable=False,
        index=True,
    )
    site_product_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    name_on_site: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    brand_on_site: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=True
    )

    # Relationships
    canonical_product: Mapped[CanonicalProduct | None] = relationship(  # noqa: F821
        "CanonicalProduct", back_populates="listings"
    )
    price_snapshots: Mapped[list[PriceSnapshot]] = relationship(  # noqa: F821
        "PriceSnapshot", back_populates="listing", lazy="select"
    )
    review_queue_entries: Mapped[list[MatchReviewQueue]] = relationship(  # noqa: F821
        "MatchReviewQueue", back_populates="listing"
    )

    __table_args__ = (
        sa.UniqueConstraint("site", "site_product_id", name="uq_listing_site_product"),
    )

    def __repr__(self) -> str:
        return f"<Listing {self.site}:{self.site_product_id}>"
