import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Bot, Download, FileText, Loader2, Plus, RefreshCw, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { ActionEditor, ActionList, DecisionEditor, DecisionList } from "../components/records";
import { SummaryView } from "../components/SummaryView";
import { TranscriptViewer } from "../components/TranscriptViewer";
import { Badge, Button, Card, CardHeader, DemoBadge, EmptyState, ErrorBox, Modal, Notice, PageHeader, Spinner, StatusBadge, Tabs } from "../components/ui";
import { ApiError, del, download, get, patch, post, qs } from "../lib/api";
import { formatBytes, formatDateTime, formatDuration, isActive } from "../lib/format";
import { canEdit, useWorkspace } from "../lib/session";
import type { ActionItem, Decision, Job, MeetingDetail, Page, Report, Summary, SystemStatus, Transcript } from "../lib/types";
import { MeetingForm, meetingPayload, toLocalInput, useProjects, type MeetingFormValue } from "./Meetings";
import { RecordingUploader } from "./Upload";

type Tab = "summary" | "transcript" | "actions" | "decisions" | "export" | "details";

function ProcessingPanel({ m, editable }: { m: MeetingDetail; editable: boolean }) {
  const qc = useQueryClient();
  const job = m.latest_job;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["meeting", m.id] }); qc.invalidateQueries({ queryKey: ["meetings"] }); };
  const act = useMutation({ mutationFn: (path: string) => post<Job>(path), onSuccess: refresh });
  const active = isActive(m.status);
  const queuedRetry = job && job.status === "queued" && job.attempts > 0;
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => get<SystemStatus>("/api/v1/system/status"), staleTime: 300_000 });
  const aiReady = status.data?.ai.configured ?? false;
  const sttReady = status.data?.transcription.configured ?? false;

  if (!active && m.status !== "failed" && m.status !== "cancelled" && m.status !== "uploaded" && m.status !== "transcribed") return null;
  return (
    <Card className="mb-6 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          {active ? <Loader2 className="mt-0.5 size-5 shrink-0 animate-spin text-accent" /> : m.status === "failed" ? <AlertTriangle className="mt-0.5 size-5 shrink-0 text-red-600" /> : <Sparkles className="mt-0.5 size-5 shrink-0 text-slate-400" />}
          <div className="min-w-0 text-sm">
            {active && job && (
              <>
                <div className="font-medium">{job.kind === "transcription" ? "Transcribing the recording" : "Analysing the transcript"}</div>
                <div className="text-muted">
                  {job.stage}{job.progress_total && job.progress_total > 1 ? ` · ${job.progress_current ?? 0} of ${job.progress_total} parts done` : ""}
                  {job.provider ? ` · ${job.provider}${job.model ? ` / ${job.model}` : ""}` : ""}
                </div>
                {queuedRetry && <div className="mt-1 text-xs text-amber-700">Attempt {job.attempts} of {job.max_attempts} failed: {job.error_message}</div>}
              </>
            )}
            {m.status === "failed" && (
              <>
                <div className="font-medium text-red-700">{m.error_stage === "analysis" ? "AI analysis failed" : "Transcription failed"}</div>
                <div className="text-slate-600">{m.error_message}</div>
                {m.error_stage === "analysis" && <div className="mt-0.5 text-xs text-muted">The transcript is safe; only the summary and extraction step failed.</div>}
              </>
            )}
            {m.status === "cancelled" && <div className="font-medium">Processing was cancelled.</div>}
            {m.status === "uploaded" && <div><div className="font-medium">Recording uploaded</div><div className="text-muted">{sttReady ? "It has not been transcribed yet." : "No transcription provider is configured on this server, so it cannot be transcribed yet."}</div></div>}
            {m.status === "transcribed" && <div><div className="font-medium">Transcript ready</div><div className="text-muted">{aiReady ? "Run the AI analysis to get a summary, decisions and action items." : "No AI provider is configured on this server, so no summary, decisions or action items can be generated. You can still add them yourself."}</div></div>}
          </div>
        </div>
        {editable && (
          <div className="flex shrink-0 gap-2">
            {active && job && <Button variant="secondary" size="sm" loading={act.isPending} onClick={() => act.mutate(`/api/v1/jobs/${job.id}/cancel`)}>Cancel</Button>}
            {!active && sttReady && m.recording?.audio_available && (m.status !== "transcribed" || m.error_stage === "transcription") && m.error_stage !== "analysis" && (
              <Button size="sm" loading={act.isPending} onClick={() => act.mutate(`/api/v1/meetings/${m.id}/transcribe`)}><RefreshCw className="size-4" />{m.status === "uploaded" ? "Transcribe" : "Retry transcription"}</Button>
            )}
            {!active && aiReady && m.has_transcript && (m.status === "transcribed" || m.error_stage === "analysis" || m.status === "cancelled") && (
              <Button size="sm" loading={act.isPending} onClick={() => act.mutate(`/api/v1/meetings/${m.id}/analyze`)}><Wand2 className="size-4" />{m.error_stage === "analysis" ? "Retry analysis" : "Analyse with AI"}</Button>
            )}
          </div>
        )}
      </div>
      <ErrorBox error={act.error} className="mt-3" />
    </Card>
  );
}

