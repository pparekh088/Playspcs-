"""Tests for failure classification and suggested fix generation."""

import pytest

from playspec.executor.diagnostics import classify_failure, generate_suggested_fix, generate_suggested_fixes
from playspec.schemas.execution_result import ExecutionResult, TestFailure, FailureType
from playspec.schemas.suggested_fix import Confidence


class TestClassifyFailure:
    def test_selector_not_found(self):
        f = TestFailure(
            test_file="t.spec.ts", test_name="test",
            error_message="Timeout 5000ms exceeded waiting for selector '#btn'",
        )
        assert classify_failure(f) == FailureType.SELECTOR_NOT_FOUND

    def test_assertion_mismatch(self):
        f = TestFailure(
            test_file="t.spec.ts", test_name="test",
            error_message="expect(received).toHaveText(expected)\nExpected: 'Hello'\nReceived: 'World'",
        )
        assert classify_failure(f) == FailureType.ASSERTION_MISMATCH

    def test_timeout(self):
        f = TestFailure(
            test_file="t.spec.ts", test_name="test",
            error_message="Timeout 30000ms exceeded. Navigation timeout",
        )
        assert classify_failure(f) == FailureType.TIMEOUT

    def test_runtime_error(self):
        f = TestFailure(
            test_file="t.spec.ts", test_name="test",
            error_message="TypeError: Cannot read property 'click' of null",
        )
        assert classify_failure(f) == FailureType.RUNTIME_ERROR

    def test_unknown(self):
        f = TestFailure(
            test_file="t.spec.ts", test_name="test",
            error_message="some unusual thing happened",
        )
        assert classify_failure(f) == FailureType.UNKNOWN


class TestSuggestedFixes:
    def test_timeout_fix(self):
        f = TestFailure(
            test_file="t.spec.ts", test_name="test",
            failure_type=FailureType.TIMEOUT,
            error_message="Timeout 30s exceeded",
        )
        fix = generate_suggested_fix(f)
        assert fix is not None
        assert fix.confidence == Confidence.LOW
        assert "waitForLoadState" in fix.proposed_patch

    def test_assertion_fix(self):
        f = TestFailure(
            test_file="t.spec.ts", test_name="test",
            failure_type=FailureType.ASSERTION_MISMATCH,
            error_message="Expected 'A' got 'B'",
        )
        fix = generate_suggested_fix(f)
        assert fix is not None
        assert fix.confidence == Confidence.HIGH

    def test_batch_fixes(self):
        result = ExecutionResult(
            run_id="r",
            total_tests=3, passed=1, failed=2,
            failures=[
                TestFailure(test_file="a.spec.ts", test_name="t1", failure_type=FailureType.TIMEOUT, error_message="timeout"),
                TestFailure(test_file="b.spec.ts", test_name="t2", failure_type=FailureType.SELECTOR_NOT_FOUND, error_message="not found"),
            ],
        )
        fixes = generate_suggested_fixes(result)
        assert len(fixes) == 2
