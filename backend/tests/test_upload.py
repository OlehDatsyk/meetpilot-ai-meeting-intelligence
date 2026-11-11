"""Upload validation, metadata extraction and storage."""

import os

import pytest
from conftest import FakeTranscriber, ffmpeg_convert, make_wav, set_env

from app import transcription
from app.audio import AudioValidationError, inspect_audio, plan_chunks, sniff_format


@pytest.mark.parametrize("ext,args,fmt", [
    ("mp3", ["-c:a", "libmp3lame", "-b:a", "64k"], "mp3"),
    ("flac", ["-c:a", "flac"], "flac"),
    ("ogg", ["-c:a", "libvorbis"], "ogg"),
    ("m4a", ["-c:a", "aac", "-b:a", "64k"], "m4a"),
    ("aac", ["-c:a", "aac", "-b:a", "64k", "-f", "adts"], "aac"),
])
def test_sniff_and_inspect_real_formats(tmp_path, ext, args, fmt):
    data = ffmpeg_convert(make_wav(3.0), ext, args)
    p = tmp_path / f"a.{ext}"
    p.write_bytes(data)
    assert sniff_format(str(p)) == fmt
    info = inspect_audio(str(p), f"meeting.{ext}")
    assert info.format == fmt and 2.5 < info.duration_seconds < 3.6


def test_wav_metadata(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(make_wav(1.5, rate=22050))
    info = inspect_audio(str(p), "a.wav")
    assert info.format == "wav" and abs(info.duration_seconds - 1.5) < 0.01
    assert info.sample_rate == 22050 and info.channels == 1


@pytest.mark.parametrize("name,content,code", [
    ("notes.txt", b"hello world, this is not audio at all", "unsupported_format"),
    ("fake.mp3", b"<html><script>alert(1)</script></html>" * 4, "unrecognised_content"),
    ("broken.wav", b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 40, "malformed_audio"),
])
def test_rejects_bad_files(tmp_path, name, content, code):
    p = tmp_path / name
    p.write_bytes(content)
    with pytest.raises(AudioValidationError) as e:
        inspect_audio(str(p), name)
    assert e.value.code == code


def test_extension_must_match_content(tmp_path):
    p = tmp_path / "x.mp3"
    p.write_bytes(make_wav())
    with pytest.raises(AudioValidationError) as e:
        inspect_audio(str(p), "x.mp3")
    assert e.value.code == "extension_mismatch"


def test_plan_chunks():
    assert plan_chunks(50, 60) == [(0.0, 50)]
    assert plan_chunks(150, 60) == [(0, 60), (60, 60), (120, 30)]


def test_upload_without_provider_stores_only(alice):
    m = alice.meeting()
    r = alice.upload(m["id"], make_wav(2.0))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job"] is None and "No transcription provider" in body["notice"]
    assert body["meeting"]["status"] == "uploaded"
    rec = body["meeting"]["recording"]
    assert rec["audio_format"] == "wav" and abs(rec["duration_seconds"] - 2.0) < 0.01
    assert body["meeting"]["duration_seconds"] == rec["duration_seconds"]
    # stored outside the database, under the storage root
    files = [f for _, _, fs in os.walk(os.environ["STORAGE_ROOT"]) for f in fs]
    assert len(files) == 1 and files[0].endswith(".wav")


def test_upload_creates_job_with_provider(alice):
    transcription.set_transcription_factory(lambda: FakeTranscriber())
    m = alice.meeting()
    r = alice.upload(m["id"], make_wav())
    assert r.status_code == 201
    assert r.json()["job"]["status"] == "queued" and r.json()["meeting"]["status"] == "queued"


def test_upload_errors(alice, monkeypatch):
    m = alice.meeting()
    r = alice.upload(m["id"], b"not audio", filename="x.exe")
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_format"
    r = alice.upload(m["id"], b"", filename="x.wav")
    assert r.status_code == 400
    set_env(monkeypatch, max_audio_size_mb=1)
    r = alice.upload(m["id"], make_wav(40.0))  # ~1.3 MB
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    set_env(monkeypatch, max_audio_size_mb=200, max_audio_duration_minutes=1)
    r = alice.upload(m["id"], make_wav(61.0, rate=8000))
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_long"
    assert not [f for _, _, fs in os.walk(os.environ["STORAGE_ROOT"]) for f in fs]  # nothing stored on failure


def test_duplicate_and_replace(alice):
    wav = make_wav(1.0)
    m1, m2 = alice.meeting("One"), alice.meeting("Two")
    assert alice.upload(m1["id"], wav).status_code == 201
    r = alice.upload(m2["id"], wav)
    assert r.status_code == 201 and r.json()["duplicate_of"] == [{"meeting_id": m1["id"], "title": "One"}]
    r = alice.upload(m1["id"], make_wav(1.2))
    assert r.status_code == 409 and r.json()["error"]["code"] == "recording_exists"
    r = alice.upload(m1["id"], make_wav(1.2), replace=True)
    assert r.status_code == 201 and abs(r.json()["meeting"]["recording"]["duration_seconds"] - 1.2) < 0.01
    files = [f for _, _, fs in os.walk(os.environ["STORAGE_ROOT"]) for f in fs]
    assert len(files) == 2  # the replaced file was removed


def test_media_streaming_ranges(alice, client):
    m = alice.meeting()
    rec = alice.upload(m["id"], make_wav(1.0)).json()["meeting"]["recording"]
    url = alice.get(f"/api/v1/recordings/{rec['id']}/media-url").json()["url"]
    full = client.get(url)
    assert full.status_code == 200 and full.headers["accept-ranges"] == "bytes"
    part = client.get(url, headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == full.content[10:20]
    assert part.headers["content-range"] == f"bytes 10-19/{len(full.content)}"
    tail = client.get(url, headers={"Range": "bytes=-5"})
    assert tail.content == full.content[-5:]
    assert client.get(url, headers={"Range": f"bytes={len(full.content) + 5}-"}).status_code == 416
