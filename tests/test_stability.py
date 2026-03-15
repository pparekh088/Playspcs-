"""Tests for stability tracking."""

import json
import pytest
from pathlib import Path

from playspec.stability import StabilityStore, TestStabilityRecord as StabilityRecord, load_stability, save_stability
from playspec.schemas.execution_result import ExecutionResult, TestFailure, FailureType


class TestStabilityRecordBehavior:
    def test_record_pass(self):
        rec = StabilityRecord()
        rec.record_pass("run-1")
        assert rec.pass_count == 1
        assert rec.flaky_score == 1.0
        assert rec.last_known_good_run_id == "run-1"

    def test_record_fail(self):
        rec = StabilityRecord()
        rec.record_fail()
        assert rec.fail_count == 1
        assert rec.flaky_score == 0.0

    def test_mixed_results(self):
        rec = StabilityRecord()
        for _ in range(8):
            rec.record_pass("r")
        for _ in range(2):
            rec.record_fail()
        assert rec.flaky_score == pytest.approx(0.8)

    def test_rolling_window(self):
        rec = StabilityRecord()
        for _ in range(25):
            rec.record_pass("r")
        assert len(rec.last_n_results) == 20


class TestStabilityStore:
    def test_update_with_failures(self):
        result = ExecutionResult(
            run_id="test-run",
            total_tests=2,
            passed=1,
            failed=1,
            failures=[TestFailure(test_file="a.spec.ts", test_name="test1", failure_type=FailureType.TIMEOUT)],
        )
        store = StabilityStore()
        store.update(result)
        assert "a.spec.ts::test1" in store.records
        assert store.records["a.spec.ts::test1"].fail_count == 1

    def test_flaky_detection(self):
        store = StabilityStore()
        rec = StabilityRecord()
        for _ in range(5):
            rec.record_pass("r")
        for _ in range(5):
            rec.record_fail()
        store.records["flaky::test"] = rec
        assert "flaky::test" in store.get_flaky_tests(threshold=0.9)
        assert "flaky::test" in store.recommend_quarantine(threshold=0.6)

    def test_serialization(self, tmp_path):
        store = StabilityStore()
        rec = StabilityRecord()
        rec.record_pass("run-1")
        store.records["test::one"] = rec

        path = tmp_path / "stability.json"
        save_stability(store, path)
        loaded = load_stability(path)
        assert "test::one" in loaded.records
        assert loaded.records["test::one"].pass_count == 1

    def test_load_empty(self, tmp_path):
        store = load_stability(tmp_path / "missing.json")
        assert store.records == {}

    def test_load_corrupt(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        store = load_stability(path)
        assert store.records == {}
