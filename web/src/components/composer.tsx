// The question box, with the answer-model, document-scope and options pickers.
import { ArrowUp, Check, ChevronDown, Cloud, Cpu, FileSearch, Files, Laptop, SlidersHorizontal, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useStoredState } from "../lib/hooks";
import type { DocumentInfo, Provider } from "../lib/types";
import { FileIcon } from "./answer";
import { Badge, Popover, Toggle, cx } from "./ui";

export interface AnswerSettings {
  provider: string | null;
  topK: number;
  rerank: boolean;
  mode: "answer" | "passages";
}

export function useAnswerSettings() {
  return useStoredState<AnswerSettings>("afrisearch.answer-settings", {
    provider: null, topK: 4, rerank: true, mode: "answer",
  });
}

export function whereItRuns(provider: Provider): { text: string; tone: "blue" | "green" | "violet"; icon: JSX.Element } {
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
  onSend, onStop, busy, providers, defaultProvider, documents, rerankAvailable, settings, setSettings, scope, setScope, autoFocus,
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
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  const [filter, setFilter] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  const available = providers.filter((p) => p.available);
  const providerId = available.some((p) => p.id === settings.provider) ? settings.provider : defaultProvider;
  const provider = providers.find((p) => p.id === providerId);
  const answering = settings.mode === "answer";
  const canSend = text.trim().length >= 2 && !busy && (!answering || Boolean(provider));

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
    <div className="rounded-2xl border border-ink-200 bg-white shadow-lg shadow-ink-900/5 focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-500/10 dark:border-ink-700 dark:bg-ink-900">
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
        placeholder={answering ? "Ask about your documents, in any language…" : "Search your documents…"}
        aria-label="Your question"
        className="block w-full resize-none bg-transparent px-4 pb-2 pt-4 text-[15px] leading-6 placeholder:text-ink-400 focus:outline-none"
      />
      <div className="flex items-center gap-1 px-2 pb-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5">
          <Popover up width="w-80" trigger={({ open, toggle }) => (
            <ToolbarButton open={open} onClick={toggle} label="Answer model">
              {answering ? (
                <>
                  <span className="max-w-[9rem] truncate">{providerName(provider)}</span>
                  <ChevronDown className="h-3 w-3" />
                </>
              ) : (
                <>
                  <FileSearch className="h-3.5 w-3.5" /> Passages only <ChevronDown className="h-3 w-3" />
                </>
              )}
            </ToolbarButton>
          )}>
            {(close) => (
              <div className="max-h-96 overflow-y-auto">
                <p className="px-2.5 pb-1 pt-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">Answer with</p>
                {available.map((p) => {
                  const where = whereItRuns(p);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => {
                        setSettings((s) => ({ ...s, provider: p.id, mode: "answer" }));
                        close();
                      }}
                      className="flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-ink-100 dark:hover:bg-ink-800"
                    >
                      <Check className={cx("mt-0.5 h-4 w-4 shrink-0 text-brand-700", !(answering && p.id === providerId) && "invisible")} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">{providerName(p)}</span>
                        <span className="block truncate text-xs text-ink-500">{p.model}</span>
                      </span>
                      <Badge tone={where.tone}>{where.icon}{where.text}</Badge>
                    </button>
                  );
                })}
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
                {providers.some((p) => !p.available) && (
                  <>
                    <p className="px-2.5 pb-1 pt-3 text-xs font-medium uppercase tracking-wide text-ink-400">Not available</p>
                    {providers.filter((p) => !p.available).map((p) => (
                      <div key={p.id} className="px-2.5 py-1.5 text-xs">
                        <span className="font-medium text-ink-600 dark:text-ink-300">{providerName(p)}</span>
                        <span className="block text-ink-400">{p.reason}</span>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </Popover>

          <Popover up width="w-80" trigger={({ open, toggle }) => (
            <ToolbarButton open={open} onClick={toggle} label="Documents to search">
              <Files className="h-3.5 w-3.5" />
              {scope.length ? `${scope.length} document${scope.length === 1 ? "" : "s"}` : "All documents"}
              <ChevronDown className="h-3 w-3" />
            </ToolbarButton>
          )}>
            <div>
              <div className="flex items-center justify-between px-2.5 pb-2 pt-1.5">
                <p className="text-xs font-medium uppercase tracking-wide text-ink-400">Search in</p>
                {scope.length > 0 && (
                  <button type="button" onClick={() => setScope([])} className="text-xs font-medium text-brand-700 dark:text-brand-400">
                    All documents
                  </button>
                )}
              </div>
              {documents.length > 6 && (
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter documents"
                  className="mx-1 mb-1 w-[calc(100%-0.5rem)] rounded-lg border border-ink-200 bg-transparent px-2.5 py-1.5 text-sm focus:border-brand-400 focus:outline-none dark:border-ink-700"
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
                        <span className="truncate">{doc.source_name}</span>
                      </label>
                    );
                  })}
              </div>
            </div>
          </Popover>

          <Popover up width="w-72" trigger={({ open, toggle }) => (
            <ToolbarButton open={open} onClick={toggle} label="Search options">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Options</span>
            </ToolbarButton>
          )}>
            <div className="space-y-4 p-2.5">
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
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-700 text-white transition hover:bg-brand-800 disabled:bg-ink-200 disabled:text-ink-400 dark:disabled:bg-ink-800 dark:disabled:text-ink-600"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