export default function MeetingDetailPage() {
  const { id = "" } = useParams();
  const ws = useWorkspace();
  const editable = canEdit(ws);
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "summary";
  const setTab = (t: Tab) => { const n = new URLSearchParams(params); n.set("tab", t); setParams(n, { replace: true }); };
  const [focus, setFocus] = useState<string | null>(location.hash ? location.hash.slice(1) : null);
  const uploadState = location.state as { notice?: string | null; duplicates?: { meeting_id: string; title: string }[] } | null;

  const meeting = useQuery({
    queryKey: ["meeting", id], queryFn: () => get<MeetingDetail>(`/api/v1/meetings/${id}`),
    refetchInterval: (q) => (q.state.data && isActive(q.state.data.status) ? 3000 : false),
  });
  const m = meeting.data;
  const hasTranscript = Boolean(m?.has_transcript);
  const transcript = useQuery({ queryKey: ["transcript", id], queryFn: () => get<Transcript>(`/api/v1/meetings/${id}/transcript`), enabled: hasTranscript });
  const summary = useQuery({ queryKey: ["summary", id, m?.status], queryFn: () => get<Summary>(`/api/v1/meetings/${id}/summary`), enabled: Boolean(m?.has_summary) });
  const actions = useQuery({ queryKey: ["actions", ws.id, "meeting", id, m?.status],
    queryFn: () => get<Page<ActionItem>>(`/api/v1/action-items${qs({ workspace_id: ws.id, meeting_id: id, page_size: 200 })}`), enabled: Boolean(m) });
  const decisions = useQuery({ queryKey: ["decisions", ws.id, "meeting", id, m?.status],
    queryFn: () => get<Page<Decision>>(`/api/v1/decisions${qs({ workspace_id: ws.id, meeting_id: id, page_size: 200 })}`), enabled: Boolean(m) });

  useEffect(() => { // refresh everything when processing finishes
    if (m && !isActive(m.status)) {
      qc.invalidateQueries({ queryKey: ["transcript", id] });
    }
  }, [m?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (meeting.isLoading) return <Spinner />;
  if (meeting.error) return meeting.error instanceof ApiError && meeting.error.status === 404
    ? <EmptyState icon={<FileText className="size-5" />} title="Meeting not found">It may have been deleted, or it belongs to another workspace.</EmptyState>
    : <ErrorBox error={meeting.error} />;
  if (!m) return null;

  const jump = (segmentId: string) => { setFocus(segmentId); setTab("transcript"); };
  const inv = [["actions", ws.id], ["decisions", ws.id], ["dashboard", ws.id], ["meeting", id]];

  return (
    <>
      <Link to="/meetings" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" />Meetings</Link>
      <PageHeader title={m.title}
        description={<span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <StatusBadge status={m.status} />{m.is_demo && <DemoBadge />}
          <span>{formatDateTime(m.meeting_date)}</span><span>{formatDuration(m.duration_seconds)}</span>
          {m.project_name && <Link to={`/projects/${m.project_id}`} className="text-accent hover:underline">{m.project_name}</Link>}
          {m.participants.length > 0 && <span>{m.participants.map((p) => p.name).join(", ")}</span>}
        </span>}
        actions={<Link to={`/assistant?meeting=${m.id}`}><Button variant="secondary"><Bot className="size-4" />Ask about this meeting</Button></Link>} />

      {uploadState?.notice && <div className="mb-4"><Notice tone="amber">{uploadState.notice}</Notice></div>}
      {uploadState?.duplicates && uploadState.duplicates.length > 0 && (
        <div className="mb-4"><Notice tone="amber">The same audio file was already uploaded to {uploadState.duplicates.map((d, i) => <span key={d.meeting_id}>{i > 0 && ", "}<Link className="underline" to={`/meetings/${d.meeting_id}`}>{d.title}</Link></span>)}.</Notice></div>
      )}
      <ProcessingPanel m={m} editable={editable} />

      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { id: "summary", label: "Summary" }, { id: "transcript", label: "Transcript" },
        { id: "actions", label: "Action items", count: actions.data?.total }, { id: "decisions", label: "Decisions", count: decisions.data?.total },
        { id: "export", label: "Reports & export" }, { id: "details", label: "Details" },
      ]} />

      {tab === "summary" && (summary.data ? <SummaryView s={summary.data} onJump={jump} /> : (
        <Card><EmptyState icon={<Sparkles className="size-5" />} title="No AI summary yet">
          {hasTranscript ? "Run the AI analysis from the panel above. It needs an AI provider configured on the server." : "A summary is created after the recording is transcribed and analysed."}
        </EmptyState></Card>
      ))}

      {tab === "transcript" && (hasTranscript ? (transcript.isLoading ? <Spinner /> : transcript.error ? <ErrorBox error={transcript.error} /> : transcript.data && (
        <Card className="p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap gap-2 text-xs text-muted">
            <Badge>{transcript.data.provider}{transcript.data.model ? ` / ${transcript.data.model}` : ""}</Badge>
            {transcript.data.language && <Badge>Language: {transcript.data.language}</Badge>}
            <Badge>{transcript.data.has_timestamps ? "Timestamps" : "No timestamps"}</Badge>
            <Badge>{transcript.data.has_diarization ? `${transcript.data.speakers.length} speakers detected` : "No speaker detection"}</Badge>
            {transcript.data.edited_at && <Badge tone="blue">Edited {formatDateTime(transcript.data.edited_at)}</Badge>}
          </div>
          <TranscriptViewer meetingId={m.id} segments={transcript.data.segments} speakers={transcript.data.speakers}
            hasTimestamps={transcript.data.has_timestamps} hasDiarization={transcript.data.has_diarization}
            recordingId={m.recording?.audio_available ? m.recording.id : null} readOnly={!editable} focusSegmentId={focus}
            perPartSpeakers={transcript.data.speaker_ids_per_part} />
        </Card>
      )) : <Card><EmptyState icon={<FileText className="size-5" />} title="No transcript yet">{m.recording ? "The transcript appears here when transcription finishes." : "Upload a recording in the Details tab."}</EmptyState></Card>)}

      {tab === "actions" && <ActionsTab meetingId={m.id} items={actions.data?.items ?? []} loading={actions.isLoading} editable={editable} inv={inv} onJump={hasTranscript ? jump : undefined} />}
      {tab === "decisions" && <DecisionsTab meetingId={m.id} items={decisions.data?.items ?? []} loading={decisions.isLoading} editable={editable} inv={inv} onJump={hasTranscript ? jump : undefined} />}
      {tab === "export" && <ExportTab m={m} editable={editable} />}
      {tab === "details" && <DetailsTab m={m} editable={editable} onDeleted={() => navigate("/meetings")} />}
    </>
  );
}

