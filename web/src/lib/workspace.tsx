// The signed-in user, their workspaces, and which one is open.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setWorkspaceId } from "./api";
import type { User, Workspace } from "./types";

interface WorkspaceState {
  user: User | null;
  workspaces: Workspace[];
  current: Workspace | null;
  error: string | null;
  switchTo: (id: string) => void;
  reload: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);
const STORAGE_KEY = "afrisearch.workspace";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setWorkspaceId(null); // /me lists every workspace, whichever is open
      const me = await api<{ user: User; workspaces: Workspace[] }>("/me");
      setUser(me.user);
      setWorkspaces(me.workspaces);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const current = workspaces.find((w) => w.id === currentId) ?? workspaces[0] ?? null;
  // Set synchronously during render so children's first requests already use it.
  setWorkspaceId(current?.id ?? null);

  const switchTo = useCallback((id: string) => {
    localStorage.setItem(STORAGE_KEY, id);
    setCurrentId(id);
  }, []);

  return (
    <WorkspaceContext.Provider value={{ user, workspaces, current, error, switchTo, reload }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceState {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace outside WorkspaceProvider");
  return value;
}
