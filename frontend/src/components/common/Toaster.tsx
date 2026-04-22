import { useEffect } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useSession, type Toast } from "@/store/useSession";

const DEFAULT_TIMEOUT: Record<Toast["severity"], number> = {
  success: 4000,
  info: 4000,
  warning: 5000,
  error: 0, // persistent until dismissed
};

const SEVERITY_META: Record<
  Toast["severity"],
  { icon: typeof AlertCircle; color: string; bg: string }
> = {
  success: { icon: CheckCircle2, color: "#4ec9b0", bg: "#4ec9b014" },
  info: { icon: Info, color: "var(--vs-accent)", bg: "#3794ff14" },
  warning: { icon: AlertTriangle, color: "#dcdcaa", bg: "#dcdcaa14" },
  error: { icon: AlertCircle, color: "#f48771", bg: "#f4877114" },
};

export function Toaster() {
  const toasts = useSession((s) => s.toasts);
  const dismiss = useSession((s) => s.dismissToast);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-4 z-[200] flex flex-col gap-2 w-[360px] max-w-[calc(100vw-32px)]">
      {toasts.map((t) => (
        <ToastRow key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
      ))}
    </div>
  );
}

function ToastRow({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: () => void;
}) {
  const meta = SEVERITY_META[toast.severity];
  const timeout = toast.timeout ?? DEFAULT_TIMEOUT[toast.severity];

  useEffect(() => {
    if (timeout <= 0) return;
    const t = setTimeout(onDismiss, timeout);
    return () => clearTimeout(t);
  }, [timeout, onDismiss]);

  const Icon = meta.icon;
  return (
    <div
      role="alert"
      className={clsx(
        "vs-card p-3 pr-2 shadow-popover flex items-start gap-2 text-[12px]",
        "animate-[fade-in_120ms_ease-out]"
      )}
      style={{ borderLeft: `3px solid ${meta.color}`, backgroundColor: meta.bg }}
    >
      <Icon size={14} style={{ color: meta.color }} className="shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] text-[var(--vs-fg-strong)] leading-snug">{toast.title}</div>
        {toast.description && (
          <div className="text-[11px] text-[var(--vs-fg-muted)] mt-0.5 whitespace-pre-wrap break-words">
            {toast.description}
          </div>
        )}
      </div>
      <button
        className="p-0.5 text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg-strong)] shrink-0"
        onClick={onDismiss}
        aria-label="Dismiss"
      >
        <X size={12} />
      </button>
    </div>
  );
}
