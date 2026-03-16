"""Auto-bug filing — create Jira bugs for persistently failing tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playspec.console import console
from playspec.stability import StabilityStore


BUG_STORE_FILE = Path(".playspec") / "bugs.json"

DEFAULT_BUG_CONSECUTIVE_FAILURES = 3
DEFAULT_BUG_LABELS = ["playspec-auto-bug"]


def load_bug_store(path: Path | None = None) -> dict[str, Any]:
    """Load the bug store from disk."""
    p = path or BUG_STORE_FILE
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_bug_store(store: dict[str, Any], path: Path | None = None) -> None:
    """Persist the bug store to disk."""
    p = path or BUG_STORE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2), encoding="utf-8")


def check_and_file_bugs(
    stability: StabilityStore,
    consecutive_threshold: int = DEFAULT_BUG_CONSECUTIVE_FAILURES,
    labels: list[str] | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Check for persistently failing tests and file Jira bugs.

    A test is a candidate when its last *consecutive_threshold* results are
    all failures.

    Returns a list of newly filed bug keys.
    """
    from playspec.integrations.jira_client import create_issue, search_issues

    if labels is None:
        labels = list(DEFAULT_BUG_LABELS)

    bug_store = load_bug_store()
    filed: list[str] = []

    for test_key, rec in stability.records.items():
        recent = rec.last_n_results[-consecutive_threshold:]
        if len(recent) < consecutive_threshold:
            continue
        if any(recent):
            # At least one pass — not a persistent failure
            continue

        # Already tracked?
        if test_key in bug_store and bug_store[test_key].get("bug_key"):
            continue

        # Search Jira for existing playspec-auto-bug for this test
        label_query = " AND ".join(f'labels = "{lb}"' for lb in labels)
        jql = f'{label_query} AND summary ~ "\\"{_escape_jql(test_key.split("::")[-1])}\\"" AND status != Done'
        existing = search_issues(jql)
        if existing:
            # Record the existing bug so we don't search again
            bug_store[test_key] = {"bug_key": existing[0]["key"], "auto_filed": False}
            continue

        if dry_run:
            console.print(f"  [yellow]Would file bug for:[/yellow] {test_key}")
            continue

        # Determine parent ticket from the test key
        parent_key = _extract_parent_key(test_key)
        project_key = _project_from_parent(parent_key)

        if not project_key:
            console.print(f"  [dim]Skipping bug for {test_key} — cannot determine project key.[/dim]")
            continue

        test_name = test_key.split("::")[-1] if "::" in test_key else test_key
        summary = f"[PlaySpec] Persistent failure: {test_name}"

        description_parts = [
            f"Test: {test_key}",
            f"Last {consecutive_threshold} runs: all FAILED",
            f"Total runs: {rec.total_runs}",
            f"Pass rate: {rec.flaky_score:.0%}",
        ]
        if rec.last_failed_at:
            description_parts.append(f"Last failure: {rec.last_failed_at}")
        if parent_key:
            description_parts.append(f"Parent story: {parent_key}")

        description = "\n".join(description_parts)

        bug_key = create_issue(
            project_key=project_key,
            summary=summary,
            description=description,
            issue_type="Bug",
            labels=labels,
            parent_key=parent_key,
        )

        if bug_key:
            bug_store[test_key] = {"bug_key": bug_key, "auto_filed": True}
            filed.append(bug_key)
            console.print(f"  [green]Filed bug {bug_key} for {test_key}[/green]")

    save_bug_store(bug_store)
    return filed


def _extract_parent_key(test_key: str) -> str | None:
    """Try to extract a Jira key from the test key (file or describe path)."""
    import re
    m = re.search(r"[A-Z]+-\d+", test_key)
    return m.group(0) if m else None


def _project_from_parent(parent_key: str | None) -> str | None:
    """Extract the Jira project key from a parent issue key like PLAY-1."""
    if not parent_key:
        return None
    parts = parent_key.split("-")
    return parts[0] if len(parts) >= 2 else None


def _escape_jql(text: str) -> str:
    """Escape special JQL characters in a search string."""
    special = '\\+-&|!(){}[]^"~*?:'
    for ch in special:
        text = text.replace(ch, "\\" + ch)
    return text
