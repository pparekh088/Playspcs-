"""Configuration loader — reads .playspec/config.yaml and validates with Pydantic."""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class RepairPolicy(str, Enum):
    PROPOSE = "propose"
    NEVER = "never"


class AuthMethod(str, Enum):
    CLI = "cli"
    ENV = "env"


class ExecutionProfile(BaseModel):
    """Settings for a named execution profile (local-dev, pr-ci, nightly, release)."""

    base_url: str = "http://localhost:3000"
    browsers: list[str] = Field(default_factory=lambda: ["chromium"])
    parallelism: int = 2
    headed: bool = False
    repair_policy: RepairPolicy = RepairPolicy.NEVER
    artifact_retention: str = "7d"
    generation_allowed: bool = False
    suggested_fixes: bool = False
    flaky_detection: bool = False
    blocking: bool = False


class BackendSettings(BaseModel):
    """Per-backend configuration."""

    mode: str = "cli"
    timeout: int = 120


class AgentBackendConfig(BaseModel):
    """Agent backend priority and per-backend settings."""

    priority: list[str] = Field(default_factory=lambda: ["claudecode", "opencode", "copilot"])
    copilot: BackendSettings = Field(default_factory=BackendSettings)
    opencode: BackendSettings = Field(default_factory=BackendSettings)
    claudecode: BackendSettings = Field(default_factory=BackendSettings)


class AuditConfig(BaseModel):
    """Audit trail settings."""

    enabled: bool = True
    output_dir: str = ".playspec/audits"
    retention_days: int = 90
    include_prompts: bool = True
    include_responses: bool = True


class AuthConfig(BaseModel):
    """Authentication method per integration."""

    jira: AuthMethod = AuthMethod.CLI
    confluence: AuthMethod = AuthMethod.CLI
    figma: AuthMethod = AuthMethod.ENV


class PlaySpecConfig(BaseModel):
    """Top-level PlaySpec configuration."""

    test_dir: str = "tests/e2e"
    page_objects_dir: str = "tests/e2e/pages"
    fixtures_dir: str = "tests/e2e/fixtures"
    naming_convention: str = "kebab-case"
    max_retries: int = 3

    agent_backend: AgentBackendConfig = Field(default_factory=AgentBackendConfig)
    profiles: dict[str, ExecutionProfile] = Field(default_factory=dict)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    @field_validator("naming_convention")
    @classmethod
    def validate_naming(cls, v: str) -> str:
        allowed = {"kebab-case", "camelCase", "PascalCase", "snake_case"}
        if v not in allowed:
            raise ValueError(f"naming_convention must be one of {allowed}, got '{v}'")
        return v

    def get_profile(self, name: str | None = None) -> ExecutionProfile:
        """Return the named profile, falling back to auto-detection then local-dev."""
        if name and name in self.profiles:
            return self.profiles[name]
        detected = _auto_detect_profile()
        if detected and detected in self.profiles:
            return self.profiles[detected]
        if "local-dev" in self.profiles:
            return self.profiles["local-dev"]
        return ExecutionProfile()


def _auto_detect_profile() -> str | None:
    """Detect execution environment from common CI env vars."""
    import os

    if os.getenv("GITHUB_ACTIONS"):
        return "pr-ci"
    if os.getenv("AZURE_PIPELINES") or os.getenv("BUILD_BUILDID"):
        return "pr-ci"
    if os.getenv("CI"):
        return "pr-ci"
    return None


CONFIG_FILENAME = "config.yaml"
CONFIG_DIR = ".playspec"


def _find_config_path(start: Path | None = None) -> Path | None:
    """Walk up from *start* looking for .playspec/config.yaml."""
    cwd = start or Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / CONFIG_DIR / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_config(path: Path | None = None) -> PlaySpecConfig:
    """Load and validate PlaySpec config from YAML.

    Args:
        path: Explicit path to config.yaml.  When *None* the file is
              discovered by walking up from the current directory.

    Raises:
        FileNotFoundError: If no config file can be found.
        ValueError: If the YAML is invalid or fails Pydantic validation.
    """
    _load_dotenv()

    if path is None:
        path = _find_config_path()
    if path is None or not path.is_file():
        raise FileNotFoundError(
            "No .playspec/config.yaml found. Run 'playspec init' to create one."
        )

    raw_text = path.read_text(encoding="utf-8")
    raw_text = _interpolate_env_vars(raw_text)
    data: dict[str, Any] = yaml.safe_load(raw_text) or {}

    try:
        return PlaySpecConfig.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Invalid config in {path}: {exc}") from exc


def _load_dotenv() -> None:
    """Load .env file from the project root (if present) into os.environ."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Walk up from cwd to find .env next to .playspec/
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        env_file = parent / ".env"
        if env_file.is_file():
            load_dotenv(env_file, override=False)
            return


_ENV_VAR_RE = re.compile(r"\$([A-Z_][A-Z0-9_]*)")


def _interpolate_env_vars(text: str) -> str:
    """Replace $VAR_NAME references with their environment variable values."""
    def _replace(match: re.Match) -> str:
        var = match.group(1)
        return os.getenv(var, match.group(0))
    return _ENV_VAR_RE.sub(_replace, text)
