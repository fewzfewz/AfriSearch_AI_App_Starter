// Asking questions: a chat with streamed, cited answers.
import {
  AlertTriangle, ArrowRight, BookOpenText, Check, Copy, Download, FileSearch, FolderOpen, Languages, ListChecks, Quote, RotateCcw,
  ThumbsDown, ThumbsUp, Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnswerText, FileIcon, SourceCard, SourceChips } from "../components/answer";
import { Composer, providerName, useAnswerSettings, whereItRuns } from "../components/composer";
import { Alert, Badge, Button, IconButton, LogoMark, MenuItem, Modal, Popover, Spinner, cx, useToast } from "../components/ui";
import { ApiError, api, streamAsk } from "../lib/api";
import { formatPages } from "../lib/format";
import { useApi } from "../lib/hooks";
import type { ChatDetail, DocumentsResponse, Message, Provider } from "../lib/types";
import { useWorkspace } from "../lib/workspace";
import { ShortcutHint, useChats } from "./AppLayout";

interface UiMessage extends Message {
  streaming?: boolean;
  question?: string; // the question an assistant message answers
}

const LANGUAGES = ["English", "አማርኛ", "Kiswahili", "Soomaali", "Afaan Oromoo", "Hausa", "Français", "العربية"];

function exportMarkdown(question: string, message: UiMessage): string {
  const lines = [`# ${question}`, "", message.content || "_Passages only, no generated answer._", "", "## Sources", ""];
  for (const source of message.data.sources ?? []) {
    const pages = formatPages(source.page, source.page_end);
    lines.push(`### ${source.label} · ${source.source_name}${pages ? ` · ${pages}` : ""}`, "", `> ${source.text.replace(/\n/g, "\n> ")}`, "");
  }
  return lines.join("\n");
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  URL.revokeObjectURL(url);
}

/** What's happening while an answer is on its way: search, then writing. */
function Progress({ searching }: { searching: boolean }) {
  const steps = [
    { label: "Searching your documents", done: !searching },
    { label: "Writing the answer", done: false },
  ];
  return (
    <div className="space-y-3" role="status">
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {steps.map((step, i) => {
          const active = searching ? i === 0 : i === 1;
          return (
            <li key={step.label} className={cx("flex items-center gap-1.5", active ? "font-medium text-ink-800 dark:text-ink-100" : step.done ? "text-ink-500" : "text-ink-400")}>
              {step.done ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : active ? <Spinner className="h-3.5 w-3.5 text-brand-600" /> : <span className="h-1.5 w-1.5 rounded-full bg-ink-300 dark:bg-ink-600" />}
              {step.label}
              {i < steps.length - 1 && <ArrowRight className="ml-1.5 h-3 w-3 text-ink-300 dark:text-ink-600" />}
            </li>
          );
        })}
      </ol>
      <div className="space-y-2" aria-hidden="true">
        <div className="skeleton h-3.5 w-[92%]" />
        <div className="skeleton h-3.5 w-[78%]" />
        <div className="skeleton h-3.5 w-[55%]" />
      </div>
    </div>
  );
}

