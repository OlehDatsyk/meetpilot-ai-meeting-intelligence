export type Role = "owner" | "admin" | "member" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  role: Role;
  is_demo: boolean;
  recording_retention_days: number | null;
  created_at: string;
}

export interface Member {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: Role;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Participant {
  id?: string;
  name: string;
  email?: string | null;
  role?: string | null;
}

export type MeetingStatus =
  | "draft"
  | "uploaded"
  | "queued"
  | "transcribing"
  | "transcribed"
  | "analysing"
  | "completed"
  | "failed"
  | "cancelled";

export interface Recording {
  id: string;
  original_filename: string;
  audio_format: string;
  content_type: string;
  size_bytes: number;
  duration_seconds: number | null;
  sample_rate: number | null;
  channels: number | null;
  created_at: string;
  audio_available: boolean;
  audio_deleted_at: string | null;
  audio_deleted_reason: string | null;
}

export interface Job {
  id: string;
  meeting_id: string;
  kind: "transcription" | "analysis";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  stage: string | null;
  progress_current: number | null;
  progress_total: number | null;
  attempts: number;
  max_attempts: number;
  error_code: string | null;
  error_message: string | null;
  provider: string | null;
  model: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  run_after: string;
}

export interface Meeting {
  id: string;
  workspace_id: string;
  project_id: string | null;
  project_name: string | null;
  title: string;
  description: string;
  meeting_date: string;
  duration_seconds: number | null;
  status: MeetingStatus;
  error_stage: "transcription" | "analysis" | null;
  error_message: string | null;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  participants: Participant[];
  has_transcript: boolean;
  has_summary: boolean;
  action_count: number;
  decision_count: number;
}

export interface MeetingDetail extends Meeting {
  recording: Recording | null;
  latest_job: Job | null;
  transcript_info: {
    provider: string;
    model: string | null;
    language: string | null;
    has_timestamps: boolean;
    has_diarization: boolean;
    chunk_count: number;
    created_at: string;
    edited_at: string | null;
  } | null;
}

export interface Speaker {
  id: string;
  label: string;
  ordinal: number;
  display_name: string | null;
  name: string;
  segment_count: number;
}

export interface Segment {
  id: string;
  position: number;
  start_seconds: number | null;
  end_seconds: number | null;
  speaker_id: string | null;
  speaker_name: string | null;
  text: string;
  original_text: string;
  edited: boolean;
  edited_at: string | null;
}

export interface Transcript {
  meeting_id: string;
  provider: string;
  model: string | null;
  language: string | null;
  has_timestamps: boolean;
  has_diarization: boolean;
  chunk_count: number;
  speaker_ids_per_part: boolean;
  created_at: string;
  edited_at: string | null;
  speakers: Speaker[];
  segments: Segment[];
}

export interface Cited {
  text: string;
  segment_ids: string[];
}

export interface Summary {
  meeting_id: string;
  executive_summary: string;
  discussion_points: { topic: string; summary: string; segment_ids: string[] }[];
  open_questions: Cited[];
  risks: Cited[];
  follow_ups: Cited[];
  key_dates: { date_text: string; date: string | null; interpreted: boolean; description: string; segment_ids: string[] }[];
  grounding_notes: string[];
  provider: string;
  model: string | null;
  chunked: boolean;
  created_at: string;
}

export interface Decision {
  id: string;
  meeting_id: string;
  meeting_title: string;
  meeting_date: string;
  project_id: string | null;
  title: string;
  description: string;
  meeting_status: "confirmed" | "proposed" | "uncertain";
  review_status: "unreviewed" | "confirmed" | "rejected";
  participants: string[];
  source_segment_ids: string[];
  excerpt: string | null;
  origin: "ai" | "user";
  user_modified: boolean;
  created_at: string;
  updated_at: string;
}

export type ActionStatus = "todo" | "in_progress" | "completed" | "cancelled";

export interface ActionItem {
  id: string;
  meeting_id: string;
  meeting_title: string;
  meeting_date: string;
  project_id: string | null;
  title: string;
  description: string;
  owner: string | null;
  owner_source: string | null;
  due_date: string | null;
  due_text: string | null;
  due_source: "transcript" | "ai_interpreted" | "user" | null;
  priority: "high" | "medium" | "low" | null;
  priority_source: "stated" | "ai_suggested" | "user" | null;
  needs_confirmation: boolean;
  status: ActionStatus;
  notes: string;
  source_segment_ids: string[];
  excerpt: string | null;
  origin: "ai" | "user";
  user_modified: boolean;
  overdue: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  meeting_count: number;
  action_total: number;
  action_completed: number;
  action_open: number;
  decision_count: number;
  last_meeting_at: string | null;
}

export interface Citation {
  label: string;
  type: "segment" | "meeting" | "action" | "decision";
  meeting_id: string;
  meeting_title: string;
  meeting_date: string;
  segment_id?: string;
  start_seconds?: number | null;
  speaker?: string | null;
  excerpt?: string | null;
}

export interface AIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  mode: "ai" | "retrieval_only" | "no_results" | null;
  citations: Citation[];
  provider: string | null;
  model: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  workspace_id: string;
  meeting_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Report {
  id: string;
  meeting_id: string;
  meeting_title: string;
  format: "pdf" | "html";
  size_bytes: number;
  include_transcript: boolean;
  created_at: string;
}

export interface Activity {
  id: string;
  action: string;
  summary: string;
  meeting_id: string | null;
  user_name: string | null;
  created_at: string;
}

export interface SystemStatus {
  version: string;
  environment: string;
  transcription: {
    configured: boolean;
    provider: string;
    model?: string;
    diarization?: boolean;
    timestamps?: boolean;
    error?: string;
    max_upload_mb?: number | null;
  };
  ai: {
    configured: boolean;
    provider: string;
    model?: string;
    fallbacks?: { provider: string; model: string }[];
    error?: string | null;
  };
  storage: { provider: string; persistent: boolean };
  uploads: { max_size_mb: number; max_duration_minutes: number; extensions: string[]; ffmpeg_available: boolean };
  worker: { embedded: boolean };
  semantic_search: boolean;
  password_reset_email: boolean;
}
