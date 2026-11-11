"""Transcription jobs (mocked providers) and the OpenAI adapter (mocked HTTP transport)."""

import json
from datetime import timedelta

import httpx
import pytest
from conftest import FakeTranscriber, ffmpeg_convert, make_wav, set_env

from app import transcription
from app.db import SessionLocal
from app.jobs import Worker, recover_stale_jobs
from app.models import ProcessingJob, utcnow
from app.transcription.base import RawSegment, TranscriptionError
from app.transcription.openai_provider import OpenAITranscriptionProvider


def _upload_and_run(account, fake, data=None, filename="call.wav"):
    transcription.set_transcription_factory(lambda: fake)
    m = account.meeting()
    r = account.upload(m["id"], data or make_wav(), filename=filename)
    assert r.status_code == 201, r.text
    assert Worker().run_once()
    return m["id"]


def test_transcription_job_saves_segments_and_speakers(alice):
    fake = FakeTranscriber()
    mid = _upload_and_run(alice, fake)
    meeting = alice.get(f"/api/v1/meetings/{mid}").json()
    assert meeting["status"] == "transcribed"
    assert meeting["latest_job"]["status"] == "succeeded" and meeting["latest_job"]["provider"] == "fake"
    t = alice.get(f"/api/v1/meetings/{mid}/transcript").json()
    assert t["has_timestamps"] and t["has_diarization"]
    assert [s["text"] for s in t["segments"]][0].startswith("Let's agree")
    assert [(s["start_seconds"], s["speaker_name"]) for s in t["segments"]] == [(0.0, "Speaker 1"), (2.6, "Speaker 2")]
    assert [s["label"] for s in t["speakers"]] == ["A", "B"]
    assert fake.calls == [(fake.calls[0][0], "wav")]  # sent directly, no conversion


def test_conversion_and_chunking_with_offsets(alice, monkeypatch):
    set_env(monkeypatch, transcription_chunk_seconds=60)
    fake = FakeTranscriber(accepted=("mp3",))
    mp3_input = ffmpeg_convert(make_wav(130.0, rate=8000), "flac", ["-c:a", "flac"])
    mid = _upload_and_run(alice, fake, mp3_input, "long.flac")
    assert len(fake.calls) == 3 and all(fmt == "mp3" for _, fmt in fake.calls)
    t = alice.get(f"/api/v1/meetings/{mid}/transcript").json()
    starts = [s["start_seconds"] for s in t["segments"]]
    assert starts == [0.0, 2.6, 60.0, 62.6, 120.0, 122.6]
    assert t["chunk_count"] == 3 and t["speaker_ids_per_part"] is True
    assert len(t["speakers"]) == 6  # ids are not assumed to match across parts
    job = alice.get(f"/api/v1/meetings/{mid}").json()["latest_job"]
    assert job["progress_total"] == 3


def test_no_timestamps_are_never_invented(alice):
    fake = FakeTranscriber(segments=[RawSegment("Plain text only.")])
    fake.supports_timestamps = False
    orig = fake.transcribe

    def no_ts(*a):
        r = orig(*a)
        r.has_timestamps = r.has_diarization = False
        return r
    fake.transcribe = no_ts
    mid = _upload_and_run(alice, fake)
    t = alice.get(f"/api/v1/meetings/{mid}/transcript").json()
    assert t["has_timestamps"] is False
    assert t["segments"][0]["start_seconds"] is None and t["segments"][0]["speaker_name"] is None
    r = alice.get(f"/api/v1/meetings/{mid}/export/transcript?format=srt")
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_timestamps"


def test_retryable_failure_is_requeued(alice):
    fake = FakeTranscriber(fail=TranscriptionError("Provider busy.", "provider_rate_limited", retryable=True))
    mid = _upload_and_run(alice, fake)
    job = alice.get(f"/api/v1/meetings/{mid}").json()["latest_job"]
    assert job["status"] == "queued" and job["attempts"] == 1 and "Retrying" in job["stage"]
    assert alice.get(f"/api/v1/meetings/{mid}").json()["status"] == "queued"
    with SessionLocal() as db:  # make it due now and exhaust the attempts
        for _ in range(2):
            j = db.get(ProcessingJob, job["id"])
            j.run_after = utcnow() - timedelta(seconds=1)
            db.commit()
            Worker().run_once()
            db.expire_all()
    m = alice.get(f"/api/v1/meetings/{mid}").json()
    assert m["status"] == "failed" and m["error_stage"] == "transcription"
    assert m["error_message"] == "Provider busy." and m["latest_job"]["attempts"] == 3


def test_non_retryable_failure(alice):
    fake = FakeTranscriber(fail=TranscriptionError("The transcription provider rejected the API key.", "provider_auth"))
    mid = _upload_and_run(alice, fake)
    m = alice.get(f"/api/v1/meetings/{mid}").json()
    assert m["status"] == "failed" and m["error_stage"] == "transcription"
    assert m["latest_job"]["error_code"] == "provider_auth" and m["latest_job"]["attempts"] == 1


