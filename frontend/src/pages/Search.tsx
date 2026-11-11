import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { Badge, Card, CardHeader, EmptyState, ErrorBox, Highlight, PageHeader, Spinner } from "../components/ui";
import { get, qs } from "../lib/api";
import { formatDate, formatTimestamp, STATUS_LABEL } from "../lib/format";
import { useWorkspace } from "../lib/session";
import type { MeetingStatus } from "../lib/types";

interface Results {
  terms: string[];
  meetings: { id: string; title: string; description: string; meeting_date: string; status: MeetingStatus }[];
  segments: { id: string; meeting_id: string; meeting_title: string; meeting_date: string; start_seconds: number | null; speaker: string | null; text: string }[];
  action_items: { id: string; meeting_id: string; meeting_title: string; title: string; owner: string | null; status: string }[];
  decisions: { id: string; meeting_id: string; meeting_title: string; title: string; meeting_status: string }[];
  projects: { id: string; name: string; description: string }[];
}

function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  if (!count) return null;
  return <Card><CardHeader title={`${title} (${count})`} /><ul className="divide-y divide-line">{children}</ul></Card>;
}

export default function SearchPage() {
  const ws = useWorkspace();
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const r = useQuery({ queryKey: ["search", ws.id, q], enabled: q.length >= 2, queryFn: () => get<Results>(`/api/v1/search${qs({ workspace_id: ws.id, q, limit: 15 })}`) });
  const d = r.data;
  const terms = d?.terms.length ? d.terms : [q];
  const total = d ? d.meetings.length + d.segments.length + d.action_items.length + d.decisions.length + d.projects.length : 0;
  return (
    <>
      <PageHeader title={`Search results for “${q}”`} description="Keyword search across meetings, transcripts, speakers, action items, decisions and projects in this workspace." />
      {r.isLoading ? <Spinner /> : r.error ? <ErrorBox error={r.error} /> : !total ? (
        <Card><EmptyState icon={<Search className="size-5" />} title="No results">Try fewer or different words.</EmptyState></Card>
      ) : (
        <div className="space-y-6">
          <Group title="Transcript passages" count={d!.segments.length}>
            {d!.segments.map((s) => (
              <li key={s.id}><Link to={`/meetings/${s.meeting_id}?tab=transcript#${s.id}`} className="block px-5 py-3 hover:bg-slate-50">
                <div className="text-xs text-muted">{s.meeting_title} · {formatDate(s.meeting_date)}{s.start_seconds !== null ? ` · ${formatTimestamp(s.start_seconds)}` : ""}{s.speaker ? ` · ${s.speaker}` : ""}</div>
                <p className="mt-0.5 text-sm"><Highlight text={s.text} query={terms} /></p>
              </Link></li>
            ))}
          </Group>
          <Group title="Meetings" count={d!.meetings.length}>
            {d!.meetings.map((m) => (
              <li key={m.id}><Link to={`/meetings/${m.id}`} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50">
                <span className="text-sm font-medium"><Highlight text={m.title} query={q} /></span><span className="text-xs text-muted">{formatDate(m.meeting_date)} · {STATUS_LABEL[m.status]}</span>
              </Link></li>
            ))}
          </Group>
          <Group title="Action items" count={d!.action_items.length}>
            {d!.action_items.map((a) => (
              <li key={a.id}><Link to={`/meetings/${a.meeting_id}?tab=actions`} className="block px-5 py-3 hover:bg-slate-50">
                <span className="text-sm font-medium"><Highlight text={a.title} query={q} /></span>
                <div className="text-xs text-muted">{a.owner || "Unassigned"} · {a.meeting_title}</div>
              </Link></li>
            ))}
          </Group>
          <Group title="Decisions" count={d!.decisions.length}>
            {d!.decisions.map((x) => (
              <li key={x.id}><Link to={`/meetings/${x.meeting_id}?tab=decisions`} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50">
                <span className="text-sm font-medium"><Highlight text={x.title} query={q} /></span><Badge>{x.meeting_status}</Badge>
              </Link></li>
            ))}
          </Group>
          <Group title="Projects" count={d!.projects.length}>
            {d!.projects.map((p) => <li key={p.id}><Link to={`/projects/${p.id}`} className="block px-5 py-3 text-sm font-medium hover:bg-slate-50">{p.name}</Link></li>)}
          </Group>
        </div>
      )}
    </>
  );
}
