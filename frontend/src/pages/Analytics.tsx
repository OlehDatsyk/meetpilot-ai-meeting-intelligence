import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardHeader, DemoBadge, EmptyState, ErrorBox, PageHeader, Select, Spinner, StatCard } from "../components/ui";
import { get, qs } from "../lib/api";
import { formatDate, formatDuration, formatHours } from "../lib/format";
import { useWorkspace } from "../lib/session";

interface Analytics {
  workspace: { is_demo: boolean };
  totals: { meetings: number; total_duration_seconds: number; average_duration_seconds: number | null; meetings_with_duration: number;
    actions_created: number; actions_completed: number; actions_outstanding: number; actions_cancelled: number };
  processing: { finished_jobs: number; succeeded: number; failed: number; success_rate: number | null };
  decisions_by_project: { project: string; decisions: number }[];
  weekly: { week_start: string; meetings: number; minutes: number; actions_created: number; actions_completed: number }[];
}

const axis = { tick: { fontSize: 11, fill: "#64748b" }, tickLine: false, axisLine: false } as const;

export default function AnalyticsPage() {
  const ws = useWorkspace();
  const [weeks, setWeeks] = useState("12");
  const q = useQuery({ queryKey: ["analytics", ws.id, weeks], queryFn: () => get<Analytics>(`/api/v1/analytics${qs({ workspace_id: ws.id, weeks })}`) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const a = q.data!;
  const weekly = a.weekly.map((w) => ({ ...w, label: formatDate(w.week_start).replace(/,? \d{4}$/, "") }));
  const t = a.totals;
  return (
    <>
      <PageHeader title="Analytics" description={<>All figures are calculated from the records stored in this workspace.{a.workspace.is_demo && <> <DemoBadge /> These are fictional demo records.</>}</>}
        actions={<Select label="Period" value={weeks} onChange={setWeeks} options={[{ value: "8", label: "Last 8 weeks" }, { value: "12", label: "Last 12 weeks" }, { value: "26", label: "Last 26 weeks" }, { value: "52", label: "Last 52 weeks" }]} />} />
      {t.meetings === 0 ? <Card><EmptyState icon={<BarChart3 className="size-5" />} title="Nothing to measure yet">Analytics appear once this workspace has meetings.</EmptyState></Card> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Meetings" value={t.meetings} hint={`${formatHours(t.total_duration_seconds)} in total`} />
            <StatCard label="Average duration" value={t.average_duration_seconds ? formatDuration(t.average_duration_seconds) : "—"} hint={`Across ${t.meetings_with_duration} meetings with a known duration`} />
            <StatCard label="Action items" value={t.actions_created} hint={`${t.actions_completed} completed · ${t.actions_outstanding} outstanding`} />
            <StatCard label="Processing success" value={a.processing.success_rate === null ? "—" : `${Math.round(a.processing.success_rate * 100)}%`}
              hint={a.processing.finished_jobs ? `${a.processing.succeeded} of ${a.processing.finished_jobs} finished jobs succeeded` : "No processing jobs have finished yet"} />
          </div>
          <div className="mt-6 grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader title="Meetings per week" subtitle="By meeting date" />
              <div className="h-64 p-3"><ResponsiveContainer><BarChart data={weekly} margin={{ left: -16, right: 8 }}>
                <CartesianGrid vertical={false} stroke="#eef0f3" /><XAxis dataKey="label" {...axis} /><YAxis allowDecimals={false} {...axis} />
                <Tooltip cursor={{ fill: "#f1f5f9" }} /><Bar dataKey="meetings" name="Meetings" fill="#4f46e5" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart></ResponsiveContainer></div>
            </Card>
            <Card>
              <CardHeader title="Action items per week" subtitle="Created (by creation date) and completed (by completion date)" />
              <div className="h-64 p-3"><ResponsiveContainer><LineChart data={weekly} margin={{ left: -16, right: 8 }}>
                <CartesianGrid vertical={false} stroke="#eef0f3" /><XAxis dataKey="label" {...axis} /><YAxis allowDecimals={false} {...axis} />
                <Tooltip /><Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                <Line dataKey="actions_created" name="Created" stroke="#4f46e5" strokeWidth={2} dot={false} />
                <Line dataKey="actions_completed" name="Completed" stroke="#10b981" strokeWidth={2} dot={false} />
              </LineChart></ResponsiveContainer></div>
            </Card>
            <Card>
              <CardHeader title="Meeting minutes per week" />
              <div className="h-64 p-3"><ResponsiveContainer><BarChart data={weekly} margin={{ left: -16, right: 8 }}>
                <CartesianGrid vertical={false} stroke="#eef0f3" /><XAxis dataKey="label" {...axis} /><YAxis {...axis} />
                <Tooltip cursor={{ fill: "#f1f5f9" }} /><Bar dataKey="minutes" name="Minutes" fill="#94a3b8" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart></ResponsiveContainer></div>
            </Card>
            <Card>
              <CardHeader title="Decisions by project" subtitle="Excluding rejected decisions" />
              {a.decisions_by_project.length === 0 ? <p className="px-5 py-10 text-center text-sm text-muted">No decisions recorded yet.</p> : (
                <ul className="divide-y divide-line">
                  {a.decisions_by_project.map((d) => {
                    const max = Math.max(...a.decisions_by_project.map((x) => x.decisions));
                    return (
                      <li key={d.project} className="px-5 py-2.5">
                        <div className="flex justify-between text-sm"><span>{d.project}</span><span className="tabular-nums text-muted">{d.decisions}</span></div>
                        <div className="mt-1.5 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-accent" style={{ width: `${(d.decisions / max) * 100}%` }} /></div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
