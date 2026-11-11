"""Local transcription with faster-whisper (CTranslate2). Runs on the server CPU; no audio leaves it.

Gives segment timestamps and language detection. It does not identify speakers.
Install with `pip install -r requirements-local.txt`.

Audio is decoded with ffmpeg into 16 kHz mono samples one window at a time (WINDOW_SECONDS), so memory use
stays flat for long recordings and does not depend on PyAV's decoder.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import Any

from ..audio import ffmpeg_exe
from .base import RawSegment, TranscriptionError, TranscriptionProvider, TranscriptionResult

log = logging.getLogger("meetpilot.transcription.local")
WINDOW_SECONDS = 600
SAMPLE_RATE = 16000

_models: dict[tuple[str, str], Any] = {}
_lock = threading.Lock()


def _load_model(name: str, compute_type: str, threads: int, download_root: str | None):
    key = (name, compute_type)
    with _lock:
        if key not in _models:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise TranscriptionError("Local transcription is not installed on this server "
                                         "(faster-whisper is missing).", "not_configured") from e
            try:
                _models[key] = WhisperModel(name, device="cpu", compute_type=compute_type, cpu_threads=threads,
                                            download_root=download_root or None)
            except Exception as e:
                log.error("Could not load Whisper model %s (%s)", name, type(e).__name__)
                raise TranscriptionError(f"The local Whisper model '{name}' could not be loaded.",
                                         "model_unavailable", retryable=True) from e
        return _models[key]


def decode_window(path: str, start: float, seconds: float):
    """16 kHz mono float32 samples for [start, start + seconds)."""
    import numpy as np
    exe = ffmpeg_exe()
    if not exe:
        raise TranscriptionError("ffmpeg is not available for local transcription.", "not_configured")
    cmd = [exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}",
           "-i", path, "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=600, check=False)
    if proc.returncode != 0:
        raise TranscriptionError("The audio could not be decoded for transcription.", "decode_failed")
    return np.frombuffer(proc.stdout, dtype=np.float32)


class LocalWhisperProvider(TranscriptionProvider):
    name = "local"
    accepted_formats = frozenset({"mp3", "wav", "m4a", "aac", "ogg", "flac"})
    max_upload_bytes = None
    supports_timestamps = True
    supports_diarization = False

    def __init__(self, model: str = "tiny", compute_type: str = "int8", threads: int = 2, download_root: str = ""):
        self.model = f"faster-whisper/{model}"
        self._model_name = model
        self._compute_type = compute_type
        self._threads = threads
        self._root = download_root

    def transcribe(self, path: str, audio_format: str, language: str | None, diarize: bool) -> TranscriptionResult:
        model = _load_model(self._model_name, self._compute_type, self._threads, self._root)
        segments: list[RawSegment] = []
        detected: str | None = language
        probability = None
        start = 0.0
        try:
            while True:
                samples = decode_window(path, start, WINDOW_SECONDS)
                if samples.size == 0:
                    break
                seg_iter, info = model.transcribe(samples, language=detected or None, vad_filter=True, beam_size=1)
                for s in seg_iter:
                    if s.text and s.text.strip():
                        segments.append(RawSegment(text=s.text.strip(), start=round(start + float(s.start), 3),
                                                   end=round(start + float(s.end), 3)))
                if detected is None:  # keep the language detected in the first window for the rest
                    detected = getattr(info, "language", None)
                    probability = round(float(getattr(info, "language_probability", 0) or 0), 3)
                if samples.size < WINDOW_SECONDS * SAMPLE_RATE:
                    break
                start += WINDOW_SECONDS
        except TranscriptionError:
            raise
        except Exception as e:
            log.error("Local transcription failed (%s)", type(e).__name__)
            raise TranscriptionError("Local transcription failed while processing this audio.",
                                     "local_transcription_failed") from e
        return TranscriptionResult(segments=segments, language=detected, model=self.model, has_timestamps=True,
                                   has_diarization=False, details={"language_probability": probability})
