"""Request and response models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    message: str


class Stripped(BaseModel):
    """Input model whose text fields are trimmed before validation (never used for passwords)."""
    model_config = ConfigDict(str_strip_whitespace=True)


# --- Auth ---------------------------------------------------------------------------------------

class RegisterIn(BaseModel):  # not stripped: passwords are kept exactly as typed
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ProfileIn(Stripped):
    name: str = Field(min_length=1, max_length=120)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


# --- Workspaces -------------------------------------------------------------------------------

class WorkspaceIn(Stripped):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    recording_retention_days: int | None = Field(default=None, ge=1, le=3650)
    clear_retention: bool = False


class WorkspaceOut(BaseModel):
    id: str
    name: str
    role: str
    is_demo: bool
    recording_retention_days: int | None
    created_at: datetime


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


class MemberUpdate(BaseModel):
    role: Literal["owner", "admin", "member", "viewer"]


class MemberOut(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    created_at: datetime


# --- Projects ---------------------------------------------------------------------------------

class ProjectIn(Stripped):
    workspace_id: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    meeting_count: int = 0
    action_total: int = 0
    action_completed: int = 0
    action_open: int = 0
    decision_count: int = 0
    last_meeting_at: datetime | None = None


# --- Meetings ---------------------------------------------------------------------------------

class ParticipantIn(Stripped):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    role: str | None = Field(default=None, max_length=120)


class ParticipantOut(ParticipantIn):
    id: str


class MeetingIn(Stripped):
    workspace_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    meeting_date: datetime | None = None
    duration_minutes: float | None = Field(default=None, ge=0, le=24 * 60)
    project_id: str | None = None
    participants: list[ParticipantIn] = Field(default_factory=list, max_length=200)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    meeting_date: datetime | None = None
    duration_minutes: float | None = Field(default=None, ge=0, le=24 * 60)
    project_id: str | None = None
    clear_project: bool = False
    participants: list[ParticipantIn] | None = Field(default=None, max_length=200)


class RecordingOut(BaseModel):
    id: str
    original_filename: str
    audio_format: str
    content_type: str
    size_bytes: int
    duration_seconds: float | None
    sample_rate: int | None
    channels: int | None
    created_at: datetime
    audio_available: bool
    audio_deleted_at: datetime | None
    audio_deleted_reason: str | None


class JobOut(BaseModel):
    id: str
    meeting_id: str
    kind: str
    status: str
    stage: str | None
    progress_current: int | None
    progress_total: int | None
    attempts: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    provider: str | None
    model: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    run_after: datetime


class MeetingOut(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None
    project_name: str | None
    title: str
    description: str
    meeting_date: datetime
    duration_seconds: float | None
    status: str
    error_stage: str | None
    error_message: str | None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    participants: list[ParticipantOut]
    has_transcript: bool
    has_summary: bool
    action_count: int = 0
    decision_count: int = 0


class MeetingDetailOut(MeetingOut):
    recording: RecordingOut | None
    latest_job: JobOut | None
    transcript_info: dict[str, Any] | None


class UploadOut(BaseModel):
    meeting: MeetingDetailOut
    job: JobOut | None
    duplicate_of: list[dict[str, str]]
    notice: str | None


# --- Transcript -------------------------------------------------------------------------------

class SpeakerOut(BaseModel):
    id: str
    label: str
    ordinal: int
    display_name: str | None
    name: str
    segment_count: int


class SpeakerUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)


class SegmentOut(BaseModel):
    id: str
    position: int
    start_seconds: float | None
    end_seconds: float | None
    speaker_id: str | None
    speaker_name: str | None
    text: str
    original_text: str
    edited: bool
    edited_at: datetime | None


class SegmentUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=20000)
    speaker_id: str | None = None
    revert: bool = False


class TranscriptOut(BaseModel):
    meeting_id: str
    provider: str
    model: str | None
    language: str | None
    has_timestamps: bool
    has_diarization: bool
    chunk_count: int
    speaker_ids_per_part: bool
    created_at: datetime
    edited_at: datetime | None
    speakers: list[SpeakerOut]
    segments: list[SegmentOut]


# --- Analysis ---------------------------------------------------------------------------------

class SummaryOut(BaseModel):
    meeting_id: str
    executive_summary: str
    discussion_points: list[dict[str, Any]]
    open_questions: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    follow_ups: list[dict[str, Any]]
    key_dates: list[dict[str, Any]]
    grounding_notes: list[str]
    provider: str
    model: str | None
    chunked: bool
    created_at: datetime


class DecisionIn(BaseModel):
    meeting_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    meeting_status: Literal["confirmed", "proposed", "uncertain"] = "confirmed"
    participants: list[str] = Field(default_factory=list, max_length=50)


class DecisionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    meeting_status: Literal["confirmed", "proposed", "uncertain"] | None = None
    review_status: Literal["unreviewed", "confirmed", "rejected"] | None = None
    participants: list[str] | None = Field(default=None, max_length=50)


class DecisionOut(BaseModel):
    id: str
    meeting_id: str
    meeting_title: str
    meeting_date: datetime
    project_id: str | None
    title: str
    description: str
    meeting_status: str
    review_status: str
    participants: list[str]
    source_segment_ids: list[str]
    excerpt: str | None
    origin: str
    user_modified: bool
    created_at: datetime
    updated_at: datetime


class ActionIn(BaseModel):
    meeting_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    priority: Literal["high", "medium", "low"] | None = None
    notes: str = Field(default="", max_length=5000)


class ActionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    owner: str | None = Field(default=None, max_length=120)
    clear_owner: bool = False
    due_date: date | None = None
    clear_due_date: bool = False
    priority: Literal["high", "medium", "low"] | None = None
    clear_priority: bool = False
    status: Literal["todo", "in_progress", "completed", "cancelled"] | None = None
    notes: str | None = Field(default=None, max_length=5000)
    needs_confirmation: bool | None = None


class ActionOut(BaseModel):
    id: str
    meeting_id: str
    meeting_title: str
    meeting_date: datetime
    project_id: str | None
    title: str
    description: str
    owner: str | None
    owner_source: str | None
    due_date: date | None
    due_text: str | None
    due_source: str | None
    priority: str | None
    priority_source: str | None
    needs_confirmation: bool
    status: str
    notes: str
    source_segment_ids: list[str]
    excerpt: str | None
    origin: str
    user_modified: bool
    overdue: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Assistant --------------------------------------------------------------------------------

class ConversationIn(BaseModel):
    workspace_id: str
    meeting_id: str | None = None
    title: str | None = Field(default=None, max_length=200)


class ConversationOut(BaseModel):
    id: str
    workspace_id: str
    meeting_id: str | None
    title: str
    created_at: datetime
    updated_at: datetime


class AskIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    project_id: str | None = None


class AIMessageOut(BaseModel):
    id: str
    role: str
    content: str
    mode: str | None
    citations: list[dict[str, Any]]
    provider: str | None
    model: str | None
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[AIMessageOut]


# --- Reports ----------------------------------------------------------------------------------

class ReportIn(BaseModel):
    format: Literal["pdf", "html"] = "pdf"
    include_transcript: bool = False


class ReportOut(BaseModel):
    id: str
    meeting_id: str
    meeting_title: str
    format: str
    size_bytes: int
    include_transcript: bool
    created_at: datetime
