"""
schemas/admin.py
================
Pydantic schemas for the admin endpoints (scrape trigger + job status).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# POST /api/admin/scrape  — request body
# ---------------------------------------------------------------------------

VALID_SITES = {"primor", "sephora", "nocibe"}


class ScrapeRequest(BaseModel):
    sites: list[Literal["primor", "sephora", "nocibe"]]

    @field_validator("sites")
    @classmethod
    def non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one site must be specified.")
        return v


# ---------------------------------------------------------------------------
# POST /api/admin/scrape  — response
# ---------------------------------------------------------------------------

class ScrapeStartResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    sites: list[str]


# ---------------------------------------------------------------------------
# GET /api/admin/scrape/{job_id}  — response
# ---------------------------------------------------------------------------

class ScrapeJobOut(BaseModel):
    job_id: uuid.UUID
    status: str
    sites: list[str]
    started_at: datetime
    finished_at: datetime | None
    items_added: int
    items_updated: int
    items_errored: int
    duration_seconds: float | None

    @classmethod
    def from_orm_job(cls, job: object) -> ScrapeJobOut:
        from app.models.scrape_job import ScrapeJob  # avoid circular at module load

        j: ScrapeJob = job  # type: ignore[assignment]
        duration = None
        if j.finished_at and j.started_at:
            duration = (j.finished_at - j.started_at).total_seconds()
        return cls(
            job_id=j.id,
            status=j.status,
            sites=j.sites,
            started_at=j.started_at,
            finished_at=j.finished_at,
            items_added=j.items_added,
            items_updated=j.items_updated,
            items_errored=j.items_errored,
            duration_seconds=duration,
        )
