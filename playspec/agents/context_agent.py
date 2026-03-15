"""Context agent — gathers data from JIRA, Confluence, Figma, copy decks and synthesizes a UTS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from playspec.backends.base import AgentBackend
from playspec.config import PlaySpecConfig
from playspec.console import console
from playspec.schemas.uts import UnifiedTestSpec


def gather_context(
    jira_key: str,
    confluence_urls: list[str] | None,
    figma_url: str | None,
    copy_deck_path: Path | None,
    backend: AgentBackend,
    config: PlaySpecConfig,
) -> UnifiedTestSpec:
    """Collect context from all sources and ask the agent to produce a UnifiedTestSpec.

    Each integration failure is handled gracefully — if Figma fails, we continue
    without it and warn the user.
    """
    context_parts: dict[str, str] = {}

    try:
        from playspec.integrations.jira_client import get_issue
        issue = get_issue(jira_key, config)
        context_parts["jira"] = json.dumps(issue, indent=2)
    except Exception as exc:
        console.print(f"[yellow]Warning: JIRA fetch failed: {exc}[/yellow]")

    if confluence_urls:
        try:
            from playspec.integrations.confluence_client import get_page
            pages = []
            for url in confluence_urls:
                pages.append(get_page(url, config))
            context_parts["confluence"] = json.dumps(pages, indent=2)
        except Exception as exc:
            console.print(f"[yellow]Warning: Confluence fetch failed: {exc}[/yellow]")

    if figma_url:
        try:
            from playspec.integrations.figma_client import get_file
            figma_data = get_file(figma_url, config)
            from playspec.parsers.figma_tree import extract_components, extract_text_map, extract_viewports, extract_flows
            context_parts["figma_components"] = json.dumps([c.model_dump() for c in extract_components(figma_data)])
            context_parts["figma_text"] = json.dumps(extract_text_map(figma_data))
            context_parts["figma_viewports"] = json.dumps(extract_viewports(figma_data))
            context_parts["figma_flows"] = json.dumps([f.model_dump() for f in extract_flows(figma_data)])
        except Exception as exc:
            console.print(f"[yellow]Warning: Figma fetch failed: {exc}[/yellow]")

    if copy_deck_path:
        try:
            from playspec.parsers.copy_deck import parse_copy_deck
            deck = parse_copy_deck(copy_deck_path)
            context_parts["copy_deck"] = deck.model_dump_json()
        except Exception as exc:
            console.print(f"[yellow]Warning: Copy deck parse failed: {exc}[/yellow]")

    try:
        from playspec.parsers.codebase_scanner import scan_conventions
        conventions = scan_conventions(config)
        context_parts["codebase_conventions"] = conventions.model_dump_json()
    except Exception as exc:
        console.print(f"[yellow]Warning: Codebase scan failed: {exc}[/yellow]")

    from playspec.prompts.loader import load_prompt
    prompt = load_prompt("context", context_parts)

    response = backend.invoke(prompt)

    try:
        parsed = json.loads(response.content)
        return UnifiedTestSpec.model_validate(parsed)
    except (json.JSONDecodeError, Exception) as exc:
        console.print(f"[yellow]Warning: Could not parse UTS from agent response, using minimal spec: {exc}[/yellow]")
        return UnifiedTestSpec(feature_name=jira_key, jira_key=jira_key)
