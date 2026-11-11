"""Meeting analysis: prompt construction, long-transcript windowing and grounding validation.

The model is asked to cite transcript line numbers for everything it extracts. Its output is then checked
against the transcript in code: uncited decisions and actions are dropped, owners and deadlines that do not
appear in the cited lines are removed, and every change is recorded as a grounding note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from . import AIClient


# --- Output schema (what the model must return) -------------------------------------------------

class DiscussionPointOut(BaseModel):
    topic: str
    summary: str
    segment_ids: list[int]


class DecisionOut(BaseModel):
    title: str
    description: str
    status: Literal["confirmed", "proposed", "uncertain"]
    participants: list[str]
    segment_ids: list[int]


class ActionOut(BaseModel):
    title: str
    description: str
    owner: str | None
    deadline_text: str | None
    deadline_date: str | None
    priority: Literal["high", "medium", "low"] | None
    priority_basis: Literal["stated", "suggested"] | None
    needs_confirmation: bool
    segment_ids: list[int]


class QuestionOut(BaseModel):
    question: str
    segment_ids: list[int]


class NoteOut(BaseModel):
    description: str
    segment_ids: list[int]


class KeyDateOut(BaseModel):
    date_text: str
    date: str | None
    description: str
    segment_ids: list[int]


class AnalysisOut(BaseModel):
    executive_summary: str
    discussion_points: list[DiscussionPointOut] = Field(default_factory=list)
    decisions: list[DecisionOut] = Field(default_factory=list)
    action_items: list[ActionOut] = Field(default_factory=list)
    open_questions: list[QuestionOut] = Field(default_factory=list)
    risks: list[NoteOut] = Field(default_factory=list)
    follow_ups: list[NoteOut] = Field(default_factory=list)
    key_dates: list[KeyDateOut] = Field(default_factory=list)


SYSTEM_PROMPT = """You analyse meeting transcripts for a meeting-notes product. Each transcript line starts with \
a line number in square brackets, then an optional timestamp and speaker label.

