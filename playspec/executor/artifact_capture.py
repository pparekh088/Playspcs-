"""Artifact capture — organise screenshots, traces, videos, and snapshots per run."""

from __future__ import annotations

from pathlib import Path


def ensure_run_dirs(run_id: str) -> dict[str, Path]:
    """Create and return the standard artifact directories for a run.

    Returns:
        Dict mapping artifact type to its directory path.
    """
    base = Path(".playspec") / "runs" / run_id
    dirs: dict[str, Path] = {
        "root": base,
        "screenshots": base / "screenshots",
        "traces": base / "traces",
        "videos": base / "videos",
        "dom_snapshots": base / "dom_snapshots",
        "a11y_snapshots": base / "a11y_snapshots",
        "har": base / "har",
        "logs": base / "logs",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def playwright_config_args(run_id: str) -> list[str]:
    """Return extra CLI args to configure Playwright artifact capture.

    These are appended to the npx playwright test invocation.
    """
    dirs = ensure_run_dirs(run_id)
    return [
        f"--output={dirs['root'] / 'artifacts'}",
        "--trace=on-first-retry",
        "--screenshot=only-on-failure",
    ]
