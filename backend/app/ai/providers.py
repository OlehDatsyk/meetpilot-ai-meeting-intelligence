"""AI provider adapters: OpenAI, Anthropic Claude and Google Gemini."""

from __future__ import annotations

from typing import Any

from .base import AIProvider, AIProviderError

DEFAULT_MODELS = {"openai": "gpt-5-mini", "anthropic": "claude-opus-5-5", "gemini": "gemini-2.5-flash"}


# --- OpenAI ------------------------------------------------------------------------------------

class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "", timeout: float = 300, client: Any = None):
        self.model = model or DEFAULT_MODELS["openai"]
        if client is None:
            import openai
            client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=1)
        self.client = client

    def _call(self, messages: list[dict[str, str]], max_tokens: int, response_format: dict | None) -> str:
        import openai
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "max_completion_tokens": max_tokens}
        if response_format:
            kwargs["response_format"] = response_format
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as e:
            raise AIProviderError("OpenAI rejected the API key.", "provider_auth") from e
        except openai.RateLimitError as e:
            raise AIProviderError("OpenAI is rate limiting requests or the account has no quota.",
                                  "provider_rate_limited", retryable=True) from e
        except openai.BadRequestError as e:
            raise AIProviderError("OpenAI rejected the request (check AI_MODEL).", "provider_bad_request") from e
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise AIProviderError("Could not reach OpenAI.", "provider_unavailable", retryable=True) from e
        except openai.APIStatusError as e:
            raise AIProviderError(f"OpenAI returned HTTP {e.status_code}.", "provider_error",
                                  retryable=e.status_code >= 500) from e
        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            raise AIProviderError("The OpenAI model declined to answer.", "provider_refusal")
        if choice.finish_reason == "length":
            raise AIProviderError("The OpenAI response was cut off before it finished.", "output_truncated",
                                  retryable=True)
        return choice.message.content or ""

    def generate_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> str:
        fmt = {"type": "json_schema", "json_schema": {"name": "result", "schema": schema, "strict": True}}
        return self._call([{"role": "system", "content": system}, {"role": "user", "content": user}],
                          max_tokens, fmt)

    def generate_text(self, system: str, user: str, max_tokens: int) -> str:
        return self._call([{"role": "system", "content": system}, {"role": "user", "content": user}],
                          max_tokens, None)


# --- Anthropic ---------------------------------------------------------------------------------

# Models that accept the server-side refusal fallback ("fallbacks": "default").
_ANTHROPIC_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1",
                              "claude-fable-5-2"}


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "", timeout: float = 300, client: Any = None):
        self.model = model or DEFAULT_MODELS["anthropic"]
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)
        self.client = client

    def _call(self, system: str, user: str, max_tokens: int, output_format: dict | None) -> str:
        import anthropic
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "system": system,
                                  "messages": [{"role": "user", "content": user}]}
        if output_format:
            kwargs["output_config"] = {"format": output_format}
        use_fallbacks = self.model in _ANTHROPIC_FALLBACK_MODELS
        try:
            if use_fallbacks:
                resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                        fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise AIProviderError("Anthropic rejected the API key.", "provider_auth") from e
        except anthropic.PermissionDeniedError as e:
            raise AIProviderError("The Anthropic API key cannot use this model.", "provider_permission") from e
        except anthropic.NotFoundError as e:
            raise AIProviderError("The Anthropic model was not found (check AI_MODEL).", "provider_bad_request") from e
        except anthropic.RateLimitError as e:
            raise AIProviderError("Anthropic is rate limiting requests.", "provider_rate_limited",
                                  retryable=True) from e
        except anthropic.BadRequestError as e:
            raise AIProviderError("Anthropic rejected the request.", "provider_bad_request") from e
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            raise AIProviderError("Could not reach Anthropic.", "provider_unavailable", retryable=True) from e
        except anthropic.APIStatusError as e:
            raise AIProviderError(f"Anthropic returned HTTP {e.status_code}.", "provider_error",
                                  retryable=e.status_code >= 500) from e
        if resp.stop_reason == "refusal":
            raise AIProviderError("The Claude model declined to process this content.", "provider_refusal")
        if resp.stop_reason == "max_tokens":
            raise AIProviderError("The Claude response was cut off before it finished.", "output_truncated",
                                  retryable=True)
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def generate_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> str:
        return self._call(system, user, max_tokens, {"type": "json_schema", "schema": schema})

    def generate_text(self, system: str, user: str, max_tokens: int) -> str:
        return self._call(system, user, max_tokens, None)


# --- Google Gemini -----------------------------------------------------------------------------

class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "", timeout: float = 300, client: Any = None):
        self.model = model or DEFAULT_MODELS["gemini"]
        if client is None:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout * 1000)))
        self.client = client

    def _call(self, system: str, user: str, max_tokens: int, schema: dict | None) -> str:
        from google.genai import errors, types
        cfg: dict[str, Any] = {"system_instruction": system, "max_output_tokens": max_tokens}
        if schema:
            cfg["response_mime_type"] = "application/json"
            cfg["response_json_schema"] = schema
        try:
            resp = self.client.models.generate_content(model=self.model, contents=user,
                                                       config=types.GenerateContentConfig(**cfg))
        except errors.ClientError as e:
            code = getattr(e, "code", 400)
            if code in (401, 403):
                raise AIProviderError("Gemini rejected the API key.", "provider_auth") from e
            if code == 429:
                raise AIProviderError("Gemini is rate limiting requests.", "provider_rate_limited",
                                      retryable=True) from e
            raise AIProviderError(f"Gemini rejected the request (HTTP {code}).", "provider_bad_request") from e
        except errors.ServerError as e:
            raise AIProviderError("Gemini had a temporary error.", "provider_error", retryable=True) from e
        except errors.APIError as e:
            raise AIProviderError("Gemini returned an error.", "provider_error", retryable=True) from e
        except Exception as e:  # network errors surface as httpx exceptions
            if type(e).__module__.startswith(("httpx", "httpcore")):
                raise AIProviderError("Could not reach Gemini.", "provider_unavailable", retryable=True) from e
            raise
        candidates = getattr(resp, "candidates", None) or []
        finish = str(getattr(candidates[0], "finish_reason", "")) if candidates else ""
        if "MAX_TOKENS" in finish:
            raise AIProviderError("The Gemini response was cut off before it finished.", "output_truncated",
                                  retryable=True)
        if "SAFETY" in finish or "PROHIBITED" in finish:
            raise AIProviderError("The Gemini model declined to process this content.", "provider_refusal")
        text = getattr(resp, "text", None)
        if not text:
            raise AIProviderError("Gemini returned an empty response.", "empty_output", retryable=True)
        return text

    def generate_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> str:
        return self._call(system, user, max_tokens, schema)

    def generate_text(self, system: str, user: str, max_tokens: int) -> str:
        return self._call(system, user, max_tokens, None)


PROVIDER_CLASSES: dict[str, type[AIProvider]] = {"openai": OpenAIProvider, "anthropic": AnthropicProvider,
                                                 "gemini": GeminiProvider}
