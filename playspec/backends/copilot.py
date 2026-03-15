"""GitHub Copilot CLI backend.

Note: `gh copilot suggest -t shell` is a shell-command suggestion tool, not
a general code-generation endpoint.  For author-mode code generation the
OpenCode or Claude Code backends are more capable.  This backend passes the
prompt as-is and returns whatever Copilot produces; callers should prefer
other backends for complex generation tasks.
"""

from __future__ import annotations

import hashlib
import os
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

        prompt_file: str | None = None
        try:
            fd, prompt_file = tempfile.mkstemp(suffix=".md", prefix="playspec-")
            os.write(fd, prompt.encode())
            os.close(fd)

            proc = subprocess.run(
                ["gh", "copilot", "suggest", "-t", "shell", f"cat {prompt_file}"],
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
        finally:
            if prompt_file and os.path.exists(prompt_file):
                os.unlink(prompt_file)

        elapsed = time.monotonic() - start
        content = proc.stdout.strip()
        if context:
            content = f"[context keys: {', '.join(context)}]\n{content}"

        return AgentResponse(
            content=content,
            backend_name=self.name(),
            duration_seconds=elapsed,
            prompt_hash=prompt_hash,
        )
