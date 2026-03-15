"""GitHub Copilot CLI backend."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import time

from playspec.backends.base import AgentBackend, AgentResponse


class CopilotBackend(AgentBackend):
    """Invoke GitHub Copilot via the gh copilot CLI."""

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    def name(self) -> str:
        return "copilot"

    def is_available(self) -> bool:
        if not shutil.which("gh"):
            return False
        try:
            proc = subprocess.run(
                ["gh", "copilot", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def invoke(self, prompt: str, context: dict | None = None) -> AgentResponse:
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        start = time.monotonic()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            proc = subprocess.run(
                ["gh", "copilot", "suggest", "-t", "shell", prompt],
                capture_output=True, text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return AgentResponse(
                content="ERROR: Copilot timed out.",
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
