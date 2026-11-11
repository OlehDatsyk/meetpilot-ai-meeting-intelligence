import type { ActionItem, MeetingStatus } from "./types";

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "—";
  const m = Math.round(seconds / 60);
  if (m < 1) return `${Math.round(seconds)} s`;
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function formatHours(seconds: number): string {
  if (!seconds) return "0 min";
  const h = seconds / 3600;
  return h >= 1 ? `${h.toFixed(h >= 10 ? 0 : 1)} h` : `${Math.round(seconds / 60)} min`;
}

export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "";
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dateFmt.format(d);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dateTimeFmt.format(d);
}

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return formatDate(iso);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const STATUS_LABEL: Record<MeetingStatus, string> = {
  draft: "No recording",
  uploaded: "Uploaded",
  queued: "Queued",
  transcribing: "Transcribing",
  transcribed: "Transcription completed",
  analysing: "Analysing",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const ACTION_STATUS_LABEL = {
  todo: "To do",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
} as const;

export function ownerLabel(a: Pick<ActionItem, "owner">) {
  return a.owner || "Unassigned";
}

export function dueLabel(a: Pick<ActionItem, "due_date">) {
  return a.due_date ? formatDate(a.due_date) : "No deadline specified";
}

export function isActive(status: MeetingStatus) {
  return status === "queued" || status === "transcribing" || status === "analysing";
}
