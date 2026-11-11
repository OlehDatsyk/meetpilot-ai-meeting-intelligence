"""Transcription provider interface. Kept separate from the LLM analysis layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawSegment:
    text: str
    start: float | None = None  # seconds, only when the provider returned timestamps
    end: float | None = None
    speaker: str | None = None  # provider speaker id, only when the provider diarised


@dataclass
class TranscriptionResult:
    segments: list[RawSegment]
    language: str | None
    model: str
    has_timestamps: bool
    has_diarization: bool
    details: dict[str, Any] = field(default_factory=dict)


class TranscriptionError(Exception):
    """A transcription failure with a message that is safe to show to users."""

    def __init__(self, message: str, code: str = "transcription_failed", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


class TranscriptionProvider(ABC):
    name: str
    model: str
    #: container formats the provider accepts directly; others are converted to MP3 first
    accepted_formats: frozenset[str]
    #: maximum bytes per request (None = no limit)
    max_upload_bytes: int | None = None
    supports_diarization: bool = False
    supports_timestamps: bool = False

    @abstractmethod
    def transcribe(self, path: str, audio_format: str, language: str | None, diarize: bool) -> TranscriptionResult:
        ...

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "diarization": self.supports_diarization,
                "timestamps": self.supports_timestamps, "accepted_formats": sorted(self.accepted_formats),
                "max_upload_mb": round(self.max_upload_bytes / 1024 / 1024) if self.max_upload_bytes else None}
