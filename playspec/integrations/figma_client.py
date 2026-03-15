"""Figma integration — fetch file data via Figma REST API."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from playspec.config import PlaySpecConfig
from playspec.console import console


def get_file(file_url: str, config: PlaySpecConfig) -> dict[str, Any]:
    """Fetch a Figma file and return the parsed document tree.

    Args:
        file_url: Figma file URL.
        config: PlaySpec config.

    Returns:
        Parsed Figma JSON document.
    """
    token = os.getenv("FIGMA_TOKEN", "")
    if not token:
        raise RuntimeError(
            "FIGMA_TOKEN env var is not set. "
            "Generate a personal access token at https://www.figma.com/developers/api"
        )

    file_key = _extract_file_key(file_url)
    url = f"https://api.figma.com/v1/files/{file_key}"
    headers = {"X-Figma-Token": token}

    with httpx.Client(timeout=60) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()

    return resp.json()


def _extract_file_key(url: str) -> str:
    """Extract file key from a Figma URL."""
    m = re.search(r"figma\.com/(?:file|design)/([a-zA-Z0-9]+)", url)
    if m:
        return m.group(1)
    return url
