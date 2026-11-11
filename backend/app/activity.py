"""Workspace activity log (no transcript content is written here)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import ActivityRecord


def record(db: Session, workspace_id: str, action: str, summary: str, user_id: str | None = None,
           meeting_id: str | None = None) -> None:
    db.add(ActivityRecord(workspace_id=workspace_id, user_id=user_id, meeting_id=meeting_id, action=action,
                          summary=summary[:300]))
