"""
scrapers/runner.py
==================
Orchestrator for a full scrape pass.

Responsibilities
----------------
1. Instantiate all active scrapers.
2. For each scraper, iterate ``list_category_urls()`` and collect
   ``RawListing`` objects from ``scrape_category(url)``.
3. Pass each listing through the matcher (``resolver.resolve``).
4. Upsert the ``listing`` DB record and append a ``price_snapshot``.
5. Record the overall job in ``scrape_job`` (start time, end time, counts).
6. Write per-item failures to ``scrape_error`` (with full context for debug).
7. Log a summary per site at the end.

Usage
-----
Called by the FastAPI admin endpoint or directly from the CLI::

    # from CLI
    python -m backend.app.scrapers.runner

    # from FastAPI (background task)
    from backend.app.scrapers.runner import run_scrape
    job_id = await run_scrape(sites=["primor", "nocibe"])

Database interface (provided by Dev 2)
---------------------------------------
The runner imports from ``backend.app.db`` (SQLAlchemy session factory) and
from ``backend.app.models.*``.  During early development, when those don't
exist yet, it runs in ``--dry-run`` mode and only prints what it *would* write.
"""
from __future__ import annotations

import logging
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .base import BaseScraper, RawListing
from .nocibe import NocibeScraper
from .primor import PrimorScraper
from .sephora import SephoraScraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry — add new scrapers here
# ---------------------------------------------------------------------------

