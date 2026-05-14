"""
routers/products.py
====================
Public read-only product endpoints.

GET /api/products          — paginated list with filters
GET /api/products/{id}     — full detail with per-site prices
GET /api/products/{id}/history — price history
GET /api/brands            — distinct brand list
"""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud.products import get_brands, get_product_detail, get_product_history, get_products
from app.db import get_session
from app.schemas.product import (
    BrandsResponse,
    ProductDetailOut,
    ProductHistoryOut,
    ProductListResponse,
)

router = APIRouter(prefix="/api", tags=["products"])

DB = Annotated[Session, Depends(get_session)]


@router.get("/products", response_model=ProductListResponse)
def list_products(
    db: DB,
    q: str | None = Query(default=None, description="Search by name or brand"),
    brand: str | None = Query(default=None),
    gender: Literal["men", "women", "unisex"] | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    sort: Literal["name", "price_asc", "price_desc"] = Query(default="name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ProductListResponse:
    """
    Return a paginated list of canonical products with the cheapest current price.
    """
    return get_products(
        db,
        q=q,
        brand=brand,
        gender=gender,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def product_detail(product_id: uuid.UUID, db: DB) -> ProductDetailOut:
    """
    Return a canonical product with all its site listings and latest prices.
    """
    result = get_product_detail(db, product_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return result


@router.get("/products/{product_id}/history", response_model=ProductHistoryOut)
def product_history(
    product_id: uuid.UUID,
    db: DB,
    days: int = Query(default=30, ge=1, le=365),
) -> ProductHistoryOut:
    """
    Return all price snapshots for a product over the last N days.
    """
    result = get_product_history(db, product_id, days=days)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return result


@router.get("/brands", response_model=BrandsResponse)
def brands(db: DB) -> BrandsResponse:
    """
    Return distinct brand list with product counts (for filter dropdown).
    """
    return get_brands(db)
