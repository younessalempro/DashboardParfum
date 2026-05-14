"""Smoke tests for PrimorScraper — mocked HTTP, no real network calls.

Architecture note (2026-05)
----------------------------
PrimorScraper primary strategy revised to:
  1. curl_cffi category page fetch (bypasses Cloudflare).
  2. Extract PDP links matching /fr_fr/<slug>-<id>.html.
  3. Fetch each PDP and parse application/ld+json (JSON-LD) + spConfig volumen
     blob to emit ONE RawListing per size variant.

Frizbit feed kept as supplemental path (_fetch_frizbit / _parse_frizbit).
"""
import re
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.app.scrapers.primor import (
    PrimorScraper,
    _extract_size_ml,
    _extract_sku_to_ml,
    _sku_from_url,
)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Dior Sauvage EDT 100ml", 100),
    ("Chanel No 5 50 ml", 50),
    ("Parfum 200ML", 200),
    ("No size here", None),
    ("", None),
])
def test_extract_size_ml(name, expected):
    assert _extract_size_ml(name) == expected


def test_sku_from_url_numeric_suffix():
    assert _sku_from_url("https://fr.primor.eu/fr_fr/dior-sauvage-edt-12345.html") == "12345"


def test_sku_from_url_fallback():
    url = "https://fr.primor.eu/fr_fr/some-product"
    result = _sku_from_url(url)
    assert result == "some-product"


# ---------------------------------------------------------------------------
# _extract_sku_to_ml — spConfig volumen block parser
# ---------------------------------------------------------------------------

SPCONFIG_HTML = """
<script>
var spConfig = {"attributes":{"854":{"code":"volumen","label":"Volumen",
  "options":[
    {"id":"1001","label":"30","skus":["SKU-30"]},
    {"id":"1002","label":"60","skus":["SKU-60A","SKU-60B"]},
    {"id":"1003","label":"100","skus":["SKU-100"]}
  ]}}};
</script>
"""

SPCONFIG_HTML_NO_VOLUMEN = """
<script>
var spConfig = {"attributes":{"855":{"code":"color","label":"Color",
  "options":[{"id":"1","label":"Red","skus":["SKU-R"]}]}}};
</script>
"""


def test_extract_sku_to_ml_basic():
    result = _extract_sku_to_ml(SPCONFIG_HTML)
    assert result["SKU-30"] == 30
    assert result["SKU-100"] == 100


def test_extract_sku_to_ml_multi_sku_per_option():
    result = _extract_sku_to_ml(SPCONFIG_HTML)
    assert result["SKU-60A"] == 60
    assert result["SKU-60B"] == 60


def test_extract_sku_to_ml_all_skus_present():
    result = _extract_sku_to_ml(SPCONFIG_HTML)
    assert set(result.keys()) == {"SKU-30", "SKU-60A", "SKU-60B", "SKU-100"}


def test_extract_sku_to_ml_no_volumen_returns_empty():
    result = _extract_sku_to_ml(SPCONFIG_HTML_NO_VOLUMEN)
    assert result == {}


def test_extract_sku_to_ml_empty_html():
    assert _extract_sku_to_ml("<html></html>") == {}


# ---------------------------------------------------------------------------
# _extract_skus (kept for Frizbit supplemental path)
# ---------------------------------------------------------------------------

def test_extract_skus_basic():
    scraper = PrimorScraper()
    html = 'var data = {"skus":["111","222","333"]}'
    skus = scraper._extract_skus(html)
    assert skus == ["111", "222", "333"]


def test_extract_skus_deduplication():
    scraper = PrimorScraper()
    html = '{"skus":["A","B"]} ... {"skus":["B","C"]}'
    skus = scraper._extract_skus(html)
    assert skus == ["A", "B", "C"]


def test_extract_skus_no_match():
    scraper = PrimorScraper()
    assert scraper._extract_skus("<html>nothing here</html>") == []


# ---------------------------------------------------------------------------
# _parse_frizbit (supplemental path — real field names verified 2026-05)
# ---------------------------------------------------------------------------

def test_parse_frizbit_valid():
    """Use actual Frizbit field names (verified against live API 2026-05)."""
    scraper = PrimorScraper()
    payload = {
        "product_name": "Dior Sauvage EDT 100ml",
        "product_brand": "Dior",
        "product_sale_price": 89.90,
        "product_price": 120.0,
        "product_image": "https://cdn.example.com/img.jpg",
        "product_url": "https://fr.primor.eu/fr_fr/dior-sauvage-12345.html",
        "product_instock": "in_stock",
    }
    listing = scraper._parse_frizbit("12345", payload)
    assert listing is not None
    assert listing.site == "primor"
    assert listing.site_product_id == "12345"
    assert listing.price == Decimal("89.9")
    assert listing.in_stock is True
    assert listing.size_ml == 100
    assert listing.brand == "Dior"


