"""Demo mode: clearly labelled fictional meetings. No real people, companies or recordings are used.

The content was written for this project. It powers two things:
- a public, read-only demo page (no account, no AI provider needed), and
- an optional "Demo workspace" a signed-in user can create to try editing, exports and reports.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from . import activity
from .models import (ActionItem, Decision, Meeting, MeetingSummary, Participant, Project, Speaker, Transcript,
                     TranscriptSegment, Workspace, WorkspaceMember, new_id)

DEMO_NOTICE = "Fictional demo data. The people, company and conversation are invented."


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _next_weekday(d: date, weekday: int) -> date:
    days = (weekday - d.weekday()) % 7
    return d + timedelta(days=days or 7)


def build_demo(now: datetime | None = None) -> dict[str, Any]:
    """The fictional dataset, with dates relative to `now` so deadlines stay meaningful."""
    now = now or datetime.now(timezone.utc)
    m1_date = (now - timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
    m2_date = (now - timedelta(days=9)).replace(hour=10, minute=30, second=0, microsecond=0)
    friday = _next_weekday(m1_date.date(), 4)
    freeze = m1_date.date() + timedelta(days=16)
    freeze_text = f"{freeze.strftime('%B')} {_ordinal(freeze.day)}"
    launch = freeze + timedelta(days=7)
    launch_text = f"{launch.strftime('%B')} {_ordinal(launch.day)}"

    speakers = [("A", "Maya (Product)"), ("B", "Daniel (Engineering)"), ("C", "Priya (Design)"), ("D", None)]
    lines = [
        ("A", "Okay, let's get started. The goal today is to lock the scope for the Orbitkit 2.4 release and agree "
              "on the timeline."),
        ("A", f"Marketing has asked for a public launch on {launch_text}, so I'd like to work backwards from that."),
        ("B", f"From the engineering side, the offline sync rewrite is the big item. If we want a code freeze on "
              f"{freeze_text}, offline sync has to be feature complete by the end of next week."),
        ("C", "Design for offline states is about eighty percent done. The empty state and the conflict dialog still "
              "need review."),
        ("A", "Priya, can you get the conflict dialog designs into review by Friday?"),
        ("C", "Yes, I'll have the conflict dialog ready for review by Friday."),
        ("D", "One concern from support. The current sync bug is our number one ticket driver. If 2.4 slips, can we "
              "ship a hotfix for the duplicate-entries issue separately?"),
        ("B", "We could, but a hotfix would touch the same code we're rewriting. I'd rather not maintain two versions."),
        ("A", "Let's decide that now. Do we agree to skip the hotfix and put everything into 2.4?"),
        ("B", "I agree, as long as the freeze date holds."),
        ("D", "Okay from support, if we publish a known-issue article this week."),
        ("A", "Great, so decided: no separate hotfix, the fix ships in 2.4. Can you write that known-issue article?"),
        ("D", "Sure, I'll publish it this week."),
        ("A", "Next, the dark mode request. It keeps coming up in feedback."),
        ("C", "I'd propose we move dark mode to 2.5. Doing it properly means auditing every colour token."),
        ("B", "Agreed, it's too big to squeeze in."),
        ("A", "Fine, dark mode moves to 2.5. That's decided."),
        ("B", "There is a risk I want to flag. The iOS background refresh limits might stop sync from finishing on "
              "large accounts. We haven't tested with more than ten thousand records."),
        ("A", "That's important. Daniel, can you run a load test with a large account before the freeze?"),
        ("B", "Yes. I'll set up a test account with fifty thousand records and report back at next week's sync."),
        ("C", "Should we also show a progress indicator during the first sync? Users might think the app froze."),
        ("A", "Good idea, but I'm not sure we have time. Let's think about it and revisit next week."),
        ("D", "One more question: do we know if the Android team can match the same freeze date?"),
        ("A", "I don't know yet. I'll ask their lead today."),
        ("A", "Someone also needs to update the release notes draft once scope is final."),
        ("B", "It's urgent that we get the beta build to testers early, ideally right after the freeze."),
        ("A", "Agreed. Let's wrap up. Thanks everyone."),
    ]
    starts = [0, 14, 24, 41, 55, 61, 67, 84, 95, 102, 106, 113, 121, 125, 131, 141, 145, 151, 166, 173, 182, 192,
              199, 206, 211, 219, 227]
    segs = []
    for i, ((sp, text), start) in enumerate(zip(lines, starts, strict=True), 1):
        end = starts[i] - 0.5 if i < len(starts) else start + 6
        segs.append({"position": i, "speaker": sp, "text": text, "start": float(start * 3), "end": float(end * 3)})

    m1 = {
        "key": "m1",
        "title": "Orbitkit 2.4 release planning",
        "description": "Scope and timeline for the 2.4 mobile release. " + DEMO_NOTICE,
        "date": m1_date,
        "duration": segs[-1]["end"] + 4.0,
        "participants": [("Maya Chen", "Product lead"), ("Daniel Okafor", "Engineering lead"),
                         ("Priya Raman", "Product designer"), ("Tom Weiss", "Support")],
        "speakers": speakers,
        "segments": segs,
        "summary": {
            "executive": (f"The team set the scope for the Orbitkit 2.4 release, working back from a requested "
                          f"public launch on {launch_text} with a code freeze on {freeze_text}. They agreed to ship "
                          "the duplicate-entries sync fix inside 2.4 instead of a separate hotfix, and to move dark "
                          "mode to 2.5. A risk was raised that iOS background refresh limits could stop sync on large "
                          "accounts; a load test was assigned. Whether the Android team can meet the same freeze "
                          "date is still unknown."),
            "points": [
                {"topic": "Release timeline", "summary": f"Launch requested for {launch_text}; code freeze on "
                                                         f"{freeze_text}.", "segs": [2, 3]},
                {"topic": "Offline sync rewrite", "summary": "Must be feature complete by the end of next week to "
                                                             "hold the freeze.", "segs": [3]},
                {"topic": "Hotfix versus 2.4", "summary": "Support asked for a separate hotfix; engineering preferred "
                                                          "not to maintain two code paths.", "segs": [7, 8, 9]},
                {"topic": "Dark mode", "summary": "Too large for 2.4 because every colour token needs an audit.",
                 "segs": [14, 15, 16]},
                {"topic": "First-sync experience", "summary": "A progress indicator was suggested but not agreed.",
                 "segs": [21, 22]},
            ],
            "questions": [
                {"text": "Can the Android team match the same code freeze date?", "segs": [23, 24]},
                {"text": "Should the first sync show a progress indicator?", "segs": [21, 22]},
            ],
            "risks": [
                {"text": "iOS background refresh limits might stop sync from finishing on large accounts; untested "
                         "above ten thousand records.", "segs": [18]},
                {"text": "The freeze depends on offline sync being feature complete by the end of next week.",
                 "segs": [3]},
            ],
            "follow_ups": [
                {"text": "Review the large-account load test results at next week's sync.", "segs": [20]},
                {"text": "Revisit the first-sync progress indicator next week.", "segs": [22]},
            ],
            "key_dates": [
                {"date_text": launch_text, "date": launch.isoformat(), "interpreted": False,
                 "description": "Requested public launch", "segs": [2]},
                {"date_text": freeze_text, "date": freeze.isoformat(), "interpreted": False,
                 "description": "Code freeze", "segs": [3]},
                {"date_text": "by Friday", "date": friday.isoformat(), "interpreted": True,
                 "description": "Conflict dialog designs ready for review", "segs": [5, 6]},
            ],
            "notes": ["Owner “Support team” for “Update the release notes draft” was not found "
                      "in the cited lines and was removed."],
        },
        "decisions": [
            {"title": "Ship the duplicate-entries fix in 2.4 instead of a separate hotfix",
             "description": "The fix for the duplicate-entries sync bug ships with 2.4. Support will publish a "
                            "known-issue article in the meantime.",
             "status": "confirmed", "people": [], "segs": [9, 10, 11, 12]},
            {"title": "Move dark mode to release 2.5", "description": "Dark mode needs a full colour-token audit and "
                                                                     "does not fit in 2.4.",
             "status": "confirmed", "people": ["Priya (Design)"], "segs": [15, 16, 17]},
            {"title": "Show a progress indicator during the first sync", "description": "Suggested to avoid users "
                     "thinking the app froze. Not agreed; to be revisited.",
             "status": "proposed", "people": [], "segs": [21, 22]},
        ],
        "actions": [
            {"title": "Get the conflict dialog designs into review", "description": "Finish the offline conflict "
             "dialog designs and share them for review.", "owner": "Priya", "due": friday, "due_text": "by Friday",
             "due_source": "ai_interpreted", "priority": None, "priority_source": None, "needs": True,
             "status": "in_progress", "segs": [5, 6]},
            {"title": "Run a load test with a 50,000-record account", "description": "Check whether sync completes "
             "within iOS background refresh limits. Report back at next week's sync.", "owner": "Daniel",
             "due": freeze, "due_text": "before the freeze", "due_source": "ai_interpreted", "priority": "high",
             "priority_source": "ai_suggested", "needs": True, "status": "todo", "segs": [19, 20]},
            {"title": "Publish a known-issue article for the duplicate-entries bug", "description": "Agreed as the "
             "condition for skipping a separate hotfix.", "owner": "Speaker 4", "due": friday,
             "due_text": "this week", "due_source": "ai_interpreted", "priority": None, "priority_source": None,
             "needs": True, "status": "todo", "segs": [11, 12, 13]},
            {"title": "Ask the Android lead whether they can match the freeze date", "description": "",
             "owner": "Maya (Product)", "due": m1_date.date(), "due_text": "today", "due_source": "ai_interpreted", "priority": None,
             "priority_source": None, "needs": False, "status": "completed", "segs": [23, 24]},
            {"title": "Update the release notes draft once scope is final", "description": "No one was named for "
             "this task.", "owner": None, "due": None, "due_text": None, "due_source": None, "priority": None,
             "priority_source": None, "needs": True, "status": "todo", "segs": [25]},
            {"title": "Get the beta build to testers right after the freeze", "description": "", "owner": None,
             "due": None, "due_text": None, "due_source": None, "priority": "high", "priority_source": "stated",
             "needs": True, "status": "todo", "segs": [26]},
        ],
    }
    m2_lines = [
        ("A", "Quick design sync. Priya, where are we on the onboarding illustrations?"),
        ("C", "Final versions are uploaded. I still need sign-off on the third screen."),
        ("A", "I've looked at it and it's approved. Let's use the new set in 2.4."),
        ("B", "I'll swap the assets in the app once they're exported. Should take a day."),
        ("C", "Exports will be in the shared folder this afternoon."),
        ("A", "Perfect. That's all for today."),
    ]
    m2_segs = [{"position": i, "speaker": sp, "text": t, "start": float((i - 1) * 25), "end": float(i * 25 - 1)}
               for i, (sp, t) in enumerate(m2_lines, 1)]
    m2 = {
        "key": "m2",
        "title": "Weekly design sync",
        "description": "Short weekly check-in between product, design and engineering. " + DEMO_NOTICE,
        "date": m2_date,
        "duration": 2 * 60 + 31.0,
        "participants": [("Maya Chen", "Product lead"), ("Daniel Okafor", "Engineering lead"),
                         ("Priya Raman", "Product designer")],
        "speakers": speakers[:3],
        "segments": m2_segs,
        "summary": {
            "executive": "The onboarding illustrations were approved for 2.4. Design will export the assets the same "
                         "afternoon and engineering will swap them into the app.",
            "points": [{"topic": "Onboarding illustrations", "summary": "Final set approved, including the third "
                                                                        "screen.", "segs": [1, 2, 3]}],
            "questions": [], "risks": [],
            "follow_ups": [{"text": "Confirm the new illustrations appear in the 2.4 beta build.", "segs": [4]}],
            "key_dates": [], "notes": [],
        },
        "decisions": [{"title": "Use the new onboarding illustrations in 2.4", "description": "",
                       "status": "confirmed", "people": ["Maya (Product)"], "segs": [3]}],
        "actions": [
            {"title": "Export the onboarding illustrations to the shared folder", "description": "",
             "owner": "Priya (Design)", "due": m2_date.date(), "due_text": "this afternoon",
             "due_source": "ai_interpreted", "priority": None, "priority_source": None, "needs": False,
             "status": "completed", "segs": [5]},
            {"title": "Swap the new onboarding assets into the app", "description": "", "owner": "Daniel (Engineering)",
             "due": None, "due_text": None, "due_source": None, "priority": None, "priority_source": None,
             "needs": False, "status": "completed", "segs": [4]},
        ],
    }
    return {"project": {"name": "Orbitkit 2.4 (demo)", "description": "Fictional mobile app release used for the "
                                                                       "demo."},
            "meetings": [m1, m2], "notice": DEMO_NOTICE}


def seed_demo_workspace(db: Session, user_id: str) -> Workspace:
    data = build_demo()
    ws = Workspace(name="Demo workspace (fictional)", is_demo=True, created_by=user_id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user_id, role="owner"))
    project = Project(workspace_id=ws.id, name=data["project"]["name"], description=data["project"]["description"],
                      created_by=user_id)
    db.add(project)
    db.flush()
    for md in data["meetings"]:
        m = Meeting(workspace_id=ws.id, project_id=project.id, title=md["title"], description=md["description"],
                    meeting_date=md["date"], duration_seconds=md["duration"], status="completed", is_demo=True,
                    created_by=user_id)
        m.participants = [Participant(name=n, role=r) for n, r in md["participants"]]
        db.add(m)
        db.flush()
        sp_map: dict[str, Speaker] = {}
        for i, (label, name) in enumerate(md["speakers"], 1):
            sp = Speaker(meeting_id=m.id, label=label, ordinal=i, display_name=name)
            db.add(sp)
            sp_map[label] = sp
        db.flush()
        pos_to_id: dict[int, str] = {}
        for s in md["segments"]:
            seg = TranscriptSegment(id=new_id(), meeting_id=m.id, workspace_id=ws.id, position=s["position"],
                                    start_seconds=s["start"], end_seconds=s["end"], speaker_id=sp_map[s["speaker"]].id,
                                    original_text=s["text"], text=s["text"])
            db.add(seg)
            pos_to_id[s["position"]] = seg.id
        db.add(Transcript(meeting_id=m.id, provider="demo", model="fictional sample", language="en",
                          has_timestamps=True, has_diarization=True, chunk_count=1, created_at=md["date"]))

        def ids(segs: list[int]) -> list[str]:
            return [pos_to_id[p] for p in segs if p in pos_to_id]

        def excerpt(segs: list[int]) -> str:
            by = {s["position"]: s for s in md["segments"]}
            names = dict(md["speakers"])
            return " ".join(f"{names.get(by[p]['speaker']) or 'Speaker ' + str(list(names).index(by[p]['speaker']) + 1)}: "
                            f"{by[p]['text']}" for p in segs[:3] if p in by)

        s = md["summary"]
        db.add(MeetingSummary(
            meeting_id=m.id, executive_summary=s["executive"],
            discussion_points=[{"topic": x["topic"], "summary": x["summary"], "segment_ids": ids(x["segs"])}
                               for x in s["points"]],
            open_questions=[{"text": x["text"], "segment_ids": ids(x["segs"])} for x in s["questions"]],
            risks=[{"text": x["text"], "segment_ids": ids(x["segs"])} for x in s["risks"]],
            follow_ups=[{"text": x["text"], "segment_ids": ids(x["segs"])} for x in s["follow_ups"]],
            key_dates=[{"date_text": k["date_text"], "date": k["date"], "interpreted": k["interpreted"],
                        "description": k["description"], "segment_ids": ids(k["segs"])} for k in s["key_dates"]],
            grounding_notes=s["notes"], provider="demo", model="fictional sample", chunked=False))
        for d in md["decisions"]:
            db.add(Decision(meeting_id=m.id, workspace_id=ws.id, title=d["title"], description=d["description"],
                            meeting_status=d["status"], participants=d["people"], source_segment_ids=ids(d["segs"]),
                            excerpt=excerpt(d["segs"]), origin="ai"))
        for a in md["actions"]:
            completed = m.meeting_date + timedelta(days=1) if a["status"] == "completed" else None
            db.add(ActionItem(meeting_id=m.id, workspace_id=ws.id, title=a["title"], description=a["description"],
                              owner=a["owner"], owner_source="transcript" if a["owner"] else None, due_date=a["due"],
                              due_text=a["due_text"] if a["due"] else None, due_source=a["due_source"] if a["due"] else None,
                              priority=a["priority"], priority_source=a["priority_source"],
                              needs_confirmation=a["needs"], status=a["status"], source_segment_ids=ids(a["segs"]),
                              excerpt=excerpt(a["segs"]), origin="ai", completed_at=completed,
                              created_at=m.meeting_date + timedelta(minutes=20)))
    activity.record(db, ws.id, "demo_created", "Demo workspace created with fictional sample meetings",
                    user_id=user_id)
    db.flush()
    return ws


def public_demo_payload() -> dict[str, Any]:
    """Read-only demo for visitors without an account. Shaped like the API's meeting responses."""
    data = build_demo()
    meetings = []
    for md in data["meetings"]:
        names = {label: (name or f"Speaker {i}") for i, (label, name) in enumerate(md["speakers"], 1)}
        seg_id = {s["position"]: f"demo-{md['key']}-{s['position']}" for s in md["segments"]}

        def ids(segs: list[int]) -> list[str]:
            return [seg_id[p] for p in segs if p in seg_id]

        s = md["summary"]
        meetings.append({
            "id": f"demo-{md['key']}", "title": md["title"], "description": md["description"],
            "meeting_date": md["date"], "duration_seconds": md["duration"], "project_name": data["project"]["name"],
            "participants": [{"name": n, "role": r} for n, r in md["participants"]],
            "speakers": [{"id": f"demo-{md['key']}-sp-{lab}", "label": lab, "ordinal": i, "display_name": name,
                          "name": names[lab]} for i, (lab, name) in enumerate(md["speakers"], 1)],
            "segments": [{"id": seg_id[x["position"]], "position": x["position"], "start_seconds": x["start"],
                          "end_seconds": x["end"], "speaker_name": names[x["speaker"]], "text": x["text"]}
                         for x in md["segments"]],
            "summary": {"executive_summary": s["executive"],
                        "discussion_points": [{"topic": x["topic"], "summary": x["summary"],
                                               "segment_ids": ids(x["segs"])} for x in s["points"]],
                        "open_questions": [{"text": x["text"], "segment_ids": ids(x["segs"])} for x in s["questions"]],
                        "risks": [{"text": x["text"], "segment_ids": ids(x["segs"])} for x in s["risks"]],
                        "follow_ups": [{"text": x["text"], "segment_ids": ids(x["segs"])} for x in s["follow_ups"]],
                        "key_dates": [{"date_text": k["date_text"], "date": k["date"], "interpreted": k["interpreted"],
                                       "description": k["description"], "segment_ids": ids(k["segs"])}
                                      for k in s["key_dates"]],
                        "grounding_notes": s["notes"]},
            "decisions": [{"id": f"demo-{md['key']}-d{i}", "title": d["title"], "description": d["description"],
                           "meeting_status": d["status"], "review_status": "unreviewed", "participants": d["people"],
                           "source_segment_ids": ids(d["segs"])} for i, d in enumerate(md["decisions"], 1)],
            "action_items": [{"id": f"demo-{md['key']}-a{i}", "title": a["title"], "description": a["description"],
                              "owner": a["owner"], "due_date": a["due"], "due_text": a["due_text"] if a["due"] else None,
                              "due_source": a["due_source"] if a["due"] else None, "priority": a["priority"],
                              "priority_source": a["priority_source"], "needs_confirmation": a["needs"],
                              "status": a["status"], "source_segment_ids": ids(a["segs"])}
                             for i, a in enumerate(md["actions"], 1)],
        })
    return {"notice": data["notice"], "project": data["project"], "meetings": meetings}
