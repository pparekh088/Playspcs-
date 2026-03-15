"""Playwright test runner — shells out to npx playwright test."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from playspec.config import ExecutionProfile
from playspec.console import console
from playspec.schemas.execution_result import ExecutionResult, TestFailure, FailureType


def run_tests(
    test_files: list[str],
    profile: ExecutionProfile,
    run_id: str,
    test_dir: str,
) -> ExecutionResult:
    """Execute Playwright tests and return structured results.

    Args:
        test_files: Paths to .spec.ts files to execute.
        profile: Execution profile controlling browsers, parallelism, etc.
        run_id: Unique identifier for this run.
        test_dir: Base test directory (for artifact organisation).

    Returns:
        Parsed ExecutionResult with pass/fail counts and failure details.
    """
    run_dir = Path(".playspec") / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    json_report = run_dir / "results.json"

    cmd = _build_command(test_files, profile, run_dir, json_report)

    console.print(f"[dim]Executing: {' '.join(cmd[:6])}…[/dim]")

    import os as _os
    env = {**_os.environ, "PLAYWRIGHT_JSON_OUTPUT_NAME": str(json_report)}

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=profile.parallelism * 600,
            env=env,
        )
    except subprocess.TimeoutExpired:
        console.print("[red]Playwright execution timed out.[/red]")
        return ExecutionResult(run_id=run_id, failures=[
            TestFailure(test_file="*", test_name="*", failure_type=FailureType.TIMEOUT, error_message="Global timeout expired")
        ])
    except FileNotFoundError:
        console.print("[red]npx not found. Install Node.js and Playwright:[/red]  npm i -D @playwright/test")
        return ExecutionResult(run_id=run_id)

    if proc.stderr:
        (run_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")

    if json_report.is_file():
        return _parse_json_report(json_report, run_id, test_files)

    return _parse_exit_code(proc, run_id)


def _build_command(
    test_files: list[str],
    profile: ExecutionProfile,
    run_dir: Path,
    json_report: Path,
) -> list[str]:
    """Assemble the npx playwright test command."""
    cmd = [
        "npx", "playwright", "test",
        *test_files,
        f"--reporter=json",
        f"--output={run_dir / 'artifacts'}",
        f"--workers={profile.parallelism}",
    ]

    for browser in profile.browsers:
        cmd.extend([f"--project={browser}"])

    if profile.headed:
        cmd.append("--headed")

    return cmd


def _parse_json_report(json_path: Path, run_id: str, test_files: list[str] | None = None) -> ExecutionResult:
    """Parse the Playwright JSON reporter output into an ExecutionResult."""
    try:
        data: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[yellow]Warning: failed to parse JSON report: {exc}[/yellow]")
        return ExecutionResult(run_id=run_id)

    failures: list[TestFailure] = []
    passing_test_keys: list[str] = []
    total = 0
    passed = 0
    failed = 0
    skipped = 0
    duration = data.get("stats", {}).get("duration", 0) / 1000.0

    # Build basename → full path lookup from the test_files we ran
    _basename_to_full: dict[str, str] = {}
    for tf in (test_files or []):
        _basename_to_full[Path(tf).name] = tf

    def _resolve_file(reported: str) -> str:
        """Return the full path for a reported file name."""
        if not reported:
            return reported
        if "/" in reported or "\\" in reported:
            return reported
        return _basename_to_full.get(reported, reported)

    def _walk_suite(suite: dict, file_hint: str = "") -> None:
        nonlocal total, passed, failed, skipped
        raw_file = suite.get("file", "") or file_hint
        file_name = _resolve_file(raw_file) or file_hint
        for spec in suite.get("specs", []):
            spec_file = _resolve_file(spec.get("file", "")) or file_name
            test_file = spec_file
            test_name = spec.get("title", "")
            for test in spec.get("tests", []):
                total += 1
                status = test.get("status", "")
                if status == "expected":
                    passed += 1
                    passing_test_keys.append(f"{test_file}::{test_name}")
                elif status == "skipped":
                    skipped += 1
                else:
                    failed += 1
                    results = test.get("results", [{}])
                    last = results[-1] if results else {}
                    error = last.get("error", {})
                    failures.append(TestFailure(
                        test_file=test_file,
                        test_name=test_name,
                        error_message=error.get("message", ""),
                        stack_trace=error.get("stack", ""),
                        artifact_paths=[a.get("path", "") for a in last.get("attachments", [])],
                    ))
        for child in suite.get("suites", []):
            _walk_suite(child, file_name)

    for suite in data.get("suites", []):
        _walk_suite(suite)

    return ExecutionResult(
        run_id=run_id,
        total_tests=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        failures=failures,
        passing_test_keys=passing_test_keys,
        duration_seconds=duration,
    )


def _parse_exit_code(proc: subprocess.CompletedProcess[str], run_id: str) -> ExecutionResult:
    """Fallback: derive a minimal result from the process exit code."""
    if proc.returncode == 0:
        return ExecutionResult(run_id=run_id, total_tests=1, passed=1)
    return ExecutionResult(
        run_id=run_id,
        total_tests=1,
        failed=1,
        failures=[TestFailure(
            test_file="unknown",
            test_name="unknown",
            error_message=proc.stdout[-2000:] if proc.stdout else "Unknown error",
        )],
    )
