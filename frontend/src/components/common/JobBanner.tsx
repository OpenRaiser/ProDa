import clsx from "clsx";
import {
  AlertCircle,
  Ban,
  CheckCircle2,
  Loader2,
} from "lucide-react";

export interface JobLike {
  status: "pending" | "running" | "done" | "error" | "cancelled";
  progress: number;
  message: string;
  total?: number;
  done?: number;
  error?: string | null;
  effective_mode?: string;
}

interface Props {
  job: JobLike;
  labels: {
    pending: string;
    running: string;
    done: string;
    error: string;
    cancelled: string;
  };
  extras?: React.ReactNode;
}

export function JobBanner({ job, labels, extras }: Props) {
  const color =
    job.status === "error"
      ? "#f48771"
      : job.status === "done"
      ? "#4ec9b0"
      : job.status === "cancelled"
      ? "#dcdcaa"
      : "var(--vs-accent)";

  const Icon =
    job.status === "error"
      ? AlertCircle
      : job.status === "done"
      ? CheckCircle2
      : job.status === "cancelled"
      ? Ban
      : Loader2;

  const label =
    job.status === "pending"
      ? labels.pending
      : job.status === "running"
      ? labels.running
      : job.status === "done"
      ? labels.done
      : job.status === "cancelled"
      ? labels.cancelled
      : labels.error;

  return (
    <div className="vs-card p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <Icon
          size={14}
          style={{ color }}
          className={clsx(
            (job.status === "running" || job.status === "pending") &&
              "animate-spin"
          )}
        />
        <span className="text-[13px] text-white">{label}</span>
        {job.effective_mode && (
          <span className="text-[11px] text-[var(--vs-fg-subtle)] font-mono">
            · mode={job.effective_mode}
          </span>
        )}
        {(job.total ?? 0) > 0 && (
          <span className="text-[11px] text-[var(--vs-fg-subtle)] font-mono">
            · {job.done ?? 0}/{job.total}
          </span>
        )}
        {extras}
        <span className="ml-auto text-[11px] text-[var(--vs-fg-muted)] font-mono">
          {job.progress}%
        </span>
      </div>
      <div className="h-[4px] bg-[var(--vs-panel)] rounded-sm overflow-hidden">
        <div
          className="h-full transition-all"
          style={{
            width: `${Math.max(0, Math.min(100, job.progress))}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <div className="text-[11px] text-[var(--vs-fg-muted)] truncate" title={job.message}>
        {job.message}
      </div>
      {job.error && (
        <pre className="text-[11px] text-[#f48771] font-mono whitespace-pre-wrap max-h-[180px] overflow-auto">
          {job.error}
        </pre>
      )}
    </div>
  );
}
