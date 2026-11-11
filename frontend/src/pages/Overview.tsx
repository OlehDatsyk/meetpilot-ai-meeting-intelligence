import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarClock, CheckCircle2, Clock, FileAudio, Gavel, ListTodo, Sparkles, Upload, Users } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DueText, MeetingList } from "../components/records";
import { Button, Card, CardHeader, EmptyState, ErrorBox, PageHeader, Spinner, StatCard } from "../components/ui";
import { get, post, qs } from "../lib/api";
import { formatDate, formatHours, relativeTime } from "../lib/format";
import { canEdit, useSession, useWorkspace } from "../lib/session";
import type { ActionItem, Activity, Meeting } from "../lib/types";

interface Dashboard {
  stats: { total_meetings: number; total_duration_seconds: number; meetings_processed: number; meetings_in_progress: number;
    actions_outstanding: number; actions_completed: number; actions_overdue: number; decisions_recorded: number };
  recent_meetings: Meeting[];
  upcoming_deadlines: ActionItem[];
  recent_activity: Activity[];
  meetings_per_week: { week_start: string; meetings: number; minutes: number }[];
}

export function useDemoWorkspace() {
  const { refreshWorkspaces, selectWorkspace } = useSession();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: () => post<{ message: string }>("/api/v1/demo/workspace"),
    onSuccess: async (r) => { await refreshWorkspaces(); selectWorkspace(r.message); navigate("/"); },
  });
}

export default function OverviewPage() {
  const ws = useWorkspace();
  const { user } = useSession();
  const demo = useDemoWorkspace();
  const q = useQuery({ queryKey: ["dashboard", ws.id], queryFn: () => get<Dashboard>(`/api/v1/dashboard${qs({ workspace_id: ws.id })}`),
    refetchInterval: (query) => (query.state.data?.stats.meetings_in_progress ? 5000 : false) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data!;
  const s = d.stats;
  const chart = d.meetings_per_week.map((w) => ({ ...w, label: formatDate(w.week_start).replace(/,? \d{4}$/, "") }));

  return (
    <>
      <PageHeader title={`Good to see you, ${user?.name.split(" ")[0]}`} description={`Overview of ${ws.name}.`}
        actions={canEdit(ws) && <Link to="/upload"><Button><Upload className="size-4" />Upload recording</Button></Link>} />

      {s.total_meetings === 0 ? (
        <Card>
          <EmptyState icon={<FileAudio className="size-5" />} title="No meetings yet"
            action={<div className="flex flex-wrap justify-center gap-2">
              {canEdit(ws) && <Link to="/upload"><Button><Upload className="size-4" />Upload your first recording</Button></Link>}
              {!ws.is_demo && <Button variant="secondary" loading={demo.isPending} onClick={() => demo.mutate()}><Sparkles className="size-4" />Open the demo workspace</Button>}
            </div>}>
            Upload a meeting recording to get a transcript, summary, decisions and action items. Or open a demo workspace with fictional sample meetings to look around first.
          </EmptyState>
          <ErrorBox error={demo.error} className="mx-5 mb-5" />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Meetings" value={s.total_meetings} icon={<Users className="size-4" />}
              hint={`${s.meetings_processed} fully processed${s.meetings_in_progress ? ` · ${s.meetings_in_progress} in progress` : ""}`} />
            <StatCard label="Recorded time" value={formatHours(s.total_duration_seconds)} icon={<Clock className="size-4" />} hint="Sum of meeting durations" />
            <StatCard label="Open action items" value={s.actions_outstanding} icon={<ListTodo className="size-4" />}
              hint={<>{s.actions_completed} completed{s.actions_overdue ? <span className="text-red-600"> · {s.actions_overdue} overdue</span> : ""}</>} />
            <StatCard label="Decisions recorded" value={s.decisions_recorded} icon={<Gavel className="size-4" />} hint="Excluding rejected" />
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title="Recent meetings" action={<Link to="/meetings" className="text-xs font-medium text-accent hover:underline">View all</Link>} />
              <MeetingList meetings={d.recent_meetings} />
            </Card>
            <Card>
              <CardHeader title="Upcoming deadlines" subtitle="Open action items with a deadline" />
              {d.upcoming_deadlines.length === 0 ? (
                <p className="px-5 py-8 text-center text-sm text-muted">No open action items have a deadline.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {d.upcoming_deadlines.map((a) => (
                    <li key={a.id} className="px-5 py-3">
                      <Link to={`/meetings/${a.meeting_id}?tab=actions`} className="text-sm font-medium text-ink hover:text-accent">{a.title}</Link>
                      <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-slate-600">
                        <span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5" /><DueText a={a} /></span>
                        <span>{a.owner || "Unassigned"}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title="Meeting activity" subtitle="Meetings per week, by meeting date (last 8 weeks)" />
              <div className="h-64 px-2 py-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ top: 4, right: 12, left: -16, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="#eef0f3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={false} />
                    <Tooltip cursor={{ fill: "#f1f5f9" }} formatter={(v) => [v, "Meetings"]} labelFormatter={(l) => `Week of ${l}`} />
                    <Bar dataKey="meetings" fill="#4f46e5" radius={[4, 4, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <CardHeader title="Recent activity" />
              {d.recent_activity.length === 0 ? <p className="px-5 py-8 text-center text-sm text-muted">No activity yet.</p> : (
                <ul className="divide-y divide-line">
                  {d.recent_activity.map((a) => (
                    <li key={a.id} className="flex gap-2.5 px-5 py-2.5 text-sm">
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-slate-300" />
                      <div className="min-w-0">
                        {a.meeting_id ? <Link to={`/meetings/${a.meeting_id}`} className="text-ink hover:text-accent">{a.summary}</Link> : <span>{a.summary}</span>}
                        <div className="text-xs text-muted">{a.user_name ? `${a.user_name} · ` : ""}{relativeTime(a.created_at)}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
