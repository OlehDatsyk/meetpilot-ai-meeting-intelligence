import { useQuery } from "@tanstack/react-query";
import {
  BarChart3, Bot, CheckSquare, ChevronDown, FileText, FolderKanban, Gavel, LayoutDashboard, LogOut, Menu,
  MessageSquareText, Search, Settings, Upload, Users, X,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { get } from "../lib/api";
import { useSession } from "../lib/session";
import type { SystemStatus } from "../lib/types";
import { Logo } from "./Logo";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/meetings", label: "Meetings", icon: Users },
  { to: "/upload", label: "Upload Recording", icon: Upload },
  { to: "/transcripts", label: "Transcripts", icon: MessageSquareText },
  { to: "/action-items", label: "Action Items", icon: CheckSquare },
  { to: "/decisions", label: "Decisions", icon: Gavel },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/assistant", label: "AI Assistant", icon: Bot },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

function WorkspaceSwitcher() {
  const { workspaces, workspace, selectWorkspace } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  if (!workspace) return null;
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-lg border border-navy-700 bg-navy-800/60 px-2.5 py-2 text-left hover:bg-navy-800">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-indigo-500/20 text-xs font-semibold text-indigo-200">
          {workspace.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-white">{workspace.name}</span>
          <span className="block text-[11px] capitalize text-slate-400">{workspace.is_demo ? "Demo · fictional data" : workspace.role}</span>
        </span>
        <ChevronDown className="size-4 text-slate-400" />
      </button>
      {open && (
        <div className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-lg border border-navy-700 bg-navy-900 py-1 shadow-xl">
          {workspaces.map((w) => (
            <button key={w.id} onClick={() => { selectWorkspace(w.id); setOpen(false); navigate("/"); }}
              className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-navy-800 ${w.id === workspace.id ? "text-white" : "text-slate-300"}`}>
              <span className="truncate">{w.name}</span>
              {w.is_demo && <span className="ml-2 rounded bg-amber-400/15 px-1.5 text-[10px] text-amber-300">DEMO</span>}
            </button>
          ))}
          <button onClick={() => { setOpen(false); navigate("/settings#workspaces"); }}
            className="w-full border-t border-navy-700 px-3 py-2 text-left text-xs text-slate-400 hover:bg-navy-800 hover:text-white">
            Manage workspaces…
          </button>
        </div>
      )}
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, signOut } = useSession();
  return (
    <div className="flex h-full flex-col bg-navy-950 text-slate-300">
      <div className="px-4 pb-4 pt-5"><Logo dark /></div>
      <div className="px-3"><WorkspaceSwitcher /></div>
      <nav className="mt-4 flex-1 space-y-0.5 overflow-y-auto px-3" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} onClick={onNavigate}
            className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${isActive ? "bg-navy-800 font-medium text-white" : "hover:bg-navy-900 hover:text-white"}`}>
            <Icon className="size-4 shrink-0" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-navy-800 p-3">
        <div className="flex items-center gap-2.5 px-1">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-white">
            {user?.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-white">{user?.name}</div>
            <div className="truncate text-xs text-slate-400">{user?.email}</div>
          </div>
          <button onClick={() => signOut()} title="Sign out" aria-label="Sign out" className="rounded-md p-1.5 text-slate-400 hover:bg-navy-800 hover:text-white">
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length >= 2) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  };
  return (
    <form onSubmit={submit} role="search" className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search meetings, transcripts, tasks…"
        aria-label="Search" className="input !pl-9" />
    </form>
  );
}

export function AppLayout() {
  const [open, setOpen] = useState(false);
  const { workspace } = useSession();
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => get<SystemStatus>("/api/v1/system/status"), staleTime: 300_000 });
  const ephemeral = status.data && !status.data.storage.persistent;

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 lg:block"><Sidebar /></aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw]">
            <button className="absolute right-3 top-4 z-10 rounded p-1 text-slate-300" onClick={() => setOpen(false)} aria-label="Close menu"><X className="size-5" /></button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="size-5" /></button>
          <GlobalSearch />
        </header>
        {workspace?.is_demo && (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900 sm:px-6">
            You are in the demo workspace. Its meetings, people and company are fictional sample data.
          </div>
        )}
        {ephemeral && (
          <div className="border-b border-slate-200 bg-slate-100 px-4 py-2 text-center text-xs text-slate-700 sm:px-6">
            This server uses temporary storage: uploaded audio and generated report files can disappear when it restarts.
          </div>
        )}
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8"><Outlet /></div>
        </main>
      </div>
    </div>
  );
}
