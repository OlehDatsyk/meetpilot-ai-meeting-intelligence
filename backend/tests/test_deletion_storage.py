"""Data deletion, retention, storage backends, demo mode and migrations."""

import os
from datetime import timedelta

import pytest
from conftest import Account, FakeTranscriber, make_wav
from test_analysis import ANALYSIS, FakeAI

from app import ai, transcription
from app.ai import AIClient
from app.db import SessionLocal
from app.jobs import Worker, sweep_retention
from app.models import (ActionItem, AIMessage, Decision, Recording, Report, TranscriptSegment, Workspace)
from app.storage import LocalStorage, S3Storage

STORAGE_FILES = lambda: [f for _, _, fs in os.walk(os.environ["STORAGE_ROOT"]) for f in fs]  # noqa: E731


def _full_meeting(account):
    transcription.set_transcription_factory(lambda: FakeTranscriber())
    ai.set_ai_factory(lambda: AIClient([FakeAI(payload=ANALYSIS, text="Beta ships Friday [S1].")]))
    m = account.meeting("To delete")
    account.upload(m["id"], make_wav())
    Worker().run_once()
    Worker().run_once()
    account.post(f"/api/v1/meetings/{m['id']}/reports", json={"format": "pdf"})
    conv = account.post("/api/v1/assistant/conversations", json={"workspace_id": account.workspace_id}).json()
    account.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"content": "beta release notes"})
    return m["id"], conv["id"]


def test_delete_meeting_removes_all_derived_data(alice):
    mid, conv = _full_meeting(alice)
    assert len(STORAGE_FILES()) == 2  # recording + report
    assert alice.delete(f"/api/v1/meetings/{mid}").status_code == 200
    assert STORAGE_FILES() == []
    with SessionLocal() as db:
        for model in (TranscriptSegment, ActionItem, Decision, Recording, Report):
            assert db.query(model).count() == 0, model.__name__
        answer = db.query(AIMessage).filter(AIMessage.role == "assistant").one()
        assert "removed" in answer.content and answer.citations == []
    assert alice.get(f"/api/v1/meetings/{mid}").status_code == 404
    activity = alice.get(f"/api/v1/workspaces/{alice.workspace_id}/activity").json()
    assert all("To delete" not in a["summary"] for a in activity)


def test_delete_audio_only_keeps_transcript(alice, client):
    mid, _ = _full_meeting(alice)
    rec = alice.get(f"/api/v1/meetings/{mid}").json()["recording"]
    url = alice.get(f"/api/v1/recordings/{rec['id']}/media-url").json()["url"]
    assert alice.delete(f"/api/v1/recordings/{rec['id']}/audio").status_code == 200
    m = alice.get(f"/api/v1/meetings/{mid}").json()
    assert m["recording"]["audio_available"] is False and m["recording"]["audio_deleted_reason"] == "user"
    assert alice.get(f"/api/v1/meetings/{mid}/transcript").status_code == 200
    assert client.get(url).status_code == 404
    assert alice.get(f"/api/v1/recordings/{rec['id']}/media-url").status_code == 410
    assert len(STORAGE_FILES()) == 1  # only the report remains


def test_delete_workspace_and_account(client):
    a = Account(client, "wipe@example.com")
    second = a.post("/api/v1/workspaces", json={"name": "Second"}).json()
    _full_meeting(a)
    assert len(STORAGE_FILES()) == 2
    assert a.delete(f"/api/v1/workspaces/{a.workspace_id}").status_code == 200
    assert STORAGE_FILES() == []
    a.workspace_id = second["id"]
    _full_meeting(a)
    assert a.delete("/api/v1/auth/me", json={"password": a.password}).status_code == 200
    assert STORAGE_FILES() == []
    with SessionLocal() as db:
        assert db.query(Workspace).count() == 0


def test_retention_sweep(alice):
    mid, _ = _full_meeting(alice)
    alice.patch(f"/api/v1/workspaces/{alice.workspace_id}", json={"recording_retention_days": 7})
    with SessionLocal() as db:
        assert sweep_retention(db) == 0
        rec = db.query(Recording).one()
        rec.created_at = rec.created_at - timedelta(days=8)
        db.commit()
        assert sweep_retention(db) == 1
    m = alice.get(f"/api/v1/meetings/{mid}").json()
    assert m["recording"]["audio_deleted_reason"] == "retention"
    assert alice.get(f"/api/v1/meetings/{mid}/transcript").status_code == 200


