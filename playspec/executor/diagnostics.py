"""Failure diagnostics — heuristic classification and suggested fix generation."""

from __future__ import annotations

import re

from playspec.schemas.execution_result import ExecutionResult, TestFailure, FailureType
from playspec.schemas.suggested_fix import Confidence, SuggestedFix

_SELECTOR_PATTERNS = [
    re.compile(r"waiting for (selector|locator)", re.IGNORECASE),
    re.compile(r"no element found", re.IGNORECASE),
    re.compile(r"could not find", re.IGNORECASE),
    re.compile(r"Timeout.*waiting.*selector", re.IGNORECASE),
    re.compile(r"locator resolved to \d+ elements", re.IGNORECASE),
]

_TIMEOUT_PATTERNS = [
    re.compile(r"Timeout \d+ms exceeded", re.IGNORECASE),
    re.compile(r"navigation timeout", re.IGNORECASE),
    re.compile(r"page\.goto.*timeout", re.IGNORECASE),
]

_ASSERTION_PATTERNS = [
    re.compile(r"expect\(.*\)\.", re.IGNORECASE),
    re.compile(r"Expected.*Received", re.IGNORECASE),
    re.compile(r"toHaveText|toBeVisible|toHaveURL|toContainText", re.IGNORECASE),
    re.compile(r"AssertionError", re.IGNORECASE),
]


def classify_failure(failure: TestFailure) -> FailureType:
    """Classify a test failure by pattern-matching on the error message and stack trace."""
    text = f"{failure.error_message}\n{failure.stack_trace}"

    for p in _SELECTOR_PATTERNS:
        if p.search(text):
            return FailureType.SELECTOR_NOT_FOUND

    for p in _ASSERTION_PATTERNS:
        if p.search(text):
            return FailureType.ASSERTION_MISMATCH

    for p in _TIMEOUT_PATTERNS:
        if p.search(text):
            return FailureType.TIMEOUT

    if "Error" in text or "error" in text:
        return FailureType.RUNTIME_ERROR

    return FailureType.UNKNOWN


def generate_suggested_fix(failure: TestFailure) -> SuggestedFix | None:
    """Produce a heuristic fix suggestion for a classified failure."""
    ft = failure.failure_type

    if ft == FailureType.SELECTOR_NOT_FOUND:
        return SuggestedFix(
            test_file=failure.test_file,
            test_name=failure.test_name,
            failure_type=ft,
            error_message=failure.error_message,
            proposed_patch="// Consider using a more resilient selector (data-testid, role, or text content).",
            confidence=Confidence.MEDIUM,
        )

    if ft == FailureType.TIMEOUT:
        return SuggestedFix(
            test_file=failure.test_file,
            test_name=failure.test_name,
            failure_type=ft,
            error_message=failure.error_message,
            proposed_patch="// Add await page.waitForLoadState('networkidle') before the assertion, or increase the timeout.",
            confidence=Confidence.LOW,
        )

    if ft == FailureType.ASSERTION_MISMATCH:
        return SuggestedFix(
            test_file=failure.test_file,
            test_name=failure.test_name,
            failure_type=ft,
            error_message=failure.error_message,
            proposed_patch=f"// Expected value does not match actual. Review: {failure.error_message[:200]}",
            confidence=Confidence.HIGH,
        )

    return None


def generate_suggested_fixes(result: ExecutionResult) -> list[SuggestedFix]:
    """Generate suggested fixes for all failures in an execution result."""
    fixes: list[SuggestedFix] = []
    for failure in result.failures:
        fix = generate_suggested_fix(failure)
        if fix:
            fixes.append(fix)
    return fixes
