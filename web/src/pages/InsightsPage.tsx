// Usage and answer quality for the workspace.
import {
  BarChart3, Clock3, Coins, FileStack, HardDrive, MessagesSquare, ScanText, SearchX, TextQuote, ThumbsDown, ThumbsUp,
} from "lucide-react";
import { useState } from "react";
import { FileTile } from "../components/answer";
import { Alert, Card, EmptyState, PageHeader, Spinner, Stat } from "../components/ui";
import { formatSize, formatTokens, formatUsd, shortModelName, timeAgo } from "../lib/format";
import { useApi } from "../lib/hooks";
import type { Insights, UsageSummary } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

/** Share of helpful ratings as a ring. */
function RatingRing({ up, total }: { up: number; total: number }) {
  const share = total ? up / total : 0;
  const radius = 34;
  const length = 2 * Math.PI * radius;
  return (
    <div className="relative h-24 w-24 shrink-0">
      <svg viewBox="0 0 80 80" className="h-24 w-24 -rotate-90" aria-hidden="true">
        <circle cx="40" cy="40" r={radius} fill="none" strokeWidth="8" className="stroke-ink-100 dark:stroke-ink-800" />
        {total > 0 && (
          <circle cx="40" cy="40" r={radius} fill="none" strokeWidth="8" strokeLinecap="round" className="stroke-emerald-500"
            strokeDasharray={`${share * length} ${length}`} />
        )}
      </svg>
      <span className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-semibold tabular-nums">{total ? `${Math.round(share * 100)}%` : "–"}</span>
        <span className="text-[10px] uppercase tracking-wide text-ink-400">helpful</span>
      </span>
    </div>
  );
}

