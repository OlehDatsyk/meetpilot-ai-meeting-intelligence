import { useQuery } from "@tanstack/react-query";
import { MessageSquareText, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { Card, CardHeader, EmptyState, ErrorBox, Highlight, PageHeader, Spinner } from "../components/ui";
import { get, qs } from "../lib/api";
import { formatDate, formatDuration, formatTimestamp } from "../lib/format";
import { useWorkspace } from "../lib/session";
import type { Meeting, Page } from "../lib/types";

interface SegmentHit { id: string; meeting_id: string; meeting_title: string; meeting_date: string; start_seconds: number | null; speaker: string | null; text: string }

export default function TranscriptsPage() {
  const ws = useWorkspace();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const meetings = useQuery({ queryKey: ["meetings", ws.id, "with-transcripts"],
    queryFn: () => get<Page<Meeting>>(`/api/v1/meetings${qs({ workspace_id: ws.id, status: "transcribed,analysing,completed", page_size: 100 })}`) });
  const search = useQuery({ queryKey: ["transcript-search", ws.id, q], enabled: q.length >= 2,
    queryFn: () => get<{ segments: SegmentHit[]; terms: string[] }>(`/api/v1/search${qs({ workspace_id: ws.id, q, limit: 25 })}`) });
  const submit = (e: FormEvent) => { e.preventDefault(); setQ(input.trim()); };
  const withTranscript = (meetings.data?.items ?? []).filter((m) => m.has_transcript);

  return (
    <>
      <PageHeader title="Transcripts" description="Search what was said across every meeting in this workspace." />
      <form onSubmit={submit} className="relative mb-6" role="search">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Search spoken words or speaker names, then press Enter" aria-label="Search transcripts" className="input !py-2.5 !pl-9" />
      </form>
      {q && (
        <Card className="mb-6">
          <CardHeader title={`Matches for “${q}”`} subtitle="Keyword search, ranked by how often the words appear." />
          {search.isLoading ? <Spinner /> : search.error ? <div className="p-5"><ErrorBox error={search.error} /></div> : !search.data?.segments.length ? (
            <p className="px-5 py-8 text-center text-sm text-muted">Nothing in your transcripts matches.</p>
          ) : (
            <ul className="divide-y divide-line">
              {search.data.segments.map((s) => (
                <li key={s.id}>
                  <Link to={`/meetings/${s.meeting_id}?tab=transcript`} className="block px-5 py-3 hover:bg-slate-50">
                    <div className="text-xs text-muted">{s.meeting_title} · {formatDate(s.meeting_date)}{s.start_seconds !== null ? ` · ${formatTimestamp(s.start_seconds)}` : ""}{s.speaker ? ` · ${s.speaker}` : ""}</div>
                    <p className="mt-0.5 text-sm text-slate-800"><Highlight text={s.text} query={search.data.terms.length ? search.data.terms : q} /></p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      <Card>
        <CardHeader title="Meetings with a transcript" />
        {meetings.isLoading ? <Spinner /> : meetings.error ? <div className="p-5"><ErrorBox error={meetings.error} /></div> : withTranscript.length === 0 ? (
          <EmptyState icon={<MessageSquareText className="size-5" />} title="No transcripts yet">Transcripts appear here after a recording has been transcribed.</EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {withTranscript.map((m) => (
              <li key={m.id}>
                <Link to={`/meetings/${m.id}?tab=transcript`} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50">
                  <span className="truncate text-sm font-medium">{m.title}</span>
                  <span className="shrink-0 text-xs text-muted">{formatDate(m.meeting_date)} · {formatDuration(m.duration_seconds)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
