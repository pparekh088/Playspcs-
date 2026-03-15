"""Prompt template loader — reads .md templates and fills variables."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str, variables: dict[str, Any] | None = None) -> str:
    """Load a prompt template and substitute {{ variable }} placeholders.

    Args:
        name: Template name (without .md extension).
        variables: Dict of values to inject into the template.

    Returns:
        The rendered prompt string.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {path}")

    template = path.read_text(encoding="utf-8")

    if variables:
        for key, value in variables.items():
            placeholder = "{{ " + key + " }}"
            template = template.replace(placeholder, str(value))
            placeholder_no_space = "{{" + key + "}}"
            template = template.replace(placeholder_no_space, str(value))

    return template
