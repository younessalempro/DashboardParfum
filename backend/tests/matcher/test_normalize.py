"""Tests for matcher/normalize.py — pure functions, no DB needed."""
import pytest

from backend.app.matcher.normalize import (
    BRAND_ALIASES,
    extract_size_ml,
    make_match_key,
    normalize_brand,
    normalize_name,
    normalize_text,
    strip_accents,
    strip_size_token,
)


# ---------------------------------------------------------------------------
# strip_accents
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_str,expected", [
    ("éàü", "eau"),
    ("Ñoño", "Nono"),
    ("café", "cafe"),
    ("Chloé", "Chloe"),
    ("plain", "plain"),
    ("", ""),
])
def test_strip_accents(input_str, expected):
    assert strip_accents(input_str) == expected


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_str,expected", [
    ("  Hello World  ", "hello world"),
    ("Dior Sauvage!", "dior sauvage"),
    ("Chloé Nomade", "chloe nomade"),
    ("YSL Black-Opium", "ysl black opium"),
])
def test_normalize_text(input_str, expected):
    assert normalize_text(input_str) == expected


# ---------------------------------------------------------------------------
# extract_size_ml
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Dior Sauvage 100ml", 100),
    ("Perfume 50 ML", 50),
    ("No size", None),
    ("200ml EDT", 200),
    ("", None),
])
def test_extract_size_ml(name, expected):
    assert extract_size_ml(name) == expected


# ---------------------------------------------------------------------------
# strip_size_token
# ---------------------------------------------------------------------------

def test_strip_size_token():
    assert strip_size_token("Dior Sauvage EDT 100ml") == "Dior Sauvage EDT"
    assert strip_size_token("100ml perfume name") == "perfume name"
    assert strip_size_token("no size") == "no size"


# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Dior Sauvage EDT 100ml", "dior sauvage edt"),
    ("Chanel No 5 EDP 50ml", "chanel no 5 edp"),
    ("YSL Black Opium EDP 30ml", "ysl black opium edp"),
    ("Perfume Name", "perfume name"),
])
def test_normalize_name(name, expected):
    assert normalize_name(name) == expected


# ---------------------------------------------------------------------------
# normalize_brand
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("brand,expected", [
    ("Christian Dior", "dior"),
    ("Yves Saint Laurent", "ysl"),
    ("Giorgio Armani", "armani"),
    ("CHANEL", "chanel"),
    ("Lancôme", "lancome"),
    ("Hermès", "hermes"),
    ("Unknown Brand", "unknown brand"),
    ("", ""),
])
def test_normalize_brand(brand, expected):
    assert normalize_brand(brand) == expected


def test_brand_aliases_no_empty_values():
    for alias, canonical in BRAND_ALIASES.items():
        assert canonical, f"Empty canonical for alias '{alias}'"
        assert alias, "Empty alias key"


# ---------------------------------------------------------------------------
# make_match_key
# ---------------------------------------------------------------------------

def test_make_match_key_with_size():
    key = make_match_key("Christian Dior", "Sauvage EDT 100ml", 100)
    assert key == "dior|sauvage edt|100"


def test_make_match_key_no_size():
    key = make_match_key("Chanel", "No 5 EDP", None)
    assert key == "chanel|no 5 edp|none"


def test_make_match_key_same_product_different_sites():
    """Same perfume from two sites must produce the same key."""
    key1 = make_match_key("Christian Dior", "Sauvage EDT 100ml", 100)
    key2 = make_match_key("Dior", "Sauvage EDT", 100)
    assert key1 == key2


def test_make_match_key_different_sizes_different_keys():
    key_100 = make_match_key("Dior", "Sauvage EDT", 100)
    key_50 = make_match_key("Dior", "Sauvage EDT", 50)
    assert key_100 != key_50
