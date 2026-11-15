// The question box, with the answer-model, document-scope and options pickers.
import { ArrowUp, BookOpen, Check, ChevronDown, Cloud, Cpu, FileSearch, Files, Laptop, SlidersHorizontal, Sparkles, Square, Tag } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useStoredState } from "../lib/hooks";
import type { DocumentInfo, Provider } from "../lib/types";
import { FileIcon } from "./answer";
import { Badge, Popover, Toggle, cx } from "./ui";

export interface AnswerSettings {
  provider: string | null;
  model: string | null;
  topK: number;
  rerank: boolean;
  mode: "answer" | "passages";
  deepMode?: boolean;
}

export function useAnswerSettings() {
  return useStoredState<AnswerSettings>("afrisearch.answer-settings", {
    provider: null, model: null, topK: 4, rerank: true, mode: "answer", deepMode: false,
  });
}

export function whereItRuns(provider: Provider): { text: string; tone: "blue" | "green" | "violet"; icon: JSX.Element } {
  if (provider.custom_key) return { text: "Your Key", tone: "green", icon: <Cloud className="h-3 w-3" /> };
  if (provider.kind === "api") return { text: "Cloud", tone: "blue", icon: <Cloud className="h-3 w-3" /> };
  if (provider.label.includes("CPU")) return { text: "On this computer", tone: "green", icon: <Laptop className="h-3 w-3" /> };
  return { text: "Local GPU", tone: "violet", icon: <Cpu className="h-3 w-3" /> };
}

/** "Qwen 2.5 0.5B (local, runs on CPU)" -> "Qwen 2.5 0.5B" */
export function providerName(provider: Provider | undefined): string {
  return provider ? provider.label.replace(/\s*\(.*\)\s*$/, "") : "No model";
}

function ToolbarButton({ open, onClick, children, label }: { open: boolean; onClick: () => void; children: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-expanded={open}
      onClick={onClick}
      className={cx(
        "flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition",
        open ? "bg-ink-100 text-ink-900 dark:bg-ink-800 dark:text-white" : "text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800",
      )}
    >
      {children}
    </button>
  );
}

