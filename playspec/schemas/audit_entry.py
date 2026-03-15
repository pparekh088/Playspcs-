"""Audit entry schema — immutable record of every PlaySpec run."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    AUTHOR = "author"
    REGRESSION = "regression"


class AuditPhase(BaseModel):
    """A phase within an author-mode run (context, planning, generation, repair)."""

    name: str
    duration_seconds: float = 0.0
    backend_used: str | None = None
    prompt_hash: str | None = None
    success: bool = True
    error: str | None = None


class AuditResults(BaseModel):
    """Pass/fail/skip counts embedded in an audit entry."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0


class AuditEntry(BaseModel):
    """Immutable audit record for a single PlaySpec run."""

    run_id: str
    mode: RunMode
    profile: str = "local-dev"
    suite: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float = 0.0
    agent_backend_used: str | None = None
    trigger: str = "manual"
    git_ref: str | None = None
    git_sha: str | None = None
    environment: str | None = None
    resolved_tests: int = 0
    quarantined_skipped: int = 0
    results: AuditResults = Field(default_factory=AuditResults)
    failures: list[str] = Field(default_factory=list)
    stability_updates: int = 0
    coverage_drift: float | None = None
    phases: list[AuditPhase] = Field(default_factory=list)