def test_parse_frizbit_out_of_stock():
    scraper = PrimorScraper()
    payload = {
        "product_name": "Chanel No 5 50ml",
        "product_brand": "Chanel",
        "product_sale_price": 79.0,
        "product_url": "https://fr.primor.eu/fr_fr/chanel-no5-99999.html",
        "product_instock": "out_of_stock",
    }
    listing = scraper._parse_frizbit("99999", payload)
    assert listing is not None
    assert listing.in_stock is False


def test_parse_frizbit_missing_name_returns_none():
    scraper = PrimorScraper()
    payload = {"product_sale_price": 10.0, "product_url": "https://fr.primor.eu/fr_fr/x-1.html"}
    assert scraper._parse_frizbit("1", payload) is None


def test_parse_frizbit_zero_price_returns_none():
    scraper = PrimorScraper()
    payload = {
        "product_name": "Some Perfume",
        "product_brand": "Brand",
        "product_sale_price": 0,
        "product_price": 0,
        "product_url": "https://fr.primor.eu/fr_fr/some-2.html",
    }
    assert scraper._parse_frizbit("2", payload) is None


def test_parse_frizbit_legacy_fields_still_work():
    """Old field names (title/brand/price/url) are kept as fallbacks."""
    scraper = PrimorScraper()
    payload = {
        "title": "Armani Acqua 75ml",
        "brand": "Armani",
        "price": 65.0,
        "url": "https://fr.primor.eu/fr_fr/armani-acqua-11111.html",
        "availability": "in stock",
    }
    listing = scraper._parse_frizbit("11111", payload)
    assert listing is not None
    assert listing.name == "Armani Acqua 75ml"


# ---------------------------------------------------------------------------
# _map_json_ld_variants — multi-variant PDP parser (primary path)
# ---------------------------------------------------------------------------

MULTI_OFFER_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Libre Eau de Parfum",
    "brand": {"@type": "Brand", "name": "Yves Saint Laurent"},
    "image": "https://cdn2.primor.eu/libre.jpg",
    "offers": [
        {
            "@type": "Offer",
            "sku": "SKU-30",
            "price": "44.37",
            "priceCurrency": "EUR",
            "availability": "http://schema.org/InStock",
        },
        {
            "@type": "Offer",
            "sku": "SKU-60",
            "price": "79.00",
            "priceCurrency": "EUR",
            "availability": "http://schema.org/InStock",
        },
        {
            "@type": "Offer",
            "sku": "SKU-100",
            "price": "119.00",
            "priceCurrency": "EUR",
            "availability": "http://schema.org/OutOfStock",
        },
    ],
}

SKU_TO_ML = {"SKU-30": 30, "SKU-60": 60, "SKU-100": 100}
PDP_URL = "https://fr.primor.eu/fr_fr/ysl-libre-111829.html"


def test_map_json_ld_variants_emits_one_per_offer():
    scraper = PrimorScraper()
    listings = list(scraper._map_json_ld_variants(PDP_URL, MULTI_OFFER_JSON_LD, SKU_TO_ML))
    assert len(listings) == 3


def test_map_json_ld_variants_correct_size_ml():
    scraper = PrimorScraper()
    listings = list(scraper._map_json_ld_variants(PDP_URL, MULTI_OFFER_JSON_LD, SKU_TO_ML))
    by_sku = {l.site_product_id: l for l in listings}
    assert by_sku["SKU-30"].size_ml == 30
    assert by_sku["SKU-60"].size_ml == 60
    assert by_sku["SKU-100"].size_ml == 100


def test_map_json_ld_variants_correct_prices():
    scraper = PrimorScraper()
    listings = list(scraper._map_json_ld_variants(PDP_URL, MULTI_OFFER_JSON_LD, SKU_TO_ML))
    by_sku = {l.site_product_id: l for l in listings}
    assert by_sku["SKU-30"].price == Decimal("44.37")
    assert by_sku["SKU-60"].price == Decimal("79.00")
    assert by_sku["SKU-100"].price == Decimal("119.00")


