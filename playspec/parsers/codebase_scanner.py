"""Codebase scanner — detect conventions from existing test files."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from playspec.config import PlaySpecConfig


class CodebaseConventions(BaseModel):
    """Detected conventions from an existing Playwright test suite."""

    page_objects: list[str] = Field(default_factory=list)
    fixture_style: str | None = None
    selector_strategy: str | None = None
    assertion_style: str | None = None
    file_naming: str | None = None


def scan_conventions(config: PlaySpecConfig) -> CodebaseConventions:
    """Scan the configured test directory for conventions.

    Args:
        config: PlaySpec config with test_dir and page_objects_dir.

    Returns:
        Detected CodebaseConventions.
    """
    conv = CodebaseConventions()

    po_dir = Path(config.page_objects_dir)
    if po_dir.is_dir():
        conv.page_objects = [f.stem for f in po_dir.glob("*.ts")]

    test_dir = Path(config.test_dir)
    if not test_dir.is_dir():
        return conv

    test_files = list(test_dir.rglob("*.spec.ts"))
    if not test_files:
        return conv

    conv.file_naming = _detect_naming(test_files)
    conv.selector_strategy = _detect_selector_strategy(test_files)
    conv.assertion_style = _detect_assertion_style(test_files)
    conv.fixture_style = _detect_fixture_style(test_files, config)

    return conv


def _detect_naming(files: list[Path]) -> str:
    """Detect file naming convention from file names."""
    names = [f.stem.replace(".spec", "") for f in files]
    if not names:
        return "kebab-case"
    if all("-" in n for n in names if len(n) > 5):
        return "kebab-case"
    if all("_" in n for n in names if len(n) > 5):
        return "snake_case"
    if any(n[0].isupper() for n in names):
        return "PascalCase"
    return "camelCase"


def _detect_selector_strategy(files: list[Path]) -> str:
    """Detect the primary selector strategy used in tests."""
    counts = {"data-testid": 0, "role": 0, "aria-label": 0, "css": 0}
    for f in files[:10]:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        counts["data-testid"] += content.count("data-testid")
        counts["role"] += content.count("getByRole")
        counts["aria-label"] += content.count("aria-label")
        counts["css"] += len(re.findall(r"page\.locator\(['\"](?!data-testid)", content))

    if not any(counts.values()):
        return "data-testid"
    return max(counts, key=lambda k: counts[k])


def _detect_assertion_style(files: list[Path]) -> str:
    """Detect the primary assertion style."""
    for f in files[:5]:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if "expect(" in content:
            return "expect"
    return "expect"


def _detect_fixture_style(files: list[Path], config: PlaySpecConfig) -> str:
    """Detect fixture pattern: factory, file-based, or inline."""
    fixtures_dir = Path(config.fixtures_dir)
    if fixtures_dir.is_dir() and any(fixtures_dir.iterdir()):
        return "file-based"

    for f in files[:5]:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if "factory" in content.lower() or "create" in content.lower():
            return "factory"
    return "inline"
