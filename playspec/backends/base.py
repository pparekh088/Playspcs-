"""Abstract base class for agent backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class AgentResponse(BaseModel):
    """Structured response from an agent backend."""

    content: str
    structured: dict | None = None
    backend_name: str
    duration_seconds: float
    prompt_hash: str


class AgentBackend(ABC):
    """Interface that all agent backends must implement."""

    @abstractmethod
    def invoke(self, prompt: str, context: dict | None = None) -> AgentResponse:
        """Send a prompt to the agent backend and return the response."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is installed, authenticated, and ready."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for audit logs."""
        ...
