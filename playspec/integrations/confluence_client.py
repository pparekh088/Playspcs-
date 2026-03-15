"""Confluence integration — fetch pages via Atlassian REST API."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from playspec.config import PlaySpecConfig
from playspec.console import console


def get_page(url_or_id: str, config: PlaySpecConfig) -> dict[str, Any]:
    """Fetch a Confluence page and return a normalised dict.

    Args:
        url_or_id: Confluence page URL or page ID.
        config: PlaySpec config for auth settings.

    Returns:
        Dict with title, body (markdown), child pages, labels.
    """
    token = _resolve_token()
    base_url = os.getenv("CONFLUENCE_BASE_URL", "")
    if not base_url:
        raise RuntimeError("CONFLUENCE_BASE_URL env var is required.")

    page_id = _extract_page_id(url_or_id)
    url = f"{base_url}/wiki/api/v2/pages/{page_id}?body-format=atlas_doc_format"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()

    data = resp.json()
    body_adf = data.get("body", {}).get("atlas_doc_format", {}).get("value", "")

    return {
        "id": page_id,
        "title": data.get("title", ""),
        "body": adf_to_markdown(body_adf) if isinstance(body_adf, (dict, str)) else "",
        "labels": [lb.get("name", "") for lb in data.get("labels", {}).get("results", [])],
    }


def _resolve_token() -> str:
    token = os.getenv("CONFLUENCE_TOKEN", "")
    if not token:
        raise RuntimeError("CONFLUENCE_TOKEN env var is not set.")
    return token


def _extract_page_id(url_or_id: str) -> str:
    """Extract page ID from a Confluence URL or return as-is if already an ID."""
    if url_or_id.isdigit():
        return url_or_id
    m = re.search(r"/pages/(\d+)", url_or_id)
    if m:
        return m.group(1)
    m = re.search(r"pageId=(\d+)", url_or_id)
    if m:
        return m.group(1)
    return url_or_id


def adf_to_markdown(adf: Any) -> str:
    """Convert Atlassian Document Format to markdown.

    Handles: headings, paragraphs, lists, tables, code blocks, inline cards.
    """
    if isinstance(adf, str):
        try:
            import json
            adf = json.loads(adf)
        except (ValueError, TypeError):
            return adf

    if not isinstance(adf, dict):
        return str(adf)

    parts: list[str] = []
    for block in adf.get("content", []):
        parts.append(_convert_block(block))
    return "\n\n".join(p for p in parts if p)


def _convert_block(block: dict) -> str:
    """Convert a single ADF block to markdown."""
    btype = block.get("type", "")

    if btype == "heading":
        level = block.get("attrs", {}).get("level", 1)
        text = _inline_text(block)
        return f"{'#' * level} {text}"

    if btype == "paragraph":
        return _inline_text(block)

    if btype in ("bulletList", "orderedList"):
        items = []
        for i, item in enumerate(block.get("content", [])):
            prefix = "- " if btype == "bulletList" else f"{i+1}. "
            items.append(prefix + _inline_text(item))
        return "\n".join(items)

    if btype == "codeBlock":
        lang = block.get("attrs", {}).get("language", "")
        code = _inline_text(block)
        return f"```{lang}\n{code}\n```"

    if btype == "table":
        rows: list[list[str]] = []
        for row in block.get("content", []):
            cells = [_inline_text(cell) for cell in row.get("content", [])]
            rows.append(cells)
        if not rows:
            return ""
        md = "| " + " | ".join(rows[0]) + " |\n"
        md += "| " + " | ".join("---" for _ in rows[0]) + " |\n"
        for row in rows[1:]:
            md += "| " + " | ".join(row) + " |\n"
        return md.strip()

    return _inline_text(block)


def _inline_text(block: dict) -> str:
    """Extract plain text from inline content nodes."""
    parts: list[str] = []
    for node in block.get("content", []):
        ntype = node.get("type", "")
        if ntype == "text":
            parts.append(node.get("text", ""))
        elif ntype == "inlineCard":
            parts.append(node.get("attrs", {}).get("url", ""))
        elif "content" in node:
            parts.append(_inline_text(node))
    return "".join(parts)
