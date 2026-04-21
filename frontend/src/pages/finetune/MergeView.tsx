import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  GitMerge,
  Loader2,
} from "lucide-react";
import { DiffEditor } from "@monaco-editor/react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { usePageLabels } from "@/hooks/usePageLabels";
import { getFineTuneData } from "@/api/finetune";
import {
  getFlowState,
  getSupplement,
  listSupplements,
  merge,
} from "@/api/diagnosis";
import type {
  FineTuneRow,
  FlowState,
  MergeResponse,
  SupplementDataset,
} from "@/types";

function summarizeRows(rows: FineTuneRow[]): Record<string, unknown> {
  const counts: Record<string, number> = { qa: 0, choice: 0, tf: 0, other: 0 };
  for (const r of rows) {
    const q = String(r.question_type ?? "").toLowerCase();
    if (q === "qa") counts.qa += 1;
    else if (q === "single_choice" || q === "multiple_choice") counts.choice += 1;
    else if (q === "true_false") counts.tf += 1;
    else counts.other += 1;
  }
  return {
    total_rows: rows.length,
    type_counts: counts,
  };
}

export function MergeView() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const project = useSession((s) => s.currentProject);
  const openTab = useSession((s) => s.openTab);

  const [supplements, setSupplements] = useState<SupplementDataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [supplementRows, setSupplementRows] = useState<FineTuneRow[]>([]);
  const [originalRows, setOriginalRows] = useState<FineTuneRow[]>([]);

  const [targetTotal, setTargetTotal] = useState(1000);
  const [diagRatio, setDiagRatio] = useState(0.35);
  const [mixWithOriginal, setMixWithOriginal] = useState(true);
  const [excludeSameL2, setExcludeSameL2] = useState(true);
  const [fallback, setFallback] = useState(true);
  const [seed, setSeed] = useState(42);

  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState("");
  const [mergeResult, setMergeResult] = useState<MergeResponse | null>(null);
  const [flowState, setFlowState] = useState<FlowState | null>(null);

  const refreshSupplements = useCallback(async () => {
    if (!project) return;
    try {
      const list = await listSupplements(project.id);
      setSupplements(list);
      if (list.length && !datasetId) setDatasetId(list[0].dataset_id);
    } catch {
      /* ignore */
    }
  }, [project, datasetId]);

  const refreshOriginal = useCallback(async () => {
    if (!project) return;
    try {
      const rows = await getFineTuneData(project.id);
      setOriginalRows(rows);
    } catch {
      /* ignore */
    }
  }, [project]);

  const refreshFlow = useCallback(async () => {
    if (!project) return;
    try {
      const fs = await getFlowState(project.id);
      setFlowState(fs);
    } catch {
      /* ignore */
    }
  }, [project]);

  useEffect(() => {
    refreshSupplements();
    refreshOriginal();
    refreshFlow();
  }, [refreshSupplements, refreshOriginal, refreshFlow]);

  useEffect(() => {
    if (!project || !datasetId) {
      setSupplementRows([]);
      return;
    }
    let cancel = false;
    (async () => {
      try {
        const data = await getSupplement(project.id, datasetId, 1_000_000);
        if (cancel) return;
        setSupplementRows(data.preview);
      } catch {
        if (!cancel) setSupplementRows([]);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [project, datasetId]);

  // Live estimate of merge outcome (local preview — actual values come from backend)
  const estimatedMerge = useMemo(() => {
    const diagTarget = mixWithOriginal
      ? Math.min(supplementRows.length, Math.round(targetTotal * diagRatio))
      : Math.min(supplementRows.length, targetTotal);
    const diagSelected = diagTarget;

    let origPool = originalRows.length;
    if (excludeSameL2) {
      const usedL2 = new Set<string>();
      for (const r of supplementRows) {
        const ids = Array.isArray(r.l2_statement_ids)
          ? (r.l2_statement_ids as string[])
          : r.l2_statement_id
          ? [String(r.l2_statement_id)]
          : [];
        for (const x of ids) if (x) usedL2.add(x);
      }
      origPool = originalRows.filter((r) => {
        const ids = Array.isArray(r.l2_statement_ids)
          ? (r.l2_statement_ids as string[])
          : r.l2_statement_id
          ? [String(r.l2_statement_id)]
          : [];
        return !ids.some((x) => usedL2.has(String(x)));
      }).length;
    }
    const origTarget = Math.max(0, targetTotal - diagSelected);
    const origAvailable = Math.min(origPool, origTarget);
    const fallbackUsed =
      fallback && origAvailable < origTarget
        ? Math.min(originalRows.length - origAvailable, origTarget - origAvailable)
        : 0;
    const total = mixWithOriginal
      ? diagSelected + origAvailable + fallbackUsed
      : diagSelected;

    return {
      diagPool: supplementRows.length,
      diagSelected,
      origPool,
      origTarget,
      origAvailable,
      fallbackUsed,
      total,
    };
  }, [
    supplementRows,
    originalRows,
    targetTotal,
    diagRatio,
    mixWithOriginal,
    excludeSameL2,
    fallback,
  ]);

  const leftSummary = useMemo(
    () => JSON.stringify(summarizeRows(originalRows), null, 2),
    [originalRows]
  );
  const rightSummary = useMemo(() => {
    const merged: FineTuneRow[] = [
      ...supplementRows.slice(0, estimatedMerge.diagSelected),
      ...originalRows.slice(
        0,
        estimatedMerge.origAvailable + estimatedMerge.fallbackUsed
      ),
    ];
    return JSON.stringify(
      {
        ...summarizeRows(merged),
        source_dataset_id: datasetId || "—",
        diagnostic_selected: estimatedMerge.diagSelected,
        original_selected: estimatedMerge.origAvailable + estimatedMerge.fallbackUsed,
        fallback_used: estimatedMerge.fallbackUsed,
      },
      null,
      2
    );
  }, [supplementRows, originalRows, estimatedMerge, datasetId]);

  const handleMerge = async () => {
    if (!project || !datasetId) return;
    setMerging(true);
    setMergeError("");
    setMergeResult(null);
    try {
      const result = await merge(project.id, {
        dataset_id: datasetId,
        target_total: targetTotal,
        diagnostic_ratio: diagRatio,
        mix_with_original: mixWithOriginal,
        exclude_same_l2: excludeSameL2,
        fallback_random_if_insufficient: fallback,
        random_seed: seed,
      });
      setMergeResult(result);
      setFlowState(result.flow_state);
      await refreshOriginal();
    } catch (e: unknown) {
      const err = e as { message?: string };
      setMergeError(err?.message ?? "Merge failed");
    } finally {
      setMerging(false);
    }
  };

  const canMerge =
    !!datasetId && supplementRows.length > 0 && targetTotal > 0 && !merging;

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1280px] mx-auto px-10 py-6 space-y-6">
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">
            {t("merge.title")}
          </h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("merge.desc")}</p>
        </div>

        {/* Pre-check */}
        {supplements.length === 0 ? (
          <div className="vs-card p-4 border-[#dcdcaa]/50 bg-[#dcdcaa]/5">
            <div className="flex items-start gap-3">
              <AlertCircle
                size={18}
                className="text-[#dcdcaa] shrink-0 mt-0.5"
              />
              <div className="text-[13px] text-[#dcdcaa]">
                {t("merge.need_supplement")}
              </div>
            </div>
          </div>
        ) : originalRows.length === 0 ? (
          <div className="vs-card p-4 border-[#dcdcaa]/50 bg-[#dcdcaa]/5">
            <div className="flex items-start gap-3">
              <AlertCircle
                size={18}
                className="text-[#dcdcaa] shrink-0 mt-0.5"
              />
              <div className="text-[13px] text-[#dcdcaa]">
                {t("merge.need_original")}
              </div>
            </div>
          </div>
        ) : null}

        {supplements.length > 0 && (
          <>
            {/* Dataset picker */}
            <section>
              <h2 className="vs-panel-title mb-3">
                {t("merge.dataset_picker_title")}
              </h2>
              <div className="vs-card p-4">
                <select
                  className="vs-input w-full"
                  value={datasetId}
                  onChange={(e) => setDatasetId(e.target.value)}
                >
                  {supplements.map((s) => (
                    <option key={s.dataset_id} value={s.dataset_id}>
                      {s.created_at} · rows={s.row_count} · id={s.dataset_id}
                    </option>
                  ))}
                </select>
                <div className="mt-2 text-[11px] text-[var(--vs-fg-muted)] font-mono flex gap-4">
                  <span>
                    {t("merge.stat_diag_pool")}: {supplementRows.length}
                  </span>
                  <span>
                    {t("merge.stat_orig_pool")}: {originalRows.length}
                  </span>
                </div>
              </div>
            </section>

            {/* Config */}
            <section>
              <h2 className="vs-panel-title mb-3">{t("merge.config_title")}</h2>
              <div className="vs-card p-4 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <NumField
                    label={t("merge.target_total")}
                    value={targetTotal}
                    min={1}
                    max={500000}
                    step={50}
                    onChange={setTargetTotal}
                  />
                  <div>
                    <label className="vs-label">{t("merge.diag_ratio")}</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.01}
                        value={diagRatio}
                        onChange={(e) =>
                          setDiagRatio(parseFloat(e.target.value))
                        }
                        className="flex-1 accent-[var(--vs-accent)]"
                      />
                      <span className="text-[12px] font-mono text-[var(--vs-fg-strong)] w-[48px] text-right">
                        {diagRatio.toFixed(2)}
                      </span>
                    </div>
                  </div>
                  <NumField
                    label={t("merge.seed")}
                    value={seed}
                    min={0}
                    max={9999999}
                    step={1}
                    onChange={setSeed}
                  />
                </div>
                <div className="flex flex-wrap gap-6">
                  <label className="flex items-center gap-2 text-[12px] text-[var(--vs-fg)]">
                    <input
                      type="checkbox"
                      checked={mixWithOriginal}
                      onChange={(e) => setMixWithOriginal(e.target.checked)}
                      className="accent-[var(--vs-accent)]"
                    />
                    {t("merge.mix_with_original")}
                  </label>
                  <label className="flex items-center gap-2 text-[12px] text-[var(--vs-fg)]">
                    <input
                      type="checkbox"
                      checked={excludeSameL2}
                      onChange={(e) => setExcludeSameL2(e.target.checked)}
                      className="accent-[var(--vs-accent)]"
                    />
                    {t("merge.exclude_same_l2")}
                  </label>
                  <label className="flex items-center gap-2 text-[12px] text-[var(--vs-fg)]">
                    <input
                      type="checkbox"
                      checked={fallback}
                      onChange={(e) => setFallback(e.target.checked)}
                      className="accent-[var(--vs-accent)]"
                    />
                    {t("merge.fallback")}
                  </label>
                </div>
                <div className="text-[12px] text-[var(--vs-fg-muted)] font-mono border-t border-[var(--vs-border)] pt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
                  <span>
                    {t("merge.stat_diag_sel")}: {estimatedMerge.diagSelected}
                  </span>
                  <span>
                    {t("merge.stat_orig_sel")}: {estimatedMerge.origAvailable}
                  </span>
                  <span>
                    {t("merge.stat_fallback")}: {estimatedMerge.fallbackUsed}
                  </span>
                  <span>
                    {t("merge.stat_total")}: {estimatedMerge.total}
                  </span>
                </div>
              </div>
            </section>

            {/* Diff viewer */}
            <section>
              <h2 className="vs-panel-title mb-3">{t("merge.diff_title")}</h2>
              <div className="vs-card overflow-hidden">
                <div className="grid grid-cols-2 text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)]">
                  <div className="px-4 py-2">{t("merge.diff_left")}</div>
                  <div className="px-4 py-2 border-l border-[var(--vs-border)]">
                    {t("merge.diff_right")}
                  </div>
                </div>
                <div style={{ height: 340 }}>
                  <DiffEditor
                    original={leftSummary}
                    modified={rightSummary}
                    language="json"
                    theme="vs-dark"
                    options={{
                      readOnly: true,
                      renderSideBySide: true,
                      minimap: { enabled: false },
                      fontSize: 12,
                      scrollBeyondLastLine: false,
                      wordWrap: "on",
                    }}
                  />
                </div>
              </div>
            </section>

            {/* Execute */}
            <section className="space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  className="vs-btn flex items-center gap-2"
                  onClick={handleMerge}
                  disabled={!canMerge}
                >
                  {merging ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <GitMerge size={14} />
                  )}
                  {t("merge.execute")}
                </button>
                {mergeError && (
                  <span className="text-[12px] text-[#f48771] flex items-center gap-1">
                    <AlertCircle size={12} />
                    {mergeError}
                  </span>
                )}
              </div>

              {mergeResult && (
                <div className="vs-card p-4 border-[#4ec9b0]/50 bg-[#4ec9b0]/5">
                  <div className="flex items-center gap-2 text-[13px] text-[#4ec9b0] mb-2">
                    <CheckCircle2 size={14} />
                    {t("merge.done", {
                      diag: String(mergeResult.stats.diagnostic_selected ?? 0),
                      orig: String(mergeResult.stats.original_selected ?? 0),
                      total: String(mergeResult.merged_count),
                    })}
                  </div>
                  <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono">
                    {mergeResult.merged_file}
                  </div>
                </div>
              )}

              {flowState?.merged_ready && (
                <div className="flex items-center gap-2">
                  <button
                    className="vs-card px-4 py-3 flex items-center gap-3 hover:border-[var(--vs-accent)]"
                    onClick={() => openTab(buildTab("fine_tuning"))}
                  >
                    <div className="text-left">
                      <div className="text-[13px] text-[var(--vs-fg-strong)]">
                        {t("merge.go_step5")}
                      </div>
                      <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono mt-0.5">
                        {t("merge.flow_ready", {
                          rows: String(flowState.merged_rows ?? 0),
                        })}
                      </div>
                    </div>
                    <ArrowRight size={16} className="text-[var(--vs-accent)] ml-2" />
                  </button>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function NumField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="vs-label">{label}</label>
      <input
        type="number"
        className="vs-input font-mono"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number.parseFloat(e.target.value) || 0)}
      />
    </div>
  );
}
