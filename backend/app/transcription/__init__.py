"""Transcription provider registry."""

from __future__ import annotations

from collections.abc import Callable

from ..config import get_settings
from .base import RawSegment, TranscriptionError, TranscriptionProvider, TranscriptionResult

__all__ = ["RawSegment", "TranscriptionError", "TranscriptionProvider", "TranscriptionResult",
           "get_transcription_provider", "set_transcription_factory", "transcription_status"]

_factory: Callable[[], TranscriptionProvider | None] | None = None


def set_transcription_factory(factory: Callable[[], TranscriptionProvider | None] | None) -> None:
    """Override provider construction (tests use this to inject mocked providers)."""
    global _factory
    _factory = factory


def get_transcription_provider() -> TranscriptionProvider | None:
    """The configured provider, or None when transcription is turned off."""
    if _factory is not None:
        return _factory()
    s = get_settings()
    if s.transcription_provider == "openai":
        from .openai_provider import OpenAITranscriptionProvider
        return OpenAITranscriptionProvider(s.transcription_key, s.transcription_model,
                                           timeout=s.transcription_timeout_seconds)
    if s.transcription_provider == "local":
        from .local_provider import LocalWhisperProvider
        return LocalWhisperProvider(s.transcription_model or s.local_whisper_model, s.local_whisper_compute_type,
                                    s.local_whisper_threads, s.local_whisper_model_dir)
    return None


def transcription_status() -> dict:
    s = get_settings()
    try:
        p = get_transcription_provider()
    except TranscriptionError as e:
        return {"configured": False, "provider": s.transcription_provider, "error": e.message}
    if p is None:
        return {"configured": False, "provider": "none"}
    return {"configured": True, **p.describe()}
