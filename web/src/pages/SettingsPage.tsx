// Workspace, team, appearance and account settings.
import { LogOut, Monitor, Moon, Sun, Trash2, UserPlus } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, ConfirmDialog, cx, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { initials, shortModelName } from "../lib/format";
import { useApi } from "../lib/hooks";
import { useTheme } from "../lib/theme";
import type { DocumentsResponse, Member } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-ink-200 py-8 first:border-t-0 first:pt-0 dark:border-ink-800 md:grid-cols-3">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
      </div>
      <div className="md:col-span-2">{children}</div>
    </section>
  );
}

const inputClass = "w-full rounded-lg border border-ink-300 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10 disabled:opacity-60 dark:border-ink-700 dark:bg-ink-900";

export function SettingsPage() {
  const { current, workspaces, user, reload, switchTo } = useWorkspace();
  const { config, signOut } = useAuth();
  const [theme, setTheme] = useTheme();
  const toast = useToast();
  const navigate = useNavigate();
  const isOwner = current?.role === "owner";
  const [name, setName] = useState(current?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [email, setEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmName, setConfirmName] = useState("");
  const members = useApi<{ members: Member[] }>(current ? `/workspaces/${current.id}/members` : null);
  const system = useApi<DocumentsResponse>("/documents");
  const multiUser = config?.auth === "supabase";

  const rename = async () => {
    setSaving(true);
    try {
      await api(`/workspaces/${current!.id}`, { method: "PATCH", json: { name: name.trim() } });
      await reload();
      toast("Workspace renamed");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const invite = async () => {
    setInviting(true);
    try {
      const result = await api<{ members: Member[] }>(`/workspaces/${current!.id}/members`, { json: { email: email.trim() } });
      members.setData(result);
      setEmail("");
      toast("Member added");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setInviting(false);
    }
  };

  const removeMember = async (member: Member) => {
    try {
      const result = await api<{ members: Member[] }>(`/workspaces/${current!.id}/members/${member.id}`, { method: "DELETE" });
      if (member.id === user?.id) {
        await reload();
        switchTo(workspaces.find((w) => w.id !== current!.id)?.id ?? "");
        navigate("/app");
        toast(`You left ${current!.name}`);
      } else {
        members.setData(result);
      }
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  if (!current) return null;
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
      <div className="mt-8">
        <Section title="Workspace" description="A workspace holds documents and chats. Create one per team, project or client.">
          <label htmlFor="ws-name" className="text-sm font-medium">Name</label>
          <div className="mt-1.5 flex gap-2">
            <input id="ws-name" value={name} maxLength={80} disabled={!isOwner} onChange={(e) => setName(e.target.value)} className={inputClass} />
            <Button variant="primary" loading={saving} disabled={!isOwner || !name.trim() || name.trim() === current.name} onClick={rename}>Save</Button>
          </div>
          {!isOwner && <p className="mt-2 text-xs text-ink-500">Only the owner can rename this workspace.</p>}
        </Section>

        <Section title="Members" description={multiUser ? "People who can search and ask in this workspace." : "Sign-in is off on this server, so there is one local user. Turn on Supabase sign-in to share workspaces."}>
          <Card className="divide-y divide-ink-100 dark:divide-ink-800">
            {(members.data?.members ?? []).map((member) => (
              <div key={member.id} className="flex items-center gap-3 px-4 py-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-100 text-xs font-semibold dark:bg-ink-800">{initials(member.name, member.email)}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{member.name}{member.id === user?.id && <span className="text-ink-400"> (you)</span>}</p>
                  <p className="truncate text-xs text-ink-500">{member.email || "local user"}</p>
                </div>
                <Badge tone={member.role === "owner" ? "brand" : "gray"}>{member.role}</Badge>
                {member.role !== "owner" && (isOwner || member.id === user?.id) && (
                  <Button size="sm" variant="ghost" onClick={() => removeMember(member)}>{member.id === user?.id ? "Leave" : "Remove"}</Button>
                )}
              </div>
            ))}
          </Card>
          {multiUser && isOwner && (
            <div className="mt-3 flex gap-2">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@example.org" aria-label="Email to add"
                onKeyDown={(e) => e.key === "Enter" && email.includes("@") && invite()} className={inputClass} />
              <Button icon={<UserPlus className="h-4 w-4" />} loading={inviting} disabled={!email.includes("@")} onClick={invite}>Add</Button>
            </div>
          )}
          {multiUser && isOwner && <p className="mt-2 text-xs text-ink-500">They need to have signed up to AfriSearch first.</p>}
        </Section>

        <Section title="Appearance">
          <div className="grid grid-cols-3 gap-2">
            {([["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Monitor, "System"]] as const).map(([value, Icon, label]) => (
              <button key={value} type="button" onClick={() => setTheme(value)} aria-pressed={theme === value}
                className={cx("flex flex-col items-center gap-2 rounded-xl border p-4 text-sm transition",
                  theme === value ? "border-brand-500 bg-brand-50 font-medium text-brand-900 dark:bg-brand-950 dark:text-brand-100" : "border-ink-200 hover:border-ink-300 dark:border-ink-800 dark:hover:border-ink-700")}>
                <Icon className="h-5 w-5" /> {label}
              </button>
            ))}
          </div>
        </Section>

        <Section title="Account">
          <Card className="flex items-center gap-3 p-4">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-ink-800 text-sm font-semibold text-white dark:bg-ink-200 dark:text-ink-900">{initials(user?.name ?? "", user?.email)}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{user?.name}</p>
              <p className="truncate text-sm text-ink-500">{user?.email || "Local mode: no account needed on this computer"}</p>
            </div>
            {multiUser && <Button icon={<LogOut className="h-4 w-4" />} onClick={async () => { await signOut(); navigate("/"); }}>Sign out</Button>}
          </Card>
        </Section>

        <Section title="About" description="What this server uses to read and search your documents.">
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <div><dt className="text-ink-500">Version</dt><dd className="font-medium">{config?.version}</dd></div>
            <div><dt className="text-ink-500">Sign-in</dt><dd className="font-medium">{multiUser ? "Supabase accounts" : "Off (local mode)"}</dd></div>
            <div><dt className="text-ink-500">Search model</dt><dd className="font-medium">{shortModelName(system.data?.embedder) || "…"}</dd></div>
            <div><dt className="text-ink-500">Reranker</dt><dd className="font-medium">{system.data ? shortModelName(system.data.reranker) || "Off" : "…"}</dd></div>
            <div className="sm:col-span-2"><dt className="text-ink-500">OCR</dt><dd className="font-medium">
              {system.data ? (system.data.ocr.available ? `On · ${system.data.ocr.languages.join(", ")}` : `Off · ${system.data.ocr.reason}`) : "…"}
            </dd></div>
          </dl>
          <a href="/api/docs" target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline dark:text-brand-400">API documentation →</a>
        </Section>

        {isOwner && (
          <Section title="Danger zone">
            <Card className="flex flex-wrap items-center gap-4 border-red-200 p-4 dark:border-red-900">
              <div className="min-w-0 flex-1">
                <p className="font-medium">Delete this workspace</p>
                <p className="text-sm text-ink-500">Deletes its documents, chats and feedback for everyone. This can't be undone.</p>
              </div>
              <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} disabled={workspaces.length < 2}
                title={workspaces.length < 2 ? "You can't delete your only workspace" : undefined} onClick={() => setDeleteOpen(true)}>
                Delete workspace
              </Button>
            </Card>
          </Section>
        )}
      </div>

      <ConfirmDialog
        open={deleteOpen}
        title={`Delete ${current.name}?`}
        confirmLabel="Delete forever"
        onClose={() => { setDeleteOpen(false); setConfirmName(""); }}
        confirmDisabled={confirmName !== current.name}
        onConfirm={async () => {
          await api(`/workspaces/${current.id}`, { method: "DELETE" });
          switchTo(workspaces.find((w) => w.id !== current.id)!.id);
          await reload();
          navigate("/app");
          toast("Workspace deleted");
        }}
      >
        <p>All documents, chats and feedback in this workspace will be deleted for everyone. Type <strong className="text-ink-900 dark:text-white">{current.name}</strong> to confirm.</p>
        <input value={confirmName} onChange={(e) => setConfirmName(e.target.value)} aria-label="Workspace name" className={cx(inputClass, "mt-3")} />
      </ConfirmDialog>
    </div>
  );
}
