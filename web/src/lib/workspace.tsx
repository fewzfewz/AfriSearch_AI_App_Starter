// The signed-in user, their organizations, workspaces, and which one is active.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setOrganizationId, setWorkspaceId } from "./api";
import type { Organization, User, Workspace } from "./types";

interface WorkspaceState {
  user: User | null;
  organizations: Organization[];
  currentOrganization: Organization | null;
  workspaces: Workspace[];
  current: Workspace | null;
  error: string | null;
  switchOrganization: (id: string) => void;
  switchTo: (id: string) => void;
  reload: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);
const ORG_STORAGE_KEY = "afrisearch.organization";
const WORKSPACE_STORAGE_KEY = "afrisearch.workspace";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [currentOrgId, setCurrentOrgId] = useState<string | null>(() => localStorage.getItem(ORG_STORAGE_KEY));
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(() => localStorage.getItem(WORKSPACE_STORAGE_KEY));
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setWorkspaceId(null);
      const me = await api<{ user: User; organizations?: Organization[]; workspaces: Workspace[] }>("/me");
      setUser(me.user);
      const orgs = me.organizations || [];
      setOrganizations(orgs);
      setWorkspaces(me.workspaces);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const currentOrganization = organizations.find((o) => o.id === currentOrgId) ?? organizations[0] ?? null;
  setOrganizationId(currentOrganization?.id ?? null);

  const scopedWorkspaces = currentOrganization
    ? workspaces.filter((w) => !w.organization_id || w.organization_id === currentOrganization.id)
    : workspaces;

  const current = scopedWorkspaces.find((w) => w.id === currentId) ?? scopedWorkspaces[0] ?? null;
  setWorkspaceId(current?.id ?? null);

  const switchOrganization = useCallback(
    (id: string) => {
      localStorage.setItem(ORG_STORAGE_KEY, id);
      setCurrentOrgId(id);
      setOrganizationId(id);
      const orgWorkspaces = workspaces.filter((w) => !w.organization_id || w.organization_id === id);
      const nextWs = orgWorkspaces[0]?.id ?? null;
      if (nextWs) {
        localStorage.setItem(WORKSPACE_STORAGE_KEY, nextWs);
        setCurrentId(nextWs);
        setWorkspaceId(nextWs);
      }
    },
    [workspaces]
  );

  const switchTo = useCallback((id: string) => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, id);
    setCurrentId(id);
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        user,
        organizations,
        currentOrganization,
        workspaces: scopedWorkspaces,
        current,
        error,
        switchOrganization,
        switchTo,
        reload,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceState {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace outside WorkspaceProvider");
  return value;
}
