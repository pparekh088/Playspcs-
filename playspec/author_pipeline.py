"""Author mode pipeline — AI-assisted test generation from JIRA, Confluence, Figma."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from playspec.console import console


def run_author(
    jira_key: str,
    confluence_urls: list[str] | None = None,
    figma_url: str | None = None,
    copy_deck_path: Path | None = None,
    output_dir: Path | None = None,
    backend_name: str | None = None,
    max_retries: int = 3,
    skip_repair: bool = False,
    apply_fixes_run_id: str | None = None,
) -> None:
    """Execute the full author pipeline: context → plan → generate → execute → repair.

    Args:
        jira_key: JIRA ticket key (required).
        confluence_urls: Optional Confluence page URLs for additional context.
        figma_url: Optional Figma file URL.
        copy_deck_path: Optional path to a copy deck file.
        output_dir: Directory to write generated test files.
        backend_name: Force a specific agent backend.
        max_retries: Maximum repair attempts per failing test.
        skip_repair: If True, skip the repair loop.
        apply_fixes_run_id: Apply suggested fixes from an earlier regression run.
    """
    from playspec.config import load_config
    from playspec.backends import get_backend
    from playspec.agents.context_agent import gather_context
    from playspec.agents.planner_agent import plan_tests
    from playspec.agents.generator_agent import generate_tests
    from playspec.agents.repair_agent import repair_tests
    from playspec.executor.runner import run_tests as execute_tests
    from playspec.manifest import load_manifest
    from playspec.run_id import generate_run_id
    from playspec.audit import create_audit, save_audit
    from playspec.schemas.audit_entry import AuditResults, RunMode

    config = load_config()
    profile = config.get_profile("local-dev")
    backend = get_backend(config, override=backend_name)
    run_id = generate_run_id()

    console.print(Panel(f"[bold]Author Mode[/bold] — {jira_key}\nBackend: {backend.name()}\nRun: {run_id}", expand=False))

    with console.status("[bold blue]Gathering context…"):
        uts = gather_context(
            jira_key=jira_key,
            confluence_urls=confluence_urls,
            figma_url=figma_url,
            copy_deck_path=copy_deck_path,
            backend=backend,
            config=config,
        )
    console.print(f"[green]✓[/green] Unified Test Spec assembled: {uts.feature_name}")

    with console.status("[bold blue]Planning tests…"):
        test_plan = plan_tests(uts=uts, backend=backend)
    console.print(f"[green]✓[/green] Test plan: {len(test_plan.test_suites)} suites, {sum(len(s.scenarios) for s in test_plan.test_suites)} scenarios")

    with console.status("[bold blue]Generating test files…"):
        generated_files = generate_tests(
            plan=test_plan,
            backend=backend,
            config=config,
            output_dir=output_dir or Path(config.test_dir),
        )
    console.print(f"[green]✓[/green] Generated {len(generated_files)} test file(s)")

    with console.status("[bold blue]Executing generated tests…"):
        result = execute_tests(generated_files, profile, run_id, config.test_dir)

    console.print(f"Results: ✅ {result.passed}  ❌ {result.failed}  ⏭ {result.skipped}")

    if result.failed > 0 and not skip_repair:
        console.print("[bold]Starting repair loop…[/bold]")
        repair_tests(
            result=result,
            backend=backend,
            config=config,
            max_retries=max_retries,
            run_id=run_id,
        )

    audit = create_audit(
        run_id=run_id,
        mode=RunMode.AUTHOR,
        profile="local-dev",
        suite=jira_key,
        resolved_tests=len(generated_files),
        results=AuditResults(passed=result.passed, failed=result.failed, skipped=result.skipped),
        failures=[f.test_name for f in result.failures],
        duration_seconds=result.duration_seconds,
        agent_backend_used=backend.name(),
    )
    save_audit(audit)

    console.print(Panel(f"[bold green]Author pipeline complete.[/bold green]\nAudit: {run_id}", expand=False))


def run_plan(
    jira_key: str,
    confluence_urls: list[str] | None = None,
    figma_url: str | None = None,
    copy_deck_path: Path | None = None,
    backend_name: str | None = None,
    export_json: Path | None = None,
) -> None:
    """Run context gathering and planning only — no generation or execution.

    Args:
        jira_key: JIRA ticket key.
        confluence_urls: Optional Confluence page URLs.
        figma_url: Optional Figma file URL.
        copy_deck_path: Optional copy deck path.
        backend_name: Override agent backend.
        export_json: If provided, write the plan as JSON to this path.
    """
    from playspec.config import load_config
    from playspec.backends import get_backend
    from playspec.agents.context_agent import gather_context
    from playspec.agents.planner_agent import plan_tests

    config = load_config()
    backend = get_backend(config, override=backend_name)

    with console.status("[bold blue]Gathering context…"):
        uts = gather_context(
            jira_key=jira_key,
            confluence_urls=confluence_urls,
            figma_url=figma_url,
            copy_deck_path=copy_deck_path,
            backend=backend,
            config=config,
        )

    with console.status("[bold blue]Planning tests…"):
        test_plan = plan_tests(uts=uts, backend=backend)

    table = Table(title=f"Test Plan for {jira_key}")
    table.add_column("Suite")
    table.add_column("Category")
    table.add_column("Priority")
    table.add_column("Scenarios", justify="right")

    for suite in test_plan.test_suites:
        table.add_row(suite.name, suite.category.value, suite.priority.value, str(len(suite.scenarios)))

    console.print(table)

    if test_plan.gap_analysis:
        console.print("\n[bold yellow]Gap Analysis:[/bold yellow]")
        for gap in test_plan.gap_analysis:
            console.print(f"  ⚠ {gap.acceptance_criterion}: {gap.reason}")

    if export_json:
        export_json.write_text(test_plan.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]✓[/green] Plan exported to {export_json}")
