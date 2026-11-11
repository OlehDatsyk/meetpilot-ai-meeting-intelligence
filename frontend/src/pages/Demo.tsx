import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CalendarClock, CheckCircle2, Circle, CircleDot, ExternalLink, Sparkles, User } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Logo } from "../components/Logo";
import { SummaryView, type SummaryLike } from "../components/SummaryView";
import { TranscriptViewer, type ViewSegment, type ViewSpeaker } from "../components/TranscriptViewer";
import { Badge, Button, Card, CardHeader, ErrorBox, Spinner, Tabs } from "../components/ui";
import { get, url } from "../lib/api";
import { formatDate, formatDateTime, formatDuration } from "../lib/format";

interface DemoAction { id: string; title: string; description: string; owner: string | null; due_date: string | null; due_text: string | null;
  due_source: string | null; priority: string | null; priority_source: string | null; needs_confirmation: boolean; status: string; source_segment_ids: string[] }
interface DemoDecision { id: string; title: string; description: string; meeting_status: "confirmed" | "proposed" | "uncertain"; participants: string[]; source_segment_ids: string[] }
interface DemoMeeting { id: string; title: string; description: string; meeting_date: string; duration_seconds: number; project_name: string;
  participants: { name: string; role: string }[]; speakers: ViewSpeaker[]; segments: ViewSegment[]; summary: SummaryLike;
  decisions: DemoDecision[]; action_items: DemoAction[] }
interface DemoData { notice: string; meetings: DemoMeeting[] }

type Tab = "summary" | "transcript" | "actions" | "decisions";
const STATUS_ICON = { todo: Circle, in_progress: CircleDot, completed: CheckCircle2, cancelled: Circle } as Record<string, typeof Circle>;

