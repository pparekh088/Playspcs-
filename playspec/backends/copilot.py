"""GitHub Copilot CLI backend.

The ``gh copilot`` CLI extension exposes two sub-commands:

* ``suggest`` — returns a single shell/git/gh command.  Unsuitable for
  multi-line code generation.
* ``explain`` — accepts a natural-language query and returns an
  explanation.  This is the closest analogue to a general-purpose prompt,
  though it is optimised for *explaining* commands rather than *writing*
  code.

Because of these limitations the Copilot backend is ranked **last** in
the default priority list.  For author-mode code generation, prefer
OpenCode or Claude Code.
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
    """Invoke GitHub Copilot via ``gh copilot explain``."""

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
        full_prompt = prompt
        if context:
            context_header = "\n".join(f"[{k}]: {v}" for k, v in context.items())
            full_prompt = f"{context_header}\n\n{prompt}"

        prompt_hash = hashlib.sha256(full_prompt.encode()).hexdigest()
        start = time.monotonic()

        prompt_file: str | None = None
        try:
            fd, prompt_file = tempfile.mkstemp(suffix=".md", prefix="playspec-")
            os.write(fd, full_prompt.encode())
            os.close(fd)

            proc = subprocess.run(
                ["gh", "copilot", "explain", full_prompt[:600]],
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
        return AgentResponse(
            content=proc.stdout.strip(),
            backend_name=self.name(),
            duration_seconds=elapsed,
            prompt_hash=prompt_hash,
        )
