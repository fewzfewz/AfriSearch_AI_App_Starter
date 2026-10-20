// The signed-in app: sidebar (workspaces, navigation, recent chats) and the page.
import {
  BarChart3, Check, ChevronsUpDown, FolderOpen, LogOut, Menu, MessageSquare, Monitor, Moon, MoreHorizontal, Pencil,
  Plus, Settings, Sun, Trash2, Users, X,
} from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Button, ConfirmDialog, IconButton, Logo, MenuItem, Modal, Popover, Spinner, cx, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { initials, timeAgo } from "../lib/format";
import { useTheme, type Theme } from "../lib/theme";
import type { ChatSummary } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

interface ChatsState {
  chats: ChatSummary[];
  shared: ChatSummary[]; // chats other members shared with this workspace
  reload: () => void;
}
const ChatsContext = createContext<ChatsState>({ chats: [], shared: [], reload: () => {} });
export const useChats = () => useContext(ChatsContext);

function NameDialog({ open, title, initial, confirm, onSave, onClose }: {
  open: boolean;
  title: string;
  initial: string;
  confirm: string;
  onSave: (name: string) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState(initial);
  const [busy, setBusy] = useState(false);
  useEffect(() => setName(initial), [initial, open]);
  const save = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await onSave(name.trim());
      onClose();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!name.trim()} onClick={save}>{confirm}</Button>
        </>
      }
    >
      <input
        autoFocus
        value={name}
        maxLength={80}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && save()}
        className="w-full rounded-lg border border-ink-300 bg-transparent px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10 dark:border-ink-700"
      />
    </Modal>
  );
}

function WorkspaceSwitcher() {
  const { workspaces, current, switchTo, reload } = useWorkspace();
  const navigate = useNavigate();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <Popover width="w-64" trigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="flex w-full items-center gap-2.5 rounded-xl border border-ink-200 bg-white px-2.5 py-2 text-left shadow-sm transition hover:border-ink-300 dark:border-ink-800 dark:bg-ink-900 dark:hover:border-ink-700"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-xs font-bold text-brand-800 dark:bg-brand-900 dark:text-brand-200">
            {initials(current?.name ?? "")}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold">{current?.name ?? "…"}</span>
            <span className="block text-xs text-ink-500">{current?.role === "owner" ? "Workspace" : "Shared with you"}</span>
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 text-ink-400" />
        </button>
      )}>
        {(close) => (
          <>
            <p className="px-2.5 pb-1 pt-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">Workspaces</p>
            {workspaces.map((w) => (
              <MenuItem
                key={w.id}
                onClick={() => {
                  switchTo(w.id);
                  close();
                  navigate("/app");
                }}
                hint={w.id === current?.id ? <Check className="h-4 w-4 text-brand-700" /> : undefined}
              >
                <span className="block truncate">{w.name}</span>
              </MenuItem>
            ))}
            <div className="my-1 border-t border-ink-100 dark:border-ink-800" />
            <MenuItem icon={<Plus className="h-4 w-4" />} onClick={() => { close(); setCreating(true); }}>
              New workspace
            </MenuItem>
          </>
        )}
      </Popover>
      <NameDialog
        open={creating}
        title="New workspace"
        initial=""
        confirm="Create"
        onClose={() => setCreating(false)}
        onSave={async (name) => {
          try {
            const created = await api<{ id: string }>("/workspaces", { json: { name } });
            await reload();
            switchTo(created.id);
            navigate("/app/library");
            toast(`Created “${name}”. Add documents to get started.`);
          } catch (e) {
            toast((e as Error).message, "error");
          }
        }}
      />
    </>
  );
}

