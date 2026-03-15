"""Tests for Pydantic schemas — validation, defaults, serialization."""

import pytest
from pydantic import ValidationError

from playspec.schemas.uts import UnifiedTestSpec, UIComponent, CopyDeck, NavigationFlow, ExistingPattern
from playspec.schemas.test_plan import TestPlan, TestSuite, TestScenario, Priority, TestCategory, GapAnalysisItem
from playspec.schemas.execution_result import ExecutionResult, TestFailure, FailureType
from playspec.schemas.audit_entry import AuditEntry, AuditPhase, AuditResults, RunMode
from playspec.schemas.manifest_schema import RegressionManifest, SuiteConfig, SuiteHooks, GlobalDefaults
from playspec.schemas.suggested_fix import SuggestedFix, Confidence


class TestUnifiedTestSpec:
    def test_minimal(self):
        uts = UnifiedTestSpec(feature_name="Login")
        assert uts.feature_name == "Login"
        assert uts.acceptance_criteria == []
        assert uts.ui_components == []

    def test_full(self):
        uts = UnifiedTestSpec(
            feature_name="Checkout",
            jira_key="PROJ-42",
            acceptance_criteria=["User can complete payment"],
            business_rules=["Tax calculated at checkout"],
            ui_components=[UIComponent(name="PaymentForm", states=["default", "loading"])],
            copy=CopyDeck(error_messages={"card_declined": "Card was declined"}),
            navigation_flows=[NavigationFlow(name="Cart to Payment", steps=["Click checkout"])],
            viewports=[375, 1440],
            existing_patterns=ExistingPattern(page_objects=["CheckoutPage"]),
        )
        assert uts.jira_key == "PROJ-42"
        assert len(uts.ui_components) == 1
        assert uts.copy_deck.error_messages["card_declined"] == "Card was declined"
        assert uts.viewports == [375, 1440]

    def test_serialization_roundtrip(self):
        uts = UnifiedTestSpec(feature_name="Test", jira_key="X-1")
        data = uts.model_dump()
        restored = UnifiedTestSpec.model_validate(data)
        assert restored.feature_name == "Test"


class TestTestPlan:
    def test_minimal(self):
        plan = TestPlan(feature_name="Login")
        assert plan.test_suites == []
        assert plan.gap_analysis == []

    def test_with_suites(self):
        plan = TestPlan(
            feature_name="Login",
            jira_key="PROJ-1",
            test_suites=[
                TestSuite(
                    name="Happy Path",
                    category=TestCategory.HAPPY_PATH,
                    priority=Priority.P0,
                    scenarios=[TestScenario(title="logs in", steps=["goto /login"])],
                )
            ],
            gap_analysis=[GapAnalysisItem(acceptance_criterion="AC1", reason="not covered")],
        )
        assert len(plan.test_suites) == 1
        assert plan.test_suites[0].priority == Priority.P0

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            TestSuite(name="x", category="nonexistent", priority="P0")


class TestExecutionResult:
    def test_defaults(self):
        r = ExecutionResult(run_id="ps-test")
        assert r.total_tests == 0
        assert r.failures == []

    def test_with_failures(self):
        r = ExecutionResult(
            run_id="ps-test",
            total_tests=3,
            passed=2,
            failed=1,
            failures=[TestFailure(
                test_file="login.spec.ts",
                test_name="logs in",
                failure_type=FailureType.SELECTOR_NOT_FOUND,
                error_message="locator not found",
            )],
            duration_seconds=12.5,
        )
        assert r.failed == 1
        assert r.failures[0].failure_type == FailureType.SELECTOR_NOT_FOUND


class TestAuditEntry:
    def test_minimal(self):
        a = AuditEntry(run_id="ps-test", mode=RunMode.REGRESSION)
        assert a.mode == RunMode.REGRESSION
        assert a.results.passed == 0

    def test_with_phases(self):
        a = AuditEntry(
            run_id="ps-test",
            mode=RunMode.AUTHOR,
            phases=[AuditPhase(name="context", duration_seconds=2.5, backend_used="copilot")],
        )
        assert len(a.phases) == 1
        assert a.phases[0].backend_used == "copilot"


class TestRegressionManifest:
    def test_empty(self):
        m = RegressionManifest()
        assert m.suites == {}
        assert m.quarantine == []

    def test_with_suites(self):
        m = RegressionManifest(
            suites={
                "smoke": SuiteConfig(
                    description="Critical path",
                    timeout_minutes=10,
                    tags=["smoke", "p0"],
                    blocking=True,
                )
            },
            quarantine=["tests/flaky.spec.ts"],
        )
        assert m.suites["smoke"].blocking is True
        assert "tests/flaky.spec.ts" in m.quarantine

    def test_hooks(self):
        m = RegressionManifest(
            hooks={"checkout": SuiteHooks(setup="seed.sh", teardown="cleanup.sh")}
        )
        assert m.hooks["checkout"].setup == "seed.sh"


class TestSuggestedFix:
    def test_creation(self):
        fix = SuggestedFix(
            test_file="login.spec.ts",
            test_name="logs in",
            failure_type=FailureType.TIMEOUT,
            confidence=Confidence.LOW,
            proposed_patch="// add wait",
        )
        assert fix.confidence == Confidence.LOW
