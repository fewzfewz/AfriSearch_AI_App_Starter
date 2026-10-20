// The signed-in app: sidebar (workspaces, navigation, chats, account), the page, and ⌘K.
import {
  BarChart3, Check, ChevronsUpDown, FolderOpen, LogOut, Menu, MessageSquare, Monitor, Moon, MoreHorizontal,
  PanelLeftClose, PanelLeftOpen, Pencil, Plus, Search, Settings, Shield, Sun, Trash2, Upload, Users, X,
} from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { FileIcon } from "../components/answer";
import { CommandPalette, isMac, type CommandItem } from "../components/command";
import { Button, ConfirmDialog, IconButton, Kbd, Logo, LogoMark, MenuItem, Modal, Popover, Spinner, cx, useToast } from "../components/ui";
import { api, openDocument } from "../lib/api";
import { useAuth } from "../lib/auth";
import { initials, timeAgo } from "../lib/format";
import { useStoredState } from "../lib/hooks";
import { useTheme, type Theme } from "../lib/theme";
import type { ChatSummary, DocumentsResponse } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

interface ChatsState {
  chats: ChatSummary[];
  shared: ChatSummary[]; // chats other members shared with this workspace
  reload: () => void;
}
const ChatsContext = createContext<ChatsState>({ chats: [], shared: [], reload: () => {} });
export const useChats = () => useContext(ChatsContext);

const NAV = [
  { to: "/app", label: "Ask", icon: MessageSquare, end: true },
  { to: "/app/library", label: "Library", icon: FolderOpen },
  { to: "/app/insights", label: "Insights", icon: BarChart3 },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

/** "Today", "Yesterday", "Previous 7 days", "Earlier": how chat lists are usually grouped. */
function dateGroup(iso: string): string {
  const day = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.floor((today.getTime() - new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "Previous 7 days";
  return "Earlier";
}

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
        className="w-full rounded-xl border border-ink-300 bg-transparent px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10 dark:border-ink-700"
      />
    </Modal>
  );
}

function WorkspaceAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cx("flex shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-amber-100 to-brand-200 text-xs font-bold text-brand-900 dark:from-brand-900 dark:to-brand-800 dark:text-brand-100", className)}>
      {initials(name)}
    </span>
  );
}

