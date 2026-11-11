import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash, Sparkles, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { Badge, Button, Card, CardHeader, ErrorBox, Field, Modal, Notice, PageHeader, Spinner } from "../components/ui";
import { del, get, patch, post, setToken } from "../lib/api";
import { useSession, useWorkspace } from "../lib/session";
import type { Member, Role, SystemStatus, User } from "../lib/types";
import { useDemoWorkspace } from "./Overview";

function Section({ id, title, description, children }: { id?: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} className="grid gap-4 border-b border-line py-8 first:pt-0 last:border-0 lg:grid-cols-[280px_1fr]">
      <div><h2 className="text-sm font-semibold">{title}</h2>{description && <p className="mt-1 text-sm text-muted">{description}</p>}</div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Profile() {
  const { user, setUser } = useSession();
  const [name, setName] = useState(user?.name ?? "");
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const save = useMutation({ mutationFn: () => patch<User>("/api/v1/auth/me", { name }), onSuccess: setUser });
  const change = useMutation({ mutationFn: () => post<{ access_token: string }>("/api/v1/auth/change-password", pw),
    onSuccess: (r) => { setToken(r.access_token); setPw({ current_password: "", new_password: "" }); } });
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card className="space-y-3 p-5">
        <Field label="Name" htmlFor="s-name"><input id="s-name" className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Email"><input className="input" value={user?.email ?? ""} disabled /></Field>
        <ErrorBox error={save.error} />
        <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>{save.isSuccess ? "Saved" : "Save profile"}</Button>
      </Card>
      <Card className="space-y-3 p-5">
        <Field label="Current password" htmlFor="s-cur"><input id="s-cur" type="password" autoComplete="current-password" className="input" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
        <Field label="New password" htmlFor="s-new" hint="At least 10 characters. Other devices are signed out."><input id="s-new" type="password" autoComplete="new-password" minLength={10} className="input" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
        <ErrorBox error={change.error} />
        {change.isSuccess && <p className="text-sm text-emerald-700">Password changed.</p>}
        <Button variant="secondary" loading={change.isPending} disabled={!pw.current_password || pw.new_password.length < 10} onClick={() => change.mutate()}>Change password</Button>
      </Card>
    </div>
  );
}

