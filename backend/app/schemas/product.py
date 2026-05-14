"""
schemas/product.py
==================
Pydantic schemas for canonical products, listings, price history,
and the brand list endpoint.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

class ListingPriceOut(BaseModel):
    """Latest price info for one retail site listing."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site: Literal["primor", "sephora", "nocibe"]
    url: str | None
    name_on_site: str | None
    image_url: str | None
    latest_price: float | None
    currency: str | None
    in_stock: bool | None
    last_seen_at: datetime | None


class PricePointOut(BaseModel):
    """A single price snapshot data point (for history charts)."""

    model_config = ConfigDict(from_attributes=True)

    site: str
    price: float
    currency: str
    in_stock: bool | None
    scraped_at: datetime


# ---------------------------------------------------------------------------
# Product list endpoint
# ---------------------------------------------------------------------------

class ProductListItem(BaseModel):
    """Compact representation used in GET /api/products."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand: str
    name: str
    size_ml: int | None
    gender: str | None
    image_url: str | None
    cheapest_price: float | None
    cheapest_site: str | None
    cheapest_currency: str | None


class ProductListResponse(BaseModel):
    """Paginated product list."""

    total: int
    page: int
    page_size: int
    items: list[ProductListItem]


# ---------------------------------------------------------------------------
# Product detail endpoint
# ---------------------------------------------------------------------------

class ProductDetailOut(BaseModel):
    """Full canonical product with all site listings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand: str
    name: str
    size_ml: int | None
    gender: str | None
    image_url: str | None
    created_at: datetime
    listings: list[ListingPriceOut]


# ---------------------------------------------------------------------------
# Price history endpoint
# ---------------------------------------------------------------------------

class ProductHistoryOut(BaseModel):
    """All price snapshots for a product, grouped across sites."""

    product_id: uuid.UUID
    days: int
    snapshots: list[PricePointOut]


# ---------------------------------------------------------------------------
# Brands endpoint
# ---------------------------------------------------------------------------

class BrandItem(BaseModel):
    brand: str
    count: int


class BrandsResponse(BaseModel):
    items: list[BrandItem]
