import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Info, MessageSquarePlus, Send, Trash2 } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { Badge, Button, Card, ErrorBox, Notice, PageHeader, Select, Spinner } from "../components/ui";
import { del, get, post, qs } from "../lib/api";
import { formatDate, formatTimestamp } from "../lib/format";
import { useWorkspace } from "../lib/session";
import type { AIMessage, Citation, Conversation, MeetingDetail, SystemStatus } from "../lib/types";
import { useProjects } from "./Meetings";

const SUGGESTIONS = ["What decisions were made?", "What actions were assigned to me?", "Which tasks are overdue?",
  "What deadlines were discussed?", "What problems or risks were raised?", "What remains unresolved?"];

function citationLink(c: Citation) {
  if (c.type === "segment" && c.segment_id) return `/meetings/${c.meeting_id}?tab=transcript#${c.segment_id}`;
  if (c.type === "action") return `/meetings/${c.meeting_id}?tab=actions`;
  if (c.type === "decision") return `/meetings/${c.meeting_id}?tab=decisions`;
  return `/meetings/${c.meeting_id}`;
}

function renderAnswer(text: string, cites: Citation[]): ReactNode {
  const by = new Map(cites.map((c) => [c.label, c]));
  return text.split("\n").map((line, li) => (
    <Fragment key={li}>
      {li > 0 && <br />}
      {line.split(/(\[[SMAD]\d+\])/g).map((part, i) => {
        const label = part.match(/^\[([SMAD]\d+)\]$/)?.[1];
        const c = label ? by.get(label) : undefined;
        return c ? <Link key={i} to={citationLink(c)} title={`${c.meeting_title}${c.excerpt ? `: ${c.excerpt}` : ""}`}
          className="mx-0.5 rounded bg-accent-soft px-1 text-[11px] font-semibold text-accent hover:bg-indigo-100">{label}</Link> : <span key={i}>{part}</span>;
      })}
    </Fragment>
  ));
}

function Sources({ cites }: { cites: Citation[] }) {
  if (!cites.length) return null;
  return (
    <div className="mt-3 space-y-1.5 border-t border-line pt-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Sources</div>
      {cites.map((c) => (
        <Link key={c.label} to={citationLink(c)} className="flex gap-2 rounded-md px-1.5 py-1 text-xs hover:bg-slate-50">
          <span className="font-semibold text-accent">{c.label}</span>
          <span className="min-w-0 text-slate-600">
            <span className="font-medium text-ink">{c.meeting_title}</span> · {formatDate(c.meeting_date)}
            {c.type === "segment" && c.start_seconds !== null && c.start_seconds !== undefined && ` · ${formatTimestamp(c.start_seconds)}`}
            {c.speaker && ` · ${c.speaker}`}
            {c.excerpt && <span className="block truncate text-muted">“{c.excerpt}”</span>}
          </span>
        </Link>
      ))}
    </div>
  );
}

