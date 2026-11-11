"""Transcript editing, speakers, action items, decisions, search, assistant, reports and analytics."""

import json
from datetime import date, timedelta

from conftest import FakeTranscriber, make_wav
from test_analysis import ANALYSIS, FakeAI

from app import ai, transcription
from app.ai import AIClient
from app.jobs import Worker


def _meeting(account, analyse=True, title="Beta planning"):
    transcription.set_transcription_factory(lambda: FakeTranscriber())
    if analyse:
        ai.set_ai_factory(lambda: AIClient([FakeAI(payload=ANALYSIS)]))
    m = account.meeting(title)
    account.upload(m["id"], make_wav())
    Worker().run_once()
    if analyse:
        Worker().run_once()
    ai.set_ai_factory(None)
    return m["id"]


def test_edit_segment_preserves_original(alice):
    mid = _meeting(alice, analyse=False)
    t = alice.get(f"/api/v1/meetings/{mid}/transcript").json()
    seg = t["segments"][0]
    r = alice.patch(f"/api/v1/segments/{seg['id']}", json={"text": "Let's agree to ship the beta on Thursday."})
    assert r.status_code == 200
    body = r.json()
    assert body["edited"] and body["text"].endswith("Thursday.") and body["original_text"].endswith("Friday.")
    assert body["edited_at"]
    assert alice.get(f"/api/v1/meetings/{mid}/transcript").json()["edited_at"]
    reverted = alice.patch(f"/api/v1/segments/{seg['id']}", json={"revert": True}).json()
    assert reverted["text"] == reverted["original_text"] and not reverted["edited"]


def test_rename_and_reassign_speakers(alice):
    mid = _meeting(alice, analyse=False)
    t = alice.get(f"/api/v1/meetings/{mid}/transcript").json()
    sp1, sp2 = t["speakers"]
    r = alice.patch(f"/api/v1/speakers/{sp1['id']}", json={"display_name": "Maya"})
    assert r.json()["name"] == "Maya" and r.json()["label"] == "A"  # original id preserved
    t = alice.get(f"/api/v1/meetings/{mid}/transcript").json()
    assert t["segments"][0]["speaker_name"] == "Maya"
    seg2 = t["segments"][1]
    r = alice.patch(f"/api/v1/segments/{seg2['id']}", json={"speaker_id": sp1["id"]})
    assert r.json()["speaker_name"] == "Maya"
    other = _meeting(alice, analyse=False, title="Other")
    other_sp = alice.get(f"/api/v1/meetings/{other}/transcript").json()["speakers"][0]
    assert alice.patch(f"/api/v1/segments/{seg2['id']}", json={"speaker_id": other_sp["id"]}).status_code == 400
    cleared = alice.patch(f"/api/v1/speakers/{sp1['id']}", json={"display_name": ""}).json()
    assert cleared["name"] == "Speaker 1" and cleared["display_name"] is None


def test_action_items_crud_and_filters(alice):
    mid = _meeting(alice)
    base = f"/api/v1/action-items?workspace_id={alice.workspace_id}"
    items = alice.get(base).json()["items"]
    assert len(items) == 2
    assert alice.get(base + "&owner=unassigned").json()["total"] == 1
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    a = alice.post("/api/v1/action-items", json={"meeting_id": mid, "title": "Late task", "owner": "Sam",
                                                 "due_date": yesterday, "priority": "low"}).json()
    assert a["overdue"] and a["owner_source"] == "user" and a["priority_source"] == "user"
    assert alice.get(base + "&overdue=true").json()["total"] == 1
    done = alice.patch(f"/api/v1/action-items/{a['id']}", json={"status": "completed", "notes": "Done early"}).json()
    assert done["status"] == "completed" and done["completed_at"] and not done["overdue"]
    assert alice.get(base + "&status=completed").json()["total"] == 1
    assert alice.get(base + "&q=early").json()["total"] == 1
    cleared = alice.patch(f"/api/v1/action-items/{a['id']}", json={"clear_owner": True, "clear_due_date": True}).json()
    assert cleared["owner"] is None and cleared["due_date"] is None
    assert alice.get(base + "&sort=priority").status_code == 200
    assert alice.delete(f"/api/v1/action-items/{a['id']}").status_code == 200


