"""Tests for scrapers/base.py — RawListing model validation."""
from decimal import Decimal

import pytest

from backend.app.scrapers.base import RawListing


def make_valid() -> dict:
    return dict(
        site="primor",
        site_product_id="12345",
        url="https://fr.primor.eu/parfums/p/12345-dior-sauvage.html",
        name="Dior Sauvage EDT 100ml",
        brand="Dior",
        price=Decimal("89.90"),
        in_stock=True,
        size_ml=100,
    )


def test_raw_listing_valid():
    listing = RawListing(**make_valid())
    assert listing.price == Decimal("89.90")
    assert listing.currency == "EUR"
    assert listing.size_ml == 100


def test_raw_listing_price_positive():
    with pytest.raises(ValueError, match="price must be > 0"):
        RawListing(**{**make_valid(), "price": Decimal("0")})


def test_raw_listing_currency_uppercased():
    listing = RawListing(**{**make_valid(), "currency": "eur"})
    assert listing.currency == "EUR"


def test_raw_listing_optional_fields_default():
    listing = RawListing(**make_valid())
    assert listing.image_url is None
    assert listing.raw_payload == {}


def test_raw_listing_image_url_optional():
    listing = RawListing(**{**make_valid(), "image_url": "https://cdn.example.com/img.jpg"})
    assert listing.image_url == "https://cdn.example.com/img.jpg"
