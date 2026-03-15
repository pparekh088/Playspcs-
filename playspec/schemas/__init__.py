"""Pydantic schemas for PlaySpec data contracts."""

from playspec.schemas.uts import UnifiedTestSpec, UIComponent, CopyDeck, NavigationFlow
from playspec.schemas.test_plan import TestPlan, TestSuite, TestScenario, GapAnalysisItem
from playspec.schemas.execution_result import ExecutionResult, TestFailure, FailureType
from playspec.schemas.audit_entry import AuditEntry, AuditPhase
from playspec.schemas.manifest_schema import RegressionManifest, SuiteConfig, QuarantineEntry, SuiteHooks
from playspec.schemas.suggested_fix import SuggestedFix, Confidence

__all__ = [
    "UnifiedTestSpec", "UIComponent", "CopyDeck", "NavigationFlow",
    "TestPlan", "TestSuite", "TestScenario", "GapAnalysisItem",
    "ExecutionResult", "TestFailure", "FailureType",
    "AuditEntry", "AuditPhase",
    "RegressionManifest", "SuiteConfig", "QuarantineEntry", "SuiteHooks",
    "SuggestedFix", "Confidence",
]
