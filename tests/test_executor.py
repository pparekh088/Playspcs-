"""Tests for the Playwright executor — uses mocked subprocess."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from playspec.config import ExecutionProfile
from playspec.executor.runner import run_tests, _parse_json_report
from playspec.executor.artifact_capture import ensure_run_dirs
from playspec.schemas.execution_result import ExecutionResult


@pytest.fixture
def sample_json_report(tmp_path):
    """Create a sample Playwright JSON report."""
    report = {
        "stats": {"duration": 5000},
        "suites": [
            {
                "file": "login.spec.ts",
                "specs": [
                    {
                        "title": "logs in",
                        "file": "login.spec.ts",
                        "tests": [
                            {"status": "expected", "results": [{}]},
                        ],
                    },
                    {
                        "title": "shows error",
                        "file": "login.spec.ts",
                        "tests": [
                            {
                                "status": "unexpected",
                                "results": [{
                                    "error": {
                                        "message": "expect(received).toHaveText(expected)",
                                        "stack": "at test.spec.ts:10",
                                    },
                                    "attachments": [{"path": "screenshots/fail.png"}],
                                }],
                            },
                        ],
                    },
                ],
            }
        ],
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


class TestJsonReportParsing:
    def test_parse_report(self, sample_json_report):
        result = _parse_json_report(sample_json_report, "test-run")
        assert result.run_id == "test-run"
        assert result.total_tests == 2
        assert result.passed == 1
        assert result.failed == 1
        assert len(result.failures) == 1
        assert result.failures[0].test_name == "shows error"
        assert result.duration_seconds == 5.0

    def test_parse_empty_report(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("{}", encoding="utf-8")
        result = _parse_json_report(path, "run-1")
        assert result.total_tests == 0


class TestRunTests:
    @patch("playspec.executor.runner.subprocess.run")
    def test_run_with_mocked_subprocess(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="All tests passed", stderr=""
        )
        profile = ExecutionProfile(browsers=["chromium"], parallelism=2)
        result = run_tests(["test.spec.ts"], profile, "ps-test-run", "tests/e2e")
        assert mock_run.called

    @patch("playspec.executor.runner.subprocess.run")
    def test_run_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=600)
        profile = ExecutionProfile()
        result = run_tests(["test.spec.ts"], profile, "ps-timeout", "tests/e2e")
        assert result.failures[0].error_message == "Global timeout expired"


class TestArtifactCapture:
    def test_ensure_run_dirs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        dirs = ensure_run_dirs("test-run")
        assert dirs["screenshots"].is_dir()
        assert dirs["traces"].is_dir()
        assert dirs["videos"].is_dir()
        assert dirs["dom_snapshots"].is_dir()
