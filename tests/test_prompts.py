"""Tests for prompt template loading."""

import pytest
from pathlib import Path

from playspec.prompts.loader import load_prompt


class TestPromptLoader:
    def test_load_context_prompt(self):
        prompt = load_prompt("context", {
            "jira": '{"key": "PROJ-1"}',
            "confluence": "[]",
            "figma_components": "[]",
            "figma_text": "{}",
            "figma_viewports": "[]",
            "figma_flows": "[]",
            "copy_deck": "{}",
            "codebase_conventions": "{}",
        })
        assert "QA engineer" in prompt
        assert "PROJ-1" in prompt

    def test_load_planner_prompt(self):
        prompt = load_prompt("planner", {"uts": '{"feature_name": "Login"}'})
        assert "senior QA lead" in prompt
        assert "Login" in prompt

    def test_load_generator_prompt(self):
        prompt = load_prompt("generator", {
            "test_plan": "{}",
            "conventions": "{}",
            "test_dir": "tests/e2e",
            "naming_convention": "kebab-case",
        })
        assert "senior SDET" in prompt

    def test_load_repair_prompt(self):
        prompt = load_prompt("repair", {
            "test_file": "login.spec.ts",
            "test_name": "logs in",
            "error_message": "timeout",
            "stack_trace": "at line 10",
            "original_code": "test('logs in', () => {})",
        })
        assert "debugging" in prompt
        assert "login.spec.ts" in prompt

    def test_missing_template(self):
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent")
