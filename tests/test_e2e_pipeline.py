"""End-to-end pipeline tests against the example-app.

These tests exercise the full production code path:
  executor.runner  →  real npx playwright test
  stability        →  pass tracking + flaky detection
  diagnostics      →  executable patch generation
  repair_agent     →  auto-apply + validate loop (mock LLM, real Playwright)
  regression.py    →  auto-quarantine + repair_policy correction

Playwright 1.56.0 + Chromium 1194 (pre-cached) must be available.
Tests are skipped automatically when the browser is absent.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from playspec.config import ExecutionProfile, RepairPolicy, load_config
from playspec.executor.runner import run_tests
from playspec.executor.diagnostics import classify_failure, generate_suggested_fix
from playspec.manifest import load_manifest
from playspec.run_id import generate_run_id
from playspec.schemas.execution_result import ExecutionResult, FailureType, TestFailure
from playspec.stability import StabilityStore, load_stability, save_stability

# ── helpers ──────────────────────────────────────────────────────────

EXAMPLE_APP = Path(__file__).parent.parent / "example-app"
BROWSER_CACHE = Path("/root/.cache/ms-playwright")
PLAYWRIGHT_ENV = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(BROWSER_CACHE)}


def _profile() -> ExecutionProfile:
    return ExecutionProfile(
        base_url="http://localhost:3000",
        browsers=["chromium"],
        parallelism=1,
        headed=False,
        repair_policy=RepairPolicy.NEVER,
    )


def _run(spec_files: list[str], tmp_path: Path, *, cwd: Path = EXAMPLE_APP) -> ExecutionResult:
    """Run test files via the PlaySpec executor inside the example-app dir."""
    env_orig = os.environ.copy()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSER_CACHE)
    prev_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        return run_tests(spec_files, _profile(), generate_run_id(), "tests/e2e")
    finally:
        os.chdir(prev_cwd)
        os.environ.clear()
        os.environ.update(env_orig)


def _pw_available() -> bool:
    try:
        subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True, check=True,
            env=PLAYWRIGHT_ENV,
            cwd=str(EXAMPLE_APP),
        )
        return BROWSER_CACHE.is_dir()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


needs_playwright = pytest.mark.skipif(
    not _pw_available(),
    reason="Playwright / Chromium not available",
)


# ── passing suite ─────────────────────────────────────────────────────

@needs_playwright
class TestPassingSuite:
    """login.spec.ts and dashboard.spec.ts should pass cleanly."""

    def test_login_spec_passes(self, tmp_path):
        spec = str(EXAMPLE_APP / "tests/e2e/login.spec.ts")
        result = _run([spec], tmp_path)
        assert result.failed == 0, f"Unexpected failures: {[f.test_name for f in result.failures]}"
        assert result.passed >= 4

    def test_dashboard_spec_passes(self, tmp_path):
        spec = str(EXAMPLE_APP / "tests/e2e/dashboard.spec.ts")
        result = _run([spec], tmp_path)
        assert result.failed == 0, f"Unexpected failures: {[f.test_name for f in result.failures]}"
        assert result.passed >= 3

    def test_passing_test_keys_populated(self, tmp_path):
        """passing_test_keys must be populated for every test that passes."""
        spec = str(EXAMPLE_APP / "tests/e2e/login.spec.ts")
        result = _run([spec], tmp_path)
        assert len(result.passing_test_keys) == result.passed
        for key in result.passing_test_keys:
            assert "::" in key, f"Bad key format: {key}"

    def test_stability_records_passes(self, tmp_path):
        """StabilityStore.update() must call record_pass for each passing test."""
        spec = str(EXAMPLE_APP / "tests/e2e/login.spec.ts")
        result = _run([spec], tmp_path)

        store = StabilityStore()
        store.update(result, run_id=result.run_id)

        for key in result.passing_test_keys:
            assert key in store.records, f"Missing stability record for: {key}"
            assert store.records[key].pass_count >= 1
            assert store.records[key].flaky_score == 1.0

    def test_no_quarantine_recommended_for_healthy_tests(self, tmp_path):
        """Healthy tests (flaky_score=1.0) must never be recommended for quarantine."""
        spec = str(EXAMPLE_APP / "tests/e2e/login.spec.ts")
        result = _run([spec], tmp_path)
        store = StabilityStore()
        store.update(result, run_id=result.run_id)
        assert store.recommend_quarantine() == []


# ── failing suite ─────────────────────────────────────────────────────

@needs_playwright
class TestFailingSuite:
    """login-broken.spec.ts contains bad selectors — must be caught and classified."""

    def test_broken_selectors_fail(self, tmp_path):
        spec = str(EXAMPLE_APP / "tests/e2e/login-broken.spec.ts")
        result = _run([spec], tmp_path)
        assert result.failed > 0

    def test_failures_carry_error_messages(self, tmp_path):
        spec = str(EXAMPLE_APP / "tests/e2e/login-broken.spec.ts")
        result = _run([spec], tmp_path)
        for f in result.failures:
            assert f.error_message, f"Empty error_message for: {f.test_name}"

    def test_failures_classified_as_selector_not_found(self, tmp_path):
        spec = str(EXAMPLE_APP / "tests/e2e/login-broken.spec.ts")
        result = _run([spec], tmp_path)
        for failure in result.failures:
            ft = classify_failure(failure)
            assert ft in (FailureType.SELECTOR_NOT_FOUND, FailureType.TIMEOUT), (
                f"Expected selector/timeout failure, got {ft} for: {failure.test_name}\n{failure.error_message}"
            )

    def test_diagnostics_generate_patches(self, tmp_path):
        spec = str(EXAMPLE_APP / "tests/e2e/login-broken.spec.ts")
        result = _run([spec], tmp_path)
        for failure in result.failures:
            failure.failure_type = classify_failure(failure)
            fix = generate_suggested_fix(failure)
            if fix:
                assert fix.proposed_patch.strip(), f"Empty patch for: {failure.test_name}"
                assert fix.confidence is not None

    def test_stability_records_failures(self, tmp_path):
        spec = str(EXAMPLE_APP / "tests/e2e/login-broken.spec.ts")
        result = _run([spec], tmp_path)
        store = StabilityStore()
        store.update(result, run_id=result.run_id)
        for f in result.failures:
            key = f"{f.test_file}::{f.test_name}"
            assert key in store.records
            assert store.records[key].fail_count >= 1
            assert store.records[key].flaky_score < 1.0


# ── mixed suite ───────────────────────────────────────────────────────

@needs_playwright
class TestMixedSuite:
    """Running both good and broken specs together validates mixed-result handling."""

    def test_mixed_results_counted_correctly(self, tmp_path):
        specs = [
            str(EXAMPLE_APP / "tests/e2e/login.spec.ts"),
            str(EXAMPLE_APP / "tests/e2e/login-broken.spec.ts"),
        ]
        result = _run(specs, tmp_path)
        assert result.passed > 0, "Expected some tests to pass"
        assert result.failed > 0, "Expected broken spec to fail"
        assert result.passed + result.failed + result.skipped == result.total_tests

    def test_passing_keys_never_overlap_with_failure_keys(self, tmp_path):
        specs = [
            str(EXAMPLE_APP / "tests/e2e/login.spec.ts"),
            str(EXAMPLE_APP / "tests/e2e/login-broken.spec.ts"),
        ]
        result = _run(specs, tmp_path)
        failure_keys = {f"{f.test_file}::{f.test_name}" for f in result.failures}
        for key in result.passing_test_keys:
            assert key not in failure_keys, f"Test appears in both passing and failing: {key}"


# ── repair agent (mock LLM, real Playwright validation) ───────────────

@needs_playwright
class TestRepairAgent:
    """repair_tests() must auto-apply a correct patch and validate it passes."""

    def test_repair_applies_valid_patch_and_confirms(self, tmp_path, monkeypatch):
        """Repair agent: mock LLM returns correct selectors → test should pass after repair."""
        from unittest.mock import MagicMock
        from playspec.agents.repair_agent import repair_tests

        # Copy broken spec inside EXAMPLE_APP so __dirname resolves HTML paths correctly
        broken_src = (EXAMPLE_APP / "tests/e2e/login-broken.spec.ts").read_text()
        broken_copy = EXAMPLE_APP / "tests/e2e/_repair_test_target.spec.ts"
        broken_copy.write_text(broken_src, encoding="utf-8")

        # Run to get failure context
        env_orig = os.environ.copy()
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSER_CACHE)
        prev_cwd = Path.cwd()
        os.chdir(EXAMPLE_APP)

        try:
            result = run_tests([str(broken_copy)], _profile(), generate_run_id(), "tests/e2e")
            assert result.failed > 0, "Setup: expected broken spec to fail"

            # The correct fix: replace broken IDs with data-testid selectors
            fixed_content = broken_src.replace(
                "page.locator('#email-input')", "page.getByTestId('email')"
            ).replace(
                "page.locator('#password-input')", "page.getByTestId('password')"
            ).replace(
                "page.locator('#login-btn')", "page.getByTestId('submit-button')"
            ).replace(
                "page.locator('#error-msg')", "page.getByTestId('error-message')"
            ).replace(
                ".toHaveText('Incorrect password.')", ".toContainText('Invalid')"
            )

            # Mock backend returns the corrected file as JSON patch
            mock_backend = MagicMock()
            mock_backend.invoke.return_value = MagicMock(
                content=json.dumps({
                    "diagnosis": "Selectors use old #id format; replaced with data-testid",
                    "patch": fixed_content,
                    "changes_made": ["Updated all locators to use getByTestId"],
                })
            )

            from playspec.config import load_config as _lc
            mock_config = MagicMock()
            mock_config.test_dir = "tests/e2e"

            repaired = repair_tests(
                result=result,
                backend=mock_backend,
                config=mock_config,
                profile=_profile(),
                max_retries=2,
                run_id=generate_run_id(),
            )

            assert repaired > 0, "Expected at least one test to be repaired"
            # After repair the file should contain fixed selectors
            patched = broken_copy.read_text()
            assert "getByTestId" in patched

        finally:
            broken_copy.unlink(missing_ok=True)
            os.chdir(prev_cwd)
            os.environ.clear()
            os.environ.update(env_orig)

    def test_repair_restores_original_when_all_attempts_fail(self, tmp_path, monkeypatch):
        """When the LLM returns a nonsense patch, the original file must be restored."""
        from unittest.mock import MagicMock
        from playspec.agents.repair_agent import repair_tests

        broken_src = (EXAMPLE_APP / "tests/e2e/login-broken.spec.ts").read_text()
        broken_copy = EXAMPLE_APP / "tests/e2e/_stubborn_test_target.spec.ts"
        broken_copy.write_text(broken_src, encoding="utf-8")

        env_orig = os.environ.copy()
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSER_CACHE)
        prev_cwd = Path.cwd()
        os.chdir(EXAMPLE_APP)

        try:
            result = run_tests([str(broken_copy)], _profile(), generate_run_id(), "tests/e2e")
            assert result.failed > 0

            # Mock backend returns a "fix" that is still broken (uses different wrong selectors)
            still_broken = broken_src.replace("#email-input", "#old-email").replace(
                "#login-btn", "#old-btn"
            )
            mock_backend = MagicMock()
            mock_backend.invoke.return_value = MagicMock(
                content=json.dumps({
                    "diagnosis": "updated selectors",
                    "patch": still_broken,
                    "changes_made": [],
                })
            )

            mock_config = MagicMock()
            mock_config.test_dir = "tests/e2e"

            repaired = repair_tests(
                result=result,
                backend=mock_backend,
                config=mock_config,
                profile=_profile(),
                max_retries=2,
                run_id=generate_run_id(),
            )

            assert repaired == 0, "No tests should be repaired when patch is still broken"
            # Original must be restored
            assert broken_copy.read_text() == broken_src

        finally:
            broken_copy.unlink(missing_ok=True)
            os.chdir(prev_cwd)
            os.environ.clear()
            os.environ.update(env_orig)


# ── diagnostics ───────────────────────────────────────────────────────

class TestDiagnostics:
    """Unit-level checks for diagnostics patch generation (no Playwright needed)."""

    def test_selector_patch_extracts_broken_selector(self):
        f = TestFailure(
            test_file="login.spec.ts",
            test_name="logs in",
            failure_type=FailureType.SELECTOR_NOT_FOUND,
            error_message="waiting for locator('#email-input')",
        )
        fix = generate_suggested_fix(f)
        assert fix is not None
        assert "#email-input" in fix.proposed_patch
        assert "getByTestId" in fix.proposed_patch or "data-testid" in fix.proposed_patch

    def test_timeout_fix_is_auto_applicable(self):
        f = TestFailure(
            test_file="login.spec.ts",
            test_name="navigates",
            failure_type=FailureType.TIMEOUT,
            error_message="page.goto timed out after 10000ms",
        )
        fix = generate_suggested_fix(f)
        assert fix is not None
        assert fix.is_auto_applicable is True
        assert "waitForLoadState" in fix.proposed_patch

    def test_selector_fix_not_auto_applicable(self):
        f = TestFailure(
            test_file="login.spec.ts",
            test_name="logs in",
            failure_type=FailureType.SELECTOR_NOT_FOUND,
            error_message="waiting for locator('#old-id')",
        )
        fix = generate_suggested_fix(f)
        assert fix is not None
        assert fix.is_auto_applicable is False

    def test_assertion_mismatch_includes_expected_received(self):
        f = TestFailure(
            test_file="login.spec.ts",
            test_name="checks text",
            failure_type=FailureType.ASSERTION_MISMATCH,
            error_message=(
                "expect(received).toHaveText(expected)\n"
                "Expected: 'Sign in'\nReceived: 'Log in'"
            ),
        )
        fix = generate_suggested_fix(f)
        assert fix is not None
        assert "Sign in" in fix.proposed_patch
        assert "Log in" in fix.proposed_patch


# ── regression pipeline features ─────────────────────────────────────

class TestRegressionPipelineFeatures:
    """Verify regression.py behaviour (auto-correction, auto-quarantine) with mocked runner."""

    def test_repair_policy_auto_corrects(self, tmp_path, monkeypatch):
        """regression.py must auto-correct repair_policy instead of crashing."""
        from unittest.mock import patch as mpatch, MagicMock
        import playspec.regression as reg

        ps_dir = tmp_path / ".playspec"
        ps_dir.mkdir()
        (ps_dir / "config.yaml").write_text(
            yaml.dump({
                "test_dir": "tests/e2e",
                "profiles": {
                    "local-dev": {"repair_policy": "propose", "browsers": ["chromium"]},
                },
            })
        )
        (ps_dir / "regression-manifest.yaml").write_text(
            yaml.dump({"suites": {"smoke": {"tags": ["smoke"], "blocking": False}}})
        )
        monkeypatch.chdir(tmp_path)

        empty_result = ExecutionResult(run_id="test", total_tests=0)

        with mpatch.object(reg, "load_stability", return_value=MagicMock(
            update=lambda *a, **kw: 0,
            recommend_quarantine=lambda: [],
        )), mpatch.object(reg, "save_stability"), \
             mpatch.object(reg, "run_tests", return_value=empty_result), \
             mpatch.object(reg, "save_audit"), mpatch.object(reg, "create_audit", return_value=MagicMock()):
            # Should NOT raise — must auto-correct instead
            try:
                reg.run_regression(suite_names=["smoke"], profile_name="local-dev")
            except SystemExit as e:
                if e.code != 0:
                    raise

    def test_auto_quarantine_writes_manifest(self, tmp_path, monkeypatch):
        """Tests below quarantine threshold should be written to manifest automatically."""
        from playspec.stability import StabilityStore, TestStabilityRecord

        ps_dir = tmp_path / ".playspec"
        ps_dir.mkdir()
        manifest_path = ps_dir / "regression-manifest.yaml"
        manifest_path.write_text(
            yaml.dump({
                "suites": {},
                "quarantine": [],
            })
        )
        monkeypatch.chdir(tmp_path)

        store = StabilityStore()
        # Simulate a test that has been consistently flaky: 3 fails, 2 passes → score 0.4
        rec = TestStabilityRecord()
        for _ in range(3):
            rec.record_fail()
        for i in range(2):
            rec.record_pass(f"run-{i}")
        store.records["tests/e2e/flaky.spec.ts::broken animation"] = rec

        candidates = store.recommend_quarantine(threshold=0.5)
        assert len(candidates) == 1

        # Simulate what regression.py does
        from playspec.manifest import load_manifest
        manifest = load_manifest(manifest_path)
        new_quarantined = [q for q in candidates if q not in manifest.get_quarantined()]
        for key in new_quarantined:
            manifest.raw.quarantine.append(key)
        manifest_path.write_text(
            yaml.safe_dump(manifest.raw.model_dump(), default_flow_style=False),
            encoding="utf-8",
        )

        reloaded = load_manifest(manifest_path)
        assert "tests/e2e/flaky.spec.ts::broken animation" in reloaded.get_quarantined()

    def test_generator_retry_on_parse_failure(self, tmp_path):
        """Generator must retry and raise RuntimeError when LLM always returns invalid JSON."""
        from unittest.mock import MagicMock
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from playspec.agents.generator_agent import generate_tests
        from playspec.schemas.test_plan import TestPlan

        mock_backend = MagicMock()
        # All 3 attempts return invalid JSON
        mock_backend.invoke.return_value = MagicMock(content="not json at all {{{ broken")

        mock_config = MagicMock()
        mock_config.test_dir = str(tmp_path / "tests/e2e")
        mock_config.naming_convention = "kebab-case"

        mock_plan = MagicMock(spec=TestPlan)
        mock_plan.model_dump_json.return_value = "{}"

        with pytest.raises(RuntimeError, match="3 attempts"):
            generate_tests(
                plan=mock_plan,
                backend=mock_backend,
                config=mock_config,
                output_dir=tmp_path / "out",
            )

        assert mock_backend.invoke.call_count == 3

    def test_generator_succeeds_on_second_attempt(self, tmp_path):
        """Generator must succeed if the second attempt returns valid JSON."""
        from unittest.mock import MagicMock, call
        from playspec.agents.generator_agent import generate_tests
        from playspec.schemas.test_plan import TestPlan

        valid_json = json.dumps({"login.spec.ts": "// generated\nimport { test } from '@playwright/test';\n"})

        mock_backend = MagicMock()
        mock_backend.invoke.side_effect = [
            MagicMock(content="bad json >>>"),  # first attempt fails
            MagicMock(content=valid_json),       # second succeeds
        ]

        mock_config = MagicMock()
        mock_config.test_dir = str(tmp_path / "tests/e2e")
        mock_config.naming_convention = "kebab-case"

        mock_plan = MagicMock(spec=TestPlan)
        mock_plan.model_dump_json.return_value = "{}"

        out_dir = tmp_path / "out"
        files = generate_tests(plan=mock_plan, backend=mock_backend, config=mock_config, output_dir=out_dir)

        assert len(files) == 1
        assert "login.spec.ts" in files[0]
        assert mock_backend.invoke.call_count == 2
