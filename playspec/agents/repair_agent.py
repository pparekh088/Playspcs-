"""Repair agent — automatically patches failing tests and validates the fix."""

from __future__ import annotations

import json
from pathlib import Path

from playspec.backends.base import AgentBackend
from playspec.config import ExecutionProfile, PlaySpecConfig
from playspec.console import console
from playspec.prompts.loader import load_prompt
from playspec.schemas.execution_result import ExecutionResult


def repair_tests(
    result: ExecutionResult,
    backend: AgentBackend,
    config: PlaySpecConfig,
    profile: ExecutionProfile,
    max_retries: int = 3,
    run_id: str = "",
) -> int:
    """Attempt to repair each failing test by applying LLM-generated patches.

    Each patch is applied to the test file and immediately re-executed to
    validate it. Successful repairs are kept; all-retry failures restore the
    original content.

    Args:
        result: Execution result with failures.
        backend: Agent backend.
        config: PlaySpec config.
        profile: Execution profile used to re-run tests for validation.
        max_retries: Max repair attempts per test.
        run_id: Current run ID for artifact storage.

    Returns:
        Number of tests successfully repaired.
    """
    from playspec.executor.runner import run_tests as execute_tests

    if not result.failures:
        return 0

    repairs_dir = Path(".playspec") / "runs" / run_id / "repairs"
    repairs_dir.mkdir(parents=True, exist_ok=True)

    repaired = 0

    for failure in result.failures:
        console.print(f"\n[bold]Repairing:[/bold] {failure.test_file} :: {failure.test_name}")

        test_path = Path(failure.test_file)
        if not test_path.is_file():
            console.print(f"  [yellow]File not found, skipping.[/yellow]")
            continue

        original = test_path.read_text(encoding="utf-8")
        current_error = failure.error_message
        current_stack = failure.stack_trace
        fixed = False

        repaired = False
        for attempt in range(1, max_retries + 1):
            console.print(f"  Attempt {attempt}/{max_retries}…")

            context = {
                "test_file": failure.test_file,
                "test_name": failure.test_name,
                "error_message": current_error,
                "stack_trace": current_stack,
                "original_code": test_path.read_text(encoding="utf-8"),
            }
            prompt = load_prompt("repair", context)
            response = backend.invoke(prompt)

            patch_file = repairs_dir / f"{test_path.stem}-attempt{attempt}.patch"
            patch_file.write_text(response.content, encoding="utf-8")

            try:
                data = json.loads(response.content)
                patched_content = data.get("patch", "")
                diagnosis = data.get("diagnosis", "")
            except (json.JSONDecodeError, AttributeError):
                console.print(f"  [yellow]Could not parse repair response, skipping attempt.[/yellow]")
                continue

            if not patched_content.strip():
                console.print(f"  [yellow]Empty patch returned, skipping attempt.[/yellow]")
                continue

            console.print(f"  [dim]Diagnosis: {diagnosis}[/dim]")

            # Apply patch and validate by re-running the test
            test_path.write_text(patched_content, encoding="utf-8")
            validation = execute_tests([str(test_path)], profile, f"{run_id}-repair{attempt}", config.test_dir)
            if _verify_patch(validation):
                console.print(f"  [green]✓ Repair validated — test now passes.[/green]")
                fixed = True
                repaired += 1
                break
            else:
                # Feed the new error back into the next attempt
                if validation.failures:
                    current_error = validation.failures[0].error_message
                    current_stack = validation.failures[0].stack_trace
                console.print(f"  [yellow]Patch did not fix the test. Retrying…[/yellow]")

        if not fixed:
            console.print(f"  [red]Could not repair after {max_retries} attempts. Restoring original.[/red]")
            test_path.write_text(original, encoding="utf-8")

    console.print(f"\n[bold]Repairs complete:[/bold] {repaired}/{len(result.failures)} tests fixed")
    return repaired


def _verify_patch(validation) -> bool:
    """Return True if the validation run produced zero failures."""
    return validation.failed == 0