def test_map_json_ld_variants_stock_status():
    scraper = PrimorScraper()
    listings = list(scraper._map_json_ld_variants(PDP_URL, MULTI_OFFER_JSON_LD, SKU_TO_ML))
    by_sku = {l.site_product_id: l for l in listings}
    assert by_sku["SKU-30"].in_stock is True
    assert by_sku["SKU-100"].in_stock is False


def test_map_json_ld_variants_shared_fields():
    """All variants share name, brand, image, url from the parent Product."""
    scraper = PrimorScraper()
    listings = list(scraper._map_json_ld_variants(PDP_URL, MULTI_OFFER_JSON_LD, SKU_TO_ML))
    for l in listings:
        assert l.name == "Libre Eau de Parfum"
        assert l.brand == "Yves Saint Laurent"
        assert l.image_url == "https://cdn2.primor.eu/libre.jpg"
        assert l.url == PDP_URL
        assert l.site == "primor"


def test_map_json_ld_variants_no_duplicate_skus():
    """Duplicate SKU in offers list → only one listing emitted."""
    scraper = PrimorScraper()
    obj = {
        **MULTI_OFFER_JSON_LD,
        "offers": [
            {"sku": "SKU-30", "price": "44.37", "availability": "http://schema.org/InStock"},
            {"sku": "SKU-30", "price": "44.37", "availability": "http://schema.org/InStock"},
        ],
    }
    listings = list(scraper._map_json_ld_variants(PDP_URL, obj, SKU_TO_ML))
    assert len(listings) == 1


def test_map_json_ld_variants_zero_price_skipped():
    """Offers with price=0 must be skipped."""
    scraper = PrimorScraper()
    obj = {
        **MULTI_OFFER_JSON_LD,
        "offers": [
            {"sku": "SKU-30", "price": "0", "availability": "http://schema.org/InStock"},
            {"sku": "SKU-60", "price": "79.00", "availability": "http://schema.org/InStock"},
        ],
    }
    listings = list(scraper._map_json_ld_variants(PDP_URL, obj, SKU_TO_ML))
    assert len(listings) == 1
    assert listings[0].site_product_id == "SKU-60"


def test_map_json_ld_variants_fallback_size_from_name():
    """When sku_to_ml has no entry, fall back to parsing ml from product name."""
    scraper = PrimorScraper()
    obj = {
        **MULTI_OFFER_JSON_LD,
        "name": "Libre Eau de Parfum 75ml",
        "offers": [
            {"sku": "SKU-UNKNOWN", "price": "95.00", "availability": "http://schema.org/InStock"},
        ],
    }
    listings = list(scraper._map_json_ld_variants(PDP_URL, obj, {}))  # empty sku_to_ml
    assert len(listings) == 1
    assert listings[0].size_ml == 75


# ---------------------------------------------------------------------------
# _map_json_ld — backward-compat wrapper (returns first variant)
# ---------------------------------------------------------------------------

SAMPLE_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Libre Eau de Parfum Rechargeable",
    "brand": {"@type": "Brand", "name": "Yves Saint Laurent"},
    "image": "https://cdn2.primor.eu/libre.jpg",
    "offers": {
        "@type": "Offer",
        "sku": "4AF05713",
        "price": "44.37",
        "priceCurrency": "EUR",
        "availability": "http://schema.org/InStock",
    },
}


def test_map_json_ld_valid():
    scraper = PrimorScraper()
    url = "https://fr.primor.eu/fr_fr/ysl-libre-111829.html"
    listing = scraper._map_json_ld(url, SAMPLE_JSON_LD)

    assert listing is not None
    assert listing.site == "primor"
    assert listing.name == "Libre Eau de Parfum Rechargeable"
    assert listing.brand == "Yves Saint Laurent"
    assert listing.price == Decimal("44.37")
    assert listing.in_stock is True
    assert listing.site_product_id == "4AF05713"
    assert listing.image_url == "https://cdn2.primor.eu/libre.jpg"
    assert listing.url == url


def test_map_json_ld_zero_price_returns_none():
    scraper = PrimorScraper()
    obj = {**SAMPLE_JSON_LD, "offers": {"price": "0"}}
    assert scraper._map_json_ld("https://fr.primor.eu/fr_fr/x-1.html", obj) is None


def test_map_json_ld_missing_name_returns_none():
    scraper = PrimorScraper()
    obj = {**SAMPLE_JSON_LD, "name": ""}
    assert scraper._map_json_ld("https://fr.primor.eu/fr_fr/x-1.html", obj) is None


