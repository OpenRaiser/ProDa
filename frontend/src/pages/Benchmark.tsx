import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Play,
  Square,
  Loader2,
  Download,
  Save,
  ArrowRight,
  AlertCircle,
  FileCode2,
  Link2,
} from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { usePageLabels } from "@/hooks/usePageLabels";
import {
  startBenchmark,
  getBenchmarkJob,
  cancelBenchmarkJob,
} from "@/api/benchmark";
import {
  getBenchmark,
  getKnowledgeCore,
  saveBenchmark,
} from "@/api/projects";
import type {
  BenchmarkJob,
  KnowledgeCore,
  MCQItem,
} from "@/types";
import { JobBanner } from "@/components/common/JobBanner";
import { EditableTable, type ColumnDef } from "@/components/data/EditableTable";
import { reconcileFiltered, stripRid, withRid } from "@/lib/rowKey";

interface FlatMCQ {
  sample_id: string;
  chain_id: string;
  domain_context: string;
  process_name: string;
  question: string;
  opt_A: string;
  opt_B: string;
  opt_C: string;
  opt_D: string;
  answer: string;
  explanation: string;
  [key: string]: unknown;
}

function toFlat(m: MCQItem): FlatMCQ {
  const opts = m.options ?? ({ A: "", B: "", C: "", D: "" } as MCQItem["options"]);
  return {
    sample_id: String(m.sample_id ?? ""),
    chain_id: String(m.chain_id ?? ""),
    domain_context: String(m.domain_context ?? ""),
    process_name: String(m.process_name ?? ""),
    question: String(m.question ?? ""),
    opt_A: String(opts.A ?? ""),
    opt_B: String(opts.B ?? ""),
    opt_C: String(opts.C ?? ""),
    opt_D: String(opts.D ?? ""),
    answer: String(m.answer ?? ""),
    explanation: String(m.explanation ?? ""),
  };
}

function fromFlat(f: FlatMCQ): MCQItem {
  return {
    sample_id: f.sample_id,
    chain_id: f.chain_id,
    domain_context: f.domain_context,
    process_name: f.process_name,
    question: f.question,
    options: {
      A: f.opt_A,
      B: f.opt_B,
      C: f.opt_C,
      D: f.opt_D,
    },
    answer: f.answer,
    explanation: f.explanation,
  };
}

