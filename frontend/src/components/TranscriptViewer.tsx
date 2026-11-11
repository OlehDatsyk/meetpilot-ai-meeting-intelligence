import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Pencil, RotateCcw, Search, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { get, patch } from "../lib/api";
import { formatTimestamp, formatDateTime } from "../lib/format";
import { Badge, Button, ErrorBox, Highlight } from "./ui";

export interface ViewSegment {
  id: string;
  position: number;
  start_seconds: number | null;
  end_seconds: number | null;
  speaker_id?: string | null;
  speaker_name: string | null;
  text: string;
  original_text?: string;
  edited?: boolean;
  edited_at?: string | null;
}

export interface ViewSpeaker { id: string; label: string; ordinal: number; display_name: string | null; name: string; segment_count?: number }

const SPEAKER_COLORS = ["text-indigo-700", "text-emerald-700", "text-amber-700", "text-rose-700", "text-sky-700", "text-violet-700", "text-teal-700", "text-orange-700"];

/** Plays a private recording. The URL is short-lived, so it is refreshed when it expires. */
function useMediaUrl(recordingId: string | null) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!recordingId) return;
    try {
      const r = await get<{ url: string; absolute: boolean }>(`/api/v1/recordings/${recordingId}/media-url`);
      const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
      setSrc(r.absolute ? r.url : `${base}${r.url}`);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Audio unavailable.");
    }
  }, [recordingId]);
  useEffect(() => { load(); }, [load]);
  return { src, error, reload: load };
}

