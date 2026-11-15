// Workspace, team, appearance and account settings.
import {
  AlertTriangle, Building2, Check, Copy, Cpu, CreditCard, Download, FolderOpen, Info, Key, LogOut, Monitor, Moon, Palette, Settings, Sparkles, Sun, Trash2, UserPlus, UserRound, Users,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card, ConfirmDialog, Modal, PageHeader, cx, useToast } from "../components/ui";
import { api, createOrganizationAPIKey, deleteOrganizationAIKey, deleteOrganizationAPIKey, downloadFile, setOrganizationAIKey } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatSize, initials, shortModelName } from "../lib/format";
import { useApi } from "../lib/hooks";
import { useTheme } from "../lib/theme";
import type { CheckoutResponse, DeveloperApiKey, DocumentsResponse, InvoicesResponse, Member, OrganizationUsageResponse } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

interface Team {
  members: Member[];
  invitations: { email: string; created_at: string }[];
}

const SECTIONS = [
  { id: "organization", title: "Organization", icon: Building2 },
  { id: "ai_keys", title: "AI Model Keys (BYOK)", icon: Cpu },
  { id: "api_keys", title: "Developer API Keys", icon: Key },
  { id: "workspace", title: "Workspace", icon: FolderOpen },
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
  const { current, organizations, currentOrganization, workspaces, user, reload, switchOrganization, switchTo } = useWorkspace();
  const { config, signOut } = useAuth();
  const [theme, setTheme] = useTheme();
  const toast = useToast();
  const navigate = useNavigate();
  const isOwner = current?.role === "owner";
  const isWsAdmin = current?.role === "owner" || current?.role === "admin";
  const isOrgOwner = currentOrganization?.role === "owner" || currentOrganization?.owner_id === user?.id;
  const [name, setName] = useState(current?.name ?? "");
  const [orgName, setOrgName] = useState(currentOrganization?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [savingOrg, setSavingOrg] = useState(false);
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "member" | "viewer">("member");
  const [inviting, setInviting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmName, setConfirmName] = useState("");
  const [deleteOrgOpen, setDeleteOrgOpen] = useState(false);
  const [confirmOrgName, setConfirmOrgName] = useState("");
  const [exporting, setExporting] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [confirmAccount, setConfirmAccount] = useState("");

  useEffect(() => {
    if (current?.name) setName(current.name);
  }, [current?.name]);

  useEffect(() => {
    if (currentOrganization?.name) setOrgName(currentOrganization.name);
  }, [currentOrganization?.name]);

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
  const orgUsage = useApi<OrganizationUsageResponse>(currentOrganization ? `/organizations/${currentOrganization.id}/usage` : null);
  const invoices = useApi<InvoicesResponse>(currentOrganization ? `/organizations/${currentOrganization.id}/invoices` : null);
  const aiKeysApi = useApi<{ keys: Record<string, string> }>(
    currentOrganization ? `/organizations/${currentOrganization.id}/ai-keys` : null
  );
  const [editingProvider, setEditingProvider] = useState<"openai" | "claude" | "gemini" | null>(null);
  const [newAiKey, setNewAiKey] = useState("");
  const [savingAiKey, setSavingAiKey] = useState(false);

  const devKeysApi = useApi<{ api_keys: DeveloperApiKey[] }>(
    currentOrganization ? `/organizations/${currentOrganization.id}/api-keys` : null
  );
  const [createKeyModal, setCreateKeyModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyWorkspace, setNewKeyWorkspace] = useState<string>("");
  const [creatingKey, setCreatingKey] = useState(false);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);
  const [secretCopied, setSecretCopied] = useState(false);
  const [revokingKey, setRevokingKey] = useState<DeveloperApiKey | null>(null);
  const [revoking, setRevoking] = useState(false);

  const handleSaveAiKey = async () => {
    if (!currentOrganization || !editingProvider || !newAiKey.trim()) return;
    setSavingAiKey(true);
    const providerToActivate = editingProvider === "openai" ? "chatgpt" : editingProvider;
    try {
      await setOrganizationAIKey(currentOrganization.id, editingProvider, newAiKey.trim());
      await aiKeysApi.reload();
      try {
        const stored = JSON.parse(localStorage.getItem("afrisearch.answer-settings") || "{}");
        localStorage.setItem(
          "afrisearch.answer-settings",
          JSON.stringify({ ...stored, provider: providerToActivate, mode: "answer" })
        );
      } catch {
        // ignore storage errors
      }
      window.dispatchEvent(new Event("afrisearch:providers-updated"));
      setEditingProvider(null);
      setNewAiKey("");
      toast("AI provider key saved successfully. Enabled for Ask & Search!", "success");
    } catch (e: any) {
      toast(e.message || "Failed to save AI key", "error");
    } finally {
      setSavingAiKey(false);
    }
  };

  const handleDeleteAiKey = async (provider: "openai" | "claude" | "gemini") => {
    if (!currentOrganization) return;
    try {
      await deleteOrganizationAIKey(currentOrganization.id, provider);
      await aiKeysApi.reload();
      window.dispatchEvent(new Event("afrisearch:providers-updated"));
      toast("AI provider key removed. Now using platform default", "success");
    } catch (e: any) {
      toast(e.message || "Failed to remove key", "error");
    }
  };

  const handleCreateDevKey = async () => {
    if (!currentOrganization || !newKeyName.trim()) return;
    setCreatingKey(true);
    try {
      const res = await createOrganizationAPIKey(
        currentOrganization.id,
        newKeyName.trim(),
        newKeyWorkspace || null
      );
      await devKeysApi.reload();
      setNewKeyName("");
      setNewKeyWorkspace("");
      setCreateKeyModal(false);
      setCreatedSecret(res.secret);
      toast("Developer API key generated", "success");
    } catch (e: any) {
      toast(e.message || "Failed to create API key", "error");
    } finally {
      setCreatingKey(false);
    }
  };

  const handleRevokeDevKey = async () => {
    if (!currentOrganization || !revokingKey) return;
    setRevoking(true);
    try {
      await deleteOrganizationAPIKey(currentOrganization.id, revokingKey.id);
      await devKeysApi.reload();
      setRevokingKey(null);
      toast("API key revoked", "success");
    } catch (e: any) {
      toast(e.message || "Failed to revoke key", "error");
    } finally {
      setRevoking(false);
    }
  };

  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<"pro" | "business">("pro");
  const [selectedProvider, setSelectedProvider] = useState<"stripe" | "chapa">("stripe");
  const [checkingOut, setCheckingOut] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  const handleCheckout = async () => {
    if (!currentOrganization) return;
    setCheckingOut(true);
    try {
      const res = await api<CheckoutResponse>(`/organizations/${currentOrganization.id}/checkout`, {
        method: "POST",
        json: {
          plan_id: selectedPlan,
          provider: selectedProvider,
          currency: selectedProvider === "chapa" ? "ETB" : "USD",
          seats: 1,
        },
      });
      if (res.checkout_url) {
        if (res.is_mock) {
          toast(`Simulation checkout completed for ${selectedPlan.toUpperCase()} plan.`);
          setUpgradeOpen(false);
          orgUsage.reload();
          invoices.reload();
        } else {
          window.location.href = res.checkout_url;
        }
      }
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setCheckingOut(false);
    }
  };

  const handlePortal = async () => {
    if (!currentOrganization) return;
    setPortalLoading(true);
    try {
      const res = await api<{ portal_url: string }>(`/organizations/${currentOrganization.id}/billing-portal`, {
        method: "POST",
      });
      if (res.portal_url) {
        window.location.href = res.portal_url;
      }
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setPortalLoading(false);
    }
  };
  const multiUser = config?.auth === "supabase";

  const renameOrg = async () => {
    if (!currentOrganization) return;
    setSavingOrg(true);
    try {
      await api(`/organizations/${currentOrganization.id}`, { method: "PATCH", json: { name: orgName.trim() } });
      await reload();
      toast("Organization renamed");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSavingOrg(false);
    }
  };

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
      const result = await api<Team & { message: string }>(`/workspaces/${current!.id}/members`, {
        json: { email: email.trim(), role: inviteRole },
      });
      members.setData(result);
      setEmail("");
      toast(result.message);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setInviting(false);
    }
  };

  const updateMemberRole = async (member: Member, role: "admin" | "member" | "viewer") => {
    try {
      const result = await api<Team>(`/workspaces/${current!.id}/members/${member.id}`, {
        method: "PATCH",
        json: { role },
      });
      members.setData(result);
      toast(`Updated ${member.name || member.email} to ${role}`);
    } catch (e) {
      toast((e as Error).message, "error");
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
            {SECTIONS.filter((s) => s.id !== "danger" || isOwner || isOrgOwner).map(({ id, title, icon: Icon }) => (
              <li key={id}>
                <a href={`#${id}`} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-ink-600 transition hover:bg-ink-100 hover:text-ink-900 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-white">
                  <Icon className="h-4 w-4" /> {title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="space-y-5">
        {currentOrganization && (
          <Section id="organization" description="An organization represents your team or company, subscription plan, and workspaces.">
            <div className="space-y-6">
              <div>
                <label htmlFor="org-name" className="text-sm font-medium">Organization name</label>
                <div className="mt-1.5 flex gap-2">
                  <input
                    id="org-name"
                    value={orgName}
                    maxLength={80}
                    disabled={!isOrgOwner}
                    onChange={(e) => setOrgName(e.target.value)}
                    className={inputClass}
                  />
                  <Button
                    variant="primary"
                    loading={savingOrg}
                    disabled={!isOrgOwner || !orgName.trim() || orgName.trim() === currentOrganization.name}
                    onClick={renameOrg}
                  >
                    Save
                  </Button>
                </div>
                {!isOrgOwner && <p className="mt-2 text-xs text-ink-500">Only the organization owner can rename this organization.</p>}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-ink-200/80 p-4 dark:border-ink-800">
                <div className="flex items-center gap-3">
                  <div>
                    <p className="text-xs text-ink-500">Active Plan</p>
                    <p className="text-base font-semibold text-ink-900 dark:text-white">
                      {orgUsage.data?.plan.name ?? "Free Tier"}
                    </p>
                  </div>
                  <Badge tone={orgUsage.data?.plan.id === "free" ? "gray" : "brand"}>
                    {orgUsage.data?.plan.id?.toUpperCase() ?? "FREE"}
                  </Badge>
                </div>
                <div className="flex items-center gap-3">
                  {isOrgOwner && (
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="primary" onClick={() => setUpgradeOpen((v) => !v)}>
                        <CreditCard className="mr-1.5 h-3.5 w-3.5" />
                        {orgUsage.data?.plan.id === "free" ? "Upgrade Plan" : "Change Plan"}
                      </Button>
                      {orgUsage.data?.plan.id !== "free" && (
                        <Button size="sm" variant="ghost" loading={portalLoading} onClick={handlePortal}>
                          Billing Portal
                        </Button>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-ink-500">Your role:</span>
                    <Badge tone={isOrgOwner ? "brand" : "gray"}>{currentOrganization.role}</Badge>
                  </div>
                </div>
              </div>

              {upgradeOpen && (
                <div className="rounded-xl border border-brand-500/30 bg-brand-50/50 p-4 dark:border-brand-500/20 dark:bg-brand-950/20">
                  <div className="mb-3 flex items-center justify-between">
                    <h4 className="flex items-center gap-1.5 text-sm font-semibold text-ink-900 dark:text-white">
                      <CreditCard className="h-4 w-4 text-brand-600" />
                      Select Plan & Payment Gateway
                    </h4>
                    <button
                      type="button"
                      onClick={() => setUpgradeOpen(false)}
                      className="text-xs text-ink-400 hover:text-ink-600 dark:hover:text-ink-200"
                    >
                      Cancel
                    </button>
                  </div>

                  <div className="mb-4 grid gap-3 sm:grid-cols-2">
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedPlan("pro")}
                      onKeyDown={(e) => e.key === "Enter" && setSelectedPlan("pro")}
                      className={cx(
                        "cursor-pointer rounded-xl border p-3 transition-all",
                        selectedPlan === "pro"
                          ? "border-brand-500 bg-white shadow-sm dark:bg-ink-900"
                          : "border-ink-200 bg-white/60 hover:border-ink-300 dark:border-ink-800 dark:bg-ink-900/60"
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-ink-900 dark:text-white">Pro Tier</span>
                        <span className="text-sm font-bold text-brand-600 dark:text-brand-400">
                          {selectedProvider === "chapa" ? "3,500 ETB / mo" : "$29 / mo"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-ink-500">
                        10 Workspaces, 15 Seats, 10 GB Storage, 1,500 monthly queries, Claude 3.5 & GPT-4o models.
                      </p>
                    </div>

                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedPlan("business")}
                      onKeyDown={(e) => e.key === "Enter" && setSelectedPlan("business")}
                      className={cx(
                        "cursor-pointer rounded-xl border p-3 transition-all",
                        selectedPlan === "business"
                          ? "border-brand-500 bg-white shadow-sm dark:bg-ink-900"
                          : "border-ink-200 bg-white/60 hover:border-ink-300 dark:border-ink-800 dark:bg-ink-900/60"
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-ink-900 dark:text-white">Business Tier</span>
                        <span className="text-sm font-bold text-brand-600 dark:text-brand-400">
                          {selectedProvider === "chapa" ? "18,000 ETB / mo" : "$149 / mo"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-ink-500">
                        Unlimited Workspaces, 50 Seats, 100 GB Storage, 10,000 monthly queries, all premium AI models.
                      </p>
                    </div>
                  </div>

                  <div className="mb-4">
                    <label className="mb-1.5 block text-xs font-medium text-ink-600 dark:text-ink-300">
                      Payment Rail
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedProvider("stripe")}
                        className={cx(
                          "rounded-lg border px-3 py-2 text-left text-xs font-medium transition-all",
                          selectedProvider === "stripe"
                            ? "border-brand-500 bg-brand-500 text-white"
                            : "border-ink-300 bg-white text-ink-700 hover:bg-ink-50 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-200"
                        )}
                      >
                        <p className="font-semibold">Credit Card / Global</p>
                        <p className="opacity-80">Stripe (USD)</p>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSelectedProvider("chapa")}
                        className={cx(
                          "rounded-lg border px-3 py-2 text-left text-xs font-medium transition-all",
                          selectedProvider === "chapa"
                            ? "border-brand-500 bg-brand-500 text-white"
                            : "border-ink-300 bg-white text-ink-700 hover:bg-ink-50 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-200"
                        )}
                      >
                        <p className="font-semibold">African Rails / Ethiopia</p>
                        <p className="opacity-80">Telebirr, CBE Birr (Chapa ETB)</p>
                      </button>
                    </div>
                  </div>

                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setUpgradeOpen(false)}>
                      Cancel
                    </Button>
                    <Button variant="primary" size="sm" loading={checkingOut} onClick={handleCheckout}>
                      Checkout with {selectedProvider === "stripe" ? "Stripe" : "Chapa"}
                    </Button>
                  </div>
                </div>
              )}

              {orgUsage.data && (
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Usage & Quotas</h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-ink-200/80 p-3.5 dark:border-ink-800">
                      <div className="flex justify-between text-xs">
                        <span className="text-ink-500">Workspaces</span>
                        <span className="font-medium text-ink-900 dark:text-white">
                          {orgUsage.data.usage.workspace_count} / {orgUsage.data.limits.max_workspaces > 1000 ? "Unlimited" : orgUsage.data.limits.max_workspaces}
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                        <div
                          className="h-full bg-brand-500 transition-all"
                          style={{
                            width: `${Math.min(100, (orgUsage.data.usage.workspace_count / Math.max(1, orgUsage.data.limits.max_workspaces)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>

                    <div className="rounded-xl border border-ink-200/80 p-3.5 dark:border-ink-800">
                      <div className="flex justify-between text-xs">
                        <span className="text-ink-500">Team Seats</span>
                        <span className="font-medium text-ink-900 dark:text-white">
                          {orgUsage.data.usage.seats_used} / {orgUsage.data.limits.max_seats > 1000 ? "Unlimited" : orgUsage.data.limits.max_seats}
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                        <div
                          className="h-full bg-brand-500 transition-all"
                          style={{
                            width: `${Math.min(100, (orgUsage.data.usage.seats_used / Math.max(1, orgUsage.data.limits.max_seats)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>

                    <div className="rounded-xl border border-ink-200/80 p-3.5 dark:border-ink-800">
                      <div className="flex justify-between text-xs">
                        <span className="text-ink-500">Storage</span>
                        <span className="font-medium text-ink-900 dark:text-white">
                          {formatSize(orgUsage.data.usage.storage_bytes)} / {formatSize(orgUsage.data.limits.max_storage_bytes)}
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                        <div
                          className="h-full bg-brand-500 transition-all"
                          style={{
                            width: `${Math.min(100, (orgUsage.data.usage.storage_bytes / Math.max(1, orgUsage.data.limits.max_storage_bytes)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>

                    <div className="rounded-xl border border-ink-200/80 p-3.5 dark:border-ink-800">
                      <div className="flex justify-between text-xs">
                        <span className="text-ink-500">Total Documents</span>
                        <span className="font-medium text-ink-900 dark:text-white">
                          {orgUsage.data.usage.document_count} / {orgUsage.data.limits.max_documents}
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                        <div
                          className="h-full bg-brand-500 transition-all"
                          style={{
                            width: `${Math.min(100, (orgUsage.data.usage.document_count / Math.max(1, orgUsage.data.limits.max_documents)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>

                    <div className="rounded-xl border border-ink-200/80 p-3.5 dark:border-ink-800 sm:col-span-2">
                      <div className="flex justify-between text-xs">
                        <span className="text-ink-500">Monthly AI Questions</span>
                        <span className="font-medium text-ink-900 dark:text-white">
                          {orgUsage.data.usage.questions_count} / {orgUsage.data.limits.max_queries_per_month}
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                        <div
                          className="h-full bg-brand-500 transition-all"
                          style={{
                            width: `${Math.min(100, (orgUsage.data.usage.questions_count / Math.max(1, orgUsage.data.limits.max_queries_per_month)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {invoices.data?.invoices && invoices.data.invoices.length > 0 && (
                <div className="space-y-2 pt-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-500">Billing History & Invoices</h4>
                  <div className="divide-y divide-ink-100 overflow-hidden rounded-xl border border-ink-200/80 dark:divide-ink-800 dark:border-ink-800">
                    {invoices.data.invoices.map((inv) => (
                      <div key={inv.id} className="flex items-center justify-between px-4 py-2.5 text-xs">
                        <div>
                          <p className="font-medium text-ink-900 dark:text-white">
                            {inv.currency} {(inv.amount_cents / 100).toFixed(2)}
                          </p>
                          <p className="text-[11px] text-ink-500">
                            {new Date(inv.created_at).toLocaleDateString()} • {inv.provider.toUpperCase()}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge tone={inv.status === "paid" ? "green" : "gray"}>{inv.status}</Badge>
                          {(inv.hosted_invoice_url || inv.pdf_url) && (
                            <a
                              href={inv.hosted_invoice_url || inv.pdf_url || "#"}
                              target="_blank"
                              rel="noreferrer"
                              className="text-brand-600 hover:underline"
                            >
                              Download
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Section>
        )}

        {currentOrganization && (
          <Section
            id="ai_keys"
            description="Bring your own AI provider keys (BYOK). Keys are encrypted at rest with Fernet and decrypted only in memory during requests. If not set, requests automatically use AfriSearch's hosted models."
          >
            <div className="space-y-4">
              <div className="rounded-xl border border-brand-200/80 bg-brand-50/40 p-4 text-xs text-brand-900 dark:border-brand-900/50 dark:bg-brand-950/30 dark:text-brand-200">
                <div className="flex items-start gap-2">
                  <Sparkles className="h-4 w-4 shrink-0 text-brand-600 mt-0.5" />
                  <div>
                    <strong className="font-semibold">Hosted Models vs Custom Keys:</strong> Paid plans include hosted model inference out of the box with zero setup required. Adding your own key is optional and recommended if your company has enterprise credits with OpenAI, Anthropic, or Google.
                  </div>
                </div>
              </div>

              <div className="divide-y divide-ink-100 rounded-xl border border-ink-200/80 dark:divide-ink-800 dark:border-ink-800 overflow-hidden">
                {[
                  { id: "openai", name: "OpenAI", desc: "GPT-4o, GPT-4o-mini", prefix: "sk-proj- / sk-" },
                  { id: "claude", name: "Anthropic Claude", desc: "Claude 3.5 Sonnet, Claude 3 Opus", prefix: "sk-ant-" },
                  { id: "gemini", name: "Google Gemini", desc: "Gemini 1.5 Pro, Gemini 1.5 Flash", prefix: "AIzaSy..." },
                ].map((item) => {
                  const existingKeyHint = aiKeysApi.data?.keys?.[item.id];
                  const isEditing = editingProvider === item.id;

                  return (
                    <div key={item.id} className="p-4 sm:p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink-100 dark:bg-ink-800 text-ink-700 dark:text-ink-300 font-bold">
                            <Cpu className="h-5 w-5" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="font-semibold text-sm text-ink-900 dark:text-white">{item.name}</h4>
                              <Badge tone={existingKeyHint ? "green" : "gray"}>
                                {existingKeyHint ? "Custom Key Active" : "Default (Hosted Model)"}
                              </Badge>
                            </div>
                            <p className="text-xs text-ink-500 mt-0.5">{item.desc}</p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {existingKeyHint ? (
                            <>
                              <code className="text-xs font-mono bg-ink-100 dark:bg-ink-800 px-2 py-1 rounded text-ink-600 dark:text-ink-300">
                                {existingKeyHint}
                              </code>
                              {isOrgOwner && (
                                <>
                                  <Button size="sm" variant="secondary" onClick={() => { setEditingProvider(item.id as any); setNewAiKey(""); }}>
                                    Update
                                  </Button>
                                  <Button size="sm" variant="ghost" className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/50" onClick={() => handleDeleteAiKey(item.id as any)}>
                                    Remove
                                  </Button>
                                </>
                              )}
                            </>
                          ) : (
                            isOrgOwner && (
                              <Button size="sm" variant="secondary" onClick={() => { setEditingProvider(item.id as any); setNewAiKey(""); }}>
                                Add Key
                              </Button>
                            )
                          )}
                        </div>
                      </div>

                      {isEditing && (
                        <div className="mt-4 rounded-xl border border-ink-200 bg-ink-50/60 p-3.5 dark:border-ink-800 dark:bg-ink-950/60">
                          <label className="block text-xs font-medium text-ink-700 dark:text-ink-300 mb-1.5">
                            Enter your {item.name} API Key ({item.prefix})
                          </label>
                          <div className="flex gap-2">
                            <input
                              type="password"
                              value={newAiKey}
                              placeholder={`${item.prefix}...`}
                              onChange={(e) => setNewAiKey(e.target.value)}
                              className={inputClass}
                            />
                            <Button variant="primary" loading={savingAiKey} disabled={!newAiKey.trim()} onClick={handleSaveAiKey}>
                              Save Encrypted
                            </Button>
                            <Button variant="ghost" onClick={() => setEditingProvider(null)}>
                              Cancel
                            </Button>
                          </div>
                          <p className="mt-2 text-[11px] text-ink-500">
                            Your API key is never logged or exposed. It is encrypted in SQLite using Fernet symmetric encryption with a private machine key.
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </Section>
        )}

        {currentOrganization && (
          <Section
            id="api_keys"
            description="Manage live programmatic API keys to integrate AfriSearch with customer support widgets, mobile apps, or backend pipelines."
          >
            <div className="space-y-6">
              {orgUsage.data?.plan.id === "free" ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-6 dark:border-amber-900/60 dark:bg-amber-950/30">
                  <div className="flex items-start gap-3">
                    <Key className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5" />
                    <div>
                      <h4 className="font-semibold text-ink-950 dark:text-white text-base">
                        Developer API is a Professional Feature
                      </h4>
                      <p className="mt-1 text-sm text-ink-600 dark:text-ink-300 leading-relaxed">
                        Generate live keys (<code className="text-xs bg-amber-100 dark:bg-amber-900/60 px-1 rounded">afri_live_*</code>) to query semantic document search and citation-backed question answering from your custom client apps or embeddable support widgets.
                      </p>
                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <Button size="sm" variant="primary" onClick={() => setUpgradeOpen(true)}>
                          Upgrade to Pro to Enable API
                        </Button>
                        <Link to="/developers" className="text-xs font-semibold text-brand-700 dark:text-brand-400 hover:underline">
                          Read Developer Documentation →
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  {createdSecret && (
                    <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-950/50">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-1.5 font-bold text-sm text-emerald-900 dark:text-emerald-200">
                            <Check className="h-4 w-4" /> New Developer API Key Generated
                          </div>
                          <p className="mt-1 text-xs text-emerald-800 dark:text-emerald-300">
                            Copy this secret now. For security, it will never be displayed again.
                          </p>
                          <div className="mt-3 flex items-center gap-2">
                            <code className="rounded bg-white dark:bg-ink-900 px-3 py-1.5 font-mono text-xs font-bold text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 select-all">
                              {createdSecret}
                            </code>
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => {
                                navigator.clipboard.writeText(createdSecret);
                                setSecretCopied(true);
                                setTimeout(() => setSecretCopied(false), 2000);
                              }}
                            >
                              {secretCopied ? <Check className="h-3.5 w-3.5 text-emerald-600 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
                              {secretCopied ? "Copied" : "Copy Secret"}
                            </Button>
                          </div>
                        </div>
                        <Button size="sm" variant="ghost" onClick={() => setCreatedSecret(null)}>
                          Dismiss
                        </Button>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-semibold text-sm text-ink-900 dark:text-white">Active API Keys</h4>
                      <p className="text-xs text-ink-500">Live tokens authorized to query your organization's workspaces.</p>
                    </div>
                    {isOrgOwner && (
                      <Button size="sm" variant="primary" onClick={() => setCreateKeyModal(true)}>
                        <Key className="mr-1.5 h-3.5 w-3.5" /> Generate Key
                      </Button>
                    )}
                  </div>

                  <div className="divide-y divide-ink-100 overflow-hidden rounded-xl border border-ink-200/80 dark:divide-ink-800 dark:border-ink-800">
                    {(devKeysApi.data?.api_keys ?? []).length === 0 ? (
                      <div className="p-8 text-center text-sm text-ink-500">
                        No developer API keys created yet. Generate one to integrate with customer support widgets or your backend.
                      </div>
                    ) : (
                      (devKeysApi.data?.api_keys ?? []).map((k) => (
                        <div key={k.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 text-xs">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-ink-900 dark:text-white text-sm">{k.name}</span>
                              <code className="font-mono bg-ink-100 dark:bg-ink-800 px-1.5 py-0.5 rounded text-ink-600 dark:text-ink-400">
                                {k.key_prefix}
                              </code>
                            </div>
                            <div className="mt-1 flex items-center gap-3 text-ink-500 text-[11px]">
                              <span>Created {new Date(k.created_at).toLocaleDateString()}</span>
                              <span>•</span>
                              <span>Scope: {k.workspace_id ? (workspaces.find((w) => w.id === k.workspace_id)?.name || "Specific workspace") : "All workspaces"}</span>
                              <span>•</span>
                              <span>Last used: {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "Never"}</span>
                            </div>
                          </div>

                          {isOrgOwner && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/50"
                              onClick={() => setRevokingKey(k)}
                            >
                              Revoke
                            </Button>
                          )}
                        </div>
                      ))
                    )}
                  </div>

                  <div className="pt-2 flex items-center justify-between text-xs text-ink-500">
                    <span>Need integration help?</span>
                    <Link to="/developers" className="font-medium text-brand-700 dark:text-brand-400 hover:underline">
                      View API documentation & Support Chatbot Tutorial →
                    </Link>
                  </div>
                </>
              )}
            </div>
          </Section>
        )}

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
                {member.role === "owner" ? (
                  <Badge tone="brand">owner</Badge>
                ) : isWsAdmin && member.id !== user?.id ? (
                  <select
                    value={member.role}
                    onChange={(e) => updateMemberRole(member, e.target.value as "admin" | "member" | "viewer")}
                    className="rounded-lg border border-ink-200 bg-white px-2 py-1 text-xs dark:border-ink-700 dark:bg-ink-900"
                  >
                    <option value="admin">admin</option>
                    <option value="member">member</option>
                    <option value="viewer">viewer</option>
                  </select>
                ) : (
                  <Badge tone={member.role === "admin" ? "brand" : "gray"}>{member.role}</Badge>
                )}
                {member.role !== "owner" && (isWsAdmin || member.id === user?.id) && (
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
                {isWsAdmin && (
                  <Button size="sm" variant="ghost" onClick={async () => {
                    const result = await api<Team>(`/workspaces/${current!.id}/invitations/${encodeURIComponent(invitation.email)}`, { method: "DELETE" });
                    members.setData(result);
                  }}>Cancel</Button>
                )}
              </div>
            ))}
          </div>
          {multiUser && isWsAdmin && (
            <div className="mt-3 flex gap-2">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@example.org" aria-label="Email to add"
                onKeyDown={(e) => e.key === "Enter" && email.includes("@") && invite()} className={inputClass} />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as "admin" | "member" | "viewer")}
                className="rounded-xl border border-ink-300 bg-white px-2.5 py-2 text-sm dark:border-ink-700 dark:bg-ink-900"
                aria-label="Role to assign"
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
                <option value="viewer">Viewer</option>
              </select>
              <Button icon={<UserPlus className="h-4 w-4" />} loading={inviting} disabled={!email.includes("@")} onClick={invite}>Add</Button>
            </div>
          )}
          {multiUser && isWsAdmin && (
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

        {(isOwner || isOrgOwner) && (
          <Section id="danger" danger>
            <div className="space-y-5">
              {isOwner && (
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
              )}
              {isOrgOwner && organizations.length > 1 && (
                <div className={cx("flex flex-wrap items-center gap-4", isOwner && "border-t border-ink-100 pt-5 dark:border-ink-800")}>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">Delete this organization</p>
                    <p className="text-sm text-ink-500">Deletes the organization and all its workspaces. Only allowed when no other members remain.</p>
                  </div>
                  <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => setDeleteOrgOpen(true)}>
                    Delete organization
                  </Button>
                </div>
              )}
            </div>
          </Section>
        )}
        </div>
      </div>

      {/* Create Developer Key Modal */}
      <Modal
        open={createKeyModal}
        onClose={() => setCreateKeyModal(false)}
        title="Generate Developer API Key"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreateKeyModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={creatingKey} disabled={!newKeyName.trim()} onClick={handleCreateDevKey}>
              Create Key
            </Button>
          </div>
        }
      >
        <div className="space-y-4 text-sm">
          <div>
            <label htmlFor="key-name" className="block text-xs font-medium text-ink-700 dark:text-ink-300 mb-1">
              Key Name / Purpose
            </label>
            <input
              id="key-name"
              placeholder="e.g. Website Support Chatbot, Mobile App Backend"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              className={inputClass}
            />
          </div>

          <div>
            <label htmlFor="key-ws" className="block text-xs font-medium text-ink-700 dark:text-ink-300 mb-1">
              Workspace Scope
            </label>
            <select
              id="key-ws"
              value={newKeyWorkspace}
              onChange={(e) => setNewKeyWorkspace(e.target.value)}
              className={inputClass}
            >
              <option value="">All current and future workspaces in organization</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} only
                </option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-ink-500">
              Restricting the key to a specific workspace ensures it cannot query documents from other team workspaces.
            </p>
          </div>
        </div>
      </Modal>

      {/* Revoke Key Confirmation Dialog */}
      <ConfirmDialog
        open={!!revokingKey}
        title="Revoke Developer API Key"
        confirmLabel={revoking ? "Revoking..." : "Revoke Key"}
        confirmDisabled={revoking}
        onConfirm={handleRevokeDevKey}
        onClose={() => setRevokingKey(null)}
        danger
      >
        <p className="text-sm text-ink-600 dark:text-ink-300">
          Are you sure you want to revoke <strong>{revokingKey?.name}</strong> (<code>{revokingKey?.key_prefix}</code>)?
          Any integrations, customer support widgets, or scripts using this key will immediately be blocked with HTTP 401.
        </p>
      </ConfirmDialog>

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

      {currentOrganization && (
        <ConfirmDialog
          open={deleteOrgOpen}
          title={`Delete ${currentOrganization.name}?`}
          confirmLabel="Delete forever"
          onClose={() => { setDeleteOrgOpen(false); setConfirmOrgName(""); }}
          confirmDisabled={confirmOrgName !== currentOrganization.name}
          onConfirm={async () => {
            try {
              await api(`/organizations/${currentOrganization.id}`, { method: "DELETE" });
              const nextOrg = organizations.find((o) => o.id !== currentOrganization.id);
              if (nextOrg) switchOrganization(nextOrg.id);
              await reload();
              navigate("/app");
              toast("Organization deleted");
            } catch (e) {
              toast((e as Error).message, "error");
            }
          }}
        >
          <p>All workspaces, documents, and chats in this organization will be permanently deleted for everyone. Type <strong className="text-ink-900 dark:text-white">{currentOrganization.name}</strong> to confirm.</p>
          <input value={confirmOrgName} onChange={(e) => setConfirmOrgName(e.target.value)} aria-label="Organization name" className={cx(inputClass, "mt-3")} />
        </ConfirmDialog>
      )}
    </div>
  );
}
