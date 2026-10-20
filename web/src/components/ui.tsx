// Shared building blocks: buttons, badges, dialogs, menus, toasts.
import { CheckCircle2, Loader2, X, XCircle } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useClickOutside } from "../lib/hooks";

/** Keep Tab inside an open dialog, focus it on open, and return focus to where it was on close. */
function useFocusTrap(ref: React.RefObject<HTMLElement>, open: boolean) {
  useEffect(() => {
    if (!open || !ref.current) return;
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () => Array.from(ref.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? []);
    const autofocus = ref.current.querySelector<HTMLElement>("[autofocus]");
    (autofocus ?? focusable()[0] ?? ref.current).focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const [first, last] = [items[0], items[items.length - 1]];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [ref, open]);
}

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-gradient text-white shadow-sm shadow-brand-900/20 hover:brightness-110 active:brightness-95",
  secondary:
    "bg-white text-ink-800 ring-1 ring-ink-200 hover:bg-ink-50 shadow-sm dark:bg-ink-900 dark:text-ink-100 dark:ring-ink-700 dark:hover:bg-ink-800",
  ghost: "text-ink-600 hover:bg-ink-100 hover:text-ink-900 dark:text-ink-300 dark:hover:bg-ink-800 dark:hover:text-white",
  danger: "bg-red-600 text-white hover:bg-red-700 shadow-sm disabled:bg-red-600/50",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}) {
  const sizes = { sm: "h-8 px-3 text-sm gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-6 text-base gap-2" };
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center rounded-xl font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:focus-visible:ring-offset-ink-950",
        sizes[size],
        VARIANTS[variant],
        className,
      )}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function IconButton({
  label,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cx(
        "inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-500 transition hover:bg-ink-100 hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:opacity-40 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-white",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

const TONES = {
  gray: "bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-300",
  brand: "bg-brand-50 text-brand-800 ring-1 ring-inset ring-brand-200 dark:bg-brand-950 dark:text-brand-300 dark:ring-brand-900",
  green: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  blue: "bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  violet: "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  red: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
  amber: "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

export function Badge({ tone = "gray", children, className }: { tone?: keyof typeof TONES; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("h-5 w-5 animate-spin text-ink-400", className)} aria-label="Loading" />;
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("rounded-2xl border border-ink-200/80 bg-white shadow-soft dark:border-ink-800 dark:bg-ink-900/70 dark:shadow-none", className)}>
      {children}
    </div>
  );
}

export function Alert({ tone = "amber", title, children, action }: { tone?: "amber" | "red" | "blue"; title?: string; children: ReactNode; action?: ReactNode }) {
  const tones = {
    amber: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200",
    red: "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/60 dark:text-red-200",
    blue: "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-200",
  };
  return (
    <div role={tone === "red" ? "alert" : "status"} className={cx("flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-sm", tones[tone])}>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        <div className={title ? "mt-0.5" : ""}>{children}</div>
      </div>
      {action}
    </div>
  );
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (value: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:opacity-50",
        checked ? "bg-brand-700" : "bg-ink-300 dark:bg-ink-700",
      )}
    >
      <span className={cx("inline-block h-5 w-5 rounded-full bg-white shadow transition", checked ? "translate-x-5" : "translate-x-0.5")} />
    </button>
  );
}

