// Usage and answer quality for the workspace.
import { BarChart3, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { FileIcon } from "../components/answer";
import { Alert, Card, EmptyState, Spinner } from "../components/ui";
import { formatSize, timeAgo } from "../lib/format";
import { useApi } from "../lib/hooks";
import type { Insights } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card className="p-4">
      <p className="text-sm text-ink-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-400">{hint}</p>}
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
                  className="w-full max-w-[28px] rounded-t-[4px] bg-brand-600 transition-opacity"
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
  const helpful = data.feedback.total ? `${Math.round((data.feedback.up / data.feedback.total) * 100)}%` : "–";
  const maxCited = Math.max(1, ...data.top_documents.map((d) => d.answers));
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight">Insights</h1>
      <p className="mt-1 text-sm text-ink-500">How {current?.name} is being used, and how good the answers are.</p>

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Questions answered" value={data.questions} hint={`in ${data.chats} chat${data.chats === 1 ? "" : "s"} · ${data.people} ${data.people === 1 ? "person" : "people"}`} />
        <Stat label="Rated helpful" value={helpful} hint={`${data.feedback.total} rating${data.feedback.total === 1 ? "" : "s"}`} />
        <Stat label="Not covered by documents" value={data.not_covered} hint="questions with no good match" />
        <Stat label="Average answer time" value={data.average_seconds !== null ? `${data.average_seconds}s` : "–"} />
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
                  <div className="flex items-center gap-2 text-sm">
                    <FileIcon name={doc.source_name} />
                    <span className="min-w-0 flex-1 truncate">{doc.source_name}</span>
                    <span className="tabular-nums text-ink-500">{doc.answers}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-ink-100 dark:bg-ink-800">
                    <div className="h-full rounded-full bg-brand-600" style={{ width: `${(doc.answers / maxCited) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="py-8 text-center text-sm text-ink-500">Nothing cited yet.</p>}
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Documents" value={data.documents} />
        <Stat label="Passages" value={data.passages} />
        <Stat label="Read with OCR" value={data.ocr_documents} />
        <Stat label="Storage" value={formatSize(data.bytes) || "0 KB"} />
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
