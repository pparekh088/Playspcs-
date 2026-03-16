"""PlaySpec CLI — powered by Typer."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from playspec.console import console

app = typer.Typer(
    name="playspec",
    help="Regression platform with agentic test generation for Playwright.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── Sub-command groups ──────────────────────────────────────────────

inspect_app = typer.Typer(help="Inspect test inventory, suites, and coverage.", no_args_is_help=True)
quarantine_app = typer.Typer(help="Manage quarantined tests.", no_args_is_help=True)
audit_app = typer.Typer(help="View and manage audit trail.", no_args_is_help=True)
report_app = typer.Typer(help="Generate reports.", no_args_is_help=True)

app.add_typer(inspect_app, name="inspect")
app.add_typer(quarantine_app, name="quarantine")
app.add_typer(audit_app, name="audit")
app.add_typer(report_app, name="report")


# ── init ────────────────────────────────────────────────────────────

@app.command()
def init(
    project_dir: Optional[Path] = typer.Argument(None, help="Project root (defaults to cwd)."),
) -> None:
    """Initialize PlaySpec in the current project."""
    from playspec.init_cmd import run_init

    run_init(project_dir)


# ── regress ─────────────────────────────────────────────────────────

@app.command()
def regress(
    suite: Optional[list[str]] = typer.Option(None, "--suite", "-s", help="Suite(s) to run (repeatable)."),
    tags: Optional[list[str]] = typer.Option(None, "--tags", "-t", help="Filter by tag(s)."),
    changed_files: bool = typer.Option(False, "--changed-files", help="Auto-detect from git diff."),
    pr: Optional[int] = typer.Option(None, "--pr", help="Detect changed files from a PR number."),
    jira: Optional[str] = typer.Option(None, "--jira", help="Run tests tagged with a JIRA key."),
    manifest: Optional[Path] = typer.Option(None, "--manifest", help="Alternative manifest file."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Execution profile override."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Override base URL."),
    include_quarantined: bool = typer.Option(False, "--include-quarantined", help="Include quarantined tests."),
) -> None:
    """Run regression tests driven by the manifest."""
    from playspec.regression import run_regression

    run_regression(
        suite_names=suite,
        tags=tags,
        changed_files=changed_files,
        pr_number=pr,
        jira_key=jira,
        manifest_path=manifest,
        profile_name=profile,
        base_url_override=base_url,
        include_quarantined=include_quarantined,
    )


# ── author ──────────────────────────────────────────────────────────

@app.command()
def author(
    jira: str = typer.Option(..., "--jira", help="JIRA ticket key (required)."),
    confluence: Optional[list[str]] = typer.Option(None, "--confluence", help="Confluence page URL(s)."),
    figma: Optional[str] = typer.Option(None, "--figma", help="Figma file URL."),
    copy_deck: Optional[Path] = typer.Option(None, "--copy-deck", help="Path to copy deck file."),
    output: Optional[Path] = typer.Option(None, "--output", help="Output directory for generated tests."),
    backend: Optional[str] = typer.Option(None, "--backend", help="Force a specific agent backend."),
    max_retries: int = typer.Option(3, "--max-retries", help="Repair loop budget."),
    skip_repair: bool = typer.Option(False, "--skip-repair", help="Skip the repair loop."),
    apply_fixes: Optional[str] = typer.Option(None, "--apply-fixes", help="Apply fixes from a regression run ID."),
) -> None:
    """Generate Playwright tests from JIRA, Confluence, Figma, and copy decks."""
    from playspec.author_pipeline import run_author

    run_author(
        jira_key=jira,
        confluence_urls=confluence,
        figma_url=figma,
        copy_deck_path=copy_deck,
        output_dir=output,
        backend_name=backend,
        max_retries=max_retries,
        skip_repair=skip_repair,
        apply_fixes_run_id=apply_fixes,
    )


# ── plan ────────────────────────────────────────────────────────────

@app.command()
def plan(
    jira: str = typer.Option(..., "--jira", help="JIRA ticket key."),
    confluence: Optional[list[str]] = typer.Option(None, "--confluence", help="Confluence page URL(s)."),
    figma: Optional[str] = typer.Option(None, "--figma", help="Figma file URL."),
    copy_deck: Optional[Path] = typer.Option(None, "--copy-deck", help="Path to copy deck file."),
    backend: Optional[str] = typer.Option(None, "--backend", help="Force a specific agent backend."),
    export_json: Optional[Path] = typer.Option(None, "--export-json", help="Export plan to JSON file."),
) -> None:
    """Generate a test plan without writing test files."""
    from playspec.author_pipeline import run_plan

    run_plan(
        jira_key=jira,
        confluence_urls=confluence,
        figma_url=figma,
        copy_deck_path=copy_deck,
        backend_name=backend,
        export_json=export_json,
    )


# ── inspect ─────────────────────────────────────────────────────────

@inspect_app.command("tests")
def inspect_tests() -> None:
    """Show all registered tests with tags, stability, and quarantine status."""
    from playspec.inspect_cmd import show_tests

    show_tests()


@inspect_app.command("suites")
def inspect_suites() -> None:
    """Show suites with test counts and run stats."""
    from playspec.inspect_cmd import show_suites

    show_suites()


@inspect_app.command("coverage")
def inspect_coverage(
    jira: str = typer.Option(..., "--jira", help="JIRA key to check coverage for."),
    gap_only: bool = typer.Option(False, "--gap-only", help="Show only uncovered acceptance criteria."),
) -> None:
    """Show which acceptance criteria are covered by tests."""
    from playspec.inspect_cmd import show_coverage

    show_coverage(jira, gap_only=gap_only)


# ── report ──────────────────────────────────────────────────────────

@report_app.command("traceability")
def report_traceability(
    fmt: str = typer.Option("terminal", "--format", "-f", help="Output format: terminal, json, or md."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Write report to file."),
    jira: Optional[str] = typer.Option(None, "--jira", help="Filter to a specific JIRA ticket."),
    last_n: int = typer.Option(5, "--last-n", help="Number of recent runs to show."),
) -> None:
    """Generate a traceability matrix: Ticket -> Tests -> Results -> Stability -> Bugs."""
    from playspec.report_cmd import show_traceability

    show_traceability(fmt=fmt, output=output, jira_filter=jira, last_n=last_n)


# ── quarantine ──────────────────────────────────────────────────────

@quarantine_app.command("add")
def quarantine_add(
    test_path: str = typer.Argument(..., help="Path to test file to quarantine."),
    reason: str = typer.Option("", "--reason", "-r", help="Reason for quarantining."),
) -> None:
    """Add a test to quarantine."""
    from playspec.quarantine_cmd import add_quarantine

    add_quarantine(test_path, reason)


@quarantine_app.command("remove")
def quarantine_remove(
    test_path: str = typer.Argument(..., help="Path to test file to un-quarantine."),
) -> None:
    """Remove a test from quarantine."""
    from playspec.quarantine_cmd import remove_quarantine

    remove_quarantine(test_path)


@quarantine_app.command("list")
def quarantine_list() -> None:
    """List all quarantined tests."""
    from playspec.quarantine_cmd import list_quarantine

    list_quarantine()


# ── audit ───────────────────────────────────────────────────────────

@audit_app.command("list")
def audit_list() -> None:
    """List all audit records."""
    from playspec.audit import list_audits_cmd

    list_audits_cmd()


@audit_app.command("show")
def audit_show(
    run_id: str = typer.Argument(..., help="Run ID to show."),
) -> None:
    """Show details of an audit record."""
    from playspec.audit import show_audit_cmd

    show_audit_cmd(run_id)


@audit_app.command("diff")
def audit_diff(
    run_a: str = typer.Argument(..., help="First run ID."),
    run_b: str = typer.Argument(..., help="Second run ID."),
) -> None:
    """Compare two audit records side by side."""
    from playspec.audit import diff_audits_cmd

    diff_audits_cmd(run_a, run_b)


@audit_app.command("export")
def audit_export(
    run_id: str = typer.Argument(..., help="Run ID to export."),
    fmt: str = typer.Option("json", "--format", "-f", help="Export format: json or md."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
) -> None:
    """Export an audit record to file."""
    from playspec.audit import export_audit_cmd

    export_audit_cmd(run_id, fmt, output)


@audit_app.command("prune")
def audit_prune(
    older_than: str = typer.Option("90d", "--older-than", help="Remove audits older than this (e.g. 90d)."),
) -> None:
    """Delete old audit records."""
    from playspec.audit import prune_audits_cmd

    prune_audits_cmd(older_than)


# ── auth-check ──────────────────────────────────────────────────────

@app.command("auth-check")
def auth_check() -> None:
    """Check availability of integrations and agent backends."""
    from playspec.auth_check import run_auth_check

    run_auth_check()


# ── Entrypoint (for typer) ──────────────────────────────────────────

def main() -> None:
    """CLI entrypoint invoked by the console_scripts hook."""
    app()


if __name__ == "__main__":
    main()
