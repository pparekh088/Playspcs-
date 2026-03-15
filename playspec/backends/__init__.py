"""Agent backend resolver — picks the highest-priority available backend."""

from __future__ import annotations

from playspec.backends.base import AgentBackend, AgentResponse
from playspec.backends.copilot import CopilotBackend
from playspec.backends.opencode import OpenCodeBackend
from playspec.backends.claudecode import ClaudeCodeBackend
from playspec.config import PlaySpecConfig

_REGISTRY: dict[str, type[AgentBackend]] = {
    "copilot": CopilotBackend,
    "opencode": OpenCodeBackend,
    "claudecode": ClaudeCodeBackend,
}


def get_backend(config: PlaySpecConfig, override: str | None = None) -> AgentBackend:
    """Return the highest-priority available backend.

    Args:
        config: PlaySpec configuration with agent_backend priority list.
        override: If specified, force this backend regardless of priority.

    Raises:
        RuntimeError: If no backend is available.
    """
    if override:
        cls = _REGISTRY.get(override)
        if cls is None:
            raise RuntimeError(
                f"Unknown backend '{override}'. Available: {', '.join(_REGISTRY)}"
            )
        backend = cls()
        if not backend.is_available():
            raise RuntimeError(
                f"Backend '{override}' is not available. "
                f"Make sure the CLI tool is installed and authenticated."
            )
        return backend

    for name in config.agent_backend.priority:
        cls = _REGISTRY.get(name)
        if cls is None:
            continue
        backend = cls()
        if backend.is_available():
            return backend

    lines = [
        "No agent backend is available. Install one of:",
        "  • GitHub Copilot: gh extension install github/gh-copilot",
        "  • OpenCode: https://github.com/opencode-ai/opencode",
        "  • Claude Code: https://claude.ai/code",
    ]
    raise RuntimeError("\n".join(lines))


__all__ = [
    "AgentBackend",
    "AgentResponse",
    "CopilotBackend",
    "OpenCodeBackend",
    "ClaudeCodeBackend",
    "get_backend",
]
