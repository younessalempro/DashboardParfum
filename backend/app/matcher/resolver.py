"""
matcher/resolver.py
===================
Resolves a ``RawListing`` to a ``canonical_product_id`` in the database.

Three-step algorithm
---------------------
1. **Deterministic key match**
   Compute ``(brand_normalized, name_normalized, size_ml)`` and look for an
   exact match in ``canonical_product``.  95 %+ of cases resolve here.

2. **Fuzzy fallback** (within same ``brand_normalized``)
   Use ``rapidfuzz.token_sort_ratio`` to compare the normalised listing name
   against all canonical product names for the same brand.

   - Score ≥ 92 → auto-merge (link listing to existing canonical).
   - Score 80–91 → enqueue for manual review after listing is written;
     return ``None`` for canonical_product_id (listing saved without a link).
   - Score < 80 → create a new ``canonical_product``; return its ID.

3. **New product**
   If no match at all, insert a new ``canonical_product`` and return its ID.

Dry-run / offline mode
-----------------------
When the database is not available (models not yet written, running tests),
``resolve()`` logs what it *would* do and returns a synthetic UUID so the
rest of the pipeline can continue.

Dependencies
------------
- ``rapidfuzz`` for fuzzy string matching.
- ``backend.app.models`` for ORM types (guarded import).
- ``backend.app.db`` for the SQLAlchemy session factory (guarded import).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from ..scrapers.base import RawListing
from .normalize import (
    extract_size_ml,
    make_match_key,
    normalize_brand,
    normalize_name,
)

logger = logging.getLogger(__name__)

# Fuzzy score thresholds.
AUTO_MERGE_THRESHOLD = 92
REVIEW_QUEUE_THRESHOLD = 80


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ResolveResult:
    """Result of resolving a listing to a canonical product.

    Attributes
    ----------
    canonical_id:
        UUID string of the canonical product, or None if the listing was placed
        in the review queue.
    review_candidate_id:
        UUID string of the candidate canonical product to compare against in the
        review queue (only set when ``canonical_id is None`` and a fuzzy near-
        match was found).  The runner should write a ``MatchReviewQueue`` row
        using this after the Listing row is committed.
    review_score:
        Fuzzy match score (0–100) for the review candidate, or None.
    """
    canonical_id: str | None
    review_candidate_id: str | None = None
    review_score: float | None = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def resolve(listing: RawListing) -> ResolveResult:
    """Resolve *listing* to a canonical product.

    Returns
    -------
    ResolveResult
        Always returns a ResolveResult.  ``canonical_id`` is None only when
        the listing was placed in the manual review queue (score 80–91).
    """
    try:
        SessionLocal, models = _try_import_db()
    except Exception as exc:
        logger.warning("DB not available — resolve() running in dry-run mode: %s", exc)
        return ResolveResult(canonical_id=_dry_run_resolve(listing))

    if SessionLocal is None:
        return ResolveResult(canonical_id=_dry_run_resolve(listing))

    brand_norm = normalize_brand(listing.brand)
    name_norm = normalize_name(listing.name)
    size_ml = listing.size_ml or extract_size_ml(listing.name)
    key = make_match_key(listing.brand, listing.name, size_ml)

    with SessionLocal() as session:
        # Step 1 — deterministic key match.
        canonical = _deterministic_match(session, models, brand_norm, name_norm, size_ml)
        if canonical is not None:
            logger.debug("[resolver] deterministic match: %s → %s", key, canonical.id)
            return ResolveResult(canonical_id=str(canonical.id))

        # Step 2 — fuzzy match within brand.
        action, value, score = _fuzzy_match(session, models, brand_norm, name_norm)

        if action == "matched":
            logger.info("[resolver] fuzzy auto-merge (score=%.1f): %s → %s", score, key, value)
            return ResolveResult(canonical_id=value)

        if action == "queued":
            # Return None canonical_id + the candidate so the runner can write
            # the MatchReviewQueue row after the Listing is committed.
            logger.info(
                "[resolver] fuzzy review queue (score=%.1f): %s vs candidate=%s",
                score, key, value,
            )
            return ResolveResult(
                canonical_id=None,
                review_candidate_id=value,
                review_score=score,
            )

        # action == "create" — fall through to step 3.

        # Step 3 — create new canonical product.
        new_id = _create_canonical(session, models, listing, brand_norm, name_norm, size_ml)
        return ResolveResult(canonical_id=new_id)


# ---------------------------------------------------------------------------
# Step 1 — deterministic key match
# ---------------------------------------------------------------------------

def _deterministic_match(session, models, brand_norm: str, name_norm: str, size_ml: int | None):
    """Return the matching CanonicalProduct or None."""
    try:
        return (
            session.query(models.CanonicalProduct)
            .filter(
                models.CanonicalProduct.brand == brand_norm,
                models.CanonicalProduct.name == name_norm,
                models.CanonicalProduct.size_ml == size_ml,
            )
            .first()
        )
    except Exception as exc:
        logger.error("[resolver] deterministic match DB error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Step 2 — fuzzy match
# ---------------------------------------------------------------------------

def _fuzzy_match(
    session,
    models,
    brand_norm: str,
    name_norm: str,
) -> tuple[str, str | None, float]:
    """Fuzzy search among canonical products for the same brand.

    Returns
    -------
    tuple[str, str | None, float]
        (action, candidate_id_or_none, score) where action is one of:
        - ``"matched"`` : auto-merged; candidate_id is the canonical product ID.
        - ``"queued"``  : near-match for review; candidate_id is the candidate ID.
        - ``"create"``  : no match; candidate_id is None; caller creates new product.
    """
    try:
        from rapidfuzz import fuzz  # type: ignore[import]
    except ImportError:
        logger.warning("[resolver] rapidfuzz not installed — skipping fuzzy match")
        return ("create", None, 0.0)

    # Load all canonical products for this brand.
    try:
        candidates = (
            session.query(models.CanonicalProduct)
            .filter(models.CanonicalProduct.brand == brand_norm)
            .all()
        )
    except Exception as exc:
        logger.error("[resolver] fuzzy match DB error: %s", exc)
        return ("create", None, 0.0)
    if not candidates:
        return ("create", None, 0.0)

    best_score = 0.0
    best_candidate = None

    for candidate in candidates:
        score = fuzz.token_sort_ratio(name_norm, candidate.name)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_score >= AUTO_MERGE_THRESHOLD:
        return ("matched", str(best_candidate.id), best_score)

    if best_score >= REVIEW_QUEUE_THRESHOLD:
        return ("queued", str(best_candidate.id), best_score)

    # Score < threshold — no match, create new canonical product.
    return ("create", None, best_score)


# ---------------------------------------------------------------------------
# Step 3 — create new canonical product
# ---------------------------------------------------------------------------

def _create_canonical(
    session,
    models,
    listing: RawListing,
    brand_norm: str,
    name_norm: str,
    size_ml: int | None,
) -> str:
    """Insert a new canonical_product and return its ID."""
    try:
        new_id = str(uuid.uuid4())
        canonical = models.CanonicalProduct(
            id=new_id,
            brand=brand_norm,
            name=name_norm,
            size_ml=size_ml,
            image_url=listing.image_url,
        )
        session.add(canonical)
        session.flush()
        session.commit()
        logger.info(
            "[resolver] created new canonical product %s: %s / %s / %s ml",
            new_id, brand_norm, name_norm, size_ml,
        )
        return new_id
    except Exception as exc:
        logger.error("[resolver] failed to create canonical product: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Dry-run / offline mode
# ---------------------------------------------------------------------------

def _dry_run_resolve(listing: RawListing) -> str:
    """Simulate resolution without a database.  Returns a synthetic UUID."""
    size_ml = listing.size_ml or extract_size_ml(listing.name)
    key = make_match_key(listing.brand, listing.name, size_ml)
    synthetic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, key))
    logger.debug("[resolver][dry-run] %s → %s", key, synthetic_id)
    return synthetic_id


# ---------------------------------------------------------------------------
# DB import guard
# ---------------------------------------------------------------------------

def _try_import_db():
    """Return (SessionLocal, models) or (None, None) if not available."""
    try:
        from app import models  # type: ignore[import]
        from app.db import SessionLocal  # type: ignore[import]
        return SessionLocal, models
    except ImportError:
        return None, None
