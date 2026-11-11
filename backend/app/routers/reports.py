"""Report generation, stored reports and exports."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import activity
from .. import schemas as S
from .. import serializers as ser
from ..db import get_db
from ..deps import get_current_user, get_meeting_for, get_report_for, rate_limit, require_workspace
from ..errors import AppError, bad_request
from ..models import ActionItem, Decision, Meeting, Report, User
from ..reports import (actions_export, build_report_data, deadlines_ics, decisions_export, render_html, render_pdf,
                       summary_export, transcript_export)
from ..services import purge_files
from ..storage import StorageError, get_storage

router = APIRouter(tags=["reports"])

# Downloaded HTML must never run script on the API origin.
_SAFE_HEADERS = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'; "
                 "style-src 'unsafe-inline'", "Cache-Control": "private, no-store"}


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (s or "meeting")[:60]


def _file(content: str | bytes, media_type: str, filename: str) -> Response:
    headers = {**_SAFE_HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'}
    if isinstance(content, str) and not media_type.startswith("application/pdf"):
        media_type += "; charset=utf-8"
    return Response(content, media_type=media_type, headers=headers)


@router.post("/meetings/{meeting_id}/reports", response_model=S.ReportOut, status_code=201,
             dependencies=[Depends(rate_limit("report", 30, 3600))])
def create_report(meeting_id: str, body: S.ReportIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id, "member")
    data = build_report_data(db, m, body.include_transcript)
    if body.format == "pdf":
        content, ctype = render_pdf(data), "application/pdf"
    else:
        content, ctype = render_html(data).encode("utf-8"), "text/html"
    r = Report(meeting_id=m.id, workspace_id=m.workspace_id, format=body.format, storage_key="pending",
               size_bytes=len(content), include_transcript=body.include_transcript, created_by=user.id)
    db.add(r)
    db.flush()
    r.storage_key = f"reports/{m.workspace_id}/{m.id}/{r.id}.{body.format}"
    get_storage().save_bytes(r.storage_key, content, ctype)
    activity.record(db, m.workspace_id, "report_generated", f"Generated a {body.format.upper()} report for "
                                                            f"“{m.title}”", user.id, m.id)
    db.commit()
    return ser.report(r, m)


@router.get("/reports", response_model=list[S.ReportOut])
def list_reports(workspace_id: str, meeting_id: str | None = None, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    stmt = select(Report, Meeting).join(Meeting, Report.meeting_id == Meeting.id).where(Report.workspace_id == workspace_id)
    if meeting_id:
        stmt = stmt.where(Report.meeting_id == meeting_id)
    return [ser.report(r, m) for r, m in db.execute(stmt.order_by(Report.created_at.desc()).limit(200)).all()]


@router.get("/reports/{report_id}/download")
def download_report(report_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = get_report_for(db, user, report_id)
    m = db.get(Meeting, r.meeting_id)
    try:
        content = get_storage().read_bytes(r.storage_key)
    except StorageError as e:
        raise AppError(410, "report_missing", "This report file is no longer in storage. Generate it again.") from e
    ctype = "application/pdf" if r.format == "pdf" else "text/html"
    return _file(content, ctype, f"{_slug(m.title)}-report.{r.format}")


@router.delete("/reports/{report_id}", response_model=S.Message)
def delete_report(report_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = get_report_for(db, user, report_id, "member")
    key = r.storage_key
    db.delete(r)
    db.commit()
    purge_files([key])
    return S.Message(message="Report deleted.")


@router.get("/meetings/{meeting_id}/export/{kind}")
def export_meeting(meeting_id: str, kind: str, format: str = Query("txt"), include_transcript: bool = False,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id)
    name = _slug(m.title)
    if kind == "transcript":
        if format not in ("txt", "srt", "vtt", "json"):
            raise bad_request("Transcript format must be txt, srt, vtt or json.")
        if not m.segments:
            raise bad_request("This meeting has no transcript.", "no_transcript")
        try:
            content, ctype = transcript_export(db, m, format)
        except ValueError as e:
            raise bad_request(str(e), "no_timestamps") from e
        return _file(content, ctype, f"{name}-transcript.{format}")
    if kind == "summary":
        if format not in ("md", "json"):
            raise bad_request("Summary format must be md or json.")
        content, ctype = summary_export(build_report_data(db, m, False), format)
        return _file(content, ctype, f"{name}-summary.{format}")
    if kind == "report":
        if format not in ("pdf", "html"):
            raise bad_request("Report format must be pdf or html.")
        data = build_report_data(db, m, include_transcript)
        if format == "pdf":
            return _file(render_pdf(data), "application/pdf", f"{name}-report.pdf")
        return _file(render_html(data), "text/html", f"{name}-report.html")
    if kind == "action-items":
        rows = [(a, m) for a in db.scalars(select(ActionItem).where(ActionItem.meeting_id == m.id)).all()]
        if format == "ics":
            return _file(deadlines_ics(rows), "text/calendar", f"{name}-deadlines.ics")
        content, ctype = actions_export(rows, "csv" if format == "csv" else "md")
        return _file(content, ctype, f"{name}-action-items.{'csv' if format == 'csv' else 'md'}")
    if kind == "decisions":
        rows = [(d, m) for d in db.scalars(select(Decision).where(Decision.meeting_id == m.id)).all()]
        content, ctype = decisions_export(rows, "csv" if format == "csv" else "md")
        return _file(content, ctype, f"{name}-decisions.{'csv' if format == 'csv' else 'md'}")
    raise AppError(404, "not_found", "Unknown export type.")


@router.get("/exports/action-items")
def export_workspace_actions(workspace_id: str, format: str = Query("csv", pattern="^(csv|md|ics)$"),
                             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    rows = db.execute(select(ActionItem, Meeting).join(Meeting, ActionItem.meeting_id == Meeting.id)
                      .where(ActionItem.workspace_id == workspace_id)
                      .order_by(ActionItem.due_date.is_(None), ActionItem.due_date)).all()
    rows = [(a, m) for a, m in rows]
    if format == "ics":
        return _file(deadlines_ics(rows), "text/calendar", "action-item-deadlines.ics")
    content, ctype = actions_export(rows, format)
    return _file(content, ctype, f"action-items.{format}")


@router.get("/exports/decisions")
def export_workspace_decisions(workspace_id: str, format: str = Query("csv", pattern="^(csv|md)$"),
                               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    rows = db.execute(select(Decision, Meeting).join(Meeting, Decision.meeting_id == Meeting.id)
                      .where(Decision.workspace_id == workspace_id).order_by(Meeting.meeting_date.desc())).all()
    content, ctype = decisions_export([(d, m) for d, m in rows], format)
    return _file(content, ctype, f"decisions.{format}")
