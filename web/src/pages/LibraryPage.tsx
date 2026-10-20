// The workspace's documents: upload, indexing progress, and the document list.
import {
  AlertCircle, Camera, CheckCircle2, ExternalLink, FilePlus2, FileStack, FileUp, FolderOpen, HardDrive, Loader2, MoreHorizontal,
  RefreshCw, ScanText, Search, TextQuote, Trash2, Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { FileTile } from "../components/answer";
import {
  Alert, Badge, Button, Card, ConfirmDialog, Drawer, EmptyState, IconButton, MenuItem, PageHeader, Popover, Spinner, Stat, cx, useToast,
} from "../components/ui";
import { api, authHeaders, openDocument, uploadFiles } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatPages, formatSize, timeAgo } from "../lib/format";
import { useApi, useInterval } from "../lib/hooks";
import type { DocumentInfo, DocumentsResponse, FailedFile, Job, Passage } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

const PAGE_SIZE = 50;

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

function PassagesDrawer({ doc, onClose }: { doc: DocumentInfo | null; onClose: () => void }) {
  const { data, loading, error } = useApi<{ passages: Passage[] }>(doc ? `/documents/${encodeURIComponent(doc.source_id)}/passages` : null);
  const [query, setQuery] = useState("");
  const toast = useToast();
  const passages = (data?.passages ?? []).filter((p) => p.text.toLowerCase().includes(query.toLowerCase()));
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
      {!loading && data && passages.length === 0 && <p className="text-center text-sm text-ink-500">No passage contains “{query}”.</p>}
    </Drawer>
  );
}

export function LibraryPage() {
  const toast = useToast();
  const { config } = useAuth();
  const { current } = useWorkspace();
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

  const data = documents.data;
  const shown = (data?.documents ?? []).filter((d) => d.source_name.toLowerCase().includes(query.toLowerCase()));

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
        <DropZone onFiles={onFiles} accept={config?.file_types ?? []} maxMb={config?.max_upload_mb ?? 15}
          disabled={Boolean(upload) || Boolean(active)} compact={Boolean(data?.documents.length)} />
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
                  <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeletingSelected(true)}>Delete selected</Button>
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
                              <MenuItem icon={<Search className="h-4 w-4" />} onClick={() => { close(); setViewing(doc); }}>Read passages</MenuItem>
                              <MenuItem icon={<ExternalLink className="h-4 w-4" />} onClick={() => { close(); openDocument(doc.source_id).catch((e: Error) => toast(e.message, "error")); }}>Open original</MenuItem>
                              <MenuItem icon={<FilePlus2 className="h-4 w-4" />} onClick={() => { close(); setReplacing(doc); replaceInput.current?.click(); }}>Upload new version</MenuItem>
                              <MenuItem danger icon={<Trash2 className="h-4 w-4" />} onClick={() => { close(); setDeleting(doc); }}>Delete</MenuItem>
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

      <PassagesDrawer doc={viewing} onClose={() => setViewing(null)} />
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
    </div>
  );
}
