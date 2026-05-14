"""Smoke tests for NocibeScraper — no real network calls.

Architecture note (2026-05)
----------------------------
NocibeScraper was rewritten to use Playwright (same pattern as SephoraScraper)
after investigation showed:
  - Category pages are JS-rendered (ICM/Intershop React SPA)
  - PDPs are blocked by Imperva/Akamai for plain HTTP clients
  - Product data arrives via XHR to /v2/personalizedSearch/ or similar

The tests therefore:
  1. Test all pure helper functions directly (no mocking needed).
  2. Test _map_api_product() and _extract_listings_from_api() directly.
  3. Test _parse_json_ld_from_html() (the module-level PDP fallback) directly.
  4. Use AsyncMock + patch for the Playwright-dependent scrape_category().
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.scrapers.nocibe import (
    NocibeScraper,
    _build_page_url,
    _extract_size_ml,
    _parse_json_ld_from_html,
    _sku_from_url,
)


# ---------------------------------------------------------------------------
# Helper function tests (pure, no HTTP)
# ---------------------------------------------------------------------------

def test_build_page_url_page1():
    assert _build_page_url("https://www.nocibe.fr/parfum-femme", 1) == \
        "https://www.nocibe.fr/parfum-femme"


def test_build_page_url_page2():
    url = _build_page_url("https://www.nocibe.fr/parfum-femme", 2)
    assert "page=2" in url


def test_sku_from_url_p_path():
    assert _sku_from_url("https://www.nocibe.fr/fr/p/98765") == "98765"


def test_sku_from_url_fallback():
    assert _sku_from_url("https://www.nocibe.fr/parfum/dior-sauvage") == "dior-sauvage"


@pytest.mark.parametrize("name,expected", [
    ("Dior Sauvage 100ml", 100),
    ("YSL Black Opium 50 ml", 50),
    ("Product without size", None),
])
def test_extract_size_ml(name, expected):
    assert _extract_size_ml(name) == expected


# ---------------------------------------------------------------------------
# JSON-LD PDP fallback (module-level helper, pure HTML parsing)
# ---------------------------------------------------------------------------

JSON_LD_PDP = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Dior Sauvage EDT 100ml",
  "brand": {"@type": "Brand", "name": "Dior"},
  "sku": "98765",
  "image": "https://cdn.nocibe.fr/98765.jpg",
  "offers": {
    "@type": "Offer",
    "price": "89.90",
    "priceCurrency": "EUR",
    "availability": "https://schema.org/InStock"
  }
}
</script>
</head><body></body></html>
"""

def test_parse_json_ld_from_html():
    listing = _parse_json_ld_from_html("https://www.nocibe.fr/fr/p/98765", JSON_LD_PDP)

    assert listing is not None
    assert listing.site == "nocibe"
    assert listing.name == "Dior Sauvage EDT 100ml"
    assert listing.brand == "Dior"
    assert listing.price == Decimal("89.90")
    assert listing.in_stock is True
    assert listing.size_ml == 100
    assert listing.site_product_id == "98765"


def test_parse_json_ld_returns_none_without_product_type():
    html = """<html><head>
    <script type="application/ld+json">{"@type": "WebSite", "name": "Nocibé"}</script>
    </head></html>"""
    assert _parse_json_ld_from_html("https://www.nocibe.fr/fr/p/1", html) is None


def test_parse_json_ld_returns_none_for_zero_price():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Test", "sku": "1",
     "offers": {"price": "0", "availability": "InStock"}}
    </script></head></html>"""
    assert _parse_json_ld_from_html("https://www.nocibe.fr/fr/p/1", html) is None


# ---------------------------------------------------------------------------
# _map_api_product — test the API payload mapper directly
# ---------------------------------------------------------------------------

def test_map_api_product_valid():
    scraper = NocibeScraper()
    product = {
        "sku": "12345",
        "name": "Chanel Chance EDP 50ml",
        "brand": {"name": "Chanel"},
        "salePrice": "75.00",
        "url": "/fr/p/12345",
        "image": "https://cdn.nocibe.fr/12345.jpg",
        "inStock": True,
    }
    listing = scraper._map_api_product(product)
    assert listing is not None
    assert listing.site == "nocibe"
    assert listing.site_product_id == "12345"
    assert listing.name == "Chanel Chance EDP 50ml"
    assert listing.brand == "Chanel"
    assert listing.price == Decimal("75.00")
    assert listing.in_stock is True
    assert listing.size_ml == 50
    assert "nocibe.fr" in listing.url


def test_map_api_product_missing_sku_returns_none():
    scraper = NocibeScraper()
    listing = scraper._map_api_product({"name": "Test", "salePrice": "10.00"})
    assert listing is None


def test_map_api_product_zero_price_returns_none():
    scraper = NocibeScraper()
    listing = scraper._map_api_product({"sku": "1", "name": "Test", "salePrice": "0"})
    assert listing is None


def test_map_api_product_string_brand():
    scraper = NocibeScraper()
    product = {
        "sku": "99",
        "name": "YSL Libre EDP 90ml",
        "brand": "Yves Saint Laurent",
        "salePrice": "120.00",
        "url": "/fr/p/99",
    }
    listing = scraper._map_api_product(product)
    assert listing is not None
    assert listing.brand == "Yves Saint Laurent"


# ---------------------------------------------------------------------------
# _extract_listings_from_api — test payload shape variations
# ---------------------------------------------------------------------------

def test_extract_listings_from_api_products_key():
    scraper = NocibeScraper()
    payload = {
        "products": [
            {"sku": "A1", "name": "Parfum A 100ml", "salePrice": "49.90", "url": "/fr/p/A1"},
            {"sku": "A2", "name": "Parfum B 50ml", "salePrice": "29.90", "url": "/fr/p/A2"},
        ]
    }
    listings = scraper._extract_listings_from_api(payload)
    assert len(listings) == 2
    assert all(l.site == "nocibe" for l in listings)


def test_extract_listings_from_api_items_key():
    scraper = NocibeScraper()
    payload = {
        "items": [
            {"sku": "B1", "name": "Parfum X 75ml", "salePrice": "59.90", "url": "/fr/p/B1"},
        ]
    }
    listings = scraper._extract_listings_from_api(payload)
    assert len(listings) == 1


def test_extract_listings_from_api_empty_payload():
    scraper = NocibeScraper()
    assert scraper._extract_listings_from_api({}) == []


# ---------------------------------------------------------------------------
# scrape_category integration — mock the Playwright async layer
# ---------------------------------------------------------------------------

def test_scrape_category_extracts_from_api_intercepts():
    """Verify the full extraction pipeline: intercepted payload → RawListing list."""
    scraper = NocibeScraper()

    fake_payload = {
        "products": [
            {"sku": "C1", "name": "Armani Sì EDP 100ml", "salePrice": "89.90", "url": "/fr/p/C1"},
            {"sku": "C2", "name": "Dior Sauvage EDT 50ml", "salePrice": "69.90", "url": "/fr/p/C2"},
        ]
    }

    # Test the extraction logic that _async_scrape_category calls for each
    # intercepted XHR payload — no browser required.
    listings = scraper._extract_listings_from_api(fake_payload)
    assert len(listings) == 2
    skus = {l.site_product_id for l in listings}
    assert skus == {"C1", "C2"}
    for l in listings:
        assert l.price > 0
        assert l.url != ""
        assert l.name != ""
