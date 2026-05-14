"""
scripts/seed.py
===============
Smoke-test seed: inserts one fake canonical product, three listings (one per
site), and one price snapshot each — then reads them back to verify the schema.

Run from the backend/ directory:
    python scripts/seed.py

Make sure DATABASE_URL is set (copy .env.example → .env and adjust if needed).
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure `backend/` is on the path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, engine, Base
from app.models.canonical_product import CanonicalProduct
from app.models.listing import Listing
from app.models.price_snapshot import PriceSnapshot

# Create all tables if they don't exist yet (handy for quick local testing
# without running Alembic).  In production, always use `alembic upgrade head`.
Base.metadata.create_all(bind=engine)


def seed() -> None:
    db = SessionLocal()
    try:
        # ------------------------------------------------------------------ #
        # 1. Canonical product
        # ------------------------------------------------------------------ #
        product = CanonicalProduct(
            id=uuid.uuid4(),
            brand="dior",
            name="sauvage eau de parfum",
            size_ml=100,
            gender="men",
            image_url="https://media.sephora.fr/p/sauvage-edp-large.jpg",
        )
        db.add(product)
        db.flush()  # get product.id before creating listings

        # ------------------------------------------------------------------ #
        # 2. Listings + price snapshots (one per site)
        # ------------------------------------------------------------------ #
        site_data = [
            {
                "site": "primor",
                "site_product_id": "primor-sauvage-100",
                "url": "https://fr.primor.eu/dior-sauvage-edp-100ml",
                "name_on_site": "Dior Sauvage EDP 100 ml",
                "brand_on_site": "Dior",
                "price": 89.90,
                "in_stock": True,
            },
            {
                "site": "sephora",
                "site_product_id": "sephora-P123456",
                "url": "https://www.sephora.fr/p/sauvage-edp-100ml-P123456.html",
                "name_on_site": "Sauvage Eau de Parfum",
                "brand_on_site": "Christian Dior",
                "price": 95.00,
                "in_stock": True,
            },
            {
                "site": "nocibe",
                "site_product_id": "nocibe-78901",
                "url": "https://www.nocibe.fr/dior-sauvage-edp-100ml-78901",
                "name_on_site": "DIOR Sauvage EDP 100ml",
                "brand_on_site": "DIOR",
                "price": 92.50,
                "in_stock": False,
            },
        ]

        now = datetime.now(timezone.utc)
        listings = []
        for data in site_data:
            listing = Listing(
                id=uuid.uuid4(),
                canonical_product_id=product.id,
                site=data["site"],
                site_product_id=data["site_product_id"],
                url=data["url"],
                name_on_site=data["name_on_site"],
                brand_on_site=data["brand_on_site"],
                image_url=None,
                last_seen_at=now,
            )
            db.add(listing)
            db.flush()

            snapshot = PriceSnapshot(
                listing_id=listing.id,
                price=data["price"],
                currency="EUR",
                in_stock=data["in_stock"],
                scraped_at=now,
            )
            db.add(snapshot)
            listings.append(listing)

        db.commit()

        # ------------------------------------------------------------------ #
        # 3. Read back and verify
        # ------------------------------------------------------------------ #
        db.expire_all()
        loaded = db.get(CanonicalProduct, product.id)
        assert loaded is not None, "Product not found after insert!"
        assert len(loaded.listings) == 3, f"Expected 3 listings, got {len(loaded.listings)}"

        prices = [s.price for l in loaded.listings for s in l.price_snapshots]
        assert len(prices) == 3, f"Expected 3 price snapshots, got {len(prices)}"

        print("✓ Seed successful!")
        print(f"  Product : {loaded.brand} — {loaded.name} ({loaded.size_ml}ml)")
        for listing in loaded.listings:
            snap = listing.price_snapshots[0]
            stock = "in stock" if snap.in_stock else "out of stock"
            print(f"  [{listing.site:8s}] {float(snap.price):.2f} {snap.currency} — {stock}")

    except Exception as exc:
        db.rollback()
        print(f"✗ Seed failed: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
