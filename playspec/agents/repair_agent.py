"""Repair agent — proposes targeted patches for failing tests."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from playspec.backends.base import AgentBackend
from playspec.config import PlaySpecConfig
from playspec.console import console
from playspec.prompts.loader import load_prompt
from playspec.schemas.execution_result import ExecutionResult


def repair_tests(
    result: ExecutionResult,
    backend: AgentBackend,
    config: PlaySpecConfig,
    max_retries: int = 3,
    run_id: str = "",
) -> None:
    """Attempt to repair each failing test.

    Repairs are staged as diffs for developer review, never auto-committed.

    Args:
        result: Execution result with failures.
        backend: Agent backend.
        config: PlaySpec config.
        max_retries: Max repair attempts per test.
        run_id: Current run ID for artifact storage.
    """
    if not result.failures:
        return

    repairs_dir = Path(".playspec") / "runs" / run_id / "repairs"
    repairs_dir.mkdir(parents=True, exist_ok=True)

    for failure in result.failures:
        console.print(f"\n[bold]Repairing:[/bold] {failure.test_file} :: {failure.test_name}")

        test_path = Path(failure.test_file)
        if not test_path.is_file():
            console.print(f"  [yellow]File not found, skipping.[/yellow]")
            continue

        original = test_path.read_text(encoding="utf-8")
        context = {
            "test_file": failure.test_file,
            "test_name": failure.test_name,
            "error_message": failure.error_message,
            "stack_trace": failure.stack_trace,
            "original_code": original,
        }
        prompt = load_prompt("repair", context)

        for attempt in range(1, max_retries + 1):
            console.print(f"  Attempt {attempt}/{max_retries}…")
            response = backend.invoke(prompt)

            patch_file = repairs_dir / f"{test_path.stem}-attempt{attempt}.patch"
            patch_file.write_text(response.content, encoding="utf-8")
            console.print(f"  [dim]Patch written to {patch_file}[/dim]")

            console.print(f"  [yellow]Patch staged for review (not auto-applied).[/yellow]")
            break

    console.print(f"\n[bold]Repair patches available in:[/bold] {repairs_dir}")
