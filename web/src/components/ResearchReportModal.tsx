// Executive Research Dossier & Report Generator Modal
import {
  Copy, Download, FileDown, FileText,
  MessageSquare, Printer, Sparkles, X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { downloadReportDocx, generateReport, type ReportResult } from "../lib/api";
import { useApi } from "../lib/hooks";
import type { DocumentInfo, Provider } from "../lib/types";
import { FileIcon } from "./answer";
import { Badge, Button, IconButton, cx, useToast } from "./ui";

const TEMPLATE_OPTIONS: {
  id: "executive" | "comprehensive" | "review";
  title: string;
  tagline: string;
  desc: string;
  badge: string;
}[] = [
  {
    id: "executive",
    title: "Executive Briefing Memo",
    tagline: "High-impact & action-oriented (~900 words)",
    desc: "Designed for leaders and executives: high-level thesis, critical findings with page citations, risk analysis, and actionable next steps.",
    badge: "Most Popular",
  },
  {
    id: "comprehensive",
    title: "Comprehensive Research Dossier",
    tagline: "Rigorous deep-dive synthesis (~1,600 words)",
    desc: "Multi-section formal dossier: abstract, thematic breakdown, comparative analysis matrix, critical evaluation, and recommendations.",
    badge: "Deep Analysis",
  },
  {
    id: "review",
    title: "Literature & Document Review",
    tagline: "Comparative state of knowledge (~1,200 words)",
    desc: "Source-by-source profiling, areas of consensus vs contradiction, knowledge gaps, and comparative assessment table.",
    badge: "Scholarly",
  },
];

const PRESET_DIRECTIVES = [
  "Focus on strategic opportunities, operational feasibility, and quantifiable metrics.",
  "Highlight financial risks, budget implications, and cost-benefit trade-offs.",
  "Evaluate regulatory compliance, governance risks, and policy standards.",
  "Compare technology readiness, implementation timelines, and resource dependencies.",
];

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function printViaIframe(contentHtml: string, title: string) {
  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.right = "0";
  iframe.style.bottom = "0";
  iframe.style.width = "0";
  iframe.style.height = "0";
  iframe.style.border = "none";
  document.body.appendChild(iframe);

  const doc = iframe.contentWindow?.document;
  if (!doc) return;

  doc.open();
  doc.write(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>${title}</title>
        <style>
          @page { margin: 18mm; size: A4; }
          body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #0f172a;
            line-height: 1.6;
            font-size: 11pt;
            margin: 0;
            padding: 0;
          }
          h1 { font-size: 20pt; margin: 0 0 6px 0; color: #0f172a; border-bottom: 2px solid #0284c7; padding-bottom: 8px; }
          .meta-banner { font-size: 9pt; color: #64748b; margin-bottom: 20px; font-style: italic; }
          .summary-card {
            background: #f8fafc;
            border-left: 4px solid #0284c7;
            padding: 10px 14px;
            margin-bottom: 24px;
            border-radius: 4px;
          }
          .summary-card strong { color: #0369a1; }
          h2 { font-size: 13pt; margin-top: 24px; margin-bottom: 8px; color: #0369a1; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; page-break-after: avoid; }
          h3 { font-size: 11.5pt; margin-top: 16px; margin-bottom: 6px; color: #1e293b; page-break-after: avoid; }
          p { margin: 0 0 10px 0; }
          ul, ol { margin: 0 0 12px 0; padding-left: 20px; }
          li { margin-bottom: 4px; }
          strong { font-weight: 600; color: #0f172a; }
          blockquote {
            border-left: 3px solid #0284c7;
            margin: 12px 0;
            padding: 8px 14px;
            background: #f8fafc;
            font-style: italic;
            color: #334155;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            margin: 14px 0;
            font-size: 9.5pt;
            page-break-inside: avoid;
          }
          th, td {
            border: 1px solid #cbd5e1;
            padding: 6px 10px;
            text-align: left;
          }
          th { background: #f1f5f9; font-weight: 600; }
        </style>
      </head>
      <body>
        ${contentHtml}
      </body>
    </html>
  `);
  doc.close();

  iframe.contentWindow?.focus();
  setTimeout(() => {
    iframe.contentWindow?.print();
    setTimeout(() => {
      if (document.body.contains(iframe)) {
        document.body.removeChild(iframe);
      }
    }, 1000);
  }, 400);
}

export function ResearchReportModal({
  open,
  initialDocIds,
  allDocuments,
  chatMessages,
  onClose,
}: {
  open: boolean;
  initialDocIds?: string[];
  allDocuments?: DocumentInfo[];
  chatMessages?: any[];
  onClose: () => void;
}) {
  const toast = useToast();
  const navigate = useNavigate();

  const [selectedIds, setSelectedIds] = useState<string[]>(initialDocIds ?? []);
  const [template, setTemplate] = useState<"executive" | "comprehensive" | "review">("executive");
  const [customTitle, setCustomTitle] = useState("");
  const [focusPrompt, setFocusPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [exportingDocx, setExportingDocx] = useState(false);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [activeTab, setActiveTab] = useState<"preview" | "markdown">("preview");

  const printableRef = useRef<HTMLDivElement>(null);
  const providers = useApi<{ providers: Provider[]; default: string | null }>("/providers");
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      if (initialDocIds && initialDocIds.length > 0) {
        setSelectedIds(initialDocIds);
      }
    }
  }, [open, initialDocIds]);

  if (!open) return null;

  const currentProvider = selectedProvider ?? providers.data?.default ?? "qwen-small";
  const docsList = allDocuments ?? [];
  const selectedDocs = docsList.filter((d) => selectedIds.includes(d.source_id));

  const handleGenerate = async () => {
    if (selectedIds.length === 0 && (!chatMessages || chatMessages.length === 0)) {
      toast("Please select at least 1 document or provide chat findings", "error");
      return;
    }

    setGenerating(true);
    setResult(null);

    try {
      const data = await generateReport({
        source_ids: selectedIds.length > 0 ? selectedIds : undefined,
        chat_messages: chatMessages && chatMessages.length > 0 ? chatMessages : undefined,
        template,
        title: customTitle.trim() || undefined,
        focus_prompt: focusPrompt.trim() || undefined,
        provider: currentProvider,
      });

      setResult(data);
      setActiveTab("preview");
      toast("Executive dossier generated!");
    } catch (e: any) {
      toast(e.message || "Failed to generate research report", "error");
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadDocx = async () => {
    if (!result) return;
    setExportingDocx(true);
    try {
      await downloadReportDocx({
        title: result.title,
        markdown: result.markdown,
        documents: result.documents,
        metadata: {
          provider: result.provider,
          template: result.template_label,
          created_at: result.created_at,
        },
      });
      toast("Word document (.docx) downloaded!");
    } catch (e: any) {
      toast(e.message || "Failed to download Word document", "error");
    } finally {
      setExportingDocx(false);
    }
  };

  const handlePrint = () => {
    if (!result || !printableRef.current) return;
    printViaIframe(printableRef.current.innerHTML, result.title);
  };

  const handleCopyMarkdown = () => {
    if (!result) return;
    navigator.clipboard.writeText(result.markdown).then(() => {
      toast("Full Markdown dossier copied to clipboard!");
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-ink-950/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal Dialog */}
      <div className="relative flex flex-col w-full max-w-5xl max-h-[92vh] rounded-2xl bg-white shadow-2xl dark:bg-ink-900 border border-ink-200 dark:border-ink-800 overflow-hidden animate-in fade-in-50 zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-ink-100 px-6 py-4 dark:border-ink-800 bg-ink-50/50 dark:bg-ink-900/50">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 text-white shadow-sm">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-ink-900 dark:text-white">
                  Executive Research Dossier & Report Generator
                </h2>
                <Badge tone="blue">Word • PDF • Markdown</Badge>
              </div>
              <p className="text-xs text-ink-500">
                Synthesize findings across documents into publication-grade dossiers with citations and export options.
              </p>
            </div>
          </div>
          <IconButton label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Top Controls: Templates & Options */}
          <div className="rounded-xl border border-ink-200/80 bg-ink-50/40 p-4 dark:border-ink-800 dark:bg-ink-950/40 space-y-4">
            {/* Template Selector Cards */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-ink-600 dark:text-ink-400 mb-2">
                1. Select Report Template
              </label>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {TEMPLATE_OPTIONS.map((tmpl) => {
                  const isSelected = template === tmpl.id;
                  return (
                    <button
                      key={tmpl.id}
                      type="button"
                      onClick={() => setTemplate(tmpl.id)}
                      className={cx(
                        "flex flex-col text-left p-3.5 rounded-xl border transition-all relative",
                        isSelected
                          ? "border-brand-600 bg-brand-50/50 dark:border-brand-400 dark:bg-brand-950/30 ring-2 ring-brand-500/20"
                          : "border-ink-200 bg-white hover:border-ink-300 dark:border-ink-800 dark:bg-ink-900 dark:hover:border-ink-700"
                      )}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-xs text-ink-900 dark:text-white">
                          {tmpl.title}
                        </span>
                        <span
                          className={cx(
                            "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                            isSelected
                              ? "bg-brand-600 text-white"
                              : "bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-400"
                          )}
                        >
                          {tmpl.badge}
                        </span>
                      </div>
                      <span className="text-[11px] font-medium text-brand-700 dark:text-brand-300 mb-1">
                        {tmpl.tagline}
                      </span>
                      <p className="text-[11px] leading-relaxed text-ink-500 dark:text-ink-400">
                        {tmpl.desc}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Report Title, Focus Directive & Provider Selector */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
              <div className="sm:col-span-2 space-y-3">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-ink-700 dark:text-ink-300">
                      Report Title (Optional)
                    </label>
                    <span className="text-[11px] text-ink-400">Leave blank for AI auto-title</span>
                  </div>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    placeholder="e.g. East Africa Grid Integration & Renewable Strategy 2026"
                    className="w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-xs shadow-soft focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-ink-700 dark:bg-ink-900"
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-ink-700 dark:text-ink-300">
                      Custom Focus Directive (Optional)
                    </label>
                    <span className="text-[11px] text-ink-400">Tailors analysis to specific priorities</span>
                  </div>
                  <input
                    type="text"
                    value={focusPrompt}
                    onChange={(e) => setFocusPrompt(e.target.value)}
                    placeholder="e.g. Focus on regulatory compliance, risk factors, and financial projections..."
                    className="w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-xs shadow-soft focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-ink-700 dark:bg-ink-900"
                  />
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {PRESET_DIRECTIVES.map((preset, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => setFocusPrompt(preset)}
                        className="rounded-lg bg-ink-100 px-2 py-0.5 text-[10px] text-ink-600 hover:bg-brand-50 hover:text-brand-700 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-brand-950 dark:hover:text-brand-300 transition"
                      >
                        + {preset.slice(0, 36)}...
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-ink-700 dark:text-ink-300">
                  AI Model
                </label>
                <select
                  value={currentProvider}
                  onChange={(e) => setSelectedProvider(e.target.value)}
                  className="w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-xs shadow-soft focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-ink-700 dark:bg-ink-900"
                >
                  {(providers.data?.providers ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label || p.id} ({p.kind === "local" ? "Local CPU" : "Cloud"})
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-ink-400">
                  Runs on all cloud providers & local CPU offline.
                </p>
              </div>
            </div>

            {/* Document Sources Badge List */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-200/60 pt-3 dark:border-ink-800">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-medium text-ink-500">Sources included:</span>
                {selectedDocs.length > 0 ? (
                  selectedDocs.map((d) => (
                    <span
                      key={d.source_id}
                      className="inline-flex items-center gap-1 rounded-lg bg-white px-2 py-0.5 text-xs font-medium text-ink-700 shadow-xs border border-ink-200 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-300"
                    >
                      <FileIcon name={d.source_name} />
                      <span className="max-w-[150px] truncate">{d.source_name}</span>
                      <button
                        type="button"
                        onClick={() => setSelectedIds((all) => all.filter((id) => id !== d.source_id))}
                        className="text-ink-400 hover:text-ink-700 dark:hover:text-white"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))
                ) : chatMessages && chatMessages.length > 0 ? (
                  <Badge tone="blue">Active Chat Conversation & Cited Passages</Badge>
                ) : (
                  <span className="text-xs text-amber-600">No documents selected</span>
                )}
              </div>

              <Button
                variant="primary"
                onClick={handleGenerate}
                loading={generating}
                disabled={generating || (selectedIds.length === 0 && (!chatMessages || chatMessages.length === 0))}
                icon={<Sparkles className="h-3.5 w-3.5" />}
              >
                {generating ? "Synthesizing Dossier..." : "Generate Executive Dossier"}
              </Button>
            </div>
          </div>

          {/* Generated Result View */}
          {result && (
            <div className="space-y-4 animate-fade-in">
              {/* Report Action Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-200 pb-3 dark:border-ink-800">
                <div className="flex items-center gap-2">
                  <div className="flex items-center rounded-lg bg-ink-100 p-0.5 text-xs font-medium dark:bg-ink-800">
                    <button
                      type="button"
                      onClick={() => setActiveTab("preview")}
                      className={cx(
                        "rounded-md px-3 py-1 transition",
                        activeTab === "preview"
                          ? "bg-white text-ink-900 shadow-xs font-semibold dark:bg-ink-700 dark:text-white"
                          : "text-ink-600 hover:text-ink-900 dark:text-ink-400 dark:hover:text-white"
                      )}
                    >
                      Executive Layout
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("markdown")}
                      className={cx(
                        "rounded-md px-3 py-1 transition",
                        activeTab === "markdown"
                          ? "bg-white text-ink-900 shadow-xs font-semibold dark:bg-ink-700 dark:text-white"
                          : "text-ink-600 hover:text-ink-900 dark:text-ink-400 dark:hover:text-white"
                      )}
                    >
                      Markdown Source
                    </button>
                  </div>
                  <span className="text-xs text-ink-400">
                    {result.word_count} words · ~{result.reading_time_minutes} min read
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Printer className="h-3.5 w-3.5 text-brand-600" />}
                    onClick={handlePrint}
                    title="Print or Save as PDF using clean document layout"
                  >
                    Print / PDF
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<FileText className="h-3.5 w-3.5 text-blue-600" />}
                    onClick={handleDownloadDocx}
                    loading={exportingDocx}
                    title="Export as native Microsoft Word document (.docx)"
                  >
                    Download .docx
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Download className="h-3.5 w-3.5" />}
                    onClick={() => downloadBlob(`${result.title.replace(/\s+/g, "_")}.md`, result.markdown, "text/markdown")}
                    title="Download Markdown file"
                  >
                    .md
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Copy className="h-3.5 w-3.5" />}
                    onClick={handleCopyMarkdown}
                    title="Copy full markdown"
                  >
                    Copy
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<MessageSquare className="h-3.5 w-3.5 text-brand-600" />}
                    onClick={() => {
                      onClose();
                      navigate("/app", {
                        state: {
                          question: `Based on the executive dossier '${result.title}', what are the key risks and strategic next steps?`,
                          scope: result.source_ids,
                        },
                      });
                    }}
                    title="Discuss report findings in Chat"
                  >
                    Discuss in Chat
                  </Button>
                </div>
              </div>

              {/* View 1: Executive Styled Preview (Printable) */}
              {activeTab === "preview" && (
                <div
                  ref={printableRef}
                  className="rounded-2xl border border-ink-200/90 bg-white p-8 shadow-sm dark:border-ink-800 dark:bg-ink-950 font-sans"
                >
                  {/* Document Header */}
                  <div className="border-b-2 border-brand-600 pb-4 mb-6">
                    <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-brand-700 dark:text-brand-400 mb-1">
                      <span>{result.template_label}</span>
                      <span className="font-normal text-ink-400 lowercase">
                        generated via {result.provider}
                      </span>
                    </div>
                    <h1 className="text-2xl font-bold tracking-tight text-ink-950 dark:text-white">
                      {result.title}
                    </h1>
                    <div className="meta-banner mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-500">
                      <span>{new Date(result.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}</span>
                      <span>•</span>
                      <span>{result.word_count} words</span>
                      <span>•</span>
                      <span>~{result.reading_time_minutes} min read</span>
                      <span>•</span>
                      <span>{result.documents.length} Source Document{result.documents.length === 1 ? "" : "s"}</span>
                    </div>
                  </div>

                  {/* Executive Summary Callout */}
                  {result.executive_summary && (
                    <div className="summary-card mb-6 rounded-xl border border-brand-200 bg-brand-50/40 p-4 dark:border-brand-900/60 dark:bg-brand-950/20">
                      <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-brand-800 dark:text-brand-300 mb-1">
                        <Sparkles className="h-3.5 w-3.5 text-brand-600" />
                        <span>Executive Summary & Bottom Line</span>
                      </div>
                      <p className="text-sm leading-relaxed text-ink-800 dark:text-ink-200 font-medium">
                        {result.executive_summary}
                      </p>
                    </div>
                  )}

                  {/* Main Rendered Markdown */}
                  <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-headings:tracking-tight prose-h1:text-xl prose-h2:text-lg prose-h2:border-b prose-h2:border-ink-200 prose-h2:pb-1.5 prose-h2:mt-6 prose-h3:text-base prose-p:leading-relaxed prose-table:my-4 prose-th:bg-ink-100 dark:prose-th:bg-ink-800 prose-td:border prose-th:border prose-td:border-ink-200 dark:prose-td:border-ink-800 prose-blockquote:border-l-4 prose-blockquote:border-brand-500 prose-blockquote:bg-ink-50/60 dark:prose-blockquote:bg-ink-900/40 prose-blockquote:py-1 prose-blockquote:px-3">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {result.markdown}
                    </ReactMarkdown>
                  </div>

                  {/* Sources Appendix */}
                  {result.documents.length > 0 && (
                    <div className="mt-10 border-t border-ink-200 pt-6 dark:border-ink-800">
                      <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-900 dark:text-white mb-3">
                        Appendix: Referenced Materials & Indexed Sources
                      </h3>
                      <div className="overflow-x-auto rounded-xl border border-ink-200 dark:border-ink-800">
                        <table className="w-full text-left text-xs">
                          <thead className="border-b border-ink-200 bg-ink-50 text-ink-600 dark:border-ink-800 dark:bg-ink-900">
                            <tr>
                              <th className="px-3 py-2 font-semibold">Document Name</th>
                              <th className="px-3 py-2 font-semibold">Pages</th>
                              <th className="px-3 py-2 font-semibold">Indexed Passages</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                            {result.documents.map((d, i) => (
                              <tr key={i} className="hover:bg-ink-50/50 dark:hover:bg-ink-900/50">
                                <td className="px-3 py-2 font-medium text-ink-900 dark:text-white flex items-center gap-1.5">
                                  <FileIcon name={d.source_name} />
                                  <span>{d.source_name}</span>
                                </td>
                                <td className="px-3 py-2 text-ink-600 dark:text-ink-400 tabular-nums">
                                  {d.pages}
                                </td>
                                <td className="px-3 py-2 text-ink-600 dark:text-ink-400 tabular-nums">
                                  {d.passages_count ?? "–"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* View 2: Raw Markdown Source */}
              {activeTab === "markdown" && (
                <div className="rounded-xl border border-ink-200 bg-ink-950 p-4 text-ink-100 font-mono text-xs dark:border-ink-800">
                  <pre className="whitespace-pre-wrap leading-relaxed overflow-x-auto max-h-[600px]">
                    {result.markdown}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Empty / Initial State */}
          {!result && !generating && (
            <div className="rounded-2xl border border-dashed border-ink-300 py-16 text-center dark:border-ink-700">
              <FileDown className="mx-auto mb-3 h-10 w-10 text-ink-400 opacity-60" />
              <h3 className="font-semibold text-ink-800 dark:text-ink-200">
                Ready to synthesize your research
              </h3>
              <p className="mt-1 text-xs text-ink-500 max-w-md mx-auto">
                Select your desired template, add any optional focus directive, and click Generate Executive Dossier to create a publication-ready document.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
