"""Claude Code CLI backend."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time

from playspec.backends.base import AgentBackend, AgentResponse


class ClaudeCodeBackend(AgentBackend):
    """Invoke Claude Code via its CLI in non-interactive (--print) mode."""

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    def name(self) -> str:
        return "claudecode"

    def is_available(self) -> bool:
        if not shutil.which("claude"):
            return False
        try:
            proc = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def invoke(self, prompt: str, context: dict | None = None) -> AgentResponse:
        full_prompt = prompt
        if context:
            context_header = "\n".join(f"[{k}]: {v}" for k, v in context.items())
            full_prompt = f"{context_header}\n\n{prompt}"

        prompt_hash = hashlib.sha256(full_prompt.encode()).hexdigest()
        start = time.monotonic()

        try:
            proc = subprocess.run(
                ["claude", "--print", full_prompt],
                capture_output=True, text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return AgentResponse(
                content="ERROR: Claude Code timed out.",
                backend_name=self.name(),
                duration_seconds=time.monotonic() - start,
                prompt_hash=prompt_hash,
            )

        elapsed = time.monotonic() - start
        return AgentResponse(
            content=proc.stdout.strip(),
            backend_name=self.name(),
            duration_seconds=elapsed,
            prompt_hash=prompt_hash,
        )
