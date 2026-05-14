"""
crud/listings.py
================
Upsert helper used by Dev 1's scrapers.

The scraper calls:
    upsert_listing(db, raw_listing) -> (listing, is_new)

It returns the ORM Listing object and whether it was newly created.
The caller is responsible for committing the session.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.price_snapshot import PriceSnapshot
from app.scrapers.base import RawListing

if TYPE_CHECKING:
    pass


def upsert_listing(
    db: Session,
    raw: RawListing,
    canonical_product_id: uuid.UUID | None = None,
) -> tuple[Listing, bool]:
    """
    Insert or update a Listing from a RawListing.

    Returns (listing, is_new).

    After calling this, you should:
    1. Optionally set listing.canonical_product_id if the matcher resolved it.
    2. Call db.commit().
    """
    now = datetime.now(timezone.utc)

    # --- Look up existing listing by (site, site_product_id) ---
    listing = (
        db.query(Listing)
        .filter(Listing.site == raw.site, Listing.site_product_id == raw.site_product_id)
        .first()
    )

    is_new = listing is None
    if is_new:
        listing = Listing(
            id=uuid.uuid4(),
            site=raw.site,
            site_product_id=raw.site_product_id,
        )
        db.add(listing)

    # Update mutable fields
    listing.url = raw.url
    listing.name_on_site = raw.name
    listing.brand_on_site = raw.brand
    listing.image_url = raw.image_url
    listing.last_seen_at = now
    if canonical_product_id is not None:
        listing.canonical_product_id = canonical_product_id

    # --- Append price snapshot ---
    if raw.price is not None:
        snapshot = PriceSnapshot(
            listing_id=listing.id,
            price=raw.price,
            currency=raw.currency or "EUR",
            in_stock=raw.in_stock,
            scraped_at=now,
        )
        db.add(snapshot)

    return listing, is_new
