"""SQLAlchemy models. Audio is never stored in the database: recordings hold a storage key only."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


# --- Users and workspaces ---------------------------------------------------------------------

class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[WorkspaceMember]] = relationship(back_populates="user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recording_retention_days: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    members: Mapped[list[WorkspaceMember]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")  # owner|admin|member|viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


# --- Projects and meetings --------------------------------------------------------------------

class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


MEETING_STATUSES = ("draft", "uploaded", "queued", "transcribing", "transcribed", "analysing", "completed",
                    "failed", "cancelled")


class Meeting(TimestampMixin, Base):
    __tablename__ = "meetings"
    __table_args__ = (Index("ix_meetings_ws_date", "workspace_id", "meeting_date"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meeting_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    error_stage: Mapped[str | None] = mapped_column(String(20))  # transcription | analysis
    error_message: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    project: Mapped[Project | None] = relationship()
    participants: Mapped[list[Participant]] = relationship(cascade="all, delete-orphan",
                                                            order_by="Participant.name")
    recording: Mapped[Recording | None] = relationship(cascade="all, delete-orphan", uselist=False)
    transcript: Mapped[Transcript | None] = relationship(cascade="all, delete-orphan", uselist=False)
    segments: Mapped[list[TranscriptSegment]] = relationship(cascade="all, delete-orphan",
                                                              order_by="TranscriptSegment.position")
    speakers: Mapped[list[Speaker]] = relationship(cascade="all, delete-orphan", order_by="Speaker.label")
    summary: Mapped[MeetingSummary | None] = relationship(cascade="all, delete-orphan", uselist=False)
    decisions: Mapped[list[Decision]] = relationship(cascade="all, delete-orphan")
    action_items: Mapped[list[ActionItem]] = relationship(cascade="all, delete-orphan")
    jobs: Mapped[list[ProcessingJob]] = relationship(cascade="all, delete-orphan")
    reports: Mapped[list[Report]] = relationship(cascade="all, delete-orphan")


class Participant(Base):
    __tablename__ = "participants"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True,
                                            nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    role: Mapped[str | None] = mapped_column(String(120))


class Recording(Base):
    __tablename__ = "recordings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True,
                                            nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500))  # None once the audio file was deleted
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_format: Mapped[str] = mapped_column(String(10), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_deleted_reason: Mapped[str | None] = mapped_column(String(40))


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_jobs_status_run_after", "status", "run_after"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True,
                                            nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # transcription | analysis
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    # queued | running | succeeded | failed | cancelled
    stage: Mapped[str | None] = mapped_column(String(200))
    progress_current: Mapped[int | None] = mapped_column(Integer)
    progress_total: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Transcripts ------------------------------------------------------------------------------

class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True,
                                            nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(20))
    has_timestamps: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_diarization: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Speaker(Base):
    __tablename__ = "speakers"
    __table_args__ = (UniqueConstraint("meeting_id", "label", name="uq_speaker_label"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True,
                                            nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)  # original provider speaker id, never changed
    display_name: Mapped[str | None] = mapped_column(String(120))  # user supplied only
    ordinal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 1-based "Speaker N"


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (Index("ix_segments_meeting_position", "meeting_id", "position"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float | None] = mapped_column(Float)
    end_seconds: Mapped[float | None] = mapped_column(Float)
    speaker_id: Mapped[str | None] = mapped_column(ForeignKey("speakers.id", ondelete="SET NULL"))
    original_text: Mapped[str] = mapped_column(Text, nullable=False)  # machine output, never edited
    text: Mapped[str] = mapped_column(Text, nullable=False)  # current text, may be user edited
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    speaker: Mapped[Speaker | None] = relationship()


# --- AI analysis ------------------------------------------------------------------------------

class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True,
                                            nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    discussion_points: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    open_questions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    follow_ups: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    key_dates: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    grounding_notes: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    chunked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Decision(TimestampMixin, Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True,
                                            nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meeting_status: Mapped[str] = mapped_column(String(20), default="uncertain", nullable=False)
    # confirmed (agreed in the meeting) | proposed | uncertain
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)
    # unreviewed | confirmed | rejected  (the user's review)
    participants: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(10), default="ai", nullable=False)  # ai | user
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


ACTION_STATUSES = ("todo", "in_progress", "completed", "cancelled")


class ActionItem(TimestampMixin, Base):
    __tablename__ = "action_items"
    __table_args__ = (Index("ix_actions_ws_status", "workspace_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True,
                                            nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner: Mapped[str | None] = mapped_column(String(120))
    owner_source: Mapped[str | None] = mapped_column(String(20))  # transcript | user
    due_date: Mapped[date | None] = mapped_column(Date)
    due_text: Mapped[str | None] = mapped_column(String(200))  # verbatim phrase from the transcript
    due_source: Mapped[str | None] = mapped_column(String(20))  # transcript | ai_interpreted | user
    priority: Mapped[str | None] = mapped_column(String(10))  # high | medium | low
    priority_source: Mapped[str | None] = mapped_column(String(20))  # stated | ai_suggested | user
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(10), default="ai", nullable=False)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    meeting: Mapped[Meeting] = relationship(viewonly=True)


# --- Assistant, reports, activity -------------------------------------------------------------

class AIConversation(TimestampMixin, Base):
    __tablename__ = "ai_conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    messages: Mapped[list[AIMessage]] = relationship(cascade="all, delete-orphan", order_by="AIMessage.created_at")


class AIMessage(Base):
    __tablename__ = "ai_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True,
                                                 nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str | None] = mapped_column(String(20))  # ai | retrieval_only | no_results
    citations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    cited_meeting_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True,
                                            nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
                                              nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf | html
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    include_transcript: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ActivityRecord(Base):
    __tablename__ = "activity_records"
    __table_args__ = (Index("ix_activity_ws_created", "workspace_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
