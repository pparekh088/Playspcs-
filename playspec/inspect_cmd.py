"""Inspect commands — test inventory, suites, and coverage views."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from playspec.config import load_config
from playspec.console import console
from playspec.manifest import load_manifest, parse_test_tags, parse_jira_key, parse_owner
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
        jira = parse_jira_key(tf) or "—"
        owner = parse_owner(tf) or "—"

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


def show_coverage(jira_key: str) -> None:
    """Show which tests are tagged with the given JIRA key."""
    config = load_config()
    manifest = load_manifest()

    files = manifest.resolve_jira_tag(jira_key, config.test_dir)
    if not files:
        console.print(f"[yellow]No tests tagged with {jira_key}.[/yellow]")
        return

    table = Table(title=f"Coverage for {jira_key}")
    table.add_column("Test File", style="bold")
    table.add_column("Tags")

    for f in files:
        tags = parse_test_tags(f)
        table.add_row(f, ", ".join(sorted(tags)))

    console.print(table)