export function TranscriptViewer({ meetingId, segments, speakers, hasTimestamps, hasDiarization, recordingId, readOnly,
  focusSegmentId, perPartSpeakers }: {
  meetingId: string; segments: ViewSegment[]; speakers: ViewSpeaker[]; hasTimestamps: boolean; hasDiarization: boolean;
  recordingId: string | null; readOnly?: boolean; focusSegmentId?: string | null; perPartSpeakers?: boolean;
}) {
  const qc = useQueryClient();
  const audio = useRef<HTMLAudioElement>(null);
  const media = useMediaUrl(hasTimestamps ? recordingId : null);
  const [time, setTime] = useState(0);
  const [query, setQuery] = useState("");
  const [matchIdx, setMatchIdx] = useState(0);
  const [speakerFilter, setSpeakerFilter] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ text: "", speaker_id: "" });
  const [showSpeakers, setShowSpeakers] = useState(false);
  const refs = useRef<Record<string, HTMLLIElement | null>>({});
  const invalidate = () => qc.invalidateQueries({ queryKey: ["transcript", meetingId] });

  const saveSeg = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => patch(`/api/v1/segments/${id}`, body),
    onSuccess: () => { setEditing(null); invalidate(); },
  });
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => patch(`/api/v1/speakers/${id}`, { display_name: name }),
    onSuccess: invalidate,
  });

  const visible = useMemo(() => segments.filter((s) => !speakerFilter || s.speaker_id === speakerFilter), [segments, speakerFilter]);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? visible.filter((s) => s.text.toLowerCase().includes(q) || (s.speaker_name || "").toLowerCase().includes(q)) : [];
  }, [visible, query]);
  useEffect(() => setMatchIdx(0), [query, speakerFilter]);

  const scrollTo = (id: string) => refs.current[id]?.scrollIntoView({ behavior: "smooth", block: "center" });
  useEffect(() => { if (matches[matchIdx]) scrollTo(matches[matchIdx].id); }, [matchIdx, matches]);
  useEffect(() => { if (focusSegmentId) setTimeout(() => scrollTo(focusSegmentId), 50); }, [focusSegmentId]);

  const active = hasTimestamps ? segments.findLast((s) => s.start_seconds !== null && s.start_seconds <= time + 0.05)?.id : undefined;
  const seek = (s: ViewSegment) => {
    if (!audio.current || s.start_seconds === null || !media.src) return;
    audio.current.currentTime = s.start_seconds;
    audio.current.play().catch(() => undefined);
  };
  const colorFor = (id?: string | null) => {
    const sp = speakers.find((x) => x.id === id);
    return sp ? SPEAKER_COLORS[(sp.ordinal - 1) % SPEAKER_COLORS.length] : "text-slate-700";
  };

  return (
    <div className="space-y-4">
      {hasTimestamps && recordingId && (
        <div className="sticky top-14 z-10 rounded-xl border border-line bg-white p-3 shadow-sm">
          {media.error ? <p className="text-sm text-muted">{media.error}</p> : (
            <audio ref={audio} src={media.src ?? undefined} preload="metadata" className="w-full" controls
              aria-label="Meeting recording" onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} onError={() => media.reload()} />
          )}
        </div>
      )}
      {hasTimestamps && !recordingId && <p className="text-xs text-muted">Playback is unavailable because the audio for this meeting has been deleted.</p>}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search this transcript" aria-label="Search this transcript" className="input !pl-9 !pr-28"
            onKeyDown={(e) => { if (e.key === "Enter" && matches.length) setMatchIdx((i) => (i + (e.shiftKey ? matches.length - 1 : 1)) % matches.length); }} />
          {query && (
            <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1 text-xs text-muted">
              <span>{matches.length ? `${matchIdx + 1}/${matches.length}` : "0 found"}</span>
              <button aria-label="Previous match" className="rounded p-0.5 hover:bg-slate-100" onClick={() => setMatchIdx((i) => (i + matches.length - 1) % Math.max(1, matches.length))}><ChevronUp className="size-4" /></button>
              <button aria-label="Next match" className="rounded p-0.5 hover:bg-slate-100" onClick={() => setMatchIdx((i) => (i + 1) % Math.max(1, matches.length))}><ChevronDown className="size-4" /></button>
            </div>
          )}
        </div>
        {speakers.length > 0 && (
          <div className="flex gap-2">
            <select aria-label="Filter by speaker" className="input !w-auto" value={speakerFilter} onChange={(e) => setSpeakerFilter(e.target.value)}>
              <option value="">All speakers</option>
              {speakers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <Button variant="secondary" onClick={() => setShowSpeakers((v) => !v)}><Users className="size-4" />Speakers</Button>
          </div>
        )}
      </div>

      {!hasDiarization && <p className="text-xs text-muted">The transcription provider did not identify speakers for this recording, so lines are not attributed to anyone.</p>}
      {perPartSpeakers && <p className="text-xs text-amber-800">This long recording was transcribed in parts. Speaker labels are only consistent within each part; give the same name to speakers who are the same person.</p>}

      {showSpeakers && (
        <div className="rounded-xl border border-line bg-slate-50 p-4">
          <h3 className="text-sm font-semibold">Speakers</h3>
          <p className="mt-0.5 text-xs text-muted">Names come only from you. MeetPilot AI never identifies people from their voice. The provider's original label is kept.</p>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {speakers.map((s) => (
              <li key={s.id} className="flex items-center gap-2">
                <span className={`w-24 shrink-0 text-xs font-medium ${colorFor(s.id)}`}>Speaker {s.ordinal}<span className="block font-normal text-muted">id “{s.label}”{s.segment_count !== undefined ? ` · ${s.segment_count} lines` : ""}</span></span>
                <input className="input" placeholder={`Speaker ${s.ordinal}`} defaultValue={s.display_name ?? ""} disabled={readOnly} aria-label={`Name for speaker ${s.ordinal}`}
                  onBlur={(e) => e.target.value !== (s.display_name ?? "") && rename.mutate({ id: s.id, name: e.target.value })} />
              </li>
            ))}
          </ul>
          <ErrorBox error={rename.error} className="mt-2" />
        </div>
      )}

      <ErrorBox error={saveSeg.error} />
      <ol className="space-y-1">
        {visible.map((s) => {
          const isMatch = matches[matchIdx]?.id === s.id;
          return (
            <li key={s.id} ref={(el) => { refs.current[s.id] = el; }}
              className={`group flex gap-3 rounded-lg px-3 py-2 ${active === s.id ? "bg-accent-soft" : focusSegmentId === s.id || isMatch ? "bg-amber-50" : "hover:bg-slate-50"}`}>
              <button onClick={() => seek(s)} disabled={s.start_seconds === null || !media.src}
                className="w-14 shrink-0 pt-0.5 text-left font-mono text-xs tabular-nums text-muted enabled:hover:text-accent"
                aria-label={s.start_seconds !== null ? `Play from ${formatTimestamp(s.start_seconds)}` : "No timestamp"}>
                {s.start_seconds !== null ? formatTimestamp(s.start_seconds) : `#${s.position}`}
              </button>
              <div className="min-w-0 flex-1">
                {s.speaker_name && <div className={`text-xs font-semibold ${colorFor(s.speaker_id)}`}>{s.speaker_name}</div>}
                {editing === s.id ? (
                  <div className="mt-1 space-y-2">
                    <textarea className="input" rows={3} value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} autoFocus />
                    {speakers.length > 0 && (
                      <select className="input !w-auto" aria-label="Speaker" value={draft.speaker_id} onChange={(e) => setDraft({ ...draft, speaker_id: e.target.value })}>
                        {speakers.map((sp) => <option key={sp.id} value={sp.id}>{sp.name}</option>)}
                      </select>
                    )}
                    <div className="flex gap-2">
                      <Button size="sm" loading={saveSeg.isPending} disabled={!draft.text.trim()} onClick={() => saveSeg.mutate({ id: s.id, body: {
                        text: draft.text, ...(speakers.length && draft.speaker_id !== s.speaker_id ? { speaker_id: draft.speaker_id } : {}) } })}>Save</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm leading-relaxed text-slate-800"><Highlight text={s.text} query={query} /></p>
                )}
                {s.edited && editing !== s.id && (
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <Badge tone="blue">Edited {s.edited_at ? formatDateTime(s.edited_at) : ""}</Badge>
                    <details className="inline"><summary className="cursor-pointer hover:text-ink">Original</summary><span className="italic">{s.original_text}</span></details>
                    {!readOnly && <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => saveSeg.mutate({ id: s.id, body: { revert: true } })}><RotateCcw className="size-3" />Revert</button>}
                  </div>
                )}
              </div>
              {!readOnly && editing !== s.id && (
                <button onClick={() => { setEditing(s.id); setDraft({ text: s.text, speaker_id: s.speaker_id ?? "" }); }}
                  className="h-fit rounded p-1 text-slate-400 opacity-0 hover:bg-slate-100 hover:text-ink focus:opacity-100 group-hover:opacity-100" aria-label="Edit line">
                  <Pencil className="size-3.5" />
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