function ChatList({ onNavigate }: { onNavigate: () => void }) {
  const { chats, reload } = useChats();
  // The sidebar sits outside the chat route, so read the open chat from the URL.
  const chatId = useLocation().pathname.match(/^\/app\/chat\/([^/]+)/)?.[1];
  const navigate = useNavigate();
  const toast = useToast();
  const [renaming, setRenaming] = useState<ChatSummary | null>(null);
  const [deleting, setDeleting] = useState<ChatSummary | null>(null);
  if (!chats.length) return <p className="px-3 py-2 text-xs text-ink-400">Your conversations appear here.</p>;
  return (
    <>
      <ul className="space-y-0.5">
        {chats.map((chat) => (
          <li key={chat.id} className="group relative">
            <Link
              to={`/app/chat/${chat.id}`}
              onClick={onNavigate}
              className={cx(
                "block rounded-lg py-1.5 pl-3 pr-8 text-sm transition",
                chat.id === chatId ? "bg-ink-200/70 font-medium text-ink-900 dark:bg-ink-800 dark:text-white" : "text-ink-600 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800/60",
              )}
              title={chat.title}
            >
              <span className="flex items-center gap-1 truncate">
                {chat.shared ? <Users className="h-3 w-3 shrink-0 text-ink-400" aria-label="Shared" /> : null}
                <span className="truncate">{chat.title}</span>
              </span>
              <span className="block text-[11px] text-ink-400">{timeAgo(chat.updated_at)}</span>
            </Link>
            <div className="absolute right-1 top-1.5 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
              <Popover align="right" width="w-40" trigger={({ toggle }) => (
                <IconButton label="Chat options" onClick={toggle} className="h-7 w-7">
                  <MoreHorizontal className="h-4 w-4" />
                </IconButton>
              )}>
                {(close) => (
                  <>
                    <MenuItem icon={<Pencil className="h-4 w-4" />} onClick={() => { close(); setRenaming(chat); }}>Rename</MenuItem>
                    <MenuItem icon={<Users className="h-4 w-4" />} onClick={async () => {
                      close();
                      await api(`/chats/${chat.id}`, { method: "PATCH", json: { shared: !chat.shared } }).catch((e: Error) => toast(e.message, "error"));
                      toast(chat.shared ? "Stopped sharing" : "Shared read-only with everyone in this workspace");
                      reload();
                    }}>{chat.shared ? "Stop sharing" : "Share with workspace"}</MenuItem>
                    <MenuItem danger icon={<Trash2 className="h-4 w-4" />} onClick={() => { close(); setDeleting(chat); }}>Delete</MenuItem>
                  </>
                )}
              </Popover>
            </div>
          </li>
        ))}
      </ul>
      <NameDialog
        open={Boolean(renaming)}
        title="Rename chat"
        initial={renaming?.title ?? ""}
        confirm="Save"
        onClose={() => setRenaming(null)}
        onSave={async (title) => {
          await api(`/chats/${renaming!.id}`, { method: "PATCH", json: { title } }).catch((e: Error) => toast(e.message, "error"));
          reload();
        }}
      />
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete chat?"
        confirmLabel="Delete"
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          await api(`/chats/${deleting!.id}`, { method: "DELETE" }).catch((e: Error) => toast(e.message, "error"));
          if (deleting!.id === chatId) navigate("/app");
          reload();
        }}
      >
        “{deleting?.title}” and its answers will be deleted. Your documents aren't affected.
      </ConfirmDialog>
    </>
  );
}