function ActionsTab({ meetingId, items, loading, editable, inv, onJump }: { meetingId: string; items: ActionItem[]; loading: boolean; editable: boolean; inv: string[][]; onJump?: (id: string) => void }) {
  const [adding, setAdding] = useState(false);
  return (
    <Card>
      <CardHeader title="Action items" subtitle="Owners and deadlines are only filled in when the meeting stated them."
        action={editable && <Button size="sm" variant="secondary" onClick={() => setAdding(true)}><Plus className="size-4" />Add</Button>} />
      {loading ? <Spinner /> : items.length ? <ActionList items={items} invalidate={inv} readOnly={!editable} showMeeting={false} onJump={onJump} /> : <p className="px-5 py-10 text-center text-sm text-muted">No action items for this meeting.</p>}
      {adding && <ActionEditor meetingId={meetingId} onClose={() => setAdding(false)} invalidate={inv} />}
    </Card>
  );
}

function DecisionsTab({ meetingId, items, loading, editable, inv, onJump }: { meetingId: string; items: Decision[]; loading: boolean; editable: boolean; inv: string[][]; onJump?: (id: string) => void }) {
  const [adding, setAdding] = useState(false);
  return (
    <Card>
      <CardHeader title="Decisions" subtitle="Proposals are kept separate from decisions that were confirmed in the meeting."
        action={editable && <Button size="sm" variant="secondary" onClick={() => setAdding(true)}><Plus className="size-4" />Add</Button>} />
      {loading ? <Spinner /> : items.length ? <DecisionList items={items} invalidate={inv} readOnly={!editable} showMeeting={false} onJump={onJump} /> : <p className="px-5 py-10 text-center text-sm text-muted">No decisions for this meeting.</p>}
      {adding && <DecisionEditor meetingId={meetingId} onClose={() => setAdding(false)} invalidate={inv} />}
    </Card>
  );
}

