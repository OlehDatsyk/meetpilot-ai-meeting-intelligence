import { useQuery } from "@tanstack/react-query";
import { Download, Gavel, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { DecisionList } from "../components/records";
import { Button, Card, EmptyState, ErrorBox, PageHeader, Select, Spinner } from "../components/ui";
import { download, get, qs } from "../lib/api";
import { canEdit, useWorkspace } from "../lib/session";
import type { Decision, Page } from "../lib/types";
import { useProjects } from "./Meetings";

export default function DecisionsPage() {
  const ws = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const ms = params.get("meeting_status") ?? "";
  const review = params.get("review") ?? "unreviewed,confirmed";
  const project = params.get("project") ?? "";
  const [error, setError] = useState<unknown>(null);
  const projects = useProjects();
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }); };
  useEffect(() => { const t = setTimeout(() => set("q", q), 300); return () => clearTimeout(t); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const list = useQuery({ queryKey: ["decisions", ws.id, params.toString()], queryFn: () => get<Page<Decision>>(`/api/v1/decisions${qs({
    workspace_id: ws.id, q: params.get("q"), meeting_status: ms, review_status: review === "all" ? "" : review, project_id: project, page_size: 200 })}`) });
  return (
    <>
      <PageHeader title="Decisions" description="Review what was decided. Confirmed decisions are kept apart from proposals and unclear items."
        actions={<Button variant="secondary" onClick={() => download(`/api/v1/exports/decisions${qs({ workspace_id: ws.id, format: "csv" })}`, "decisions.csv").catch(setError)}><Download className="size-4" />CSV</Button>} />
      <ErrorBox error={error} className="mb-4" />
      <Card>
        <div className="flex flex-col gap-2 border-b border-line p-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search decisions" aria-label="Search decisions" className="input !pl-9" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Select label="Status in meeting" value={ms} onChange={(v) => set("meeting_status", v)} options={[
              { value: "", label: "Any meeting status" }, { value: "confirmed", label: "Confirmed in meeting" }, { value: "proposed", label: "Proposed" }, { value: "uncertain", label: "Uncertain" }]} />
            <Select label="Review" value={review} onChange={(v) => set("review", v)} options={[
              { value: "unreviewed,confirmed", label: "Not rejected" }, { value: "unreviewed", label: "Needs review" }, { value: "confirmed", label: "Reviewed" },
              { value: "rejected", label: "Rejected" }, { value: "all", label: "All" }]} />
            <Select label="Project" value={project} onChange={(v) => set("project", v)} options={[{ value: "", label: "All projects" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))]} />
          </div>
        </div>
        {list.isLoading ? <Spinner /> : list.error ? <div className="p-5"><ErrorBox error={list.error} /></div> : list.data!.items.length === 0 ? (
          <EmptyState icon={<Gavel className="size-5" />} title="No decisions here">Decisions appear after a meeting is analysed, or when you record one on a meeting.</EmptyState>
        ) : <DecisionList items={list.data!.items} invalidate={[["decisions", ws.id], ["dashboard", ws.id]]} readOnly={!canEdit(ws)} />}
      </Card>
    </>
  );
}
