"""
models/price_snapshot.py
=========================
Append-only price log. Never update — always insert a new row.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshot"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("listing.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[float] = mapped_column(sa.Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(sa.CHAR(3), nullable=False, server_default="EUR")
    in_stock: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), index=True
    )

    # Relationship
    listing: Mapped[Listing] = relationship(  # noqa: F821
        "Listing", back_populates="price_snapshots"
    )

    __table_args__ = (
        sa.Index("ix_price_snapshot_listing_scraped", "listing_id", sa.desc("scraped_at")),
    )

    def __repr__(self) -> str:
        return f"<PriceSnapshot listing={self.listing_id} price={self.price} {self.currency}>"
