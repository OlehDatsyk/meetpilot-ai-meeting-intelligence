import { useQuery } from "@tanstack/react-query";
import { CheckSquare, Download, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { ActionList } from "../components/records";
import { Button, Card, EmptyState, ErrorBox, PageHeader, Select, Spinner } from "../components/ui";
import { download, get, qs } from "../lib/api";
import { canEdit, useWorkspace } from "../lib/session";
import type { ActionItem, Page } from "../lib/types";
import { useProjects } from "./Meetings";

export default function ActionItemsPage() {
  const ws = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [owner, setOwner] = useState(params.get("owner") ?? "");
  const status = params.get("status") ?? "todo,in_progress";
  const view = params.get("view") ?? "";
  const project = params.get("project") ?? "";
  const sort = params.get("sort") ?? "due_asc";
  const [error, setError] = useState<unknown>(null);
  const projects = useProjects();
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }); };
  useEffect(() => { const t = setTimeout(() => { const n = new URLSearchParams(params); q ? n.set("q", q) : n.delete("q"); owner ? n.set("owner", owner) : n.delete("owner"); setParams(n, { replace: true }); }, 300); return () => clearTimeout(t); }, [q, owner]); // eslint-disable-line react-hooks/exhaustive-deps

  const key = ["actions", ws.id, params.toString()];
  const list = useQuery({ queryKey: key, queryFn: () => get<Page<ActionItem>>(`/api/v1/action-items${qs({
    workspace_id: ws.id, status: status === "all" ? "" : status, q: params.get("q"), owner: view === "unassigned" ? "unassigned" : params.get("owner"),
    overdue: view === "overdue" || undefined, project_id: project, sort, page_size: 200 })}`) });

  return (
    <>
      <PageHeader title="Action items" description="Tasks agreed in meetings. Unclear owners show as Unassigned; nothing is guessed."
        actions={<>
          <Button variant="secondary" onClick={() => download(`/api/v1/exports/action-items${qs({ workspace_id: ws.id, format: "csv" })}`, "action-items.csv").catch(setError)}><Download className="size-4" />CSV</Button>
          <Button variant="secondary" onClick={() => download(`/api/v1/exports/action-items${qs({ workspace_id: ws.id, format: "ics" })}`, "deadlines.ics").catch(setError)}><Download className="size-4" />Deadlines (.ics)</Button>
        </>} />
      <ErrorBox error={error} className="mb-4" />
      <Card>
        <div className="flex flex-col gap-2 border-b border-line p-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tasks and notes" aria-label="Search action items" className="input !pl-9" />
          </div>
          <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Owner" aria-label="Filter by owner" className="input lg:!w-40" />
          <div className="flex flex-wrap gap-2">
            <Select label="Status" value={status} onChange={(v) => set("status", v)} options={[
              { value: "todo,in_progress", label: "Open" }, { value: "todo", label: "To do" }, { value: "in_progress", label: "In progress" },
              { value: "completed", label: "Completed" }, { value: "cancelled", label: "Cancelled" }, { value: "all", label: "All statuses" }]} />
            <Select label="View" value={view} onChange={(v) => set("view", v)} options={[
              { value: "", label: "Everyone" }, { value: "overdue", label: "Overdue" }, { value: "unassigned", label: "Unassigned" }]} />
            <Select label="Project" value={project} onChange={(v) => set("project", v)} options={[{ value: "", label: "All projects" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))]} />
            <Select label="Sort" value={sort} onChange={(v) => set("sort", v)} options={[
              { value: "due_asc", label: "Deadline" }, { value: "priority", label: "Priority" }, { value: "created_desc", label: "Newest" }]} />
          </div>
        </div>
        {list.isLoading ? <Spinner /> : list.error ? <div className="p-5"><ErrorBox error={list.error} /></div> : list.data!.items.length === 0 ? (
          <EmptyState icon={<CheckSquare className="size-5" />} title="No action items here">
            Action items appear after a meeting is analysed, or when you add them to a meeting yourself.
          </EmptyState>
        ) : (
          <>
            <ActionList items={list.data!.items} invalidate={[["actions", ws.id], ["dashboard", ws.id]]} readOnly={!canEdit(ws)} />
            <div className="border-t border-line px-5 py-3 text-xs text-muted">{list.data!.total} action item{list.data!.total === 1 ? "" : "s"}</div>
          </>
        )}
      </Card>
    </>
  );
}
