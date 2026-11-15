// The workspace's documents: upload, indexing progress, and the document list.
import {
  AlertCircle, ArrowRight, BookOpen, Camera, CheckCircle2, Copy, Download, ExternalLink, FilePlus2, FileStack, FileUp, FolderOpen, GitCompare, HardDrive, Headphones, HelpCircle, ListTree, Loader2, MessageSquare, MoreHorizontal,
  Plus, RefreshCw, ScanText, Search, Sparkles, Tag, TextQuote, Trash2, Upload, X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileTile } from "../components/answer";
import { AudioOverviewModal } from "../components/AudioOverviewModal";
import { DocumentCompareModal } from "../components/DocumentCompareModal";
import {
  Alert, Badge, Button, Card, ConfirmDialog, Drawer, EmptyState, IconButton, MenuItem, Modal, PageHeader, Popover, Spinner, Stat, cx, useToast,
} from "../components/ui";
import { api, authHeaders, openDocument, uploadFiles } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatPages, formatSize, timeAgo } from "../lib/format";
import { useApi, useInterval } from "../lib/hooks";
import type { DocumentInfo, DocumentsResponse, FailedFile, Job, OutlineItem, Passage } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

const PAGE_SIZE = 50;

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ProgressBar({ value }: { value: number | null }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800" role="progressbar" aria-valuenow={value === null ? undefined : Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      {value === null ? (
        <div className="h-full w-1/3 animate-pulse rounded-full bg-brand-gradient" />
      ) : (
        <div className="h-full rounded-full bg-brand-gradient transition-all duration-500" style={{ width: `${Math.max(3, value * 100)}%` }} />
      )}
    </div>
  );
}

/** How far along a job is (0-1), counting pages within the current file. */
function jobFraction(job: Job): number | null {
  const p = job.progress;
  if (job.status === "queued") return 0;
  if (p.stage === "embedding") return 0.95;
  if (!p.file_count || !p.file_number) return null;
  const withinFile = p.page && p.page_count ? p.page / p.page_count : 0;
  return Math.min(0.9, ((p.file_number - 1 + withinFile) / p.file_count) * 0.9);
}

function jobLabel(job: Job): string {
  const p = job.progress;
  if (job.status === "queued") return "Waiting to start…";
  if (p.stage === "embedding") return `Making ${p.passages ?? ""} passages searchable…`;
  if (p.stage === "reading" && p.file) {
    const page = p.page && p.page_count ? ` · page ${p.page} of ${p.page_count}` : "";
    const files = p.file_count && p.file_count > 1 ? ` · file ${p.file_number} of ${p.file_count}` : "";
    return `Reading ${p.file}${page}${files}`;
  }
  return "Starting…";
}

