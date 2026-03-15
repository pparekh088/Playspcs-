"""Auth-check command — verify availability of integrations and backends."""

from __future__ import annotations

import os
import shutil
import subprocess

from rich.table import Table

from playspec.console import console


def run_auth_check() -> None:
    """Check and display the status of every integration and agent backend."""
    table = Table(title="Integration & Backend Status")
    table.add_column("Integration", style="bold")
    table.add_column("Status")
    table.add_column("Detail")

    table.add_row("Node.js / npx", *_check_command(["npx", "--version"]))
    table.add_row("Playwright", *_check_command(["npx", "playwright", "--version"]))
    table.add_row("Git", *_check_command(["git", "--version"]))
    table.add_row("GitHub CLI", *_check_command(["gh", "--version"]))
    table.add_row("JIRA (Atlassian CLI)", *_check_command(["atlas", "auth", "status"]))
    table.add_row("Figma (env token)", *_check_env("FIGMA_TOKEN"))
    table.add_row("GH Copilot", *_check_command(["gh", "copilot", "--version"]))
    table.add_row("OpenCode", *_check_command(["opencode", "--version"]))
    table.add_row("Claude Code", *_check_command(["claude", "--version"]))

    console.print(table)


def _check_command(cmd: list[str]) -> tuple[str, str]:
    """Try running a command; return (status_str, detail)."""
    if not shutil.which(cmd[0]):
        return "[red]unavailable[/red]", f"{cmd[0]} not found on PATH"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        if proc.returncode == 0:
            ver = proc.stdout.strip().splitlines()[0][:60] if proc.stdout.strip() else "ok"
            return "[green]available[/green]", ver
        return "[yellow]error[/yellow]", (proc.stderr.strip()[:80] or "non-zero exit")
    except subprocess.TimeoutExpired:
        return "[yellow]timeout[/yellow]", "command timed out"
    except Exception as exc:
        return "[red]error[/red]", str(exc)[:80]


def _check_env(var_name: str) -> tuple[str, str]:
    """Check if an environment variable is set."""
    val = os.getenv(var_name)
    if val:
        return "[green]available[/green]", f"{var_name} is set ({len(val)} chars)"
    return "[red]unavailable[/red]", f"{var_name} not set"
