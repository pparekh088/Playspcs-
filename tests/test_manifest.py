"""Tests for manifest loading, suite resolution, and tag parsing."""

import pytest
import yaml
from pathlib import Path

from playspec.manifest import (
    Manifest,
    load_manifest,
    parse_test_tags,
    parse_jira_key,
    parse_owner,
)
from playspec.schemas.manifest_schema import RegressionManifest, SuiteConfig, SuiteHooks


@pytest.fixture
def test_project(tmp_path):
    """Create a project with manifest and tagged test files."""
    ps = tmp_path / ".playspec"
    ps.mkdir()

    manifest = {
        "suites": {
            "smoke": {
                "description": "Quick check",
                "timeout_minutes": 10,
                "tags": ["smoke", "p0"],
                "blocking": True,
                "browsers": ["chromium"],
                "parallelism": 4,
            },
            "full": {
                "description": "All tests",
                "timeout_minutes": 60,
                "tags": ["regression"],
                "blocking": False,
            },
        },
        "quarantine": ["tests/e2e/flaky.spec.ts"],
        "hooks": {
            "smoke": {
                "setup": "echo setup",
                "teardown": "echo teardown",
            }
        },
    }
    (ps / "regression-manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")

    e2e = tmp_path / "tests" / "e2e"
    e2e.mkdir(parents=True)

    (e2e / "login.spec.ts").write_text(
        "// @tags: smoke, p0, regression, auth\n"
        "// @jira: PROJ-1234\n"
        "// @owner: team-auth\n"
        "import { test } from '@playwright/test';\n"
        "test('logs in', async ({ page }) => {});\n"
    )
    (e2e / "checkout.spec.ts").write_text(
        "// @tags: regression, p1\n"
        "// @jira: PROJ-5678\n"
        "import { test } from '@playwright/test';\n"
    )
    (e2e / "flaky.spec.ts").write_text(
        "// @tags: smoke\n"
        "import { test } from '@playwright/test';\n"
    )

    return tmp_path


class TestTagParsing:
    def test_parse_tags(self, test_project):
        tags = parse_test_tags(test_project / "tests/e2e/login.spec.ts")
        assert "smoke" in tags
        assert "p0" in tags
        assert "auth" in tags
        assert "regression" in tags

    def test_parse_jira(self, test_project):
        key = parse_jira_key(test_project / "tests/e2e/login.spec.ts")
        assert key == "PROJ-1234"

    def test_parse_owner(self, test_project):
        owner = parse_owner(test_project / "tests/e2e/login.spec.ts")
        assert owner == "team-auth"

    def test_parse_missing_file(self):
        tags = parse_test_tags("/nonexistent/file.spec.ts")
        assert tags == set()

    def test_parse_no_jira(self, test_project):
        key = parse_jira_key(test_project / "tests/e2e/flaky.spec.ts")
        assert key is None


class TestManifestLoading:
    def test_load_valid(self, test_project, monkeypatch):
        monkeypatch.chdir(test_project)
        m = load_manifest()
        assert "smoke" in m.suites
        assert m.is_blocking("smoke") is True
        assert m.is_blocking("full") is False

    def test_load_explicit_path(self, test_project):
        path = test_project / ".playspec" / "regression-manifest.yaml"
        m = load_manifest(path)
        assert "smoke" in m.suites

    def test_load_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="playspec init"):
            load_manifest(tmp_path / "missing.yaml")


class TestSuiteResolution:
    def test_resolve_smoke(self, test_project, monkeypatch):
        monkeypatch.chdir(test_project)
        m = load_manifest()
        files = m.resolve_suite("smoke", "tests/e2e")
        names = [Path(f).name for f in files]
        assert "login.spec.ts" in names
        assert "flaky.spec.ts" in names

    def test_resolve_regression(self, test_project, monkeypatch):
        monkeypatch.chdir(test_project)
        m = load_manifest()
        files = m.resolve_suite("full", "tests/e2e")
        names = [Path(f).name for f in files]
        assert "login.spec.ts" in names
        assert "checkout.spec.ts" in names

    def test_resolve_unknown_suite(self, test_project, monkeypatch):
        monkeypatch.chdir(test_project)
        m = load_manifest()
        files = m.resolve_suite("nonexistent", "tests/e2e")
        assert files == []

    def test_resolve_jira(self, test_project, monkeypatch):
        monkeypatch.chdir(test_project)
        m = load_manifest()
        files = m.resolve_jira_tag("PROJ-1234", "tests/e2e")
        assert len(files) == 1
        assert "login.spec.ts" in files[0]

    def test_quarantined(self, test_project, monkeypatch):
        monkeypatch.chdir(test_project)
        m = load_manifest()
        q = m.get_quarantined()
        assert "tests/e2e/flaky.spec.ts" in q

    def test_hooks(self, test_project, monkeypatch):
        monkeypatch.chdir(test_project)
        m = load_manifest()
        assert m.get_hook("smoke", "setup") == "echo setup"
        assert m.get_hook("smoke", "teardown") == "echo teardown"
        assert m.get_hook("full", "setup") is None
