"""Planner agent — produces a TestPlan from a UnifiedTestSpec."""

from __future__ import annotations

import json

from playspec.backends.base import AgentBackend
from playspec.console import console
from playspec.prompts.loader import load_prompt
from playspec.schemas.test_plan import TestPlan
from playspec.schemas.uts import UnifiedTestSpec


def plan_tests(uts: UnifiedTestSpec, backend: AgentBackend) -> TestPlan:
    """Ask the agent backend to produce a comprehensive test plan.

    Args:
        uts: The Unified Test Specification.
        backend: The agent backend to use.

    Returns:
        A validated TestPlan.
    """
    context = {"uts": uts.model_dump_json(indent=2)}
    prompt = load_prompt("planner", context)
    response = backend.invoke(prompt)

    try:
        parsed = json.loads(response.content)
        return TestPlan.model_validate(parsed)
    except (json.JSONDecodeError, Exception) as exc:
        console.print(f"[yellow]Warning: Could not parse TestPlan from agent response: {exc}[/yellow]")
        return TestPlan(feature_name=uts.feature_name, jira_key=uts.jira_key)