def test_local_storage_rejects_traversal(tmp_path):
    s = LocalStorage(str(tmp_path / "root"))
    for bad in ("../x", "/etc/passwd", "a/../../b", "a\\b"):
        with pytest.raises(ValueError):
            s.save_bytes(bad, b"x", "text/plain")
    s.save_bytes("ok/file.txt", b"hello", "text/plain")
    assert s.read_bytes("ok/file.txt") == b"hello" and s.size("ok/file.txt") == 5
    with s.local_copy("ok/file.txt") as p:
        assert open(p, "rb").read() == b"hello"
    s.delete("ok/file.txt")
    assert not s.exists("ok/file.txt")


def test_s3_storage_with_moto(tmp_path, monkeypatch):
    moto = pytest.importorskip("moto")
    import boto3
    from conftest import set_env
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with moto.mock_aws():
        client = boto3.client("s3", region_name="eu-central-1")
        client.create_bucket(Bucket="meetpilot-test", CreateBucketConfiguration={"LocationConstraint": "eu-central-1"})
        set_env(monkeypatch, s3_bucket="meetpilot-test", s3_region="eu-central-1")
        from app.config import get_settings
        s = S3Storage(get_settings(), client=client)
        src = tmp_path / "a.wav"
        src.write_bytes(make_wav(0.5))
        s.save_file("recordings/w/m/a.wav", str(src), "audio/wav")
        assert s.exists("recordings/w/m/a.wav") and s.size("recordings/w/m/a.wav") == src.stat().st_size
        with s.local_copy("recordings/w/m/a.wav") as p:
            assert open(p, "rb").read() == src.read_bytes()
            local = p
        assert not os.path.exists(local)  # temporary copy cleaned up
        url = s.presigned_url("recordings/w/m/a.wav", "audio/wav", 60)
        assert "X-Amz-Expires=60" in url and "meetpilot/recordings" in url
        s.check()
        s.delete("recordings/w/m/a.wav")
        assert not s.exists("recordings/w/m/a.wav")


def test_public_demo_and_demo_workspace(client):
    r = client.get("/api/v1/demo")
    assert r.status_code == 200
    data = r.json()
    assert "Fictional" in data["notice"] and len(data["meetings"]) == 2
    m = data["meetings"][0]
    assert m["segments"][0]["speaker_name"] == "Maya (Product)" and m["action_items"]
    seg_ids = {s["id"] for s in m["segments"]}
    for a in m["action_items"]:  # every demo action points at real demo transcript lines
        assert a["source_segment_ids"] and set(a["source_segment_ids"]) <= seg_ids
    assert any(a["owner"] is None for a in m["action_items"])
    html = client.get("/api/v1/demo/report.html")
    assert html.status_code == 200 and "Demo content" in html.text

    a = Account(client, "demo@example.com")
    ws_id = a.post("/api/v1/demo/workspace").json()["message"]
    assert a.post("/api/v1/demo/workspace").json()["message"] == ws_id  # created once
    ws = [w for w in a.get("/api/v1/workspaces").json() if w["id"] == ws_id][0]
    assert ws["is_demo"] and "fictional" in ws["name"].lower()
    meetings = a.get(f"/api/v1/meetings?workspace_id={ws_id}").json()["items"]
    assert len(meetings) == 2 and all(m["is_demo"] for m in meetings)
    mid = meetings[0]["id"]
    assert a.post(f"/api/v1/meetings/{mid}/reports", json={"format": "pdf"}).status_code == 201
    assert a.get(f"/api/v1/meetings/{mid}/transcript").json()["has_diarization"]
    assert a.delete(f"/api/v1/workspaces/{ws_id}").status_code == 200


def test_migrations_match_models(tmp_path, monkeypatch):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext

    from app.config import get_settings
    from app.db import Base, get_engine, reset_engine
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path.as_posix()}/migrated.db")
    get_settings.cache_clear()
    reset_engine()
    here = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "alembic"))
    command.upgrade(cfg, "head")
    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
