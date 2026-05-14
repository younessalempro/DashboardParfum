"""
crud/products.py
================
Read queries powering the public product endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.canonical_product import CanonicalProduct
from app.models.listing import Listing
from app.models.price_snapshot import PriceSnapshot
from app.schemas.product import (
    BrandItem,
    BrandsResponse,
    ListingPriceOut,
    PricePointOut,
    ProductDetailOut,
    ProductHistoryOut,
    ProductListItem,
    ProductListResponse,
)

# ---------------------------------------------------------------------------
# Latest price CTE helper
# ---------------------------------------------------------------------------

def _latest_price_subquery(db: Session):
    """
    Returns a subquery that gives the most recent PriceSnapshot per listing.
    Columns: listing_id, price, currency, in_stock, scraped_at.
    """
    ranked = (
        select(
            PriceSnapshot.listing_id,
            PriceSnapshot.price,
            PriceSnapshot.currency,
            PriceSnapshot.in_stock,
            PriceSnapshot.scraped_at,
            func.row_number()
            .over(
                partition_by=PriceSnapshot.listing_id,
                order_by=desc(PriceSnapshot.scraped_at),
            )
            .label("rn"),
        )
        .subquery("ranked_prices")
    )
    latest = (
        select(ranked).where(ranked.c.rn == 1).subquery("latest_prices")
    )
    return latest


# ---------------------------------------------------------------------------
# GET /api/products
# ---------------------------------------------------------------------------

def get_products(
    db: Session,
    *,
    q: str | None = None,
    brand: str | None = None,
    gender: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "name",
    page: int = 1,
    page_size: int = 20,
) -> ProductListResponse:
    latest = _latest_price_subquery(db)

    # Cheapest price across all listings for each canonical product
    cheapest = (
        select(
            Listing.canonical_product_id,
            func.min(latest.c.price).label("cheapest_price"),
        )
        .join(latest, Listing.id == latest.c.listing_id)
        .where(Listing.canonical_product_id.isnot(None))
        .group_by(Listing.canonical_product_id)
        .subquery("cheapest")
    )

    # Cheapest site (the site that has the min price).
    # We pick ONE site per canonical product (lowest site price, then site name
    # as tiebreaker) to avoid duplicate rows when two sites have the same price.
    cheapest_site_inner = (
        select(
            Listing.canonical_product_id,
            Listing.site.label("cheapest_site"),
            latest.c.price.label("site_price"),
            latest.c.currency.label("cheapest_currency"),
            func.row_number()
            .over(
                partition_by=Listing.canonical_product_id,
                order_by=[latest.c.price.asc(), Listing.site.asc()],
            )
            .label("rn"),
        )
        .join(latest, Listing.id == latest.c.listing_id)
        .where(Listing.canonical_product_id.isnot(None))
        .subquery("cheapest_site_inner")
    )
    cheapest_site_subq = (
        select(cheapest_site_inner)
        .where(cheapest_site_inner.c.rn == 1)
        .subquery("cheapest_site_sub")
    )

    # Main query
    stmt = (
        select(
            CanonicalProduct,
            cheapest.c.cheapest_price,
            cheapest_site_subq.c.cheapest_site,
            cheapest_site_subq.c.cheapest_currency,
        )
        .outerjoin(cheapest, CanonicalProduct.id == cheapest.c.canonical_product_id)
        .outerjoin(
            cheapest_site_subq,
            CanonicalProduct.id == cheapest_site_subq.c.canonical_product_id,
        )
    )

    # Filters
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(CanonicalProduct.name).like(pattern)
            | func.lower(CanonicalProduct.brand).like(pattern)
        )
    if brand:
        stmt = stmt.where(func.lower(CanonicalProduct.brand) == brand.lower())
    if gender:
        stmt = stmt.where(CanonicalProduct.gender == gender)
    if min_price is not None:
        stmt = stmt.where(cheapest.c.cheapest_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(cheapest.c.cheapest_price <= max_price)

    # Sort
    if sort == "price_asc":
        stmt = stmt.order_by(cheapest.c.cheapest_price.asc().nulls_last())
    elif sort == "price_desc":
        stmt = stmt.order_by(cheapest.c.cheapest_price.desc().nulls_last())
    else:
        stmt = stmt.order_by(CanonicalProduct.brand, CanonicalProduct.name)

    # Total count (before pagination)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    rows = db.execute(stmt.offset(offset).limit(page_size)).all()

    items = [
        ProductListItem(
            id=cp.id,
            brand=cp.brand,
            name=cp.name,
            size_ml=cp.size_ml,
            gender=cp.gender,
            image_url=cp.image_url,
            cheapest_price=float(cheapest_price) if cheapest_price is not None else None,
            cheapest_site=cheapest_site,
            cheapest_currency=cheapest_currency,
        )
        for cp, cheapest_price, cheapest_site, cheapest_currency in rows
    ]

    return ProductListResponse(total=total, page=page, page_size=page_size, items=items)


# ---------------------------------------------------------------------------
# GET /api/products/{id}
# ---------------------------------------------------------------------------

def get_product_detail(db: Session, product_id: uuid.UUID) -> ProductDetailOut | None:
    product = db.get(CanonicalProduct, product_id)
    if product is None:
        return None

    latest = _latest_price_subquery(db)

    rows = db.execute(
        select(
            Listing,
            latest.c.price,
            latest.c.currency,
            latest.c.in_stock,
            latest.c.scraped_at,
        )
        .outerjoin(latest, Listing.id == latest.c.listing_id)
        .where(Listing.canonical_product_id == product_id)
        .order_by(latest.c.price.asc().nulls_last())
    ).all()

    listings_out = [
        ListingPriceOut(
            id=listing.id,
            site=listing.site,
            url=listing.url,
            name_on_site=listing.name_on_site,
            image_url=listing.image_url,
            latest_price=float(price) if price is not None else None,
            currency=currency,
            in_stock=in_stock,
            last_seen_at=scraped_at,
        )
        for listing, price, currency, in_stock, scraped_at in rows
    ]

    return ProductDetailOut(
        id=product.id,
        brand=product.brand,
        name=product.name,
        size_ml=product.size_ml,
        gender=product.gender,
        image_url=product.image_url,
        created_at=product.created_at,
        listings=listings_out,
    )


# ---------------------------------------------------------------------------
# GET /api/products/{id}/history
# ---------------------------------------------------------------------------

def get_product_history(
    db: Session, product_id: uuid.UUID, days: int = 30
) -> ProductHistoryOut | None:
    product = db.get(CanonicalProduct, product_id)
    if product is None:
        return None

    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = db.execute(
        select(
            Listing.site,
            PriceSnapshot.price,
            PriceSnapshot.currency,
            PriceSnapshot.in_stock,
            PriceSnapshot.scraped_at,
        )
        .join(PriceSnapshot, Listing.id == PriceSnapshot.listing_id)
        .where(
            Listing.canonical_product_id == product_id,
            PriceSnapshot.scraped_at >= since,
        )
        .order_by(PriceSnapshot.scraped_at.asc())
    ).all()

    snapshots = [
        PricePointOut(
            site=site,
            price=float(price),
            currency=currency,
            in_stock=in_stock,
            scraped_at=scraped_at,
        )
        for site, price, currency, in_stock, scraped_at in rows
    ]

    return ProductHistoryOut(product_id=product_id, days=days, snapshots=snapshots)


# ---------------------------------------------------------------------------
# GET /api/brands
# ---------------------------------------------------------------------------

def get_brands(db: Session) -> BrandsResponse:
    rows = db.execute(
        select(CanonicalProduct.brand, func.count(CanonicalProduct.id).label("cnt"))
        .group_by(CanonicalProduct.brand)
        .order_by(CanonicalProduct.brand)
    ).all()

    return BrandsResponse(items=[BrandItem(brand=brand, count=cnt) for brand, cnt in rows])