def test_map_json_ld_extracts_size_ml():
    scraper = PrimorScraper()
    obj = {**SAMPLE_JSON_LD, "name": "Chanel No 5 EDP 100ml"}
    listing = scraper._map_json_ld("https://fr.primor.eu/fr_fr/chanel-1.html", obj)
    assert listing is not None
    assert listing.size_ml == 100


# ---------------------------------------------------------------------------
# _extract_pdp_links
# ---------------------------------------------------------------------------

CATEGORY_HTML = """
<html><body>
  <a href="/fr_fr/dior-sauvage-edt-100ml-12345.html">Dior Sauvage</a>
  <a href="/fr_fr/chanel-no5-edp-50ml-99999.html">Chanel No5</a>
  <a href="/fr_fr/parfums-pour-femme">Category nav</a>
  <a href="https://fr.primor.eu/fr_fr/armani-si-edp-11111.html">Armani Si</a>
  <a href="/fr_fr/dior-sauvage-edt-100ml-12345.html">Dior Sauvage (dup)</a>
</body></html>
"""


def test_extract_pdp_links_deduplicates():
    from bs4 import BeautifulSoup
    scraper = PrimorScraper()
    soup = BeautifulSoup(CATEGORY_HTML, "lxml")
    links = scraper._extract_pdp_links(soup)
    assert len(links) == 3  # 2 relative + 1 absolute, dup removed
    for link in links:
        assert link.startswith("https://")
        assert link.endswith(".html")


def test_extract_pdp_links_excludes_category_nav():
    from bs4 import BeautifulSoup
    scraper = PrimorScraper()
    soup = BeautifulSoup(CATEGORY_HTML, "lxml")
    links = scraper._extract_pdp_links(soup)
    # /fr_fr/parfums-pour-femme has no numeric suffix — should be excluded
    assert all(re.search(r"-\d+\.html$", link) for link in links)


# ---------------------------------------------------------------------------
# Integration: scrape_category with mocked HTTP — multi-variant products
# ---------------------------------------------------------------------------

MOCK_CATEGORY_HTML = """
<html><body>
<a href="/fr_fr/ysl-libre-111.html">YSL Libre</a>
<a href="/fr_fr/chanel-chance-222.html">Chanel Chance</a>
</body></html>
"""

# Product 111: 2 variants (30ml + 60ml), SKU data in spConfig
JSON_LD_PDP_111 = """
<html><head>
<script type="application/ld+json">
{"@type":"Product","name":"YSL Libre EDP",
 "brand":{"name":"Yves Saint Laurent"},
 "image":"https://cdn.primor.eu/111.jpg",
 "offers":[
   {"sku":"M-111A","price":"44.00","priceCurrency":"EUR","availability":"http://schema.org/InStock"},
   {"sku":"M-111B","price":"79.00","priceCurrency":"EUR","availability":"http://schema.org/InStock"}
 ]}
</script>
<script>
var spConfig = {"attributes":{"854":{"code":"volumen","options":[
  {"label":"30","skus":["M-111A"]},
  {"label":"60","skus":["M-111B"]}
]}}};
</script>
</head><body></body></html>
"""

# Product 222: 1 variant (50ml)
JSON_LD_PDP_222 = """
<html><head>
<script type="application/ld+json">
{"@type":"Product","name":"Chanel Chance EDP",
 "brand":{"name":"Chanel"},
 "image":"https://cdn.primor.eu/222.jpg",
 "offers":{"sku":"M-222","price":"75.00","priceCurrency":"EUR","availability":"http://schema.org/InStock"}}
</script>
<script>
var spConfig = {"attributes":{"854":{"code":"volumen","options":[
  {"label":"50","skus":["M-222"]}
]}}};
</script>
</head><body></body></html>
"""

_MULTI_URL_MAP = {
    "https://fr.primor.eu/fr_fr/parfums-pour-femme": MOCK_CATEGORY_HTML,
    "https://fr.primor.eu/fr_fr/ysl-libre-111.html": JSON_LD_PDP_111,
    "https://fr.primor.eu/fr_fr/chanel-chance-222.html": JSON_LD_PDP_222,
}


