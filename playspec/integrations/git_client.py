"""Git integration — branch, SHA, diff detection via subprocess."""

from __future__ import annotations

import subprocess

from playspec.console import console


def _run_git(args: list[str], timeout: int = 30) -> str:
    """Run a git command and return stripped stdout."""
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        console.print("[red]git not found on PATH.[/red]")
        return ""
    except subprocess.CalledProcessError as exc:
        console.print(f"[yellow]git {' '.join(args)} failed:[/yellow] {exc.stderr.strip()[:200]}")
        return ""
    except subprocess.TimeoutExpired:
        console.print(f"[yellow]git {' '.join(args)} timed out.[/yellow]")
        return ""


def get_changed_files(base_branch: str = "main") -> list[str]:
    """Return files changed relative to *base_branch* via git diff."""
    output = _run_git(["diff", "--name-only", base_branch])
    if not output:
        return []
    return [line for line in output.splitlines() if line.strip()]


def get_pr_changed_files(pr_number: int) -> list[str]:
    """Return files changed in a PR via the GitHub CLI."""
    try:
        proc = subprocess.run(
            ["gh", "pr", "diff", str(pr_number), "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return [line for line in proc.stdout.strip().splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        console.print(f"[yellow]Failed to get PR diff: {exc}[/yellow]")
        return []


def get_current_branch() -> str:
    """Return the current git branch name."""
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def get_current_sha() -> str:
    """Return the current commit SHA."""
    return _run_git(["rev-parse", "HEAD"])