Rules:
- Use only what the transcript says. Never invent decisions, deadlines, attendees, owners or commitments.
- Cite the line numbers that support every item in `segment_ids`. Items without support must be left out.
- decisions: use status "confirmed" only when the transcript shows agreement on the decision; "proposed" when it \
was suggested but not agreed; "uncertain" when it is unclear. Do not list mere ideas as decisions.
- action_items: `owner` is the person or speaker label explicitly responsible in the transcript, else null. \
Never guess an owner. `deadline_text` is the exact words used for the deadline (copied verbatim), else null. \
`deadline_date` is YYYY-MM-DD only when the date can be worked out from those words and the meeting date, else \
null. `priority` is set with priority_basis "stated" only when the urgency was explicitly said; you may suggest a \
priority with basis "suggested"; otherwise both null. Set needs_confirmation true when anything about the task \
is ambiguous.
- open_questions: questions raised that were not answered in the meeting.
- risks: problems, risks or blockers that were explicitly discussed.
- follow_ups: sensible next steps that follow directly from the discussion.
- key_dates: dates or deadlines mentioned. date_text must be copied verbatim from the transcript.
- Speaker labels like "Speaker 2" are anonymous; never guess who a speaker is.
- If the transcript contains little substance, say so in the executive summary and return empty lists.
- Write in the same language as the transcript."""


@dataclass
class SegmentView:
    id: str
    position: int
    text: str
    start: float | None
    speaker_label: str | None  # display name or "Speaker N"


def fmt_ts(seconds: float | None) -> str:
    if seconds is None:
        return ""
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def transcript_lines(segments: list[SegmentView]) -> list[str]:
    out = []
    for s in segments:
        parts = [f"[{s.position}]"]
        if s.start is not None:
            parts.append(f"({fmt_ts(s.start)})")
        if s.speaker_label:
            parts.append(f"{s.speaker_label}:")
        parts.append(s.text.replace("\n", " "))
        out.append(" ".join(parts))
    return out


def windows(lines: list[str], max_chars: int) -> list[list[str]]:
    out: list[list[str]] = [[]]
    size = 0
    for line in lines:
        if out[-1] and size + len(line) + 1 > max_chars:
            out.append([])
            size = 0
        out[-1].append(line)
        size += len(line) + 1
    return [w for w in out if w]


def _context(title: str, meeting_date: datetime, participants: list[str], part: tuple[int, int] | None) -> str:
    lines = [f"Meeting title: {title}", f"Meeting date: {meeting_date.date().isoformat()} "
             f"({meeting_date.strftime('%A')})"]
    if participants:
        lines.append("Participants listed by the user: " + ", ".join(participants))
    if part:
        lines.append(f"This is part {part[0]} of {part[1]} of a long transcript; analyse this part only.")
    return "\n".join(lines)


def run_analysis(client: AIClient, title: str, meeting_date: datetime, participants: list[str],
                 segments: list[SegmentView], max_chars: int) -> tuple[AnalysisOut, str, str, bool]:
    """Returns (analysis, provider, model, chunked)."""
    lines = transcript_lines(segments)
    parts = windows(lines, max_chars)
    results: list[AnalysisOut] = []
    provider = model = ""
    for i, part in enumerate(parts, 1):
        ctx = _context(title, meeting_date, participants, (i, len(parts)) if len(parts) > 1 else None)
        user = f"{ctx}\n\nTranscript:\n" + "\n".join(part) + "\n\nReturn the analysis as JSON."
        out, provider, model = client.structured(SYSTEM_PROMPT, user, AnalysisOut)
        results.append(out)
    if len(results) == 1:
        return results[0], provider, model, False
    merged = merge_analyses(results)
    partials = "\n\n".join(f"Part {i}: {r.executive_summary}" for i, r in enumerate(results, 1))
    summary, provider, model = client.text(
        "You combine partial meeting summaries into one concise executive summary. Use only the information "
        "given. Do not add facts.", f"Meeting title: {title}\n\n{partials}\n\nWrite one executive summary of at "
        "most 150 words.", max_tokens=2000)
    merged.executive_summary = summary.strip()
    return merged, provider, model, True


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def merge_analyses(parts: list[AnalysisOut]) -> AnalysisOut:
    merged = AnalysisOut(executive_summary="")
    seen: dict[str, set[str]] = {"decisions": set(), "action_items": set()}
    for p in parts:
        merged.discussion_points += p.discussion_points
        merged.open_questions += p.open_questions
        merged.risks += p.risks
        merged.follow_ups += p.follow_ups
        merged.key_dates += p.key_dates
        for d in p.decisions:
            if _norm(d.title) not in seen["decisions"]:
                seen["decisions"].add(_norm(d.title))
                merged.decisions.append(d)
        for a in p.action_items:
            if _norm(a.title) not in seen["action_items"]:
                seen["action_items"].add(_norm(a.title))
                merged.action_items.append(a)
    return merged


# --- Grounding validation -----------------------------------------------------------------------

_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|"
           "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_ABSOLUTE_DATE = re.compile(rf"(\b\d{{4}}-\d{{1,2}}-\d{{1,2}}\b)|(\b\d{{1,2}}[/.]\d{{1,2}}([/.]\d{{2,4}})?\b)|"
                            rf"(\b({_MONTHS})\.?\s+\d{{1,2}}(st|nd|rd|th)?\b)|(\b\d{{1,2}}(st|nd|rd|th)?\s+"
                            rf"(of\s+)?({_MONTHS})\b)", re.IGNORECASE)


@dataclass
class GroundedDecision:
    title: str
    description: str
    status: str
    participants: list[str]
    segment_ids: list[str]
    excerpt: str


@dataclass
class GroundedAction:
    title: str
    description: str
    owner: str | None
    due_date: date | None
    due_text: str | None
    due_source: str | None
    priority: str | None
    priority_source: str | None
    needs_confirmation: bool
    segment_ids: list[str]
    excerpt: str


@dataclass
class GroundedAnalysis:
    executive_summary: str
    discussion_points: list[dict] = field(default_factory=list)
    decisions: list[GroundedDecision] = field(default_factory=list)
    action_items: list[GroundedAction] = field(default_factory=list)
    open_questions: list[dict] = field(default_factory=list)
    risks: list[dict] = field(default_factory=list)
    follow_ups: list[dict] = field(default_factory=list)
    key_dates: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _contains(haystack: str, needle: str) -> bool:
    n = _norm(needle)
    if not n:
        return False
    return re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", _norm(haystack)) is not None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def ground(out: AnalysisOut, segments: list[SegmentView], known_names: list[str]) -> GroundedAnalysis:
    by_pos = {s.position: s for s in segments}
    known = {_norm(n) for n in known_names if n}
    g = GroundedAnalysis(executive_summary=out.executive_summary.strip())

    def resolve(ids: list[int]) -> list[SegmentView]:
        seen, res = set(), []
        for i in ids:
            if i in by_pos and i not in seen:
                seen.add(i)
                res.append(by_pos[i])
        return sorted(res, key=lambda s: s.position)

    def cited_text(segs: list[SegmentView]) -> str:
        return " \n ".join(s.text for s in segs)

    def excerpt(segs: list[SegmentView]) -> str:
        text = " ".join((f"{s.speaker_label}: " if s.speaker_label else "") + s.text for s in segs[:3])
        return text if len(text) <= 500 else text[:497] + "..."

    def name_ok(name: str, segs: list[SegmentView]) -> bool:
        if _contains(cited_text(segs), name):
            return True
        if any(s.speaker_label and _norm(s.speaker_label) == _norm(name) for s in segs):
            return True
        first = name.split()[0] if name.split() else ""
        return len(first) >= 3 and _norm(name) in known and _contains(cited_text(segs), first)

    def simple(items, text_attr: str, label: str) -> list[dict]:
        res = []
        for it in items:
            segs = resolve(it.segment_ids)
            text = getattr(it, text_attr).strip()
            if not text:
                continue
            if not segs:
                g.notes.append(f"Removed {label} without a valid transcript reference: \"{text[:80]}\"")
                continue
            res.append({"text": text, "segment_ids": [s.id for s in segs]})
        return res

    for p in out.discussion_points:
        segs = resolve(p.segment_ids)
        g.discussion_points.append({"topic": p.topic.strip(), "summary": p.summary.strip(),
                                    "segment_ids": [s.id for s in segs]})
    g.open_questions = simple(out.open_questions, "question", "question")
    g.risks = simple(out.risks, "description", "risk")
    g.follow_ups = simple(out.follow_ups, "description", "follow-up")

    for d in out.decisions:
        segs = resolve(d.segment_ids)
        if not segs:
            g.notes.append(f"Removed decision without a valid transcript reference: \"{d.title[:80]}\"")
            continue
        people = [n.strip() for n in d.participants if n.strip() and name_ok(n.strip(), segs)]
        dropped = [n for n in d.participants if n.strip() and n.strip() not in people]
        if dropped:
            g.notes.append(f"Removed participants not found in the cited lines for decision \"{d.title[:60]}\": "
                           + ", ".join(dropped))
        g.decisions.append(GroundedDecision(d.title.strip()[:300], d.description.strip(), d.status, people,
                                            [s.id for s in segs], excerpt(segs)))

    for a in out.action_items:
        segs = resolve(a.segment_ids)
        if not segs:
            g.notes.append(f"Removed action item without a valid transcript reference: \"{a.title[:80]}\"")
            continue
        needs = a.needs_confirmation
        owner = (a.owner or "").strip() or None
        if owner and not name_ok(owner, segs):
            g.notes.append(f"Owner \"{owner}\" for \"{a.title[:60]}\" was not found in the cited lines and was "
                           "removed.")
            owner, needs = None, True
        due_text = (a.deadline_text or "").strip() or None
        due_date = _parse_date(a.deadline_date)
        due_source = None
        if due_text and not _contains(cited_text(segs), due_text):
            g.notes.append(f"Deadline \"{due_text}\" for \"{a.title[:60]}\" was not found in the cited lines and "
                           "was removed.")
            due_text, due_date, needs = None, None, True
        if due_text:
            if due_date and not _ABSOLUTE_DATE.search(due_text):
                due_source = "ai_interpreted"
                needs = True
            else:
                due_source = "transcript"
        elif due_date:
            due_date = None  # a date with no supporting words is never kept
        priority = a.priority
        priority_source = None
        if priority:
            priority_source = "stated" if a.priority_basis == "stated" else "ai_suggested"
        g.action_items.append(GroundedAction(a.title.strip()[:300], a.description.strip(), owner, due_date,
                                             due_text[:200] if due_text else None, due_source, priority,
                                             priority_source, needs, [s.id for s in segs], excerpt(segs)))

    for k in out.key_dates:
        segs = resolve(k.segment_ids)
        if not segs or not _contains(cited_text(segs), k.date_text):
            g.notes.append(f"Removed key date \"{k.date_text[:60]}\": not found in the cited lines.")
            continue
        parsed = _parse_date(k.date)
        g.key_dates.append({"date_text": k.date_text.strip(), "date": parsed.isoformat() if parsed else None,
                            "interpreted": bool(parsed and not _ABSOLUTE_DATE.search(k.date_text)),
                            "description": k.description.strip(), "segment_ids": [s.id for s in segs]})
    return g
