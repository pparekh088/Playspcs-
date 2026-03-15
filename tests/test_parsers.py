"""Tests for parsers: copy deck, figma tree, codebase scanner."""

import json
import pytest
import yaml
from pathlib import Path

from playspec.parsers.copy_deck import parse_copy_deck
from playspec.parsers.figma_tree import (
    extract_components,
    extract_text_map,
    extract_viewports,
    extract_flows,
)
from playspec.parsers.codebase_scanner import scan_conventions, CodebaseConventions
from playspec.config import PlaySpecConfig


class TestCopyDeckParser:
    def test_json_deck(self, tmp_path):
        deck = {
            "error_messages": {"invalid": "Invalid input"},
            "labels": {"submit": "Submit"},
        }
        path = tmp_path / "deck.json"
        path.write_text(json.dumps(deck), encoding="utf-8")
        result = parse_copy_deck(path)
        assert result.error_messages["invalid"] == "Invalid input"
        assert result.labels["submit"] == "Submit"

    def test_yaml_deck(self, tmp_path):
        deck = {"error_messages": {"err": "Oops"}, "labels": {"btn": "Click"}}
        path = tmp_path / "deck.yaml"
        path.write_text(yaml.dump(deck), encoding="utf-8")
        result = parse_copy_deck(path)
        assert result.error_messages["err"] == "Oops"

    def test_markdown_deck(self, tmp_path):
        content = "## Error Messages\ninvalid: Invalid input\n\n## Labels\nsubmit: Submit\n"
        path = tmp_path / "deck.md"
        path.write_text(content, encoding="utf-8")
        result = parse_copy_deck(path)
        assert result.error_messages["invalid"] == "Invalid input"
        assert result.labels["submit"] == "Submit"

    def test_unsupported_format(self, tmp_path):
        path = tmp_path / "deck.txt"
        path.write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            parse_copy_deck(path)


class TestFigmaTree:
    @pytest.fixture
    def figma_doc(self):
        return {
            "document": {
                "children": [
                    {
                        "type": "FRAME",
                        "name": "Desktop",
                        "absoluteBoundingBox": {"width": 1440, "height": 900},
                        "children": [
                            {
                                "type": "COMPONENT",
                                "name": "LoginForm",
                                "id": "1:23",
                                "children": [
                                    {"type": "TEXT", "name": "EmailLabel", "characters": "Email address"},
                                    {"type": "TEXT", "name": "PasswordLabel", "characters": "Password"},
                                ],
                            },
                            {
                                "type": "FRAME",
                                "name": "Mobile",
                                "absoluteBoundingBox": {"width": 375, "height": 812},
                                "children": [],
                            },
                        ],
                    }
                ],
            }
        }

    def test_extract_components(self, figma_doc):
        components = extract_components(figma_doc)
        assert len(components) == 1
        assert components[0].name == "LoginForm"
        assert components[0].figma_node_id == "1:23"

    def test_extract_text_map(self, figma_doc):
        text = extract_text_map(figma_doc)
        assert "EmailLabel" in text
        assert text["EmailLabel"] == "Email address"

    def test_extract_viewports(self, figma_doc):
        viewports = extract_viewports(figma_doc)
        assert 1440 in viewports
        assert 375 in viewports

    def test_extract_flows_empty(self, figma_doc):
        flows = extract_flows(figma_doc)
        assert flows == []


class TestCodebaseScanner:
    def test_scan_empty(self, tmp_path):
        config = PlaySpecConfig(
            test_dir=str(tmp_path / "tests/e2e"),
            page_objects_dir=str(tmp_path / "tests/e2e/pages"),
            fixtures_dir=str(tmp_path / "tests/e2e/fixtures"),
        )
        conv = scan_conventions(config)
        assert isinstance(conv, CodebaseConventions)

    def test_scan_with_tests(self, tmp_path):
        test_dir = tmp_path / "tests" / "e2e"
        test_dir.mkdir(parents=True)
        (test_dir / "login-flow.spec.ts").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('login', async ({ page }) => {\n"
            "  await page.locator('[data-testid=\"email\"]').fill('user@test.com');\n"
            "  await expect(page).toHaveURL('/dashboard');\n"
            "});\n"
        )

        pages_dir = tmp_path / "tests" / "e2e" / "pages"
        pages_dir.mkdir(parents=True)
        (pages_dir / "login.ts").write_text("export class LoginPage {}")

        config = PlaySpecConfig(
            test_dir=str(test_dir),
            page_objects_dir=str(pages_dir),
            fixtures_dir=str(tmp_path / "tests/e2e/fixtures"),
        )
        conv = scan_conventions(config)
        assert "login" in conv.page_objects
        assert conv.selector_strategy == "data-testid"
        assert conv.assertion_style == "expect"