export function Benchmark() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const project = useSession((s) => s.currentProject);
  const openTab = useSession((s) => s.openTab);
  const profiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);
  const job = useSession((s) => s.benchmarkJob);
  const setJob = useSession((s) => s.setBenchmarkJob);
  const knowledgeCoreCache = useSession((s) => s.knowledgeCoreCache);
  const setKnowledgeCoreCache = useSession((s) => s.setKnowledgeCoreCache);

  const [kc, setKc] = useState<KnowledgeCore | null>(null);
  const [rows, setRows] = useState<MCQItem[]>([]);
  const [flatRows, setFlatRows] = useState<FlatMCQ[]>([]);
  const [dirty, setDirty] = useState(false);
  const [savingRows, setSavingRows] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [filter, setFilter] = useState("");

  const [qpc, setQpc] = useState(5);
  const [workers, setWorkers] = useState(4);
  const [temperature, setTemperature] = useState(0.3);
  const [retries, setRetries] = useState(2);

  const [starting, setStarting] = useState(false);
  const [launchError, setLaunchError] = useState("");

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshAll = useCallback(async () => {
    if (!project) return;
    try {
      const [c, bm] = await Promise.all([
        getKnowledgeCore(project.id),
        getBenchmark(project.id),
      ]);
      setKc(c ?? null);
      if (c) setKnowledgeCoreCache(c);
      const list = bm ?? [];
      setRows(list);
      setFlatRows(withRid(list.map(toFlat)) as unknown as FlatMCQ[]);
      setDirty(false);
    } catch {
      // ignore
    }
  }, [project, setKnowledgeCoreCache]);

  const startPolling = useCallback((jobId: string) => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    pollTimer.current = setInterval(async () => {
      try {
        const j = await getBenchmarkJob(jobId);
        setJob(j);
        if (j.status === "done" || j.status === "error" || j.status === "cancelled") {
          if (pollTimer.current) {
            clearInterval(pollTimer.current);
            pollTimer.current = null;
          }
          if (j.result?.mcqs) {
            setRows(j.result.mcqs);
            setFlatRows(
              withRid(j.result.mcqs.map(toFlat)) as unknown as FlatMCQ[]
            );
            setDirty(false);
          }
        }
      } catch {
        // ignore polling errors
      }
    }, 900);
  }, [setJob]);

  useEffect(() => {
    refreshAll();
    // Resume polling if a benchmark job was in-progress before this tab was left
    const existing = useSession.getState().benchmarkJob;
    if (existing && (existing.status === "pending" || existing.status === "running")) {
      startPolling(existing.id);
    }
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [refreshAll, startPolling]);

  // Poll for KC until step 1 completes (handles case where user is on this tab while step 1 runs)
  useEffect(() => {
    const effectiveKc = kc ?? knowledgeCoreCache;
    if (effectiveKc || !project) return;
    const timer = setInterval(async () => {
      try {
        const c = await getKnowledgeCore(project.id);
        if (c && (c.l3_chains ?? []).length > 0) {
          setKc(c);
          setKnowledgeCoreCache(c);
        }
      } catch {
        // ignore
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [kc, knowledgeCoreCache, project, setKnowledgeCoreCache]);

  const effectiveKc = kc ?? knowledgeCoreCache;
  const l3Count = (effectiveKc?.l3_chains ?? []).length;
  const targetTotal = Math.max(0, l3Count) * Math.max(1, qpc);

  const handleStart = async (resume = false) => {
    if (!project) return;
    setLaunchError("");
    if (l3Count === 0) {
      setLaunchError(t("bm.need_kc"));
      return;
    }
    if (!selectedModel) {
      setLaunchError(t("dp.choose_model_first"));
      return;
    }
    const [providerKey, modelId] = selectedModel.split("::");
    const profile = profiles[providerKey];
    if (!profile?.configured || !profile.api_key) {
      setLaunchError(t("dp.api_not_ready"));
      return;
    }
    setStarting(true);
    try {
      const jobId = await startBenchmark(project.id, {
        max_workers: workers,
        questions_per_chain: qpc,
        temperature,
        retries,
        resume,
        llm: {
          provider: providerKey,
          model: modelId,
          api_key: profile.api_key,
          api_base: profile.api_base,
        },
      });
      setJob({
        id: jobId,
        project_id: project.id,
        status: "pending",
        progress: 0,
        message: resume ? "Resuming..." : "Queued",
        total: targetTotal,
        done: resume ? Math.min(rows.length, targetTotal) : 0,
        chains: l3Count,
        questions_per_chain: qpc,
        result: null,
        error: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      startPolling(jobId);
    } catch (e: any) {
      setLaunchError(e?.message ?? "Start failed");
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async () => {
    if (!job) return;
    try {
      const j = await cancelBenchmarkJob(job.id);
      setJob(j);
    } catch {
      // ignore
    }
  };

  const handleSave = async () => {
    if (!project) return;
    if (filter.trim()) {
      setSaveMsg(t("bm.filter_warn"));
      return;
    }
    setSavingRows(true);
    try {
      const cleaned = stripRid(flatRows) as FlatMCQ[];
      const reconstructed = cleaned.map(fromFlat);
      await saveBenchmark(project.id, reconstructed);
      setRows(reconstructed);
      setDirty(false);
      setSaveMsg(t("bm.saved"));
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e: any) {
      setSaveMsg(e?.message ?? "Save failed");
    } finally {
      setSavingRows(false);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(rows, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "benchmark_mcq.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const filtered = useMemo(() => {
    if (!filter.trim()) return flatRows;
    const s = filter.toLowerCase();
    return flatRows.filter((r) =>
      JSON.stringify(r).toLowerCase().includes(s)
    );
  }, [filter, flatRows]);

  const running = job?.status === "pending" || job?.status === "running";
  const stats = job?.result?.stats;

  const cols: ColumnDef<FlatMCQ>[] = [
    { key: "sample_id", title: t("bm.col_sample"), readonly: true, width: "140px" },
    { key: "chain_id", title: t("bm.col_chain"), readonly: true, width: "110px" },
    { key: "question", title: t("bm.col_question"), type: "textarea" },
    { key: "opt_A", title: "A", type: "textarea" },
    { key: "opt_B", title: "B", type: "textarea" },
    { key: "opt_C", title: "C", type: "textarea" },
    { key: "opt_D", title: "D", type: "textarea" },
    { key: "answer", title: t("bm.col_answer"), width: "80px" },
    { key: "domain_context", title: t("bm.col_domain"), width: "120px" },
    { key: "explanation", title: t("bm.col_explanation"), type: "textarea" },
  ];

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1280px] mx-auto px-10 py-8 space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">{t("bm.title")}</h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("bm.desc")}</p>
        </div>

        {/* KC status */}
        {l3Count === 0 ? (
          <div className="vs-card p-4 border-[#dcdcaa]/50 bg-[#dcdcaa]/5">
            <div className="flex items-start gap-3">
              <AlertCircle size={18} className="text-[#dcdcaa] shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="text-[13px] text-[#dcdcaa] mb-2">
                  {t("bm.need_kc")}
                </div>
                <button
                  className="vs-btn-secondary flex items-center gap-2"
                  onClick={() => openTab(buildTab("data_processing"))}
                >
                  <FileCode2 size={14} />
                  {t("bm.goto_step1")}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-[12px] text-[#4ec9b0]">
            <Link2 size={14} />
            <span>{t("bm.loaded_chains", { count: String(l3Count) })}</span>
          </div>
        )}

        {/* Config */}
        {l3Count > 0 && (
          <section>
            <h2 className="vs-panel-title mb-3">{t("bm.config_title")}</h2>
            <div className="vs-card p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <SliderField
                  label={t("bm.questions_per_chain")}
                  value={qpc}
                  min={1}
                  max={10}
                  step={1}
                  onChange={setQpc}
                />
                <SliderField
                  label={t("bm.max_workers")}
                  value={workers}
                  min={1}
                  max={16}
                  step={1}
                  onChange={setWorkers}
                />
                <SliderField
                  label={t("bm.temperature")}
                  value={temperature}
                  min={0}
                  max={1.5}
                  step={0.1}
                  precision={1}
                  onChange={setTemperature}
                />
                <SliderField
                  label={t("bm.retries")}
                  value={retries}
                  min={0}
                  max={5}
                  step={1}
                  onChange={setRetries}
                />
              </div>
              <div className="text-[12px] text-[var(--vs-fg-muted)] font-mono border-t border-[var(--vs-border)] pt-3">
                {t("bm.expected_total", {
                  chains: String(l3Count),
                  qpc: String(qpc),
                  total: String(targetTotal),
                })}
              </div>
            </div>
          </section>
        )}

        {/* Start / Cancel / Job banner */}
        {l3Count > 0 && (
          <section className="space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              {/* Resume button — shown when partial results exist */}
              {rows.length > 0 && rows.length < targetTotal && (
                <button
                  className="vs-btn flex items-center gap-2"
                  onClick={() => handleStart(true)}
                  disabled={starting || running || !selectedModel}
                >
                  {starting ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Play size={14} />
                  )}
                  {t("bm.resume", { done: String(rows.length), total: String(targetTotal) })}
                </button>
              )}
              {/* Normal start button — always shown */}
              <button
                className={rows.length > 0 ? "vs-btn-secondary flex items-center gap-2" : "vs-btn flex items-center gap-2"}
                onClick={() => handleStart(false)}
                disabled={starting || running || !selectedModel}
              >
                {starting ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Play size={14} />
                )}
                {rows.length > 0 ? t("bm.restart") : t("bm.start")}
              </button>
              {running && (
                <button
                  className="vs-btn-secondary flex items-center gap-2"
                  onClick={handleCancel}
                >
                  <Square size={12} />
                  {t("bm.cancel")}
                </button>
              )}
              {!selectedModel && (
                <button
                  onClick={() => setConfigModalOpen(true)}
                  className="text-[12px] text-[var(--vs-accent)] hover:underline"
                >
                  {t("dp.choose_model_first")} →
                </button>
              )}
              {launchError && (
                <span className="text-[12px] text-[#f48771] flex items-center gap-1">
                  <AlertCircle size={12} />
                  {launchError}
                </span>
              )}
            </div>

            {job && (
              <JobBanner
                job={job}
                labels={{
                  pending: t("bm.job_pending"),
                  running: t("bm.job_running"),
                  done: t("bm.job_done"),
                  error: t("bm.job_error"),
                  cancelled: t("bm.job_cancelled"),
                }}
              />
            )}

            {stats && (
              <div className="vs-card p-4">
                <div className="vs-panel-title mb-3">{t("bm.stats_title")}</div>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                  <StatChip label={t("bm.stat_submitted")} value={stats.submitted ?? 0} />
                  <StatChip
                    label={t("bm.stat_succeeded")}
                    value={stats.succeeded ?? 0}
                    color="#4ec9b0"
                  />
                  <StatChip
                    label={t("bm.stat_failed")}
                    value={stats.failed ?? 0}
                    color="#f48771"
                  />
                  <StatChip
                    label={t("bm.stat_duplicates")}
                    value={stats.duplicates_dropped ?? 0}
                    color="var(--vs-fg-muted)"
                  />
                  <StatChip
                    label={t("bm.stat_semantic_dups")}
                    value={stats.semantic_dedup_dropped ?? 0}
                    color="#c586c0"
                  />
                  <StatChip
                    label={t("bm.stat_refill_rounds")}
                    value={stats.refill_rounds ?? 0}
                    color="#dcb67a"
                  />
                </div>
                {stats.adaptive_enabled && (
                  <div className="mt-3 text-[11px] text-[var(--vs-fg-muted)] font-mono">
                    {t("bm.stat_adaptive")}: {t("bm.adaptive_workers", {
                      initial: String(stats.initial_workers ?? 0),
                      minw: String(stats.min_workers ?? 0),
                      maxw: String(stats.max_workers_seen ?? 0),
                      final: String(stats.final_workers ?? 0),
                      adjusts: String(stats.worker_adjustments ?? 0),
                    })}
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* Results */}
        {rows.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="vs-panel-title">
                {t("bm.results_title")} · {rows.length}
              </h2>
              <div className="flex items-center gap-2">
                <input
                  className="vs-input w-[260px]"
                  placeholder={t("bm.filter_keyword")}
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
                {saveMsg && (
                  <span
                    className={clsx(
                      "text-[11px]",
                      saveMsg === t("bm.saved")
                        ? "text-[#4ec9b0]"
                        : "text-[#dcdcaa]"
                    )}
                  >
                    {saveMsg}
                  </span>
                )}
                {dirty && (
                  <span className="text-[11px] text-[#dcdcaa]">● unsaved</span>
                )}
                <button
                  className="vs-btn-secondary flex items-center gap-2"
                  onClick={handleSave}
                  disabled={savingRows || !dirty}
                >
                  {savingRows ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Save size={13} />
                  )}
                  {t("bm.save")}
                </button>
                <button
                  className="vs-btn flex items-center gap-2"
                  onClick={handleDownload}
                >
                  <Download size={13} />
                  {t("bm.download")}
                </button>
              </div>
            </div>

            <EditableTable<FlatMCQ>
              columns={cols}
              rows={filtered}
              onChange={(next) => {
                setFlatRows(reconcileFiltered(flatRows, filtered, next));
                setDirty(true);
              }}
              emptyTemplate={{
                sample_id: "",
                chain_id: "",
                domain_context: "",
                process_name: "",
                question: "",
                opt_A: "",
                opt_B: "",
                opt_C: "",
                opt_D: "",
                answer: "A",
                explanation: "",
              }}
              maxHeight="560px"
            />
          </section>
        )}

        {/* Next actions */}
        {rows.length > 0 && (
          <section>
            <h2 className="vs-panel-title mb-3">{t("dp.next_actions")}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <button
                className="vs-card p-4 flex items-center justify-between hover:border-[var(--vs-accent)] text-left"
                onClick={() => openTab(buildTab("data_processing"))}
              >
                <div>
                  <div className="text-[14px] text-[var(--vs-fg-strong)]">{t("bm.back_step1")}</div>
                  <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1 font-mono">
                    1_data_processing.py
                  </div>
                </div>
                <ArrowRight size={18} className="text-[var(--vs-accent)]" />
              </button>
              <button
                className="vs-card p-4 flex items-center justify-between hover:border-[var(--vs-accent)] text-left"
                onClick={() => openTab(buildTab("finetune"))}
              >
                <div>
                  <div className="text-[14px] text-[var(--vs-fg-strong)]">{t("bm.go_finetune")}</div>
                  <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1 font-mono">
                    3_finetune.py
                  </div>
                </div>
                <ArrowRight size={18} className="text-[var(--vs-accent)]" />
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function StatChip({
  label,
  value,
  color = "var(--vs-accent)",
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div
      className="vs-card px-3 py-2"
      style={{ borderLeft: `3px solid ${color}` }}
    >
      <div className="text-[10px] uppercase tracking-wider text-[var(--vs-fg-muted)]">
        {label}
      </div>
      <div className="text-[18px] font-light text-[var(--vs-fg-strong)] font-mono mt-0.5">
        {value}
      </div>
    </div>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  precision = 0,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  precision?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="vs-label mb-0">{label}</span>
        <span className="text-[12px] font-mono text-[var(--vs-fg-strong)]">
          {value.toFixed(precision)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number.parseFloat(e.target.value))}
        className="w-full accent-[var(--vs-accent)]"
      />
      <div className="flex justify-between text-[10px] text-[var(--vs-fg-subtle)] font-mono mt-0.5">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}
