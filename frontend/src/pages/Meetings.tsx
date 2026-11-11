import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Search, Upload, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { MeetingList } from "../components/records";
import { Button, Card, EmptyState, ErrorBox, Field, Modal, PageHeader, Select, Spinner } from "../components/ui";
import { get, post, qs } from "../lib/api";
import { STATUS_LABEL } from "../lib/format";
import { canEdit, useWorkspace } from "../lib/session";
import type { Meeting, MeetingDetail, Page, Project } from "../lib/types";

export function useProjects() {
  const ws = useWorkspace();
  return useQuery({ queryKey: ["projects", ws.id], queryFn: () => get<Project[]>(`/api/v1/projects${qs({ workspace_id: ws.id })}`) });
}

export function MeetingForm({ value, onChange, projects }:
  { value: MeetingFormValue; onChange: (v: MeetingFormValue) => void; projects: Project[] }) {
  return (
    <div className="space-y-4">
      <Field label="Title" htmlFor="m-title"><input id="m-title" className="input" maxLength={200} required value={value.title} onChange={(e) => onChange({ ...value, title: e.target.value })} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Date and time" htmlFor="m-date"><input id="m-date" type="datetime-local" className="input" value={value.date} onChange={(e) => onChange({ ...value, date: e.target.value })} /></Field>
        <Field label="Project" htmlFor="m-project">
          <select id="m-project" className="input" value={value.project_id} onChange={(e) => onChange({ ...value, project_id: e.target.value })}>
            <option value="">No project</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Participants" htmlFor="m-people" hint="Comma separated. Used only as context; speakers are never identified from voices.">
        <input id="m-people" className="input" value={value.participants} onChange={(e) => onChange({ ...value, participants: e.target.value })} placeholder="e.g. Maya Chen, Daniel Okafor" />
      </Field>
      <Field label="Description" htmlFor="m-desc"><textarea id="m-desc" rows={3} className="input" value={value.description} onChange={(e) => onChange({ ...value, description: e.target.value })} /></Field>
    </div>
  );
}

export interface MeetingFormValue { title: string; date: string; project_id: string; participants: string; description: string }

export function toLocalInput(iso?: string) {
  const d = iso ? new Date(iso) : new Date();
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}

export function meetingPayload(v: MeetingFormValue) {
  return {
    title: v.title.trim(), description: v.description, meeting_date: v.date ? new Date(v.date).toISOString() : undefined,
    participants: v.participants.split(",").map((n) => n.trim()).filter(Boolean).map((name) => ({ name })),
  };
}

export default function MeetingsPage() {
  const ws = useWorkspace();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const project = params.get("project") ?? "";
  const status = params.get("status") ?? "";
  const sort = params.get("sort") ?? "date_desc";
  const dateFrom = params.get("from") ?? "";
  const dateTo = params.get("to") ?? "";
  const page = Number(params.get("page") ?? 1);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<MeetingFormValue>({ title: "", date: toLocalInput(), project_id: "", participants: "", description: "" });
  const projects = useProjects();

  useEffect(() => {
    const t = setTimeout(() => update({ q, page: "" }), 300);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  }

  const key = ["meetings", ws.id, params.get("q") ?? "", project, status, sort, dateFrom, dateTo, page];
  const list = useQuery({
    queryKey: key,
    queryFn: () => get<Page<Meeting>>(`/api/v1/meetings${qs({ workspace_id: ws.id, q: params.get("q"), project_id: project, status, sort,
      date_from: dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : "", date_to: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : "",
      page, page_size: 20 })}`),
    refetchInterval: (query) => (query.state.data?.items.some((m) => ["queued", "transcribing", "analysing"].includes(m.status)) ? 5000 : false),
  });
  const create = useMutation({
    mutationFn: () => post<MeetingDetail>("/api/v1/meetings", { workspace_id: ws.id, project_id: form.project_id || null, ...meetingPayload(form) }),
    onSuccess: (m) => { qc.invalidateQueries({ queryKey: ["meetings", ws.id] }); navigate(`/meetings/${m.id}`); },
  });
  const filtered = Boolean(params.get("q") || project || status || dateFrom || dateTo);
  const data = list.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Meetings" description="Every meeting in this workspace, with its processing status."
        actions={canEdit(ws) && <>
          <Button variant="secondary" onClick={() => setCreating(true)}><CalendarPlus className="size-4" />New meeting</Button>
          <Link to="/upload"><Button><Upload className="size-4" />Upload recording</Button></Link>
        </>} />
      <Card>
        <div className="flex flex-col gap-2 border-b border-line p-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input aria-label="Search meetings" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search titles and descriptions" className="input !pl-9" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Select label="Project" value={project} onChange={(v) => update({ project: v, page: "" })}
              options={[{ value: "", label: "All projects" }, { value: "none", label: "No project" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))]} />
            <Select label="Status" value={status} onChange={(v) => update({ status: v, page: "" })}
              options={[{ value: "", label: "Any status" }, ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))]} />
            <input type="date" aria-label="From date" className="input !w-auto" value={dateFrom} onChange={(e) => update({ from: e.target.value, page: "" })} />
            <input type="date" aria-label="To date" className="input !w-auto" value={dateTo} onChange={(e) => update({ to: e.target.value, page: "" })} />
            <Select label="Sort" value={sort} onChange={(v) => update({ sort: v })}
              options={[{ value: "date_desc", label: "Newest first" }, { value: "date_asc", label: "Oldest first" }, { value: "title_asc", label: "Title A–Z" }, { value: "title_desc", label: "Title Z–A" }]} />
          </div>
        </div>
        {list.isLoading ? <Spinner /> : list.error ? <div className="p-5"><ErrorBox error={list.error} /></div> : data!.items.length === 0 ? (
          <EmptyState icon={<Users className="size-5" />} title={filtered ? "No meetings match these filters" : "No meetings yet"}>
            {filtered ? "Try clearing a filter." : "Create a meeting or upload a recording to get started."}
          </EmptyState>
        ) : (
          <>
            <MeetingList meetings={data!.items} />
            <div className="flex items-center justify-between border-t border-line px-5 py-3 text-xs text-muted">
              <span>{data!.total} meeting{data!.total === 1 ? "" : "s"}</span>
              {pages > 1 && <div className="flex items-center gap-2">
                <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>Previous</Button>
                <span>Page {page} of {pages}</span>
                <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>Next</Button>
              </div>}
            </div>
          </>
        )}
      </Card>
      <Modal open={creating} onClose={() => setCreating(false)} title="New meeting"
        footer={<><Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button loading={create.isPending} disabled={!form.title.trim()} onClick={() => create.mutate()}>Create meeting</Button></>}>
        <ErrorBox error={create.error} />
        <MeetingForm value={form} onChange={setForm} projects={projects.data ?? []} />
        <p className="text-xs text-muted">You can upload a recording for this meeting afterwards, or keep it as a manual record and add decisions and action items yourself.</p>
      </Modal>
    </>
  );
}