function Workspaces() {
  const ws = useWorkspace();
  const { refreshWorkspaces, selectWorkspace, workspaces, user } = useSession();
  const qc = useQueryClient();
  const isAdmin = ws.role === "owner" || ws.role === "admin";
  const [name, setName] = useState(ws.name);
  const [retention, setRetention] = useState(ws.recording_retention_days ? String(ws.recording_retention_days) : "");
  const [newName, setNewName] = useState("");
  const [invite, setInvite] = useState({ email: "", role: "member" as Role });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const members = useQuery({ queryKey: ["members", ws.id], queryFn: () => get<Member[]>(`/api/v1/workspaces/${ws.id}/members`) });
  const refreshMembers = () => qc.invalidateQueries({ queryKey: ["members", ws.id] });
  const save = useMutation({ mutationFn: () => patch(`/api/v1/workspaces/${ws.id}`, { name, ...(retention ? { recording_retention_days: Number(retention) } : { clear_retention: true }) }), onSuccess: () => refreshWorkspaces() });
  const create = useMutation({ mutationFn: () => post<{ id: string }>("/api/v1/workspaces", { name: newName }), onSuccess: async (w) => { setNewName(""); await refreshWorkspaces(); selectWorkspace(w.id); } });
  const add = useMutation({ mutationFn: () => post(`/api/v1/workspaces/${ws.id}/members`, invite), onSuccess: () => { setInvite({ email: "", role: "member" }); refreshMembers(); } });
  const setRole = useMutation({ mutationFn: ({ id, role }: { id: string; role: Role }) => patch(`/api/v1/workspaces/${ws.id}/members/${id}`, { role }), onSuccess: refreshMembers });
  const removeMember = useMutation({ mutationFn: (id: string) => del(`/api/v1/workspaces/${ws.id}/members/${id}`), onSuccess: async () => { refreshMembers(); await refreshWorkspaces(); } });
  const remove = useMutation({ mutationFn: () => del(`/api/v1/workspaces/${ws.id}`), onSuccess: async () => {
    const next = workspaces.find((w) => w.id !== ws.id);
    if (next) selectWorkspace(next.id);
    qc.clear();
    await refreshWorkspaces();
    setConfirmDelete(false);
  } });

  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-5">
        <div className="flex items-center gap-2"><h3 className="text-sm font-semibold">Current workspace</h3><Badge>{ws.role}</Badge>{ws.is_demo && <Badge tone="amber">Demo</Badge>}</div>
        <fieldset disabled={!isAdmin} className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" htmlFor="w-name"><input id="w-name" className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Delete recording audio after (days)" htmlFor="w-ret" hint="Empty keeps audio until you delete it. Transcripts and analysis are kept.">
            <input id="w-ret" type="number" min={1} max={3650} className="input" value={retention} onChange={(e) => setRetention(e.target.value)} />
          </Field>
        </fieldset>
        <ErrorBox error={save.error} />
        {isAdmin && <Button loading={save.isPending} onClick={() => save.mutate()}>{save.isSuccess ? "Saved" : "Save workspace"}</Button>}
      </Card>

      <Card>
        <CardHeader title="Members" subtitle="People must already have a MeetPilot AI account. Viewers can read but not change anything." />
        {members.isLoading ? <Spinner /> : (
          <ul className="divide-y divide-line">
            {(members.data ?? []).map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
                <div className="min-w-0"><div className="text-sm font-medium">{m.name}{m.user_id === user?.id && " (you)"}</div><div className="text-xs text-muted">{m.email}</div></div>
                <div className="flex items-center gap-2">
                  {isAdmin ? (
                    <select aria-label={`Role for ${m.name}`} className="input !w-auto !py-1" value={m.role} onChange={(e) => setRole.mutate({ id: m.id, role: e.target.value as Role })}>
                      {(["owner", "admin", "member", "viewer"] as Role[]).map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  ) : <Badge>{m.role}</Badge>}
                  {(isAdmin || m.user_id === user?.id) && <button aria-label={m.user_id === user?.id ? "Leave workspace" : `Remove ${m.name}`} title={m.user_id === user?.id ? "Leave" : "Remove"}
                    onClick={() => confirm(m.user_id === user?.id ? "Leave this workspace?" : `Remove ${m.name}?`) && removeMember.mutate(m.id)} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"><Trash2 className="size-4" /></button>}
                </div>
              </li>
            ))}
          </ul>
        )}
        <ErrorBox error={setRole.error || removeMember.error || add.error} className="mx-5 mb-3" />
        {isAdmin && !ws.is_demo && (
          <div className="flex flex-col gap-2 border-t border-line p-4 sm:flex-row">
            <input type="email" placeholder="colleague@example.com" aria-label="Email to add" className="input" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
            <select aria-label="Role" className="input sm:!w-36" value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value as Role })}>
              <option value="member">Member</option><option value="admin">Admin</option><option value="viewer">Viewer</option>
            </select>
            <Button loading={add.isPending} disabled={!invite.email} onClick={() => add.mutate()}>Add</Button>
          </div>
        )}
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="space-y-3 p-5">
          <h3 className="text-sm font-semibold">Create a workspace</h3>
          <div className="flex gap-2"><input className="input" placeholder="Workspace name" aria-label="New workspace name" value={newName} onChange={(e) => setNewName(e.target.value)} /><Button loading={create.isPending} disabled={!newName.trim()} onClick={() => create.mutate()}>Create</Button></div>
          <ErrorBox error={create.error} />
        </Card>
        {ws.role === "owner" && (
          <Card className="space-y-3 p-5">
            <h3 className="text-sm font-semibold">Delete this workspace</h3>
            <p className="text-sm text-muted">Deletes every meeting, recording, transcript, report and conversation in it.</p>
            <Button variant="danger" onClick={() => setConfirmDelete(true)}><Trash2 className="size-4" />Delete workspace</Button>
          </Card>
        )}
      </div>
      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title={`Delete “${ws.name}”?`}
        footer={<><Button variant="secondary" onClick={() => setConfirmDelete(false)}>Cancel</Button><Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Delete permanently</Button></>}>
        <p className="text-sm">All data in this workspace will be permanently deleted for every member. This cannot be undone.</p>
        <ErrorBox error={remove.error} />
      </Modal>
    </div>
  );
}