ALL_SCRAPERS: dict[str, type[BaseScraper]] = {
    "primor": PrimorScraper,
    "nocibe": NocibeScraper,
    "sephora": SephoraScraper,
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SiteResult:
    site: str
    added: int = 0
    updated: int = 0
    errored: int = 0
    errors: list[dict] = field(default_factory=list)


@dataclass
class JobResult:
    job_id: str
    started_at: datetime
    finished_at: datetime | None = None
    sites: dict[str, SiteResult] = field(default_factory=dict)
    status: str = "running"  # "running" | "done" | "failed"

    @property
    def total_added(self) -> int:
        return sum(r.added for r in self.sites.values())

    @property
    def total_updated(self) -> int:
        return sum(r.updated for r in self.sites.values())

    @property
    def total_errored(self) -> int:
        return sum(r.errored for r in self.sites.values())


# ---------------------------------------------------------------------------
# Database interface (guarded import — works without DB during dev)
# ---------------------------------------------------------------------------

def _try_import_db():
    """Return (db_session_factory, models) or (None, None) in dry-run mode."""
    try:
        from app import models  # type: ignore[import]
        from app.db import SessionLocal  # type: ignore[import]
        return SessionLocal, models
    except ImportError:
        return None, None


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------

def run_scrape(
    db=None,
    job=None,
    sites: list[str] | None = None,
    *,
    dry_run: bool = False,
) -> JobResult:
    """Run a full scrape pass for *sites* (default: all scrapers).

    Parameters
    ----------
    db:
        SQLAlchemy Session, provided by the admin router for status tracking.
        When None the runner falls back to its own session management.
    job:
        ORM ScrapeJob instance associated with this run, used to update
        status counters. When None a standalone JobResult is used.
    sites:
        Subset of scraper keys to run, e.g. ``["primor", "nocibe"]``.
        Pass ``None`` to run all registered scrapers.
    dry_run:
        When True, scrape and match normally but skip all DB writes.
        Useful for testing scrapers in isolation.

    Returns
    -------
    JobResult
        Summary of the scrape pass (counts per site, errors, timing).
    """
    SessionLocal, models = _try_import_db()
    if SessionLocal is None or dry_run:
        dry_run = True
        logger.info("Runner: DB not available or dry_run=True — skipping all DB writes.")

    # Resolve which scrapers to run.
    selected_keys = sites or list(ALL_SCRAPERS.keys())
    unknown = set(selected_keys) - set(ALL_SCRAPERS.keys())
    if unknown:
        raise ValueError(f"Unknown scraper site(s): {unknown}. Valid: {set(ALL_SCRAPERS.keys())}")

    job_id = str(uuid.uuid4())
    job_result = JobResult(
        job_id=job_id,
        started_at=datetime.now(tz=timezone.utc),
    )

    logger.info("=== Scrape job %s started (sites: %s) ===", job_id, selected_keys)

    # Record job start in DB.
    if not dry_run:
        _write_job_start(SessionLocal, models, job_result)

    # -----------------------------------------------------------------------
    # Main scrape loop
    # -----------------------------------------------------------------------

    for site_key in selected_keys:
        site_result = SiteResult(site=site_key)
        job_result.sites[site_key] = site_result

        scraper_cls = ALL_SCRAPERS[site_key]
        try:
            scraper = scraper_cls()
        except Exception as exc:
            logger.error("[%s] Failed to instantiate scraper: %s", site_key, exc)
            site_result.errored += 1
            continue

        category_urls = scraper.list_category_urls()
        logger.info("[%s] %d categories to scrape", site_key, len(category_urls))

        for cat_url in category_urls:
            try:
                listings = list(scraper.scrape_category(cat_url))
            except Exception as exc:
                logger.error("[%s] Category scrape failed for %s: %s", site_key, cat_url, exc)
                site_result.errored += 1
                site_result.errors.append({
                    "url": cat_url,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })
                if not dry_run:
                    _write_scrape_error(
                        SessionLocal, models, job_id, site_key, cat_url, exc
                    )
                continue

            for listing in listings:
                try:
                    _process_listing(
                        listing,
                        site_result,
                        job_id,
                        dry_run=dry_run,
                        SessionLocal=SessionLocal,
                        models=models,
                    )
                except Exception as exc:
                    logger.error(
                        "[%s] Failed to process listing %s: %s",
                        site_key, listing.site_product_id, exc,
                    )
                    site_result.errored += 1
                    site_result.errors.append({
                        "url": listing.url,
                        "sku": listing.site_product_id,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    })
                    if not dry_run:
                        _write_scrape_error(
                            SessionLocal, models, job_id, site_key, listing.url, exc
                        )

        logger.info(
            "[%s] done — added=%d updated=%d errored=%d",
            site_key, site_result.added, site_result.updated, site_result.errored,
        )

    # -----------------------------------------------------------------------
    # Finalise
    # -----------------------------------------------------------------------

    job_result.finished_at = datetime.now(tz=timezone.utc)
    job_result.status = "done"

    elapsed = (job_result.finished_at - job_result.started_at).total_seconds()
    logger.info(
        "=== Job %s finished in %.1f s — total: added=%d updated=%d errored=%d ===",
        job_id, elapsed,
        job_result.total_added, job_result.total_updated, job_result.total_errored,
    )

    if not dry_run:
        _write_job_end(SessionLocal, models, job_result)

    return job_result


# ---------------------------------------------------------------------------
# Per-listing processing
# ---------------------------------------------------------------------------

def _process_listing(
    listing: RawListing,
    site_result: SiteResult,
    job_id: str,
    *,
    dry_run: bool,
    SessionLocal,
    models,
) -> None:
    """Match → upsert listing → append price snapshot → (optionally) enqueue review."""
    from app.matcher.resolver import resolve  # type: ignore[import]

    result = resolve(listing)
    canonical_id = result.canonical_id  # str UUID or None (review queue)

    if dry_run:
        logger.debug(
            "[dry-run] %s %s → canonical=%s price=%s in_stock=%s",
            listing.site, listing.site_product_id,
            canonical_id, listing.price, listing.in_stock,
        )
        site_result.added += 1
        return

    with SessionLocal() as session:
        # Upsert listing record.
        existing = (
            session.query(models.Listing)
            .filter_by(site=listing.site, site_product_id=listing.site_product_id)
            .first()
        )
        now = datetime.now(tz=timezone.utc)

        if existing is None:
            db_listing = models.Listing(
                id=str(uuid.uuid4()),
                canonical_product_id=canonical_id,
                site=listing.site,
                site_product_id=listing.site_product_id,
                url=listing.url,
                name_on_site=listing.name,
                brand_on_site=listing.brand,
                image_url=listing.image_url,
                last_seen_at=now,
            )
            session.add(db_listing)
            site_result.added += 1
        else:
            existing.canonical_product_id = canonical_id or existing.canonical_product_id
            existing.url = listing.url
            existing.name_on_site = listing.name
            existing.brand_on_site = listing.brand
            existing.image_url = listing.image_url or existing.image_url
            existing.last_seen_at = now
            db_listing = existing
            site_result.updated += 1

        session.flush()  # ensure db_listing.id is set

        # Back-fill size_ml on the canonical product if the scraper now has it
        # and the DB record is still null (happens on first re-scrape after the
        # multi-variant fix was deployed).
        if listing.size_ml is not None and canonical_id is not None:
            try:
                canonical = (
                    session.query(models.CanonicalProduct)
                    .filter_by(id=canonical_id)
                    .first()
                )
                if canonical is not None and canonical.size_ml is None:
                    canonical.size_ml = listing.size_ml
            except Exception as exc:
                logger.warning(
                    "[runner] could not back-fill size_ml for canonical %s: %s",
                    canonical_id, exc,
                )

        # Append price snapshot.
        snapshot = models.PriceSnapshot(
            listing_id=db_listing.id,
            price=listing.price,
            currency=listing.currency,
            in_stock=listing.in_stock,
            scraped_at=now,
        )
        session.add(snapshot)

        # If the resolver flagged a fuzzy near-match for review, write the queue
        # entry now that we have a committed listing_id.
        if result.review_candidate_id is not None:
            try:
                queue_entry = models.MatchReviewQueue(
                    listing_id=db_listing.id,
                    candidate_canonical_id=result.review_candidate_id,
                    score=result.review_score,
                    status="pending",
                )
                session.add(queue_entry)
            except Exception as qe:
                logger.warning(
                    "[runner] could not enqueue review for %s %s: %s",
                    listing.site, listing.site_product_id, qe,
                )

        session.commit()


# ---------------------------------------------------------------------------
# DB write helpers (stubs — fill in once models are available)
# ---------------------------------------------------------------------------

def _write_job_start(SessionLocal, models, job: JobResult) -> None:
    try:
        with SessionLocal() as session:
            db_job = models.ScrapeJob(
                id=job.job_id,
                started_at=job.started_at,
                status="running",
            )
            session.add(db_job)
            session.commit()
    except Exception as exc:
        logger.warning("Could not write job start to DB: %s", exc)


def _write_job_end(SessionLocal, models, job: JobResult) -> None:
    try:
        with SessionLocal() as session:
            db_job = session.query(models.ScrapeJob).get(job.job_id)
            if db_job:
                db_job.finished_at = job.finished_at
                db_job.status = job.status
                db_job.total_added = job.total_added
                db_job.total_updated = job.total_updated
                db_job.total_errored = job.total_errored
                session.commit()
    except Exception as exc:
        logger.warning("Could not write job end to DB: %s", exc)


def _write_scrape_error(
    SessionLocal, models, job_id: str, site: str, url: str, exc: Exception
) -> None:
    try:
        with SessionLocal() as session:
            err = models.ScrapeError(
                id=str(uuid.uuid4()),
                job_id=job_id,
                site=site,
                url=url,
                error_type=type(exc).__name__,
                error_message=str(exc),
                traceback=traceback.format_exc(),
                occurred_at=datetime.now(tz=timezone.utc),
            )
            session.add(err)
            session.commit()
    except Exception as db_exc:
        logger.warning("Could not write scrape error to DB: %s", db_exc)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Run the perfume price scraper")
    parser.add_argument(
        "--sites",
        nargs="*",
        choices=list(ALL_SCRAPERS.keys()),
        default=None,
        help="Which sites to scrape (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and match but skip all DB writes",
    )
    args = parser.parse_args()

    result = run_scrape(sites=args.sites, dry_run=args.dry_run)
    print(
        f"\nJob {result.job_id} — status={result.status} "
        f"added={result.total_added} updated={result.total_updated} errored={result.total_errored}"
    )
    if result.total_errored:
        sys.exit(1)