function DropZone({ onFiles, accept, maxMb, disabled, compact }: {
  onFiles: (files: File[]) => void;
  accept: string[];
  maxMb: number;
  disabled: boolean;
  compact?: boolean; // a slim bar once there are documents
}) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) onFiles(Array.from(e.dataTransfer.files));
      }}
      onClick={() => !disabled && input.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      aria-label="Upload documents"
      className={cx(
        "group flex cursor-pointer items-center rounded-2xl border-2 border-dashed transition",
        compact ? "flex-col gap-3 px-5 py-4 text-center sm:flex-row sm:text-left" : "flex-col justify-center px-6 py-12 text-center",
        over ? "scale-[1.01] border-brand-500 bg-brand-50 dark:bg-brand-950/40" : "border-ink-200 bg-ink-50/40 hover:border-brand-300 hover:bg-brand-50/40 dark:border-ink-700 dark:bg-ink-900/30 dark:hover:border-brand-800 dark:hover:bg-brand-950/20",
        disabled && "pointer-events-none opacity-60",
      )}
    >
      <div className={cx("flex shrink-0 items-center justify-center bg-brand-gradient text-white shadow-glow transition group-hover:-translate-y-0.5",
        compact ? "h-10 w-10 rounded-xl" : "h-14 w-14 rounded-2xl")}>
        <FileUp className={compact ? "h-5 w-5" : "h-6 w-6"} />
      </div>
      <div className={compact ? "min-w-0 flex-1" : ""}>
        <p className={cx("font-semibold", !compact && "mt-4")}>Drop files here, or <span className="text-brand-700 dark:text-brand-400">browse</span></p>
        <p className="mt-0.5 text-sm text-ink-500">PDF, Word, Excel, PowerPoint, text, or photos and scans of pages · up to {maxMb} MB each</p>
      </div>
      {/* On phones, open the camera straight away: photos of pages are read with OCR. */}
      <label onClick={(e) => e.stopPropagation()}
        className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg bg-white px-3 text-sm font-medium text-ink-700 shadow-sm ring-1 ring-ink-200 hover:bg-ink-50 dark:bg-ink-900 dark:text-ink-200 dark:ring-ink-700 sm:hidden">
        <Camera className="h-4 w-4" /> Take a photo
        <input type="file" accept="image/*" capture="environment" hidden disabled={disabled}
          onChange={(e) => { onFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
      </label>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        accept={accept.map((ext) => `.${ext}`).join(",")}
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </div>
  );
}

interface ExecutiveBrief {
  headline?: string;
  summary?: string;
  takeaways?: string[];
  structure?: string[];
  suggested_questions?: string[];
  markdown?: string;
  created_at?: string;
  provider?: string;
  model?: string;
}

function PassagesDrawer({
  doc,
  onClose,
  onOpenPodcast,
}: {
  doc: DocumentInfo | null;
  onClose: () => void;
  onOpenPodcast?: (docIds: string[]) => void;
}) {
  const { data, loading, error } = useApi<{ passages: Passage[] }>(doc ? `/documents/${encodeURIComponent(doc.source_id)}/passages` : null);
  const { data: outlineData } = useApi<{ outline: OutlineItem[] }>(doc ? `/documents/${encodeURIComponent(doc.source_id)}/outline` : null);
  const { data: summaryData, reload: reloadSummary } = useApi<{ summary: string | null; brief?: ExecutiveBrief | null }>(doc ? `/documents/${encodeURIComponent(doc.source_id)}/summary` : null);

  const [activeTab, setActiveTab] = useState<"summary" | "outline" | "passages">("summary");
  const [selectedChapter, setSelectedChapter] = useState<OutlineItem | null>(null);
  const [query, setQuery] = useState("");
  const [summarizing, setSummarizing] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const outline = outlineData?.outline ?? doc?.outline ?? [];
  const rawSummary = summaryData?.summary ?? doc?.summary;
  const brief: ExecutiveBrief | null = (() => {
    if (summaryData?.brief) return summaryData.brief;
    if (!rawSummary) return null;
    try {
      const parsed = JSON.parse(rawSummary);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
      return null;
    }
  })();
  const markdownText = brief?.markdown || rawSummary || "";

  useEffect(() => {
    if (doc) {
      setSelectedChapter(null);
      setQuery("");
      // Default to Executive Briefing if available, otherwise outline or passages
      if (doc.summary) {
        setActiveTab("summary");
      } else if (doc.outline && doc.outline.length > 0) {
        setActiveTab("outline");
      } else {
        setActiveTab("passages");
      }
    }
  }, [doc]);

  const passages = (data?.passages ?? []).filter((p) => {
    if (selectedChapter) {
      const page = p.page || 1;
      const start = selectedChapter.page;
      const end = selectedChapter.page_end || start;
      if (page < start || page > end) return false;
    }
    if (query) {
      return p.text.toLowerCase().includes(query.toLowerCase());
    }
    return true;
  });

  const handleGenerateSummary = async () => {
    if (!doc) return;
    setSummarizing(true);
    try {
      await api<{ summary: string }>(`/documents/${encodeURIComponent(doc.source_id)}/summarize`, {
        method: "POST",
      });
      toast("Executive summary generated!");
      reloadSummary();
      setActiveTab("summary");
    } catch (e: any) {
      toast(e.message || "Failed to generate summary", "error");
    } finally {
      setSummarizing(false);
    }
  };

  return (
    <Drawer
      open={Boolean(doc)}
      onClose={onClose}
      title={doc?.source_name ?? ""}
      subtitle={doc && (
        <span className="flex flex-wrap items-center gap-2">
          {doc.passages} passages{doc.pages ? ` · ${doc.pages} pages` : ""} · {formatSize(doc.bytes)}
          {doc.ocr && <Badge tone="blue"><ScanText className="h-3 w-3" />OCR</Badge>}
          <button className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline dark:text-brand-400"
            onClick={() => openDocument(doc.source_id).catch((e: Error) => toast(e.message, "error"))}>
            <ExternalLink className="h-3.5 w-3.5" /> Open original
          </button>
        </span>
      )}
    >
      {/* Tab Switcher */}
      <div className="flex items-center gap-1 border-b border-ink-200 pb-2 mb-4 text-xs font-medium dark:border-ink-800">
        <button
          type="button"
          onClick={() => setActiveTab("summary")}
          className={cx(
            "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition",
            activeTab === "summary"
              ? "bg-brand-500/10 text-brand-700 dark:bg-brand-500/20 dark:text-brand-300 font-semibold"
              : "text-ink-600 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800"
          )}
        >
          <Sparkles className="h-3.5 w-3.5 text-brand-500" />
          <span>Executive Briefing {brief ? "✨" : ""}</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("outline")}
          className={cx(
            "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition",
            activeTab === "outline"
              ? "bg-brand-500/10 text-brand-700 dark:bg-brand-500/20 dark:text-brand-300 font-semibold"
              : "text-ink-600 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800"
          )}
        >
          <ListTree className="h-3.5 w-3.5" />
          <span>Outline ({outline.length})</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("passages")}
          className={cx(
            "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition",
            activeTab === "passages"
              ? "bg-brand-500/10 text-brand-700 dark:bg-brand-500/20 dark:text-brand-300 font-semibold"
              : "text-ink-600 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800"
          )}
        >
          <TextQuote className="h-3.5 w-3.5" />
          <span>Passages ({data?.passages?.length ?? doc?.passages ?? 0})</span>
        </button>
      </div>

      {/* Tab 1: Outline / Chapters */}
      {activeTab === "outline" && (
        <div className="space-y-2">
          {outline.length === 0 ? (
            <div className="py-12 text-center text-sm text-ink-500">
              <BookOpen className="mx-auto mb-2 h-8 w-8 text-ink-400 opacity-60" />
              <p className="font-medium text-ink-700 dark:text-ink-300">No formal Table of Contents detected.</p>
              <p className="mt-1 text-xs text-ink-400">You can explore and search all passages directly.</p>
              <Button
                variant="secondary"
                className="mt-4"
                onClick={() => setActiveTab("passages")}
              >
                View Passages
              </Button>
            </div>
          ) : (
            <div className="space-y-1.5 max-h-[70vh] overflow-y-auto pr-1">
              {outline.map((item, i) => (
                <div
                  key={i}
                  className={cx(
                    "group flex items-center justify-between rounded-xl border border-ink-200/80 p-2.5 transition hover:border-brand-300 hover:bg-brand-50/40 dark:border-ink-800 dark:hover:border-brand-700/60 dark:hover:bg-brand-950/20",
                    item.level === 1 ? "bg-ink-50/50 dark:bg-ink-800/40 font-medium" : "ml-3 text-xs"
                  )}
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <p className={cx("truncate text-xs", item.level === 1 ? "font-semibold text-ink-900 dark:text-ink-100" : "text-ink-700 dark:text-ink-300")}>
                      {item.title}
                    </p>
                    <span className="text-[11px] text-ink-400">
                      {item.page_end && item.page_end > item.page ? `Pages ${item.page}–${item.page_end}` : `Page ${item.page}`}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 opacity-80 group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedChapter(item);
                        setActiveTab("passages");
                      }}
                      className="rounded-md border border-ink-200 bg-white px-2 py-1 text-[11px] font-medium text-ink-700 hover:bg-ink-50 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-200"
                    >
                      Passages
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        navigate("/app", {
                          state: {
                            question: `Explain "${item.title}" in detail from ${doc!.source_name}`,
                            scope: [doc!.source_id],
                          },
                        });
                      }}
                      title="Ask AI about this chapter"
                      className="flex items-center gap-1 rounded-md bg-brand-500/10 px-2 py-1 text-[11px] font-medium text-brand-700 hover:bg-brand-500/20 dark:bg-brand-500/20 dark:text-brand-300"
                    >
                      <MessageSquare className="h-3 w-3" />
                      <span>Ask AI</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Passages */}
      {activeTab === "passages" && (
        <>
          {selectedChapter && (
            <div className="mb-3 flex items-center justify-between rounded-lg bg-brand-500/10 px-3 py-1.5 text-xs text-brand-800 dark:bg-brand-500/20 dark:text-brand-200">
              <span>Filtered to chapter: <strong>{selectedChapter.title}</strong> (pp. {selectedChapter.page}{selectedChapter.page_end ? `–${selectedChapter.page_end}` : ""})</span>
              <button
                type="button"
                onClick={() => setSelectedChapter(null)}
                className="font-medium underline hover:text-brand-900 dark:hover:text-brand-100"
              >
                Clear filter
              </button>
            </div>
          )}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find in this document"
              className="w-full rounded-lg border border-ink-200 bg-transparent py-2 pl-9 pr-3 text-sm focus:border-brand-400 focus:outline-none dark:border-ink-700" />
          </div>
          {loading && <div className="flex justify-center py-10"><Spinner /></div>}
          {error && <Alert tone="red">{error}</Alert>}
          <ol className="space-y-3">
            {passages.map((passage) => {
              const number = (data?.passages ?? []).indexOf(passage) + 1;
              return (
                <li key={passage.chunk_id} className="rounded-xl border border-ink-200 p-4 dark:border-ink-800">
                  <div className="mb-2 flex items-center gap-2 text-xs text-ink-500">
                    <span className="font-semibold text-ink-700 dark:text-ink-300">Passage {number}</span>
                    {formatPages(passage.page, passage.page_end) && <span>· {formatPages(passage.page, passage.page_end)}</span>}
                    {passage.ocr && <Badge tone="blue">OCR</Badge>}
                  </div>
                  <p className="whitespace-pre-line text-sm leading-6 text-ink-700 dark:text-ink-300">{passage.text}</p>
                </li>
              );
            })}
          </ol>
          {!loading && data && passages.length === 0 && <p className="text-center text-sm text-ink-500">No passage matches your filter.</p>}
        </>
      )}

      {/* Tab: Executive Briefing */}
      {activeTab === "summary" && (
        <div className="space-y-4">
          {markdownText ? (
            <div className="space-y-4 animate-fade-in">
              {/* Briefing Top Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-100 pb-2.5 dark:border-ink-800">
                <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-brand-700 dark:text-brand-300">
                  <Sparkles className="h-4 w-4 text-brand-600" />
                  <span>Executive Intelligence Briefing</span>
                  {brief?.provider && (
                    <Badge tone="gray">via {brief.provider}</Badge>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Copy className="h-3 w-3" />}
                    onClick={() => navigator.clipboard.writeText(markdownText).then(() => toast("Executive brief copied"))}
                    title="Copy full brief"
                  >
                    Copy
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Download className="h-3 w-3" />}
                    onClick={() => downloadBlob(`${doc?.source_name ?? "document"}-brief.md`, markdownText, "text/markdown")}
                    title="Download Markdown"
                  >
                    .md
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<MessageSquare className="h-3 w-3 text-brand-600" />}
                    onClick={() => {
                      onClose();
                      navigate("/app", {
                        state: {
                          question: `Summarize the strategic implications of ${doc?.source_name}`,
                          scope: [doc!.source_id],
                        },
                      });
                    }}
                    title="Ask follow-up questions in Chat"
                  >
                    Discuss in Chat
                  </Button>
                  {onOpenPodcast && (
                    <Button
                      size="sm"
                      variant="secondary"
                      icon={<Headphones className="h-3 w-3 text-indigo-600" />}
                      onClick={() => {
                        onClose();
                        onOpenPodcast([doc!.source_id]);
                      }}
                      title="Listen to 2-host audio overview"
                    >
                      Audio Overview
                    </Button>
                  )}
                  <button
                    type="button"
                    onClick={handleGenerateSummary}
                    disabled={summarizing}
                    className="text-xs text-ink-500 hover:text-ink-800 underline dark:hover:text-ink-200 ml-1"
                  >
                    {summarizing ? "Regenerating..." : "Regenerate"}
                  </button>
                </div>
              </div>

              {/* Executive One-Liner Headline */}
              {brief?.headline && (
                <div className="rounded-2xl border border-brand-200/90 bg-gradient-to-r from-brand-50/90 to-brand-100/40 p-4 shadow-soft dark:border-brand-900/60 dark:from-brand-950/60 dark:to-brand-900/30">
                  <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-brand-700 dark:text-brand-300 mb-1">
                    <Sparkles className="h-3 w-3" /> One-Liner Executive Thesis
                  </span>
                  <p className="text-sm font-semibold leading-relaxed text-ink-900 dark:text-ink-50">
                    "{brief.headline}"
                  </p>
                </div>
              )}

              {/* Suggested Questions to Ask */}
              {brief?.suggested_questions && brief.suggested_questions.length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 flex items-center gap-1.5">
                    <HelpCircle className="h-3.5 w-3.5 text-brand-600" /> Suggested Questions to Ask
                  </span>
                  <div className="flex flex-col gap-1.5">
                    {brief.suggested_questions.map((q, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => {
                          onClose();
                          navigate("/app", {
                            state: {
                              question: q,
                              scope: [doc!.source_id],
                            },
                          });
                        }}
                        className="group flex items-center justify-between gap-2 rounded-xl border border-ink-200/80 bg-white p-2.5 text-left text-xs text-ink-800 shadow-soft transition hover:-translate-y-0.5 hover:border-brand-400 hover:bg-brand-50/50 hover:text-brand-900 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-200 dark:hover:border-brand-700 dark:hover:bg-brand-950/30"
                      >
                        <span className="font-medium">{q}</span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-ink-400 transition group-hover:translate-x-0.5 group-hover:text-brand-600" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Key Takeaways & Core Findings */}
              {brief?.takeaways && brief.takeaways.length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Key Takeaways & Core Findings
                  </span>
                  <div className="space-y-1.5">
                    {brief.takeaways.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2.5 rounded-xl border border-ink-200/70 bg-ink-50/40 p-3 text-xs leading-relaxed text-ink-800 dark:border-ink-800/80 dark:bg-ink-900/40 dark:text-ink-200"
                      >
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 font-bold text-[10px]">✓</span>
                        <div className="flex-1">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item}</ReactMarkdown>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Full Executive Brief Prose */}
              <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-soft dark:border-ink-800 dark:bg-ink-900/60 prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {brief?.summary ? `### Executive Summary\n${brief.summary}\n\n${brief.structure ? `### Structure & Core Themes\n${brief.structure.join("\n\n")}` : ""}` : markdownText}
                </ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center">
              <Sparkles className="mx-auto mb-3 h-10 w-10 text-brand-500 opacity-80" />
              <h4 className="text-base font-semibold text-ink-900 dark:text-ink-100">No Executive Briefing Yet</h4>
              <p className="mt-1 max-w-sm mx-auto text-xs text-ink-500">
                Generate an AI-powered executive briefing with thesis headline, key takeaways, chapter structure, and suggested inquiries.
              </p>
              <div className="mt-5">
                <Button
                  onClick={handleGenerateSummary}
                  loading={summarizing}
                  icon={<Sparkles className="h-4 w-4" />}
                >
                  Generate Executive Briefing
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}

function TagModal({
  open,
  doc,
  workspaceTags,
  onClose,
  onSave,
}: {
  open: boolean;
  doc: DocumentInfo | null;
  workspaceTags: string[];
  onClose: () => void;
  onSave: (sourceId: string, tags: string[]) => Promise<void>;
}) {
  const [tags, setTags] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (doc) {
      setTags(doc.tags ?? []);
      setInput("");
    }
  }, [doc, open]);

  if (!doc) return null;

  const addTag = (tagToAdd: string) => {
    const cleaned = tagToAdd.trim();
    if (!cleaned || tags.some((t) => t.toLowerCase() === cleaned.toLowerCase())) return;
    setTags([...tags, cleaned]);
    setInput("");
  };

  const removeTag = (tagToRemove: string) => {
    setTags(tags.filter((t) => t.toLowerCase() !== tagToRemove.toLowerCase()));
  };

  const save = async () => {
    setBusy(true);
    try {
      await onSave(doc.source_id, tags);
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const unusedWorkspaceTags = workspaceTags.filter(
    (wt) => !tags.some((t) => t.toLowerCase() === wt.toLowerCase())
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Tags for ${doc.source_name}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} loading={busy}>Save tags</Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-xs text-ink-500">
          Organize documents into structured collections (e.g. Legal, Financial, Guidelines) to filter in the Library and Ask search scope.
        </p>

        <div className="flex min-h-[42px] flex-wrap items-center gap-1.5 rounded-xl border border-ink-200 p-2 dark:border-ink-700">
          {tags.length === 0 ? (
            <span className="text-xs text-ink-400">No tags added yet.</span>
          ) : (
            tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800 dark:bg-brand-950/60 dark:text-brand-300"
              >
                <Tag className="h-3 w-3" />
                {tag}
                <button
                  type="button"
                  onClick={() => removeTag(tag)}
                  className="ml-0.5 rounded p-0.5 hover:bg-brand-200/50 dark:hover:bg-brand-800"
                  aria-label={`Remove ${tag}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            addTag(input);
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="New tag name (e.g. Legal)"
            maxLength={50}
            className="flex-1 rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-soft focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-500/10 dark:border-ink-800 dark:bg-ink-900"
          />
          <Button
            type="submit"
            variant="secondary"
            disabled={!input.trim()}
            icon={<Plus className="h-3.5 w-3.5" />}
          >
            Add
          </Button>
        </form>

        {unusedWorkspaceTags.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">Existing tags</p>
            <div className="flex flex-wrap gap-1.5">
              {unusedWorkspaceTags.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => addTag(t)}
                  className="inline-flex items-center gap-1 rounded-lg border border-dashed border-ink-300 px-2 py-1 text-xs text-ink-600 hover:border-brand-500 hover:text-brand-700 dark:border-ink-700 dark:text-ink-300 dark:hover:border-brand-400 dark:hover:text-brand-300"
                >
                  <Plus className="h-3 w-3" />
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

function BulkTagModal({
  open,
  selectedCount,
  workspaceTags,
  onClose,
  onApply,
}: {
  open: boolean;
  selectedCount: number;
  workspaceTags: string[];
  onClose: () => void;
  onApply: (tagsToAdd: string[]) => Promise<void>;
}) {
  const [tags, setTags] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setTags([]);
      setInput("");
    }
  }, [open]);

  const addTag = (tagToAdd: string) => {
    const cleaned = tagToAdd.trim();
    if (!cleaned || tags.some((t) => t.toLowerCase() === cleaned.toLowerCase())) return;
    setTags([...tags, cleaned]);
    setInput("");
  };

  const removeTag = (tagToRemove: string) => {
    setTags(tags.filter((t) => t.toLowerCase() !== tagToRemove.toLowerCase()));
  };

  const save = async () => {
    if (tags.length === 0) return;
    setBusy(true);
    try {
      await onApply(tags);
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const unusedWorkspaceTags = workspaceTags.filter(
    (wt) => !tags.some((t) => t.toLowerCase() === wt.toLowerCase())
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Add tags to ${selectedCount} document${selectedCount === 1 ? "" : "s"}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} loading={busy} disabled={tags.length === 0}>Apply tags</Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-xs text-ink-500">
          The tags below will be added to all {selectedCount} selected documents.
        </p>

        <div className="flex min-h-[42px] flex-wrap items-center gap-1.5 rounded-xl border border-ink-200 p-2 dark:border-ink-700">
          {tags.length === 0 ? (
            <span className="text-xs text-ink-400">Add tags below to apply them.</span>
          ) : (
            tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800 dark:bg-brand-950/60 dark:text-brand-300"
              >
                <Tag className="h-3 w-3" />
                {tag}
                <button
                  type="button"
                  onClick={() => removeTag(tag)}
                  className="ml-0.5 rounded p-0.5 hover:bg-brand-200/50 dark:hover:bg-brand-800"
                  aria-label={`Remove ${tag}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            addTag(input);
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="New tag name (e.g. Guidelines)"
            maxLength={50}
            className="flex-1 rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-soft focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-500/10 dark:border-ink-800 dark:bg-ink-900"
          />
          <Button
            type="submit"
            variant="secondary"
            disabled={!input.trim()}
            icon={<Plus className="h-3.5 w-3.5" />}
          >
            Add
          </Button>
        </form>

        {unusedWorkspaceTags.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">Existing tags</p>
            <div className="flex flex-wrap gap-1.5">
              {unusedWorkspaceTags.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => addTag(t)}
                  className="inline-flex items-center gap-1 rounded-lg border border-dashed border-ink-300 px-2 py-1 text-xs text-ink-600 hover:border-brand-500 hover:text-brand-700 dark:border-ink-700 dark:text-ink-300 dark:hover:border-brand-400 dark:hover:text-brand-300"
                >
                  <Plus className="h-3 w-3" />
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

export function LibraryPage() {
  const toast = useToast();
  const { config } = useAuth();
  const { current } = useWorkspace();
  const canManage = current?.role === "owner" || current?.role === "admin";
  const canTag = current?.role !== "viewer";
  const documents = useApi<DocumentsResponse>("/documents");
  const [job, setJob] = useState<Job | null>(null);
  const [upload, setUpload] = useState<{ names: string[]; fraction: number } | null>(null);
  const [rejected, setRejected] = useState<{ filename: string; error: string }[]>([]);
  const [failed, setFailed] = useState<FailedFile[]>([]);
  const [query, setQuery] = useState("");
  const [viewing, setViewing] = useState<DocumentInfo | null>(null);
  const [deleting, setDeleting] = useState<DocumentInfo | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [deletingSelected, setDeletingSelected] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [podcastOpen, setPodcastOpen] = useState(false);
  const [podcastDocIds, setPodcastDocIds] = useState<string[]>([]);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [taggingDoc, setTaggingDoc] = useState<DocumentInfo | null>(null);
  const [bulkTagging, setBulkTagging] = useState(false);
  const replaceInput = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState<DocumentInfo | null>(null);

  const replaceWith = async (file: File | undefined) => {
    const doc = replacing;
    setReplacing(null);
    if (!file || !doc) return;
    try {
      const body = new FormData();
      body.append("file", file, file.name);
      const response = await fetch(`/api/documents/${encodeURIComponent(doc.source_id)}/replace`, {
        method: "POST", body, headers: await authHeaders(),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "Upload failed");
      toast(`Uploaded the new version of ${doc.source_name}`);
      await startIndexing();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  const reloadDocuments = documents.reload;

  // Pick up a job that is still running (e.g. after a page reload).
  useEffect(() => {
    api<{ jobs: Job[] }>("/jobs?active=true").then((r) => r.jobs[0] && setJob(r.jobs[0])).catch(() => {});
  }, []);

  const startIndexing = useCallback(async (full = false) => {
    try {
      const { job: started } = await api<{ job: Job }>(`/documents/index?wait=false&full=${full}`, { method: "POST" });
      setJob(started);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }, [toast]);

  const active = job && (job.status === "queued" || job.status === "running");
  useInterval(async () => {
    if (!job) return;
    try {
      const next = await api<Job>(`/jobs/${job.id}`);
      setJob(next);
      if (next.status === "done") {
        const result = next.result!;
        setFailed(result.failed);
        reloadDocuments();
        if (result.new_documents.length) toast(`Added ${result.new_documents.length} document${result.new_documents.length === 1 ? "" : "s"}`);
        else if (!result.failed.length) toast("Everything is already indexed");
      } else if (next.status === "failed") {
        toast(next.error ?? "Indexing failed", "error");
      }
    } catch {
      // keep polling; a brief network hiccup shouldn't stop progress updates
    }
  }, 1000, Boolean(active));

  const onFiles = async (files: File[]) => {
    if (!files.length || !config) return;
    const tooBig = files.filter((f) => f.size > config.max_upload_mb * 1024 * 1024);
    const wrongType = files.filter((f) => !config.file_types.includes(f.name.split(".").pop()?.toLowerCase() ?? ""));
    const ok = files.filter((f) => !tooBig.includes(f) && !wrongType.includes(f));
    const clientErrors = [
      ...tooBig.map((f) => ({ filename: f.name, error: `Larger than ${config.max_upload_mb} MB.` })),
      ...wrongType.map((f) => ({ filename: f.name, error: `This file type isn't supported. Use ${config.file_types.map((t) => t.toUpperCase()).join(", ")}.` })),
    ];
    setRejected(clientErrors);
    setFailed([]);
    if (!ok.length) return;
    setUpload({ names: ok.map((f) => f.name), fraction: 0 });
    try {
      // The server takes a limited number of files per request, so send them in batches.
      const size = config.max_files_per_upload || 20;
      const errors = [...clientErrors];
      let saved = 0;
      for (let start = 0; start < ok.length; start += size) {
        const batch = ok.slice(start, start + size);
        const result = await uploadFiles(batch, (fraction) =>
          setUpload((u) => u && { ...u, fraction: (start + fraction * batch.length) / ok.length }));
        errors.push(...result.errors);
        saved += result.saved.length;
      }
      setRejected(errors);
      if (saved) await startIndexing();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setUpload(null);
    }
  };

  const handleSaveTags = async (sourceId: string, tags: string[]) => {
    try {
      await api<{ source_id: string; tags: string[] }>(`/documents/${encodeURIComponent(sourceId)}/tags`, {
        method: "PATCH",
        json: { tags },
      });
      toast("Tags updated");
      documents.reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const handleBulkApplyTags = async (tagsToAdd: string[]) => {
    try {
      await Promise.all(
        selected.map(async (id) => {
          const doc = data?.documents.find((d) => d.source_id === id);
          const currentTags = doc?.tags ?? [];
          const merged = Array.from(new Set([...currentTags, ...tagsToAdd]));
          return api(`/documents/${encodeURIComponent(id)}/tags`, {
            method: "PATCH",
            json: { tags: merged },
          });
        })
      );
      toast(`Added tags to ${selected.length} document${selected.length === 1 ? "" : "s"}`);
      setSelected([]);
      documents.reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const data = documents.data;
  const workspaceTags = data?.tags ?? Array.from(
    new Set((data?.documents ?? []).flatMap((d) => d.tags ?? []))
  ).sort();

  const shown = (data?.documents ?? []).filter((d) => {
    const matchesName = d.source_name.toLowerCase().includes(query.toLowerCase());
    const matchesTag = !selectedTag || (d.tags ?? []).some((t) => t.toLowerCase() === selectedTag.toLowerCase());
    return matchesName && matchesTag;
  });

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader icon={<FolderOpen className="h-5 w-5" />} title="Library"
        description={<>Documents in <span className="font-medium text-ink-700 dark:text-ink-300">{current?.name}</span>. Everyone in this workspace can search them.</>} />
      {data && data.documents.length > 0 && (
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <Stat label="Documents" value={data.documents.length} icon={<FileStack className="h-4 w-4" />}
            hint={`${data.documents.filter((d) => d.ocr).length} read with OCR`} />
          <Stat label="Passages" value={data.indexed_chunks.toLocaleString()} icon={<TextQuote className="h-4 w-4" />} tone="violet"
            hint="Searchable pieces of text" />
          <Stat label="Storage" value={formatSize(data.storage.used_bytes) || "0 KB"} icon={<HardDrive className="h-4 w-4" />} tone="blue"
            hint={data.storage.quota_bytes ? (
              <span className="block">
                <span className="mb-1.5 block"><ProgressBar value={data.storage.used_bytes / data.storage.quota_bytes} /></span>
                of {formatSize(data.storage.quota_bytes)}
              </span>
            ) : "No limit"} />
        </div>
      )}

      <div className="mt-6 space-y-4">
        {canManage && (
          <DropZone onFiles={onFiles} accept={config?.file_types ?? []} maxMb={config?.max_upload_mb ?? 15}
            disabled={Boolean(upload) || Boolean(active)} compact={Boolean(data?.documents.length)} />
        )}
        {data && !data.ocr.available && (
          <p className="text-xs text-ink-500">
            <ScanText className="mr-1 inline h-3.5 w-3.5" />
            OCR is off on this server, so scans and photos can't be read yet. {data.ocr.reason}
          </p>
        )}

        {upload && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <Upload className="h-5 w-5 text-brand-600" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">Uploading {upload.names.length === 1 ? upload.names[0] : `${upload.names.length} files`}…</p>
                <div className="mt-2"><ProgressBar value={upload.fraction} /></div>
              </div>
              <span className="text-sm tabular-nums text-ink-500">{Math.round(upload.fraction * 100)}%</span>
            </div>
          </Card>
        )}

        {job && active && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-brand-600" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{jobLabel(job)}</p>
                <div className="mt-2"><ProgressBar value={jobFraction(job)} /></div>
                <p className="mt-1.5 text-xs text-ink-500">You can keep using AfriSearch; new documents become searchable when this finishes.</p>
              </div>
            </div>
          </Card>
        )}

        {[...rejected, ...failed].length > 0 && (
          <Card className="divide-y divide-ink-100 dark:divide-ink-800">
            <p className="flex items-center gap-2 px-4 py-3 text-sm font-semibold text-red-700 dark:text-red-400">
              <AlertCircle className="h-4 w-4" /> Some files weren't added
            </p>
            {rejected.map((item, i) => (
              <div key={`r${i}`} className="px-4 py-2.5 text-sm">
                <span className="font-medium">{item.filename}</span> <span className="text-ink-500">— {item.error}</span>
              </div>
            ))}
            {failed.map((item) => (
              <div key={item.source_id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <span className="min-w-0 flex-1"><span className="font-medium">{item.filename}</span> <span className="text-ink-500">— {item.error}</span></span>
                <Button size="sm" variant="ghost" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={async () => {
                  await api(`/documents/${encodeURIComponent(item.source_id)}`, { method: "DELETE" }).catch(() => {});
                  setFailed((all) => all.filter((f) => f.source_id !== item.source_id));
                }}>Remove</Button>
              </div>
            ))}
          </Card>
        )}

        {data && data.stale_documents > 0 && !active && (
          <Alert tone="amber" title="Re-indexing needed"
            action={<Button size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => startIndexing()}>Re-index now</Button>}>
            {data.stale_documents} document(s) were indexed with different search settings and are left out of search.
          </Alert>
        )}
        {data && data.unindexed_files > 0 && !active && !failed.length && (
          <Alert tone="blue" action={<Button size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => startIndexing()}>Index now</Button>}>
            {data.unindexed_files} uploaded file(s) aren't searchable yet.
          </Alert>
        )}
      </div>

      <div className="mt-8">
        {documents.loading && !data ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : !data?.documents.length ? (
          <EmptyState icon={<FileUp className="h-6 w-6" />} title="No documents yet">
            Upload reports, guides, manuals, policies or photos of printed pages. AfriSearch reads them and answers questions with citations.
          </EmptyState>
        ) : (
          <>
            {workspaceTags.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 flex items-center gap-1 text-xs font-medium text-ink-500">
                  <Tag className="h-3.5 w-3.5" /> Collections:
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedTag(null)}
                  className={cx(
                    "rounded-lg px-2.5 py-1 text-xs font-medium transition",
                    selectedTag === null
                      ? "bg-brand-600 text-white shadow-sm"
                      : "bg-ink-100 text-ink-700 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                  )}
                >
                  All ({data.documents.length})
                </button>
                {workspaceTags.map((tag) => {
                  const count = data.documents.filter((d) => (d.tags ?? []).some((t) => t.toLowerCase() === tag.toLowerCase())).length;
                  const isSelected = selectedTag?.toLowerCase() === tag.toLowerCase();
                  return (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => setSelectedTag(isSelected ? null : tag)}
                      className={cx(
                        "inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium transition",
                        isSelected
                          ? "bg-brand-600 text-white shadow-sm"
                          : "bg-ink-100 text-ink-700 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                      )}
                    >
                      <span>{tag}</span>
                      <span className={cx("rounded-full px-1.5 py-0.2 text-[10px]", isSelected ? "bg-white/20 text-white" : "bg-ink-200 text-ink-600 dark:bg-ink-700 dark:text-ink-400")}>
                        {count}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="mb-3 flex items-center gap-3">
              <div className="relative flex-1 sm:max-w-xs">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by name" aria-label="Filter documents by name"
                  className="w-full rounded-xl border border-ink-200 bg-white py-2 pl-9 pr-3 text-sm shadow-soft focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-500/10 dark:border-ink-800 dark:bg-ink-900 dark:shadow-none" />
              </div>
              <span className="text-sm text-ink-500">{shown.length} of {data.documents.length}</span>
              {selected.length > 0 && (
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-sm text-ink-500">{selected.length} selected</span>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Headphones className="h-3.5 w-3.5 text-indigo-500" />}
                    onClick={() => {
                      setPodcastDocIds(selected);
                      setPodcastOpen(true);
                    }}
                    title="Generate AI 2-host audio briefing from selected documents"
                  >
                    Audio overview
                  </Button>
                  <Button
                    size="sm"
                    variant={selected.length >= 2 ? "primary" : "secondary"}
                    icon={<GitCompare className="h-3.5 w-3.5" />}
                    onClick={() => setComparing(true)}
                  >
                    {selected.length >= 2 ? `Compare ${selected.length} documents` : "Compare with..."}
                  </Button>
                  {canTag && <Button size="sm" variant="secondary" icon={<Tag className="h-3.5 w-3.5" />} onClick={() => setBulkTagging(true)}>Tag selected</Button>}
                  {canManage && <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeletingSelected(true)}>Delete selected</Button>}
                  <Button size="sm" variant="ghost" onClick={() => setSelected([])}>Clear</Button>
                </div>
              )}
            </div>
            <Card className="overflow-hidden">
              <table className="w-full text-sm">
                <thead className="hidden border-b border-ink-100 bg-ink-50 text-left text-xs font-medium uppercase tracking-wide text-ink-500 dark:border-ink-800 dark:bg-ink-900/60 sm:table-header-group">
                  <tr>
                    <th className="w-10 pl-4">
                      <input type="checkbox" aria-label="Select all shown documents" className="h-4 w-4 rounded accent-brand-700"
                        checked={shown.length > 0 && shown.every((d) => selected.includes(d.source_id))}
                        onChange={(e) => setSelected(e.target.checked ? shown.map((d) => d.source_id) : [])} />
                    </th>
                    <th className="px-4 py-2.5">Document</th>
                    <th className="px-4 py-2.5">Pages</th>
                    <th className="px-4 py-2.5">Passages</th>
                    <th className="px-4 py-2.5">Size</th>
                    <th className="px-4 py-2.5">Added</th>
                    <th className="w-12 px-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                  {shown.slice(0, limit).map((doc) => (
                    <tr key={doc.source_id} className={cx("transition hover:bg-ink-50 dark:hover:bg-ink-800/40", selected.includes(doc.source_id) && "bg-brand-50/60 dark:bg-brand-950/30")}>
                      <td className="hidden w-10 pl-4 sm:table-cell">
                        <input type="checkbox" aria-label={`Select ${doc.source_name}`} className="h-4 w-4 rounded accent-brand-700"
                          checked={selected.includes(doc.source_id)}
                          onChange={(e) => setSelected((all) => e.target.checked ? [...all, doc.source_id] : all.filter((id) => id !== doc.source_id))} />
                      </td>
                      <td className="px-4 py-3">
                        <button type="button" onClick={() => setViewing(doc)} className="flex min-w-0 items-center gap-2.5 text-left">
                          <FileTile name={doc.source_name} />
                          <span className="min-w-0">
                            <span className="block truncate font-medium hover:text-brand-700 dark:hover:text-brand-400">{doc.source_name}</span>
                            <span className="flex flex-wrap items-center gap-1.5 text-xs text-ink-500">
                              {doc.type.toUpperCase()}
                              {doc.ocr && <Badge tone="blue"><ScanText className="h-3 w-3" />OCR</Badge>}
                              {doc.summary && (
                                <span
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setViewing(doc);
                                  }}
                                  title="Executive Briefing Ready"
                                  className="inline-flex cursor-pointer items-center gap-0.5 rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700 hover:bg-amber-100 dark:bg-amber-950/60 dark:text-amber-300 dark:hover:bg-amber-900/60"
                                >
                                  <Sparkles className="h-2.5 w-2.5 text-amber-600" />
                                  Brief
                                </span>
                              )}
                              {(doc.tags ?? []).map((t) => (
                                <span
                                  key={t}
                                  onClick={(e) => { e.stopPropagation(); setSelectedTag(t); }}
                                  title={`Filter by collection: ${t}`}
                                  className="inline-flex cursor-pointer items-center gap-0.5 rounded-md bg-brand-50 px-1.5 py-0.5 text-[11px] font-medium text-brand-700 hover:bg-brand-100 dark:bg-brand-950/60 dark:text-brand-300 dark:hover:bg-brand-900/60"
                                >
                                  <Tag className="h-2.5 w-2.5" />
                                  {t}
                                </span>
                              ))}
                              <span className="sm:hidden">· {doc.passages} passages · {formatSize(doc.bytes)}</span>
                            </span>
                          </span>
                        </button>
                      </td>
                      <td className="hidden px-4 py-3 tabular-nums text-ink-600 dark:text-ink-400 sm:table-cell">{doc.pages ?? "–"}</td>
                      <td className="hidden px-4 py-3 tabular-nums text-ink-600 dark:text-ink-400 sm:table-cell">{doc.passages}</td>
                      <td className="hidden px-4 py-3 tabular-nums text-ink-600 dark:text-ink-400 sm:table-cell">{formatSize(doc.bytes)}</td>
                      <td className="hidden px-4 py-3 text-ink-600 dark:text-ink-400 sm:table-cell">{timeAgo(doc.uploaded_at)}</td>
                      <td className="px-2 py-3">
                        <Popover align="right" width="w-48" trigger={({ toggle }) => (
                          <IconButton label={`Actions for ${doc.source_name}`} onClick={toggle}><MoreHorizontal className="h-4 w-4" /></IconButton>
                        )}>
                          {(close) => (
                            <>
                              <MenuItem icon={<Sparkles className="h-4 w-4 text-brand-600" />} onClick={() => { close(); setViewing(doc); }}>Executive briefing</MenuItem>
                              <MenuItem icon={<Headphones className="h-4 w-4 text-indigo-600" />} onClick={() => { close(); setPodcastDocIds([doc.source_id]); setPodcastOpen(true); }}>Audio overview</MenuItem>
                              <MenuItem icon={<Search className="h-4 w-4" />} onClick={() => { close(); setViewing(doc); }}>Read passages</MenuItem>
                              <MenuItem icon={<GitCompare className="h-4 w-4" />} onClick={() => { close(); setSelected([doc.source_id]); setComparing(true); }}>Compare documents</MenuItem>
                              {canTag && <MenuItem icon={<Tag className="h-4 w-4" />} onClick={() => { close(); setTaggingDoc(doc); }}>Edit tags</MenuItem>}
                              <MenuItem icon={<ExternalLink className="h-4 w-4" />} onClick={() => { close(); openDocument(doc.source_id).catch((e: Error) => toast(e.message, "error")); }}>Open original</MenuItem>
                              {canManage && <MenuItem icon={<FilePlus2 className="h-4 w-4" />} onClick={() => { close(); setReplacing(doc); replaceInput.current?.click(); }}>Upload new version</MenuItem>}
                              {canManage && <MenuItem danger icon={<Trash2 className="h-4 w-4" />} onClick={() => { close(); setDeleting(doc); }}>Delete</MenuItem>}
                            </>
                          )}
                        </Popover>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            {shown.length > limit && (
              <div className="mt-3 text-center">
                <Button size="sm" onClick={() => setLimit((n) => n + PAGE_SIZE)}>
                  Show more ({shown.length - limit} left)
                </Button>
              </div>
            )}
            {data.ocr.available && (
              <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-500">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Scans and photos are read with OCR ({data.ocr.languages.join(", ")}).
              </p>
            )}
          </>
        )}
      </div>

      <PassagesDrawer
        doc={viewing}
        onClose={() => setViewing(null)}
        onOpenPodcast={(docIds) => {
          setPodcastDocIds(docIds);
          setPodcastOpen(true);
        }}
      />
      <input ref={replaceInput} type="file" hidden accept={(config?.file_types ?? []).map((ext) => `.${ext}`).join(",")}
        onChange={(e) => { replaceWith(e.target.files?.[0]); e.target.value = ""; }} />
      <ConfirmDialog
        open={deletingSelected}
        title={`Delete ${selected.length} document${selected.length === 1 ? "" : "s"}?`}
        confirmLabel="Delete documents"
        onClose={() => setDeletingSelected(false)}
        onConfirm={async () => {
          const results = await Promise.allSettled(selected.map((id) =>
            api(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" })));
          const failed = results.filter((r) => r.status === "rejected").length;
          toast(failed ? `${failed} couldn't be deleted` : `Deleted ${selected.length} documents`, failed ? "error" : "success");
          setSelected([]);
          documents.reload();
        }}
      >
        They'll be removed for everyone in this workspace. Answers that cited them keep their quoted passages.
      </ConfirmDialog>
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete document?"
        confirmLabel="Delete document"
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          try {
            await api(`/documents/${encodeURIComponent(deleting!.source_id)}`, { method: "DELETE" });
            toast(`Deleted ${deleting!.source_name}`);
            documents.reload();
          } catch (e) {
            toast((e as Error).message, "error");
          }
        }}
      >
        <strong className="text-ink-900 dark:text-white">{deleting?.source_name}</strong> will be removed for everyone in this workspace. Answers that cited it keep their quoted passages.
      </ConfirmDialog>
      <TagModal
        open={Boolean(taggingDoc)}
        doc={taggingDoc}
        workspaceTags={workspaceTags}
        onClose={() => setTaggingDoc(null)}
        onSave={handleSaveTags}
      />
      <BulkTagModal
        open={bulkTagging}
        selectedCount={selected.length}
        workspaceTags={workspaceTags}
        onClose={() => setBulkTagging(false)}
        onApply={handleBulkApplyTags}
      />
      <DocumentCompareModal
        open={comparing}
        initialDocIds={selected}
        allDocuments={data?.documents ?? []}
        onClose={() => setComparing(false)}
      />
      <AudioOverviewModal
        open={podcastOpen}
        initialDocIds={podcastDocIds}
        allDocuments={data?.documents ?? []}
        onClose={() => setPodcastOpen(false)}
      />
    </div>
  );
}
