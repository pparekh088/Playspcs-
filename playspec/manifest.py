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
        import_patterns = []
        for f in changed_files:
            stem = Path(f).stem
            import_patterns.append(re.compile(
                rf"""(?:import|from|require)\s*[\(\s]['"]\S*{re.escape(stem)}['"]"""
            ))
        for tf in test_root.rglob("*.spec.ts"):
            try:
                content = tf.read_text(encoding="utf-8")
            except OSError:
                continue
            for pattern in import_patterns:
                if pattern.search(content):
                    test_files.append(str(tf))
                    break
        return test_files

    def resolve_jira_tag(self, jira_key: str, test_dir: str) -> list[str]:
        """Return test files annotated with @jira:<key>."""
        return _find_tests_by_jira(jira_key, test_dir)

    def get_quarantined(self) -> set[str]:
        """Return the set of quarantined test file paths."""
        return self._data.quarantine_paths()

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
JIRA_PATTERN = re.compile(r"//\s*@jira:\s*(.+)", re.IGNORECASE)
OWNER_PATTERN = re.compile(r"//\s*@owner:\s*(.+)", re.IGNORECASE)
DESCRIBE_JIRA_PATTERN = re.compile(r"""test\.describe\(\s*['"]([A-Z]+-\d+):""")


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


def parse_jira_keys(file_path: str | Path) -> list[str]:
    """Extract all @jira: keys from a test file header (comma-separated supported).

    Also discovers Jira keys from ``test.describe('PLAY-7: ...')`` blocks
    throughout the entire file.
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return []

    keys: list[str] = []
    # Header annotations (first 20 lines)
    for line in content.splitlines()[:20]:
        m = JIRA_PATTERN.match(line.strip())
        if m:
            raw = m.group(1)
            for part in raw.split(","):
                part = part.strip()
                if part:
                    keys.append(part)

    # Describe-block annotations (whole file)
    for m in DESCRIBE_JIRA_PATTERN.finditer(content):
        key = m.group(1).strip()
        if key.upper() not in {k.upper() for k in keys}:
            keys.append(key)

    return keys


def parse_jira_key(file_path: str | Path) -> str | None:
    """Extract the first @jira: annotation from a test file header.

    Backward-compatible wrapper around :func:`parse_jira_keys`.
    """
    keys = parse_jira_keys(file_path)
    return keys[0] if keys else None


def parse_describe_jira_keys(file_path: str | Path) -> dict[str, list[str]]:
    """Map ``test.describe`` block names to the Jira keys found in their titles.

    Returns:
        ``{ "PLAY-7: User Logout": ["PLAY-7"], ... }``
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return {}

    describe_re = re.compile(r"""test\.describe\(\s*['"]((?:[A-Z]+-\d+(?:,\s*)?)+:?\s*[^'"]*?)['"]""")
    jira_key_re = re.compile(r"[A-Z]+-\d+")

    result: dict[str, list[str]] = {}
    for m in describe_re.finditer(content):
        title = m.group(1).strip()
        found = jira_key_re.findall(title)
        if found:
            result[title] = found
    return result


def parse_test_to_jira_map(file_path: str | Path) -> dict[str, list[str]]:
    """Map individual test names to their Jira keys based on describe block context.

    Returns:
        ``{ "should display the login form": ["PLAY-1"], ... }``
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return {}

    file_keys = parse_jira_keys(file_path)
    jira_key_re = re.compile(r"[A-Z]+-\d+")

    # Track describe blocks with brace-depth so we know when they close
    result: dict[str, list[str]] = {}
    # Stack entries: (keys, open_depth) where open_depth is the brace depth
    # at the point the describe block's opening brace was counted.
    describe_stack: list[tuple[list[str], int]] = []
    brace_depth = 0

    for line in content.splitlines():
        stripped = line.strip()

        # Detect describe block open (before counting braces on this line)
        describe_match = re.match(r"""test\.describe\(\s*['"](.+?)['"]""", stripped)
        test_match = re.match(r"""test\(\s*['"](.+?)['"]""", stripped) if not describe_match else None

        if test_match:
            test_name = test_match.group(1)
            # Use innermost describe keys, fallback to file keys
            for frame_keys, _ in reversed(describe_stack):
                if frame_keys:
                    result[test_name] = frame_keys
                    break
            else:
                result[test_name] = list(file_keys)

        # Count braces on this line
        opens = line.count("{")
        closes = line.count("}")

        if describe_match:
            title = describe_match.group(1)
            keys = jira_key_re.findall(title)
            # The describe block's opening brace is on this line
            # After this line, brace_depth will be at the depth inside the describe
            describe_stack.append((keys, brace_depth + opens))

        brace_depth += opens - closes

        # Check if any describe blocks have closed
        while describe_stack and brace_depth < describe_stack[-1][1]:
            describe_stack.pop()

    return result


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
    """Find all .spec.ts files that reference a specific JIRA key.

    Checks both header ``@jira:`` annotations and ``test.describe`` block titles.
    """
    root = Path(test_dir)
    if not root.is_dir():
        return []
    target = jira_key.upper()
    matches: list[str] = []
    for tf in sorted(root.rglob("*.spec.ts")):
        keys = parse_jira_keys(tf)
        if any(k.upper() == target for k in keys):
            matches.append(str(tf))
    return matches
