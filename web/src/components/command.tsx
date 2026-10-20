// The command palette (⌘K / Ctrl+K): jump to a page, a chat or a document, or run an action.
import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Kbd, cx } from "./ui";

export interface CommandItem {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon: ReactNode;
  keywords?: string;
  run: () => void;
}

export const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function CommandPalette({ open, onClose, items }: { open: boolean; onClose: () => void; items: CommandItem[] }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const list = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setIndex(0);
    const previous = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() => input.current?.focus());
    return () => previous?.focus?.();
  }, [open]);

  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return items.filter((item) => {
      const text = `${item.label} ${item.keywords ?? ""} ${item.group}`.toLowerCase();
      return words.every((word) => text.includes(word));
    }).slice(0, 40);
  }, [items, query]);

  useEffect(() => setIndex(0), [query]);
  useEffect(() => {
    list.current?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }, [index]);

  if (!open) return null;
  const choose = (item: CommandItem | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };
  const groups = [...new Set(matches.map((item) => item.group))];

  return createPortal(
    <div className="fixed inset-0 z-[55] flex items-start justify-center p-4 pt-[12vh]">
      <div className="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label="Search and commands"
        className="relative w-full max-w-xl animate-scale-in overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-ink-900/5 dark:bg-ink-900 dark:ring-white/10">
        <div className="flex items-center gap-3 border-b border-ink-100 px-4 dark:border-ink-800">
          <Search className="h-4 w-4 shrink-0 text-ink-400" />
          <input
            ref={input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(i + 1, matches.length - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
              else if (e.key === "Enter") { e.preventDefault(); choose(matches[index]); }
              else if (e.key === "Escape") { e.preventDefault(); onClose(); }
              else if (e.key === "Tab") e.preventDefault(); // focus stays in the palette
            }}
            placeholder="Search chats, documents and actions…"
            aria-label="Search chats, documents and actions"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-list"
            aria-activedescendant={matches[index] ? `command-${matches[index].id}` : undefined}
            className="h-14 flex-1 bg-transparent text-[15px] placeholder:text-ink-400 focus:outline-none"
          />
          <Kbd>Esc</Kbd>
        </div>
        <div ref={list} id="command-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
          {!matches.length && <p className="px-3 py-10 text-center text-sm text-ink-500">Nothing matches “{query}”.</p>}
          {groups.map((group) => (
            <div key={group} className="pb-1">
              <p className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-ink-400">{group}</p>
              {matches.map((item, i) => item.group !== group ? null : (
                <button
                  key={item.id}
                  id={`command-${item.id}`}
                  type="button"
                  role="option"
                  aria-selected={i === index}
                  data-index={i}
                  onMouseMove={() => setIndex(i)}
                  onClick={() => choose(item)}
                  className={cx("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition",
                    i === index ? "bg-brand-50 text-brand-900 dark:bg-brand-950/50 dark:text-brand-100" : "text-ink-700 dark:text-ink-300")}
                >
                  <span className={cx("shrink-0", i === index ? "text-brand-600 dark:text-brand-400" : "text-ink-400")}>{item.icon}</span>
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {item.hint && <span className="shrink-0 text-xs text-ink-400">{item.hint}</span>}
                  {i === index && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-brand-500" />}
                </button>
              ))}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 border-t border-ink-100 bg-ink-50/60 px-4 py-2 text-[11px] text-ink-500 dark:border-ink-800 dark:bg-ink-950/40">
          <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
          <span className="flex items-center gap-1"><Kbd>↵</Kbd> open</span>
          <span className="ml-auto flex items-center gap-1"><Kbd>{isMac ? "⌘" : "Ctrl"}</Kbd><Kbd>K</Kbd> anytime</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
