"""Quarantine management commands."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.table import Table

from playspec.console import console
from playspec.manifest import load_manifest


def _load_raw_manifest() -> tuple[dict, Path]:
    """Load the raw YAML manifest and its path."""
    manifest = load_manifest()
    path = manifest.path
    if path is None:
        raise FileNotFoundError("Manifest path not found.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw, path


def add_quarantine(test_path: str, reason: str = "") -> None:
    """Add a test file to the quarantine list in the manifest."""
    raw, path = _load_raw_manifest()
    quarantine: list = raw.setdefault("quarantine", [])

    if test_path in quarantine:
        console.print(f"[yellow]{test_path} is already quarantined.[/yellow]")
        return

    quarantine.append(test_path)
    path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False), encoding="utf-8")
    console.print(f"[green]✓[/green] Quarantined {test_path}" + (f" — {reason}" if reason else ""))


def remove_quarantine(test_path: str) -> None:
    """Remove a test file from the quarantine list."""
    raw, path = _load_raw_manifest()
    quarantine: list = raw.get("quarantine", [])

    if test_path not in quarantine:
        console.print(f"[yellow]{test_path} is not in quarantine.[/yellow]")
        return

    quarantine.remove(test_path)
    raw["quarantine"] = quarantine
    path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False), encoding="utf-8")
    console.print(f"[green]✓[/green] Removed {test_path} from quarantine.")


def list_quarantine() -> None:
    """Display all quarantined tests."""
    manifest = load_manifest()
    quarantined = manifest.get_quarantined()

    if not quarantined:
        console.print("[green]No tests are quarantined.[/green]")
        return

    table = Table(title="Quarantined Tests")
    table.add_column("Test Path", style="bold")

    for t in sorted(quarantined):
        table.add_row(t)

    console.print(table)
