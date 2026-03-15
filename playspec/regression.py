"""Regression mode pipeline — deterministic Playwright test execution for CI."""

from __future__ import annotations

import json
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
        console.print("[bold red]ERROR:[/bold red] Regression mode requires repair_policy='never'. Aborting.")
        raise SystemExit(1)

    if base_url_override:
        profile = profile.model_copy(update={"base_url": base_url_override})

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

    _check_environment(profile.base_url)

    run_id = generate_run_id()
    console.print(f"[bold]Run:[/bold] {run_id}  |  [bold]Tests:[/bold] {len(resolved_files)}  |  [bold]Profile:[/bold] {profile_name or 'auto'}")

    suite_label = ",".join(suite_names) if suite_names else "ad-hoc"

    _run_hooks(manifest, suite_names, "setup")

    timeout_mins = 30
    if suite_names:
        for s in suite_names:
            sc = manifest.get_suite(s)
            if sc and sc.timeout_minutes > timeout_mins:
                timeout_mins = sc.timeout_minutes

    try:
        result: ExecutionResult = run_tests(resolved_files, profile, run_id, config.test_dir, timeout_minutes=timeout_mins)
    finally:
        _run_hooks(manifest, suite_names, "teardown")

    for failure in result.failures:
        failure.failure_type = classify_failure(failure)

    suggested = generate_suggested_fixes(result)

    if suggested:
        fixes_path = Path(".playspec") / "runs" / run_id / "suggested-fixes.json"
        fixes_path.parent.mkdir(parents=True, exist_ok=True)
        fixes_path.write_text(
            json.dumps([f.model_dump() for f in suggested], indent=2, default=str),
            encoding="utf-8",
        )

    stability = load_stability()
    updates = stability.update(result)
    save_stability(stability)

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


def _check_environment(base_url: str) -> None:
    """Verify the target environment is reachable before running tests."""
    if not base_url or base_url.startswith("$"):
        return
    import httpx
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.head(base_url)
            if resp.status_code >= 500:
                console.print(f"[yellow]Warning: {base_url} returned HTTP {resp.status_code}.[/yellow]")
    except httpx.ConnectError:
        console.print(f"[bold red]ERROR:[/bold red] Cannot reach {base_url}. Is the environment running?")
        raise SystemExit(1)
    except httpx.TimeoutException:
        console.print(f"[yellow]Warning: {base_url} timed out (10s). Tests may fail.[/yellow]")
    except Exception:
        pass


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
