"""Copy deck parser — extract UI strings from Markdown, YAML, or JSON."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from playspec.schemas.uts import CopyDeck


def parse_copy_deck(path: Path) -> CopyDeck:
    """Parse a copy deck file into a CopyDeck schema.

    Supports .json, .yaml/.yml, and .md formats.

    Args:
        path: Path to the copy deck file.

    Returns:
        Validated CopyDeck instance.
    """
    suffix = path.suffix.lower()
    content = path.read_text(encoding="utf-8")

    if suffix == ".json":
        data = json.loads(content)
        return CopyDeck.model_validate(data)

    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content)
        return CopyDeck.model_validate(data or {})

    if suffix == ".md":
        return _parse_markdown_deck(content)

    raise ValueError(f"Unsupported copy deck format: {suffix}. Use .json, .yaml, or .md.")


def _parse_markdown_deck(content: str) -> CopyDeck:
    """Parse a Markdown copy deck by section headers."""
    sections: dict[str, dict[str, str]] = {}
    current_section: str | None = None

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip().lower().replace(" ", "_")
            sections.setdefault(current_section, {})
        elif current_section and ":" in stripped:
            key, _, val = stripped.partition(":")
            sections[current_section][key.strip()] = val.strip()

    return CopyDeck(
        error_messages=sections.get("error_messages", {}),
        labels=sections.get("labels", {}),
        placeholders=sections.get("placeholders", {}),
        tooltips=sections.get("tooltips", {}),
        aria_labels=sections.get("aria_labels", {}),
        validation_messages=sections.get("validation_messages", {}),
    )
