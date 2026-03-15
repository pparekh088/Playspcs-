"""JIRA integration — fetch issues via Atlassian REST API."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from playspec.config import AuthMethod, PlaySpecConfig
from playspec.console import console

AC_HEADER_RE = re.compile(r"(?:^|\n)#+\s*acceptance\s+criteria", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"[-*]\s*\[[ x]?\]\s*(.+)", re.IGNORECASE)


def get_issue(key: str, config: PlaySpecConfig) -> dict[str, Any]:
    """Fetch a JIRA issue and return a normalised dict.

    Args:
        key: JIRA issue key (e.g. PROJ-1234).
        config: PlaySpec config for auth method.

    Returns:
        Dict with summary, description, acceptance_criteria, labels, etc.
    """
    token = _resolve_token(config)
    base_url = os.getenv("JIRA_BASE_URL", "")
    if not base_url:
        raise RuntimeError("JIRA_BASE_URL env var is required. Example: https://yoursite.atlassian.net")

    url = f"{base_url}/rest/api/3/issue/{key}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()

    data = resp.json()
    fields = data.get("fields", {})
    description = _extract_text(fields.get("description", ""))

    return {
        "key": key,
        "summary": fields.get("summary", ""),
        "description": description,
        "acceptance_criteria": _parse_acceptance_criteria(description),
        "labels": fields.get("labels", []),
        "components": [c.get("name", "") for c in fields.get("components", [])],
        "linked_issues": [link.get("outwardIssue", {}).get("key", "") for link in fields.get("issuelinks", []) if "outwardIssue" in link],
        "subtasks": [st.get("key", "") for st in fields.get("subtasks", [])],
    }


def _resolve_token(config: PlaySpecConfig) -> str:
    """Get JIRA auth token based on configured method."""
    token = os.getenv("JIRA_TOKEN", "")
    if not token:
        raise RuntimeError(
            "JIRA_TOKEN env var is not set. "
            "Set it or configure auth.jira=cli and run 'atlas auth login'."
        )
    return token


def _extract_text(desc: Any) -> str:
    """Convert Atlassian Document Format (or plain string) to text."""
    if isinstance(desc, str):
        return desc
    if isinstance(desc, dict):
        parts: list[str] = []
        for block in desc.get("content", []):
            for inline in block.get("content", []):
                text = inline.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _parse_acceptance_criteria(description: str) -> list[str]:
    """Extract acceptance criteria from a description (header or checkbox patterns)."""
    criteria: list[str] = []

    header_match = AC_HEADER_RE.search(description)
    if header_match:
        section = description[header_match.end():]
        next_header = re.search(r"\n#+\s", section)
        if next_header:
            section = section[:next_header.start()]
        for m in CHECKBOX_RE.finditer(section):
            criteria.append(m.group(1).strip())

    if not criteria:
        for m in CHECKBOX_RE.finditer(description):
            criteria.append(m.group(1).strip())

    return criteria
