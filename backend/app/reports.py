"""Meeting reports (HTML and PDF) and data exports (TXT, SRT, VTT, JSON, Markdown, CSV, ICS)."""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, timezone
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .ai.analysis import fmt_ts
from .models import ActionItem, Decision, Meeting, MeetingSummary, Transcript, TranscriptSegment
from .services import speaker_name

HERE = os.path.dirname(__file__)
_env = Environment(loader=FileSystemLoader(os.path.join(HERE, "templates")),
                   autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)

STATUS_LABELS = {"todo": "To do", "in_progress": "In progress", "completed": "Completed", "cancelled": "Cancelled"}
DECISION_LABELS = {"confirmed": "Confirmed in meeting", "proposed": "Proposed, not confirmed",
                   "uncertain": "Uncertain, needs confirmation"}


def _duration(seconds: float | None) -> str:
    if not seconds:
        return "Not recorded"
    m = int(round(seconds / 60))
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{max(m, 1)} min"


def _due(a: ActionItem) -> str:
    if not a.due_date:
        return "No deadline specified"
    if a.due_source == "ai_interpreted":
        return f"{a.due_date.isoformat()} (interpreted from \u201c{a.due_text}\u201d, confirm)"
    return a.due_date.isoformat()


def _priority(a: ActionItem) -> str:
    if not a.priority:
        return "Not set"
    suffix = {"stated": " (stated in meeting)", "ai_suggested": " (AI suggestion)", "user": ""}.get(
        a.priority_source or "", "")
    return a.priority.capitalize() + suffix


def build_report_data(db: Session, m: Meeting, include_transcript: bool) -> dict[str, Any]:
    summary = db.scalar(select(MeetingSummary).where(MeetingSummary.meeting_id == m.id))
    actions = db.scalars(select(ActionItem).where(ActionItem.meeting_id == m.id)
                         .order_by(ActionItem.due_date.is_(None), ActionItem.due_date, ActionItem.created_at)).all()
    decisions = db.scalars(select(Decision).where(Decision.meeting_id == m.id, Decision.review_status != "rejected")
                           .order_by(Decision.created_at)).all()
    segments = db.scalars(select(TranscriptSegment).options(selectinload(TranscriptSegment.speaker))
                          .where(TranscriptSegment.meeting_id == m.id).order_by(TranscriptSegment.position)).all()
    by_id = {s.id: s for s in segments}

    def excerpts(ids: list[str]) -> list[str]:
        out = []
        for i in ids[:2]:
            s = by_id.get(i)
            if s:
                ts = f"[{fmt_ts(s.start_seconds)}] " if s.start_seconds is not None else ""
                sp = f"{speaker_name(s.speaker)}: " if s.speaker else ""
                out.append(f"{ts}{sp}{s.text}")
        return out

    return {
        "title": m.title,
        "is_demo": m.is_demo,
        "date": m.meeting_date.strftime("%d %B %Y, %H:%M UTC"),
        "duration": _duration(m.duration_seconds),
        "project": m.project.name if m.project else None,
        "participants": [p.name + (f" ({p.role})" if p.role else "") for p in m.participants],
        "description": m.description,
        "generated": datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC"),
        "summary": None if summary is None else {
            "executive": summary.executive_summary,
            "points": summary.discussion_points,
            "questions": summary.open_questions,
            "risks": summary.risks,
            "follow_ups": summary.follow_ups,
            "key_dates": summary.key_dates,
            "provider": f"{summary.provider} / {summary.model}" if summary.model else summary.provider,
        },
        "decisions": [{"title": d.title, "description": d.description,
                       "status": DECISION_LABELS.get(d.meeting_status, d.meeting_status),
                       "reviewed": d.review_status == "confirmed", "participants": d.participants,
                       "excerpts": excerpts(d.source_segment_ids)} for d in decisions],
        "actions": [{"title": a.title, "description": a.description, "owner": a.owner or "Unassigned",
                     "due": _due(a), "priority": _priority(a), "status": STATUS_LABELS.get(a.status, a.status),
                     "needs_confirmation": a.needs_confirmation, "excerpts": excerpts(a.source_segment_ids)}
                    for a in actions],
        "transcript": [{"ts": fmt_ts(s.start_seconds) if s.start_seconds is not None else "",
                        "speaker": speaker_name(s.speaker) or "", "text": s.text} for s in segments]
        if include_transcript else [],
        "has_transcript": bool(segments),
    }