def test_decisions_review(alice):
    _meeting(alice)
    base = f"/api/v1/decisions?workspace_id={alice.workspace_id}"
    d = alice.get(base).json()["items"][0]
    assert d["meeting_status"] == "confirmed" and d["review_status"] == "unreviewed" and d["excerpt"]
    r = alice.patch(f"/api/v1/decisions/{d['id']}", json={"review_status": "confirmed"}).json()
    assert r["review_status"] == "confirmed" and r["user_modified"]
    assert alice.get(base + "&review_status=unreviewed").json()["total"] == 0


def test_search_across_records(alice):
    mid = _meeting(alice)
    alice.post("/api/v1/projects", json={"workspace_id": alice.workspace_id, "name": "Beta launch"})
    r = alice.get(f"/api/v1/search?workspace_id={alice.workspace_id}&q=release notes").json()
    assert r["segments"] and r["segments"][0]["meeting_id"] == mid
    assert r["action_items"][0]["title"] == "Write the release notes"
    r = alice.get(f"/api/v1/search?workspace_id={alice.workspace_id}&q=beta").json()
    assert r["meetings"] and r["projects"] and r["decisions"]
    # LIKE wildcards are escaped
    assert alice.get(f"/api/v1/search?workspace_id={alice.workspace_id}&q=%25%25").json()["segments"] == []


def test_meeting_list_filters_and_sort(alice):
    for t in ("Zeta review", "Alpha kickoff"):
        alice.meeting(t)
    base = f"/api/v1/meetings?workspace_id={alice.workspace_id}"
    assert [m["title"] for m in alice.get(base + "&sort=title_asc").json()["items"]] == ["Alpha kickoff", "Zeta review"]
    assert alice.get(base + "&q=zeta").json()["total"] == 1
    assert alice.get(base + "&status=draft").json()["total"] == 2
    assert alice.get(base + "&page_size=1&page=2").json()["items"][0]["title"]


def test_assistant_with_ai_cites_sources(alice):
    mid = _meeting(alice)
    fake = FakeAI(text="The team agreed to ship the beta on Friday [S1]. Dana owns the notes [A1] [Z9].")
    ai.set_ai_factory(lambda: AIClient([fake]))
    conv = alice.post("/api/v1/assistant/conversations", json={"workspace_id": alice.workspace_id}).json()
    r = alice.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                   json={"content": "What did we decide about the beta and who owns the action items?"})
    assert r.status_code == 200, r.text
    answer = r.json()[1]
    assert answer["mode"] == "ai"
    labels = [c["label"] for c in answer["citations"]]
    assert labels == ["S1", "A1"]  # unknown [Z9] ignored
    assert answer["citations"][0]["meeting_id"] == mid
    prompt = fake.prompts[-1]
    assert "[S1]" in prompt and "Alice Example" in prompt
    detail = alice.get(f"/api/v1/assistant/conversations/{conv['id']}").json()
    assert len(detail["messages"]) == 2 and detail["title"].startswith("What did we decide")


def test_assistant_without_ai_returns_matches_only(alice, bob):
    _meeting(alice)
    conv = alice.post("/api/v1/assistant/conversations", json={"workspace_id": alice.workspace_id}).json()
    ans = alice.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"content": "release notes"}).json()[1]
    assert ans["mode"] == "retrieval_only" and ans["citations"]
    nothing = alice.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                         json={"content": "kangaroo budget"}).json()[1]
    assert nothing["mode"] == "no_results" and nothing["citations"] == []
    # Bob cannot use Alice's conversation, and his own workspace has no access to her meetings.
    assert bob.get(f"/api/v1/assistant/conversations/{conv['id']}").status_code == 404
    bconv = bob.post("/api/v1/assistant/conversations", json={"workspace_id": bob.workspace_id}).json()
    bans = bob.post(f"/api/v1/assistant/conversations/{bconv['id']}/messages", json={"content": "release notes"}).json()[1]
    assert bans["mode"] == "no_results"
    assert bob.post("/api/v1/assistant/conversations", json={"workspace_id": alice.workspace_id}).status_code == 404


