"""Tests for agent backend abstraction — availability and fallback logic."""

import pytest
from unittest.mock import patch, MagicMock

from playspec.backends import get_backend, CopilotBackend, OpenCodeBackend, ClaudeCodeBackend
from playspec.backends.base import AgentResponse
from playspec.config import PlaySpecConfig, AgentBackendConfig


class TestBackendAvailability:
    @patch("playspec.backends.copilot.shutil.which", return_value="/usr/bin/gh")
    @patch("playspec.backends.copilot.subprocess.run")
    def test_copilot_available(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0)
        b = CopilotBackend()
        assert b.is_available() is True
        assert b.name() == "copilot"

    @patch("playspec.backends.copilot.shutil.which", return_value=None)
    def test_copilot_unavailable(self, mock_which):
        b = CopilotBackend()
        assert b.is_available() is False

    @patch("playspec.backends.opencode.shutil.which", return_value=None)
    def test_opencode_unavailable(self, mock_which):
        b = OpenCodeBackend()
        assert b.is_available() is False

    @patch("playspec.backends.claudecode.shutil.which", return_value=None)
    def test_claudecode_unavailable(self, mock_which):
        b = ClaudeCodeBackend()
        assert b.is_available() is False


class TestBackendResolver:
    @patch("playspec.backends.copilot.CopilotBackend.is_available", return_value=True)
    def test_picks_first_available(self, _):
        config = PlaySpecConfig(
            agent_backend=AgentBackendConfig(priority=["copilot", "opencode"])
        )
        backend = get_backend(config)
        assert backend.name() == "copilot"

    @patch("playspec.backends.copilot.CopilotBackend.is_available", return_value=False)
    @patch("playspec.backends.opencode.OpenCodeBackend.is_available", return_value=True)
    def test_fallback_to_second(self, _, __):
        config = PlaySpecConfig(
            agent_backend=AgentBackendConfig(priority=["copilot", "opencode"])
        )
        backend = get_backend(config)
        assert backend.name() == "opencode"

    @patch("playspec.backends.copilot.CopilotBackend.is_available", return_value=False)
    @patch("playspec.backends.opencode.OpenCodeBackend.is_available", return_value=False)
    @patch("playspec.backends.claudecode.ClaudeCodeBackend.is_available", return_value=False)
    def test_none_available(self, *_):
        config = PlaySpecConfig()
        with pytest.raises(RuntimeError, match="No agent backend"):
            get_backend(config)

    def test_unknown_override(self):
        config = PlaySpecConfig()
        with pytest.raises(RuntimeError, match="Unknown backend"):
            get_backend(config, override="nonexistent")

    @patch("playspec.backends.opencode.OpenCodeBackend.is_available", return_value=False)
    def test_override_unavailable(self, _):
        config = PlaySpecConfig()
        with pytest.raises(RuntimeError, match="not available"):
            get_backend(config, override="opencode")


class TestBackendInvoke:
    @patch("playspec.backends.copilot.subprocess.run")
    @patch("playspec.backends.copilot.shutil.which", return_value="/usr/bin/gh")
    def test_copilot_invoke(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="response text")
        b = CopilotBackend(timeout=5)
        resp = b.invoke("test prompt")
        assert isinstance(resp, AgentResponse)
        assert resp.backend_name == "copilot"
        assert resp.content == "response text"
        assert len(resp.prompt_hash) == 64

    @patch("playspec.backends.copilot.subprocess.run")
    @patch("playspec.backends.copilot.shutil.which", return_value="/usr/bin/gh")
    def test_copilot_uses_explain_not_suggest(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="explained")
        b = CopilotBackend(timeout=5)
        b.invoke("generate a playwright test for login")
        cmd = mock_run.call_args[0][0]
        assert "explain" in cmd, f"Expected 'explain' in command, got: {cmd}"
        assert "suggest" not in cmd, f"'suggest' should not be in command: {cmd}"
