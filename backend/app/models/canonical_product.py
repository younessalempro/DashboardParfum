"""
models/canonical_product.py
============================
The deduplicated, "real-world" perfume entity.

One canonical product may have multiple listings (one per retail site).
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CanonicalProduct(Base):
    __tablename__ = "canonical_product"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand: Mapped[str] = mapped_column(sa.Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    size_ml: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(
        sa.Enum("men", "women", "unisex", name="gender_enum"),
        nullable=True,
    )
    image_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    listings: Mapped[list[Listing]] = relationship(  # noqa: F821
        "Listing", back_populates="canonical_product", lazy="select"
    )

    __table_args__ = (
        sa.UniqueConstraint("brand", "name", "size_ml", name="uq_canonical_brand_name_size"),
    )

    def __repr__(self) -> str:
        return f"<CanonicalProduct {self.brand!r} {self.name!r} {self.size_ml}ml>"
