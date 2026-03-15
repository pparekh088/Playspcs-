"""Shared Rich console instance — use this instead of bare print()."""

from rich.console import Console

console = Console()
err_console = Console(stderr=True)
