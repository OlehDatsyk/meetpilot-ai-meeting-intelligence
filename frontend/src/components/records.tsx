import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CalendarClock, CheckCircle2, Circle, CircleDot, Pencil, Sparkles, Trash2, User, XCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { del, patch, post } from "../lib/api";
import { ACTION_STATUS_LABEL, dueLabel, formatDate, formatDuration, ownerLabel } from "../lib/format";
import type { ActionItem, ActionStatus, Decision, Meeting } from "../lib/types";
import { Badge, Button, DemoBadge, ErrorBox, Field, Modal, StatusBadge } from "./ui";

// --- Meetings -----------------------------------------------------------------------------------

export function MeetingList({ meetings }: { meetings: Meeting[] }) {
  return (
    <ul className="divide-y divide-line">
      {meetings.map((m) => (
        <li key={m.id}>
          <Link to={`/meetings/${m.id}`} className="flex flex-col gap-2 px-5 py-3.5 hover:bg-slate-50 sm:flex-row sm:items-center sm:gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-ink">{m.title}</span>
                {m.is_demo && <DemoBadge />}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted">
                <span>{formatDate(m.meeting_date)}</span>
                <span>{formatDuration(m.duration_seconds)}</span>
                {m.project_name && <span>{m.project_name}</span>}
                {m.participants.length > 0 && <span>{m.participants.length} participant{m.participants.length === 1 ? "" : "s"}</span>}
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted">
              {m.status === "completed" && <span>{m.action_count} actions · {m.decision_count} decisions</span>}
              <StatusBadge status={m.status} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

// --- Action items -------------------------------------------------------------------------------

const STATUS_ICON: Record<ActionStatus, typeof Circle> = { todo: Circle, in_progress: CircleDot, completed: CheckCircle2, cancelled: XCircle };

export function PriorityBadge({ a }: { a: Pick<ActionItem, "priority" | "priority_source"> }) {
  if (!a.priority) return null;
  const tone = a.priority === "high" ? "red" : a.priority === "medium" ? "amber" : "gray";
  const suggested = a.priority_source === "ai_suggested";
  return (
    <Badge tone={tone} title={suggested ? "Suggested by AI, not agreed in the meeting" : a.priority_source === "stated" ? "Stated in the meeting" : "Set by a user"}>
      {suggested && <Sparkles className="size-3" aria-hidden />}
      {a.priority[0].toUpperCase() + a.priority.slice(1)}{suggested ? " (AI suggestion)" : ""}
    </Badge>
  );
}

export function DueText({ a }: { a: ActionItem }) {
  if (!a.due_date) return <span className="text-muted">No deadline specified</span>;
  return (
    <span className={a.overdue ? "font-medium text-red-700" : ""} title={a.due_text ? `Said in the meeting: “${a.due_text}”` : undefined}>
      {dueLabel(a)}{a.overdue && " · overdue"}
      {a.due_source === "ai_interpreted" && <span className="ml-1 text-xs font-normal text-amber-700">(interpreted from “{a.due_text}”)</span>}
    </span>
  );
}

export function useActionMutations(invalidate: string[][]) {
  const qc = useQueryClient();
  const done = () => invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }));
  const update = useMutation({ mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => patch<ActionItem>(`/api/v1/action-items/${id}`, body), onSuccess: done });
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/v1/action-items/${id}`), onSuccess: done });
  return { update, remove };
}

export function ActionList({ items, invalidate, readOnly, showMeeting = true, onJump }:
  { items: ActionItem[]; invalidate: string[][]; readOnly?: boolean; showMeeting?: boolean; onJump?: (segmentId: string) => void }) {
  const { update, remove } = useActionMutations(invalidate);
  const [editing, setEditing] = useState<ActionItem | null>(null);
  const cycle: Record<ActionStatus, ActionStatus> = { todo: "in_progress", in_progress: "completed", completed: "todo", cancelled: "todo" };
  return (
    <>
      <ErrorBox error={update.error || remove.error} className="mx-5 mt-3" />
      <ul className="divide-y divide-line">
        {items.map((a) => {
          const Icon = STATUS_ICON[a.status];
          return (
            <li key={a.id} className="flex gap-3 px-5 py-3.5">
              <button disabled={readOnly || update.isPending} onClick={() => update.mutate({ id: a.id, body: { status: cycle[a.status] } })}
                title={`${ACTION_STATUS_LABEL[a.status]} — click to change`} aria-label={`Status: ${ACTION_STATUS_LABEL[a.status]}. Change status`}
                className={`mt-0.5 shrink-0 ${a.status === "completed" ? "text-emerald-600" : a.status === "in_progress" ? "text-accent" : "text-slate-400"} disabled:cursor-default`}>
                <Icon className="size-5" />
              </button>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-sm font-medium ${a.status === "completed" || a.status === "cancelled" ? "text-muted line-through" : "text-ink"}`}>{a.title}</span>
                  <PriorityBadge a={a} />
                  {a.needs_confirmation && <Badge tone="amber" title="Some details were unclear in the meeting"><AlertCircle className="size-3" />Needs confirmation</Badge>}
                  {a.status === "in_progress" && <Badge tone="indigo">In progress</Badge>}
                  {a.status === "cancelled" && <Badge>Cancelled</Badge>}
                </div>
                {a.description && <p className="mt-0.5 text-sm text-slate-600">{a.description}</p>}
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                  <span className="inline-flex items-center gap-1"><User className="size-3.5 text-slate-400" />{ownerLabel(a)}</span>
                  <span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5 text-slate-400" /><DueText a={a} /></span>
                  {showMeeting && <Link to={`/meetings/${a.meeting_id}?tab=actions`} className="text-accent hover:underline">{a.meeting_title}</Link>}
                </div>
                {a.excerpt && (
                  <button type="button" onClick={() => onJump && a.source_segment_ids[0] && onJump(a.source_segment_ids[0])} disabled={!onJump}
                    className="mt-2 block w-full rounded-md border-l-2 border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left text-xs text-slate-600 enabled:hover:border-accent">
                    “{a.excerpt}”
                  </button>
                )}
                {a.notes && <p className="mt-1.5 text-xs text-slate-600"><span className="font-medium">Notes:</span> {a.notes}</p>}
              </div>
              {!readOnly && (
                <div className="flex shrink-0 items-start gap-1">
                  <button onClick={() => setEditing(a)} className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label="Edit action item"><Pencil className="size-4" /></button>
                  <button onClick={() => confirm("Delete this action item?") && remove.mutate(a.id)} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Delete action item"><Trash2 className="size-4" /></button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {editing && <ActionEditor action={editing} onClose={() => setEditing(null)} invalidate={invalidate} />}
    </>
  );
}

export function ActionEditor({ action, meetingId, onClose, invalidate }:
  { action?: ActionItem; meetingId?: string; onClose: () => void; invalidate: string[][] }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    title: action?.title ?? "", description: action?.description ?? "", owner: action?.owner ?? "",
    due_date: action?.due_date ?? "", priority: action?.priority ?? "", status: action?.status ?? "todo",
    notes: action?.notes ?? "", needs_confirmation: action?.needs_confirmation ?? false,
  });
  const save = useMutation({
    mutationFn: () => {
      if (!action) {
        return post("/api/v1/action-items", { meeting_id: meetingId, title: f.title, description: f.description,
          owner: f.owner || null, due_date: f.due_date || null, priority: f.priority || null, notes: f.notes });
      }
      return patch(`/api/v1/action-items/${action.id}`, {
        title: f.title, description: f.description, notes: f.notes, status: f.status,
        needs_confirmation: f.needs_confirmation,
        ...(f.owner ? { owner: f.owner } : { clear_owner: true }),
        ...(f.due_date ? { due_date: f.due_date } : { clear_due_date: true }),
        ...(f.priority ? { priority: f.priority } : { clear_priority: true }),
      });
    },
    onSuccess: () => { invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k })); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title={action ? "Edit action item" : "Add action item"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} disabled={!f.title.trim()} onClick={() => save.mutate()}>Save</Button></>}>
      <ErrorBox error={save.error} />
      <Field label="Task" htmlFor="a-title"><input id="a-title" className="input" maxLength={300} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <Field label="Description" htmlFor="a-desc"><textarea id="a-desc" rows={2} className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Responsible person" htmlFor="a-owner" hint="Leave empty for Unassigned."><input id="a-owner" className="input" maxLength={120} value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} /></Field>
        <Field label="Deadline" htmlFor="a-due"><input id="a-due" type="date" className="input" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
        <Field label="Priority" htmlFor="a-prio">
          <select id="a-prio" className="input" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value as typeof f.priority })}>
            <option value="">Not set</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
          </select>
        </Field>
        {action && (
          <Field label="Status" htmlFor="a-status">
            <select id="a-status" className="input" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as ActionStatus })}>
              {Object.entries(ACTION_STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
        )}
      </div>
      <Field label="Notes" htmlFor="a-notes"><textarea id="a-notes" rows={2} className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      {action && (
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.needs_confirmation} onChange={(e) => setF({ ...f, needs_confirmation: e.target.checked })} />Needs confirmation</label>
      )}
    </Modal>
  );
}

