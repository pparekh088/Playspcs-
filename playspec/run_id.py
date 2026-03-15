"""Run ID generation — unique, sortable, human-readable identifiers."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def generate_run_id() -> str:
    """Generate a run ID in the format ps-YYYYMMDD-HHMMSS-XXXX."""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(4)
    return f"ps-{ts}-{suffix}"