def render_html(data: dict[str, Any]) -> str:
    return _env.get_template("report.html").render(**data)


# --- PDF ---------------------------------------------------------------------------------------

_FONTS_READY: tuple[str, str] | None = None


def _fonts() -> tuple[str, str]:
    global _FONTS_READY
    if _FONTS_READY is None:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        regular = os.path.join(HERE, "assets", "fonts", "DejaVuSans.ttf")
        bold = os.path.join(HERE, "assets", "fonts", "DejaVuSans-Bold.ttf")
        if os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("DejaVuSans", regular))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold))
            _FONTS_READY = ("DejaVuSans", "DejaVuSans-Bold")
        else:  # Latin-only fallback
            _FONTS_READY = ("Helvetica", "Helvetica-Bold")
    return _FONTS_READY


def render_pdf(data: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    from xml.sax.saxutils import escape

    regular, bold = _fonts()
    ink, muted, accent, line = (colors.HexColor("#0f172a"), colors.HexColor("#64748b"), colors.HexColor("#4f46e5"),
                                colors.HexColor("#e2e8f0"))
    base = ParagraphStyle("base", fontName=regular, fontSize=9.5, leading=13.5, textColor=ink, alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=11, textColor=muted)
    h1 = ParagraphStyle("h1", parent=base, fontName=bold, fontSize=18, leading=23, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=base, fontName=bold, fontSize=12, leading=16, spaceBefore=12, spaceAfter=5,
                        textColor=accent)
    h3 = ParagraphStyle("h3", parent=base, fontName=bold, fontSize=10, leading=14)
    quote = ParagraphStyle("quote", parent=small, leftIndent=8, textColor=muted, fontSize=7.8)

    def p(text: str, style=base) -> Paragraph:
        return Paragraph(escape(text or "").replace("\n", "<br/>"), style)

    story: list[Any] = [p("MEETPILOT AI \u00b7 MEETING REPORT", small), Spacer(1, 3), p(data["title"], h1)]
    if data["is_demo"]:
        story.append(p("Demo content: this meeting is fictional sample data.", small))
    meta = [["Date", data["date"]], ["Duration", data["duration"]]]
    if data["project"]:
        meta.append(["Project", data["project"]])
    if data["participants"]:
        meta.append(["Participants", ", ".join(data["participants"])])
    t = Table([[p(a, small), p(b)] for a, b in meta], colWidths=[28 * mm, None])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [Spacer(1, 6), t]

    def bullets(items: list[str]) -> ListFlowable:
        return ListFlowable([ListItem(p(i), leftIndent=10, value="circle") for i in items], bulletType="bullet",
                            start="\u2022", leftIndent=10, bulletFontName=regular, bulletFontSize=8)

    s = data["summary"]
    if s:
        story += [p("Executive summary", h2), p(s["executive"])]
        if s["points"]:
            story += [p("Discussion points", h2),
                      bullets([f"{x['topic']}: {x['summary']}" if x.get("summary") else x["topic"] for x in s["points"]])]
    story.append(p("Decisions", h2))
    if data["decisions"]:
        for d in data["decisions"]:
            reviewed = " \u00b7 reviewed" if d["reviewed"] else ""
            block = [p(d["title"], h3), p(d["status"] + reviewed, small)]
            if d["description"]:
                block.append(p(d["description"]))
            block += [p("\u201c" + e + "\u201d", quote) for e in d["excerpts"]]
            block.append(Spacer(1, 5))
            story.append(KeepTogether(block))
    else:
        story.append(p("No decisions recorded.", small))
    story.append(p("Action items", h2))
    if data["actions"]:
        rows = [[p("Task", small), p("Owner", small), p("Deadline", small), p("Priority", small), p("Status", small)]]
        for a in data["actions"]:
            title = a["title"] + (" (needs confirmation)" if a["needs_confirmation"] else "")
            rows.append([p(title), p(a["owner"]), p(a["due"]), p(a["priority"]), p(a["status"])])
        at = Table(rows, colWidths=[62 * mm, 28 * mm, 34 * mm, 26 * mm, 20 * mm], repeatRows=1)
        at.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
        story.append(at)
    else:
        story.append(p("No action items recorded.", small))
    if s:
        for key, label in (("key_dates", "Key dates"), ("questions", "Open questions"), ("risks", "Risks and blockers"),
                           ("follow_ups", "Suggested follow-up")):
            items = s[key]
            if not items:
                continue
            story.append(p(label, h2))
            if key == "key_dates":
                story.append(bullets([f"{k['date_text']}" + (f" ({k['date']}{', interpreted' if k.get('interpreted') else ''})"
                                                             if k.get("date") else "") + f": {k['description']}"
                                      for k in items]))
            else:
                story.append(bullets([x["text"] for x in items]))
    if data["transcript"]:
        story.append(p("Transcript", h2))
        for seg in data["transcript"]:
            prefix = " ".join(x for x in (f"[{seg['ts']}]" if seg["ts"] else "", seg["speaker"] and f"{seg['speaker']}:") if x)
            story.append(p(f"{prefix} {seg['text']}".strip(), small))
    story += [Spacer(1, 14), p(f"Generated by MeetPilot AI on {data['generated']}. AI-generated content can contain "
                                f"mistakes; check important details against the transcript."
                                + (f" Analysis: {s['provider']}." if s else ""), small)]

    buf = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 10 * mm, f"MeetPilot AI \u00b7 {data['title'][:80]}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"{data['title']} - Meeting report", author="MeetPilot AI")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# --- Exports -----------------------------------------------------------------------------------

def _csv_cell(v: Any) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s  # spreadsheet formula injection guard


def to_csv(rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow([_csv_cell(c) for c in r])
    return buf.getvalue()


def _srt_ts(sec: float, sep: str) -> str:
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d}{sep}{ms % 1000:03d}"


def transcript_export(db: Session, m: Meeting, fmt: str) -> tuple[str, str]:
    t = db.scalar(select(Transcript).where(Transcript.meeting_id == m.id))
    segs = db.scalars(select(TranscriptSegment).options(selectinload(TranscriptSegment.speaker))
                      .where(TranscriptSegment.meeting_id == m.id).order_by(TranscriptSegment.position)).all()
    if fmt == "json":
        return json.dumps({"meeting": {"id": m.id, "title": m.title, "date": m.meeting_date.isoformat()},
                           "transcript": {"provider": t.provider if t else None, "model": t.model if t else None,
                                          "language": t.language if t else None,
                                          "has_timestamps": t.has_timestamps if t else False,
                                          "has_diarization": t.has_diarization if t else False},
                           "segments": [{"position": s.position, "start": s.start_seconds, "end": s.end_seconds,
                                         "speaker": speaker_name(s.speaker),
                                         "speaker_label": s.speaker.label if s.speaker else None,
                                         "text": s.text, "original_text": s.original_text,
                                         "edited": s.text != s.original_text} for s in segs]},
                          ensure_ascii=False, indent=2), "application/json"
    if fmt in ("srt", "vtt"):
        timed = [s for s in segs if s.start_seconds is not None and s.end_seconds is not None]
        if not timed:
            raise ValueError("This transcript has no timestamps, so subtitles cannot be exported.")
        sep = "," if fmt == "srt" else "."
        lines = ["WEBVTT", ""] if fmt == "vtt" else []
        for i, s in enumerate(timed, 1):
            sp = speaker_name(s.speaker)
            if fmt == "srt":
                lines.append(str(i))
            lines.append(f"{_srt_ts(s.start_seconds, sep)} --> {_srt_ts(s.end_seconds, sep)}")
            lines.append((f"{sp}: " if sp else "") + s.text)
            lines.append("")
        return "\n".join(lines), "text/vtt" if fmt == "vtt" else "application/x-subrip"
    lines = [m.title, m.meeting_date.strftime("%Y-%m-%d %H:%M UTC"), ""]
    for s in segs:
        ts = f"[{fmt_ts(s.start_seconds)}] " if s.start_seconds is not None else ""
        sp = f"{speaker_name(s.speaker)}: " if s.speaker else ""
        lines.append(f"{ts}{sp}{s.text}")
    return "\n".join(lines) + "\n", "text/plain"


def summary_export(data: dict[str, Any], fmt: str) -> tuple[str, str]:
    s = data["summary"]
    if fmt == "json":
        return json.dumps({k: data[k] for k in ("title", "date", "duration", "participants", "summary", "decisions",
                                                "actions")}, ensure_ascii=False, indent=2, default=str), "application/json"
    out = [f"# {data['title']}", "", f"- Date: {data['date']}", f"- Duration: {data['duration']}"]
    if data["participants"]:
        out.append(f"- Participants: {', '.join(data['participants'])}")
    if data["is_demo"]:
        out.append("- Demo content: fictional sample data")
    if s:
        out += ["", "## Executive summary", "", s["executive"]]
        for key, label in (("points", "Discussion points"), ("questions", "Open questions"),
                           ("risks", "Risks and blockers"), ("follow_ups", "Suggested follow-up")):
            if s[key]:
                out += ["", f"## {label}", ""]
                out += [f"- **{x['topic']}**: {x['summary']}" if key == "points" else f"- {x['text']}" for x in s[key]]
        if s["key_dates"]:
            out += ["", "## Key dates", ""] + [f"- {k['date_text']}: {k['description']}" for k in s["key_dates"]]
    out += ["", "## Decisions", ""] + ([f"- **{d['title']}** ({d['status']}). {d['description']}".rstrip()
                                        for d in data["decisions"]] or ["- None recorded"])
    out += ["", "## Action items", ""] + ([f"- [{'x' if a['status'] == 'Completed' else ' '}] {a['title']} \u2014 "
                                           f"Owner: {a['owner']}; Deadline: {a['due']}; Priority: {a['priority']}"
                                           for a in data["actions"]] or ["- None recorded"])
    return "\n".join(out) + "\n", "text/markdown"


def actions_export(rows: list[tuple[ActionItem, Meeting]], fmt: str) -> tuple[str, str]:
    if fmt == "csv":
        data = [["Title", "Description", "Owner", "Deadline", "Deadline source", "Priority", "Priority source",
                 "Status", "Needs confirmation", "Meeting", "Meeting date", "Notes"]]
        for a, m in rows:
            data.append([a.title, a.description, a.owner or "Unassigned",
                         a.due_date.isoformat() if a.due_date else "No deadline specified", a.due_source or "",
                         a.priority or "", a.priority_source or "", STATUS_LABELS.get(a.status, a.status),
                         "yes" if a.needs_confirmation else "no", m.title, m.meeting_date.date().isoformat(), a.notes])
        return to_csv(data), "text/csv"
    lines = ["# Action items", ""]
    for a, m in rows:
        lines.append(f"- [{'x' if a.status == 'completed' else ' '}] {a.title} \u2014 Owner: {a.owner or 'Unassigned'}; "
                     f"Deadline: {_due(a)}; Status: {STATUS_LABELS.get(a.status, a.status)} (from \u201c{m.title}\u201d)")
    return "\n".join(lines) + "\n", "text/markdown"


def decisions_export(rows: list[tuple[Decision, Meeting]], fmt: str) -> tuple[str, str]:
    if fmt == "csv":
        data = [["Title", "Description", "Status in meeting", "Review status", "Participants", "Meeting",
                 "Meeting date", "Excerpt"]]
        for d, m in rows:
            data.append([d.title, d.description, d.meeting_status, d.review_status, "; ".join(d.participants), m.title,
                         m.meeting_date.date().isoformat(), d.excerpt or ""])
        return to_csv(data), "text/csv"
    lines = ["# Decisions", ""]
    for d, m in rows:
        lines.append(f"- **{d.title}** ({DECISION_LABELS.get(d.meeting_status, d.meeting_status)}; review: "
                     f"{d.review_status}) \u2014 {m.title}, {m.meeting_date.date().isoformat()}")
    return "\n".join(lines) + "\n", "text/markdown"


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def deadlines_ics(rows: list[tuple[ActionItem, Meeting]]) -> str:
    """All-day calendar entries for action items with a deadline. Importing is a manual user step."""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MeetPilot AI//Action deadlines//EN", "CALSCALE:GREGORIAN"]
    for a, m in rows:
        if not a.due_date:
            continue
        d: date = a.due_date
        owner = a.owner or "Unassigned"
        lines += ["BEGIN:VEVENT", f"UID:{a.id}@meetpilot-ai", f"DTSTAMP:{now}",
                  f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
                  f"SUMMARY:{_ics_escape('Due: ' + a.title[:150])}",
                  "DESCRIPTION:" + _ics_escape(f"Owner: {owner}. From meeting: {m.title}."),
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