function WorkspaceSwitcher({ collapsed }: { collapsed: boolean }) {
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
          aria-label={`Workspace: ${current?.name ?? ""}. Switch workspace`}
          title={collapsed ? current?.name : undefined}
          className={cx(
            "flex w-full items-center gap-2.5 rounded-xl text-left transition",
            collapsed ? "justify-center p-1 hover:bg-ink-200/60 dark:hover:bg-ink-800" : "border border-ink-200/80 bg-white px-2.5 py-2 shadow-soft hover:border-ink-300 dark:border-ink-800 dark:bg-ink-900 dark:shadow-none dark:hover:border-ink-700",
          )}
        >
          <WorkspaceAvatar name={current?.name ?? ""} className="h-7 w-7" />
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">{current?.name ?? "…"}</span>
                <span className="block text-xs text-ink-500">{current?.role === "owner" ? "Your workspace" : "Shared with you"}</span>
              </span>
              <ChevronsUpDown className="h-4 w-4 shrink-0 text-ink-400" />
            </>
          )}
        </button>
      )}>
        {(close) => (
          <>
            <p className="px-2.5 pb-1 pt-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">Workspaces</p>
            {workspaces.map((w) => (
              <MenuItem
                key={w.id}
                icon={<WorkspaceAvatar name={w.name} className="h-6 w-6 text-[10px]" />}
                onClick={() => {
                  switchTo(w.id);
                  close();
                  navigate("/app");
                }}
                hint={w.id === current?.id ? <Check className="h-4 w-4 text-brand-700 dark:text-brand-400" /> : undefined}
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

function chatLinkClass(active: boolean) {
  return cx(
    "block rounded-lg py-1.5 pl-3 pr-8 text-sm transition",
    active
      ? "bg-white font-medium text-ink-900 shadow-soft ring-1 ring-ink-200/80 dark:bg-ink-800 dark:text-white dark:ring-ink-700 dark:shadow-none"
      : "text-ink-600 hover:bg-ink-200/50 hover:text-ink-900 dark:text-ink-400 dark:hover:bg-ink-800/60 dark:hover:text-ink-100",
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
  if (!chats.length) {
    return (
      <div className="mx-1 rounded-xl border border-dashed border-ink-200 px-3 py-4 text-center text-xs text-ink-400 dark:border-ink-800">
        Your conversations appear here.
      </div>
    );
  }
  const groups: [string, ChatSummary[]][] = [];
  for (const chat of chats) {
    const group = dateGroup(chat.updated_at);
    const last = groups[groups.length - 1];
    if (last && last[0] === group) last[1].push(chat);
    else groups.push([group, [chat]]);
  }
  return (
    <>
      {groups.map(([group, items]) => (
        <div key={group} className="pb-3">
          <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wide text-ink-400">{group}</p>
          <ul className="space-y-0.5">
            {items.map((chat) => (
              <li key={chat.id} className="group relative">
                <Link to={`/app/chat/${chat.id}`} onClick={onNavigate} className={chatLinkClass(chat.id === chatId)} title={chat.title}>
                  <span className="flex items-center gap-1.5">
                    {chat.shared ? <Users className="h-3 w-3 shrink-0 text-brand-600 dark:text-brand-400" aria-label="Shared" /> : null}
                    <span className="truncate">{chat.title}</span>
                  </span>
                </Link>
                <div className="absolute right-1 top-1 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
                  <Popover align="right" width="w-48" trigger={({ toggle }) => (
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
        </div>
      ))}
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
    <div className="pb-3">
      <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wide text-ink-400">Shared with you</p>
      <ul className="space-y-0.5">
        {shared.map((chat) => (
          <li key={chat.id}>
            <Link to={`/app/chat/${chat.id}`} onClick={onNavigate} title={chat.title} className={chatLinkClass(chat.id === chatId)}>
              <span className="block truncate">{chat.title}</span>
              <span className="block truncate text-[11px] text-ink-400">{chat.owner_name} · {timeAgo(chat.updated_at)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
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
          className={cx("flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-xs transition",
            theme === value ? "bg-white font-medium text-ink-900 shadow-sm dark:bg-ink-700 dark:text-white" : "text-ink-500 hover:text-ink-800 dark:hover:text-ink-200")}
        >
          {icon} {label}
        </button>
      ))}
    </div>
  );
}

function AccountMenu({ collapsed, onNavigate }: { collapsed: boolean; onNavigate: () => void }) {
  const { user } = useWorkspace();
  const { config, signOut } = useAuth();
  const navigate = useNavigate();
  const avatar = (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-ink-700 to-ink-900 text-xs font-semibold text-white ring-2 ring-white dark:from-ink-200 dark:to-ink-400 dark:text-ink-900 dark:ring-ink-950">
      {initials(user?.name ?? "", user?.email)}
    </span>
  );
  return (
    <Popover up width="w-64" trigger={({ open, toggle }) => (
      <button type="button" onClick={toggle} aria-expanded={open} aria-label="Account and appearance"
        className={cx("flex w-full items-center gap-2.5 rounded-xl p-1.5 text-left transition hover:bg-ink-200/60 dark:hover:bg-ink-800", collapsed && "justify-center")}>
        {avatar}
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{user?.name ?? "…"}</span>
              <span className="block truncate text-xs text-ink-500">{user?.email || "Local mode · no sign-in"}</span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-ink-400" />
          </>
        )}
      </button>
    )}>
      {(close) => (
        <>
          <div className="flex items-center gap-2.5 px-2.5 pb-2 pt-1.5">
            {avatar}
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold">{user?.name}</span>
              <span className="block truncate text-xs text-ink-500">{user?.email || "Local mode"}</span>
            </span>
          </div>
          <div className="px-1.5 pb-1.5"><ThemeSwitch /></div>
          <div className="my-1 border-t border-ink-100 dark:border-ink-800" />
          <MenuItem icon={<Settings className="h-4 w-4" />} onClick={() => { close(); onNavigate(); navigate("/app/settings"); }}>Settings</MenuItem>
          <MenuItem icon={<Shield className="h-4 w-4" />} onClick={() => { close(); navigate("/privacy"); }}>Privacy</MenuItem>
          {config?.auth === "supabase" && (
            <MenuItem icon={<LogOut className="h-4 w-4" />} onClick={async () => { close(); await signOut(); navigate("/"); }}>Sign out</MenuItem>
          )}
        </>
      )}
    </Popover>
  );
}

function Sidebar({ onNavigate, collapsed, onToggle, onSearch }: {
  onNavigate: () => void;
  collapsed: boolean;
  onToggle?: () => void;
  onSearch: () => void;
}) {
  const navigate = useNavigate();
  return (
    <div className={cx("flex h-full flex-col gap-3 bg-ink-50 py-3 dark:bg-ink-950", collapsed ? "items-center px-2" : "px-3")}>
      <div className={cx("flex items-center", collapsed ? "flex-col gap-2" : "justify-between pl-1.5")}>
        <Link to="/app" onClick={onNavigate} aria-label="AfriSearch home">{collapsed ? <LogoMark className="h-8 w-8" /> : <Logo />}</Link>
        {onToggle && (
          <IconButton label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={onToggle}>
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </IconButton>
        )}
      </div>
      <WorkspaceSwitcher collapsed={collapsed} />
      <div className={cx("flex gap-2", collapsed && "flex-col")}>
        <Button variant="primary" className={cx(collapsed ? "h-10 w-10 px-0" : "flex-1")} icon={<Plus className="h-4 w-4" />}
          aria-label="New chat" title="New chat" onClick={() => { navigate("/app"); onNavigate(); }}>
          {!collapsed && "New chat"}
        </Button>
        <button type="button" onClick={onSearch} aria-label="Search and commands" title={`Search (${isMac ? "⌘" : "Ctrl+"}K)`}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-ink-200/80 bg-white text-ink-500 shadow-soft transition hover:text-ink-900 dark:border-ink-800 dark:bg-ink-900 dark:shadow-none dark:hover:text-white">
          <Search className="h-4 w-4" />
        </button>
      </div>
      <nav className={cx("space-y-0.5", collapsed && "flex flex-col items-center")} aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            className={({ isActive }) => cx(
              "relative flex items-center gap-2.5 rounded-lg text-sm font-medium transition",
              collapsed ? "h-10 w-10 justify-center" : "px-3 py-2",
              isActive
                ? "bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/80 dark:bg-ink-900 dark:text-white dark:ring-ink-800 dark:shadow-none"
                : "text-ink-600 hover:bg-ink-200/50 hover:text-ink-900 dark:text-ink-400 dark:hover:bg-ink-900 dark:hover:text-white",
            )}
          >
            {({ isActive }) => (
              <>
                <Icon className={cx("h-4 w-4", isActive && "text-brand-600 dark:text-brand-400")} />
                {!collapsed && label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      {collapsed ? <div className="flex-1" /> : (
        <div className="-mx-1 min-h-0 flex-1 overflow-y-auto border-t border-ink-200/70 px-1 pt-3 dark:border-ink-800">
          <ChatList onNavigate={onNavigate} />
          <SharedChats onNavigate={onNavigate} />
        </div>
      )}
      <div className={cx("border-t border-ink-200/70 pt-2 dark:border-ink-800", collapsed && "w-full")}>
        <AccountMenu collapsed={collapsed} onNavigate={onNavigate} />
      </div>
    </div>
  );
}

function useCommands(chats: ChatSummary[], shared: ChatSummary[], open: boolean): CommandItem[] {
  const navigate = useNavigate();
  const toast = useToast();
  const [, setTheme] = useTheme();
  const [documents, setDocuments] = useState<DocumentsResponse["documents"]>([]);
  useEffect(() => {
    if (open) api<DocumentsResponse>("/documents").then((r) => setDocuments(r.documents)).catch(() => {});
  }, [open]);
  return useMemo(() => {
    const icon = (Icon: typeof Plus) => <Icon className="h-4 w-4" />;
    return [
      { id: "new", group: "Actions", label: "New chat", icon: icon(Plus), keywords: "ask question", run: () => navigate("/app") },
      { id: "upload", group: "Actions", label: "Upload documents", icon: icon(Upload), keywords: "add files", run: () => navigate("/app/library") },
      { id: "light", group: "Actions", label: "Switch to light theme", icon: icon(Sun), keywords: "appearance", run: () => setTheme("light") },
      { id: "dark", group: "Actions", label: "Switch to dark theme", icon: icon(Moon), keywords: "appearance", run: () => setTheme("dark") },
      ...NAV.map(({ to, label, icon: Icon }) => ({ id: to, group: "Go to", label, icon: <Icon className="h-4 w-4" />, run: () => navigate(to) })),
      ...[...chats, ...shared].map((chat) => ({
        id: `chat-${chat.id}`, group: "Chats", label: chat.title, hint: timeAgo(chat.updated_at),
        icon: icon(MessageSquare), run: () => navigate(`/app/chat/${chat.id}`),
      })),
      ...documents.map((doc) => ({
        id: `doc-${doc.source_id}`, group: "Documents", label: doc.source_name, hint: "Open",
        icon: <FileIcon name={doc.source_name} />, keywords: "document file",
        run: () => { openDocument(doc.source_id).catch((e: Error) => toast(e.message, "error")); },
      })),
    ];
  }, [chats, shared, documents, navigate, setTheme, toast]);
}

export function AppLayout() {
  const { current, error } = useWorkspace();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useStoredState("afrisearch.sidebar-collapsed", false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [shared, setShared] = useState<ChatSummary[]>([]);
  const location = useLocation();
  const commands = useCommands(chats, shared, paletteOpen);

  const reloadChats = useCallback(() => {
    if (!current) return;
    api<{ chats: ChatSummary[]; shared: ChatSummary[] }>("/chats").then((r) => { setChats(r.chats); setShared(r.shared ?? []); }).catch(() => {});
  }, [current]);
  useEffect(reloadChats, [reloadChats]);
  useEffect(() => setMobileOpen(false), [location.pathname]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

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
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <LogoMark className="h-10 w-10 animate-pulse" />
        <Spinner className="h-5 w-5" />
      </div>
    );
  }

  return (
    <ChatsContext.Provider value={{ chats, shared, reload: reloadChats }}>
      <div className="flex h-[100dvh] overflow-hidden bg-ink-50 dark:bg-ink-950">
        <aside className={cx("hidden shrink-0 transition-[width] duration-200 lg:block", collapsed ? "w-[68px]" : "w-72")}>
          <Sidebar onNavigate={() => {}} collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} onSearch={() => setPaletteOpen(true)} />
        </aside>
        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 animate-fade-in bg-ink-950/40 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
            <aside className="absolute inset-y-0 left-0 w-80 max-w-[85%] animate-slide-in shadow-2xl">
              <Sidebar onNavigate={() => setMobileOpen(false)} collapsed={false} onSearch={() => { setMobileOpen(false); setPaletteOpen(true); }} />
              <IconButton label="Close menu" className="absolute right-3 top-3" onClick={() => setMobileOpen(false)}>
                <X className="h-4 w-4" />
              </IconButton>
            </aside>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col lg:py-2 lg:pr-2">
          <header className="flex h-14 shrink-0 items-center gap-2 border-b border-ink-200/70 bg-ink-50 px-3 dark:border-ink-800 dark:bg-ink-950 lg:hidden">
            <IconButton label="Open menu" onClick={() => setMobileOpen(true)}>
              <Menu className="h-5 w-5" />
            </IconButton>
            <Link to="/app" aria-label="AfriSearch home"><Logo /></Link>
            <span className="ml-auto max-w-[9rem] truncate text-sm text-ink-500">{current.name}</span>
            <IconButton label="Search and commands" onClick={() => setPaletteOpen(true)}>
              <Search className="h-4 w-4" />
            </IconButton>
          </header>
          {/* The page sits on a raised panel next to the sidebar. */}
          <main className="relative min-h-0 flex-1 overflow-y-auto bg-white dark:bg-ink-900/40 lg:rounded-2xl lg:border lg:border-ink-200/80 lg:shadow-soft dark:lg:border-ink-800 dark:lg:shadow-none">
            {/* Remount pages when the workspace changes, so nothing from the old one lingers. */}
            <Outlet key={current.id} />
          </main>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} items={commands} />
    </ChatsContext.Provider>
  );
}

export function ShortcutHint() {
  return <span className="inline-flex items-center gap-0.5"><Kbd>{isMac ? "⌘" : "Ctrl"}</Kbd><Kbd>K</Kbd></span>;
}
