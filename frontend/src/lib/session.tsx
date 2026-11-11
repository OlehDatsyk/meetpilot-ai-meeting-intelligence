import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { get, getToken, post, setToken, setUnauthorizedHandler } from "./api";
import type { User, Workspace } from "./types";

interface Session {
  user: User | null;
  loading: boolean;
  signIn: (token: string, user: User) => void;
  signOut: () => Promise<void>;
  setUser: (u: User) => void;
  workspaces: Workspace[];
  workspace: Workspace | null;
  selectWorkspace: (id: string) => void;
  refreshWorkspaces: () => Promise<unknown>;
}

const Ctx = createContext<Session | null>(null);
const WS_KEY = "meetpilot.workspace";

function readWs(): string | null {
  try {
    return localStorage.getItem(WS_KEY);
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(getToken()));
  const [wsId, setWsId] = useState<string | null>(readWs());

  const clear = useCallback(() => {
    setToken(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    setUnauthorizedHandler(clear);
    if (!getToken()) return;
    get<User>("/api/v1/auth/me")
      .then(setUser)
      .catch(() => clear())
      .finally(() => setLoading(false));
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  const wsQuery = useQuery({
    queryKey: ["workspaces", user?.id],
    queryFn: () => get<Workspace[]>("/api/v1/workspaces"),
    enabled: Boolean(user),
  });
  const workspaces = wsQuery.data ?? [];
  const workspace = workspaces.find((w) => w.id === wsId) ?? workspaces.find((w) => !w.is_demo) ?? workspaces[0] ?? null;

  const selectWorkspace = useCallback((id: string) => {
    setWsId(id);
    try {
      localStorage.setItem(WS_KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<Session>(() => ({
    user,
    loading: loading || (Boolean(user) && wsQuery.isLoading),
    signIn: (token, u) => {
      setToken(token);
      qc.clear();
      setUser(u);
      setLoading(false);
    },
    signOut: async () => {
      try {
        await post("/api/v1/auth/logout");
      } catch {
        /* the token is dropped locally either way */
      }
      clear();
    },
    setUser,
    workspaces,
    workspace,
    selectWorkspace,
    refreshWorkspaces: () => wsQuery.refetch(),
  }), [user, loading, wsQuery, workspaces, workspace, selectWorkspace, qc, clear]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}

/** The current workspace; pages under the app layout can rely on it being set. */
export function useWorkspace(): Workspace {
  const { workspace } = useSession();
  if (!workspace) throw new Error("No workspace selected");
  return workspace;
}

export function canEdit(ws: Workspace) {
  return ws.role !== "viewer";
}
