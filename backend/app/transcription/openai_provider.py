"""OpenAI speech-to-text.

Models behave differently, so the request is built per model:
- gpt-4o-transcribe-diarize: `diarized_json` gives segments with timestamps and speaker ids.
- whisper-1: `verbose_json` with segment timestamps, no speakers.
- other models (gpt-transcribe, gpt-4o-transcribe, ...): plain text only, no timestamps or speakers.
"""

from __future__ import annotations

import os
import re
from typing import Any

from .base import RawSegment, TranscriptionError, TranscriptionProvider, TranscriptionResult

DIARIZE_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_MODEL = DIARIZE_MODEL


def split_sentences(text: str, per_segment: int = 3) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    return [" ".join(parts[i:i + per_segment]) for i in range(0, len(parts), per_segment)]


class OpenAITranscriptionProvider(TranscriptionProvider):
    name = "openai"
    accepted_formats = frozenset({"mp3", "wav", "m4a", "ogg", "flac"})
    max_upload_bytes = 25 * 1024 * 1024

    def __init__(self, api_key: str, model: str = "", timeout: float = 900, client: Any = None):
        if not api_key and client is None:
            raise TranscriptionError("TRANSCRIPTION_API_KEY (or OPENAI_API_KEY) is not set.", "not_configured")
        self.model = model or DEFAULT_MODEL
        self.supports_diarization = self.model == DIARIZE_MODEL
        self.supports_timestamps = self.model in {DIARIZE_MODEL, "whisper-1"}
        if client is None:
            import openai
            client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=1)
        self.client = client

    def _request(self, path: str, language: str | None, diarize: bool) -> Any:
        import openai
        kwargs: dict[str, Any] = {"model": self.model}
        if language:
            kwargs["language"] = language
        if self.model == DIARIZE_MODEL:
            kwargs["response_format"] = "diarized_json" if diarize else "json"
            kwargs["chunking_strategy"] = "auto"
        elif self.model == "whisper-1":
            kwargs["response_format"] = "verbose_json"
            kwargs["timestamp_granularities"] = ["segment"]
        else:
            kwargs["response_format"] = "json"
        try:
            with open(path, "rb") as f:
                return self.client.audio.transcriptions.create(file=(os.path.basename(path), f), **kwargs)
        except openai.AuthenticationError as e:
            raise TranscriptionError("The transcription provider rejected the API key.", "provider_auth") from e
        except openai.PermissionDeniedError as e:
            raise TranscriptionError("The API key is not allowed to use this transcription model.",
                                     "provider_permission") from e
        except openai.RateLimitError as e:
            raise TranscriptionError("The transcription provider is rate limiting requests or the account has "
                                     "no remaining quota.", "provider_rate_limited", retryable=True) from e
        except openai.BadRequestError as e:
            raise TranscriptionError("The transcription provider could not process this audio.",
                                     "provider_rejected_audio") from e
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise TranscriptionError("Could not reach the transcription provider.", "provider_unavailable",
                                     retryable=True) from e
        except openai.InternalServerError as e:
            raise TranscriptionError("The transcription provider had a temporary error.", "provider_error",
                                     retryable=True) from e
        except openai.APIStatusError as e:
            raise TranscriptionError(f"The transcription provider returned an error (HTTP {e.status_code}).",
                                     "provider_error", retryable=e.status_code >= 500) from e

    def transcribe(self, path: str, audio_format: str, language: str | None, diarize: bool) -> TranscriptionResult:
        resp = self._request(path, language, diarize)
        raw_segments = getattr(resp, "segments", None)
        lang = getattr(resp, "language", None)
        segments: list[RawSegment] = []
        has_ts = has_dia = False
        if raw_segments:
            for s in raw_segments:
                text = (getattr(s, "text", "") or "").strip()
                if not text:
                    continue
                speaker = getattr(s, "speaker", None)
                segments.append(RawSegment(text=text, start=float(s.start), end=float(s.end),
                                           speaker=str(speaker) if speaker is not None else None))
            has_ts = True
            has_dia = any(s.speaker for s in segments)
        else:
            text = (getattr(resp, "text", "") or "").strip()
            segments = [RawSegment(text=t) for t in split_sentences(text)]
        return TranscriptionResult(segments=segments, language=lang, model=self.model, has_timestamps=has_ts,
                                   has_diarization=has_dia,
                                   details={"duration": getattr(resp, "duration", None)})
