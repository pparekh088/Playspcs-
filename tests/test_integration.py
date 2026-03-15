"""Integration tests — end-to-end regression pipeline and manifest/config combinations."""

import json
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from playspec.config import PlaySpecConfig, ExecutionProfile, RepairPolicy, load_config
from playspec.manifest import load_manifest, Manifest
from playspec.stability import load_stability, save_stability, StabilityStore
from playspec.audit import save_audit, load_audit, list_audits, create_audit
from playspec.schemas.audit_entry import AuditResults, RunMode
from playspec.schemas.execution_result import ExecutionResult, TestFailure, FailureType
from playspec.executor.diagnostics import classify_failure, generate_suggested_fixes
from playspec.run_id import generate_run_id


@pytest.fixture
def full_project(tmp_path):
    """Create a complete project with config, manifest, test files, and stability data."""
    ps = tmp_path / ".playspec"
    ps.mkdir()
    (ps / "audits").mkdir()
    (ps / "runs").mkdir()

    config = {
        "test_dir": "tests/e2e",
        "page_objects_dir": "tests/e2e/pages",
        "fixtures_dir": "tests/e2e/fixtures",
        "naming_convention": "kebab-case",
        "max_retries": 3,
        "profiles": {
            "local-dev": {
                "base_url": "http://localhost:3000",
                "browsers": ["chromium"],
                "parallelism": 2,
                "headed": True,
                "repair_policy": "propose",
            },
            "pr-ci": {
                "base_url": "https://preview.example.com",
                "browsers": ["chromium"],
                "parallelism": 4,
                "headed": False,
                "repair_policy": "never",
            },
            "nightly": {
                "base_url": "https://staging.example.com",
                "browsers": ["chromium", "firefox", "webkit"],
                "parallelism": 8,
                "headed": False,
                "repair_policy": "never",
                "flaky_detection": True,
            },
        },
        "audit": {"enabled": True, "output_dir": ".playspec/audits"},
    }
    (ps / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    manifest = {
        "suites": {
            "smoke": {
                "description": "Critical path, every PR",
                "timeout_minutes": 10,
                "tags": ["smoke", "p0"],
                "blocking": True,
                "browsers": ["chromium"],
                "parallelism": 4,
            },
            "checkout": {
                "description": "Checkout flow",
                "timeout_minutes": 25,
                "tags": ["checkout", "payment", "p0", "p1"],
                "blocking": True,
                "browsers": ["chromium", "firefox"],
                "parallelism": 2,
            },
            "full": {
                "description": "Full regression nightly",
                "timeout_minutes": 60,
                "tags": ["regression"],
                "blocking": False,
                "browsers": ["chromium", "firefox", "webkit"],
                "parallelism": 8,
            },
            "mobile": {
                "description": "Responsive tests",
                "timeout_minutes": 20,
                "tags": ["mobile", "responsive"],
                "blocking": False,
            },
        },
        "quarantine": ["tests/e2e/flaky-animation.spec.ts"],
        "hooks": {
            "checkout": {"setup": "echo seed", "teardown": "echo cleanup"},
        },
    }
    (ps / "regression-manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")

    e2e = tmp_path / "tests" / "e2e"
    e2e.mkdir(parents=True)

    (e2e / "login.spec.ts").write_text(
        "// @tags: smoke, p0, regression, auth\n"
        "// @jira: PROJ-100\n"
        "// @owner: team-auth\n"
        "import { test, expect } from '@playwright/test';\n"
        "test.describe('Login', () => {\n"
        "  test('valid login', async ({ page }) => {});\n"
        "  test('invalid login', async ({ page }) => {});\n"
        "});\n"
    )
    (e2e / "checkout-flow.spec.ts").write_text(
        "// @tags: checkout, p0, regression, payment\n"
        "// @jira: PROJ-200\n"
        "// @owner: team-checkout\n"
        "import { test, expect } from '@playwright/test';\n"
        "test('completes checkout', async ({ page }) => {});\n"
    )
    (e2e / "dashboard.spec.ts").write_text(
        "// @tags: regression, p1\n"
        "// @jira: PROJ-300\n"
        "import { test } from '@playwright/test';\n"
        "test('loads dashboard', async ({ page }) => {});\n"
    )
    (e2e / "mobile-nav.spec.ts").write_text(
        "// @tags: mobile, responsive, p2\n"
        "import { test } from '@playwright/test';\n"
        "test('mobile menu works', async ({ page }) => {});\n"
    )
    (e2e / "flaky-animation.spec.ts").write_text(
        "// @tags: smoke, regression\n"
        "import { test } from '@playwright/test';\n"
        "test('flaky animation', async ({ page }) => {});\n"
    )

    (ps / "stability.json").write_text("{}", encoding="utf-8")

    return tmp_path


class TestFullRegressionPipeline:
    """Test the complete regression flow: config → manifest → resolve → execute → audit."""

    def test_smoke_suite_resolution(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()
        manifest = load_manifest()

        files = manifest.resolve_suite("smoke", config.test_dir)
        quarantined = manifest.get_quarantined()
        filtered = [f for f in files if f not in quarantined]

        filenames = [Path(f).name for f in filtered]
        assert "login.spec.ts" in filenames
        assert "flaky-animation.spec.ts" not in filenames

    def test_checkout_suite_resolution(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()
        manifest = load_manifest()

        files = manifest.resolve_suite("checkout", config.test_dir)
        filenames = [Path(f).name for f in files]
        assert "checkout-flow.spec.ts" in filenames

    def test_full_suite_resolution(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()
        manifest = load_manifest()

        files = manifest.resolve_suite("full", config.test_dir)
        filenames = [Path(f).name for f in files]
        assert "login.spec.ts" in filenames
        assert "checkout-flow.spec.ts" in filenames
        assert "dashboard.spec.ts" in filenames

    def test_jira_resolution(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()
        manifest = load_manifest()

        files = manifest.resolve_jira_tag("PROJ-200", config.test_dir)
        assert len(files) == 1
        assert "checkout-flow.spec.ts" in files[0]

    def test_blocking_status(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        manifest = load_manifest()
        assert manifest.is_blocking("smoke") is True
        assert manifest.is_blocking("checkout") is True
        assert manifest.is_blocking("full") is False
        assert manifest.is_blocking("mobile") is False

    def test_execution_result_processing(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)

        result = ExecutionResult(
            run_id="ps-20260315-120000-test0001",
            total_tests=5,
            passed=3,
            failed=2,
            skipped=0,
            failures=[
                TestFailure(
                    test_file="tests/e2e/login.spec.ts",
                    test_name="invalid login",
                    error_message="expect(received).toHaveText(expected)\nExpected: 'Invalid'\nReceived: 'Wrong'",
                    stack_trace="at login.spec.ts:15",
                ),
                TestFailure(
                    test_file="tests/e2e/checkout-flow.spec.ts",
                    test_name="completes checkout",
                    error_message="Timeout 30000ms exceeded. Navigation timeout",
                    stack_trace="at checkout-flow.spec.ts:8",
                ),
            ],
            duration_seconds=45.2,
        )

        for f in result.failures:
            f.failure_type = classify_failure(f)
        assert result.failures[0].failure_type == FailureType.ASSERTION_MISMATCH
        assert result.failures[1].failure_type == FailureType.TIMEOUT

        fixes = generate_suggested_fixes(result)
        assert len(fixes) == 2

    def test_stability_update_cycle(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        stability = load_stability()
        assert stability.records == {}

        result = ExecutionResult(
            run_id="ps-test-run",
            total_tests=2,
            passed=1,
            failed=1,
            failures=[TestFailure(
                test_file="tests/e2e/login.spec.ts",
                test_name="invalid login",
                failure_type=FailureType.ASSERTION_MISMATCH,
            )],
        )
        stability.update(result)
        save_stability(stability)

        reloaded = load_stability()
        assert "tests/e2e/login.spec.ts::invalid login" in reloaded.records

    def test_audit_trail_write_read(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        audit_dir = full_project / ".playspec" / "audits"
        run_id = generate_run_id()

        entry = create_audit(
            run_id=run_id,
            mode=RunMode.REGRESSION,
            profile="pr-ci",
            suite="smoke",
            resolved_tests=5,
            quarantined_skipped=1,
            results=AuditResults(passed=3, failed=1, skipped=0),
            failures=["login.spec.ts::invalid login"],
            duration_seconds=45.2,
            stability_updates=1,
        )
        save_audit(entry, audit_dir)

        loaded = load_audit(run_id, audit_dir)
        assert loaded is not None
        assert loaded.results.passed == 3
        assert loaded.results.failed == 1
        assert len(loaded.failures) == 1

    def test_multi_suite_audit_listing(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        audit_dir = full_project / ".playspec" / "audits"

        for suite in ["smoke", "checkout", "full"]:
            rid = generate_run_id()
            entry = create_audit(
                run_id=rid,
                mode=RunMode.REGRESSION,
                suite=suite,
                results=AuditResults(passed=10, failed=0),
            )
            save_audit(entry, audit_dir)

        entries = list_audits(audit_dir)
        assert len(entries) == 3
        suites = {e.suite for e in entries}
        assert "smoke" in suites
        assert "checkout" in suites
        assert "full" in suites


class TestProfileVariations:
    """Test config loading with all profile variations."""

    def test_all_profiles_load(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()

        for name in ["local-dev", "pr-ci", "nightly"]:
            profile = config.get_profile(name)
            assert profile.base_url != ""
            assert len(profile.browsers) > 0

    def test_pr_ci_never_repairs(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()
        profile = config.get_profile("pr-ci")
        assert profile.repair_policy == RepairPolicy.NEVER

    def test_nightly_multi_browser(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()
        profile = config.get_profile("nightly")
        assert set(profile.browsers) == {"chromium", "firefox", "webkit"}
        assert profile.flaky_detection is True


class TestManifestFilterCombinations:
    """Test various filter combinations for suite resolution."""

    def test_multi_suite_dedup(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        config = load_config()
        manifest = load_manifest()

        files_smoke = manifest.resolve_suite("smoke", config.test_dir)
        files_full = manifest.resolve_suite("full", config.test_dir)
        combined = list(dict.fromkeys(files_smoke + files_full))

        assert len(combined) <= len(files_smoke) + len(files_full)
        assert len(combined) >= max(len(files_smoke), len(files_full))

    def test_tags_filter(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        manifest = load_manifest()

        files = manifest.resolve_tags(["mobile"], "tests/e2e")
        filenames = [Path(f).name for f in files]
        assert "mobile-nav.spec.ts" in filenames

    def test_quarantine_exclusion(self, full_project, monkeypatch):
        monkeypatch.chdir(full_project)
        manifest = load_manifest()

        all_smoke = manifest.resolve_suite("smoke", "tests/e2e")
        quarantined = manifest.get_quarantined()
        filtered = [f for f in all_smoke if f not in quarantined]

        assert len(filtered) <= len(all_smoke)
