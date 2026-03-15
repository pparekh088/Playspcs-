"""Suggested fix schema — diagnostic repair proposals (never auto-applied in regression mode)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from playspec.schemas.execution_result import FailureType


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SuggestedFix(BaseModel):
    """A proposed patch for a failing test, produced by heuristic diagnostics."""

    test_file: str
    test_name: str
    line_number: int | None = None
    failure_type: FailureType
    error_message: str = ""
    proposed_patch: str = ""
    confidence: Confidence = Confidence.LOW
