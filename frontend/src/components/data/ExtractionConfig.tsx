import clsx from "clsx";
import type { ProcessingMode } from "@/types";
import { useI18n } from "@/hooks/useI18n";

export interface ExtractionCfg {
  chunk_size: number;
  chunk_overlap: number;
  processing_mode: ProcessingMode;
  merge_threshold: number;
  parallel_chunks: boolean;
  max_workers: number;
}

export const DEFAULT_CFG: ExtractionCfg = {
  chunk_size: 10000,
  chunk_overlap: 800,
  processing_mode: "auto",
  merge_threshold: 16000,
  parallel_chunks: true,
  max_workers: 4,
};

function NumberField({
  label,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
  suffix,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (n: number) => void;
  suffix?: string;
}) {
  return (
    <label className={clsx("block", disabled && "opacity-50")}>
      <span className="vs-label">{label}</span>
      <div className="relative">
        <input
          type="number"
          className="vs-input font-mono pr-10"
          value={Number.isNaN(value) ? "" : value}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={(e) => {
            const n = Number.parseInt(e.target.value, 10);
            onChange(Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : min);
          }}
        />
        {suffix && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-[var(--vs-fg-subtle)] pointer-events-none">
            {suffix}
          </span>
        )}
      </div>
    </label>
  );
}

function SegControl<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-sm overflow-hidden bg-[var(--vs-border)] p-[2px]">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "px-3 py-[4px] text-[12px] rounded-sm transition-colors",
            o.value === value
              ? "bg-[var(--vs-accent-bg)] text-white"
              : "text-[var(--vs-fg)] hover:bg-[var(--vs-hover)]"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

interface Props {
  cfg: ExtractionCfg;
  onChange: (next: ExtractionCfg) => void;
}

export function ExtractionConfigForm({ cfg, onChange }: Props) {
  const { t } = useI18n();
  const set = (patch: Partial<ExtractionCfg>) => onChange({ ...cfg, ...patch });
  const isAuto = cfg.processing_mode === "auto";
  const isMerge = cfg.processing_mode === "merge";

  return (
    <div className="vs-card p-5 space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <NumberField
          label={t("dp.chunk_size")}
          value={cfg.chunk_size}
          min={2000}
          max={30000}
          step={500}
          onChange={(n) => set({ chunk_size: n })}
          suffix="chars"
        />
        <NumberField
          label={t("dp.chunk_overlap")}
          value={cfg.chunk_overlap}
          min={0}
          max={3000}
          step={100}
          onChange={(n) => set({ chunk_overlap: n })}
          suffix="chars"
        />
        <div>
          <span className="vs-label">{t("dp.processing_mode")}</span>
          <SegControl
            value={cfg.processing_mode}
            options={[
              { value: "auto", label: t("dp.mode_auto") },
              { value: "merge", label: t("dp.mode_merge") },
              { value: "per_chunk", label: t("dp.mode_per_chunk") },
            ]}
            onChange={(m) => set({ processing_mode: m })}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <NumberField
          label={t("dp.merge_threshold")}
          value={cfg.merge_threshold}
          min={2000}
          max={100000}
          step={1000}
          disabled={!isAuto}
          onChange={(n) => set({ merge_threshold: n })}
          suffix="chars"
        />
        <label className={clsx("block", isMerge && "opacity-50")}>
          <span className="vs-label">{t("dp.parallel_chunks")}</span>
          <div className="flex items-center gap-2 h-[30px]">
            <button
              disabled={isMerge}
              onClick={() => set({ parallel_chunks: !cfg.parallel_chunks })}
              className={clsx(
                "relative w-[36px] h-[18px] rounded-full transition-colors",
                cfg.parallel_chunks ? "bg-[var(--vs-accent)]" : "bg-[var(--vs-border)]",
                isMerge && "cursor-not-allowed"
              )}
              title={cfg.parallel_chunks ? "On" : "Off"}
            >
              <span
                className={clsx(
                  "absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white transition-all",
                  cfg.parallel_chunks ? "left-[20px]" : "left-[2px]"
                )}
              />
            </button>
            <span className="text-[12px] text-[var(--vs-fg)]">
              {cfg.parallel_chunks ? "On" : "Off"}
            </span>
          </div>
        </label>
        <label
          className={clsx(
            "block",
            (isMerge || !cfg.parallel_chunks) && "opacity-50"
          )}
        >
          <span className="vs-label">
            {t("dp.max_workers")}: {cfg.max_workers}
          </span>
          <input
            type="range"
            min={1}
            max={16}
            step={1}
            value={cfg.max_workers}
            disabled={isMerge || !cfg.parallel_chunks}
            onChange={(e) =>
              set({ max_workers: Number.parseInt(e.target.value, 10) })
            }
            className="w-full accent-[var(--vs-accent)]"
          />
        </label>
      </div>
    </div>
  );
}
