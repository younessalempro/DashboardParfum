"""
matcher/normalize.py
====================
Text normalisation utilities for product name / brand matching.

All functions are pure (no I/O, no DB) so they're easy to unit-test.

Pipeline for a product name
----------------------------
1. Lowercase.
2. Strip accents (NFD decomposition → remove Mn category characters).
3. Remove punctuation (keep alphanumeric + space).
4. Extract ``size_ml`` via regex and remove the size token from the name.
5. Collapse multiple spaces.

Brand canonicalization
-----------------------
A curated lookup table maps known brand variants to their canonical form.
For example:

    "christian dior"  → "dior"
    "yves saint laurent" → "ysl"
    "giorgio armani"  → "armani"
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Brand canonicalization table
# ---------------------------------------------------------------------------

# Keys: normalised (lowercase, no accents, no punctuation) variants.
# Values: canonical brand slug used in the database.
BRAND_ALIASES: dict[str, str] = {
    # Dior
    "christian dior": "dior",
    "parfums christian dior": "dior",
    # YSL
    "yves saint laurent": "ysl",
    "saint laurent": "ysl",
    "ysl beaute": "ysl",
    "ysl beauté": "ysl",
    # Armani
    "giorgio armani": "armani",
    "armani beauty": "armani",
    "armani parfums": "armani",
    # Chanel
    "chanel": "chanel",
    "parfums chanel": "chanel",
    # Guerlain
    "guerlain": "guerlain",
    "parfums guerlain": "guerlain",
    # Givenchy
    "givenchy": "givenchy",
    "parfums givenchy": "givenchy",
    # Lancôme
    "lancome": "lancome",
    "lancôme": "lancome",
    # Hermès
    "hermes": "hermes",
    "hermès": "hermes",
    # Thierry Mugler
    "thierry mugler": "mugler",
    "mugler": "mugler",
    # Paco Rabanne
    "paco rabanne": "paco rabanne",
    "rabanne": "paco rabanne",
    # Viktor & Rolf
    "viktor rolf": "viktor and rolf",
    "viktor & rolf": "viktor and rolf",
    "viktor and rolf": "viktor and rolf",
    # Versace
    "versace": "versace",
    "gianni versace": "versace",
    # Jean Paul Gaultier
    "jean paul gaultier": "jpgaultier",
    "jp gaultier": "jpgaultier",
    "jpgaultier": "jpgaultier",
    # Kenzo
    "kenzo": "kenzo",
    # Boss
    "hugo boss": "boss",
    "boss": "boss",
    # Dolce Gabbana
    "dolce gabbana": "dolce and gabbana",
    "dolce & gabbana": "dolce and gabbana",
    "dolce and gabbana": "dolce and gabbana",
    # Burberry
    "burberry": "burberry",
    "burberry parfums": "burberry",
    # Cartier
    "cartier": "cartier",
    "les must de cartier": "cartier",
    # Valentino
    "valentino": "valentino",
    "valentino beauty": "valentino",
    # Narciso Rodriguez
    "narciso rodriguez": "narciso rodriguez",
    # Tom Ford
    "tom ford": "tom ford",
    "tom ford beauty": "tom ford",
    # Carolina Herrera
    "carolina herrera": "carolina herrera",
    # Azzaro
    "azzaro": "azzaro",
    # Bulgari
    "bulgari": "bvlgari",
    "bvlgari": "bvlgari",
    "bvlgari parfums": "bvlgari",
    # Chloe
    "chloe": "chloe",
    "chloé": "chloe",
    # Issey Miyake
    "issey miyake": "issey miyake",
    # Maison Margiela
    "maison margiela": "margiela",
    "margiela": "margiela",
    "replica": "margiela",  # common misattribution
    # Diptyque
    "diptyque": "diptyque",
    # Byredo
    "byredo": "byredo",
    # Le Labo
    "le labo": "le labo",
}

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

_SIZE_ML_PATTERN = re.compile(r'\b(\d+)\s?ml\b', re.IGNORECASE)
_PUNCTUATION_RE = re.compile(r'[^\w\s]', re.UNICODE)
_SPACES_RE = re.compile(r'\s+')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    """Remove diacritical marks: 'é' → 'e', 'ç' → 'c', etc."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def normalize_text(text: str) -> str:
    """Full text normalization pipeline (no size stripping).

    Useful for brand normalization and intermediate steps.
    """
    text = text.lower()
    text = strip_accents(text)
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text


def extract_size_ml(text: str) -> int | None:
    """Return the first size in ml found in *text*, or None."""
    match = _SIZE_ML_PATTERN.search(text)
    return int(match.group(1)) if match else None


def strip_size_token(text: str) -> str:
    """Remove size tokens (e.g. '100ml', '50 ML') from *text*."""
    result = _SIZE_ML_PATTERN.sub(" ", text)
    return _SPACES_RE.sub(" ", result).strip()


def normalize_name(name: str) -> str:
    """Normalise a product name and strip the size token.

    Returns a string suitable for deterministic key matching.
    """
    norm = normalize_text(name)
    norm = strip_size_token(norm)
    return norm


def normalize_brand(brand: str) -> str:
    """Normalise a brand string and apply the canonicalization table.

    Returns the canonical brand slug, or the normalised brand if not found.
    """
    norm = normalize_text(brand)
    # Try full string first, then progressively shorter prefixes.
    if norm in BRAND_ALIASES:
        return BRAND_ALIASES[norm]
    # Check if any known alias is a substring of the normalised brand.
    for alias, canonical in BRAND_ALIASES.items():
        if alias in norm:
            return canonical
    return norm


def make_match_key(brand: str, name: str, size_ml: int | None) -> str:
    """Create the deterministic match key for a product.

    Format: ``"<brand_canonical>|<name_normalized>|<size_ml>"``

    Examples::

        make_match_key("Christian Dior", "Sauvage EDT 100ml", None)
        → "dior|sauvage edt|100"

        make_match_key("Dior", "Sauvage EDP", 50)
        → "dior|sauvage edp|50"
    """
    brand_norm = normalize_brand(brand)
    name_norm = normalize_name(name)
    size_part = str(size_ml) if size_ml is not None else "none"
    return f"{brand_norm}|{name_norm}|{size_part}"
