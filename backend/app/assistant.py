"""Grounded meeting assistant: retrieve authorised records first, then answer only from them with citations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai import get_ai_client
from .ai.analysis import fmt_ts
from .models import ActionItem, AIMessage, Decision, Meeting, MeetingSummary, User
from .retrieval import escape_like, query_terms, search_segments
from .services import speaker_name

ACTION_WORDS = ("action", "task", "assigned", "assign", "todo", "to do", "to-do", "overdue", "deadline", "due",
                "owner", "responsible", "follow up", "follow-up", "who will", "next step")
DECISION_WORDS = ("decid", "decision", "agreed", "agree", "approve", "conclu", "resolved")
OPEN_WORDS = ("unresolved", "open question", "outstanding", "remain", "pending", "blocker", "risk", "problem",
              "issue", "concern")
RECENT_WORDS = ("yesterday", "today", "last", "latest", "recent", "previous", "this week", "compare", "most recent")

SYSTEM = """You answer questions about the user's meeting records for a meeting-notes product.
Answer only from the numbered sources provided. Cite sources inline with their labels in square brackets, \
for example [S2] or [A1], directly after the statement they support. If the sources do not contain the answer, say \
that the meetings available to you do not cover it; do not guess and do not use outside knowledge. Speaker labels \
such as "Speaker 2" are anonymous: never guess who they are. Be concise and use short paragraphs or bullet points."""


@dataclass
class Source:
    label: str
    kind: str  # segment | meeting | action | decision
    text: str
    citation: dict[str, Any]


@dataclass
class Answer:
    content: str
    mode: str  # ai | retrieval_only | no_results
    citations: list[dict[str, Any]] = field(default_factory=list)
    meeting_ids: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None


def _has(q: str, words: tuple[str, ...]) -> bool:
    return any(w in q for w in words)


def _date(d: datetime) -> str:
    return d.date().isoformat()


def gather_sources(db: Session, user: User, workspace_id: str, question: str, meeting_id: str | None,
                   project_id: str | None) -> list[Source]:
    ql = question.lower()
    sources: list[Source] = []
    base = select(Meeting).where(Meeting.workspace_id == workspace_id)
    if meeting_id:
        base = base.where(Meeting.id == meeting_id)
    if project_id:
        base = base.where(Meeting.project_id == project_id)

    hits = search_segments(db, [workspace_id], query_terms(question), meeting_id=meeting_id, project_id=project_id,
                           limit=10)
    for i, h in enumerate(hits, 1):
        sp = speaker_name(h.segment.speaker)
        ts = f" at {fmt_ts(h.segment.start_seconds)}" if h.segment.start_seconds is not None else ""
        text = (f"Transcript of “{h.meeting.title}” ({_date(h.meeting.meeting_date)}){ts}"
                f"{', ' + sp if sp else ''}: {h.segment.text}")
        sources.append(Source(f"S{i}", "segment", text, {
            "type": "segment", "meeting_id": h.meeting.id, "meeting_title": h.meeting.title,
            "meeting_date": h.meeting.meeting_date.isoformat(), "segment_id": h.segment.id,
            "start_seconds": h.segment.start_seconds, "speaker": sp, "excerpt": h.segment.text[:400]}))

    # Meeting summaries: the meetings the hits came from, plus the most recent ones for time-based questions.
    meeting_ids: list[str] = []
    for h in hits:
        if h.meeting.id not in meeting_ids:
            meeting_ids.append(h.meeting.id)
    if meeting_id and meeting_id not in meeting_ids:
        meeting_ids.insert(0, meeting_id)
    if _has(ql, RECENT_WORDS):
        stmt = base
        if "yesterday" in ql:
            y = date.today() - timedelta(days=1)
            start = datetime(y.year, y.month, y.day, tzinfo=timezone.utc)
            stmt = stmt.where(Meeting.meeting_date >= start, Meeting.meeting_date < start + timedelta(days=1))
        for m in db.scalars(stmt.order_by(Meeting.meeting_date.desc()).limit(3)).all():
            if m.id not in meeting_ids:
                meeting_ids.append(m.id)
    for i, mid in enumerate(meeting_ids[:4], 1):
        m = db.get(Meeting, mid)
        if m is None:
            continue
        summ = db.scalar(select(MeetingSummary).where(MeetingSummary.meeting_id == mid))
        parts = [f"Meeting “{m.title}” on {_date(m.meeting_date)}"]
        if m.participants:
            parts.append("Participants: " + ", ".join(p.name for p in m.participants))
        if summ:
            parts.append("Summary: " + summ.executive_summary)
            if summ.open_questions:
                parts.append("Open questions: " + "; ".join(q["text"] for q in summ.open_questions[:6]))
            if summ.risks:
                parts.append("Risks: " + "; ".join(r["text"] for r in summ.risks[:6]))
        else:
            parts.append("No AI summary is available for this meeting.")
        sources.append(Source(f"M{i}", "meeting", " | ".join(parts), {
            "type": "meeting", "meeting_id": m.id, "meeting_title": m.title,
            "meeting_date": m.meeting_date.isoformat(), "excerpt": (summ.executive_summary[:400] if summ else None)}))

    if _has(ql, ACTION_WORDS) or _has(ql, OPEN_WORDS):
        stmt = (select(ActionItem, Meeting).join(Meeting, ActionItem.meeting_id == Meeting.id)
                .where(ActionItem.workspace_id == workspace_id))
        if meeting_id:
            stmt = stmt.where(ActionItem.meeting_id == meeting_id)
        if project_id:
            stmt = stmt.where(Meeting.project_id == project_id)
        if re.search(r"\b(me|my|i)\b", ql) and user.name.split():
            first = escape_like(user.name.split()[0])
            stmt = stmt.where(ActionItem.owner.ilike(f"%{first}%", escape="\\"))
        if "overdue" in ql:
            stmt = stmt.where(ActionItem.due_date < date.today(), ActionItem.status.in_(("todo", "in_progress")))
        rows = db.execute(stmt.order_by(ActionItem.due_date.is_(None), ActionItem.due_date, Meeting.meeting_date.desc())
                          .limit(25)).all()
        for i, (a, m) in enumerate(rows, 1):
            due = a.due_date.isoformat() if a.due_date else "no deadline specified"
            text = (f"Action item from “{m.title}” ({_date(m.meeting_date)}): {a.title}. Owner: "
                    f"{a.owner or 'Unassigned'}. Deadline: {due}. Status: {a.status.replace('_', ' ')}.")
            sources.append(Source(f"A{i}", "action", text, {
                "type": "action", "meeting_id": m.id, "meeting_title": m.title,
                "meeting_date": m.meeting_date.isoformat(), "action_id": a.id, "excerpt": a.title}))

    if _has(ql, DECISION_WORDS) or _has(ql, OPEN_WORDS):
        stmt = (select(Decision, Meeting).join(Meeting, Decision.meeting_id == Meeting.id)
                .where(Decision.workspace_id == workspace_id, Decision.review_status != "rejected"))
        if meeting_id:
            stmt = stmt.where(Decision.meeting_id == meeting_id)
        if project_id:
            stmt = stmt.where(Meeting.project_id == project_id)
        rows = db.execute(stmt.order_by(Meeting.meeting_date.desc()).limit(25)).all()
        for i, (d, m) in enumerate(rows, 1):
            text = (f"Decision from “{m.title}” ({_date(m.meeting_date)}): {d.title}. "
                    f"{d.description} Status in meeting: {d.meeting_status}. Review: {d.review_status}.")
            sources.append(Source(f"D{i}", "decision", text, {
                "type": "decision", "meeting_id": m.id, "meeting_title": m.title,
                "meeting_date": m.meeting_date.isoformat(), "decision_id": d.id, "excerpt": d.title}))
    return sources


def answer_question(db: Session, user: User, workspace_id: str, question: str, history: list[AIMessage],
                    meeting_id: str | None = None, project_id: str | None = None) -> Answer:
    sources = gather_sources(db, user, workspace_id, question, meeting_id, project_id)
    if not sources:
        return Answer("I could not find anything in your meetings that relates to this question. Try different "
                      "words, or check that the meeting has a transcript.", "no_results")
    client = get_ai_client()
    if client is None:
        lines = ["No AI provider is configured on this server, so I cannot write an answer. These records match "
                 "your question:"]
        lines += [f"- [{s.label}] {s.text[:300]}" for s in sources[:8]]
        cites = [{"label": s.label, **s.citation} for s in sources[:8]]
        return Answer("\n".join(lines), "retrieval_only", cites, sorted({c["meeting_id"] for c in cites}))

    convo = ""
    recent = [m for m in history if m.role in ("user", "assistant")][-6:]
    if recent:
        convo = "Earlier in this conversation (for context only; it is not a source):\n" + "\n".join(
            f"{m.role}: {m.content[:600]}" for m in recent) + "\n\n"
    prompt = (f"Today's date: {date.today().isoformat()}. The person asking is named {user.name}; \"me\" and \"my\" "
              f"refer to them.\n\n{convo}Sources:\n" + "\n".join(f"[{s.label}] {s.text}" for s in sources) +
              f"\n\nQuestion: {question}")
    text, provider, model = client.text(SYSTEM, prompt, max_tokens=2000)
    by_label = {s.label: s for s in sources}
    used: list[str] = []
    for lab in re.findall(r"\[([SMAD]\d+)\]", text):
        if lab in by_label and lab not in used:
            used.append(lab)
    cites = [{"label": lab, **by_label[lab].citation} for lab in used]
    return Answer(text.strip(), "ai", cites, sorted({c["meeting_id"] for c in cites}), provider, model)