// --- Decisions ----------------------------------------------------------------------------------

const MEETING_STATUS = {
  confirmed: { label: "Confirmed in meeting", tone: "green" },
  proposed: { label: "Proposed, not confirmed", tone: "amber" },
  uncertain: { label: "Uncertain", tone: "amber" },
} as const;

export function DecisionList({ items, invalidate, readOnly, showMeeting = true, onJump }:
  { items: Decision[]; invalidate: string[][]; readOnly?: boolean; showMeeting?: boolean; onJump?: (segmentId: string) => void }) {
  const qc = useQueryClient();
  const done = () => invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }));
  const update = useMutation({ mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => patch(`/api/v1/decisions/${id}`, body), onSuccess: done });
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/v1/decisions/${id}`), onSuccess: done });
  const [editing, setEditing] = useState<Decision | null>(null);
  return (
    <>
      <ErrorBox error={update.error || remove.error} className="mx-5 mt-3" />
      <ul className="divide-y divide-line">
        {items.map((d) => {
          const ms = MEETING_STATUS[d.meeting_status];
          return (
            <li key={d.id} className={`px-5 py-4 ${d.review_status === "rejected" ? "opacity-60" : ""}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{d.title}</span>
                    <Badge tone={ms.tone}>{ms.label}</Badge>
                    {d.review_status === "confirmed" && <Badge tone="indigo"><CheckCircle2 className="size-3" />Reviewed</Badge>}
                    {d.review_status === "rejected" && <Badge>Rejected in review</Badge>}
                    {d.origin === "ai" && d.review_status === "unreviewed" && <Badge tone="violet"><Sparkles className="size-3" />AI extracted · not reviewed</Badge>}
                  </div>
                  {d.description && <p className="mt-1 text-sm text-slate-600">{d.description}</p>}
                  <div className="mt-1.5 flex flex-wrap gap-x-4 text-xs text-muted">
                    {showMeeting && <Link to={`/meetings/${d.meeting_id}?tab=decisions`} className="text-accent hover:underline">{d.meeting_title}</Link>}
                    <span>{formatDate(d.meeting_date)}</span>
                    {d.participants.length > 0 && <span>{d.participants.join(", ")}</span>}
                  </div>
                  {d.excerpt && (
                    <button type="button" disabled={!onJump} onClick={() => onJump && d.source_segment_ids[0] && onJump(d.source_segment_ids[0])}
                      className="mt-2 block w-full rounded-md border-l-2 border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left text-xs text-slate-600 enabled:hover:border-accent">
                      “{d.excerpt}”
                    </button>
                  )}
                </div>
                {!readOnly && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {d.review_status !== "confirmed" && <Button size="sm" variant="secondary" onClick={() => update.mutate({ id: d.id, body: { review_status: "confirmed" } })}>Confirm</Button>}
                    {d.review_status !== "rejected" && <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: d.id, body: { review_status: "rejected" } })}>Reject</Button>}
                    {d.review_status !== "unreviewed" && <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: d.id, body: { review_status: "unreviewed" } })}>Reset</Button>}
                    <button onClick={() => setEditing(d)} className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label="Edit decision"><Pencil className="size-4" /></button>
                    <button onClick={() => confirm("Delete this decision?") && remove.mutate(d.id)} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Delete decision"><Trash2 className="size-4" /></button>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {editing && <DecisionEditor decision={editing} onClose={() => setEditing(null)} invalidate={invalidate} />}
    </>
  );
}

