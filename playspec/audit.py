"""Audit trail — write, read, diff, prune immutable run records."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from playspec.console import console
from playspec.schemas.audit_entry import AuditEntry, AuditResults, RunMode

AUDIT_DIR = Path(".playspec") / "audits"


def create_audit(
    run_id: str,
    mode: RunMode,
    profile: str = "auto",
    suite: str | None = None,
    resolved_tests: int = 0,
    quarantined_skipped: int = 0,
    results: AuditResults | None = None,
    failures: list[str] | None = None,
    duration_seconds: float = 0.0,
    stability_updates: int = 0,
    agent_backend_used: str | None = None,
) -> AuditEntry:
    """Build an AuditEntry with current git context."""
    from playspec.integrations.git_client import get_current_branch, get_current_sha

    return AuditEntry(
        run_id=run_id,
        mode=mode,
        profile=profile,
        suite=suite,
        duration_seconds=duration_seconds,
        git_ref=get_current_branch(),
        git_sha=get_current_sha(),
        resolved_tests=resolved_tests,
        quarantined_skipped=quarantined_skipped,
        results=results or AuditResults(),
        failures=failures or [],
        stability_updates=stability_updates,
        agent_backend_used=agent_backend_used,
    )


def save_audit(entry: AuditEntry, directory: Path | None = None) -> Path:
    """Persist an audit entry as JSON."""
    d = directory or AUDIT_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{entry.run_id}.json"
    path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_audit(run_id: str, directory: Path | None = None) -> AuditEntry | None:
    """Load an audit entry by run ID."""
    d = directory or AUDIT_DIR
    path = d / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        return AuditEntry.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_audits(directory: Path | None = None) -> list[AuditEntry]:
    """Return all audit entries sorted newest-first."""
    d = directory or AUDIT_DIR
    if not d.is_dir():
        return []
    entries: list[AuditEntry] = []
    for f in sorted(d.glob("ps-*.json"), reverse=True):
        try:
            entries.append(AuditEntry.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return entries


def prune_audits(older_than_days: int, directory: Path | None = None) -> int:
    """Delete audit files older than the specified number of days. Returns count deleted."""
    d = directory or AUDIT_DIR
    if not d.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    deleted = 0
    for f in d.glob("ps-*.json"):
        try:
            entry = AuditEntry.model_validate_json(f.read_text(encoding="utf-8"))
            ts = entry.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                f.unlink()
                deleted += 1
        except Exception:
            continue
    return deleted


# ── CLI command implementations ─────────────────────────────────────

def list_audits_cmd() -> None:
    """Print audit list as a Rich table."""
    entries = list_audits()
    if not entries:
        console.print("[yellow]No audit records found.[/yellow]")
        return

    table = Table(title="Audit Trail")
    table.add_column("Run ID", style="bold")
    table.add_column("Mode")
    table.add_column("Suite")
    table.add_column("Passed", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Timestamp")

    for e in entries:
        failed_str = f"[red]{e.results.failed}[/red]" if e.results.failed else "0"
        table.add_row(
            e.run_id,
            e.mode.value,
            e.suite or "—",
            f"[green]{e.results.passed}[/green]",
            failed_str,
            str(e.results.skipped),
            f"{e.duration_seconds:.1f}s",
            e.timestamp.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


def show_audit_cmd(run_id: str) -> None:
    """Print detailed view of a single audit entry."""
    entry = load_audit(run_id)
    if entry is None:
        console.print(f"[red]Audit record '{run_id}' not found.[/red]")
        return

    lines = [
        f"[bold]Run ID:[/bold]     {entry.run_id}",
        f"[bold]Mode:[/bold]       {entry.mode.value}",
        f"[bold]Profile:[/bold]    {entry.profile}",
        f"[bold]Suite:[/bold]      {entry.suite or '—'}",
        f"[bold]Timestamp:[/bold]  {entry.timestamp.isoformat()}",
        f"[bold]Duration:[/bold]   {entry.duration_seconds:.1f}s",
        f"[bold]Git ref:[/bold]    {entry.git_ref or '—'}",
        f"[bold]Git SHA:[/bold]    {entry.git_sha or '—'}",
        f"[bold]Resolved:[/bold]   {entry.resolved_tests} tests",
        f"[bold]Quarantined:[/bold]{entry.quarantined_skipped} skipped",
        f"[bold]Results:[/bold]    ✅ {entry.results.passed}  ❌ {entry.results.failed}  ⏭ {entry.results.skipped}",
    ]
    if entry.failures:
        lines.append(f"\n[bold red]Failures:[/bold red]")
        for f in entry.failures:
            lines.append(f"  • {f}")

    console.print(Panel("\n".join(lines), title=f"Audit: {run_id}", expand=False))


def diff_audits_cmd(run_a: str, run_b: str) -> None:
    """Compare two audit records side-by-side."""
    a = load_audit(run_a)
    b = load_audit(run_b)
    if a is None:
        console.print(f"[red]Audit '{run_a}' not found.[/red]")
        return
    if b is None:
        console.print(f"[red]Audit '{run_b}' not found.[/red]")
        return

    table = Table(title=f"Audit Diff: {run_a} vs {run_b}")
    table.add_column("Metric", style="bold")
    table.add_column(run_a)
    table.add_column(run_b)
    table.add_column("Delta")

    def _delta(va: int, vb: int) -> str:
        d = vb - va
        if d > 0:
            return f"[green]+{d}[/green]"
        if d < 0:
            return f"[red]{d}[/red]"
        return "—"

    table.add_row("Resolved tests", str(a.resolved_tests), str(b.resolved_tests), _delta(a.resolved_tests, b.resolved_tests))
    table.add_row("Passed", str(a.results.passed), str(b.results.passed), _delta(a.results.passed, b.results.passed))
    table.add_row("Failed", str(a.results.failed), str(b.results.failed), _delta(a.results.failed, b.results.failed))
    table.add_row("Skipped", str(a.results.skipped), str(b.results.skipped), _delta(a.results.skipped, b.results.skipped))
    table.add_row("Duration", f"{a.duration_seconds:.1f}s", f"{b.duration_seconds:.1f}s", "")

    console.print(table)


def export_audit_cmd(run_id: str, fmt: str, output: Optional[Path]) -> None:
    """Export an audit record to JSON or Markdown."""
    entry = load_audit(run_id)
    if entry is None:
        console.print(f"[red]Audit '{run_id}' not found.[/red]")
        return

    if fmt == "json":
        content = entry.model_dump_json(indent=2)
        ext = ".json"
    else:
        content = _audit_to_markdown(entry)
        ext = ".md"

    if output:
        out_path = output
    else:
        out_path = Path(f"{run_id}{ext}")

    out_path.write_text(content, encoding="utf-8")
    console.print(f"[green]✓[/green] Exported to {out_path}")


def prune_audits_cmd(older_than: str) -> None:
    """Parse the duration string and prune old audits."""
    m = re.match(r"(\d+)d", older_than)
    if not m:
        console.print("[red]Invalid duration. Use format like '90d'.[/red]")
        return
    days = int(m.group(1))
    deleted = prune_audits(days)
    console.print(f"[green]✓[/green] Pruned {deleted} audit(s) older than {days} days.")


def _audit_to_markdown(entry: AuditEntry) -> str:
    """Convert an audit entry to Markdown."""
    lines = [
        f"# Audit Report: {entry.run_id}\n",
        f"- **Mode:** {entry.mode.value}",
        f"- **Profile:** {entry.profile}",
        f"- **Suite:** {entry.suite or '—'}",
        f"- **Timestamp:** {entry.timestamp.isoformat()}",
        f"- **Duration:** {entry.duration_seconds:.1f}s",
        f"- **Git:** {entry.git_ref} @ {entry.git_sha or '—'}",
        "",
        "## Results\n",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Passed | {entry.results.passed} |",
        f"| Failed | {entry.results.failed} |",
        f"| Skipped | {entry.results.skipped} |",
        f"| Total resolved | {entry.resolved_tests} |",
    ]
    if entry.failures:
        lines.extend(["", "## Failures\n"])
        for f in entry.failures:
            lines.append(f"- {f}")
    return "\n".join(lines) + "\n"
