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
  cancelFineTuneJob,
  getFineTuneData,
  getFineTuneJob,
  listFineTuneJobs,
  saveFineTuneData,
  startFineTune,
} from "@/api/finetune";
import { getKnowledgeCore } from "@/api/projects";
import type {
  FineTuneJob,
  FineTuneRow,
  KnowledgeCore,
} from "@/types";
import { JobBanner } from "@/components/common/JobBanner";
import { EditableTable, type ColumnDef } from "@/components/data/EditableTable";
import { reconcileFiltered, stripRid, withRid } from "@/lib/rowKey";

// Flattened row type — dict/list fields encoded as JSON strings for the editor
interface FlatRow {
  question_type: string;
  question: string;
  answer: string;
  options_json: string;
  explanation: string;
  link_ids: string;
  extra_json: string;
  [key: string]: unknown;
}

const KNOWN_FIELDS = new Set([
  "question_type",
  "question",
  "answer",
  "options",
  "explanation",
  "l2_statement_id",
  "l2_statement_ids",
  "linked_concepts",
]);

function toFlat(row: FineTuneRow): FlatRow {
  const options = row.options;
  const ids =
    row.l2_statement_ids ??
    (row.l2_statement_id ? [row.l2_statement_id] : []);
  const extra: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) {
    if (!KNOWN_FIELDS.has(k) && k !== "__rid__") extra[k] = v;
  }
  return {
    question_type: String(row.question_type ?? ""),
    question: String(row.question ?? ""),
    answer: String(row.answer ?? ""),
    options_json:
      options && typeof options === "object"
        ? JSON.stringify(options, null, 0)
        : "",
    explanation: String(row.explanation ?? ""),
    link_ids: Array.isArray(ids)
      ? (ids as unknown[]).map(String).join(", ")
      : "",
    extra_json: Object.keys(extra).length ? JSON.stringify(extra) : "",
  };
}

function fromFlat(f: FlatRow): FineTuneRow {
  const out: FineTuneRow = {
    question_type: f.question_type,
    question: f.question,
    answer: f.answer,
    explanation: f.explanation,
  };
  const opts = f.options_json.trim();
  if (opts) {
    try {
      out.options = JSON.parse(opts);
    } catch {
      out.options = { raw: opts } as Record<string, string>;
    }
  }
  const ids = f.link_ids.trim();
  if (ids) {
    const arr = ids
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (arr.length === 1) out.l2_statement_id = arr[0];
    else if (arr.length > 1) out.l2_statement_ids = arr;
  }
  const extra = f.extra_json.trim();
  if (extra) {
    try {
      Object.assign(out, JSON.parse(extra));
    } catch {
      // ignore malformed extra json
    }
  }
  return out;
}

const QTYPE_OPTIONS = [
  "all",
  "qa",
  "single_choice",
  "multiple_choice",
  "true_false",
];

