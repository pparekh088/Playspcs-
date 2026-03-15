"""Tests for git client integration — mocked subprocess."""

import pytest
from unittest.mock import patch, MagicMock

from playspec.integrations.git_client import (
    get_changed_files,
    get_pr_changed_files,
    get_current_branch,
    get_current_sha,
)


class TestGitClient:
    @patch("playspec.integrations.git_client.subprocess.run")
    def test_changed_files(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="src/app.ts\ntests/login.spec.ts\n"
        )
        files = get_changed_files("main")
        assert files == ["src/app.ts", "tests/login.spec.ts"]
        mock_run.assert_called_once()

    @patch("playspec.integrations.git_client.subprocess.run")
    def test_changed_files_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        files = get_changed_files()
        assert files == []

    @patch("playspec.integrations.git_client.subprocess.run")
    def test_current_branch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="feature/login\n")
        assert get_current_branch() == "feature/login"

    @patch("playspec.integrations.git_client.subprocess.run")
    def test_current_sha(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123def456\n")
        assert get_current_sha() == "abc123def456"

    @patch("playspec.integrations.git_client.subprocess.run")
    def test_pr_changed_files(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="file1.ts\nfile2.ts\n"
        )
        files = get_pr_changed_files(42)
        assert files == ["file1.ts", "file2.ts"]
