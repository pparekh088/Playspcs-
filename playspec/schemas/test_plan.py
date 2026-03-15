"""Test plan schema — the output of the planner agent."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class TestCategory(str, Enum):
    HAPPY_PATH = "happy_path"
    VALIDATION_ERRORS = "validation_errors"
    BOUNDARY_VALUES = "boundary_values"
    ERROR_STATES = "error_states"
    LOADING_STATES = "loading_states"
    EMPTY_STATES = "empty_states"
    PERMISSION_AUTH = "permission_auth"
    RESPONSIVE_VIEWPORT = "responsive_viewport"
    ACCESSIBILITY = "accessibility"
    CONCURRENT_RACE = "concurrent_race"
    CROSS_FLOW = "cross_flow"


class TestScenario(BaseModel):
    """A single test scenario within a suite."""

    title: str
    steps: list[str] = Field(default_factory=list)
    assertions: list[str] = Field(default_factory=list)
    test_data: dict[str, str] = Field(default_factory=dict)
    viewports: list[int] = Field(default_factory=list)


class GapAnalysisItem(BaseModel):
    """An acceptance criterion that is not covered by any planned scenario."""

    acceptance_criterion: str
    reason: str = ""


class TestSuite(BaseModel):
    """A logical group of test scenarios."""

    name: str
    category: TestCategory
    priority: Priority = Priority.P1
    source_ac: list[str] = Field(default_factory=list, description="Acceptance criteria IDs this suite covers")
    scenarios: list[TestScenario] = Field(default_factory=list)


class TestPlan(BaseModel):
    """Complete test plan produced by the planner agent."""

    feature_name: str
    jira_key: str | None = None
    test_suites: list[TestSuite] = Field(default_factory=list)
    gap_analysis: list[GapAnalysisItem] = Field(default_factory=list)