export default function AssistantPage() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const meetingScope = params.get("meeting");
  const [active, setActive] = useState<string | null>(params.get("c"));
  const [input, setInput] = useState("");
  const [projectId, setProjectId] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const projects = useProjects();
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => get<SystemStatus>("/api/v1/system/status"), staleTime: 300_000 });
  const scopeMeeting = useQuery({ queryKey: ["meeting", meetingScope], queryFn: () => get<MeetingDetail>(`/api/v1/meetings/${meetingScope}`), enabled: Boolean(meetingScope) });
  const convs = useQuery({ queryKey: ["conversations", ws.id], queryFn: () => get<Conversation[]>(`/api/v1/assistant/conversations${qs({ workspace_id: ws.id })}`) });
  const conv = useQuery({ queryKey: ["conversation", active], enabled: Boolean(active),
    queryFn: () => get<Conversation & { messages: AIMessage[] }>(`/api/v1/assistant/conversations/${active}`) });

  const ask = useMutation({
    mutationFn: async (content: string) => {
      let id = active;
      if (!id || (meetingScope && conv.data?.meeting_id !== meetingScope)) {
        const c = await post<Conversation>("/api/v1/assistant/conversations", { workspace_id: ws.id, meeting_id: meetingScope || null });
        id = c.id;
        setActive(id);
      }
      await post<AIMessage[]>(`/api/v1/assistant/conversations/${id}/messages`, { content, project_id: projectId || null });
      return id;
    },
    onSuccess: (id) => { setInput(""); qc.invalidateQueries({ queryKey: ["conversation", id] }); qc.invalidateQueries({ queryKey: ["conversations", ws.id] }); },
  });
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/v1/assistant/conversations/${id}`),
    onSuccess: () => { setActive(null); qc.invalidateQueries({ queryKey: ["conversations", ws.id] }); } });

  useEffect(() => { // keep the newest message visible without scrolling the whole page
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [conv.data?.messages.length, ask.isPending]);
  const submit = (e?: FormEvent) => { e?.preventDefault(); if (input.trim() && !ask.isPending) ask.mutate(input.trim()); };
  const newChat = () => { setActive(null); const n = new URLSearchParams(params); n.delete("c"); setParams(n, { replace: true }); };
  const messages = active ? conv.data?.messages ?? [] : [];

  return (
    <>
      <PageHeader title="AI Assistant" description="Ask about your meetings. Answers come only from your records and link to their sources." />
      {status.data && !status.data.ai.configured && (
        <div className="mb-4"><Notice tone="amber" icon={<Info className="mt-0.5 size-4 shrink-0" />}>No AI provider is configured on this server. The assistant will show the most relevant passages from your meetings instead of writing an answer.</Notice></div>
      )}
      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <Card className="h-fit">
          <div className="border-b border-line p-3"><Button variant="secondary" className="w-full" onClick={newChat}><MessageSquarePlus className="size-4" />New conversation</Button></div>
          {convs.isLoading ? <Spinner /> : (
            <ul className="max-h-[60vh] overflow-y-auto p-1.5">
              {(convs.data ?? []).map((c) => (
                <li key={c.id} className="group flex items-center">
                  <button onClick={() => setActive(c.id)} className={`min-w-0 flex-1 truncate rounded-md px-2.5 py-2 text-left text-sm ${active === c.id ? "bg-accent-soft font-medium text-accent" : "hover:bg-slate-50"}`}>{c.title}</button>
                  <button onClick={() => confirm("Delete this conversation?") && remove.mutate(c.id)} aria-label="Delete conversation" className="rounded p-1.5 text-slate-300 opacity-0 hover:text-red-600 group-hover:opacity-100"><Trash2 className="size-3.5" /></button>
                </li>
              ))}
              {!convs.data?.length && <li className="px-3 py-6 text-center text-xs text-muted">No conversations yet.</li>}
            </ul>
          )}
        </Card>
        <Card className="flex min-h-[520px] flex-col">
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5 text-xs text-muted">
            <span>Searching:</span>
            {meetingScope ? (
              <Badge tone="indigo">Meeting: {scopeMeeting.data?.title ?? "…"}<button className="ml-1" aria-label="Search all meetings" onClick={() => { const n = new URLSearchParams(params); n.delete("meeting"); setParams(n); newChat(); }}>×</button></Badge>
            ) : <Select label="Project scope" value={projectId} onChange={setProjectId} className="!py-1 text-xs"
              options={[{ value: "", label: "All meetings in this workspace" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: `Project: ${p.name}` }))]} />}
          </div>
          <div ref={scroller} className="max-h-[65vh] flex-1 space-y-4 overflow-y-auto p-4">
            {messages.length === 0 && !ask.isPending && (
              <div className="flex flex-col items-center py-10 text-center">
                <div className="flex size-11 items-center justify-center rounded-full bg-accent-soft text-accent"><Bot className="size-5" /></div>
                <p className="mt-3 text-sm font-medium">What would you like to know?</p>
                <div className="mt-4 flex max-w-xl flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => <button key={s} onClick={() => ask.mutate(s)} className="rounded-full border border-line px-3 py-1.5 text-xs text-slate-700 hover:border-accent hover:text-accent">{s}</button>)}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
                {m.role === "user" ? <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-3.5 py-2 text-sm text-white">{m.content}</div> : (
                  <div className="max-w-[95%] rounded-2xl rounded-bl-sm border border-line bg-white px-4 py-3 text-sm leading-relaxed text-slate-800">
                    {m.mode === "retrieval_only" && <Badge tone="amber">Matching passages only (no AI provider)</Badge>}
                    {m.mode === "no_results" && <Badge>No matching records</Badge>}
                    <div className={m.mode !== "ai" ? "mt-2" : ""}>{renderAnswer(m.content, m.citations)}</div>
                    {m.mode === "ai" && m.citations.length === 0 && <p className="mt-2 text-xs text-amber-700">This answer cites no sources. Treat it with care.</p>}
                    <Sources cites={m.citations} />
                    {m.provider && <div className="mt-2 text-[11px] text-muted">{m.provider}{m.model ? ` / ${m.model}` : ""}</div>}
                  </div>
                )}
              </div>
            ))}
            {ask.isPending && <div className="text-sm text-muted">Searching your meetings…</div>}
            <ErrorBox error={ask.error} />
          </div>
          <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
            <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000} placeholder="Ask about decisions, tasks, deadlines or a topic…" aria-label="Your question" className="input" />
            <Button type="submit" loading={ask.isPending} disabled={!input.trim()} aria-label="Send"><Send className="size-4" /></Button>
          </form>
        </Card>
      </div>
    </>
  );
}
