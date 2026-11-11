import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileAudio, Info, UploadCloud, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router";
import { Button, Card, CardHeader, ErrorBox, Notice, PageHeader } from "../components/ui";
import { ApiError, get, post, uploadFile } from "../lib/api";
import { formatBytes } from "../lib/format";
import { canEdit, useWorkspace } from "../lib/session";
import type { MeetingDetail, SystemStatus } from "../lib/types";
import { MeetingForm, meetingPayload, toLocalInput, useProjects, type MeetingFormValue } from "./Meetings";

interface UploadOut { meeting: MeetingDetail; job: unknown; duplicate_of: { meeting_id: string; title: string }[]; notice: string | null }

export function RecordingUploader({ meetingId, replace, onDone }: { meetingId: string; replace?: boolean; onDone: (r: UploadOut) => void }) {
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => get<SystemStatus>("/api/v1/system/status"), staleTime: 300_000 });
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const abort = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const limits = status.data?.uploads;

  const pick = (f: File | undefined | null) => {
    setError(null);
    if (!f) return;
    const ext = `.${f.name.split(".").pop()?.toLowerCase()}`;
    if (limits && !limits.extensions.includes(ext)) return setError(new Error(`Unsupported file type ${ext}. Use MP3, WAV, M4A, AAC, OGG or FLAC.`));
    if (limits && f.size > limits.max_size_mb * 1024 * 1024) return setError(new Error(`The file is larger than the ${limits.max_size_mb} MB limit.`));
    setFile(f);
  };
  const start = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("replace", replace ? "true" : "false");
    abort.current = new AbortController();
    setProgress(0);
    setError(null);
    try {
      const r = await uploadFile<UploadOut>(`/api/v1/meetings/${meetingId}/recording`, form, setProgress, abort.current.signal);
      onDone(r);
    } catch (e) {
      if (!(e instanceof ApiError && e.code === "aborted")) setError(e);
    } finally {
      setProgress(null);
    }
  };

  return (
    <div className="space-y-3">
      {status.data && !status.data.transcription.configured && (
        <Notice tone="amber" icon={<Info className="mt-0.5 size-4 shrink-0" />}>
          No transcription provider is configured on this server, so the recording will be stored but not transcribed. An administrator can set one up (see Settings → AI and transcription).
        </Notice>
      )}
      {!file ? (
        <div onDragOver={(e: DragEvent) => e.preventDefault()} onDrop={(e: DragEvent) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}
          className="flex flex-col items-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/60 px-6 py-10 text-center">
          <UploadCloud className="size-8 text-slate-400" />
          <p className="mt-3 text-sm font-medium">Drop an audio file here</p>
          <p className="mt-1 text-xs text-muted">
            MP3, WAV, M4A, AAC, OGG or FLAC{limits ? ` · up to ${limits.max_size_mb} MB and ${limits.max_duration_minutes} minutes` : ""}
          </p>
          <Button variant="secondary" className="mt-4" onClick={() => input.current?.click()}>Choose file</Button>
          <input ref={input} type="file" className="hidden" accept={limits?.extensions.join(",") ?? "audio/*"} onChange={(e) => pick(e.target.files?.[0])} />
        </div>
      ) : (
        <div className="rounded-xl border border-line p-4">
          <div className="flex items-center gap-3">
            <FileAudio className="size-8 shrink-0 text-accent" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{file.name}</div>
              <div className="text-xs text-muted">{formatBytes(file.size)}</div>
            </div>
            {progress === null && <button onClick={() => setFile(null)} aria-label="Remove file" className="rounded p-1 text-slate-400 hover:bg-slate-100"><X className="size-4" /></button>}
          </div>
          {progress !== null && (
            <div className="mt-3">
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
                <div className="h-full bg-accent transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
              </div>
              <div className="mt-1.5 flex justify-between text-xs text-muted">
                <span>{progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : "Checking the audio file…"}</span>
                {progress < 1 && <button className="text-red-600 hover:underline" onClick={() => abort.current?.abort()}>Cancel</button>}
              </div>
            </div>
          )}
        </div>
      )}
      <ErrorBox error={error} />
      {file && progress === null && <Button onClick={start}>{replace ? "Replace recording" : "Upload and process"}</Button>}
    </div>
  );
}

export default function UploadPage() {
  const ws = useWorkspace();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const projects = useProjects();
  const [form, setForm] = useState<MeetingFormValue>({ title: "", date: toLocalInput(), project_id: "", participants: "", description: "" });
  const [meetingId, setMeetingId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (!canEdit(ws)) return <><PageHeader title="Upload recording" /><Notice tone="amber">Your role in this workspace is read-only.</Notice></>;

  const createMeeting = async () => {
    setBusy(true);
    setError(null);
    try {
      const m = await post<MeetingDetail>("/api/v1/meetings", { workspace_id: ws.id, project_id: form.project_id || null, ...meetingPayload(form) });
      setMeetingId(m.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Upload recording" description="Create the meeting, then upload its audio. Processing runs in the background; you can leave this page." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="1. Meeting details" />
            <div className="p-5">
              {meetingId ? (
                <p className="text-sm">Meeting <span className="font-medium">{form.title}</span> created. <Link to={`/meetings/${meetingId}`} className="text-accent hover:underline">Open it</Link></p>
              ) : (
                <>
                  <ErrorBox error={error} className="mb-4" />
                  <MeetingForm value={form} onChange={setForm} projects={projects.data ?? []} />
                  <Button className="mt-4" loading={busy} disabled={!form.title.trim()} onClick={createMeeting}>Continue</Button>
                </>
              )}
            </div>
          </Card>
          <Card className={meetingId ? "" : "pointer-events-none opacity-50"}>
            <CardHeader title="2. Recording" />
            <div className="p-5">
              {meetingId ? (
                <RecordingUploader meetingId={meetingId} onDone={(r) => {
                  qc.invalidateQueries({ queryKey: ["meetings", ws.id] });
                  qc.invalidateQueries({ queryKey: ["dashboard", ws.id] });
                  navigate(`/meetings/${r.meeting.id}`, { state: { notice: r.notice, duplicates: r.duplicate_of } });
                }} />
              ) : <p className="text-sm text-muted">Fill in the meeting details first.</p>}
            </div>
          </Card>
        </div>
        <Card className="h-fit p-5 text-sm text-slate-600">
          <h2 className="font-semibold text-ink">What happens next</h2>
          <ol className="mt-3 list-decimal space-y-2 pl-4">
            <li>The file is checked: its content must be real audio, not just the right extension.</li>
            <li>The audio is sent to the configured transcription provider. Long recordings are split into parts.</li>
            <li>If an AI provider is configured, the transcript is analysed for a summary, decisions and action items.</li>
          </ol>
          <p className="mt-4 text-xs text-muted">Only upload recordings you have permission to record and process. See the <Link to="/privacy" className="text-accent hover:underline">privacy notice</Link>.</p>
        </Card>
      </div>
    </>
  );
}
