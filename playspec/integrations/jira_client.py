"""JIRA integration — fetch issues and post results via Atlassian REST API."""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
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


def post_test_results(
    jira_key: str,
    run_id: str,
    test_file: str,
    passed: int,
    failed: int,
    skipped: int,
    total: int,
    duration_seconds: float,
    failures: list[dict[str, str]] | None = None,
) -> bool:
    """Post a test result summary as a comment on a JIRA issue.

    Uses Basic auth (email:api-token) for Jira Cloud.

    Returns True if the comment was posted successfully.
    """
    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")

    if not all([base_url, email, api_token]):
        console.print("[dim]Skipping Jira comment — JIRA_BASE_URL, JIRA_EMAIL, or JIRA_API_TOKEN not set.[/dim]")
        return False

    credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    url = f"{base_url}/rest/api/3/issue/{jira_key}/comment"
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    status_emoji = "PASSED" if failed == 0 else "FAILED"
    body = _build_result_comment_adf(
        run_id=run_id,
        test_file=test_file,
        status=status_emoji,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=total,
        duration=duration_seconds,
        failures=failures or [],
    )

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json={"body": body})
            resp.raise_for_status()
        console.print(f"  [green]Posted results to {jira_key}[/green]")
        return True
    except httpx.HTTPStatusError as exc:
        console.print(f"  [yellow]Failed to post to {jira_key}: HTTP {exc.response.status_code}[/yellow]")
        return False
    except Exception as exc:
        console.print(f"  [yellow]Failed to post to {jira_key}: {exc}[/yellow]")
        return False


def _build_result_comment_adf(
    run_id: str,
    test_file: str,
    status: str,
    passed: int,
    failed: int,
    skipped: int,
    total: int,
    duration: float,
    failures: list[dict[str, str]],
) -> dict:
    """Build an Atlassian Document Format (ADF) body for the test result comment."""
    content: list[dict] = []

    # Header
    content.append({
        "type": "heading",
        "attrs": {"level": 3},
        "content": [{"type": "text", "text": f"PlaySpec Test Results — {status}"}],
    })

    # Summary paragraph
    summary = f"Run: {run_id} | File: {test_file} | Duration: {duration:.1f}s"
    content.append({
        "type": "paragraph",
        "content": [{"type": "text", "text": summary}],
    })

    # Results table
    def _cell(text: str, header: bool = False) -> dict:
        node = {"type": "text", "text": text}
        if header:
            node = {"type": "text", "text": text, "marks": [{"type": "strong"}]}
        return {"type": "tableCell" if not header else "tableHeader", "content": [
            {"type": "paragraph", "content": [node]},
        ]}

    content.append({
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
        "content": [
            {"type": "tableRow", "content": [
                _cell("Total", header=True),
                _cell("Passed", header=True),
                _cell("Failed", header=True),
                _cell("Skipped", header=True),
            ]},
            {"type": "tableRow", "content": [
                _cell(str(total)),
                _cell(str(passed)),
                _cell(str(failed)),
                _cell(str(skipped)),
            ]},
        ],
    })

    # Failures detail
    if failures:
        content.append({
            "type": "heading",
            "attrs": {"level": 4},
            "content": [{"type": "text", "text": "Failures"}],
        })
        for f in failures[:10]:  # Cap at 10 to avoid huge comments
            name = f.get("test_name", "unknown")
            error = f.get("error_message", "")[:200]
            content.append({
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": f"{name}: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": error},
                ],
            })

    return {"version": 1, "type": "doc", "content": content}


def _resolve_token(config: PlaySpecConfig) -> str:
    """Get JIRA auth token based on configured method."""
    import shutil
    import subprocess

    token = os.getenv("JIRA_TOKEN", "")
    if token:
        return token

    if config.auth.jira == AuthMethod.CLI:
        if shutil.which("atlas"):
            try:
                proc = subprocess.run(
                    ["atlas", "auth", "status", "--output", "json"],
                    capture_output=True, text=True, timeout=10,
                )
                if proc.returncode == 0:
                    import json
                    data = json.loads(proc.stdout)
                    cli_token = data.get("access_token", "")
                    if cli_token:
                        return cli_token
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
                pass

    raise RuntimeError(
        "JIRA authentication failed. Either:\n"
        "  • Set JIRA_TOKEN env var, or\n"
        "  • Install Atlassian CLI and run 'atlas auth login'"
    )


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
