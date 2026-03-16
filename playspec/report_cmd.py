"""Traceability report — Ticket -> Tests -> Results -> Stability -> Bugs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.table import Table

from playspec.config import load_config
from playspec.console import console
from playspec.manifest import load_manifest, parse_jira_keys, parse_describe_jira_keys, parse_test_to_jira_map
from playspec.stability import load_stability


def _load_bug_store() -> dict[str, Any]:
    """Load the bugs.json store (if it exists)."""
    p = Path(".playspec") / "bugs.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _build_traceability_data(
    jira_filter: str | None = None,
    last_n: int = 5,
) -> list[dict[str, Any]]:
    """Build the traceability matrix data.

    Returns a list of row dicts:
      { ticket, test_file, test_name, last_n_results, stability_pct, bug_key }
    """
    config = load_config()
    stability = load_stability()
    bug_store = _load_bug_store()

    test_dir = Path(config.test_dir)
    if not test_dir.is_dir():
        return []

    # Collect all ticket -> test mappings using precise describe-block parsing.
    # Stability records may exist under both basename ("auth.spec.ts::test")
    # and full-path ("example-app/tests/auth.spec.ts::test") keys.  We merge
    # them by preferring the record with more total runs, and deduplicate on
    # (ticket, test_name).
    ticket_tests: dict[str, dict[str, dict[str, Any]]] = {}  # ticket -> test_name -> row

    for tf in sorted(test_dir.rglob("*.spec.ts")):
        tf_str = str(tf)
        basename = Path(tf_str).name
        test_jira_map = parse_test_to_jira_map(tf)

        # Walk stability records that belong to this file
        for rec_key, rec in stability.records.items():
            if not rec_key.startswith(tf_str) and not rec_key.startswith(basename):
                continue

            parts = rec_key.split("::", 1)
            test_name = parts[1] if len(parts) > 1 else rec_key

            # Look up which tickets this test maps to
            test_tickets = test_jira_map.get(test_name, [])
            if not test_tickets:
                test_tickets = parse_jira_keys(tf)

            for ticket in test_tickets:
                ticket_upper = ticket.upper()
                if jira_filter and ticket_upper != jira_filter.upper():
                    continue

                # Merge: keep the record with more data
                existing = ticket_tests.get(ticket_upper, {}).get(test_name)
                if existing and existing["_total_runs"] >= rec.total_runs:
                    continue

                recent = rec.last_n_results[-last_n:]
                pct = (sum(recent) / len(recent) * 100) if recent else 0.0
                bug_key = bug_store.get(rec_key, {}).get("bug_key", "")

                ticket_tests.setdefault(ticket_upper, {})[test_name] = {
                    "ticket": ticket_upper,
                    "test_file": basename,
                    "test_name": test_name,
                    "last_n_results": "".join("P" if r else "F" for r in recent),
                    "stability_pct": pct,
                    "bug_key": bug_key,
                    "_total_runs": rec.total_runs,
                }

    # Flatten and sort
    rows: list[dict[str, Any]] = []
    for ticket in sorted(ticket_tests):
        for entry in sorted(ticket_tests[ticket].values(), key=lambda e: e["test_name"]):
            row = {k: v for k, v in entry.items() if not k.startswith("_")}
            rows.append(row)
    return rows


def show_traceability(
    fmt: str = "terminal",
    output: str | None = None,
    jira_filter: str | None = None,
    last_n: int = 5,
) -> None:
    """Generate and display the traceability report."""
    rows = _build_traceability_data(jira_filter=jira_filter, last_n=last_n)

    if not rows:
        console.print("[yellow]No traceability data found. Run regression tests first.[/yellow]")
        return

    if fmt == "json":
        content = json.dumps(rows, indent=2)
        if output:
            Path(output).write_text(content, encoding="utf-8")
            console.print(f"[green]Wrote JSON report to {output}[/green]")
        else:
            console.print(content)
        return

    if fmt == "md":
        lines = [
            "| Ticket | Test File | Test | Last Runs | Stability | Bug |",
            "|--------|-----------|------|-----------|-----------|-----|",
        ]
        for r in rows:
            bug = r["bug_key"] or "\u2014"
            lines.append(
                f"| {r['ticket']} | {r['test_file']} | {r['test_name']} "
                f"| {r['last_n_results']} | {r['stability_pct']:.0f}% | {bug} |"
            )
        content = "\n".join(lines) + "\n"
        if output:
            Path(output).write_text(content, encoding="utf-8")
            console.print(f"[green]Wrote Markdown report to {output}[/green]")
        else:
            console.print(content)
        return

    # Default: terminal (Rich table)
    table = Table(title="Traceability Report")
    table.add_column("Ticket", style="bold")
    table.add_column("Test File")
    table.add_column("Test")
    table.add_column("Last Runs", justify="center")
    table.add_column("Stability", justify="right")
    table.add_column("Bug")

    for r in rows:
        runs_display = ""
        for ch in r["last_n_results"]:
            if ch == "P":
                runs_display += "[green]P[/green]"
            else:
                runs_display += "[red]F[/red]"

        pct = r["stability_pct"]
        if pct >= 80:
            pct_str = f"[green]{pct:.0f}%[/green]"
        elif pct >= 50:
            pct_str = f"[yellow]{pct:.0f}%[/yellow]"
        else:
            pct_str = f"[red]{pct:.0f}%[/red]"

        bug = r["bug_key"] or "\u2014"

        table.add_row(
            r["ticket"],
            r["test_file"],
            r["test_name"],
            runs_display,
            pct_str,
            bug,
        )

    console.print(table)
    if output:
        # Also write as text for file output in terminal mode
        from io import StringIO
        from rich.console import Console as RichConsole
        buf = StringIO()
        file_console = RichConsole(file=buf, width=200)
        file_console.print(table)
        Path(output).write_text(buf.getvalue(), encoding="utf-8")
        console.print(f"[green]Wrote report to {output}[/green]")
