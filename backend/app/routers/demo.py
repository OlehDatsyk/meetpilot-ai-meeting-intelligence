"""Demo mode endpoints. Everything here is fictional sample data and is labelled as such."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..config import get_settings
from ..db import get_db
from ..demo import build_demo, public_demo_payload, seed_demo_workspace
from ..deps import get_current_user, rate_limit
from ..errors import AppError
from ..models import User, Workspace, WorkspaceMember
from ..reports import STATUS_LABELS, DECISION_LABELS, render_html

router = APIRouter(prefix="/demo", tags=["demo"])


def _enabled() -> None:
    if not get_settings().demo_enabled:
        raise AppError(404, "demo_disabled", "Demo mode is turned off on this server.")


@router.get("", dependencies=[Depends(_enabled), Depends(rate_limit("demo", 120, 60))])
def public_demo():
    """Public read-only demo (no account needed)."""
    return public_demo_payload()


@router.get("/report.html", response_class=HTMLResponse, dependencies=[Depends(_enabled)])
def public_demo_report():
    data = build_demo()
    m = data["meetings"][0]
    names = {lab: (name or f"Speaker {i}") for i, (lab, name) in enumerate(m["speakers"], 1)}
    by_pos = {s["position"]: s for s in m["segments"]}

    def excerpts(segs: list[int]) -> list[str]:
        out = []
        for p in segs[:2]:
            s = by_pos[p]
            t = int(s["start"])
            out.append(f"[{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}] {names[s['speaker']]}: {s['text']}")
        return out

    def due(a: dict) -> str:
        if not a["due"]:
            return "No deadline specified"
        if a["due_source"] == "ai_interpreted":
            return f"{a['due'].isoformat()} (interpreted from “{a['due_text']}”, confirm)"
        return a["due"].isoformat()

    def prio(a: dict) -> str:
        if not a["priority"]:
            return "Not set"
        return a["priority"].capitalize() + (" (stated in meeting)" if a["priority_source"] == "stated"
                                             else " (AI suggestion)")

    s = m["summary"]
    html = render_html({
        "title": m["title"], "is_demo": True, "date": m["date"].strftime("%d %B %Y, %H:%M UTC"),
        "duration": f"{round(m['duration'] / 60)} min", "project": data["project"]["name"],
        "participants": [f"{n} ({r})" for n, r in m["participants"]], "description": m["description"],
        "generated": datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC"),
        "summary": {"executive": s["executive"], "points": s["points"],
                    "questions": s["questions"], "risks": s["risks"], "follow_ups": s["follow_ups"],
                    "key_dates": s["key_dates"], "provider": "demo / fictional sample"},
        "decisions": [{"title": d["title"], "description": d["description"],
                       "status": DECISION_LABELS[d["status"]], "reviewed": False, "participants": d["people"],
                       "excerpts": excerpts(d["segs"])} for d in m["decisions"]],
        "actions": [{"title": a["title"], "description": a["description"], "owner": a["owner"] or "Unassigned",
                     "due": due(a), "priority": prio(a), "status": STATUS_LABELS[a["status"]],
                     "needs_confirmation": a["needs"], "excerpts": excerpts(a["segs"])} for a in m["actions"]],
        "transcript": [], "has_transcript": True,
    })
    return HTMLResponse(html, headers={"Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
                                       "X-Content-Type-Options": "nosniff"})


@router.post("/workspace", response_model=S.Message, status_code=201,
             dependencies=[Depends(_enabled), Depends(rate_limit("demo_workspace", 5, 3600))])
def create_demo_workspace(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create (once) a demo workspace with fictional meetings so the user can try every feature."""
    existing = db.scalar(select(Workspace).join(WorkspaceMember).where(WorkspaceMember.user_id == user.id,
                                                                       Workspace.is_demo.is_(True)))
    if existing:
        return S.Message(message=existing.id)
    ws = seed_demo_workspace(db, user.id)
    db.commit()
    return S.Message(message=ws.id)
