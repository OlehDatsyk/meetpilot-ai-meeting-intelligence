"""AI provider registry with a primary provider and optional fallbacks."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import get_settings
from .base import AINotConfigured, AIProvider, AIProviderError
from .providers import DEFAULT_MODELS, PROVIDER_CLASSES

log = logging.getLogger("meetpilot.ai")
T = TypeVar("T", bound=BaseModel)

__all__ = ["AIClient", "AINotConfigured", "AIProvider", "AIProviderError", "get_ai_client", "set_ai_factory",
           "ai_status"]


@dataclass
class AIResult:
    value: Any
    provider: str
    model: str


class AIClient:
    def __init__(self, providers: list[AIProvider]):
        if not providers:
            raise AINotConfigured()
        self.providers = providers

    @property
    def primary(self) -> AIProvider:
        return self.providers[0]

    def _run(self, fn: Callable[[AIProvider], Any]) -> AIResult:
        errors: list[str] = []
        last: AIProviderError | None = None
        for p in self.providers:
            try:
                return AIResult(fn(p), p.name, p.model)
            except AIProviderError as e:
                log.warning("AI provider %s failed: %s (%s)", p.name, e.code, "retryable" if e.retryable else "final")
                errors.append(f"{p.name}: {e.message}")
                last = e
        assert last is not None
        if len(self.providers) > 1:
            raise AIProviderError("All configured AI providers failed. " + " ".join(errors), last.code,
                                  retryable=last.retryable)
        raise last

    def structured(self, system: str, user: str, model_cls: type[T], max_tokens: int = 16000) -> tuple[T, str, str]:
        schema = strict_schema(model_cls)

        def call(p: AIProvider) -> T:
            raw = p.generate_json(system, user, schema, max_tokens)
            try:
                return model_cls.model_validate(json.loads(_strip_fences(raw)))
            except (json.JSONDecodeError, ValidationError) as e:
                raise AIProviderError(f"{p.name} returned output that did not match the expected structure.",
                                      "invalid_output", retryable=True) from e

        r = self._run(call)
        return r.value, r.provider, r.model

    def text(self, system: str, user: str, max_tokens: int = 4000) -> tuple[str, str, str]:
        r = self._run(lambda p: p.generate_text(system, user, max_tokens))
        return r.value, r.provider, r.model


def _strip_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def strict_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema adapted for strict structured output: inline refs, every property required,
    no additional properties."""
    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return fix(dict(defs[node["$ref"].split("/")[-1]]))
            node = {k: fix(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [fix(x) for x in node]
        return node

    return fix(schema)


_factory: Callable[[], AIClient | None] | None = None


def set_ai_factory(factory: Callable[[], AIClient | None] | None) -> None:
    global _factory
    _factory = factory


def get_ai_client() -> AIClient | None:
    """The configured client, or None when no provider (with a key) is configured."""
    if _factory is not None:
        return _factory()
    s = get_settings()
    if s.ai_provider == "none":
        return None
    providers: list[AIProvider] = []
    for i, name in enumerate([s.ai_provider, *s.fallback_provider_list]):
        key = s.provider_key(name)
        if not key:
            continue
        model = s.ai_model if i == 0 and s.ai_model else ""
        providers.append(PROVIDER_CLASSES[name](key, model, timeout=s.ai_timeout_seconds))
    return AIClient(providers) if providers else None


def ai_status() -> dict[str, Any]:
    s = get_settings()
    client = get_ai_client()
    if client is None:
        missing = s.ai_provider != "none"
        return {"configured": False, "provider": s.ai_provider,
                "error": "API key missing for the configured provider." if missing else None}
    return {"configured": True, "provider": client.primary.name, "model": client.primary.model,
            "fallbacks": [{"provider": p.name, "model": p.model} for p in client.providers[1:]],
            "default_models": DEFAULT_MODELS}
