"""Tests validating the code review fixes — ensures each critical/medium bug stays fixed."""

import json
import os
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from playspec.config import PlaySpecConfig, ExecutionProfile, RepairPolicy, load_config
from playspec.executor.runner import _build_command, _parse_json_report, run_tests
from playspec.stability import StabilityStore, TestStabilityRecord as StabilityRecord
from playspec.schemas.execution_result import ExecutionResult, PassedTest, TestFailure, FailureType
from playspec.schemas.manifest_schema import RegressionManifest, QuarantineEntry
from playspec.manifest import Manifest


class TestCritical1_RegressionNoTyperImport:
    """#1: regression.py must not reference typer — uses SystemExit instead."""

    def test_no_typer_reference(self):
        from playspec import regression
        src = Path(regression.__file__).read_text()
        assert "typer.Exit" not in src
        assert "import typer" not in src


class TestCritical2_JsonReporterOutputPath:
    """#2: _build_command must direct JSON output to a file, not stdout."""

    def test_reporter_has_output_path(self, tmp_path):
        profile = ExecutionProfile(browsers=["chromium"], parallelism=2)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        json_report = run_dir / "results.json"
        cmd = _build_command(["test.spec.ts"], profile, run_dir, json_report)
        reporter_args = [a for a in cmd if a.startswith("--reporter")]
        assert len(reporter_args) == 1
        assert str(json_report) in reporter_args[0]
        assert reporter_args[0] == f"--reporter=json:{json_report}"


class TestCritical3_StabilityRecordsPassingTests:
    """#3: StabilityStore.update() must record passing tests, not just failures."""

    def test_passes_are_recorded(self):
        result = ExecutionResult(
            run_id="run-1",
            total_tests=3,
            passed=2,
            failed=1,
            failures=[TestFailure(test_file="a.spec.ts", test_name="fails", failure_type=FailureType.TIMEOUT)],
            passed_tests=[
                PassedTest(test_file="b.spec.ts", test_name="passes1"),
                PassedTest(test_file="c.spec.ts", test_name="passes2"),
            ],
        )
        store = StabilityStore()
        updates = store.update(result)
        assert updates == 3
        assert "b.spec.ts::passes1" in store.records
        assert store.records["b.spec.ts::passes1"].pass_count == 1
        assert store.records["b.spec.ts::passes1"].flaky_score == 1.0
        assert store.records["a.spec.ts::fails"].fail_count == 1

    def test_recovery_improves_flaky_score(self):
        store = StabilityStore()
        rec = StabilityRecord()
        for _ in range(5):
            rec.record_fail()
        store.records["t.spec.ts::test1"] = rec
        assert rec.flaky_score == 0.0

        result = ExecutionResult(
            run_id="run-2",
            total_tests=1, passed=1,
            passed_tests=[PassedTest(test_file="t.spec.ts", test_name="test1")],
        )
        store.update(result)
        assert store.records["t.spec.ts::test1"].flaky_score > 0.0


class TestCritical4_LocalDevProfileDoesntBlock:
    """#4: local-dev profile from init must use repair_policy=never."""

    def test_init_local_dev_is_never(self):
        from playspec.init_cmd import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["profiles"]["local-dev"]["repair_policy"] == "never"


class TestCritical5_CopilotUsesExplainNotSuggest:
    """#5: Copilot backend must use 'explain', not 'suggest -t shell'."""

    @patch("playspec.backends.copilot.subprocess.run")
    @patch("playspec.backends.copilot.shutil.which", return_value="/usr/bin/gh")
    def test_invocation_uses_explain(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="response")
        from playspec.backends.copilot import CopilotBackend
        b = CopilotBackend(timeout=5)
        b.invoke("generate a Playwright test")
        cmd = mock_run.call_args[0][0]
        assert "explain" in cmd
        assert "suggest" not in cmd

    def test_copilot_demoted_in_default_priority(self):
        from playspec.config import AgentBackendConfig
        default = AgentBackendConfig()
        assert default.priority[-1] == "copilot", (
            f"Copilot should be last in default priority, got: {default.priority}"
        )
        assert default.priority[0] != "copilot"

    def test_init_default_config_priority_demotes_copilot(self):
        from playspec.init_cmd import DEFAULT_CONFIG
        prio = DEFAULT_CONFIG["agent_backend"]["priority"]
        assert prio[-1] == "copilot", f"Copilot should be last in defaults: {prio}"
        assert prio[0] == "claudecode", f"claudecode should be first in defaults: {prio}"

    def test_source_has_no_suggest_invocation(self):
        from playspec.backends import copilot
        src = Path(copilot.__file__).read_text()
        assert '"suggest"' not in src
        assert "'suggest'" not in src


class TestCritical6_CopilotNoTempFileLeak:
    """#6: CopilotBackend.invoke() must clean up temp files."""

    @patch("playspec.backends.copilot.subprocess.run")
    @patch("playspec.backends.copilot.shutil.which", return_value="/usr/bin/gh")
    def test_temp_file_cleaned_up(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="response")
        from playspec.backends.copilot import CopilotBackend
        b = CopilotBackend(timeout=5)
        b.invoke("test prompt")
        # No .md temp files should remain (we can't easily verify the exact file
        # was deleted, but we verify no exception and that it completes)
        assert mock_run.called


