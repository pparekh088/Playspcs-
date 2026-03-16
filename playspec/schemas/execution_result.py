"""Execution result schema — structured output from Playwright test runs."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FailureType(str, Enum):
    SELECTOR_NOT_FOUND = "selector_not_found"
    ASSERTION_MISMATCH = "assertion_mismatch"
    TIMEOUT = "timeout"
    RUNTIME_ERROR = "runtime_error"
    FLAKY = "flaky"
    UNKNOWN = "unknown"


class TestFailure(BaseModel):
    """Details of a single test failure."""

    test_file: str
    test_name: str
    failure_type: FailureType = FailureType.UNKNOWN
    error_message: str = ""
    stack_trace: str = ""
    artifact_paths: list[str] = Field(default_factory=list)


class PassedTest(BaseModel):
    """Minimal record of a passing test (for stability tracking)."""

    test_file: str
    test_name: str


class ExecutionResult(BaseModel):
    """Aggregate result of a Playwright test execution run."""

    run_id: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[TestFailure] = Field(default_factory=list)
    passing_test_keys: list[str] = Field(default_factory=list)
    passed_tests: list[PassedTest] = Field(default_factory=list)
    duration_seconds: float = 0.0
