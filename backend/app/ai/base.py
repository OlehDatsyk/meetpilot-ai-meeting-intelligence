"""Provider-independent AI interface. Each adapter uses its vendor's own SDK and API conventions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AIProviderError(Exception):
    """A failure that is safe to show to users. `retryable` failures may succeed later or on a fallback."""

    def __init__(self, message: str, code: str = "ai_failed", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


class AINotConfigured(AIProviderError):
    def __init__(self) -> None:
        super().__init__("No AI provider is configured. Set AI_PROVIDER and an API key on the server.",
                         "ai_not_configured")


class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> str:
        """Return a JSON string that should match `schema` (validated by the caller)."""

    @abstractmethod
    def generate_text(self, system: str, user: str, max_tokens: int) -> str:
        ...