def _mock_polite_get_multi(session, url, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = _MULTI_URL_MAP.get(url, "<html></html>")
    return resp


@patch("backend.app.scrapers.primor.check_robots")
@patch("backend.app.scrapers.primor.polite_get", side_effect=_mock_polite_get_multi)
def test_scrape_category_multi_variant_total_count(mock_polite_get, mock_robots):
    """Product 111 has 2 variants, product 222 has 1 → 3 total listings."""
    scraper = PrimorScraper()
    listings = list(scraper.scrape_category("https://fr.primor.eu/fr_fr/parfums-pour-femme"))
    assert len(listings) == 3


@patch("backend.app.scrapers.primor.check_robots")
@patch("backend.app.scrapers.primor.polite_get", side_effect=_mock_polite_get_multi)
def test_scrape_category_correct_size_ml_from_spconfig(mock_polite_get, mock_robots):
    """All listings must have size_ml populated from spConfig, not null."""
    scraper = PrimorScraper()
    listings = list(scraper.scrape_category("https://fr.primor.eu/fr_fr/parfums-pour-femme"))
    for listing in listings:
        assert listing.size_ml is not None, (
            f"size_ml should not be None for {listing.site_product_id}"
        )
    by_sku = {l.site_product_id: l for l in listings}
    assert by_sku["M-111A"].size_ml == 30
    assert by_sku["M-111B"].size_ml == 60
    assert by_sku["M-222"].size_ml == 50


@patch("backend.app.scrapers.primor.check_robots")
@patch("backend.app.scrapers.primor.polite_get", side_effect=_mock_polite_get_multi)
def test_scrape_category_all_fields_populated(mock_polite_get, mock_robots):
    scraper = PrimorScraper()
    listings = list(scraper.scrape_category("https://fr.primor.eu/fr_fr/parfums-pour-femme"))
    for listing in listings:
        assert listing.site_product_id
        assert listing.url
        assert listing.name
        assert listing.brand
        assert listing.price > 0
        assert listing.currency == "EUR"
        assert listing.image_url is not None
        assert listing.size_ml is not None


@patch("backend.app.scrapers.primor.check_robots")
@patch("backend.app.scrapers.primor.polite_get", side_effect=_mock_polite_get_multi)
def test_scrape_category_variant_skus(mock_polite_get, mock_robots):
    scraper = PrimorScraper()
    listings = list(scraper.scrape_category("https://fr.primor.eu/fr_fr/parfums-pour-femme"))
    skus = {l.site_product_id for l in listings}
    assert skus == {"M-111A", "M-111B", "M-222"}


# ---------------------------------------------------------------------------
# Integration: single-category URL map (original tests, kept for regression)
# ---------------------------------------------------------------------------

_ORIG_URL_MAP = {
    "https://fr.primor.eu/fr_fr/parfums-pour-femme": """
<html><body>
<a href="/fr_fr/dior-sauvage-edt-111.html">Dior Sauvage</a>
<a href="/fr_fr/chanel-chance-edp-222.html">Chanel Chance</a>
</body></html>
""",
    "https://fr.primor.eu/fr_fr/dior-sauvage-edt-111.html": """
<html><head>
<script type="application/ld+json">
{"@type":"Product","name":"Dior Sauvage EDT","brand":{"name":"Christian Dior"},
 "image":"https://cdn.primor.eu/111.jpg",
 "offers":{"sku":"111","price":"89.90","priceCurrency":"EUR","availability":"http://schema.org/InStock"}}
</script></head><body></body></html>
""",
    "https://fr.primor.eu/fr_fr/chanel-chance-edp-222.html": """
<html><head>
<script type="application/ld+json">
{"@type":"Product","name":"Chanel Chance EDP","brand":{"name":"Chanel"},
 "image":"https://cdn.primor.eu/222.jpg",
 "offers":{"sku":"222","price":"75.00","priceCurrency":"EUR","availability":"http://schema.org/InStock"}}
</script></head><body></body></html>
""",
}


def _mock_polite_get_orig(session, url, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = _ORIG_URL_MAP.get(url, "<html></html>")
    return resp


@patch("backend.app.scrapers.primor.check_robots")
@patch("backend.app.scrapers.primor.polite_get", side_effect=_mock_polite_get_orig)
def test_scrape_category_yields_listings(mock_polite_get, mock_robots):
    scraper = PrimorScraper()
    listings = list(scraper.scrape_category("https://fr.primor.eu/fr_fr/parfums-pour-femme"))

    assert len(listings) == 2
    skus = {l.site_product_id for l in listings}
    assert skus == {"111", "222"}

    for listing in listings:
        assert listing.site == "primor"
        assert listing.price > 0
        assert listing.url.startswith("https://")
        assert listing.name != ""
        assert listing.brand != ""
