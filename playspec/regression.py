"""Regression mode pipeline — deterministic Playwright test execution for CI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from playspec.audit import create_audit, save_audit
from playspec.config import PlaySpecConfig, RepairPolicy, load_config
from playspec.console import console
from playspec.executor.runner import run_tests
from playspec.executor.diagnostics import classify_failure, generate_suggested_fixes
from playspec.integrations.git_client import get_changed_files, get_current_branch, get_current_sha, get_pr_changed_files
from playspec.manifest import load_manifest, Manifest
from playspec.run_id import generate_run_id
from playspec.schemas.audit_entry import AuditResults, RunMode
from playspec.schemas.execution_result import ExecutionResult
from playspec.stability import load_stability, save_stability


def run_regression(
    suite_names: list[str] | None = None,
    tags: list[str] | None = None,
    changed_files: bool = False,
    pr_number: int | None = None,
    jira_key: str | None = None,
    manifest_path: Path | None = None,
    profile_name: str | None = None,
    base_url_override: str | None = None,
    include_quarantined: bool = False,
) -> None:
    """Execute the full regression pipeline.

    This function NEVER mutates test files.  It NEVER auto-repairs.
    It reports failures or it is broken.
    """
    config = load_config()
    profile = config.get_profile(profile_name)

    if profile.repair_policy != RepairPolicy.NEVER:
        console.print("[yellow]Warning: regression mode requires repair_policy='never'. Auto-correcting.[/yellow]")
        profile.repair_policy = RepairPolicy.NEVER

    if base_url_override:
        profile.base_url = base_url_override

    manifest = load_manifest(manifest_path)
    resolved_files: list[str] = []

    if suite_names:
        for s in suite_names:
            resolved_files.extend(manifest.resolve_suite(s, config.test_dir))

    if tags:
        resolved_files.extend(manifest.resolve_tags(tags, config.test_dir))

    if changed_files:
        cf = get_changed_files()
        resolved_files.extend(manifest.resolve_changed_files(cf, config.test_dir))

    if pr_number is not None:
        pf = get_pr_changed_files(pr_number)
        resolved_files.extend(manifest.resolve_changed_files(pf, config.test_dir))

    if jira_key:
        resolved_files.extend(manifest.resolve_jira_tag(jira_key, config.test_dir))

    resolved_files = list(dict.fromkeys(resolved_files))

    quarantined = manifest.get_quarantined()
    quarantined_count = 0
    if not include_quarantined:
        before = len(resolved_files)
        resolved_files = [f for f in resolved_files if f not in quarantined]
        quarantined_count = before - len(resolved_files)

    if not resolved_files:
        console.print("[yellow]No test files resolved. Nothing to run.[/yellow]")
        return

    run_id = generate_run_id()
    console.print(f"[bold]Run:[/bold] {run_id}  |  [bold]Tests:[/bold] {len(resolved_files)}  |  [bold]Profile:[/bold] {profile_name or 'auto'}")

    suite_label = ",".join(suite_names) if suite_names else "ad-hoc"

    _run_hooks(manifest, suite_names, "setup")

    try:
        result: ExecutionResult = run_tests(resolved_files, profile, run_id, config.test_dir)
    finally:
        _run_hooks(manifest, suite_names, "teardown")

    for failure in result.failures:
        failure.failure_type = classify_failure(failure)

    suggested = generate_suggested_fixes(result)

    stability = load_stability()
    updates = stability.update(result, run_id=run_id)
    save_stability(stability)

    quarantine_candidates = stability.recommend_quarantine()
    if quarantine_candidates:
        new_quarantined = [q for q in quarantine_candidates if q not in manifest.get_quarantined()]
        if new_quarantined:
            for key in new_quarantined:
                manifest.raw.quarantine.append(key)
                console.print(f"[yellow]Auto-quarantined flaky test:[/yellow] {key}")
            if manifest.path:
                import yaml
                manifest.path.write_text(
                    yaml.safe_dump(manifest.raw.model_dump(), default_flow_style=False),
                    encoding="utf-8",
                )

    audit_entry = create_audit(
        run_id=run_id,
        mode=RunMode.REGRESSION,
        profile=profile_name or "auto",
        suite=suite_label,
        resolved_tests=len(resolved_files),
        quarantined_skipped=quarantined_count,
        results=AuditResults(passed=result.passed, failed=result.failed, skipped=result.skipped),
        failures=[f.test_name for f in result.failures],
        duration_seconds=result.duration_seconds,
        stability_updates=updates,
    )
    save_audit(audit_entry)

    _print_summary(result, suggested, run_id)

    is_blocking = suite_names and any(manifest.is_blocking(s) for s in suite_names)
    if result.failed > 0 and is_blocking:
        raise SystemExit(1)


def _run_hooks(manifest: Manifest, suite_names: list[str] | None, phase: str) -> None:
    """Run setup or teardown hooks for resolved suites."""
    import subprocess

    if not suite_names:
        return
    for s in suite_names:
        hook = manifest.get_hook(s, phase)
        if hook:
            console.print(f"[dim]Running {phase} hook for suite '{s}': {hook}[/dim]")
            try:
                subprocess.run(hook, shell=True, check=True, capture_output=True, timeout=300)
            except subprocess.CalledProcessError as exc:
                console.print(f"[red]Hook failed ({phase} for '{s}'):[/red] {exc.stderr.decode()[:500] if exc.stderr else 'unknown error'}")
            except subprocess.TimeoutExpired:
                console.print(f"[red]Hook timed out ({phase} for '{s}').[/red]")


def _print_summary(result: ExecutionResult, suggested: list, run_id: str) -> None:
    """Print a Rich summary table for the regression run."""
    table = Table(title=f"Regression Results — {run_id}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total tests", str(result.total_tests))
    table.add_row("Passed", f"[green]{result.passed}[/green]")
    table.add_row("Failed", f"[red]{result.failed}[/red]" if result.failed else "0")
    table.add_row("Skipped", str(result.skipped))
    table.add_row("Duration", f"{result.duration_seconds:.1f}s")
    table.add_row("Suggested fixes", str(len(suggested)))

    console.print(table)

    if result.failures:
        console.print("\n[bold red]Failures:[/bold red]")
        for f in result.failures:
            console.print(f"  • {f.test_file} :: {f.test_name} — {f.failure_type.value}: {f.error_message[:120]}")
        console.print(f"\n[dim]Artifacts: .playspec/runs/{run_id}/[/dim]")