function UsageCard({ usage }: { usage: UsageSummary }) {
  const month = new Date(`${usage.since}T00:00:00`).toLocaleDateString(undefined, { month: "long" });
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="flex items-center gap-2 font-semibold"><Coins className="h-4 w-4 text-amber-600" /> AI usage in {month}</h2>
          <p className="mt-0.5 text-xs text-ink-500">Answers from cloud models (Claude, ChatGPT, Gemini). Local models are free.</p>
        </div>
        <div className="text-right">
          <p className="text-[26px] font-semibold leading-none tabular-nums">{formatUsd(usage.cost_usd ?? (usage.answers ? null : 0))}</p>
          <p className="mt-1 text-xs text-ink-400">estimated cost</p>
        </div>
      </div>
      {usage.answers ? (
        <>
          <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
            {[["Answers", usage.answers.toLocaleString()], ["Tokens in", formatTokens(usage.input_tokens)], ["Tokens out", formatTokens(usage.output_tokens)]].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-ink-50 px-3 py-2.5 dark:bg-ink-800/50">
                <p className="text-xs text-ink-500">{label}</p>
                <p className="mt-0.5 font-semibold tabular-nums">{value}</p>
              </div>
            ))}
          </div>
          <table className="mt-4 w-full text-sm">
            <thead className="text-left text-xs text-ink-400">
              <tr><th className="pb-2 font-medium">Model</th><th className="pb-2 text-right font-medium">Answers</th><th className="pb-2 text-right font-medium">Tokens</th><th className="pb-2 text-right font-medium">Cost</th></tr>
            </thead>
            <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
              {usage.models.map((m) => (
                <tr key={`${m.provider}-${m.model}`}>
                  <td className="py-2"><span className="font-medium">{shortModelName(m.model)}</span> <span className="text-xs text-ink-400">{m.provider}</span></td>
                  <td className="py-2 text-right tabular-nums">{m.answers}</td>
                  <td className="py-2 text-right tabular-nums text-ink-500">{formatTokens(m.input_tokens + m.output_tokens)}</td>
                  <td className="py-2 text-right tabular-nums">{formatUsd(m.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {usage.unpriced_answers > 0 && (
            <p className="mt-3 text-xs text-ink-400">
              {usage.unpriced_answers} answer{usage.unpriced_answers === 1 ? "" : "s"} from models without a configured price aren't in the total
              (set <code className="text-[11px]">AFRISEARCH_MODEL_PRICES</code>).
            </p>
          )}
        </>
      ) : <p className="mt-5 rounded-xl bg-ink-50 px-4 py-6 text-center text-sm text-ink-500 dark:bg-ink-800/40">No cloud-model answers this month.</p>}
    </Card>
  );
}

/** Questions per day: one series, so one validated color and no legend. */
function QuestionsChart({ days }: { days: Insights["per_day"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((d) => d.questions));
  const ticks = max <= 4 ? Array.from({ length: max + 1 }, (_, i) => i) : [0, Math.round(max / 2), max];
  const label = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  return (
    <figure>
      <div className="relative flex h-48 gap-2">
        <div className="flex flex-col justify-between pb-6 text-right text-[11px] tabular-nums text-ink-400" aria-hidden="true">
          {[...ticks].reverse().map((t) => <span key={t}>{t}</span>)}
        </div>
        <div className="relative flex-1">
          <div className="absolute inset-x-0 bottom-6 top-0 flex flex-col justify-between" aria-hidden="true">
            {ticks.map((t) => <div key={t} className="border-t border-ink-100 dark:border-ink-800" />)}
          </div>
          <div className="absolute inset-x-0 bottom-6 top-0 flex items-end gap-[2px]">
            {days.map((day, i) => (
              <div
                key={day.day}
                className="relative flex h-full flex-1 items-end justify-center"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              >
                <div
                  className="w-full max-w-[28px] rounded-t-md bg-gradient-to-t from-brand-600 to-amber-400 transition-opacity"
                  style={{ height: `${(day.questions / max) * 100}%`, minHeight: day.questions ? 2 : 0, opacity: hover === null || hover === i ? 1 : 0.55 }}
                />
                {hover === i && (
                  <div className="pointer-events-none absolute bottom-full z-10 mb-2 whitespace-nowrap rounded-lg bg-ink-900 px-2.5 py-1.5 text-xs text-white shadow-lg dark:bg-white dark:text-ink-900">
                    <span className="font-semibold tabular-nums">{day.questions}</span> question{day.questions === 1 ? "" : "s"} · {label(day.day)}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="absolute inset-x-0 bottom-0 flex justify-between text-[11px] text-ink-400" aria-hidden="true">
            <span>{label(days[0].day)}</span>
            <span>{label(days[days.length - 1].day)}</span>
          </div>
        </div>
      </div>
      <figcaption className="sr-only">
        <table>
          <caption>Questions asked per day, last {days.length} days</caption>
          <tbody>{days.map((d) => <tr key={d.day}><th>{d.day}</th><td>{d.questions}</td></tr>)}</tbody>
        </table>
      </figcaption>
    </figure>
  );
}

export function InsightsPage() {
  const { current } = useWorkspace();
  const { data, loading, error } = useApi<Insights>("/insights");
  if (loading && !data) return <div className="flex justify-center py-24"><Spinner /></div>;
  if (error) return <div className="mx-auto max-w-5xl p-6"><Alert tone="red">{error}</Alert></div>;
  if (!data) return null;
  const maxCited = Math.max(1, ...data.top_documents.map((d) => d.answers));
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader icon={<BarChart3 className="h-5 w-5" />} title="Insights"
        description={<>How <span className="font-medium text-ink-700 dark:text-ink-300">{current?.name}</span> is being used, and how good the answers are.</>} />

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Questions" value={data.questions} icon={<MessagesSquare className="h-4 w-4" />}
          hint={`in ${data.chats} chat${data.chats === 1 ? "" : "s"} · ${data.people} ${data.people === 1 ? "person" : "people"}`} />
        <Stat label="Not covered" value={data.not_covered} icon={<SearchX className="h-4 w-4" />} tone="amber" hint="no good match in documents" />
        <Stat label="Answer time" value={data.average_seconds !== null ? `${data.average_seconds}s` : "–"} icon={<Clock3 className="h-4 w-4" />} tone="blue" hint="on average" />
        <Stat label="AI cost this month" value={formatUsd(data.usage.cost_usd ?? (data.usage.answers ? null : 0))} icon={<Coins className="h-4 w-4" />} tone="green"
          hint={`${formatTokens(data.usage.input_tokens + data.usage.output_tokens)} tokens`} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="p-5 lg:col-span-3">
          <h2 className="font-semibold">Questions per day</h2>
          <p className="mb-4 text-xs text-ink-500">Last 14 days</p>
          {data.questions ? <QuestionsChart days={data.per_day} /> : (
            <EmptyState icon={<BarChart3 className="h-6 w-6" />} title="No questions yet">Questions asked in this workspace show up here.</EmptyState>
          )}
        </Card>
        <Card className="p-5 lg:col-span-2">
          <h2 className="font-semibold">Most cited documents</h2>
          <p className="mb-4 text-xs text-ink-500">Answers that used each document</p>
          {data.top_documents.length ? (
            <ul className="space-y-3">
              {data.top_documents.map((doc) => (
                <li key={doc.source_name}>
                  <div className="flex items-center gap-2.5 text-sm">
                    <FileTile name={doc.source_name} size="sm" />
                    <span className="min-w-0 flex-1 truncate">{doc.source_name}</span>
                    <span className="tabular-nums text-ink-500">{doc.answers}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-ink-100 dark:bg-ink-800">
                    <div className="h-full rounded-full bg-gradient-to-r from-brand-600 to-amber-400" style={{ width: `${(doc.answers / maxCited) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="py-8 text-center text-sm text-ink-500">Nothing cited yet.</p>}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3"><UsageCard usage={data.usage} /></div>
        <Card className="flex flex-col p-5 lg:col-span-2">
          <h2 className="font-semibold">Answer ratings</h2>
          <p className="text-xs text-ink-500">From 👍 and 👎 in chats</p>
          <div className="mt-4 flex flex-1 items-center gap-5">
            <RatingRing up={data.feedback.up} total={data.feedback.total} />
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2"><ThumbsUp className="h-4 w-4 text-emerald-600" /><span className="tabular-nums font-medium">{data.feedback.up}</span> helpful</li>
              <li className="flex items-center gap-2"><ThumbsDown className="h-4 w-4 text-red-600" /><span className="tabular-nums font-medium">{data.feedback.down}</span> not helpful</li>
            </ul>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Documents" value={data.documents} icon={<FileStack className="h-4 w-4" />} />
        <Stat label="Passages" value={data.passages.toLocaleString()} icon={<TextQuote className="h-4 w-4" />} tone="violet" />
        <Stat label="Read with OCR" value={data.ocr_documents} icon={<ScanText className="h-4 w-4" />} tone="blue" />
        <Stat label="Storage" value={formatSize(data.bytes) || "0 KB"} icon={<HardDrive className="h-4 w-4" />} tone="amber" />
      </div>

      <Card className="mt-4">
        <div className="border-b border-ink-100 px-5 py-4 dark:border-ink-800">
          <h2 className="font-semibold">Recent feedback</h2>
          <p className="text-xs text-ink-500">Use 👎 comments to find documents that are missing or answers that go wrong.</p>
        </div>
        {data.feedback.recent.length ? (
          <ul className="divide-y divide-ink-100 dark:divide-ink-800">
            {data.feedback.recent.map((item, i) => (
              <li key={i} className="flex gap-3 px-5 py-3.5">
                {item.rating === "up"
                  ? <ThumbsUp className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-label="Helpful" />
                  : <ThumbsDown className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-label="Not helpful" />}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{item.question}</p>
                  {item.comment && <p className="mt-0.5 text-sm text-ink-600 dark:text-ink-400">“{item.comment}”</p>}
                  <p className="mt-1 text-xs text-ink-400">{[item.email, item.provider, timeAgo(item.time)].filter(Boolean).join(" · ")}</p>
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="px-5 py-8 text-center text-sm text-ink-500">No ratings yet. Rate answers with 👍 or 👎 in a chat.</p>}
      </Card>
    </div>
  );
}
