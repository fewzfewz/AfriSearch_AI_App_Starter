// An answer with clickable [S1] citations, and the source passages behind it.
import { Copy, ExternalLink, FileImage, FileText, ScanText } from "lucide-react";
import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { openDocument } from "../lib/api";
import { formatPages, linkCitations } from "../lib/format";
import type { Source } from "../lib/types";
import { Badge, Button, cx, useToast } from "./ui";

export function FileIcon({ name, className = "h-4 w-4" }: { name: string; className?: string }) {
  const type = name.split(".").pop()?.toLowerCase();
  if (type && ["png", "jpg", "jpeg", "tif", "tiff", "webp", "bmp"].includes(type)) return <FileImage className={cx(className, "text-sky-600")} />;
  if (type === "pdf") return <FileText className={cx(className, "text-red-600")} />;
  return <FileText className={cx(className, "text-ink-500")} />;
}

export const AnswerText = memo(function AnswerText({ text, onCite, activeLabel }: {
  text: string;
  onCite: (label: string) => void;
  activeLabel?: string | null;
}) {
  return (
    <div className="prose-answer text-[15px] leading-7 text-ink-800 dark:text-ink-100">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite-")) {
              const label = href.slice(6);
              return (
                <button
                  type="button"
                  onClick={() => onCite(label)}
                  title={`Show source ${label}`}
                  className={cx(
                    "mx-0.5 inline-flex h-5 items-center rounded-md px-1.5 align-baseline text-[11px] font-semibold transition",
                    activeLabel === label
                      ? "bg-brand-700 text-white"
                      : "bg-brand-100 text-brand-800 hover:bg-brand-200 dark:bg-brand-900/60 dark:text-brand-200 dark:hover:bg-brand-900",
                  )}
                >
                  {label}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-brand-700 underline dark:text-brand-400">
                {children}
              </a>
            );
          },
        }}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  );
});

export function SourceChips({ sources, active, onSelect }: { sources: Source[]; active: string | null; onSelect: (label: string | null) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {sources.map((source) => (
        <button
          key={source.label}
          type="button"
          onClick={() => onSelect(active === source.label ? null : source.label)}
          aria-pressed={active === source.label}
          className={cx(
            "flex max-w-[16rem] items-center gap-1.5 rounded-lg border px-2 py-1 text-xs transition",
            active === source.label
              ? "border-brand-300 bg-brand-50 text-brand-900 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-100"
              : "border-ink-200 bg-white text-ink-700 hover:border-ink-300 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-300 dark:hover:border-ink-600",
          )}
        >
          <span className="font-semibold text-brand-700 dark:text-brand-400">{source.label}</span>
          <FileIcon name={source.source_name} className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{source.source_name}</span>
          {source.page && <span className="shrink-0 text-ink-400">p.{source.page}</span>}
        </button>
      ))}
    </div>
  );
}

export function SourceCard({ source, highlight }: { source: Source; highlight?: boolean }) {
  const toast = useToast();
  const [expanded, setExpanded] = useState(false);
  const long = source.text.length > 420;
  const pages = formatPages(source.page, source.page_end);
  return (
    <div
      id={`source-${source.label}`}
      className={cx(
        "rounded-xl border p-4 transition",
        highlight ? "border-brand-300 bg-brand-50/60 shadow-sm dark:border-brand-800 dark:bg-brand-950/40" : "border-ink-200 bg-white dark:border-ink-800 dark:bg-ink-900",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-brand-700 px-1.5 py-0.5 text-xs font-bold text-white">{source.label}</span>
        <FileIcon name={source.source_name} />
        <span className="min-w-0 truncate text-sm font-medium">{source.source_name}</span>
        {pages && <span className="text-sm text-ink-500">· {pages}</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Badge tone="gray">{Math.round(source.score * 100)}% match</Badge>
        {source.rerank_score !== null && <Badge tone="gray">reranker {source.rerank_score.toFixed(1)}</Badge>}
        {source.ocr && (
          <Badge tone="blue">
            <ScanText className="h-3 w-3" /> read with OCR
          </Badge>
        )}
      </div>
      <p className={cx("mt-3 whitespace-pre-line text-sm leading-6 text-ink-700 dark:text-ink-300", !expanded && long && "line-clamp-5")}>{source.text}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {long && (
          <Button size="sm" variant="ghost" onClick={() => setExpanded((e) => !e)}>
            {expanded ? "Show less" : "Show full passage"}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          icon={<ExternalLink className="h-3.5 w-3.5" />}
          onClick={() => openDocument(source.source_id, source.page).catch((e: Error) => toast(e.message, "error"))}
        >
          Open document{source.page ? ` at page ${source.page}` : ""}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          icon={<Copy className="h-3.5 w-3.5" />}
          onClick={() => navigator.clipboard.writeText(source.text).then(() => toast("Passage copied"))}
        >
          Copy
        </Button>
      </div>
    </div>
  );
}