def test_cancel_queued_job_and_duplicate_prevention(alice):
    transcription.set_transcription_factory(lambda: FakeTranscriber())
    m = alice.meeting()
    job = alice.upload(m["id"], make_wav()).json()["job"]
    r = alice.post(f"/api/v1/meetings/{m['id']}/transcribe")
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_in_progress"
    assert alice.post(f"/api/v1/jobs/{job['id']}/cancel").json()["status"] == "cancelled"
    assert alice.get(f"/api/v1/meetings/{m['id']}").json()["status"] == "cancelled"
    assert Worker().run_once() is False
    assert alice.post(f"/api/v1/meetings/{m['id']}/transcribe").status_code == 202  # can be restarted


def test_transcribe_without_provider_is_503(alice):
    m = alice.meeting()
    alice.upload(m["id"], make_wav())
    r = alice.post(f"/api/v1/meetings/{m['id']}/transcribe")
    assert r.status_code == 503 and r.json()["error"]["code"] == "transcription_not_configured"


def test_stale_running_job_recovered(alice, monkeypatch):
    transcription.set_transcription_factory(lambda: FakeTranscriber())
    m = alice.meeting()
    job = alice.upload(m["id"], make_wav()).json()["job"]
    with SessionLocal() as db:
        j = db.get(ProcessingJob, job["id"])
        j.status, j.attempts, j.locked_at = "running", 1, utcnow() - timedelta(hours=3)
        db.commit()
        assert recover_stale_jobs(db) == 1
        db.expire_all()
        assert db.get(ProcessingJob, job["id"]).status == "queued"
    assert Worker().run_once()
    assert alice.get(f"/api/v1/meetings/{m['id']}").json()["status"] == "transcribed"


# --- OpenAI adapter against a mocked HTTP API ---------------------------------------------------

def _openai_client(handler):
    import openai
    return openai.OpenAI(api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                         max_retries=0)


def test_openai_diarized_request_and_parse(tmp_path):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={"task": "transcribe", "duration": 4.2, "text": "Hi. Hello.", "segments": [
            {"id": "s1", "type": "transcript.text.segment", "start": 0.0, "end": 1.1, "text": "Hi.", "speaker": "A"},
            {"id": "s2", "type": "transcript.text.segment", "start": 1.2, "end": 2.0, "text": "Hello.", "speaker": "B"}]})

    p = tmp_path / "a.wav"
    p.write_bytes(make_wav(1.0))
    prov = OpenAITranscriptionProvider("k", client=_openai_client(handler))
    res = prov.transcribe(str(p), "wav", "en", True)
    assert seen["url"].endswith("/audio/transcriptions")
    body = seen["body"]
    assert b"gpt-4o-transcribe-diarize" in body and b"diarized_json" in body and b'name="chunking_strategy"' in body
    assert [(s.text, s.start, s.speaker) for s in res.segments] == [("Hi.", 0.0, "A"), ("Hello.", 1.2, "B")]
    assert res.has_diarization and res.has_timestamps


def test_openai_text_only_model(tmp_path):
    def handler(request):
        assert b"verbose_json" not in request.content
        return httpx.Response(200, json={"text": "First sentence. Second one! Third? Fourth."})

    p = tmp_path / "a.wav"
    p.write_bytes(make_wav(1.0))
    res = OpenAITranscriptionProvider("k", model="gpt-transcribe", client=_openai_client(handler)).transcribe(
        str(p), "wav", None, True)
    assert not res.has_timestamps and not res.has_diarization
    assert [s.start for s in res.segments] == [None, None]


@pytest.mark.parametrize("status,code,retryable", [(401, "provider_auth", False), (429, "provider_rate_limited", True),
                                                   (500, "provider_error", True), (400, "provider_rejected_audio", False)])
def test_openai_error_mapping(tmp_path, status, code, retryable):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "nope", "type": "x"}})

    p = tmp_path / "a.wav"
    p.write_bytes(make_wav(1.0))
    with pytest.raises(TranscriptionError) as e:
        OpenAITranscriptionProvider("k", client=_openai_client(handler)).transcribe(str(p), "wav", None, True)
    assert e.value.code == code and e.value.retryable is retryable


def test_openai_unreachable(tmp_path):
    def handler(request):
        raise httpx.ConnectError("down")

    p = tmp_path / "a.wav"
    p.write_bytes(make_wav(1.0))
    with pytest.raises(TranscriptionError) as e:
        OpenAITranscriptionProvider("k", client=_openai_client(handler)).transcribe(str(p), "wav", None, True)
    assert e.value.code == "provider_unavailable" and e.value.retryable


def test_status_endpoint_never_returns_keys(alice, monkeypatch):
    set_env(monkeypatch, transcription_provider="openai", transcription_api_key="sk-test-SECRET-value")
    r = alice.get("/api/v1/system/status")
    assert r.status_code == 200
    assert "SECRET" not in json.dumps(r.json())
    assert r.json()["transcription"]["configured"] is True
