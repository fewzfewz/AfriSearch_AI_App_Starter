// Workspace, team, appearance and account settings.
import {
  AlertTriangle, Building2, Download, Info, LogOut, Monitor, Moon, Palette, Settings, Sun, Trash2, UserPlus, UserRound, Users,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card, ConfirmDialog, PageHeader, cx, useToast } from "../components/ui";
import { api, downloadFile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { initials, shortModelName } from "../lib/format";
import { useApi } from "../lib/hooks";
import { useTheme } from "../lib/theme";
import type { DocumentsResponse, Member } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

interface Team {
  members: Member[];
  invitations: { email: string; created_at: string }[];
}

const SECTIONS = [
  { id: "workspace", title: "Workspace", icon: Building2 },
  { id: "members", title: "Members", icon: Users },
  { id: "appearance", title: "Appearance", icon: Palette },
  { id: "account", title: "Account", icon: UserRound },
  { id: "about", title: "About", icon: Info },
  { id: "danger", title: "Danger zone", icon: AlertTriangle },
] as const;

function Section({ id, description, children, danger }: { id: (typeof SECTIONS)[number]["id"]; description?: string; children: ReactNode; danger?: boolean }) {
  const { title, icon: Icon } = SECTIONS.find((s) => s.id === id)!;
  return (
    <section id={id} className="scroll-mt-6">
      <Card className={cx("p-5 sm:p-6", danger && "border-red-200 dark:border-red-900/70")}>
        <div className="mb-5 flex items-start gap-3">
          <span className={cx("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
            danger ? "bg-red-50 text-red-600 dark:bg-red-950/60 dark:text-red-400" : "bg-brand-50 text-brand-700 dark:bg-brand-950/60 dark:text-brand-400")}>
            <Icon className="h-4 w-4" />
          </span>
          <div>
            <h2 className="font-semibold">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-ink-500 dark:text-ink-400">{description}</p>}
          </div>
        </div>
        {children}
      </Card>
    </section>
  );
}

const inputClass = "w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10 disabled:opacity-60 dark:border-ink-700 dark:bg-ink-900";

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
  const [exporting, setExporting] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [confirmAccount, setConfirmAccount] = useState("");

  const exportData = async () => {
    setExporting(true);
    try {
      await downloadFile("/me/export", "afrisearch-my-data.zip");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setExporting(false);
    }
  };
  const accountConfirmWord = user?.email || "DELETE";
  const ownedWorkspaces = workspaces.filter((w) => w.role === "owner");
  const members = useApi<Team>(current ? `/workspaces/${current.id}/members` : null);
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
      const result = await api<Team & { message: string }>(`/workspaces/${current!.id}/members`, { json: { email: email.trim() } });
      members.setData(result);
      setEmail("");
      toast(result.message);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setInviting(false);
    }
  };

  const removeMember = async (member: Member) => {
    try {
      const result = await api<Team>(`/workspaces/${current!.id}/members/${member.id}`, { method: "DELETE" });
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
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader icon={<Settings className="h-5 w-5" />} title="Settings" description="Your workspace, team, appearance and account." />
      <div className="mt-8 lg:grid lg:grid-cols-[180px_1fr] lg:gap-8">
        <nav aria-label="Settings sections" className="hidden lg:block">
          <ul className="sticky top-6 space-y-0.5 text-sm">
            {SECTIONS.filter((s) => s.id !== "danger" || isOwner).map(({ id, title, icon: Icon }) => (
              <li key={id}>
                <a href={`#${id}`} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-ink-600 transition hover:bg-ink-100 hover:text-ink-900 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-white">
                  <Icon className="h-4 w-4" /> {title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="space-y-5">
        <Section id="workspace" description="A workspace holds documents and chats. Create one per team, project or client.">
          <label htmlFor="ws-name" className="text-sm font-medium">Name</label>
          <div className="mt-1.5 flex gap-2">
            <input id="ws-name" value={name} maxLength={80} disabled={!isOwner} onChange={(e) => setName(e.target.value)} className={inputClass} />
            <Button variant="primary" loading={saving} disabled={!isOwner || !name.trim() || name.trim() === current.name} onClick={rename}>Save</Button>
          </div>
          {!isOwner && <p className="mt-2 text-xs text-ink-500">Only the owner can rename this workspace.</p>}
        </Section>

        <Section id="members" description={multiUser ? "People who can search and ask in this workspace." : "Sign-in is off on this server, so there is one local user. Turn on Supabase sign-in to share workspaces."}>
          <div className="divide-y divide-ink-100 overflow-hidden rounded-xl border border-ink-200/80 dark:divide-ink-800 dark:border-ink-800">
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
            {(members.data?.invitations ?? []).map((invitation) => (
              <div key={invitation.email} className="flex items-center gap-3 px-4 py-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-dashed border-ink-300 text-xs text-ink-400 dark:border-ink-700">
                  {initials("", invitation.email)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{invitation.email}</p>
                  <p className="truncate text-xs text-ink-500">Joins when they sign up or sign in with this email</p>
                </div>
                <Badge tone="amber">invited</Badge>
                {isOwner && (
                  <Button size="sm" variant="ghost" onClick={async () => {
                    const result = await api<Team>(`/workspaces/${current!.id}/invitations/${encodeURIComponent(invitation.email)}`, { method: "DELETE" });
                    members.setData(result);
                  }}>Cancel</Button>
                )}
              </div>
            ))}
          </div>
          {multiUser && isOwner && (
            <div className="mt-3 flex gap-2">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@example.org" aria-label="Email to add"
                onKeyDown={(e) => e.key === "Enter" && email.includes("@") && invite()} className={inputClass} />
              <Button icon={<UserPlus className="h-4 w-4" />} loading={inviting} disabled={!email.includes("@")} onClick={invite}>Add</Button>
            </div>
          )}
          {multiUser && isOwner && (
            <p className="mt-2 text-xs text-ink-500">
              {config?.email
                ? "People without an account get an invitation email, and join automatically when they sign up with that address."
                : "People without an account are invited: they join automatically when they sign up with that email. Send them the link to this site."}
            </p>
          )}
        </Section>

        <Section id="appearance" description="Light, dark, or follow your device.">
          <div className="grid grid-cols-3 gap-2">
            {([["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Monitor, "System"]] as const).map(([value, Icon, label]) => (
              <button key={value} type="button" onClick={() => setTheme(value)} aria-pressed={theme === value}
                className={cx("flex flex-col items-center gap-2 rounded-xl border p-4 text-sm transition",
                  theme === value ? "border-brand-400 bg-brand-50 font-medium text-brand-900 ring-4 ring-brand-500/10 dark:border-brand-700 dark:bg-brand-950/60 dark:text-brand-100" : "border-ink-200 hover:border-ink-300 dark:border-ink-800 dark:hover:border-ink-700")}>
                <Icon className="h-5 w-5" /> {label}
              </button>
            ))}
          </div>
        </Section>

        <Section id="account" description="Your sign-in, and your data.">
          <div className="flex items-center gap-3 rounded-xl bg-ink-50 p-4 dark:bg-ink-800/40">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-ink-800 text-sm font-semibold text-white dark:bg-ink-200 dark:text-ink-900">{initials(user?.name ?? "", user?.email)}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{user?.name}</p>
              <p className="truncate text-sm text-ink-500">{user?.email || "Local mode: no account needed on this computer"}</p>
            </div>
            {multiUser && <Button icon={<LogOut className="h-4 w-4" />} onClick={async () => { await signOut(); navigate("/"); }}>Sign out</Button>}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button icon={<Download className="h-4 w-4" />} loading={exporting} onClick={exportData}>Download my data</Button>
            <Button variant="ghost" className="text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950"
              icon={<Trash2 className="h-4 w-4" />} onClick={() => setDeletingAccount(true)}>
              {multiUser ? "Delete my account" : "Delete all my data"}
            </Button>
          </div>
          <p className="mt-2 text-xs text-ink-500">
            The download has your chats, ratings and the documents of workspaces you own. See the <Link to="/privacy" className="underline">privacy notice</Link>.
          </p>
        </Section>

        <Section id="about" description="What this server uses to read and search your documents.">
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <div><dt className="text-ink-500">Version</dt><dd className="font-medium">{config?.version}</dd></div>
            <div><dt className="text-ink-500">Sign-in</dt><dd className="font-medium">{multiUser ? "Supabase accounts" : "Off (local mode)"}</dd></div>
            <div><dt className="text-ink-500">Search model</dt><dd className="font-medium">{shortModelName(system.data?.embedder) || "…"}</dd></div>
            <div><dt className="text-ink-500">Reranker</dt><dd className="font-medium">{system.data ? shortModelName(system.data.reranker) || "Off" : "…"}</dd></div>
            <div className="sm:col-span-2"><dt className="text-ink-500">OCR</dt><dd className="font-medium">
              {system.data ? (system.data.ocr.available ? `On · ${system.data.ocr.languages.join(", ")}` : `Off · ${system.data.ocr.reason}`) : "…"}
            </dd></div>
          </dl>
          <p className="mt-4 flex flex-wrap gap-4 text-sm font-medium text-brand-700 dark:text-brand-400">
            <a href="/api/docs" target="_blank" rel="noreferrer" className="hover:underline">API documentation →</a>
            <Link to="/privacy" className="hover:underline">Privacy notice</Link>
            <Link to="/terms" className="hover:underline">Terms of use</Link>
          </p>
        </Section>

        {isOwner && (
          <Section id="danger" danger>
            <div className="flex flex-wrap items-center gap-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">Delete this workspace</p>
                <p className="text-sm text-ink-500">Deletes its documents, chats and feedback for everyone. This can't be undone.</p>
              </div>
              <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} disabled={workspaces.length < 2}
                title={workspaces.length < 2 ? "You can't delete your only workspace" : undefined} onClick={() => setDeleteOpen(true)}>
                Delete workspace
              </Button>
            </div>
          </Section>
        )}
        </div>
      </div>

      <ConfirmDialog
        open={deletingAccount}
        title={multiUser ? "Delete your account?" : "Delete all your data?"}
        confirmLabel="Delete forever"
        onClose={() => { setDeletingAccount(false); setConfirmAccount(""); }}
        confirmDisabled={confirmAccount.trim().toLowerCase() !== accountConfirmWord.toLowerCase()}
        onConfirm={async () => {
          try {
            const result = await api<{ message: string }>("/me", { method: "DELETE", json: { confirm: confirmAccount.trim() } });
            toast(result.message);
            if (multiUser) await signOut();
            window.location.href = "/";
          } catch (e) {
            toast((e as Error).message, "error");
          }
        }}
      >
        <p>This deletes your chats and ratings everywhere, and these workspaces with all their documents, <strong>for everyone in them</strong>:</p>
        <ul className="mt-2 list-disc pl-5">{ownedWorkspaces.map((w) => <li key={w.id}>{w.name}</li>)}</ul>
        <p className="mt-3">It can't be undone. Download your data first if you need it. Type <strong className="text-ink-900 dark:text-white">{accountConfirmWord}</strong> to confirm.</p>
        <input value={confirmAccount} onChange={(e) => setConfirmAccount(e.target.value)} aria-label="Confirmation" className={cx(inputClass, "mt-3")} />
      </ConfirmDialog>

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
