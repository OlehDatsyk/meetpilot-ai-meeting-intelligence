"""Test setup. Every test gets a fresh SQLite database and storage directory.

Provider calls are mocked here (fake providers / mocked HTTP transports). No test calls a real
transcription or AI service; see tests/live/ for opt-in live checks.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave

import pytest

_TMP = tempfile.mkdtemp(prefix="meetpilot-tests-")
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": f"sqlite:///{_TMP}/bootstrap.db",
    "STORAGE_ROOT": os.path.join(_TMP, "storage"),
    "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
    "TRANSCRIPTION_PROVIDER": "none",
    "AI_PROVIDER": "none",
    "RATE_LIMIT_ENABLED": "false",
    "EMBEDDED_WORKER": "false",
    "CORS_ORIGINS": "http://localhost:5173",
})

from fastapi.testclient import TestClient  # noqa: E402

from app import ai, transcription  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, get_engine, reset_engine  # noqa: E402
from app.deps import limiter  # noqa: E402
from app.storage import set_storage_override  # noqa: E402
from app.transcription.base import RawSegment, TranscriptionError, TranscriptionProvider, TranscriptionResult  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_env(tmp_path, monkeypatch):
    # TEST_DATABASE_URL runs the suite against PostgreSQL (tables are recreated for every test).
    pg = os.environ.get("TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", pg or f"sqlite:///{tmp_path.as_posix()}/test.db")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    reset_engine()
    set_storage_override(None)
    if pg:
        Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    limiter.reset()
    transcription.set_transcription_factory(None)
    ai.set_ai_factory(None)
    yield
    transcription.set_transcription_factory(None)
    ai.set_ai_factory(None)
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def client():
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


def set_env(monkeypatch, **values):
    for k, v in values.items():
        monkeypatch.setenv(k.upper(), str(v))
    get_settings.cache_clear()


# --- Accounts ----------------------------------------------------------------------------------

class Account:
    def __init__(self, client: TestClient, email: str, name: str = "Test User", password: str = "correct-horse-1"):
        r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": name})
        assert r.status_code == 201, r.text
        self.client = client
        self.password = password
        self.token = r.json()["access_token"]
        self.user = r.json()["user"]
        self.workspace_id = self.get("/api/v1/workspaces").json()[0]["id"]

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self.headers, **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.client.request("DELETE", url, headers=self.headers, **kw)

    def meeting(self, title="Weekly sync", **extra) -> dict:
        r = self.post("/api/v1/meetings", json={"workspace_id": self.workspace_id, "title": title, **extra})
        assert r.status_code == 201, r.text
        return r.json()

    def upload(self, meeting_id: str, data: bytes, filename: str = "call.wav", **form):
        return self.post(f"/api/v1/meetings/{meeting_id}/recording",
                         files={"file": (filename, data, "application/octet-stream")},
                         data={k: str(v).lower() if isinstance(v, bool) else v for k, v in form.items()})


@pytest.fixture
def alice(client):
    return Account(client, "alice@example.com", "Alice Example")


@pytest.fixture
def bob(client):
    return Account(client, "bob@example.com", "Bob Example")


# --- Audio fixtures ----------------------------------------------------------------------------

def make_wav(seconds: float = 2.0, rate: int = 16000, freq: float = 440.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rate)))
                          for i in range(int(seconds * rate)))
        w.writeframes(frames)
    return buf.getvalue()


def ffmpeg_convert(wav: bytes, ext: str, codec_args: list[str]) -> bytes:
    from app.audio import ffmpeg_exe
    exe = ffmpeg_exe()
    if not exe:
        pytest.skip("ffmpeg not available")
    d = tempfile.mkdtemp()
    try:
        src, dst = os.path.join(d, "in.wav"), os.path.join(d, f"out.{ext}")
        with open(src, "wb") as f:
            f.write(wav)
        subprocess.run([exe, "-nostdin", "-loglevel", "error", "-y", "-i", src, *codec_args, dst], check=True)
        with open(dst, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- Fake providers ----------------------------------------------------------------------------

class FakeTranscriber(TranscriptionProvider):
    """Mock provider. Records each call; returns two diarised segments per request."""
    name = "fake"
    model = "fake-stt-1"
    supports_diarization = True
    supports_timestamps = True

    def __init__(self, accepted=("wav", "mp3", "m4a", "ogg", "flac", "aac"), max_bytes=None, fail: Exception | None = None,
                 segments: list[RawSegment] | None = None):
        self.accepted_formats = frozenset(accepted)
        self.max_upload_bytes = max_bytes
        self.fail = fail
        self.calls: list[tuple[str, str]] = []
        self.segments = segments

    def transcribe(self, path, audio_format, language, diarize):
        self.calls.append((os.path.basename(path), audio_format))
        if self.fail:
            raise self.fail
        segs = self.segments or [
            RawSegment("Let's agree to ship the beta on Friday.", 0.0, 2.5, "A"),
            RawSegment("Agreed. Dana will write the release notes by March 3rd.", 2.6, 6.0, "B"),
        ]
        return TranscriptionResult(segments=[RawSegment(s.text, s.start, s.end, s.speaker) for s in segs],
                                   language="en", model=self.model, has_timestamps=True, has_diarization=True)


__all__ = ["Account", "FakeTranscriber", "TranscriptionError", "make_wav", "ffmpeg_convert", "set_env"]