export function Composer({
  onSend, onStop, busy, providers, defaultProvider, documents, rerankAvailable, settings, setSettings, scope, setScope,
  tagScope, setTagScope, autoFocus,
}: {
  onSend: (question: string) => void;
  onStop: () => void;
  busy: boolean;
  providers: Provider[];
  defaultProvider: string | null;
  documents: DocumentInfo[];
  rerankAvailable: boolean;
  settings: AnswerSettings;
  setSettings: (update: (s: AnswerSettings) => AnswerSettings) => void;
  scope: string[];
  setScope: (ids: string[]) => void;
  tagScope?: string[];
  setTagScope?: (tags: string[]) => void;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  const [filter, setFilter] = useState("");
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [customInputOpen, setCustomInputOpen] = useState<string | null>(null);
  const [customModelText, setCustomModelText] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  const available = providers.filter((p) => p.available);
  const providerId = available.some((p) => p.id === settings.provider) ? settings.provider : defaultProvider;
  const provider = providers.find((p) => p.id === providerId);
  const answering = settings.mode === "answer";
  const canSend = text.trim().length >= 2 && !busy && (!answering || Boolean(provider));
  const activeTagScope = tagScope ?? [];
  const availableTags = Array.from(
    new Set(documents.flatMap((d) => d.tags ?? []))
  ).sort();

  const providerModels = provider?.models ?? (provider ? [{ id: provider.model, name: provider.model }] : []);
  const activeModelId: string = settings.model || provider?.model || "";
  const activeModelObj = providerModels.find((m) => m.id === activeModelId);
  const activeModelLabel = activeModelObj ? activeModelObj.name : activeModelId.split("/").pop() || "";

  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [text]);

  useEffect(() => {
    if (autoFocus) textarea.current?.focus();
  }, [autoFocus]);

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
  };

  return (
    <div className="rounded-[22px] border border-ink-200/90 bg-white shadow-lift transition focus-within:border-brand-300 focus-within:shadow-[0_0_0_4px_rgb(249_115_22/0.10),0_12px_32px_-8px_rgb(28_25_23/0.16)] dark:border-ink-700 dark:bg-ink-900 dark:focus-within:border-brand-800 dark:focus-within:shadow-[0_0_0_4px_rgb(194_65_12/0.18)]">
      {settings.deepMode && (
        <div className="flex items-center justify-between border-b border-amber-200/60 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/40 dark:text-amber-200 rounded-t-[22px]">
          <span className="flex items-center gap-1.5 font-medium">
            <BookOpen className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
            Deep Book Mode active — Reading comprehensive multi-chapter context with 1M+ token reasoning
          </span>
          <button
            type="button"
            onClick={() => setSettings((s) => ({ ...s, deepMode: false }))}
            className="text-[11px] font-medium underline opacity-80 hover:opacity-100"
          >
            Standard RAG
          </button>
        </div>
      )}
      <textarea
        ref={textarea}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={answering ? (settings.deepMode ? "Ask a comprehensive question about your books or documents…" : "Ask about your documents, in any language…") : "Search your documents…"}
        aria-label="Your question"
        className="block w-full resize-none bg-transparent px-5 pb-2 pt-4 text-[15px] leading-6 placeholder:text-ink-400 focus:outline-none"
      />
      <div className="flex items-center gap-1 px-2 pb-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5">
          <Popover up width="w-96" trigger={({ open, toggle }) => (
            <ToolbarButton open={open} onClick={toggle} label="Answer model">
              {answering ? (
                <>
                  <span className="max-w-[10rem] truncate">{providerName(provider)}</span>
                  {activeModelLabel && (
                    <span className="hidden max-w-[8.5rem] truncate rounded bg-ink-100 px-1.5 py-0.5 text-[10px] font-medium text-ink-600 dark:bg-ink-800 dark:text-ink-300 sm:inline-block">
                      {activeModelLabel.replace(/\s*\(.*\)\s*$/, "")}
                    </span>
                  )}
                  <ChevronDown className="h-3 w-3 shrink-0" />
                </>
              ) : (
                <>
                  <FileSearch className="h-3.5 w-3.5" /> Passages only <ChevronDown className="h-3 w-3" />
                </>
              )}
            </ToolbarButton>
          )}>
            {(close) => {
              const currentExpanded = expandedProvider ?? providerId;
              return (
                <div className="max-h-[28rem] overflow-y-auto p-1 text-ink-900 dark:text-ink-100">
                  <div className="flex items-center justify-between px-2.5 pb-2 pt-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-ink-400">Answer with AI Model</p>
                    <span className="text-[11px] text-ink-400">Select provider & model</span>
                  </div>

                  <div className="space-y-1">
                    {available.map((p) => {
                      const isSelectedProvider = answering && p.id === providerId;
                      const isExpanded = currentExpanded === p.id;
                      const modelsList = p.models && p.models.length > 0 ? p.models : [{ id: p.model, name: p.model, description: "" }];
                      const where = whereItRuns(p);

                      return (
                        <div
                          key={p.id}
                          className={cx(
                            "rounded-xl border transition",
                            isSelectedProvider
                              ? "border-brand-300 bg-brand-50/20 dark:border-brand-800 dark:bg-brand-950/20"
                              : "border-ink-100 bg-transparent hover:border-ink-200 dark:border-ink-800/80 dark:hover:border-ink-700"
                          )}
                        >
                          <div className="flex items-center justify-between gap-2 p-2">
                            <button
                              type="button"
                              onClick={() => {
                                setExpandedProvider(p.id);
                                const defaultModel = p.models?.[0]?.id || p.model;
                                setSettings((s) => ({
                                  ...s,
                                  provider: p.id,
                                  model: s.provider === p.id && s.model ? s.model : defaultModel,
                                  mode: "answer",
                                }));
                              }}
                              className="flex min-w-0 flex-1 items-center gap-2 text-left"
                            >
                              <Check className={cx("h-4 w-4 shrink-0 text-brand-600", !isSelectedProvider && "invisible")} />
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-sm font-semibold text-ink-900 dark:text-white">{providerName(p)}</span>
                                  {p.custom_key && (
                                    <span className="inline-flex items-center rounded bg-emerald-100 px-1.5 py-0.2 text-[10px] font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                                      Your Key
                                    </span>
                                  )}
                                </div>
                                <span className="block truncate text-xs text-ink-500">
                                  {isSelectedProvider && activeModelLabel ? activeModelLabel : `${modelsList.length} model${modelsList.length === 1 ? "" : "s"} available`}
                                </span>
                              </div>
                            </button>

                            <div className="flex items-center gap-1">
                              <Badge tone={where.tone}>{where.icon}{where.text}</Badge>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setExpandedProvider(isExpanded ? null : p.id);
                                }}
                                className="rounded p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700 dark:hover:bg-ink-800"
                                aria-label="Toggle models"
                              >
                                <ChevronDown className={cx("h-3.5 w-3.5 transition-transform", isExpanded && "rotate-180")} />
                              </button>
                            </div>
                          </div>

                          {isExpanded && (
                            <div className="border-t border-ink-100 bg-white/50 px-2 py-2 dark:border-ink-800/60 dark:bg-ink-900/50">
                              <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-ink-400">Select Model</p>
                              <div className="space-y-0.5">
                                {modelsList.map((m) => {
                                  const isModelActive = isSelectedProvider && (activeModelId === m.id || (!settings.model && m.id === p.model));
                                  return (
                                    <button
                                      key={m.id}
                                      type="button"
                                      onClick={() => {
                                        setSettings((s) => ({ ...s, provider: p.id, model: m.id, mode: "answer" }));
                                        close();
                                      }}
                                      className={cx(
                                        "flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition",
                                        isModelActive
                                          ? "bg-brand-100/70 font-medium text-brand-900 dark:bg-brand-950 dark:text-brand-100"
                                          : "text-ink-700 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800"
                                      )}
                                    >
                                      <Check className={cx("mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-600", !isModelActive && "invisible")} />
                                      <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-1.5">
                                          <span className="font-medium text-ink-900 dark:text-white">{m.name}</span>
                                          <code className="text-[10px] text-ink-400">{m.id.split("/").pop()}</code>
                                        </div>
                                        {m.description && <p className="text-[11px] text-ink-500">{m.description}</p>}
                                      </div>
                                    </button>
                                  );
                                })}

                                {customInputOpen === p.id ? (
                                  <div className="mt-1 flex items-center gap-1.5 px-2 pt-1">
                                    <input
                                      type="text"
                                      value={customModelText}
                                      onChange={(e) => setCustomModelText(e.target.value)}
                                      placeholder="Custom model ID (e.g. gemini-2.5-flash)..."
                                      className="h-7 min-w-0 flex-1 rounded-md border border-ink-200 bg-white px-2 text-xs text-ink-900 dark:border-ink-700 dark:bg-ink-800 dark:text-white"
                                      autoFocus
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter" && customModelText.trim()) {
                                          e.preventDefault();
                                          setSettings((s) => ({ ...s, provider: p.id, model: customModelText.trim(), mode: "answer" }));
                                          setCustomInputOpen(null);
                                          close();
                                        }
                                      }}
                                    />
                                    <button
                                      type="button"
                                      disabled={!customModelText.trim()}
                                      onClick={() => {
                                        if (customModelText.trim()) {
                                          setSettings((s) => ({ ...s, provider: p.id, model: customModelText.trim(), mode: "answer" }));
                                          setCustomInputOpen(null);
                                          close();
                                        }
                                      }}
                                      className="h-7 rounded-md bg-brand-600 px-2.5 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                                    >
                                      Use
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setCustomInputOpen(null)}
                                      className="h-7 rounded-md px-1.5 text-xs text-ink-500 hover:text-ink-800"
                                    >
                                      ✕
                                    </button>
                                  </div>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setCustomInputOpen(p.id);
                                      setCustomModelText(activeModelId || "");
                                    }}
                                    className="mt-0.5 flex w-full items-center gap-1.5 px-2 py-1 text-[11px] font-medium text-brand-600 hover:underline dark:text-brand-400"
                                  >
                                    <Sparkles className="h-3 w-3" /> Custom model ID...
                                  </button>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-2 pt-2 border-t border-ink-100 dark:border-ink-800">
                    <button
                      type="button"
                      onClick={() => {
                        setSettings((s) => ({ ...s, mode: "passages" }));
                        close();
                      }}
                      className="flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-ink-100 dark:hover:bg-ink-800"
                    >
                      <Check className={cx("mt-0.5 h-4 w-4 shrink-0 text-brand-700", answering && "invisible")} />
                      <span>
                        <span className="block text-sm font-medium">Find passages only</span>
                        <span className="block text-xs text-ink-500">Instant; nothing is sent to an AI model</span>
                      </span>
                    </button>
                  </div>

                  {providers.some((p) => !p.available) && (
                    <div className="mt-2 border-t border-ink-100 px-2 pt-2 dark:border-ink-800">
                      <p className="pb-1 text-xs font-semibold uppercase tracking-wide text-ink-400">Not available</p>
                      {providers.filter((p) => !p.available).map((p) => (
                        <div key={p.id} className="py-1 text-xs">
                          <span className="font-medium text-ink-600 dark:text-ink-300">{providerName(p)}</span>
                          <span className="block text-ink-400">{p.reason}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            }}
          </Popover>

          <Popover up width="w-80" trigger={({ open, toggle }) => (
            <ToolbarButton open={open} onClick={toggle} label="Documents to search">
              <Files className="h-3.5 w-3.5" />
              {activeTagScope.length > 0 && scope.length === 0
                ? (activeTagScope.length === 1 ? `Tag: ${activeTagScope[0]}` : `${activeTagScope.length} collections`)
                : activeTagScope.length === 0 && scope.length > 0
                ? `${scope.length} document${scope.length === 1 ? "" : "s"}`
                : activeTagScope.length > 0 && scope.length > 0
                ? `${activeTagScope.length} tags, ${scope.length} docs`
                : "All documents"}
              <ChevronDown className="h-3 w-3" />
            </ToolbarButton>
          )}>
            <div>
              <div className="flex items-center justify-between px-2.5 pb-2 pt-1.5">
                <p className="text-xs font-medium uppercase tracking-wide text-ink-400">Search in</p>
                {(scope.length > 0 || activeTagScope.length > 0) && (
                  <button
                    type="button"
                    onClick={() => {
                      setScope([]);
                      setTagScope?.([]);
                    }}
                    className="text-xs font-medium text-brand-700 dark:text-brand-400"
                  >
                    All documents
                  </button>
                )}
              </div>
              {availableTags.length > 0 && (
                <div className="border-b border-ink-100 px-2.5 pb-2.5 pt-0.5 dark:border-ink-800">
                  <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-400">Collections / Tags</p>
                  <div className="flex flex-wrap gap-1">
                    {availableTags.map((tag) => {
                      const isSelected = activeTagScope.some((t) => t.toLowerCase() === tag.toLowerCase());
                      return (
                        <button
                          key={tag}
                          type="button"
                          onClick={() => {
                            if (!setTagScope) return;
                            if (isSelected) {
                              setTagScope(activeTagScope.filter((t) => t.toLowerCase() !== tag.toLowerCase()));
                            } else {
                              setTagScope([...activeTagScope, tag]);
                            }
                          }}
                          className={cx(
                            "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium transition",
                            isSelected
                              ? "bg-brand-600 text-white shadow-sm"
                              : "bg-ink-100 text-ink-700 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                          )}
                        >
                          <Tag className="h-3 w-3" />
                          {tag}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              {documents.length > 6 && (
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter documents"
                  className="mx-1 my-1.5 w-[calc(100%-0.5rem)] rounded-lg border border-ink-200 bg-transparent px-2.5 py-1.5 text-sm focus:border-brand-400 focus:outline-none dark:border-ink-700"
                />
              )}
              <div className="max-h-72 overflow-y-auto">
                {documents.length === 0 && <p className="px-2.5 py-2 text-sm text-ink-500">No documents yet.</p>}
                {documents
                  .filter((d) => d.source_name.toLowerCase().includes(filter.toLowerCase()))
                  .map((doc) => {
                    const checked = scope.includes(doc.source_id);
                    return (
                      <label key={doc.source_id} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm hover:bg-ink-100 dark:hover:bg-ink-800">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => setScope(checked ? scope.filter((id) => id !== doc.source_id) : [...scope, doc.source_id])}
                          className="h-4 w-4 rounded border-ink-300 accent-brand-700"
                        />
                        <FileIcon name={doc.source_name} />
                        <div className="min-w-0 flex-1">
                          <span className="block truncate">{doc.source_name}</span>
                          {doc.tags && doc.tags.length > 0 && (
                            <span className="flex flex-wrap gap-1 pt-0.5">
                              {doc.tags.map((t) => (
                                <span key={t} className="inline-flex items-center gap-0.5 rounded bg-ink-100 px-1 text-[10px] text-ink-600 dark:bg-ink-800 dark:text-ink-400">
                                  #{t}
                                </span>
                              ))}
                            </span>
                          )}
                        </div>
                      </label>
                    );
                  })}
              </div>
            </div>
          </Popover>

          <button
            type="button"
            onClick={() => setSettings((s) => ({ ...s, deepMode: !s.deepMode }))}
            title={settings.deepMode ? "Deep Book Mode Active: Full multi-chapter context" : "Enable Deep Book Mode for comprehensive book analysis"}
            className={cx(
              "flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition",
              settings.deepMode
                ? "bg-amber-500/15 text-amber-800 border border-amber-500/30 dark:bg-amber-500/25 dark:text-amber-200 dark:border-amber-500/40 shadow-sm"
                : "text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800"
            )}
          >
            <BookOpen className={cx("h-3.5 w-3.5", settings.deepMode ? "text-amber-600 dark:text-amber-400" : "text-ink-500")} />
            <span className="hidden sm:inline">Deep Book</span>
            {settings.deepMode && (
              <span className="hidden md:inline rounded bg-amber-500/20 px-1 py-0.2 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                1M Context
              </span>
            )}
          </button>

          <Popover up width="w-80" trigger={({ open, toggle }) => (
            <ToolbarButton open={open} onClick={toggle} label="Search options">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Options</span>
            </ToolbarButton>
          )}>
            <div className="space-y-4 p-2.5">
              <div className="flex items-start justify-between gap-3 pb-3 border-b border-ink-100 dark:border-ink-800">
                <div>
                  <div className="flex items-center gap-1.5">
                    <BookOpen className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                    <p className="text-sm font-medium">Deep Book Mode</p>
                  </div>
                  <p className="mt-0.5 text-xs text-ink-500">
                    Feeds extensive multi-chapter context into large context windows (up to 1M tokens with Gemini) for holistic book understanding.
                  </p>
                </div>
                <Toggle
                  label="Deep Book Mode"
                  checked={Boolean(settings.deepMode)}
                  onChange={(value) => setSettings((s) => ({ ...s, deepMode: value }))}
                />
              </div>

              <div>
                <div className="flex items-center justify-between text-sm">
                  <label htmlFor="top-k" className="font-medium">Passages to use</label>
                  <span className="tabular-nums text-ink-500">{settings.topK}</span>
                </div>
                <input
                  id="top-k"
                  type="range"
                  min={1}
                  max={8}
                  value={settings.topK}
                  onChange={(e) => setSettings((s) => ({ ...s, topK: Number(e.target.value) }))}
                  className="mt-2 w-full accent-brand-700"
                />
                <p className="mt-1 text-xs text-ink-500">More passages give more context but slower answers.</p>
              </div>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">Rerank passages</p>
                  <p className="text-xs text-ink-500">
                    {rerankAvailable ? "Rereads the best matches and puts the most relevant first." : "No reranker is configured on the server."}
                  </p>
                </div>
                <Toggle
                  label="Rerank passages"
                  checked={rerankAvailable && settings.rerank}
                  disabled={!rerankAvailable}
                  onChange={(value) => setSettings((s) => ({ ...s, rerank: value }))}
                />
              </div>
            </div>
          </Popover>
        </div>

        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop"
            title="Stop"
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink-900 text-white transition hover:bg-ink-700 dark:bg-white dark:text-ink-900"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!canSend}
            aria-label="Send"
            title="Send (Enter)"
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-glow transition hover:brightness-110 disabled:bg-none disabled:bg-ink-100 disabled:text-ink-400 disabled:shadow-none dark:disabled:bg-ink-800 dark:disabled:text-ink-600"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
