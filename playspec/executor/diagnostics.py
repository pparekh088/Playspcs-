"""Failure diagnostics — heuristic classification and executable patch generation."""

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

# Extracts the selector string from Playwright error messages like:
#   waiting for locator('#old-id')
#   waiting for selector ".some-class"
_SELECTOR_EXTRACT = re.compile(r"""(?:locator|selector)\s*\(?\s*['"`]([^'"`]+)['"`]""", re.IGNORECASE)

# Extracts Expected/Received values from assertion errors
_EXPECTED_EXTRACT = re.compile(r"Expected[:\s]+(.+?)(?:\n|Received)", re.DOTALL)
_RECEIVED_EXTRACT = re.compile(r"Received[:\s]+(.+?)(?:\n|$)", re.DOTALL)


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


def _make_selector_patch(failure: TestFailure) -> tuple[str, bool]:
    """Return (patch_code, is_auto_applicable) for a selector-not-found failure.

    When we can extract the broken selector we generate a direct replacement.
    Otherwise we produce a descriptive comment.
    """
    match = _SELECTOR_EXTRACT.search(failure.error_message + "\n" + failure.stack_trace)
    if not match:
        return (
            "// Could not extract selector from error. Inspect the DOM and update the locator "
            "to use data-testid, role, or visible text.",
            False,
        )

    old_selector = match.group(1)

    # Prefer data-testid; derive a candidate name from the selector
    stem = re.sub(r"[^a-zA-Z0-9-_]", "", old_selector.split("/")[-1]).lower().strip("-_") or "element"

    patch = (
        f"// AUTO-FIX: selector '{old_selector}' was not found.\n"
        f"// Replace with a resilient locator — options in order of preference:\n"
        f"//   page.getByTestId('{stem}')                          // requires data-testid\n"
        f"//   page.getByRole('button', {{ name: '{stem}' }})       // ARIA role\n"
        f"//   page.getByText('{stem}')                            // visible text\n"
        f"// Broken selector: page.locator('{old_selector}')"
    )
    # We can identify the bad selector but not auto-pick the replacement without
    # live DOM access, so flag as not auto-applicable.
    return patch, False


def _make_timeout_patch(failure: TestFailure) -> tuple[str, bool]:
    """Return (patch_code, is_auto_applicable) for a timeout failure."""
    text = failure.error_message + "\n" + failure.stack_trace

    if re.search(r"page\.goto", text, re.IGNORECASE):
        patch = (
            "// AUTO-FIX: navigation timed out.\n"
            "// Add after page.goto(...):\n"
            "await page.waitForLoadState('networkidle');"
        )
        return patch, True

    patch = (
        "// AUTO-FIX: action timed out waiting for element or network.\n"
        "// Add before the failing line:\n"
        "await page.waitForLoadState('domcontentloaded');"
    )
    return patch, True


def _make_assertion_patch(failure: TestFailure) -> tuple[str, bool]:
    """Return (patch_code, is_auto_applicable) for an assertion mismatch."""
    expected_m = _EXPECTED_EXTRACT.search(failure.error_message)
    received_m = _RECEIVED_EXTRACT.search(failure.error_message)

    if expected_m and received_m:
        expected = expected_m.group(1).strip()[:120]
        received = received_m.group(1).strip()[:120]
        patch = (
            f"// AUTO-FIX: assertion mismatch.\n"
            f"// Expected : {expected}\n"
            f"// Received : {received}\n"
            f"// Update the expected value in the assertion if the spec changed."
        )
        return patch, False

    patch = f"// Assertion mismatch. Review: {failure.error_message[:200]}"
    return patch, False


def generate_suggested_fix(failure: TestFailure) -> SuggestedFix | None:
    """Produce a heuristic fix suggestion for a classified failure."""
    ft = failure.failure_type

    if ft == FailureType.SELECTOR_NOT_FOUND:
        patch, auto = _make_selector_patch(failure)
        return SuggestedFix(
            test_file=failure.test_file,
            test_name=failure.test_name,
            failure_type=ft,
            error_message=failure.error_message,
            proposed_patch=patch,
            confidence=Confidence.MEDIUM,
            is_auto_applicable=auto,
        )

    if ft == FailureType.TIMEOUT:
        patch, auto = _make_timeout_patch(failure)
        return SuggestedFix(
            test_file=failure.test_file,
            test_name=failure.test_name,
            failure_type=ft,
            error_message=failure.error_message,
            proposed_patch=patch,
            confidence=Confidence.LOW,
            is_auto_applicable=auto,
        )

    if ft == FailureType.ASSERTION_MISMATCH:
        patch, auto = _make_assertion_patch(failure)
        return SuggestedFix(
            test_file=failure.test_file,
            test_name=failure.test_name,
            failure_type=ft,
            error_message=failure.error_message,
            proposed_patch=patch,
            confidence=Confidence.HIGH,
            is_auto_applicable=auto,
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