def test_reports_and_exports(alice):
    mid = _meeting(alice)
    alice.patch(f"/api/v1/meetings/{mid}", json={"title": "<script>alert(1)</script> Plan"})
    alice.post("/api/v1/action-items", json={"meeting_id": mid, "title": "=HYPERLINK(\"http://x\")",
                                             "due_date": "2027-02-01"})
    pdf = alice.post(f"/api/v1/meetings/{mid}/reports", json={"format": "pdf", "include_transcript": True}).json()
    html = alice.post(f"/api/v1/meetings/{mid}/reports", json={"format": "html"}).json()
    r = alice.get(f"/api/v1/reports/{pdf['id']}/download")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "attachment" in r.headers["content-disposition"]
    r = alice.get(f"/api/v1/reports/{html['id']}/download")
    text = r.text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text
    assert "sandbox" in r.headers["content-security-policy"]
    assert "Executive summary" in text and "Write the release notes" in text
    assert len(alice.get(f"/api/v1/reports?workspace_id={alice.workspace_id}").json()) == 2
    csv_text = alice.get(f"/api/v1/meetings/{mid}/export/action-items?format=csv").text
    assert "'=HYPERLINK" in csv_text  # formula injection neutralised
    srt = alice.get(f"/api/v1/meetings/{mid}/export/transcript?format=srt").text
    assert "00:00:00,000 --> 00:00:02,500" in srt and "Speaker 1:" in srt
    assert "WEBVTT" in alice.get(f"/api/v1/meetings/{mid}/export/transcript?format=vtt").text
    js = json.loads(alice.get(f"/api/v1/meetings/{mid}/export/transcript?format=json").text)
    assert js["segments"][0]["original_text"]
    md = alice.get(f"/api/v1/meetings/{mid}/export/summary?format=md").text
    assert "## Decisions" in md and "No deadline specified" in md
    ics = alice.get(f"/api/v1/meetings/{mid}/export/action-items?format=ics").text
    assert "BEGIN:VEVENT" in ics and "DTSTART;VALUE=DATE:20270201" in ics
    assert alice.get(f"/api/v1/exports/action-items?workspace_id={alice.workspace_id}&format=md").status_code == 200
    assert alice.get(f"/api/v1/exports/decisions?workspace_id={alice.workspace_id}&format=csv").status_code == 200
    direct = alice.get(f"/api/v1/meetings/{mid}/export/report?format=pdf")
    assert direct.content.startswith(b"%PDF")


def test_pdf_handles_non_latin_text(alice):
    m = alice.meeting("Планування релізу — 計画")
    r = alice.get(f"/api/v1/meetings/{m['id']}/export/report?format=pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and b"DejaVuSans" in r.content


def test_dashboard_and_analytics_from_real_records(alice):
    assert alice.get(f"/api/v1/analytics?workspace_id={alice.workspace_id}").json()["processing"]["success_rate"] is None
    mid = _meeting(alice)
    d = alice.get(f"/api/v1/dashboard?workspace_id={alice.workspace_id}").json()
    assert d["stats"]["total_meetings"] == 1 and d["stats"]["meetings_processed"] == 1
    assert d["stats"]["actions_outstanding"] == 2 and d["stats"]["decisions_recorded"] == 1
    assert abs(d["stats"]["total_duration_seconds"] - 2.0) < 0.01
    assert sum(w["meetings"] for w in d["meetings_per_week"]) == 1
    assert d["recent_meetings"][0]["id"] == mid and d["recent_activity"]
    a = alice.get(f"/api/v1/analytics?workspace_id={alice.workspace_id}").json()
    assert a["processing"] == {"finished_jobs": 2, "succeeded": 2, "failed": 0, "success_rate": 1.0,
                               "by_kind": a["processing"]["by_kind"]}
    assert a["totals"]["actions_created"] == 2 and a["totals"]["average_duration_seconds"]


def test_projects_progress(alice):
    p = alice.post("/api/v1/projects", json={"workspace_id": alice.workspace_id, "name": "Launch"}).json()
    mid = _meeting(alice)
    alice.patch(f"/api/v1/meetings/{mid}", json={"project_id": p["id"]})
    items = alice.get(f"/api/v1/action-items?workspace_id={alice.workspace_id}").json()["items"]
    alice.patch(f"/api/v1/action-items/{items[0]['id']}", json={"status": "completed"})
    proj = alice.get(f"/api/v1/projects/{p['id']}").json()
    assert (proj["meeting_count"], proj["action_total"], proj["action_completed"], proj["decision_count"]) == (1, 2, 1, 1)
    alice.delete(f"/api/v1/projects/{p['id']}")
    assert alice.get(f"/api/v1/meetings/{mid}").json()["project_id"] is None
