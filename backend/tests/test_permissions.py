"""Workspace isolation and role checks, enforced by the API regardless of the frontend."""

from conftest import Account, FakeTranscriber, make_wav

from app import transcription
from app.jobs import Worker


def _processed_meeting(a: Account) -> dict:
    fake = FakeTranscriber()
    transcription.set_transcription_factory(lambda: fake)
    m = a.meeting("Private planning")
    assert a.upload(m["id"], make_wav()).status_code == 201
    assert Worker().run_once()
    return a.get(f"/api/v1/meetings/{m['id']}").json()


def test_other_user_cannot_access_anything(alice, bob):
    m = _processed_meeting(alice)
    mid = m["id"]
    rec_id = m["recording"]["id"]
    seg_id = alice.get(f"/api/v1/meetings/{mid}/transcript").json()["segments"][0]["id"]
    report = alice.post(f"/api/v1/meetings/{mid}/reports", json={"format": "html"}).json()
    action = alice.post("/api/v1/action-items", json={"meeting_id": mid, "title": "Secret task"}).json()

    for url in (f"/api/v1/meetings/{mid}", f"/api/v1/meetings/{mid}/transcript", f"/api/v1/meetings/{mid}/summary",
                f"/api/v1/recordings/{rec_id}/media-url", f"/api/v1/reports/{report['id']}/download",
                f"/api/v1/meetings/{mid}/export/transcript?format=txt", f"/api/v1/meetings/{mid}/jobs"):
        assert bob.get(url).status_code == 404, url
    assert bob.get(f"/api/v1/meetings?workspace_id={alice.workspace_id}").status_code == 404
    assert bob.get(f"/api/v1/action-items?workspace_id={alice.workspace_id}").status_code == 404
    assert bob.get(f"/api/v1/search?workspace_id={alice.workspace_id}&q=beta").status_code == 404
    assert bob.patch(f"/api/v1/segments/{seg_id}", json={"text": "hacked"}).status_code == 404
    assert bob.patch(f"/api/v1/action-items/{action['id']}", json={"status": "completed"}).status_code == 404
    assert bob.delete(f"/api/v1/meetings/{mid}").status_code == 404
    assert bob.upload(mid, make_wav()).status_code == 404
    assert bob.post("/api/v1/meetings", json={"workspace_id": alice.workspace_id, "title": "x"}).status_code == 404
    # Bob's own search does not see Alice's transcript.
    r = bob.get(f"/api/v1/search?workspace_id={bob.workspace_id}&q=beta").json()
    assert r["segments"] == [] and r["meetings"] == []


def test_media_token_bound_to_membership(alice, bob, client):
    m = _processed_meeting(alice)
    url = alice.get(f"/api/v1/recordings/{m['recording']['id']}/media-url").json()["url"]
    assert client.get(url).status_code == 200  # token works without a header
    r = client.get(url, headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    # Removing Alice's access invalidates the token: add Bob as owner, then remove Alice.
    alice.post(f"/api/v1/workspaces/{alice.workspace_id}/members", json={"email": "bob@example.com", "role": "admin"})
    members = alice.get(f"/api/v1/workspaces/{alice.workspace_id}/members").json()
    bob_member = next(x for x in members if x["user_id"] == bob.user["id"])
    alice.patch(f"/api/v1/workspaces/{alice.workspace_id}/members/{bob_member['id']}", json={"role": "owner"})
    alice_member = next(x for x in members if x["user_id"] == alice.user["id"])
    assert alice.delete(f"/api/v1/workspaces/{alice.workspace_id}/members/{alice_member['id']}").status_code == 200
    assert client.get(url).status_code == 404
    assert client.get("/api/v1/media/not-a-valid-token").status_code == 401


def test_viewer_role_is_read_only(alice, bob):
    m = alice.meeting("Shared")
    r = alice.post(f"/api/v1/workspaces/{alice.workspace_id}/members", json={"email": "bob@example.com", "role": "viewer"})
    assert r.status_code == 201
    assert bob.get(f"/api/v1/meetings/{m['id']}").status_code == 200
    assert bob.patch(f"/api/v1/meetings/{m['id']}", json={"title": "x"}).status_code == 403
    assert bob.post("/api/v1/meetings", json={"workspace_id": alice.workspace_id, "title": "x"}).status_code == 403
    assert bob.delete(f"/api/v1/meetings/{m['id']}").status_code == 403


def test_last_owner_protected(alice):
    members = alice.get(f"/api/v1/workspaces/{alice.workspace_id}/members").json()
    r = alice.delete(f"/api/v1/workspaces/{alice.workspace_id}/members/{members[0]['id']}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "last_owner"
    r = alice.delete(f"/api/v1/workspaces/{alice.workspace_id}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "last_workspace"


def test_cross_workspace_project_rejected(alice):
    other = alice.post("/api/v1/workspaces", json={"name": "Second"}).json()
    p = alice.post("/api/v1/projects", json={"workspace_id": other["id"], "name": "Elsewhere"}).json()
    r = alice.post("/api/v1/meetings", json={"workspace_id": alice.workspace_id, "title": "x", "project_id": p["id"]})
    assert r.status_code == 400
