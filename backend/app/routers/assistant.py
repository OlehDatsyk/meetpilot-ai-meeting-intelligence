"""AI assistant conversations."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..ai import AIProviderError
from ..assistant import answer_question
from ..db import get_db
from ..deps import get_current_user, get_meeting_for, get_project_for, rate_limit, require_workspace
from ..errors import AppError, bad_request, not_found
from ..models import AIConversation, AIMessage, User, utcnow

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _conv(db: Session, user: User, conv_id: str) -> AIConversation:
    c = db.get(AIConversation, conv_id)
    # Conversations are private to the person who started them, and they must still be in the workspace.
    if c is None or c.user_id != user.id:
        raise not_found("Conversation")
    require_workspace(db, user, c.workspace_id)
    return c


def _msg(m: AIMessage) -> S.AIMessageOut:
    return S.AIMessageOut(id=m.id, role=m.role, content=m.content, mode=m.mode, citations=m.citations or [],
                          provider=m.provider, model=m.model, created_at=m.created_at)


def _out(c: AIConversation) -> S.ConversationOut:
    return S.ConversationOut(id=c.id, workspace_id=c.workspace_id, meeting_id=c.meeting_id, title=c.title,
                             created_at=c.created_at, updated_at=c.updated_at)


@router.get("/conversations", response_model=list[S.ConversationOut])
def list_conversations(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    rows = db.scalars(select(AIConversation).where(AIConversation.workspace_id == workspace_id,
                                                   AIConversation.user_id == user.id)
                      .order_by(AIConversation.updated_at.desc()).limit(100)).all()
    return [_out(c) for c in rows]


@router.post("/conversations", response_model=S.ConversationOut, status_code=201)
def create_conversation(body: S.ConversationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, body.workspace_id)
    title = body.title or "New conversation"
    if body.meeting_id:
        m = get_meeting_for(db, user, body.meeting_id)
        if m.workspace_id != body.workspace_id:
            raise bad_request("The meeting belongs to a different workspace.")
        title = body.title or f"About “{m.title}”"
    c = AIConversation(workspace_id=body.workspace_id, user_id=user.id, meeting_id=body.meeting_id, title=title[:200])
    db.add(c)
    db.commit()
    return _out(c)


@router.get("/conversations/{conv_id}", response_model=S.ConversationDetailOut)
def get_conversation(conv_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _conv(db, user, conv_id)
    return S.ConversationDetailOut(**_out(c).model_dump(), messages=[_msg(m) for m in c.messages])


@router.delete("/conversations/{conv_id}", response_model=S.Message)
def delete_conversation(conv_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _conv(db, user, conv_id)
    db.delete(c)
    db.commit()
    return S.Message(message="Conversation deleted.")


@router.post("/conversations/{conv_id}/messages", response_model=list[S.AIMessageOut],
             dependencies=[Depends(rate_limit("assistant", 40, 3600))])
def ask(conv_id: str, body: S.AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _conv(db, user, conv_id)
    if body.project_id:
        p = get_project_for(db, user, body.project_id)
        if p.workspace_id != c.workspace_id:
            raise bad_request("The project belongs to a different workspace.")
    history = list(c.messages)
    question = body.content.strip()
    try:
        ans = answer_question(db, user, c.workspace_id, question, history, c.meeting_id, body.project_id)
    except AIProviderError as e:
        raise AppError(502, e.code, f"The AI provider could not answer: {e.message}") from e
    q = AIMessage(conversation_id=c.id, role="user", content=question)
    a = AIMessage(conversation_id=c.id, role="assistant", content=ans.content, mode=ans.mode,
                  citations=ans.citations, cited_meeting_ids=ans.meeting_ids, provider=ans.provider, model=ans.model)
    db.add_all([q, a])
    if not history and c.title == "New conversation":
        c.title = question[:80] + ("…" if len(question) > 80 else "")
    c.updated_at = utcnow()
    db.commit()
    return [_msg(q), _msg(a)]
