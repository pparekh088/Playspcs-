"""Regression manifest loader and suite resolver."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from playspec.console import console
from playspec.schemas.manifest_schema import RegressionManifest, SuiteConfig, SuiteHooks


class Manifest:
    """In-memory representation of the regression manifest with resolution helpers."""

    def __init__(self, data: RegressionManifest, path: Path | None = None) -> None:
        self._data = data
        self._path = path

    @property
    def raw(self) -> RegressionManifest:
        return self._data

    @property
    def path(self) -> Path | None:
        return self._path

    def resolve_suite(self, suite_name: str, test_dir: str) -> list[str]:
        """Return test file paths whose tags match the suite's tag set."""
        suite = self._data.suites.get(suite_name)
        if suite is None:
            console.print(f"[yellow]Warning: suite '{suite_name}' not found in manifest.[/yellow]")
            return []
        return _find_tests_by_tags(suite.tags, test_dir)

    def resolve_tags(self, tags: list[str], test_dir: str) -> list[str]:
        """Return test files matching ANY of the provided tags."""
        return _find_tests_by_tags(tags, test_dir)

    def resolve_changed_files(self, changed_files: list[str], test_dir: str) -> list[str]:
        """Return test files that import or reference any changed source file."""
        test_root = Path(test_dir)
        if not test_root.is_dir():
            return []
        test_files: list[str] = []
        changed_basenames = {Path(f).stem for f in changed_files}
        for tf in test_root.rglob("*.spec.ts"):
            try:
                content = tf.read_text(encoding="utf-8")
            except OSError:
                continue
            for basename in changed_basenames:
                if basename in content:
                    test_files.append(str(tf))
                    break
        return test_files

    def resolve_jira_tag(self, jira_key: str, test_dir: str) -> list[str]:
        """Return test files annotated with @jira:<key>."""
        return _find_tests_by_jira(jira_key, test_dir)

    def get_quarantined(self) -> set[str]:
        """Return the set of quarantined test file paths."""
        return set(self._data.quarantine)

    def is_blocking(self, suite_name: str) -> bool:
        """Whether failures in this suite should cause a non-zero exit."""
        suite = self._data.suites.get(suite_name)
        if suite is None:
            return False
        return suite.blocking

    def get_hook(self, suite_name: str, phase: str) -> str | None:
        """Return the setup or teardown hook script for a suite, if any."""
        hooks = self._data.hooks.get(suite_name)
        if hooks is None:
            suite = self._data.suites.get(suite_name)
            if suite and suite.hooks:
                hooks = suite.hooks
        if hooks is None:
            return None
        return hooks.setup if phase == "setup" else hooks.teardown

    def get_suite(self, name: str) -> SuiteConfig | None:
        return self._data.suites.get(name)

    @property
    def suites(self) -> dict[str, SuiteConfig]:
        return self._data.suites


MANIFEST_FILENAME = "regression-manifest.yaml"


def load_manifest(path: Path | None = None) -> Manifest:
    """Load and validate the regression manifest.

    Args:
        path: Explicit manifest path; otherwise discovered in .playspec/.

    Raises:
        FileNotFoundError: When the manifest cannot be located.
        ValueError: When the YAML fails schema validation.
    """
    if path is None:
        path = _find_manifest()
    if path is None or not path.is_file():
        raise FileNotFoundError(
            "No regression manifest found. Run 'playspec init' to create one."
        )

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    try:
        data = RegressionManifest.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"Invalid manifest in {path}: {exc}") from exc

    return Manifest(data, path)


def _find_manifest() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".playspec" / MANIFEST_FILENAME
        if candidate.is_file():
            return candidate
    return None


# ── Tag scanning helpers ────────────────────────────────────────────

TAG_PATTERN = re.compile(r"//\s*@tags?:\s*(.+)", re.IGNORECASE)
JIRA_PATTERN = re.compile(r"//\s*@jira:\s*(\S+)", re.IGNORECASE)
OWNER_PATTERN = re.compile(r"//\s*@owner:\s*(.+)", re.IGNORECASE)


def parse_test_tags(file_path: str | Path) -> set[str]:
    """Extract tag annotations from the header of a Playwright test file."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return set()

    tags: set[str] = set()
    for line in content.splitlines()[:20]:
        m = TAG_PATTERN.match(line.strip())
        if m:
            raw = m.group(1)
            tags.update(t.strip().lower() for t in raw.split(",") if t.strip())
    return tags


def parse_jira_key(file_path: str | Path) -> str | None:
    """Extract the @jira: annotation from a test file header."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return None
    for line in content.splitlines()[:20]:
        m = JIRA_PATTERN.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def parse_owner(file_path: str | Path) -> str | None:
    """Extract the @owner: annotation from a test file header."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return None
    for line in content.splitlines()[:20]:
        m = OWNER_PATTERN.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def _find_tests_by_tags(tags: list[str], test_dir: str) -> list[str]:
    """Find all .spec.ts files under test_dir whose tags overlap with the given list."""
    root = Path(test_dir)
    if not root.is_dir():
        return []
    tag_set = {t.lower() for t in tags}
    matches: list[str] = []
    for tf in sorted(root.rglob("*.spec.ts")):
        file_tags = parse_test_tags(tf)
        if file_tags & tag_set:
            matches.append(str(tf))
    return matches


def _find_tests_by_jira(jira_key: str, test_dir: str) -> list[str]:
    """Find all .spec.ts files tagged with a specific JIRA key."""
    root = Path(test_dir)
    if not root.is_dir():
        return []
    matches: list[str] = []
    for tf in sorted(root.rglob("*.spec.ts")):
        key = parse_jira_key(tf)
        if key and key.upper() == jira_key.upper():
            matches.append(str(tf))
    return matches