function ExportTab({ m, editable }: { m: MeetingDetail; editable: boolean }) {
  const qc = useQueryClient();
  const [withTranscript, setWithTranscript] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const reports = useQuery({ queryKey: ["reports", m.workspace_id, m.id], queryFn: () => get<Report[]>(`/api/v1/reports${qs({ workspace_id: m.workspace_id, meeting_id: m.id })}`) });
  const gen = useMutation({ mutationFn: (format: "pdf" | "html") => post<Report>(`/api/v1/meetings/${m.id}/reports`, { format, include_transcript: withTranscript }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", m.workspace_id] }) });
  const dl = (path: string, name: string) => download(path, name).catch(setError);
  const exportRow = (label: string, kind: string, formats: string[], disabled = false) => (
    <li className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
      <span className="text-sm">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {formats.map((f) => <Button key={f} size="sm" variant="secondary" disabled={disabled} onClick={() => dl(`/api/v1/meetings/${m.id}/export/${kind}?format=${f}`, `${kind}.${f}`)}><Download className="size-3.5" />{f.toUpperCase()}</Button>)}
      </div>
    </li>
  );
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title="Meeting report" subtitle="Summary, decisions, action items, dates, questions and risks." />
        <div className="space-y-3 p-5">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={withTranscript} onChange={(e) => setWithTranscript(e.target.checked)} />Include the full transcript</label>
          {editable && <div className="flex gap-2">
            <Button loading={gen.isPending && gen.variables === "pdf"} onClick={() => gen.mutate("pdf")}><FileText className="size-4" />Generate PDF</Button>
            <Button variant="secondary" loading={gen.isPending && gen.variables === "html"} onClick={() => gen.mutate("html")}>Generate HTML</Button>
          </div>}
          <ErrorBox error={gen.error || error} />
        </div>
        {(reports.data?.length ?? 0) > 0 && (
          <ul className="divide-y divide-line border-t border-line">
            {reports.data!.map((r) => (
              <li key={r.id} className="flex items-center justify-between px-5 py-2.5 text-sm">
                <span>{r.format.toUpperCase()} · {formatDateTime(r.created_at)} · {formatBytes(r.size_bytes)}{r.include_transcript ? " · with transcript" : ""}</span>
                <Button size="sm" variant="ghost" onClick={() => dl(`/api/v1/reports/${r.id}/download`, `report.${r.format}`)}><Download className="size-3.5" />Download</Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardHeader title="Export data" />
        <ul className="divide-y divide-line">
          {exportRow("Full transcript", "transcript", ["txt", "srt", "vtt", "json"], !m.has_transcript)}
          {exportRow("Meeting summary", "summary", ["md", "json"])}
          {exportRow("Action items", "action-items", ["csv", "md"])}
          {exportRow("Deadlines (calendar file)", "action-items", ["ics"])}
          {exportRow("Decisions", "decisions", ["csv", "md"])}
        </ul>
        <p className="border-t border-line px-5 py-3 text-xs text-muted">The calendar file contains action items that have a deadline. Import it into your calendar app yourself; MeetPilot AI does not send invitations.</p>
      </Card>
    </div>
  );
}

function DetailsTab({ m, editable, onDeleted }: { m: MeetingDetail; editable: boolean; onDeleted: () => void }) {
  const qc = useQueryClient();
  const projects = useProjects();
  const [form, setForm] = useState<MeetingFormValue>({ title: m.title, date: toLocalInput(m.meeting_date), project_id: m.project_id ?? "",
    participants: m.participants.map((p) => p.name).join(", "), description: m.description });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["meeting", m.id] }); qc.invalidateQueries({ queryKey: ["meetings"] }); };
  const save = useMutation({ mutationFn: () => patch(`/api/v1/meetings/${m.id}`, { ...meetingPayload(form), ...(form.project_id ? { project_id: form.project_id } : { clear_project: true }) }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => del(`/api/v1/meetings/${m.id}`), onSuccess: () => { qc.invalidateQueries(); onDeleted(); } });
  const removeAudio = useMutation({ mutationFn: () => del(`/api/v1/recordings/${m.recording!.id}/audio`), onSuccess: refresh });
  const rec = m.recording;
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <Card>
        <CardHeader title="Meeting details" />
        <div className="p-5">
          <fieldset disabled={!editable} className="space-y-4">
            <MeetingForm value={form} onChange={setForm} projects={projects.data ?? []} />
          </fieldset>
          <ErrorBox error={save.error} className="mt-3" />
          {editable && <Button className="mt-4" loading={save.isPending} onClick={() => save.mutate()}>{save.isSuccess ? "Saved" : "Save changes"}</Button>}
        </div>
      </Card>
      <div className="space-y-6">
        <Card>
          <CardHeader title="Recording" />
          <div className="space-y-3 p-5 text-sm">
            {rec ? (
              <dl className="grid grid-cols-[110px_1fr] gap-y-1.5">
                <dt className="text-muted">File</dt><dd className="truncate">{rec.original_filename}</dd>
                <dt className="text-muted">Format</dt><dd>{rec.audio_format.toUpperCase()}{rec.sample_rate ? ` · ${rec.sample_rate / 1000} kHz` : ""}{rec.channels ? ` · ${rec.channels === 1 ? "mono" : `${rec.channels} ch`}` : ""}</dd>
                <dt className="text-muted">Size</dt><dd>{formatBytes(rec.size_bytes)}</dd>
                <dt className="text-muted">Duration</dt><dd>{formatDuration(rec.duration_seconds)}</dd>
                <dt className="text-muted">Uploaded</dt><dd>{formatDateTime(rec.created_at)}</dd>
                <dt className="text-muted">Audio</dt><dd>{rec.audio_available ? "Stored privately" : `Deleted ${formatDateTime(rec.audio_deleted_at)}${rec.audio_deleted_reason === "retention" ? " (retention policy)" : ""}`}</dd>
              </dl>
            ) : <p className="text-muted">No recording uploaded.</p>}
            {editable && !isActive(m.status) && (replacing || !rec ? (
              <RecordingUploader meetingId={m.id} replace={Boolean(rec)} onDone={() => { setReplacing(false); refresh(); }} />
            ) : (
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="secondary" onClick={() => setReplacing(true)}>Replace recording</Button>
                {rec?.audio_available && <Button size="sm" variant="ghost" loading={removeAudio.isPending} onClick={() => confirm("Delete the audio file? The transcript and analysis are kept.") && removeAudio.mutate()}>Delete audio only</Button>}
              </div>
            ))}
            <ErrorBox error={removeAudio.error} />
          </div>
        </Card>
        {editable && (
          <Card>
            <CardHeader title="Delete meeting" />
            <div className="p-5 text-sm">
              <p className="text-slate-600">Permanently deletes the recording, transcript, summary, decisions, action items, reports and assistant answers that cite this meeting.</p>
              <Button variant="danger" className="mt-3" onClick={() => setConfirmDelete(true)}><Trash2 className="size-4" />Delete meeting</Button>
            </div>
          </Card>
        )}
      </div>
      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Delete this meeting?"
        footer={<><Button variant="secondary" onClick={() => setConfirmDelete(false)}>Cancel</Button><Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Delete permanently</Button></>}>
        <p className="text-sm">“{m.title}” and everything derived from it will be deleted. This cannot be undone.</p>
        <ErrorBox error={remove.error} />
      </Modal>
    </div>
  );
}
