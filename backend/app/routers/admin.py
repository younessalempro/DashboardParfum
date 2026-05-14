"""
routers/admin.py
================
Admin-only endpoints. Protected by X-Admin-Token header.

POST /api/admin/scrape          — trigger on-demand scrape
GET  /api/admin/scrape/{job_id} — poll job status
"""
from __future__ import annotations

import traceback
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.crud.scrape_jobs import complete_job, create_job, fail_job, get_job, log_error
from app.db import SessionLocal, get_session
from app.schemas.admin import ScrapeJobOut, ScrapeRequest, ScrapeStartResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])

DB = Annotated[Session, Depends(get_session)]


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_admin_token(x_admin_token: str = Header(...)) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


AdminAuth = Annotated[None, Depends(require_admin_token)]


# ---------------------------------------------------------------------------
# Background scrape task
# ---------------------------------------------------------------------------

def _run_scrape(job_id: uuid.UUID, sites: list[str]) -> None:
    """Run the scrape in a background thread (FastAPI BackgroundTasks)."""
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if job is None:
            return

        from app.scrapers.runner import run_scrape  # local import to avoid circular

        result = run_scrape(db=db, job=job, sites=sites)
        complete_job(
            db,
            job,
            items_added=result.total_added,
            items_updated=result.total_updated,
            items_errored=result.total_errored,
        )
    except Exception as exc:
        db2 = SessionLocal()
        try:
            job2 = get_job(db2, job_id)
            if job2:
                log_error(
                    db2,
                    job2,
                    error_message=str(exc),
                    traceback=traceback.format_exc(),
                )
                fail_job(db2, job2, error_message=str(exc))
        finally:
            db2.close()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/scrape", response_model=ScrapeStartResponse, status_code=202)
def trigger_scrape(
    body: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: DB,
    _: AdminAuth,
) -> ScrapeStartResponse:
    """
    Kick off a background scrape for the given sites.
    Returns immediately with a job_id to poll for status.
    """
    job = create_job(db, sites=body.sites)
    background_tasks.add_task(_run_scrape, job.id, body.sites)
    return ScrapeStartResponse(job_id=job.id, status=job.status, sites=job.sites)


@router.get("/scrape/{job_id}", response_model=ScrapeJobOut)
def scrape_status(job_id: uuid.UUID, db: DB, _: AdminAuth) -> ScrapeJobOut:
    """
    Return the current status and counters for a scrape job.
    """
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return ScrapeJobOut.from_orm_job(job)
