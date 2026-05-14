"""Tests for matcher/resolver.py — dry-run mode (no DB required)."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.app.scrapers.base import RawListing
from backend.app.matcher.resolver import (
    AUTO_MERGE_THRESHOLD,
    REVIEW_QUEUE_THRESHOLD,
    ResolveResult,
    _dry_run_resolve,
    resolve,
)
from backend.app.matcher.normalize import make_match_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_listing(
    name: str = "Dior Sauvage EDT 100ml",
    brand: str = "Dior",
    price: str = "89.90",
    size_ml: int | None = None,  # None → extracted from name by resolver
) -> RawListing:
    return RawListing(
        site="primor",
        site_product_id="12345",
        url="https://fr.primor.eu/p/12345.html",
        name=name,
        brand=brand,
        price=Decimal(price),
        size_ml=size_ml,
    )


# ---------------------------------------------------------------------------
# Dry-run resolve
# ---------------------------------------------------------------------------

def test_dry_run_resolve_returns_uuid():
    listing = make_listing()
    result = _dry_run_resolve(listing)
    assert result and len(result) == 36  # UUID format


def test_dry_run_resolve_deterministic():
    listing = make_listing()
    assert _dry_run_resolve(listing) == _dry_run_resolve(listing)


def test_dry_run_resolve_different_products_different_ids():
    l1 = make_listing("Dior Sauvage EDT 100ml", "Dior")
    l2 = make_listing("Chanel No 5 EDP 50ml", "Chanel")
    assert _dry_run_resolve(l1) != _dry_run_resolve(l2)


def test_dry_run_resolve_same_product_same_id_regardless_of_site():
    """Two scrapers producing the same normalized key should map to same canonical."""
    l_primor = RawListing(
        site="primor",
        site_product_id="A",
        url="https://fr.primor.eu/p/A.html",
        name="Dior Sauvage EDT 100ml",
        brand="Christian Dior",
        price=Decimal("89.90"),
        size_ml=100,
    )
    l_nocibe = RawListing(
        site="nocibe",
        site_product_id="B",
        url="https://www.nocibe.fr/p/B.html",
        name="Dior Sauvage EDT 100ml",
        brand="Dior",
        price=Decimal("92.00"),
        size_ml=100,
    )
    assert _dry_run_resolve(l_primor) == _dry_run_resolve(l_nocibe)


# ---------------------------------------------------------------------------
# resolve() — no DB available → falls back to dry-run
# ---------------------------------------------------------------------------

@patch("backend.app.matcher.resolver._try_import_db", return_value=(None, None))
def test_resolve_fallback_to_dry_run(mock_db):
    listing = make_listing()
    result = resolve(listing)
    assert isinstance(result, ResolveResult)
    assert result.canonical_id is not None
    assert len(result.canonical_id) == 36  # UUID format
    assert result.review_candidate_id is None


# ---------------------------------------------------------------------------
# resolve() — with mocked DB: deterministic match
# ---------------------------------------------------------------------------

def _make_mock_canonical(canonical_id: str, brand: str, name: str, size_ml):
    m = MagicMock()
    m.id = canonical_id
    m.brand = brand
    m.name = name
    m.size_ml = size_ml
    return m


@patch("backend.app.matcher.resolver._try_import_db")
def test_resolve_deterministic_match(mock_import_db):
    canonical_id = "existing-canonical-uuid"
    mock_canonical = _make_mock_canonical(canonical_id, "dior", "sauvage edt", 100)

    mock_session = MagicMock()
    mock_query = mock_session.query.return_value
    mock_query.filter.return_value.first.return_value = mock_canonical

    mock_SessionLocal = MagicMock()
    mock_SessionLocal.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_SessionLocal.return_value.__exit__ = MagicMock(return_value=False)

    mock_models = MagicMock()
    mock_import_db.return_value = (mock_SessionLocal, mock_models)

    listing = make_listing()
    result = resolve(listing)
    assert isinstance(result, ResolveResult)
    assert result.canonical_id == canonical_id
    assert result.review_candidate_id is None


@patch("backend.app.matcher.resolver._try_import_db")
def test_resolve_creates_new_canonical_when_no_match(mock_import_db):
    new_canonical_id = "new-canonical-uuid"

    mock_session = MagicMock()
    # First query (deterministic) returns None, second (fuzzy candidates) returns empty list.
    mock_session.query.return_value.filter.return_value.first.return_value = None
    mock_session.query.return_value.filter.return_value.all.return_value = []

    mock_new_canonical = MagicMock()
    mock_new_canonical.id = new_canonical_id

    def side_effect_add(obj):
        obj.id = new_canonical_id

    mock_session.add.side_effect = side_effect_add
    mock_session.flush.return_value = None

    mock_SessionLocal = MagicMock()
    mock_SessionLocal.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_SessionLocal.return_value.__exit__ = MagicMock(return_value=False)

    mock_models = MagicMock()
    mock_models.CanonicalProduct.return_value = mock_new_canonical
    mock_import_db.return_value = (mock_SessionLocal, mock_models)

    listing = make_listing("Totally New Perfume 75ml", "NewBrand", size_ml=75)
    result = resolve(listing)
    # A new canonical was created; session.add should have been called.
    assert isinstance(result, ResolveResult)
    assert result.canonical_id is not None
    mock_session.add.assert_called()


# ---------------------------------------------------------------------------
# Labeled sample: cross-site exact-key matching (deterministic step only)
# ---------------------------------------------------------------------------
# The dry-run resolver uses only the deterministic key (brand + normalized name + size).
# Fuzzy matches ("EDT" vs "Eau de Toilette", "No 5" vs "N°5") require the live DB step.
# These samples test cases that ARE expected to resolve identically via exact key,
# and cases that are definitively different products (different sizes).

EXACT_KEY_SAMPLES = [
    # name1, brand1, name2, brand2, same_key_expected
    # Same name token, same brand alias, same size → identical key
    ("Dior Sauvage EDT 100ml", "Dior", "Dior Sauvage EDT 100ml", "Christian Dior", True),
    # Same brand, completely different perfume → different key
    ("YSL Black Opium EDP 30ml", "YSL", "YSL Libre EDP 30ml", "Yves Saint Laurent", False),
    # Same perfume, different sizes → different products
    ("YSL Black Opium EDP 30ml", "YSL", "YSL Black Opium EDP 50ml", "Yves Saint Laurent", False),
]


@pytest.mark.parametrize("name1,brand1,name2,brand2,same_expected", EXACT_KEY_SAMPLES)
def test_dry_run_exact_key_consistency(name1, brand1, name2, brand2, same_expected):
    """Dry-run resolver uses deterministic keys; fuzzy merging requires a live DB."""
    l1 = make_listing(name1, brand1)
    l2 = make_listing(name2, brand2)
    id1 = _dry_run_resolve(l1)
    id2 = _dry_run_resolve(l2)
    if same_expected:
        assert id1 == id2, f"Expected same canonical for '{name1}' / '{name2}'"
    else:
        assert id1 != id2, f"Expected different canonicals for '{name1}' / '{name2}'"


# Fuzzy variants that would resolve to the same product in production (with live DB + rapidfuzz)
# but produce different dry-run keys due to name wording differences.
# These are documented here as known gaps — not bugs.
FUZZY_VARIANTS_NOTE = [
    # These pairs ARE the same real perfume but differ in name wording:
    # ("Dior Sauvage EDT 100ml",         "Dior Sauvage Eau de Toilette 100ml")  → fuzzy-merge in prod
    # ("Chanel No 5 EDP 50ml",           "CHANEL N°5 Eau de Parfum 50 ml")      → fuzzy-merge in prod
    # Dry-run gives them different IDs — that's expected and correct for the dry-run mode.
]


def test_fuzzy_variants_produce_different_dry_run_ids():
    """Confirm that name-wording variants yield distinct dry-run keys.
    In production the fuzzy step would merge them; in dry-run mode they stay separate.
    This is the expected behavior — documented here to avoid confusion.
    """
    l_edt = make_listing("Dior Sauvage EDT 100ml", "Dior")
    l_eau = make_listing("Dior Sauvage Eau de Toilette 100ml", "Christian Dior")
    assert _dry_run_resolve(l_edt) != _dry_run_resolve(l_eau), (
        "Wording variants must NOT be merged in dry-run (no fuzzy); "
        "this is intentional — the live DB fuzzy step handles it."
    )