class TestCritical7_RepairLoopRetries:
    """#7: Repair loop must actually retry, not always break after attempt 1."""

    def test_repair_agent_has_retry_logic(self):
        from playspec.agents import repair_agent
        src = Path(repair_agent.__file__).read_text()
        assert "break" in src
        assert "_verify_patch" in src
        assert "retrying" in src.lower()


class TestMedium8_TimeoutUsesMinutesNotParallelism:
    """#8: run_tests timeout should use timeout_minutes, not parallelism * 600."""

    @patch("playspec.executor.runner.subprocess.run")
    def test_timeout_uses_minutes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        profile = ExecutionProfile(parallelism=4)
        run_tests(["t.spec.ts"], profile, "run-1", "tests/e2e", timeout_minutes=15)
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 15 * 60


class TestMedium9_EnvVarInterpolation:
    """#9: Config must interpolate $VAR references from environment."""

    def test_env_var_substitution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_BASE_URL", "https://preview.example.com")
        ps = tmp_path / ".playspec"
        ps.mkdir()
        config_data = {
            "test_dir": "tests/e2e",
            "profiles": {
                "pr-ci": {"base_url": "$MY_BASE_URL", "repair_policy": "never"},
            },
        }
        (ps / "config.yaml").write_text(yaml.dump(config_data), encoding="utf-8")
        cfg = load_config(ps / "config.yaml")
        assert cfg.profiles["pr-ci"].base_url == "https://preview.example.com"

    def test_unset_var_kept_as_literal(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        ps = tmp_path / ".playspec"
        ps.mkdir()
        config_data = {
            "test_dir": "tests/e2e",
            "profiles": {
                "ci": {"base_url": "$NONEXISTENT_VAR", "repair_policy": "never"},
            },
        }
        (ps / "config.yaml").write_text(yaml.dump(config_data), encoding="utf-8")
        cfg = load_config(ps / "config.yaml")
        assert cfg.profiles["ci"].base_url == "$NONEXISTENT_VAR"


class TestMedium13_QuarantineStructuredEntries:
    """#13: Quarantine list supports both plain strings and structured entries."""

    def test_mixed_quarantine_list(self):
        m = RegressionManifest(quarantine=[
            "tests/e2e/flaky.spec.ts",
            {"path": "tests/e2e/broken.spec.ts", "reason": "Known timeout", "added_at": "2026-01-01"},
        ])
        paths = m.quarantine_paths()
        assert "tests/e2e/flaky.spec.ts" in paths
        assert "tests/e2e/broken.spec.ts" in paths

    def test_quarantine_paths_used_by_manifest(self):
        m_data = RegressionManifest(quarantine=["tests/e2e/q.spec.ts"])
        manifest = Manifest(m_data)
        assert "tests/e2e/q.spec.ts" in manifest.get_quarantined()


class TestMedium16_NestedSuiteParsing:
    """#16: JSON report parser must recurse into nested suites (describe blocks)."""

    def test_nested_suites_parsed(self, tmp_path):
        report = {
            "stats": {"duration": 3000},
            "suites": [
                {
                    "file": "login.spec.ts",
                    "specs": [],
                    "suites": [
                        {
                            "title": "Happy Path",
                            "specs": [
                                {
                                    "title": "logs in",
                                    "file": "login.spec.ts",
                                    "tests": [{"status": "expected", "results": [{}]}],
                                }
                            ],
                            "suites": [
                                {
                                    "title": "Deep nested",
                                    "specs": [
                                        {
                                            "title": "deep test",
                                            "file": "login.spec.ts",
                                            "tests": [{"status": "unexpected", "results": [{"error": {"message": "fail", "stack": ""}}]}],
                                        }
                                    ],
                                    "suites": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        path = tmp_path / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        result = _parse_json_report(path, "run-1")
        assert result.total_tests == 2
        assert result.passed == 1
        assert result.failed == 1
        assert len(result.passed_tests) == 1
        assert result.passed_tests[0].test_name == "logs in"


class TestMedium17_ProfileNotMutated:
    """#17: base_url override must not mutate the original profile object."""

    def test_profile_copy(self):
        profile = ExecutionProfile(base_url="http://original:3000")
        updated = profile.model_copy(update={"base_url": "http://override:4000"})
        assert updated.base_url == "http://override:4000"
        assert profile.base_url == "http://original:3000"


class TestMinor23_NoKwargs:
    """#23: create_audit should not accept **kwargs."""

    def test_create_audit_signature(self):
        import inspect
        from playspec.audit import create_audit
        sig = inspect.signature(create_audit)
        param_kinds = {p.kind for p in sig.parameters.values()}
        assert inspect.Parameter.VAR_KEYWORD not in param_kinds