export default function DemoPage() {
  const demo = useQuery({ queryKey: ["public-demo"], queryFn: () => get<DemoData>("/api/v1/demo"), staleTime: Infinity });
  const [idx, setIdx] = useState(0);
  const [tab, setTab] = useState<Tab>("summary");
  const [focus, setFocus] = useState<string | null>(null);
  const jump = (id: string) => { setFocus(id); setTab("transcript"); };
  const m = demo.data?.meetings[idx];
  const segText = (ids: string[]) => m?.segments.filter((s) => ids.includes(s.id)).slice(0, 2).map((s) => `${s.speaker_name}: ${s.text}`).join(" ");

  return (
    <div className="min-h-full">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Logo />
          <div className="flex gap-2"><Link to="/login"><Button variant="ghost">Sign in</Button></Link><Link to="/register"><Button>Create an account</Button></Link></div>
        </div>
      </header>
      <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900">
        <strong>Demo.</strong> {demo.data?.notice ?? "Fictional sample data."} Nothing here was produced from a real recording.
      </div>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {demo.isLoading ? <Spinner /> : demo.error ? <ErrorBox error={demo.error} /> : m && (
          <>
            <div className="mb-6 flex flex-wrap gap-2">
              {demo.data!.meetings.map((x, i) => (
                <button key={x.id} onClick={() => { setIdx(i); setTab("summary"); setFocus(null); }}
                  className={`rounded-full border px-3 py-1.5 text-sm ${i === idx ? "border-accent bg-accent-soft text-accent" : "border-line bg-white text-slate-700 hover:border-slate-300"}`}>{x.title}</button>
              ))}
            </div>
            <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">{m.title}</h1>
                <p className="mt-1 flex flex-wrap gap-x-3 text-sm text-muted">
                  <Badge tone="green">Completed</Badge><span>{formatDateTime(m.meeting_date)}</span><span>{formatDuration(m.duration_seconds)}</span>
                  <span>{m.project_name}</span><span>{m.participants.map((p) => p.name).join(", ")}</span>
                </p>
              </div>
              <a href={url("/api/v1/demo/report.html")} target="_blank" rel="noopener noreferrer"><Button variant="secondary"><ExternalLink className="size-4" />View sample report</Button></a>
            </div>
            <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: "summary", label: "Summary" }, { id: "transcript", label: "Transcript" },
              { id: "actions", label: "Action items", count: m.action_items.length }, { id: "decisions", label: "Decisions", count: m.decisions.length }]} />
            {tab === "summary" && <SummaryView s={m.summary} onJump={jump} />}
            {tab === "transcript" && (
              <Card className="p-4 sm:p-5">
                <p className="mb-4 text-xs text-muted">The demo has no audio. Speakers 1 to 3 were named by a user; Speaker 4 was left unnamed.</p>
                <TranscriptViewer meetingId={m.id} segments={m.segments} speakers={m.speakers} hasTimestamps hasDiarization recordingId={null} readOnly focusSegmentId={focus} />
              </Card>
            )}
            {tab === "actions" && (
              <Card>
                <CardHeader title="Action items" subtitle="Unassigned items had no clearly named owner in the conversation." />
                <ul className="divide-y divide-line">
                  {m.action_items.map((a) => {
                    const Icon = STATUS_ICON[a.status];
                    return (
                      <li key={a.id} className="flex gap-3 px-5 py-3.5">
                        <Icon className={`mt-0.5 size-5 shrink-0 ${a.status === "completed" ? "text-emerald-600" : a.status === "in_progress" ? "text-accent" : "text-slate-400"}`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`text-sm font-medium ${a.status === "completed" ? "text-muted line-through" : ""}`}>{a.title}</span>
                            {a.priority && <Badge tone={a.priority === "high" ? "red" : "amber"}>{a.priority_source === "ai_suggested" && <Sparkles className="size-3" />}{a.priority[0].toUpperCase() + a.priority.slice(1)}{a.priority_source === "ai_suggested" ? " (AI suggestion)" : " (stated)"}</Badge>}
                            {a.needs_confirmation && <Badge tone="amber"><AlertCircle className="size-3" />Needs confirmation</Badge>}
                          </div>
                          {a.description && <p className="mt-0.5 text-sm text-slate-600">{a.description}</p>}
                          <div className="mt-1.5 flex flex-wrap gap-x-4 text-xs text-slate-600">
                            <span className="inline-flex items-center gap-1"><User className="size-3.5 text-slate-400" />{a.owner || "Unassigned"}</span>
                            <span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5 text-slate-400" />{a.due_date ? <>{formatDate(a.due_date)}{a.due_source === "ai_interpreted" && <span className="text-amber-700"> (interpreted from “{a.due_text}”)</span>}</> : "No deadline specified"}</span>
                          </div>
                          <button onClick={() => jump(a.source_segment_ids[0])} className="mt-2 block w-full rounded-md border-l-2 border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left text-xs text-slate-600 hover:border-accent">“{segText(a.source_segment_ids)}”</button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Card>
            )}
            {tab === "decisions" && (
              <Card>
                <CardHeader title="Decisions" subtitle="The proposal about a progress indicator is shown, but not as a confirmed decision." />
                <ul className="divide-y divide-line">
                  {m.decisions.map((d) => (
                    <li key={d.id} className="px-5 py-4">
                      <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium">{d.title}</span>
                        <Badge tone={d.meeting_status === "confirmed" ? "green" : "amber"}>{d.meeting_status === "confirmed" ? "Confirmed in meeting" : "Proposed, not confirmed"}</Badge></div>
                      {d.description && <p className="mt-1 text-sm text-slate-600">{d.description}</p>}
                      <button onClick={() => jump(d.source_segment_ids[0])} className="mt-2 block w-full rounded-md border-l-2 border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left text-xs text-slate-600 hover:border-accent">“{segText(d.source_segment_ids)}”</button>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            <Card className="mt-8 flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate-700">Create a free account to upload your own recordings, or to open an editable copy of this demo in your own workspace.</p>
              <Link to="/register"><Button>Get started</Button></Link>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
