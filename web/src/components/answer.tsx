// An answer with clickable [S1] citations, and the source passages behind it.
import { Copy, ExternalLink, FileCode2, FileImage, FileSpreadsheet, FileText, Presentation, ScanText } from "lucide-react";
import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { openDocument } from "../lib/api";
import { formatPages, linkCitations } from "../lib/format";
import type { Source } from "../lib/types";
import { Badge, Button, cx, useToast } from "./ui";

const FILE_KINDS = [
  { types: ["png", "jpg", "jpeg", "tif", "tiff", "webp", "bmp"], Icon: FileImage, color: "text-sky-600 dark:text-sky-400", tile: "bg-sky-50 dark:bg-sky-950/60" },
  { types: ["pdf"], Icon: FileText, color: "text-red-600 dark:text-red-400", tile: "bg-red-50 dark:bg-red-950/60" },
  { types: ["docx"], Icon: FileText, color: "text-blue-600 dark:text-blue-400", tile: "bg-blue-50 dark:bg-blue-950/60" },
  { types: ["xlsx", "csv"], Icon: FileSpreadsheet, color: "text-emerald-600 dark:text-emerald-400", tile: "bg-emerald-50 dark:bg-emerald-950/60" },
  { types: ["pptx"], Icon: Presentation, color: "text-orange-600 dark:text-orange-400", tile: "bg-orange-50 dark:bg-orange-950/60" },
  { types: ["html", "htm", "md"], Icon: FileCode2, color: "text-violet-600 dark:text-violet-400", tile: "bg-violet-50 dark:bg-violet-950/60" },
];
const PLAIN = { Icon: FileText, color: "text-ink-500 dark:text-ink-400", tile: "bg-ink-100 dark:bg-ink-800" };

function fileKind(name: string) {
  const type = name.split(".").pop()?.toLowerCase() ?? "";
  return FILE_KINDS.find((kind) => kind.types.includes(type)) ?? PLAIN;
}

export function FileIcon({ name, className = "h-4 w-4" }: { name: string; className?: string }) {
  const { Icon, color } = fileKind(name);
  return <Icon className={cx(className, color)} />;
}

/** The file-type icon on a tinted tile. */
export function FileTile({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const { Icon, color, tile } = fileKind(name);
  return (
    <span className={cx("flex shrink-0 items-center justify-center rounded-lg", tile, size === "sm" ? "h-7 w-7" : "h-9 w-9")}>
      <Icon className={cx(color, size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4")} />
    </span>
  );
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
                    "mx-0.5 inline-flex h-5 -translate-y-px items-center rounded-md px-1.5 align-middle text-[11px] font-semibold transition",
                    activeLabel === label
                      ? "bg-brand-gradient text-white shadow-sm"
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

/** One small card per source: label, document, page and the start of the passage. */
export function SourceChips({ sources, active, onSelect }: { sources: Source[]; active: string | null; onSelect: (label: string | null) => void }) {
  return (
    <div className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1">
      {sources.map((source) => (
        <button
          key={source.label}
          type="button"
          onClick={() => onSelect(active === source.label ? null : source.label)}
          aria-pressed={active === source.label}
          title={`Show source ${source.label}: ${source.source_name}`}
          className={cx(
            "group/source flex w-56 shrink-0 snap-start flex-col gap-1.5 rounded-xl border p-2.5 text-left transition",
            active === source.label
              ? "border-brand-300 bg-brand-50 ring-2 ring-brand-500/15 dark:border-brand-800 dark:bg-brand-950/50"
              : "border-ink-200/80 bg-white hover:-translate-y-0.5 hover:border-ink-300 hover:shadow-soft dark:border-ink-800 dark:bg-ink-900/70 dark:hover:border-ink-700",
          )}
        >
          <span className="flex items-center gap-1.5 text-xs">
            <span className="rounded bg-brand-gradient px-1 py-px text-[10px] font-bold text-white">{source.label}</span>
            <FileIcon name={source.source_name} className="h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 flex-1 truncate font-medium text-ink-700 dark:text-ink-200">{source.source_name}</span>
            {source.page && <span className="shrink-0 text-ink-400">p.{source.page}</span>}
          </span>
          <span className="line-clamp-2 text-xs leading-[1.1rem] text-ink-500 dark:text-ink-400">{source.text}</span>
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
        "relative overflow-hidden rounded-2xl border p-4 pl-5 transition",
        highlight ? "border-brand-300 bg-brand-50/60 shadow-soft dark:border-brand-800 dark:bg-brand-950/40" : "border-ink-200/80 bg-white dark:border-ink-800 dark:bg-ink-900/70",
      )}
    >
      <span className={cx("absolute inset-y-0 left-0 w-1", highlight ? "bg-brand-gradient" : "bg-ink-200 dark:bg-ink-700")} aria-hidden="true" />
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-brand-gradient px-1.5 py-0.5 text-xs font-bold text-white">{source.label}</span>
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
