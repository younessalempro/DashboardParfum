"""
crud/scrape_jobs.py
===================
Helpers for creating and updating ScrapeJob records.
Used by the admin router and the scraper runner.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.scrape_error import ScrapeError
from app.models.scrape_job import ScrapeJob


def create_job(db: Session, sites: list[str]) -> ScrapeJob:
    """Create a new ScrapeJob in 'running' state and commit."""
    job = ScrapeJob(
        id=uuid.uuid4(),
        status="running",
        sites=sites,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: uuid.UUID) -> ScrapeJob | None:
    return db.get(ScrapeJob, job_id)


def complete_job(
    db: Session,
    job: ScrapeJob,
    *,
    items_added: int = 0,
    items_updated: int = 0,
    items_errored: int = 0,
) -> ScrapeJob:
    """Mark a job as done with final counts."""
    job.status = "done"
    job.finished_at = datetime.now(timezone.utc)
    job.items_added = items_added
    job.items_updated = items_updated
    job.items_errored = items_errored
    db.commit()
    db.refresh(job)
    return job


def fail_job(db: Session, job: ScrapeJob, error_message: str = "") -> ScrapeJob:
    """Mark a job as failed."""
    job.status = "failed"
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def log_error(
    db: Session,
    job: ScrapeJob,
    *,
    site: str | None = None,
    url: str | None = None,
    error_message: str | None = None,
    traceback: str | None = None,
) -> ScrapeError:
    """Persist a scrape error record."""
    err = ScrapeError(
        job_id=job.id,
        site=site,
        url=url,
        error_message=error_message,
        traceback=traceback,
    )
    db.add(err)
    db.commit()
    return err