function AssistantMessage({ message, providers, onRate, onRetry, busy }: {
  message: UiMessage;
  providers: Provider[];
  onRate: (message: UiMessage, rating: "up" | "down", comment: string) => Promise<void>;
  onRetry: (question: string, providerId: string) => void;
  busy: boolean;
}) {
  const toast = useToast();
  const sources = message.data.sources ?? [];
  const passagesOnly = !message.streaming && !message.content && !message.data.error && message.data.provider === null;
  const notCovered = message.data.covered === false && sources.length > 0;
  const [active, setActive] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [rating, setRating] = useState<"up" | "down" | null>(message.rating);
  const [commenting, setCommenting] = useState(false);
  const [comment, setComment] = useState("");
  const provider = providers.find((p) => p.id === message.data.provider);
  const where = provider ? whereItRuns(provider) : null;

  const cite = useCallback((label: string) => {
    setActive(label);
    requestAnimationFrame(() => document.getElementById(`${message.id}-${label}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }, [message.id]);

  const rate = async (value: "up" | "down", text = "") => {
    try {
      await onRate(message, value, text);
      setRating(value);
      toast("Thanks for the feedback");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const shown = passagesOnly || notCovered || showAll ? sources : sources.filter((s) => s.label === active);

  return (
    <div className="group flex animate-fade-in gap-3 sm:gap-4">
      <LogoMark className="mt-0.5 h-8 w-8 shadow-glow" />
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex min-h-8 flex-wrap items-center gap-1.5 text-xs text-ink-500">
          <span className="font-semibold text-ink-800 dark:text-ink-200">{passagesOnly ? "Passages" : providerName(provider)}</span>
          {where && <Badge tone={where.tone}>{where.icon}{where.text}</Badge>}
          {message.data.seconds !== undefined && !message.streaming && <span>· {message.data.seconds}s</span>}
          {message.data.reranked && <span>· reranked</span>}
        </div>

        {message.streaming && !message.content && (
          <Progress searching={!sources.length && message.data.covered === undefined} />
        )}
        {notCovered && !message.streaming && (
          <Alert tone="amber">
            <span className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 shrink-0" /> Your documents don't seem to answer this. The closest passages are below.</span>
          </Alert>
        )}
        {message.content && !(notCovered && !message.streaming) && (
          <div>
            <AnswerText text={message.content} onCite={cite} activeLabel={active} />
            {message.streaming && <span className="ml-0.5 inline-block h-4 w-[3px] translate-y-0.5 animate-blink rounded-full bg-brand-600" aria-hidden="true" />}
          </div>
        )}
        {!message.streaming && message.content && !notCovered && sources.length > 0 && !/\[S\d/.test(message.content) && (
          <p className="flex flex-wrap items-center gap-x-2 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-3.5 w-3.5" /> This answer doesn't cite its sources, so check it against the passages.
            {!showAll && <button type="button" onClick={() => setShowAll(true)} className="font-medium underline">Show passages</button>}
          </p>
        )}
        {message.data.error && <Alert tone="red" title="The answer couldn't be completed">{message.data.error}</Alert>}
        {passagesOnly && !sources.length && <p className="text-sm text-ink-500">No passages were similar enough to the question.</p>}

        {sources.length > 0 && (
          <div className="space-y-2.5">
            {!passagesOnly && !notCovered && (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">
                    <Quote className="h-3.5 w-3.5" /> {sources.length} source{sources.length === 1 ? "" : "s"}
                  </p>
                  <button type="button" onClick={() => setShowAll((v) => !v)} className="text-xs font-medium text-brand-700 hover:underline dark:text-brand-400">
                    {showAll ? "Hide passages" : `Show all ${sources.length} passages`}
                  </button>
                </div>
                <SourceChips sources={sources} active={active} onSelect={setActive} />
              </div>
            )}
            {shown.map((source) => (
              <div key={source.label} id={`${message.id}-${source.label}`} className="scroll-mt-4 animate-fade-in">
                <SourceCard source={source} highlight={source.label === active} />
              </div>
            ))}
          </div>
        )}

        {!message.streaming && (message.content || sources.length > 0) && (
          <div className="inline-flex items-center gap-0.5 rounded-xl border border-ink-200/80 bg-white p-0.5 shadow-soft transition dark:border-ink-800 dark:bg-ink-900 dark:shadow-none sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
            {message.content && (
              <IconButton label="Copy answer" onClick={() => navigator.clipboard.writeText(message.content).then(() => toast("Answer copied"))}>
                <Copy className="h-4 w-4" />
              </IconButton>
            )}
            <IconButton label="Download as Markdown" onClick={() => download("afrisearch-answer.md", exportMarkdown(message.question ?? "", message))}>
              <Download className="h-4 w-4" />
            </IconButton>
            {message.question && providers.some((p) => p.available) && (
              <Popover up width="w-64" trigger={({ toggle }) => (
                <IconButton label="Try again with another model" onClick={toggle} disabled={busy}><RotateCcw className="h-4 w-4" /></IconButton>
              )}>
                {(close) => (
                  <>
                    <p className="px-2.5 pb-1 pt-1.5 text-xs font-medium uppercase tracking-wide text-ink-400">Try again with</p>
                    {providers.filter((p) => p.available).map((p) => (
                      <MenuItem key={p.id} onClick={() => { close(); onRetry(message.question!, p.id); }}
                        hint={p.id === message.data.provider ? <span className="text-xs text-ink-400">same</span> : undefined}>
                        {providerName(p)}
                      </MenuItem>
                    ))}
                  </>
                )}
              </Popover>
            )}
            {message.content && !message.id.startsWith("tmp-") && (
              <>
                <IconButton label="Helpful" onClick={() => rate("up")} className={cx(rating === "up" && "text-emerald-600 dark:text-emerald-400")}>
                  {rating === "up" ? <Check className="h-4 w-4" /> : <ThumbsUp className="h-4 w-4" />}
                </IconButton>
                <IconButton label="Not helpful" onClick={() => setCommenting(true)} className={cx(rating === "down" && "text-red-600 dark:text-red-400")}>
                  <ThumbsDown className="h-4 w-4" />
                </IconButton>
              </>
            )}
          </div>
        )}
      </div>
      <Modal
        open={commenting}
        onClose={() => setCommenting(false)}
        title="What was wrong with this answer?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCommenting(false)}>Cancel</Button>
            <Button variant="primary" onClick={async () => { await rate("down", comment); setCommenting(false); }}>Send feedback</Button>
          </>
        }
      >
        <textarea
          autoFocus
          value={comment}
          maxLength={1000}
          onChange={(e) => setComment(e.target.value)}
          rows={4}
          placeholder="For example: wrong number, missed the right document, wrong language… (optional)"
          className="w-full rounded-lg border border-ink-300 bg-transparent px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-ink-700"
        />
        <p className="mt-2 text-xs text-ink-500">Your rating helps improve answers for everyone in this workspace.</p>
      </Modal>
    </div>
  );
}

function greeting(name: string | undefined): string {
  const hour = new Date().getHours();
  const part = hour < 5 ? "Good evening" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const first = name && name !== "Local user" ? name.split(/\s+/)[0] : "";
  return first ? `${part}, ${first}` : part;
}

function EmptyChat({ documents, onAsk, loading }: { documents: DocumentsResponse | null; onAsk: (q: string) => void; loading: boolean }) {
  const { current, user } = useWorkspace();
  if (loading || !documents) return <div className="flex justify-center py-24"><Spinner /></div>;
  if (!documents.documents.length) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center sm:py-24">
        <div className="relative mx-auto h-20 w-20">
          <div className="absolute inset-0 rotate-6 rounded-3xl bg-brand-100 dark:bg-brand-950" />
          <div className="relative flex h-20 w-20 items-center justify-center rounded-3xl bg-white shadow-lift ring-1 ring-ink-200/80 dark:bg-ink-900 dark:ring-ink-800">
            <FolderOpen className="h-9 w-9 text-brand-600" />
          </div>
        </div>
        <h1 className="mt-7 font-display text-3xl font-semibold">Add your first documents</h1>
        <p className="mt-3 text-ink-500 dark:text-ink-400">
          Upload PDFs, Word, Excel or PowerPoint files, or photos of pages to <span className="font-medium text-ink-700 dark:text-ink-300">{current?.name}</span>. Then ask anything about them, in any language.
        </p>
        <Link to="/app/library" className="mt-7 inline-flex h-11 items-center gap-2 rounded-xl bg-brand-gradient px-5 text-sm font-medium text-white shadow-glow transition hover:brightness-110">
          <Upload className="h-4 w-4" /> Upload documents
        </Link>
      </div>
    );
  }
  const names = documents.documents.slice(0, 2).map((d) => d.source_name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
  const suggestions = [
    ...names.map((name) => ({ icon: BookOpenText, text: `What are the main points of “${name}”?` })),
    { icon: ListChecks, text: "What do my documents recommend?" },
    { icon: Languages, text: "ሰነዶቼ ስለ ምን ይናገራሉ?" },
  ].slice(0, 4);
  const passages = documents.documents.reduce((sum, d) => sum + d.passages, 0);
  return (
    <div className="mx-auto max-w-2xl py-8 text-center sm:py-14">
      <span className="inline-flex items-center gap-2 rounded-full border border-ink-200/80 bg-white/80 px-3 py-1 text-xs text-ink-600 shadow-soft backdrop-blur dark:border-ink-800 dark:bg-ink-900/80 dark:text-ink-400 dark:shadow-none">
        <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" /><span className="relative h-2 w-2 rounded-full bg-emerald-500" /></span>
        {documents.documents.length} document{documents.documents.length === 1 ? "" : "s"} · {passages} passages ready in {current?.name}
      </span>
      <h1 className="mt-6 font-display text-4xl font-semibold sm:text-5xl">{greeting(user?.name)}</h1>
      <p className="mt-3 text-lg text-ink-500 dark:text-ink-400">What would you like to know from your documents?</p>
      <div className="mt-9 grid gap-2.5 text-left sm:grid-cols-2">
        {suggestions.map(({ icon: Icon, text }) => (
          <button
            key={text}
            type="button"
            onClick={() => onAsk(text)}
            className="group flex items-start gap-3 rounded-2xl border border-ink-200/80 bg-white/80 p-4 text-sm text-ink-700 shadow-soft backdrop-blur transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-lift dark:border-ink-800 dark:bg-ink-900/70 dark:text-ink-300 dark:shadow-none dark:hover:border-brand-800"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 transition group-hover:bg-brand-gradient group-hover:text-white dark:bg-brand-950/60 dark:text-brand-400">
              <Icon className="h-4 w-4" />
            </span>
            <span className="pt-1.5">{text}</span>
          </button>
        ))}
      </div>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-1.5">
        {LANGUAGES.map((language) => <Badge key={language} className="bg-ink-100/70 dark:bg-ink-800/70">{language}</Badge>)}
        <Badge>+ 86 more</Badge>
      </div>
      <p className="mt-6 hidden items-center justify-center gap-2 text-xs text-ink-400 sm:flex">
        <FileSearch className="h-3.5 w-3.5" /> Every answer cites its sources · <ShortcutHint /> to search chats and documents
      </p>
    </div>
  );
}

export function ChatPage() {
  const { chatId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { reload: reloadChats } = useChats();
  const [settings, setSettings] = useAnswerSettings();
  const [scope, setScope] = useState<string[]>([]);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loadingChat, setLoadingChat] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sharedBy, setSharedBy] = useState<string | null>(null); // set when viewing someone else's shared chat
  const abort = useRef<AbortController | null>(null);
  const createdHere = useRef<string | null>(null); // a chat this page just created (already on screen)
  const bottom = useRef<HTMLDivElement>(null);
  const providers = useApi<{ providers: Provider[]; default: string | null }>("/providers");
  const documents = useApi<DocumentsResponse>("/documents");

  useEffect(() => {
    setSharedBy(null);
    if (!chatId) {
      if (!createdHere.current) setMessages([]);
      createdHere.current = null;
      return;
    }
    if (createdHere.current === chatId) return;
    abort.current?.abort();
    setLoadingChat(true);
    api<ChatDetail>(`/chats/${chatId}`)
      .then((chat) => {
        setSharedBy(chat.mine ? null : chat.owner_name || "a colleague");
        let question = "";
        setMessages(chat.messages.map((m) => {
          if (m.role === "user") question = m.content;
          return m.role === "assistant" ? { ...m, question } : m;
        }));
      })
      .catch((e: ApiError) => {
        toast(e.status === 404 ? "That chat doesn't exist any more." : e.message, "error");
        navigate("/app", { replace: true });
      })
      .finally(() => setLoadingChat(false));
  }, [chatId, navigate, toast]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  const update = (id: string, change: (m: UiMessage) => UiMessage) =>
    setMessages((all) => all.map((m) => (m.id === id ? change(m) : m)));

  const ask = async (question: string, providerOverride?: string) => {
    // A shared chat is read-only: asking starts the user's own chat.
    const ownChatId = sharedBy ? null : chatId ?? null;
    if (sharedBy) {
      setMessages([]);
      setSharedBy(null);
    }
    const available = providers.data?.providers.filter((p) => p.available) ?? [];
    const chosen = providerOverride ?? settings.provider;
    const provider = available.some((p) => p.id === chosen) ? chosen : providers.data?.default ?? null;
    const answering = providerOverride ? true : settings.mode === "answer";
    const now = new Date().toISOString();
    const tmp = `tmp-${Date.now()}`;
    setMessages((all) => [
      ...all,
      { id: `${tmp}-q`, role: "user", content: question, data: {}, rating: null, created_at: now },
      { id: tmp, role: "assistant", content: "", data: {}, rating: null, created_at: now, streaming: true, question },
    ]);
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    let id = tmp;
    try {
      const body = {
        question,
        top_k: settings.topK,
        rerank: settings.rerank,
        generate_answer: answering,
        provider: answering ? provider : null,
        source_ids: scope.length ? scope : null,
        chat_id: ownChatId,
        save: true,
      };
      for await (const event of streamAsk(body, controller.signal)) {
        if (event.type === "sources") {
          update(id, (m) => ({ ...m, data: { ...m.data, sources: event.sources, provider: event.provider, model: event.model, reranked: event.reranked, covered: event.covered } }));
          if (!ownChatId && event.chat_id) {
            createdHere.current = event.chat_id;
            navigate(`/app/chat/${event.chat_id}`, { replace: true });
            reloadChats();
          }
        } else if (event.type === "token") {
          update(id, (m) => ({ ...m, content: m.content + event.text }));
        } else if (event.type === "done") {
          const final = event.message_id ?? id;
          update(id, (m) => ({ ...m, id: final, content: event.answer ?? "", data: { ...m.data, removed_citations: event.removed_citations } }));
          id = final;
        } else if (event.type === "error") {
          // A refusal mid-answer: the text so far isn't an answer, so don't leave it on screen.
          update(id, (m) => ({ ...m, content: event.discard_partial ? "" : m.content, data: { ...m.data, error: event.detail } }));
        }
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        update(id, (m) => ({ ...m, data: { ...m.data, error: m.content ? null : "Stopped." } }));
      } else {
        update(id, (m) => ({ ...m, data: { ...m.data, error: (error as Error).message } }));
      }
    } finally {
      update(id, (m) => ({ ...m, streaming: false }));
      setBusy(false);
      abort.current = null;
      reloadChats();
    }
  };

  const rate = async (message: UiMessage, rating: "up" | "down", comment: string) => {
    await api("/feedback", {
      json: {
        rating, comment, message_id: message.id, question: message.question ?? "", answer: message.content,
        provider: message.data.provider ?? null,
        sources: [...new Set((message.data.sources ?? []).map((s) => s.source_name))].slice(0, 8),
      },
    });
  };

  const docs = documents.data;
  const showEmpty = !chatId && messages.length === 0;
  return (
    <div className="relative flex h-full flex-col">
      {showEmpty && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[420px]" aria-hidden="true">
          <div className="bg-glow absolute inset-0" />
          <div className="bg-dots absolute inset-0 opacity-60" />
        </div>
      )}
      <div className="relative flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 pb-8 pt-6 sm:px-6">
          {sharedBy && (
            <div className="mb-4">
              <Alert tone="blue">Shared by {sharedBy} · read-only. Asking a question starts your own chat.</Alert>
            </div>
          )}
          {docs && docs.stale_documents > 0 && (
            <div className="mb-4">
              <Alert tone="amber" action={<Link to="/app/library" className="text-sm font-medium underline">Open Library</Link>}>
                {docs.stale_documents} document(s) need re-indexing after a search-model change and are left out of search.
              </Alert>
            </div>
          )}
          {showEmpty ? (
            <EmptyChat documents={docs} loading={documents.loading} onAsk={ask} />
          ) : loadingChat ? (
            <div className="flex justify-center py-24"><Spinner /></div>
          ) : (
            <div className="space-y-8">
              {messages.map((message) =>
                message.role === "user" ? (
                  <div key={message.id} className="flex animate-fade-in justify-end">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl rounded-br-lg bg-gradient-to-br from-ink-100 to-ink-200/70 px-4 py-2.5 text-[15px] leading-6 text-ink-900 dark:from-ink-800 dark:to-ink-800/70 dark:text-ink-50">
                      {message.content}
                    </div>
                  </div>
                ) : (
                  <AssistantMessage key={message.id} message={message} providers={providers.data?.providers ?? []} onRate={rate}
                    onRetry={(question, providerId) => ask(question, providerId)} busy={busy} />
                ),
              )}
              <div ref={bottom} />
            </div>
          )}
        </div>
      </div>
      <div className="relative shrink-0 px-4 pb-3 pt-2 sm:px-6">
        <div className="mx-auto max-w-3xl">
          {scope.length > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-500">
              Searching only:
              {scope.map((id) => {
                const doc = docs?.documents.find((d) => d.source_id === id);
                return doc ? <Badge key={id}><FileIcon name={doc.source_name} className="h-3 w-3" />{doc.source_name}</Badge> : null;
              })}
            </div>
          )}
          <Composer
            onSend={ask}
            onStop={() => abort.current?.abort()}
            busy={busy}
            providers={providers.data?.providers ?? []}
            defaultProvider={providers.data?.default ?? null}
            documents={docs?.documents ?? []}
            rerankAvailable={Boolean(docs?.reranker)}
            settings={settings}
            setSettings={setSettings}
            scope={scope}
            setScope={setScope}
            autoFocus={showEmpty}
          />
          <p className="mt-2 text-center text-[11px] text-ink-400">AfriSearch can be wrong. Check important facts against the cited sources.</p>
        </div>
      </div>
    </div>
  );
}