function Providers() {
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => get<SystemStatus>("/api/v1/system/status") });
  if (status.isLoading) return <Spinner />;
  if (status.error) return <ErrorBox error={status.error} />;
  const s = status.data!;
  const row = (label: string, ok: boolean, text: ReactNode) => (
    <li className="flex items-start gap-3 px-5 py-3 text-sm">
      {ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <CircleSlash className="mt-0.5 size-4 shrink-0 text-slate-400" />}
      <div><div className="font-medium">{label}</div><div className="text-muted">{text}</div></div>
    </li>
  );
  return (
    <Card>
      <ul className="divide-y divide-line">
        {row("Transcription", s.transcription.configured, s.transcription.configured
          ? `${s.transcription.provider} / ${s.transcription.model} · ${s.transcription.timestamps ? "timestamps" : "no timestamps"} · ${s.transcription.diarization ? "speaker detection" : "no speaker detection"}`
          : s.transcription.error || "Not configured. Set TRANSCRIPTION_PROVIDER on the server.")}
        {row("AI analysis and assistant", s.ai.configured, s.ai.configured
          ? `${s.ai.provider} / ${s.ai.model}${s.ai.fallbacks?.length ? ` · fallback: ${s.ai.fallbacks.map((f) => f.provider).join(", ")}` : ""}`
          : s.ai.error || "Not configured. Set AI_PROVIDER and an API key on the server.")}
        {row("Storage", s.storage.persistent && s.storage.database_persistent, `${s.storage.provider}${s.storage.persistent ? "" : " · temporary: files can be lost when the server restarts"}${s.storage.database_persistent ? "" : " · the database is temporary too: all data is deleted on restart"}`)}
        {row("Uploads", true, `${s.uploads.extensions.join(", ")} · up to ${s.uploads.max_size_mb} MB and ${s.uploads.max_duration_minutes} min${s.uploads.ffmpeg_available ? "" : " · ffmpeg missing, so long files cannot be split"}`)}
        {row("Search", true, "Keyword search. Semantic (embedding) search is not implemented.")}
        {row("Password reset email", s.password_reset_email, s.password_reset_email ? "Configured" : "No mail server configured")}
      </ul>
      <p className="border-t border-line px-5 py-3 text-xs text-muted">Provider keys are kept on the server and are never sent to the browser. Version {s.version}.</p>
    </Card>
  );
}

function DangerZone() {
  const { signOut } = useSession();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const remove = useMutation({ mutationFn: () => del("/api/v1/auth/me", { password }), onSuccess: async () => { await signOut().catch(() => undefined); navigate("/login"); } });
  return (
    <Card className="space-y-3 p-5">
      <p className="text-sm text-slate-600">Deletes your account and every workspace where you are the only owner, including their recordings, transcripts and reports. Read the <Link to="/privacy" className="text-accent hover:underline">privacy notice</Link> for what is stored.</p>
      <Button variant="danger" onClick={() => setOpen(true)}><Trash2 className="size-4" />Delete my account</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Delete your account?"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button variant="danger" loading={remove.isPending} disabled={!password} onClick={() => remove.mutate()}>Delete account</Button></>}>
        <Notice tone="amber">This cannot be undone.</Notice>
        <Field label="Confirm with your password" htmlFor="del-pw"><input id="del-pw" type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <ErrorBox error={remove.error} />
      </Modal>
    </Card>
  );
}

export default function SettingsPage() {
  const { workspaces } = useSession();
  const demo = useDemoWorkspace();
  const hasDemo = workspaces.some((w) => w.is_demo);
  return (
    <>
      <PageHeader title="Settings" />
      <Section title="Profile" description="Your name and password."><Profile /></Section>
      <Section id="workspaces" title="Workspaces" description="Members, roles, retention and deletion."><Workspaces /></Section>
      <Section title="AI and transcription" description="What this server is configured to use. Changed by the server administrator through environment variables."><Providers /></Section>
      <Section title="Demo workspace" description="Fictional sample meetings for trying features without your own data.">
        <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
          <p className="text-sm text-muted">{hasDemo ? "You already have a demo workspace. Pick it from the workspace menu." : "Creates a separate workspace with two fictional meetings."}</p>
          {!hasDemo && <Button variant="secondary" loading={demo.isPending} onClick={() => demo.mutate()}><Sparkles className="size-4" />Create demo workspace</Button>}
          <ErrorBox error={demo.error} />
        </Card>
      </Section>
      <Section title="Account and data" description="Delete your account and data."><DangerZone /></Section>
    </>
  );
}
