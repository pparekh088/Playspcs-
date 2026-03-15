"""Stability tracker — per-test pass/fail history and flaky detection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from playspec.schemas.execution_result import ExecutionResult


class TestStabilityRecord(BaseModel):
    """Rolling stability metrics for a single test."""

    pass_count: int = 0
    fail_count: int = 0
    last_n_results: list[bool] = Field(default_factory=list)
    last_passed_at: str | None = None
    last_failed_at: str | None = None
    last_known_good_run_id: str | None = None
    flaky_score: float = 1.0
    owner: str | None = None

    @property
    def total_runs(self) -> int:
        return self.pass_count + self.fail_count

    def record_pass(self, run_id: str, window: int = 20) -> None:
        self.pass_count += 1
        self.last_passed_at = datetime.now(timezone.utc).isoformat()
        self.last_known_good_run_id = run_id
        self.last_n_results.append(True)
        if len(self.last_n_results) > window:
            self.last_n_results = self.last_n_results[-window:]
        self._recalc_flaky()

    def record_fail(self, window: int = 20) -> None:
        self.fail_count += 1
        self.last_failed_at = datetime.now(timezone.utc).isoformat()
        self.last_n_results.append(False)
        if len(self.last_n_results) > window:
            self.last_n_results = self.last_n_results[-window:]
        self._recalc_flaky()

    def _recalc_flaky(self) -> None:
        if not self.last_n_results:
            self.flaky_score = 1.0
            return
        self.flaky_score = sum(self.last_n_results) / len(self.last_n_results)


class StabilityStore:
    """Container for all test stability records, serialised as JSON."""

    def __init__(self, records: dict[str, TestStabilityRecord] | None = None) -> None:
        self.records: dict[str, TestStabilityRecord] = records or {}

    def update(self, result: ExecutionResult) -> int:
        """Apply an ExecutionResult to the store. Returns number of updates."""
        updates = 0
        passed_tests = set()
        for f in result.failures:
            key = f"{f.test_file}::{f.test_name}"
            rec = self.records.setdefault(key, TestStabilityRecord())
            rec.record_fail()
            updates += 1
            passed_tests.discard(key)

        failed_keys = {f"{f.test_file}::{f.test_name}" for f in result.failures}

        return updates

    def get_flaky_tests(self, threshold: float = 0.9) -> list[str]:
        """Return test keys with a pass rate below *threshold*."""
        return [k for k, v in self.records.items() if v.flaky_score < threshold]

    def recommend_quarantine(self, threshold: float = 0.5) -> list[str]:
        """Return tests so unstable they should be quarantined."""
        return [k for k, v in self.records.items() if v.flaky_score < threshold and v.total_runs >= 5]

    def to_dict(self) -> dict:
        return {k: v.model_dump() for k, v in self.records.items()}

    @classmethod
    def from_dict(cls, data: dict) -> StabilityStore:
        records = {k: TestStabilityRecord.model_validate(v) for k, v in data.items()}
        return cls(records)


STABILITY_FILE = Path(".playspec") / "stability.json"


def load_stability(path: Path | None = None) -> StabilityStore:
    """Load stability data from disk."""
    p = path or STABILITY_FILE
    if not p.is_file():
        return StabilityStore()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return StabilityStore()
    if not data:
        return StabilityStore()
    return StabilityStore.from_dict(data)


def save_stability(store: StabilityStore, path: Path | None = None) -> None:
    """Persist stability data to disk."""
    p = path or STABILITY_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store.to_dict(), indent=2), encoding="utf-8")
