import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FolderKanban, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ActionList, DecisionList, MeetingList } from "../components/records";
import { Button, Card, CardHeader, EmptyState, ErrorBox, Field, Modal, PageHeader, Spinner, StatCard } from "../components/ui";
import { del, get, patch, post, qs } from "../lib/api";
import { formatDate, relativeTime } from "../lib/format";
import { canEdit, useWorkspace } from "../lib/session";
import type { ActionItem, Activity, Decision, Meeting, Page, Project } from "../lib/types";
import { useProjects } from "./Meetings";

function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs text-muted"><span>{total ? `${done} of ${total} action items completed` : "No action items yet"}</span>{total > 0 && <span>{pct}%</span>}</div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

function ProjectEditor({ project, onClose }: { project?: Project; onClose: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const save = useMutation({
    mutationFn: () => (project ? patch(`/api/v1/projects/${project.id}`, { name, description }) : post("/api/v1/projects", { workspace_id: ws.id, name, description })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["projects", ws.id] }); qc.invalidateQueries({ queryKey: ["project"] }); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title={project ? "Edit project" : "New project"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>Save</Button></>}>
      <ErrorBox error={save.error} />
      <Field label="Name" htmlFor="p-name"><input id="p-name" className="input" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Description" htmlFor="p-desc"><textarea id="p-desc" rows={3} className="input" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
    </Modal>
  );
}

export function ProjectsPage() {
  const ws = useWorkspace();
  const projects = useProjects();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader title="Projects" description="Group related meetings and follow their decisions and action items."
        actions={canEdit(ws) && <Button onClick={() => setCreating(true)}><Plus className="size-4" />New project</Button>} />
      {projects.isLoading ? <Spinner /> : projects.error ? <ErrorBox error={projects.error} /> : !projects.data!.length ? (
        <Card><EmptyState icon={<FolderKanban className="size-5" />} title="No projects yet">Create a project, then assign meetings to it from the meeting's details.</EmptyState></Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.data!.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="card block p-5 transition-shadow hover:shadow-md">
              <h2 className="font-semibold text-ink">{p.name}</h2>
              <p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted">{p.description || "No description."}</p>
              <div className="mt-4 flex gap-4 text-xs text-slate-600">
                <span>{p.meeting_count} meetings</span><span>{p.decision_count} decisions</span><span>{p.action_open} open actions</span>
              </div>
              <div className="mt-3"><Progress done={p.action_completed} total={p.action_total} /></div>
              <div className="mt-3 text-xs text-muted">{p.last_meeting_at ? `Last meeting ${formatDate(p.last_meeting_at)}` : "No meetings yet"}</div>
            </Link>
          ))}
        </div>
      )}
      {creating && <ProjectEditor onClose={() => setCreating(false)} />}
    </>
  );
}

export function ProjectDetailPage() {
  const { id = "" } = useParams();
  const ws = useWorkspace();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const project = useQuery({ queryKey: ["project", id], queryFn: () => get<Project>(`/api/v1/projects/${id}`) });
  const meetings = useQuery({ queryKey: ["meetings", ws.id, "project", id], queryFn: () => get<Page<Meeting>>(`/api/v1/meetings${qs({ workspace_id: ws.id, project_id: id, page_size: 100 })}`) });
  const actions = useQuery({ queryKey: ["actions", ws.id, "project", id], queryFn: () => get<Page<ActionItem>>(`/api/v1/action-items${qs({ workspace_id: ws.id, project_id: id, status: "todo,in_progress", page_size: 50 })}`) });
  const decisions = useQuery({ queryKey: ["decisions", ws.id, "project", id], queryFn: () => get<Page<Decision>>(`/api/v1/decisions${qs({ workspace_id: ws.id, project_id: id, review_status: "unreviewed,confirmed", page_size: 50 })}`) });
  const activity = useQuery({ queryKey: ["activity", ws.id], queryFn: () => get<Activity[]>(`/api/v1/workspaces/${ws.id}/activity?limit=100`) });
  const remove = useMutation({ mutationFn: () => del(`/api/v1/projects/${id}`), onSuccess: () => { qc.invalidateQueries({ queryKey: ["projects", ws.id] }); navigate("/projects"); } });

  if (project.isLoading) return <Spinner />;
  if (project.error) return <ErrorBox error={project.error} />;
  const p = project.data!;
  const meetingIds = new Set((meetings.data?.items ?? []).map((m) => m.id));
  const recent = (activity.data ?? []).filter((a) => a.meeting_id && meetingIds.has(a.meeting_id)).slice(0, 8);
  const inv = [["actions", ws.id], ["decisions", ws.id], ["project", id]];

  return (
    <>
      <Link to="/projects" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" />Projects</Link>
      <PageHeader title={p.name} description={p.description}
        actions={canEdit(ws) && <>
          <Button variant="secondary" onClick={() => setEditing(true)}><Pencil className="size-4" />Edit</Button>
          <Button variant="ghost" onClick={() => confirm("Delete this project? Its meetings are kept without a project.") && remove.mutate()}><Trash2 className="size-4" />Delete</Button>
        </>} />
      <ErrorBox error={remove.error} className="mb-4" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Meetings" value={p.meeting_count} />
        <StatCard label="Decisions" value={p.decision_count} />
        <StatCard label="Open action items" value={p.action_open} />
        <Card className="p-4"><div className="text-xs font-medium text-muted">Progress</div><div className="mt-3"><Progress done={p.action_completed} total={p.action_total} /></div></Card>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card><CardHeader title="Meetings" />{meetings.data?.items.length ? <MeetingList meetings={meetings.data.items} /> : <p className="px-5 py-8 text-center text-sm text-muted">No meetings in this project.</p>}</Card>
        <Card><CardHeader title="Recent activity" />
          {recent.length ? <ul className="divide-y divide-line">{recent.map((a) => <li key={a.id} className="px-5 py-2.5 text-sm">{a.summary}<div className="text-xs text-muted">{relativeTime(a.created_at)}</div></li>)}</ul>
            : <p className="px-5 py-8 text-center text-sm text-muted">No recent activity.</p>}
        </Card>
        <Card><CardHeader title="Open action items" />{actions.data?.items.length ? <ActionList items={actions.data.items} invalidate={inv} readOnly={!canEdit(ws)} /> : <p className="px-5 py-8 text-center text-sm text-muted">No open action items.</p>}</Card>
        <Card><CardHeader title="Decisions" />{decisions.data?.items.length ? <DecisionList items={decisions.data.items} invalidate={inv} readOnly={!canEdit(ws)} /> : <p className="px-5 py-8 text-center text-sm text-muted">No decisions yet.</p>}</Card>
      </div>
      {editing && <ProjectEditor project={p} onClose={() => setEditing(false)} />}
    </>
  );
}