function SharedChats({ onNavigate }: { onNavigate: () => void }) {
  const { shared } = useChats();
  const chatId = useLocation().pathname.match(/^\/app\/chat\/([^/]+)/)?.[1];
  if (!shared.length) return null;
  return (
    <>
      <p className="px-3 pb-1.5 pt-4 text-xs font-medium uppercase tracking-wide text-ink-400">Shared with you</p>
      <ul className="space-y-0.5">
        {shared.map((chat) => (
          <li key={chat.id}>
            <Link to={`/app/chat/${chat.id}`} onClick={onNavigate} title={chat.title}
              className={cx("block rounded-lg px-3 py-1.5 text-sm transition",
                chat.id === chatId ? "bg-ink-200/70 font-medium dark:bg-ink-800" : "text-ink-600 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800/60")}>
              <span className="block truncate">{chat.title}</span>
              <span className="block text-[11px] text-ink-400">{chat.owner_name} · {timeAgo(chat.updated_at)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  const options: [Theme, ReactNode, string][] = [
    ["light", <Sun key="l" className="h-3.5 w-3.5" />, "Light"],
    ["system", <Monitor key="s" className="h-3.5 w-3.5" />, "System"],
    ["dark", <Moon key="d" className="h-3.5 w-3.5" />, "Dark"],
  ];
  return (
    <div className="flex rounded-lg bg-ink-100 p-0.5 dark:bg-ink-800" role="radiogroup" aria-label="Theme">
      {options.map(([value, icon, label]) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          title={label}
          onClick={() => setTheme(value)}
          className={cx("flex flex-1 items-center justify-center gap-1 rounded-md py-1 text-xs transition",
            theme === value ? "bg-white shadow-sm dark:bg-ink-700" : "text-ink-500 hover:text-ink-800 dark:hover:text-ink-200")}
        >
          {icon}
        </button>
      ))}
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const { user } = useWorkspace();
  const { config, signOut } = useAuth();
  const navigate = useNavigate();
  const nav = [
    { to: "/app", label: "Ask", icon: MessageSquare, end: true },
    { to: "/app/library", label: "Library", icon: FolderOpen },
    { to: "/app/insights", label: "Insights", icon: BarChart3 },
    { to: "/app/settings", label: "Settings", icon: Settings },
  ];
  return (
    <div className="flex h-full flex-col gap-4 bg-ink-50 px-3 py-4 dark:bg-ink-950">
      <Link to="/app" onClick={onNavigate} className="px-1.5"><Logo /></Link>
      <WorkspaceSwitcher />
      <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { navigate("/app"); onNavigate(); }}>
        New chat
      </Button>
      <nav className="space-y-0.5" aria-label="Main">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) => cx(
              "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
              isActive ? "bg-white text-brand-800 shadow-sm ring-1 ring-ink-200 dark:bg-ink-900 dark:text-brand-300 dark:ring-ink-800" : "text-ink-600 hover:bg-ink-100 hover:text-ink-900 dark:text-ink-400 dark:hover:bg-ink-900 dark:hover:text-white",
            )}
          >
            <Icon className="h-4 w-4" /> {label}
          </NavLink>
        ))}
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="px-3 pb-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">Recent chats</p>
        <ChatList onNavigate={onNavigate} />
        <SharedChats onNavigate={onNavigate} />
      </div>
      <div className="space-y-3 border-t border-ink-200 pt-3 dark:border-ink-800">
        <ThemeSwitch />
        <div className="flex items-center gap-2.5 px-1">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-800 text-xs font-semibold text-white dark:bg-ink-200 dark:text-ink-900">
            {initials(user?.name ?? "", user?.email)}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{user?.name ?? "…"}</span>
            <span className="block truncate text-xs text-ink-500">{user?.email || "Local mode · no sign-in"}</span>
          </span>
          {config?.auth === "supabase" && (
            <IconButton label="Sign out" onClick={async () => { await signOut(); navigate("/"); }}>
              <LogOut className="h-4 w-4" />
            </IconButton>
          )}
        </div>
      </div>
    </div>
  );
}

export function AppLayout() {
  const { current, error } = useWorkspace();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [shared, setShared] = useState<ChatSummary[]>([]);
  const location = useLocation();

  const reloadChats = useCallback(() => {
    if (!current) return;
    api<{ chats: ChatSummary[]; shared: ChatSummary[] }>("/chats").then((r) => { setChats(r.chats); setShared(r.shared ?? []); }).catch(() => {});
  }, [current]);
  useEffect(reloadChats, [reloadChats]);
  useEffect(() => setMobileOpen(false), [location.pathname]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center">
        <div>
          <p className="font-semibold">Couldn't load your workspace</p>
          <p className="mt-1 text-sm text-ink-500">{error}</p>
          <Button className="mt-4" onClick={() => window.location.reload()}>Try again</Button>
        </div>
      </div>
    );
  }
  if (!current) {
    return <div className="flex min-h-screen items-center justify-center"><Spinner className="h-6 w-6" /></div>;
  }

  return (
    <ChatsContext.Provider value={{ chats, shared, reload: reloadChats }}>
      <div className="flex h-[100dvh] overflow-hidden">
        <aside className="hidden w-72 shrink-0 border-r border-ink-200 dark:border-ink-800 lg:block">
          <Sidebar onNavigate={() => {}} />
        </aside>
        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-ink-950/40" onClick={() => setMobileOpen(false)} />
            <aside className="absolute inset-y-0 left-0 w-80 max-w-[85%] animate-fade-in shadow-2xl">
              <Sidebar onNavigate={() => setMobileOpen(false)} />
              <IconButton label="Close menu" className="absolute right-3 top-4" onClick={() => setMobileOpen(false)}>
                <X className="h-4 w-4" />
              </IconButton>
            </aside>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center gap-3 border-b border-ink-200 px-4 dark:border-ink-800 lg:hidden">
            <IconButton label="Open menu" onClick={() => setMobileOpen(true)}>
              <Menu className="h-5 w-5" />
            </IconButton>
            <Logo />
            <span className="ml-auto truncate text-sm text-ink-500">{current.name}</span>
          </header>
          <main className="min-h-0 flex-1 overflow-y-auto">
            {/* Remount pages when the workspace changes, so nothing from the old one lingers. */}
            <Outlet key={current.id} />
          </main>
        </div>
      </div>
    </ChatsContext.Provider>
  );
}
