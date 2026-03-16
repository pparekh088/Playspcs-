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


def comment_exists(jira_key: str, run_id: str) -> bool:
    """Check whether a PlaySpec comment for *run_id* already exists on the issue."""
    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")

    if not all([base_url, email, api_token]):
        return False

    credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    url = f"{base_url}/rest/api/3/issue/{jira_key}/comment"
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
        for comment in resp.json().get("comments", []):
            body_text = _extract_text(comment.get("body", ""))
            if run_id in body_text:
                return True
    except Exception:
        pass
    return False


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
    passed_tests: list[dict[str, str]] | None = None,
    stability_hint: str = "",
    deduplicate: bool = True,
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

    if deduplicate and comment_exists(jira_key, run_id):
        console.print(f"  [dim]Skipping {jira_key} — comment for {run_id} already exists.[/dim]")
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
        passed_tests=passed_tests or [],
        stability_hint=stability_hint,
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


def create_issue(
    project_key: str,
    summary: str,
    description: str,
    issue_type: str = "Bug",
    labels: list[str] | None = None,
    parent_key: str | None = None,
) -> str | None:
    """Create a new Jira issue and return its key, or ``None`` on failure."""
    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")

    if not all([base_url, email, api_token]):
        console.print("[dim]Skipping Jira issue creation — env vars not set.[/dim]")
        return None

    credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    url = f"{base_url}/rest/api/3/issue"
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "description": {
            "version": 1,
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
        },
        "issuetype": {"name": issue_type},
    }
    if labels:
        fields["labels"] = labels
    if parent_key:
        fields["issuelinks"] = [{
            "type": {"name": "Relates"},
            "outwardIssue": {"key": parent_key},
        }]

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json={"fields": fields})
            if resp.status_code == 400:
                # Bug type may not exist — retry with Task
                if issue_type == "Bug":
                    fields["issuetype"] = {"name": "Task"}
                    resp = client.post(url, headers=headers, json={"fields": fields})
            resp.raise_for_status()
        key = resp.json().get("key", "")
        console.print(f"  [green]Created Jira issue {key}[/green]")
        return key
    except Exception as exc:
        console.print(f"  [yellow]Failed to create Jira issue: {exc}[/yellow]")
        return None


def search_issues(jql: str) -> list[dict[str, Any]]:
    """Run a JQL search and return a list of issue dicts (key, summary, status)."""
    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")

    if not all([base_url, email, api_token]):
        return []

    credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    url = f"{base_url}/rest/api/3/search"
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json={"jql": jql, "maxResults": 50, "fields": ["summary", "status"]})
            resp.raise_for_status()
        results = []
        for issue in resp.json().get("issues", []):
            fields = issue.get("fields", {})
            results.append({
                "key": issue.get("key", ""),
                "summary": fields.get("summary", ""),
                "status": fields.get("status", {}).get("name", ""),
            })
        return results
    except Exception:
        return []


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
    passed_tests: list[dict[str, str]] | None = None,
    stability_hint: str = "",
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
    if stability_hint:
        summary += f" | {stability_hint}"
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

    # Per-test pass list
    if passed_tests:
        content.append({
            "type": "heading",
            "attrs": {"level": 4},
            "content": [{"type": "text", "text": "Passed Tests"}],
        })
        for pt in passed_tests[:15]:
            name = pt.get("test_name", "unknown")
            content.append({
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": f"PASS ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": name},
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
                    {"type": "text", "text": f"FAIL {name}: ", "marks": [{"type": "strong"}]},
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