export function GenerateView() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const project = useSession((s) => s.currentProject);
  const openTab = useSession((s) => s.openTab);
  const profiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);

  const [kc, setKc] = useState<KnowledgeCore | null>(null);
  const [rows, setRows] = useState<FineTuneRow[]>([]);
  const [flatRows, setFlatRows] = useState<FlatRow[]>([]);
  const [dirty, setDirty] = useState(false);
  const [savingRows, setSavingRows] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [qtypeFilter, setQtypeFilter] = useState<string>("all");
  const [kwFilter, setKwFilter] = useState("");

  // Config
  const [totalSamples, setTotalSamples] = useState(300);
  const [qaRatio, setQaRatio] = useState(0.6);
  const [choiceRatio, setChoiceRatio] = useState(0.3);
  const [singleChoiceRatio, setSingleChoiceRatio] = useState(0.7);
  const [trueRatio, setTrueRatio] = useState(0.6);
  const [maxWorkers, setMaxWorkers] = useState(6);
  const [retries, setRetries] = useState(2);
  const [batchSize, setBatchSize] = useState(8);
  const [l2WindowSize, setL2WindowSize] = useState(8);
  const [l1Topn, setL1Topn] = useState(20);
  const [allowL2Reuse, setAllowL2Reuse] = useState(true);
  const [authorNotes, setAuthorNotes] = useState("");

  const [job, setJob] = useState<FineTuneJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [launchError, setLaunchError] = useState("");
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshAll = useCallback(async () => {
    if (!project) return;
    try {
      const [c, ft] = await Promise.all([
        getKnowledgeCore(project.id),
        getFineTuneData(project.id),
      ]);
      setKc(c ?? null);
      setRows(ft);
      setFlatRows(withRid(ft.map(toFlat)) as unknown as FlatRow[]);
      setDirty(false);
    } catch {
      /* ignore */
    }
  }, [project]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  // Adopt a running job on mount (so switching section/tab doesn't lose it)
  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    (async () => {
      try {
        const jobs = await listFineTuneJobs(project.id);
        const running = jobs.find(
          (j) => j.status === "pending" || j.status === "running"
        );
        if (!cancelled && running) {
          setJob(running);
          startPolling(running.id);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
    // startPolling is stable (uses refs/setState only); only re-run if project changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  const l2Count = (kc?.l2_statements ?? []).length;

  const targets = useMemo(() => {
    const qa = Math.max(1, Math.round(totalSamples * qaRatio));
    const choice = Math.max(1, Math.round(totalSamples * choiceRatio));
    const tf = Math.max(1, totalSamples - qa - choice);
    return { qa, choice, tf, total: qa + choice + tf };
  }, [totalSamples, qaRatio, choiceRatio]);

  const startPolling = (jobId: string) => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    pollTimer.current = setInterval(async () => {
      try {
        const j = await getFineTuneJob(jobId);
        setJob(j);
        if (
          j.status === "done" ||
          j.status === "error" ||
          j.status === "cancelled"
        ) {
          if (pollTimer.current) {
            clearInterval(pollTimer.current);
            pollTimer.current = null;
          }
          if (j.result?.rows) {
            setRows(j.result.rows);
            setFlatRows(
              withRid(j.result.rows.map(toFlat)) as unknown as FlatRow[]
            );
            setDirty(false);
          }
        }
      } catch {
        /* ignore polling errors */
      }
    }, 900);
  };

  const handleStart = async () => {
    if (!project) return;
    setLaunchError("");
    if (l2Count === 0) {
      setLaunchError(t("ft.need_kc"));
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
      const jobId = await startFineTune(project.id, {
        total_samples: totalSamples,
        qa_ratio: qaRatio,
        choice_ratio: choiceRatio,
        single_choice_ratio: singleChoiceRatio,
        true_ratio: trueRatio,
        author_notes: authorNotes,
        max_workers: maxWorkers,
        retries,
        max_refill_rounds: 4,
        adaptive_concurrency: true,
        batch_size: batchSize,
        l2_window_size: l2WindowSize,
        l1_topn: l1Topn,
        allow_l2_reuse_after_exhausted: allowL2Reuse,
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
        message: "Queued",
        total: totalSamples,
        done: 0,
        total_samples: totalSamples,
        qa_ratio: qaRatio,
        choice_ratio: choiceRatio,
        true_ratio: trueRatio,
        result: null,
        error: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      startPolling(jobId);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLaunchError(err?.message ?? "Start failed");
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async () => {
    if (!job) return;
    try {
      const j = await cancelFineTuneJob(job.id);
      setJob(j);
    } catch {
      /* ignore */
    }
  };

  const handleSave = async () => {
    if (!project) return;
    if (qtypeFilter !== "all" || kwFilter.trim()) {
      setSaveMsg(t("ft.filter_warn"));
      return;
    }
    setSavingRows(true);
    try {
      const cleaned = stripRid(flatRows) as FlatRow[];
      const reconstructed = cleaned.map(fromFlat);
      await saveFineTuneData(project.id, reconstructed);
      setRows(reconstructed);
      setDirty(false);
      setSaveMsg(t("ft.saved"));
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setSaveMsg(err?.message ?? "Save failed");
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
    a.download = "finetune_data.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const filtered = useMemo(() => {
    let out = flatRows;
    if (qtypeFilter !== "all") {
      out = out.filter(
        (r) => String(r.question_type).toLowerCase() === qtypeFilter
      );
    }
    if (kwFilter.trim()) {
      const s = kwFilter.toLowerCase();
      out = out.filter((r) => JSON.stringify(r).toLowerCase().includes(s));
    }
    return out;
  }, [flatRows, qtypeFilter, kwFilter]);

  const running = job?.status === "pending" || job?.status === "running";
  const stats = job?.result?.stats;

  const cols: ColumnDef<FlatRow>[] = [
    {
      key: "question_type",
      title: t("ft.col_qtype"),
      width: "130px",
    },
    { key: "question", title: t("ft.col_question"), type: "textarea" },
    { key: "answer", title: t("ft.col_answer"), type: "textarea" },
    {
      key: "options_json",
      title: t("ft.col_options"),
      type: "textarea",
      placeholder: "{}",
    },
    { key: "explanation", title: t("ft.col_explanation"), type: "textarea" },
    {
      key: "link_ids",
      title: t("ft.col_links"),
      width: "180px",
      placeholder: "id1, id2",
    },
    {
      key: "extra_json",
      title: t("ft.col_extra"),
      type: "textarea",
      placeholder: "{}",
    },
  ];

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1280px] mx-auto px-10 py-6 space-y-6">
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">{t("ft.title")}</h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("ft.desc")}</p>
        </div>

        {/* KC status */}
        {l2Count === 0 ? (
          <div className="vs-card p-4 border-[#dcdcaa]/50 bg-[#dcdcaa]/5">
            <div className="flex items-start gap-3">
              <AlertCircle
                size={18}
                className="text-[#dcdcaa] shrink-0 mt-0.5"
              />
              <div className="flex-1">
                <div className="text-[13px] text-[#dcdcaa] mb-2">
                  {t("ft.need_kc")}
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
            <span>
              {t("ft.loaded_l2", { count: String(l2Count) })}
            </span>
          </div>
        )}

        {/* Config */}
        {l2Count > 0 && (
          <section>
            <h2 className="vs-panel-title mb-3">{t("ft.config_title")}</h2>
            <div className="vs-card p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <SliderField
                  label={t("ft.total_samples")}
                  value={totalSamples}
                  min={30}
                  max={5000}
                  step={10}
                  onChange={setTotalSamples}
                />
                <SliderField
                  label={t("ft.qa_ratio")}
                  value={qaRatio}
                  min={0.1}
                  max={0.9}
                  step={0.05}
                  precision={2}
                  onChange={setQaRatio}
                />
                <SliderField
                  label={t("ft.choice_ratio")}
                  value={choiceRatio}
                  min={0.05}
                  max={0.8}
                  step={0.05}
                  precision={2}
                  onChange={setChoiceRatio}
                />
                <SliderField
                  label={t("ft.single_choice_ratio")}
                  value={singleChoiceRatio}
                  min={0.1}
                  max={0.95}
                  step={0.05}
                  precision={2}
                  onChange={setSingleChoiceRatio}
                />
                <SliderField
                  label={t("ft.true_ratio")}
                  value={trueRatio}
                  min={0.1}
                  max={0.9}
                  step={0.05}
                  precision={2}
                  onChange={setTrueRatio}
                />
                <SliderField
                  label={t("ft.max_workers")}
                  value={maxWorkers}
                  min={1}
                  max={32}
                  step={1}
                  onChange={setMaxWorkers}
                />
                <SliderField
                  label={t("ft.retries")}
                  value={retries}
                  min={0}
                  max={5}
                  step={1}
                  onChange={setRetries}
                />
                <SliderField
                  label={t("ft.batch_size")}
                  value={batchSize}
                  min={1}
                  max={20}
                  step={1}
                  onChange={setBatchSize}
                />
                <SliderField
                  label={t("ft.l2_window")}
                  value={l2WindowSize}
                  min={1}
                  max={30}
                  step={1}
                  onChange={setL2WindowSize}
                />
                <SliderField
                  label={t("ft.l1_topn")}
                  value={l1Topn}
                  min={1}
                  max={80}
                  step={1}
                  onChange={setL1Topn}
                />
                <label className="flex items-center gap-2 text-[12px] text-[var(--vs-fg)] mt-5">
                  <input
                    type="checkbox"
                    checked={allowL2Reuse}
                    onChange={(e) => setAllowL2Reuse(e.target.checked)}
                    className="accent-[var(--vs-accent)]"
                  />
                  {t("ft.allow_l2_reuse")}
                </label>
              </div>
              <div>
                <label className="vs-label">{t("ft.author_notes")}</label>
                <textarea
                  className="vs-input min-h-[56px] font-mono"
                  value={authorNotes}
                  onChange={(e) => setAuthorNotes(e.target.value)}
                  placeholder={t("ft.author_notes_ph")}
                />
              </div>
              <div className="text-[12px] text-[var(--vs-fg-muted)] font-mono border-t border-[var(--vs-border)] pt-3">
                {t("ft.target_calc", {
                  qa: String(targets.qa),
                  choice: String(targets.choice),
                  tf: String(targets.tf),
                  total: String(targets.total),
                })}
              </div>
            </div>
          </section>
        )}

        {/* Start / Cancel / Job banner */}
        {l2Count > 0 && (
          <section className="space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <button
                className="vs-btn flex items-center gap-2"
                onClick={handleStart}
                disabled={starting || running || !selectedModel}
              >
                {starting ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Play size={14} />
                )}
                {t("ft.start")}
              </button>
              {running && (
                <button
                  className="vs-btn-secondary flex items-center gap-2"
                  onClick={handleCancel}
                >
                  <Square size={12} />
                  {t("ft.cancel")}
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
                  pending: t("ft.job_pending"),
                  running: t("ft.job_running"),
                  done: t("ft.job_done"),
                  error: t("ft.job_error"),
                  cancelled: t("ft.job_cancelled"),
                }}
              />
            )}

            {stats && (
              <div className="vs-card p-4">
                <div className="vs-panel-title mb-3">{t("ft.stats_title")}</div>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                  <StatChip label={t("ft.stat_submitted")} value={stats.submitted ?? 0} />
                  <StatChip
                    label={t("ft.stat_succeeded")}
                    value={stats.succeeded_jobs ?? 0}
                    color="#4ec9b0"
                  />
                  <StatChip
                    label={t("ft.stat_failed")}
                    value={stats.failed_jobs ?? 0}
                    color="#f48771"
                  />
                  <StatChip
                    label={t("ft.stat_refill_rounds")}
                    value={stats.refill_rounds ?? 0}
                    color="#dcb67a"
                  />
                  <StatChip
                    label={t("ft.stat_empty_windows")}
                    value={stats.empty_windows ?? 0}
                    color="var(--vs-fg-muted)"
                  />
                  <StatChip
                    label={t("ft.stat_batch")}
                    value={stats.batch_size ?? 0}
                    color="#c586c0"
                  />
                </div>
                {stats.adaptive_enabled && (
                  <div className="mt-3 text-[11px] text-[var(--vs-fg-muted)] font-mono">
                    {t("ft.stat_adaptive")}:{" "}
                    {t("bm.adaptive_workers", {
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

        {/* Results table */}
        {rows.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="vs-panel-title">
                {t("ft.results_title")} · {rows.length}
              </h2>
              <div className="flex items-center gap-2">
                <select
                  className="vs-input w-[160px]"
                  value={qtypeFilter}
                  onChange={(e) => setQtypeFilter(e.target.value)}
                >
                  {QTYPE_OPTIONS.map((o) => (
                    <option key={o} value={o}>
                      {o === "all" ? t("common.all") : o}
                    </option>
                  ))}
                </select>
                <input
                  className="vs-input w-[220px]"
                  placeholder={t("bm.filter_keyword")}
                  value={kwFilter}
                  onChange={(e) => setKwFilter(e.target.value)}
                />
                {saveMsg && (
                  <span
                    className={clsx(
                      "text-[11px]",
                      saveMsg === t("ft.saved")
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
                  {t("ft.save")}
                </button>
                <button
                  className="vs-btn flex items-center gap-2"
                  onClick={handleDownload}
                >
                  <Download size={13} />
                  {t("ft.download")}
                </button>
              </div>
            </div>

            <EditableTable<FlatRow>
              columns={cols}
              rows={filtered}
              onChange={(next) => {
                setFlatRows(reconcileFiltered(flatRows, filtered, next));
                setDirty(true);
              }}
              emptyTemplate={{
                question_type: "qa",
                question: "",
                answer: "",
                options_json: "",
                explanation: "",
                link_ids: "",
                extra_json: "",
              }}
              maxHeight="520px"
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
                onClick={() => openTab(buildTab("benchmark"))}
              >
                <div>
                  <div className="text-[14px] text-[var(--vs-fg-strong)]">
                    {t("ft.back_benchmark")}
                  </div>
                  <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1 font-mono">
                    2_benchmark.py
                  </div>
                </div>
                <ArrowRight size={18} className="text-[var(--vs-accent)]" />
              </button>
              <button
                className="vs-card p-4 flex items-center justify-between hover:border-[var(--vs-accent)] text-left"
                onClick={() => openTab(buildTab("fine_tuning"))}
              >
                <div>
                  <div className="text-[14px] text-[var(--vs-fg-strong)]">
                    {t("ft.go_finetune")}
                  </div>
                  <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1 font-mono">
                    5_fine_tuning.py
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
