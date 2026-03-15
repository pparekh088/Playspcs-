"""Implementation of `playspec init` — scaffold .playspec/ directory."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml
from rich.panel import Panel

from playspec.console import console

DEFAULT_CONFIG: dict = {
    "test_dir": "tests/e2e",
    "page_objects_dir": "tests/e2e/pages",
    "fixtures_dir": "tests/e2e/fixtures",
    "naming_convention": "kebab-case",
    "max_retries": 3,
    "agent_backend": {
        "priority": ["copilot", "opencode", "claudecode"],
        "copilot": {"mode": "cli"},
        "opencode": {"mode": "cli"},
        "claudecode": {"mode": "cli"},
    },
    "profiles": {
        "local-dev": {
            "base_url": "http://localhost:3000",
            "browsers": ["chromium"],
            "parallelism": 2,
            "headed": True,
            "repair_policy": "propose",
            "artifact_retention": "7d",
            "generation_allowed": True,
        },
        "pr-ci": {
            "base_url": "$PREVIEW_URL",
            "browsers": ["chromium"],
            "parallelism": 4,
            "headed": False,
            "repair_policy": "never",
            "artifact_retention": "30d",
            "generation_allowed": False,
            "suggested_fixes": True,
        },
        "nightly": {
            "base_url": "https://staging.example.com",
            "browsers": ["chromium", "firefox", "webkit"],
            "parallelism": 8,
            "headed": False,
            "repair_policy": "never",
            "artifact_retention": "90d",
            "generation_allowed": False,
            "flaky_detection": True,
        },
        "release": {
            "base_url": "https://uat.example.com",
            "browsers": ["chromium", "firefox", "webkit"],
            "parallelism": 4,
            "headed": False,
            "repair_policy": "never",
            "artifact_retention": "365d",
            "generation_allowed": False,
            "blocking": True,
        },
    },
    "audit": {
        "enabled": True,
        "output_dir": ".playspec/audits",
        "retention_days": 90,
        "include_prompts": True,
        "include_responses": True,
    },
    "auth": {
        "jira": "cli",
        "confluence": "cli",
        "figma": "env",
    },
}

DEFAULT_MANIFEST: dict = {
    "suites": {
        "smoke": {
            "description": "Critical path validation, runs on every PR",
            "timeout_minutes": 10,
            "tags": ["smoke", "p0"],
            "blocking": True,
            "browsers": ["chromium"],
            "parallelism": 4,
        },
        "full": {
            "description": "Complete regression, runs nightly",
            "timeout_minutes": 60,
            "tags": ["regression"],
            "blocking": False,
            "browsers": ["chromium", "firefox", "webkit"],
            "parallelism": 8,
        },
    },
    "quarantine": [],
    "hooks": {},
}


def _detect_backends() -> list[str]:
    """Return names of agent backends available on PATH."""
    checks = {
        "copilot": ["gh", "copilot", "--version"],
        "opencode": ["opencode", "--version"],
        "claudecode": ["claude", "--version"],
    }
    available: list[str] = []
    for name, cmd in checks.items():
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, capture_output=True, timeout=10, check=False)
                available.append(name)
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
    return available


def _detect_test_dir(root: Path | None = None) -> str | None:
    """Look for common Playwright test directories."""
    base = root or Path.cwd()
    candidates = [
        "tests/e2e",
        "e2e",
        "test/e2e",
        "tests",
        "test",
    ]
    for c in candidates:
        if (base / c).is_dir():
            return c
    return None


def _detect_playwright_config(root: Path | None = None) -> bool:
    """Check if a Playwright config file exists in cwd."""
    base = root or Path.cwd()
    names = ["playwright.config.ts", "playwright.config.js", "playwright.config.mjs"]
    return any((base / n).is_file() for n in names)


def run_init(project_dir: Path | None = None) -> None:
    """Create .playspec/ scaffolding in the target directory.

    Args:
        project_dir: Root of the project.  Defaults to cwd.
    """
    root = project_dir or Path.cwd()
    ps_dir = root / ".playspec"
    config_path = ps_dir / "config.yaml"
    manifest_path = ps_dir / "regression-manifest.yaml"

    if config_path.is_file():
        console.print("[yellow]⚠ .playspec/config.yaml already exists — skipping config generation.[/yellow]")
    else:
        config = dict(DEFAULT_CONFIG)
        detected_dir = _detect_test_dir(root)
        if detected_dir:
            config["test_dir"] = detected_dir
            console.print(f"[dim]Detected test directory:[/dim] {detected_dir}")

        backends = _detect_backends()
        if backends:
            config["agent_backend"]["priority"] = backends
            console.print(f"[dim]Detected agent backends:[/dim] {', '.join(backends)}")

        if _detect_playwright_config(root):
            console.print("[dim]Detected existing Playwright config.[/dim]")

        ps_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False), encoding="utf-8")
        console.print(f"[green]✓[/green] Created {config_path.relative_to(root)}")

    if manifest_path.is_file():
        console.print("[yellow]⚠ .playspec/regression-manifest.yaml already exists — skipping.[/yellow]")
    else:
        ps_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            yaml.dump(DEFAULT_MANIFEST, default_flow_style=False, sort_keys=False), encoding="utf-8"
        )
        console.print(f"[green]✓[/green] Created {manifest_path.relative_to(root)}")

    (ps_dir / "audits").mkdir(parents=True, exist_ok=True)
    (ps_dir / "runs").mkdir(parents=True, exist_ok=True)
    (ps_dir / "stability.json").touch(exist_ok=True)

    console.print(
        Panel(
            "[bold green]PlaySpec initialized.[/bold green]\n\n"
            "Next steps:\n"
            "  1. Review .playspec/config.yaml\n"
            "  2. Edit .playspec/regression-manifest.yaml to register your suites\n"
            "  3. Run [bold]playspec regress --suite smoke[/bold]",
            title="playspec init",
            expand=False,
        )
    )
