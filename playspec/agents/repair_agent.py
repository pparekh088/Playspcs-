"""Repair agent — proposes targeted patches for failing tests."""

from __future__ import annotations

import json
import shutil
import subprocess
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
    """Attempt to repair each failing test via a retry loop.

    For each failure:
      1. Send failure context to the agent backend.
      2. Apply the proposed patch to a temporary copy of the test file.
      3. Re-run only the failing test.
      4. If it passes, stage the patch for developer review.
      5. If it fails, retry up to *max_retries* times.

    Repairs are staged as diffs for developer review, never auto-committed.
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

        repaired = False
        for attempt in range(1, max_retries + 1):
            console.print(f"  Attempt {attempt}/{max_retries}…")
            response = backend.invoke(prompt)

            patch_file = repairs_dir / f"{test_path.stem}-attempt{attempt}.patch"
            patch_file.write_text(response.content, encoding="utf-8")
            console.print(f"  [dim]Patch written to {patch_file}[/dim]")

            patched_content = _extract_patched_code(response.content, original)
            if patched_content is None:
                console.print(f"  [yellow]Could not extract patched code from response.[/yellow]")
                continue

            if _verify_patch(patched_content, test_path, config):
                staged = repairs_dir / f"{test_path.stem}-fix.ts"
                staged.write_text(patched_content, encoding="utf-8")
                console.print(f"  [green]Patch verified — staged at {staged}[/green]")
                repaired = True
                break
            else:
                console.print(f"  [yellow]Patch did not fix the failure, retrying…[/yellow]")
                context["error_message"] = f"Previous patch attempt {attempt} did not fix the issue. {failure.error_message}"
                prompt = load_prompt("repair", context)

        if not repaired:
            console.print(f"  [red]Could not repair after {max_retries} attempts.[/red]")

    console.print(f"\n[bold]Repair patches available in:[/bold] {repairs_dir}")


def _extract_patched_code(response: str, original: str) -> str | None:
    """Try to extract the patched file content from the agent response."""
    try:
        parsed = json.loads(response)
        if isinstance(parsed, dict) and "patch" in parsed:
            return parsed["patch"]
    except (json.JSONDecodeError, TypeError):
        pass

    if "import" in response and ("test(" in response or "test.describe(" in response):
        return response

    return None


def _verify_patch(patched_content: str, original_path: Path, config: PlaySpecConfig) -> bool:
    """Apply patch to a temp file and re-run the test to check if it passes."""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".spec.ts", dir=original_path.parent, delete=False
        ) as tmp:
            tmp.write(patched_content)
            tmp_path = Path(tmp.name)

        try:
            proc = subprocess.run(
                ["npx", "playwright", "test", str(tmp_path), "--reporter=list"],
                capture_output=True, text=True, timeout=120,
            )
            return proc.returncode == 0
        finally:
            tmp_path.unlink(missing_ok=True)
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
