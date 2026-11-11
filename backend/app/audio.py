"""Audio validation, metadata extraction and ffmpeg helpers.

The file extension is never trusted on its own: the container is identified from its first bytes and must
then parse cleanly with mutagen, which also gives the duration.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from dataclasses import dataclass

FORMATS: dict[str, dict[str, object]] = {
    "mp3": {"extensions": {".mp3"}, "content_type": "audio/mpeg"},
    "wav": {"extensions": {".wav", ".wave"}, "content_type": "audio/wav"},
    "m4a": {"extensions": {".m4a"}, "content_type": "audio/mp4"},
    "aac": {"extensions": {".aac"}, "content_type": "audio/aac"},
    "ogg": {"extensions": {".ogg", ".oga", ".opus"}, "content_type": "audio/ogg"},
    "flac": {"extensions": {".flac"}, "content_type": "audio/flac"},
}
ALLOWED_EXTENSIONS = sorted({e for f in FORMATS.values() for e in f["extensions"]})  # type: ignore[union-attr]


class AudioValidationError(Exception):
    def __init__(self, message: str, code: str = "invalid_audio"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class AudioInfo:
    format: str
    content_type: str
    duration_seconds: float
    sample_rate: int | None
    channels: int | None


def _skip_id3(head: bytes) -> int:
    if head[:3] == b"ID3" and len(head) >= 10:
        size = (head[6] & 0x7F) << 21 | (head[7] & 0x7F) << 14 | (head[8] & 0x7F) << 7 | (head[9] & 0x7F)
        footer = 10 if head[5] & 0x10 else 0
        return 10 + size + footer
    return 0


def sniff_format(path: str) -> str | None:
    """Identify the container from magic bytes. Returns a key of FORMATS or None."""
    with open(path, "rb") as f:
        head = f.read(64)
        if len(head) < 12:
            return None
        if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
            return "wav"
        if head[:4] == b"fLaC":
            return "flac"
        if head[:4] == b"OggS":
            return "ogg"
        if head[4:8] == b"ftyp":
            return "m4a"
        offset = _skip_id3(head)
        if offset:
            f.seek(offset)
            head = f.read(16)
            if head[:4] == b"fLaC":
                return "flac"
        if len(head) >= 2 and head[0] == 0xFF:
            if (head[1] & 0xF6) == 0xF0:  # ADTS sync word with layer 00 -> AAC
                return "aac"
            if (head[1] & 0xE0) == 0xE0 and (head[1] & 0x06) != 0:  # MPEG audio frame, layer I-III
                return "mp3"
    return None


def inspect_audio(path: str, filename: str) -> AudioInfo:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported file type '{ext or 'none'}'. Supported: MP3, WAV, M4A, AAC, OGG and FLAC.",
            "unsupported_format")
    fmt = sniff_format(path)
    if fmt is None:
        raise AudioValidationError("The file's content is not a recognised audio format.", "unrecognised_content")
    if ext not in FORMATS[fmt]["extensions"]:  # type: ignore[operator]
        raise AudioValidationError(
            f"The file's content is {fmt.upper()} audio but its name ends in '{ext}'. Rename it and try again.",
            "extension_mismatch")

    import mutagen
    from mutagen.aac import AAC
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis
    from mutagen.wave import WAVE

    parsers = {"mp3": [MP3], "wav": [WAVE], "m4a": [MP4], "aac": [AAC], "flac": [FLAC],
               "ogg": [OggVorbis, OggOpus]}
    parsed = None
    for cls in parsers[fmt]:
        try:
            parsed = cls(path)
            break
        except Exception:  # mutagen raises format-specific errors for malformed files
            continue
    if parsed is None or parsed.info is None:
        raise AudioValidationError("The audio file appears to be damaged and could not be read.", "malformed_audio")
    length = float(getattr(parsed.info, "length", 0) or 0)
    if not math.isfinite(length) or length <= 0:
        raise AudioValidationError("The recording has no measurable duration.", "malformed_audio")
    if fmt == "m4a" and isinstance(parsed, mutagen.mp4.MP4):
        codec = (getattr(parsed.info, "codec", "") or "").lower()
        if codec and not (codec.startswith("mp4a") or codec in {"alac", "ac-3", "ec-3"}):
            raise AudioValidationError("The MP4 file does not contain a supported audio track.", "malformed_audio")
    return AudioInfo(format=fmt, content_type=str(FORMATS[fmt]["content_type"]), duration_seconds=round(length, 3),
                     sample_rate=getattr(parsed.info, "sample_rate", None) or None,
                     channels=getattr(parsed.info, "channels", None) or None)


# --- ffmpeg ------------------------------------------------------------------------------------

def ffmpeg_exe() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class FFmpegError(Exception):
    pass


def transcode_to_mp3(src: str, dest: str, start: float | None = None, duration: float | None = None,
                     timeout: int = 900) -> None:
    """Mono 16 kHz 48 kbit/s MP3: small enough for API limits and sufficient for speech recognition."""
    exe = ffmpeg_exe()
    if not exe:
        raise FFmpegError("ffmpeg is not available, so this recording cannot be converted or split.")
    cmd = [exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", dest]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        raise FFmpegError("Converting the audio took too long.") from e
    if proc.returncode != 0 or not os.path.exists(dest) or os.path.getsize(dest) == 0:
        raise FFmpegError("The audio could not be decoded. The file may be damaged.")


def plan_chunks(duration: float, chunk_seconds: int) -> list[tuple[float, float]]:
    """Split [0, duration) into (start, length) windows of at most chunk_seconds."""
    if duration <= chunk_seconds:
        return [(0.0, duration)]
    n = math.ceil(duration / chunk_seconds)
    return [(i * chunk_seconds, min(chunk_seconds, duration - i * chunk_seconds)) for i in range(n)]
