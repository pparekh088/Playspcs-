"""Regression manifest schema — drives suite resolution and execution policies."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SuiteHooks(BaseModel):
    """Setup/teardown scripts for a suite."""

    setup: str | None = None
    teardown: str | None = None


class SuiteConfig(BaseModel):
    """Configuration for a single regression suite."""

    description: str = ""
    timeout_minutes: int = 30
    tags: list[str] = Field(default_factory=list)
    blocking: bool = False
    browsers: list[str] = Field(default_factory=lambda: ["chromium"])
    parallelism: int = 1
    devices: list[str] | None = None
    hooks: SuiteHooks | None = None


class QuarantineEntry(BaseModel):
    """A quarantined test with optional metadata."""

    path: str
    reason: str = ""
    added_at: str | None = None


class GlobalDefaults(BaseModel):
    """Fallback values when a suite doesn't specify its own."""

    timeout_minutes: int = 30
    browsers: list[str] = Field(default_factory=lambda: ["chromium"])
    parallelism: int = 1
    blocking: bool = False


class RegressionManifest(BaseModel):
    """Top-level regression manifest that drives suite resolution."""

    suites: dict[str, SuiteConfig] = Field(default_factory=dict)
    quarantine: list[str] = Field(default_factory=list)
    hooks: dict[str, SuiteHooks] = Field(default_factory=dict)
    global_defaults: GlobalDefaults = Field(default_factory=GlobalDefaults)