export function DecisionEditor({ decision, meetingId, onClose, invalidate }:
  { decision?: Decision; meetingId?: string; onClose: () => void; invalidate: string[][] }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ title: decision?.title ?? "", description: decision?.description ?? "",
    meeting_status: decision?.meeting_status ?? "confirmed", participants: decision?.participants.join(", ") ?? "" });
  const save = useMutation({
    mutationFn: () => {
      const body = { title: f.title, description: f.description, meeting_status: f.meeting_status,
        participants: f.participants.split(",").map((p) => p.trim()).filter(Boolean) };
      return decision ? patch(`/api/v1/decisions/${decision.id}`, body) : post("/api/v1/decisions", { ...body, meeting_id: meetingId });
    },
    onSuccess: () => { invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k })); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title={decision ? "Edit decision" : "Record a decision"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} disabled={!f.title.trim()} onClick={() => save.mutate()}>Save</Button></>}>
      <ErrorBox error={save.error} />
      <Field label="Decision" htmlFor="d-title"><input id="d-title" className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <Field label="Details" htmlFor="d-desc"><textarea id="d-desc" rows={3} className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <Field label="Status in the meeting" htmlFor="d-status">
        <select id="d-status" className="input" value={f.meeting_status} onChange={(e) => setF({ ...f, meeting_status: e.target.value as Decision["meeting_status"] })}>
          <option value="confirmed">Confirmed in meeting</option><option value="proposed">Proposed, not confirmed</option><option value="uncertain">Uncertain</option>
        </select>
      </Field>
      <Field label="Relevant participants" htmlFor="d-people" hint="Comma separated."><input id="d-people" className="input" value={f.participants} onChange={(e) => setF({ ...f, participants: e.target.value })} /></Field>
    </Modal>
  );
}