export function Modal({ open, onClose, title, children, footer, wide }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  useFocusTrap(dialog, open);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div className="absolute inset-0 bg-ink-950/50 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx("relative w-full animate-scale-in rounded-2xl bg-white shadow-2xl ring-1 ring-ink-900/5 dark:bg-ink-900 dark:ring-white/10", wide ? "max-w-2xl" : "max-w-md")}
      >
        <div className="flex items-center justify-between border-b border-ink-100 px-5 py-4 dark:border-ink-800">
          <h2 className="text-base font-semibold">{title}</h2>
          <IconButton label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-ink-100 px-5 py-3 dark:border-ink-800">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

export function Drawer({ open, onClose, title, subtitle, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  const panel = useRef<HTMLElement>(null);
  useFocusTrap(panel, open);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-ink-950/40" onClick={onClose} />
      <aside ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="absolute inset-y-0 right-0 flex w-full max-w-xl animate-fade-in flex-col bg-white shadow-2xl dark:bg-ink-900">
        <div className="flex items-start justify-between gap-4 border-b border-ink-100 px-5 py-4 dark:border-ink-800">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">{title}</h2>
            {subtitle && <div className="mt-1 text-sm text-ink-500">{subtitle}</div>}
          </div>
          <IconButton label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </div>,
    document.body,
  );
}

/** A button that opens a floating panel below it. */
export function Popover({ trigger, children, align = "left", width = "w-72", up = false }: {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  align?: "left" | "right";
  width?: string;
  up?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useClickOutside(ref, close, open);
  return (
    <div className="relative" ref={ref}>
      {trigger({ open, toggle: () => setOpen((o) => !o) })}
      {open && (
        <div
          className={cx(
            "absolute z-40 animate-scale-in rounded-xl border border-ink-200/80 bg-white/95 p-1.5 shadow-lift backdrop-blur dark:border-ink-700 dark:bg-ink-900/95",
            width,
            align === "right" ? "right-0" : "left-0",
            up ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}

export function MenuItem({ icon, children, onClick, danger, disabled, hint }: {
  icon?: ReactNode;
  children: ReactNode;
  onClick?: () => void;
  danger?: boolean;
  disabled?: boolean;
  hint?: ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50",
        danger ? "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950" : "hover:bg-ink-100 dark:hover:bg-ink-800",
      )}
    >
      {icon && <span className="shrink-0 text-ink-500 dark:text-ink-400">{icon}</span>}
      <span className="min-w-0 flex-1">{children}</span>
      {hint}
    </button>
  );
}

export function ConfirmDialog({ open, title, children, confirmLabel, onConfirm, onClose, danger = true, confirmDisabled }: {
  open: boolean;
  confirmDisabled?: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
  danger?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant={danger ? "danger" : "primary"}
            loading={busy}
            disabled={confirmDisabled}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
                onClose();
              } finally {
                setBusy(false);
              }
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm text-ink-600 dark:text-ink-300">{children}</div>
    </Modal>
  );
}

export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-700 ring-1 ring-brand-100 dark:bg-brand-950 dark:text-brand-400 dark:ring-brand-900/60">{icon}</div>
      <h3 className="mt-4 text-base font-semibold">{title}</h3>
      {children && <div className="mt-1.5 max-w-sm text-sm text-ink-500 dark:text-ink-400">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** The magnifier mark on the brand gradient. */
export function LogoMark({ className }: { className?: string }) {
  // Each mark needs its own gradient id: a gradient defined in a hidden copy (e.g. the
  // desktop sidebar on a phone) doesn't render for the others.
  const gradient = `afrisearch-mark-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" className={cx("shrink-0", className)} aria-hidden="true">
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f97316" />
          <stop offset="0.55" stopColor="#c2410c" />
          <stop offset="1" stopColor="#b91c1c" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
      <circle cx="14" cy="14" r="7" fill="none" stroke="#fff" strokeWidth="3" />
      <path d="M19 19l6 6" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/** A keyboard key, for shortcut hints. */
export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd className={cx("inline-flex h-5 min-w-5 items-center justify-center rounded border border-ink-200 bg-white px-1 font-sans text-[10px] font-medium text-ink-500 shadow-[0_1px_0] shadow-ink-200 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-400 dark:shadow-ink-950", className)}>
      {children}
    </kbd>
  );
}

/** The title block at the top of a page. */
export function PageHeader({ title, description, icon, actions }: { title: string; description?: ReactNode; icon?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 items-center gap-3.5">
        {icon && (
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-700 ring-1 ring-brand-100 dark:bg-brand-950/60 dark:text-brand-400 dark:ring-brand-900/60">
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h1 className="font-display text-[28px] font-semibold leading-tight">{title}</h1>
          {description && <p className="mt-0.5 text-sm text-ink-500 dark:text-ink-400">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const STAT_TONES = {
  brand: "bg-brand-50 text-brand-700 dark:bg-brand-950/60 dark:text-brand-400",
  green: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400",
  blue: "bg-sky-50 text-sky-700 dark:bg-sky-950/60 dark:text-sky-400",
  violet: "bg-violet-50 text-violet-700 dark:bg-violet-950/60 dark:text-violet-400",
  amber: "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-400",
};

/** A number with a label, an icon and an optional hint. */
export function Stat({ label, value, hint, icon, tone = "brand", className }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: keyof typeof STAT_TONES;
  className?: string;
}) {
  return (
    <Card className={cx("p-4 sm:p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-ink-500 dark:text-ink-400">{label}</p>
        {icon && <span className={cx("flex h-8 w-8 shrink-0 items-center justify-center rounded-xl", STAT_TONES[tone])}>{icon}</span>}
      </div>
      <p className="mt-2 text-[26px] font-semibold leading-none tabular-nums tracking-tight">{value}</p>
      {hint && <div className="mt-2 text-xs text-ink-400">{hint}</div>}
    </Card>
  );
}

export function Logo({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <LogoMark className="h-7 w-7" />
      {!compact && <span className="text-lg">AfriSearch</span>}
    </span>
  );
}

// --- toasts ---------------------------------------------------------------------------

interface Toast {
  id: number;
  message: string;
  tone: "success" | "error";
}

const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Toast["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((all) => [...all, { id, message, tone }]);
    setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), tone === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className="pointer-events-auto flex animate-fade-in items-start gap-3 rounded-xl border border-ink-200/80 bg-white/95 px-4 py-3 text-sm shadow-lift backdrop-blur dark:border-ink-700 dark:bg-ink-900/95">
            {toast.tone === "success" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
            )}
            <span className="flex-1">{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
