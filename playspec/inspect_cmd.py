"""Inspect commands — test inventory, suites, and coverage views."""

from __future__ import annotations

import re
from pathlib import Path

from rich.table import Table

from playspec.config import load_config
from playspec.console import console
from playspec.manifest import load_manifest, parse_test_tags, parse_jira_key, parse_jira_keys, parse_owner
from playspec.stability import load_stability


def show_tests() -> None:
    """Display a table of all registered tests with tags, stability, and quarantine."""
    config = load_config()
    manifest = load_manifest()
    stability = load_stability()
    quarantined = manifest.get_quarantined()

    test_dir = Path(config.test_dir)
    if not test_dir.is_dir():
        console.print(f"[yellow]Test directory '{config.test_dir}' not found.[/yellow]")
        return

    table = Table(title="Test Inventory")
    table.add_column("File", style="bold")
    table.add_column("Tags")
    table.add_column("JIRA")
    table.add_column("Owner")
    table.add_column("Stability", justify="right")
    table.add_column("Status")

    test_files = sorted(test_dir.rglob("*.spec.ts"))
    if not test_files:
        console.print("[yellow]No .spec.ts files found.[/yellow]")
        return

    for tf in test_files:
        tags = parse_test_tags(tf)
        keys = parse_jira_keys(tf)
        jira = ", ".join(keys) if keys else "\u2014"
        owner = parse_owner(tf) or "\u2014"

        tf_str = str(tf)
        q_status = "[red]quarantined[/red]" if tf_str in quarantined else "[green]active[/green]"

        flaky_str = "—"
        for key, rec in stability.records.items():
            if key.startswith(tf_str):
                flaky_str = f"{rec.flaky_score:.0%}"
                break

        table.add_row(
            tf_str,
            ", ".join(sorted(tags)) if tags else "—",
            jira,
            owner,
            flaky_str,
            q_status,
        )

    console.print(table)


def show_suites() -> None:
    """Display a table of suites with metadata and test counts."""
    config = load_config()
    manifest = load_manifest()

    table = Table(title="Suites")
    table.add_column("Suite", style="bold")
    table.add_column("Description")
    table.add_column("Tags")
    table.add_column("Blocking")
    table.add_column("Browsers")
    table.add_column("Tests", justify="right")

    for name, suite in manifest.suites.items():
        count = len(manifest.resolve_suite(name, config.test_dir))
        blocking = "[red]yes[/red]" if suite.blocking else "no"
        table.add_row(
            name,
            suite.description[:50],
            ", ".join(suite.tags),
            blocking,
            ", ".join(suite.browsers),
            str(count),
        )

    console.print(table)


def show_coverage(jira_key: str, gap_only: bool = False) -> None:
    """Show which tests cover a JIRA key's acceptance criteria.

    When Jira credentials are available, fetches acceptance criteria and
    cross-references with test names to show a gap analysis.
    """
    config = load_config()
    manifest = load_manifest()

    files = manifest.resolve_jira_tag(jira_key, config.test_dir)

    # Gather all test names for the matching files
    stability = load_stability()
    test_names: list[str] = []
    for f in files:
        for key in stability.records:
            if key.startswith(f) or key.startswith(Path(f).name):
                parts = key.split("::", 1)
                if len(parts) > 1:
                    test_names.append(parts[1])

    # Try to fetch acceptance criteria from Jira
    criteria: list[str] = []
    summary = ""
    try:
        import os
        if os.getenv("JIRA_BASE_URL"):
            from playspec.integrations.jira_client import get_issue
            issue = get_issue(jira_key, config)
            criteria = issue.get("acceptance_criteria", [])
            summary = issue.get("summary", "")
    except Exception:
        pass

    if not files and not criteria:
        console.print(f"[yellow]No tests tagged with {jira_key} and no AC found.[/yellow]")
        return

    # If we have AC, show gap analysis
    if criteria:
        if summary:
            console.print(f"\n[bold]{jira_key}:[/bold] {summary}\n")

        table = Table(title=f"Coverage Gap Analysis for {jira_key}")
        table.add_column("Acceptance Criterion", style="bold")
        table.add_column("Test(s)")
        table.add_column("Status")

        covered = 0
        for ac in criteria:
            # Keyword matching: split AC into significant words and look for overlaps
            ac_words = set(re.findall(r"\w{3,}", ac.lower()))
            matching: list[str] = []
            for tn in test_names:
                tn_words = set(re.findall(r"\w{3,}", tn.lower()))
                overlap = ac_words & tn_words
                if len(overlap) >= 2 or (len(ac_words) <= 3 and len(overlap) >= 1):
                    matching.append(tn)

            if matching:
                covered += 1
                if not gap_only:
                    table.add_row(
                        ac[:60],
                        ", ".join(matching[:3]),
                        "[green]Covered[/green]",
                    )
            else:
                table.add_row(
                    ac[:60],
                    "(none)",
                    "[red]GAP[/red]",
                )

        console.print(table)
        total_ac = len(criteria)
        pct = (covered / total_ac * 100) if total_ac else 0
        console.print(f"\n[bold]{covered} of {total_ac} acceptance criteria covered ({pct:.0f}%)[/bold]")
        return

    # Fallback: simple file listing (no AC available)
    table = Table(title=f"Coverage for {jira_key}")
    table.add_column("Test File", style="bold")
    table.add_column("Tags")

    for f in files:
        tags = parse_test_tags(f)
        table.add_row(f, ", ".join(sorted(tags)))

    console.print(table)
