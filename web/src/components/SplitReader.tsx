// In-app Side-by-Side Split Document & PDF Reader
import {
  ChevronLeft, ChevronRight, Copy, ExternalLink, Maximize2, Minimize2,
  Quote, RefreshCw, X
} from "lucide-react";
import { useEffect, useState } from "react";
import { getDocumentBlobUrl, openDocument } from "../lib/api";
import { formatPages } from "../lib/format";
import { Badge, Button, IconButton, Spinner, cx, useToast } from "./ui";
import { FileIcon } from "./answer";

export interface ActiveReaderTarget {
  sourceId: string;
  sourceName: string;
  page?: number | null;
  pageEnd?: number | null;
  label?: string;
  text?: string;
  score?: number;
  totalPages?: number | null;
}

export function SplitReader({
  target,
  onClose,
  onPageChange,
}: {
  target: ActiveReaderTarget;
  onClose: () => void;
  onPageChange?: (page: number) => void;
}) {
  const toast = useToast();
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(target.page || 1);
  const [pageInput, setPageInput] = useState<string>(String(target.page || 1));
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showCallout, setShowCallout] = useState(Boolean(target.text));

  const isPdf = target.sourceName.toLowerCase().endsWith(".pdf");
  const pagesLabel = formatPages(target.page, target.pageEnd);

  // Update page when target changes
  useEffect(() => {
    if (target.page) {
      setCurrentPage(target.page);
      setPageInput(String(target.page));
    }
    if (target.text) {
      setShowCallout(true);
    }
  }, [target.sourceId, target.page, target.label]);

  // Load document blob
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    getDocumentBlobUrl(target.sourceId)
      .then((url) => {
        if (active) {
          setBlobUrl(url);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message || "Failed to load document");
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [target.sourceId]);

  const handlePageJump = (newPage: number) => {
    const valid = Math.max(1, newPage);
    setCurrentPage(valid);
    setPageInput(String(valid));
    onPageChange?.(valid);
  };

  const iframeSrc = isPdf && blobUrl ? `${blobUrl}#page=${currentPage}&view=FitH` : blobUrl || "";

  return (
    <div
      className={cx(
        "flex flex-col bg-white dark:bg-ink-900 border-l border-ink-200/80 dark:border-ink-800 transition-all duration-200",
        isFullscreen ? "fixed inset-0 z-50 w-screen h-screen border-l-0" : "h-full w-full"
      )}
    >
      {/* Reader Header */}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-ink-200/80 px-3 bg-ink-50/70 dark:border-ink-800 dark:bg-ink-950/80 backdrop-blur">
        <div className="flex items-center gap-2 min-w-0 mr-2">
          <FileIcon name={target.sourceName} className="h-4 w-4 shrink-0" />
          <span className="truncate text-xs font-semibold text-ink-800 dark:text-ink-200" title={target.sourceName}>
            {target.sourceName}
          </span>
          {target.label && (
            <Badge tone="brand">
              {target.label}
            </Badge>
          )}
        </div>

        {/* Page Nav & Controls */}
        <div className="flex items-center gap-1 shrink-0">
          {isPdf && (
            <div className="flex items-center gap-0.5 rounded-lg border border-ink-200 bg-white px-1 py-0.5 text-xs dark:border-ink-700 dark:bg-ink-800 mr-1 shadow-sm">
              <button
                type="button"
                onClick={() => handlePageJump(currentPage - 1)}
                disabled={currentPage <= 1}
                className="p-1 text-ink-500 hover:text-ink-800 disabled:opacity-30 dark:hover:text-ink-100"
                title="Previous page"
              >
                <ChevronLeft className="h-3 w-3" />
              </button>
              <input
                type="text"
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const parsed = parseInt(pageInput, 10);
                    if (!isNaN(parsed)) handlePageJump(parsed);
                  }
                }}
                className="w-9 text-center text-xs font-semibold bg-transparent focus:outline-none focus:ring-1 focus:ring-brand-500 rounded"
              />
              {target.totalPages && (
                <span className="text-[11px] text-ink-400 mr-1">/ {target.totalPages}</span>
              )}
              <button
                type="button"
                onClick={() => handlePageJump(currentPage + 1)}
                className="p-1 text-ink-500 hover:text-ink-800 dark:hover:text-ink-100"
                title="Next page"
              >
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          )}

          <IconButton
            label={isFullscreen ? "Exit fullscreen" : "Expand to fullscreen"}
            onClick={() => setIsFullscreen((prev) => !prev)}
          >
            {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </IconButton>
          <IconButton
            label="Open in new browser tab"
            onClick={() => openDocument(target.sourceId, currentPage).catch((e: Error) => toast(e.message, "error"))}
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton
            label="Close reader"
            onClick={onClose}
          >
            <X className="h-3.5 w-3.5" />
          </IconButton>
        </div>
      </div>

      {/* Cited Passage Preview Card */}
      {showCallout && target.text && (
        <div className="shrink-0 border-b border-brand-200 bg-brand-50/70 p-3 text-xs dark:border-brand-900/50 dark:bg-brand-950/40 animate-fade-in">
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-semibold text-brand-900 dark:text-brand-300 flex items-center gap-1.5">
              <Quote className="h-3 w-3 text-brand-600" />
              Cited Passage {target.label ? `[${target.label}]` : ""} {pagesLabel ? `· ${pagesLabel}` : ""}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(target.text || "").then(() => toast("Passage copied"))}
                className="text-[11px] text-brand-700 hover:text-brand-900 dark:text-brand-400 underline flex items-center gap-1"
              >
                <Copy className="h-2.5 w-2.5" /> Copy
              </button>
              <button
                type="button"
                onClick={() => setShowCallout(false)}
                className="text-ink-400 hover:text-ink-600 text-xs ml-1"
                title="Dismiss banner"
              >
                ×
              </button>
            </div>
          </div>
          <p className="line-clamp-2 leading-relaxed text-ink-700 dark:text-ink-300 italic">
            "{target.text}"
          </p>
        </div>
      )}

      {/* Embedded Document Viewport */}
      <div className="relative flex-1 w-full h-full overflow-hidden bg-ink-100/50 dark:bg-ink-950/70">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 z-10 bg-white/80 dark:bg-ink-900/80 backdrop-blur-sm">
            <Spinner />
            <span className="text-xs text-ink-500">Loading document...</span>
          </div>
        )}

        {error ? (
          <div className="flex h-full flex-col items-center justify-center p-6 text-center">
            <p className="text-sm font-medium text-red-600 dark:text-red-400">{error}</p>
            <Button
              size="sm"
              variant="secondary"
              icon={<RefreshCw className="h-3 w-3" />}
              onClick={() => {
                setLoading(true);
                setError(null);
                getDocumentBlobUrl(target.sourceId)
                  .then((url) => {
                    setBlobUrl(url);
                    setLoading(false);
                  })
                  .catch((err) => {
                    setError(err.message || "Failed to load");
                    setLoading(false);
                  });
              }}
              className="mt-3"
            >
              Retry
            </Button>
          </div>
        ) : (
          blobUrl && (
            <iframe
              key={`${target.sourceId}-${currentPage}`}
              src={iframeSrc}
              className="h-full w-full border-0"
              title={target.sourceName}
            />
          )
        )}
      </div>
    </div>
  );
}
