// Document Compare & Cross-Analysis Matrix Modal
import {
  Copy, Download, FileSpreadsheet, FileText, GitCompare, MessageSquare,
  Sparkles, Table, X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamCompare } from "../lib/api";
import { useApi } from "../lib/hooks";
import type { DocumentInfo, Provider } from "../lib/types";
import { FileIcon } from "./answer";
import { SplitReader, type ActiveReaderTarget } from "./SplitReader";
import { Button, IconButton, Spinner, cx, useToast } from "./ui";

const PRESET_FOCI = [
  { label: "Key Findings & Metrics", focus: "Compare key findings, statistical metrics, performance outcomes, and main results." },
  { label: "Methodology & Framework", focus: "Compare the methodologies, theoretical frameworks, data sources, and investigative approaches." },
  { label: "Financials & Pricing", focus: "Compare revenue, costs, pricing models, budget allocations, and commercial terms." },
  { label: "Risks & Compliance", focus: "Compare risk factors, regulatory compliance, liabilities, limitations, and governance requirements." },
  { label: "Comprehensive Synthesis", focus: "Perform an end-to-end comprehensive comparison across objectives, scope, methodology, results, and recommendations." },
];

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function DocumentCompareModal({
  open,
  initialDocIds,
  allDocuments,
  onClose,
}: {
  open: boolean;
  initialDocIds: string[];
  allDocuments: DocumentInfo[];
  onClose: () => void;
}) {
  const toast = useToast();
  const navigate = useNavigate();
  const [selectedIds, setSelectedIds] = useState<string[]>(initialDocIds);
  const [focus, setFocus] = useState<string>(PRESET_FOCI[0].focus);
  const [streaming, setStreaming] = useState(false);
  const [markdown, setMarkdown] = useState<string>("");
  const [matrixTable, setMatrixTable] = useState<string>("");
  const [matrixCsv, setMatrixCsv] = useState<string>("");
  const [viewTab, setViewTab] = useState<"matrix" | "report">("matrix");
  const [readerTarget, setReaderTarget] = useState<ActiveReaderTarget | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const providers = useApi<{ providers: Provider[]; default: string | null }>("/providers");
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setSelectedIds(initialDocIds.length >= 2 ? initialDocIds : initialDocIds.slice(0, 5));
      setMarkdown("");
      setMatrixTable("");
      setMatrixCsv("");
      setReaderTarget(null);
      setStreaming(false);
    }
  }, [open, initialDocIds]);

  const selectedDocs = allDocuments.filter((d) => selectedIds.includes(d.source_id));
  const availableDocsToAdd = allDocuments.filter((d) => !selectedIds.includes(d.source_id));

  const handleStartComparison = async () => {
    if (selectedIds.length < 2) {
      toast("Please select at least 2 documents to compare.", "error");
      return;
    }

    setStreaming(true);
    setMarkdown("");
    setMatrixTable("");
    setMatrixCsv("");
    setViewTab("matrix");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let accumulated = "";
      for await (const event of streamCompare(
        {
          source_ids: selectedIds,
          focus,
          provider: selectedProvider,
        },
        controller.signal
      )) {
        if (event.type === "token") {
          accumulated += event.text;
          setMarkdown(accumulated);
        } else if (event.type === "done") {
          setMarkdown(event.comparison_markdown);
          setMatrixTable(event.matrix_table);
          setMatrixCsv(event.matrix_csv);
          if (event.matrix_table) {
            setViewTab("matrix");
          } else {
            setViewTab("report");
          }
        } else if (event.type === "error") {
          toast(event.detail, "error");
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        toast(err.message || "Comparison failed", "error");
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const handleOpenInChat = () => {
    onClose();
    navigate("/app", {
      state: {
        question: `Based on the cross-analysis of ${selectedDocs.map((d) => d.source_name).join(" and ")}, what are the most critical takeaways?`,
        scope: selectedIds,
      },
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-ink-950/60 backdrop-blur-sm animate-fade-in">
      <div className="relative flex flex-col w-full max-w-5xl h-[92vh] max-h-[900px] rounded-2xl bg-white shadow-2xl dark:bg-ink-900 border border-ink-200/80 dark:border-ink-800 overflow-hidden">
        
        {/* Header */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-ink-200/80 px-4 sm:px-6 dark:border-ink-800 bg-ink-50/60 dark:bg-ink-950/40">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-gradient text-white shadow-sm">
              <GitCompare className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-ink-900 dark:text-ink-50">Document Cross-Analysis & Comparison Matrix</h2>
              <p className="text-[11px] text-ink-500">Synthesize, contrast, and uncover discrepancies across 2+ documents</p>
            </div>
          </div>
          <IconButton label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>

        {/* Main Content Area */}
        <div className="flex flex-1 min-h-0 divide-x divide-ink-200/80 dark:divide-ink-800">
          
          {/* Left / Top Controls Pane (Scrollable) */}
          <div className="w-full md:w-80 lg:w-96 flex flex-col shrink-0 overflow-y-auto p-4 sm:p-5 space-y-5 bg-ink-50/30 dark:bg-ink-950/20">
            
            {/* Selected Documents */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                  Documents to Compare ({selectedDocs.length})
                </span>
                {selectedDocs.length < 2 && (
                  <span className="text-[11px] text-amber-600 dark:text-amber-400 font-medium">Pick at least 2</span>
                )}
              </div>
              <div className="space-y-1.5">
                {selectedDocs.map((doc) => (
                  <div
                    key={doc.source_id}
                    className="flex items-center justify-between gap-2 rounded-xl border border-ink-200/80 bg-white p-2 text-xs shadow-soft dark:border-ink-800 dark:bg-ink-900"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileIcon name={doc.source_name} className="h-4 w-4 shrink-0" />
                      <span className="truncate font-medium text-ink-800 dark:text-ink-200" title={doc.source_name}>
                        {doc.source_name}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedIds((all) => all.filter((id) => id !== doc.source_id))}
                      className="text-ink-400 hover:text-ink-600 dark:hover:text-ink-200 p-0.5"
                      title="Remove from comparison"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>

              {/* Add document dropdown */}
              {availableDocsToAdd.length > 0 && selectedIds.length < 5 && (
                <div className="mt-2">
                  <select
                    className="w-full text-xs rounded-xl border border-dashed border-ink-300 bg-transparent px-2.5 py-1.5 text-ink-600 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-ink-700 dark:text-ink-400"
                    onChange={(e) => {
                      if (e.target.value) {
                        setSelectedIds([...selectedIds, e.target.value]);
                        e.target.value = "";
                      }
                    }}
                    defaultValue=""
                  >
                    <option value="" disabled>+ Add another document to comparison...</option>
                    {availableDocsToAdd.map((d) => (
                      <option key={d.source_id} value={d.source_id}>{d.source_name}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Comparison Criteria & Focus */}
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-500 block mb-2">
                Analysis Focus & Criteria
              </span>
              <div className="flex flex-wrap gap-1.5 mb-2.5">
                {PRESET_FOCI.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => setFocus(p.focus)}
                    className={cx(
                      "rounded-lg px-2.5 py-1 text-xs font-medium transition text-left",
                      focus === p.focus
                        ? "bg-brand-600 text-white shadow-sm"
                        : "bg-ink-100 text-ink-700 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <textarea
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                rows={3}
                placeholder="Specify comparison criteria (e.g. compare pricing, liabilities, technical metrics)..."
                className="w-full text-xs rounded-xl border border-ink-200 bg-white p-2.5 shadow-soft focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/10 dark:border-ink-800 dark:bg-ink-900"
              />
            </div>

            {/* Provider Selector */}
            {providers.data && providers.data.providers.length > 0 && (
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-ink-500 block mb-1.5">
                  AI Model
                </span>
                <select
                  value={selectedProvider || ""}
                  onChange={(e) => setSelectedProvider(e.target.value || null)}
                  className="w-full text-xs rounded-xl border border-ink-200 bg-white px-2.5 py-2 shadow-soft focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-ink-800 dark:bg-ink-900 text-ink-700 dark:text-ink-200"
                >
                  <option value="">Default AI Model</option>
                  {providers.data.providers.filter((p) => p.available).map((p) => (
                    <option key={p.id} value={p.id}>{p.label || p.id} ({p.kind === "local" ? "Local CPU" : "Cloud"})</option>
                  ))}
                </select>
              </div>
            )}

            {/* Action Button */}
            <div className="pt-2">
              {streaming ? (
                <Button variant="danger" className="w-full" onClick={handleStop}>
                  Stop Analysis
                </Button>
              ) : (
                <Button
                  variant="primary"
                  className="w-full shadow-glow"
                  onClick={handleStartComparison}
                  disabled={selectedIds.length < 2}
                  icon={<Sparkles className="h-4 w-4" />}
                >
                  {markdown ? "Re-Run Comparison" : "Generate Comparison Matrix"}
                </Button>
              )}
            </div>
          </div>

          {/* Right Pane: Results, Matrix Table & Report */}
          <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-ink-900 overflow-hidden">
            
            {/* Top View Selector & Export Tools */}
            {markdown && (
              <div className="flex h-11 shrink-0 items-center justify-between border-b border-ink-200/80 px-4 bg-ink-50/50 dark:border-ink-800 dark:bg-ink-950/30">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setViewTab("matrix")}
                    disabled={!matrixTable}
                    className={cx(
                      "flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-lg transition",
                      viewTab === "matrix"
                        ? "bg-white text-brand-700 shadow-sm dark:bg-ink-800 dark:text-brand-300 font-semibold"
                        : "text-ink-600 hover:text-ink-900 dark:text-ink-400 disabled:opacity-40"
                    )}
                  >
                    <Table className="h-3.5 w-3.5" />
                    Comparison Matrix
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewTab("report")}
                    className={cx(
                      "flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-lg transition",
                      viewTab === "report"
                        ? "bg-white text-brand-700 shadow-sm dark:bg-ink-800 dark:text-brand-300 font-semibold"
                        : "text-ink-600 hover:text-ink-900 dark:text-ink-400"
                    )}
                  >
                    <FileText className="h-3.5 w-3.5" />
                    Full Report
                  </button>
                </div>

                <div className="flex items-center gap-1.5">
                  {matrixCsv && (
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<FileSpreadsheet className="h-3.5 w-3.5 text-emerald-600" />}
                      onClick={() => downloadBlob("comparison-matrix.csv", matrixCsv, "text/csv")}
                      title="Download as CSV (Excel/Sheets)"
                    >
                      Export CSV
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Download className="h-3.5 w-3.5" />}
                    onClick={() => downloadBlob("document-comparison.md", markdown, "text/markdown")}
                    title="Download full Markdown report"
                  >
                    Export .md
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Copy className="h-3.5 w-3.5" />}
                    onClick={() => navigator.clipboard.writeText(markdown).then(() => toast("Comparison copied"))}
                    title="Copy full comparison to clipboard"
                  >
                    Copy
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<MessageSquare className="h-3.5 w-3.5 text-brand-600" />}
                    onClick={handleOpenInChat}
                    title="Continue discussing these documents in Chat"
                  >
                    Discuss in Chat
                  </Button>
                </div>
              </div>
            )}

            {/* Split View with Embedded Reader if a document is opened */}
            <div className="flex flex-1 min-h-0 overflow-hidden">
              
              {/* Results Viewport */}
              <div className={cx(
                "flex-1 overflow-y-auto p-5 sm:p-6 transition-all duration-200",
                readerTarget ? "lg:w-[50%]" : "w-full"
              )}>
                {streaming && !markdown && (
                  <div className="flex h-full flex-col items-center justify-center gap-3 text-center py-24">
                    <Spinner className="h-7 w-7 text-brand-600" />
                    <div>
                      <p className="text-sm font-semibold text-ink-800 dark:text-ink-200">Cross-referencing documents...</p>
                      <p className="text-xs text-ink-500 mt-1">Analyzing sections, extracting metrics, and detecting divergences</p>
                    </div>
                  </div>
                )}

                {!streaming && !markdown && (
                  <div className="flex h-full flex-col items-center justify-center gap-3 text-center py-24 text-ink-400">
                    <div className="h-12 w-12 rounded-2xl bg-ink-100 dark:bg-ink-800 flex items-center justify-center text-ink-500">
                      <GitCompare className="h-6 w-6" />
                    </div>
                    <p className="text-sm font-medium text-ink-700 dark:text-ink-300">Ready to compare {selectedDocs.length} documents</p>
                    <p className="text-xs max-w-sm text-ink-500">
                      Select your analysis criteria on the left and click "Generate Comparison Matrix" to synthesize findings side-by-side.
                    </p>
                  </div>
                )}

                {markdown && (
                  <div className="prose prose-sm dark:prose-invert max-w-none animate-fade-in space-y-4">
                    {viewTab === "matrix" && matrixTable ? (
                      <div className="space-y-4">
                        <div className="overflow-x-auto rounded-xl border border-ink-200 shadow-soft dark:border-ink-800">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {matrixTable}
                          </ReactMarkdown>
                        </div>
                        <p className="text-xs text-ink-400 italic">
                          Switch to "Full Report" above for executive summary, dimensional deep dive, and contradiction analysis.
                        </p>
                      </div>
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          table({ children }) {
                            return (
                              <div className="overflow-x-auto my-4 rounded-xl border border-ink-200 shadow-soft dark:border-ink-800">
                                <table className="w-full text-left text-sm">{children}</table>
                              </div>
                            );
                          },
                          a({ href, children }) {
                            return (
                              <a href={href} target="_blank" rel="noreferrer" className="text-brand-600 underline">
                                {children}
                              </a>
                            );
                          },
                        }}
                      >
                        {markdown}
                      </ReactMarkdown>
                    )}
                  </div>
                )}
              </div>

              {/* Side Split Reader if user wants to check a cited document */}
              {readerTarget && (
                <div className="w-[50%] h-full shrink-0 border-l border-ink-200/80 dark:border-ink-800 animate-slide-in">
                  <SplitReader
                    target={readerTarget}
                    onClose={() => setReaderTarget(null)}
                  />
                </div>
              )}
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}
