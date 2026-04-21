import { useRef, useState } from "react";
import {
  Upload,
  File as FileIcon,
  FileText,
  FileJson,
  Trash2,
  RefreshCw,
  Loader2,
} from "lucide-react";
import clsx from "clsx";
import type { UploadedFileMeta } from "@/types";
import { useI18n } from "@/hooks/useI18n";

const ACCEPT = ".pdf,.txt,.md,.docx,.json";

function pickIcon(ext: string) {
  const e = ext.toLowerCase();
  if (e === "json") return FileJson;
  if (e === "pdf") return FileIcon;
  if (e === "md" || e === "txt") return FileText;
  return FileIcon;
}

function humanSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

interface Props {
  uploads: UploadedFileMeta[];
  uploading: boolean;
  onUpload: (files: FileList) => void;
  onDelete: (fileId: string) => void;
  onRefresh: () => void;
}

export function FileUploadZone({
  uploads,
  uploading,
  onUpload,
  onDelete,
  onRefresh,
}: Props) {
  const { t } = useI18n();
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (!e.dataTransfer.files?.length) return;
    onUpload(e.dataTransfer.files);
  };

  return (
    <div>
      <div
        className={clsx(
          "vs-card px-4 py-6 text-center border-dashed transition-colors cursor-pointer",
          isDragging
            ? "border-[var(--vs-accent)] bg-[color:var(--vs-accent-bg)]/30"
            : "hover:border-[var(--vs-accent)]"
        )}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) onUpload(e.target.files);
            e.currentTarget.value = "";
          }}
        />
        <div className="flex items-center justify-center gap-2 text-[var(--vs-fg-muted)] pointer-events-none">
          {uploading ? (
            <Loader2 size={22} className="animate-spin text-[var(--vs-accent)]" />
          ) : (
            <Upload size={22} className="text-[var(--vs-accent)]" />
          )}
          <span className="text-[13px] text-[var(--vs-fg)]">{t("dp.drag_hint")}</span>
        </div>
        <div className="text-[11px] text-[var(--vs-fg-subtle)] mt-2 pointer-events-none">
          {t("dp.upload_hint")}  ·  {ACCEPT}
        </div>
      </div>

      <div className="flex items-center justify-between mt-3 mb-1">
        <span className="text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)]">
          {uploads.length} file{uploads.length === 1 ? "" : "s"}
        </span>
        <button
          className="flex items-center gap-1 text-[12px] text-[var(--vs-fg-muted)] hover:text-white"
          onClick={onRefresh}
        >
          <RefreshCw size={12} />
          {t("common.refresh")}
        </button>
      </div>

      {uploads.length === 0 ? (
        <div className="text-[12px] text-[var(--vs-fg-subtle)] italic px-1 py-2">
          {t("dp.no_uploads")}
        </div>
      ) : (
        <div className="space-y-1">
          {uploads.map((u) => {
            const Icon = pickIcon(u.ext);
            return (
              <div
                key={u.file_id}
                className="group flex items-center gap-2 px-2 py-[5px] rounded-sm bg-[var(--vs-sidebar)] hover:bg-[var(--vs-hover)]"
              >
                <Icon size={14} className="text-[#519aba] shrink-0" />
                <span className="font-mono text-[12.5px] text-[var(--vs-fg)] truncate flex-1">
                  {u.filename}
                </span>
                <span className="text-[11px] text-[var(--vs-fg-subtle)] shrink-0">
                  {humanSize(u.size)}
                </span>
                <button
                  className="opacity-0 group-hover:opacity-100 p-1 rounded-sm text-[var(--vs-fg-muted)] hover:text-[#f48771] hover:bg-[var(--vs-border)]"
                  onClick={() => onDelete(u.file_id)}
                  title="Remove"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
