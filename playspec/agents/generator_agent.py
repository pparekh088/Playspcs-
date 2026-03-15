"""Generator agent — produces Playwright .spec.ts files from a TestPlan."""

from __future__ import annotations

import json
from pathlib import Path

from playspec.backends.base import AgentBackend
from playspec.config import PlaySpecConfig
from playspec.console import console
from playspec.prompts.loader import load_prompt
from playspec.schemas.test_plan import TestPlan


def generate_tests(
    plan: TestPlan,
    backend: AgentBackend,
    config: PlaySpecConfig,
    output_dir: Path,
) -> list[str]:
    """Ask the agent to generate test files for the plan.

    Args:
        plan: The test plan to generate from.
        backend: Agent backend.
        config: PlaySpec config for conventions.
        output_dir: Where to write generated files.

    Returns:
        List of generated file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "test_plan": plan.model_dump_json(indent=2),
        "test_dir": config.test_dir,
        "naming_convention": config.naming_convention,
    }

    try:
        from playspec.parsers.codebase_scanner import scan_conventions
        conventions = scan_conventions(config)
        context["conventions"] = conventions.model_dump_json(indent=2)
    except Exception:
        pass

    prompt = load_prompt("generator", context)
    response = backend.invoke(prompt)

    generated: list[str] = []
    try:
        files = json.loads(response.content)
        if isinstance(files, dict):
            for filename, content in files.items():
                path = output_dir / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                generated.append(str(path))
                console.print(f"  [green]✓[/green] {path}")
        elif isinstance(files, list):
            for entry in files:
                if isinstance(entry, dict) and "filename" in entry and "content" in entry:
                    path = output_dir / entry["filename"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(entry["content"], encoding="utf-8")
                    generated.append(str(path))
                    console.print(f"  [green]✓[/green] {path}")
    except (json.JSONDecodeError, Exception) as exc:
        console.print(f"[yellow]Warning: Could not parse generated files: {exc}[/yellow]")
        fallback_path = output_dir / "generated.spec.ts"
        fallback_path.write_text(response.content, encoding="utf-8")
        generated.append(str(fallback_path))

    return generated
