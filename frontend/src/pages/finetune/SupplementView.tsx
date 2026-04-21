import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Download,
  Loader2,
  Play,
  Square,
  Trash2,
  Info,
} from "lucide-react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import {
  cancelDiagnosisJob,
  deleteSupplement,
  getDiagnosisJob,
  getReport,
  getSupplement,
  listDiagnosisJobs,
  listReports,
  listSupplements,
  startSupplement,
} from "@/api/diagnosis";
import type {
  DiagnosisJob,
  DiagnosisReportSummary,
  FineTuneRow,
  SupplementDataset,
} from "@/types";
import { JobBanner } from "@/components/common/JobBanner";

export function SupplementView() {
  const { t } = useI18n();
  const project = useSession((s) => s.currentProject);
  const profiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);

  const [reports, setReports] = useState<DiagnosisReportSummary[]>([]);
  const [reportId, setReportId] = useState<string>("");
  const [issueCounts, setIssueCounts] = useState<{
    concept_gap: number;
    capability_deficit: number;
  }>({ concept_gap: 0, capability_deficit: 0 });

  // Params
  const [maxErrorSamples, setMaxErrorSamples] = useState(300);
  const [maxWorkers, setMaxWorkers] = useState(6);
  const [retries, setRetries] = useState(2);
  const [maxTokens, setMaxTokens] = useState(2048);

  // Windows matrix
  const [cgQa, setCgQa] = useState(4);
  const [cgChoice, setCgChoice] = useState(2);
  const [cgTf, setCgTf] = useState(1);
  const [cdQa, setCdQa] = useState(3);
  const [cdChoice, setCdChoice] = useState(3);
  const [cdTf, setCdTf] = useState(1);

  const [job, setJob] = useState<DiagnosisJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [launchError, setLaunchError] = useState("");

  const [supplements, setSupplements] = useState<SupplementDataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [preview, setPreview] = useState<FineTuneRow[]>([]);
  const [previewSummary, setPreviewSummary] =
    useState<SupplementDataset | null>(null);
  const [totalInDataset, setTotalInDataset] = useState(0);

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshReports = useCallback(async () => {
    if (!project) return;
    try {
      const list = await listReports(project.id);
      setReports(list);
      setReportId((prev) => prev || list[0]?.report_id || "");
    } catch {
      /* ignore */
    }
  }, [project]);

  const refreshSupplements = useCallback(async () => {
    if (!project) return;
    try {
      const list = await listSupplements(project.id);
      setSupplements(list);
      setDatasetId((prev) => prev || list[0]?.dataset_id || "");
    } catch {
      /* ignore */
    }
  }, [project]);

  useEffect(() => {
    refreshReports();
    refreshSupplements();
  }, [refreshReports, refreshSupplements]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  // Adopt a running "supplement" job on mount
  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    (async () => {
      try {
        const jobs = await listDiagnosisJobs(project.id);
        const running = jobs.find(
          (j) =>
            j.kind === "supplement" &&
            (j.status === "pending" || j.status === "running")
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  // Load report to show issue counts
  useEffect(() => {
    if (!project || !reportId) {
      setIssueCounts({ concept_gap: 0, capability_deficit: 0 });
      return;
    }
    let cancel = false;
    (async () => {
      try {
        const { report } = await getReport(project.id, reportId);
        if (cancel) return;
        const dist =
          (report.llm_diagnosis_issue_distribution as
            | Record<string, number>
            | undefined) ?? {};
        setIssueCounts({
          concept_gap: Number(dist.concept_gap ?? 0),
          capability_deficit: Number(dist.capability_deficit ?? 0),
        });
      } catch {
        if (!cancel) setIssueCounts({ concept_gap: 0, capability_deficit: 0 });
      }
    })();
    return () => {
      cancel = true;
    };
  }, [project, reportId]);

  // Load supplement preview when datasetId changes
  useEffect(() => {
    if (!project || !datasetId) {
      setPreview([]);
      setPreviewSummary(null);
      setTotalInDataset(0);
      return;
    }
    let cancel = false;
    (async () => {
      try {
        const data = await getSupplement(project.id, datasetId, 100);
        if (cancel) return;
        setPreview(data.preview);
        setPreviewSummary(data.summary);
        setTotalInDataset(data.total);
      } catch {
        if (!cancel) {
          setPreview([]);
          setPreviewSummary(null);
          setTotalInDataset(0);
        }
      }
    })();
    return () => {
      cancel = true;
    };
  }, [project, datasetId]);

  const estimated =
    issueCounts.concept_gap * (cgQa + cgChoice + cgTf) +
    issueCounts.capability_deficit * (cdQa + cdChoice + cdTf);

  const startPolling = (jobId: string) => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    pollTimer.current = setInterval(async () => {
      try {
        const j = await getDiagnosisJob(jobId);
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
          await refreshSupplements();
          if (j.result?.dataset_id) setDatasetId(j.result.dataset_id);
        }
      } catch {
        /* ignore */
      }
    }, 900);
  };

  const handleStart = async () => {
    if (!project) return;
    setLaunchError("");
    if (!reportId) {
      setLaunchError(t("sup.need_report"));
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
      const jobId = await startSupplement(project.id, {
        report_id: reportId,
        max_error_samples: maxErrorSamples,
        max_workers: maxWorkers,
        max_tokens: maxTokens,
        retries,
        concept_gap: { qa: cgQa, choice: cgChoice, tf: cgTf },
        capability_deficit: { qa: cdQa, choice: cdChoice, tf: cdTf },
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
        total: 0,
        done: 0,
        kind: "supplement",
        report_id: reportId,
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
      const j = await cancelDiagnosisJob(job.id);
      setJob(j);
    } catch {
      /* ignore */
    }
  };

  const handleDelete = async (dsId: string) => {
    if (!project) return;
    if (!window.confirm(t("sup.delete_confirm"))) return;
    try {
      await deleteSupplement(project.id, dsId);
      if (datasetId === dsId) setDatasetId("");
      await refreshSupplements();
    } catch {
      /* ignore */
    }
  };

  const handleDownload = async () => {
    if (!project || !datasetId) return;
    try {
      const data = await getSupplement(project.id, datasetId, 1_000_000);
      const blob = new Blob([JSON.stringify(data.preview, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${datasetId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      /* ignore */
    }
  };

  const running = job?.status === "pending" || job?.status === "running";
  const typeCounts = previewSummary?.stats?.type_counts;

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1280px] mx-auto px-10 py-6 space-y-6">
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">{t("sup.title")}</h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("sup.desc")}</p>
        </div>

        {reports.length === 0 ? (
          <div className="vs-card p-4 border-[#dcdcaa]/50 bg-[#dcdcaa]/5">
            <div className="flex items-start gap-3">
              <AlertCircle
                size={18}
                className="text-[#dcdcaa] shrink-0 mt-0.5"
              />
              <div className="text-[13px] text-[#dcdcaa]">
                {t("sup.need_report")}
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Report picker */}
            <section>
              <h2 className="vs-panel-title mb-3">
                {t("sup.report_picker_title")}
              </h2>
              <div className="vs-card p-4">
                <select
                  className="vs-input w-full"
                  value={reportId}
                  onChange={(e) => setReportId(e.target.value)}
                >
                  {reports.map((r) => (
                    <option key={r.report_id} value={r.report_id}>
                      {r.created_at} · {r.model_name} · errs=
                      {r.error_samples_count} · acc=
                      {(r.accuracy * 100).toFixed(1)}%
                    </option>
                  ))}
                </select>
                <div className="mt-2 text-[11px] text-[var(--vs-fg-muted)] font-mono flex gap-4">
                  <span>concept_gap: {issueCounts.concept_gap}</span>
                  <span>capability_deficit: {issueCounts.capability_deficit}</span>
                </div>
              </div>
            </section>

            {/* Params */}
            <section>
              <h2 className="vs-panel-title mb-3">{t("sup.config_title")}</h2>
              <div className="vs-card p-4 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <NumField
                    label={t("sup.max_error_samples")}
                    value={maxErrorSamples}
                    min={1}
                    max={200000}
                    step={10}
                    onChange={setMaxErrorSamples}
                  />
                  <NumField
                    label={t("sup.max_workers")}
                    value={maxWorkers}
                    min={1}
                    max={64}
                    step={1}
                    onChange={setMaxWorkers}
                  />
                  <NumField
                    label={t("sup.retries")}
                    value={retries}
                    min={0}
                    max={10}
                    step={1}
                    onChange={setRetries}
                  />
                  <NumField
                    label={t("sup.max_tokens")}
                    value={maxTokens}
                    min={256}
                    max={8192}
                    step={128}
                    onChange={setMaxTokens}
                  />
                </div>

                {/* Windows matrix */}
                <div>
                  <div className="vs-label">{t("sup.windows_title")}</div>
                  <div className="grid grid-cols-4 gap-2 text-[11px] text-[var(--vs-fg-muted)] font-mono mb-1">
                    <span></span>
                    <span>{t("sup.w_qa")}</span>
                    <span>{t("sup.w_choice")}</span>
                    <span>{t("sup.w_tf")}</span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 mb-2 items-center">
                    <span className="text-[12px] text-[#c586c0] font-mono">
                      concept_gap
                    </span>
                    <MiniNum value={cgQa} onChange={setCgQa} />
                    <MiniNum value={cgChoice} onChange={setCgChoice} />
                    <MiniNum value={cgTf} onChange={setCgTf} />
                  </div>
                  <div className="grid grid-cols-4 gap-2 items-center">
                    <span className="text-[12px] text-[#dcb67a] font-mono">
                      capability_deficit
                    </span>
                    <MiniNum value={cdQa} onChange={setCdQa} />
                    <MiniNum value={cdChoice} onChange={setCdChoice} />
                    <MiniNum value={cdTf} onChange={setCdTf} />
                  </div>
                </div>

                <div className="text-[12px] text-[var(--vs-fg-muted)] font-mono border-t border-[var(--vs-border)] pt-3 flex items-center gap-2">
                  <Info size={12} />
                  {t("sup.estimated", { count: String(estimated) })}
                </div>
              </div>
            </section>

            {/* Start / Cancel / Banner */}
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
                  {t("sup.start")}
                </button>
                {running && (
                  <button
                    className="vs-btn-secondary flex items-center gap-2"
                    onClick={handleCancel}
                  >
                    <Square size={12} />
                    {t("sup.cancel")}
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
                {running && (
                  <span className="text-[11px] text-[#dcdcaa] flex items-center gap-1">
                    <AlertCircle size={11} />
                    {t("diag.no_hard_cancel")}
                  </span>
                )}
              </div>
              {job && (
                <JobBanner
                  job={job}
                  labels={{
                    pending: t("sup.job_pending"),
                    running: t("sup.job_running"),
                    done: t("sup.job_done"),
                    error: t("sup.job_error"),
                    cancelled: t("sup.job_cancelled"),
                  }}
                />
              )}
            </section>
          </>
        )}

        {/* History + preview */}
        <section className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="vs-panel-title">{t("sup.history_title")}</h2>
            {datasetId && (
              <button
                className="vs-btn flex items-center gap-2"
                onClick={handleDownload}
              >
                <Download size={13} />
                {t("sup.download")}
              </button>
            )}
          </div>
          {supplements.length === 0 ? (
            <div className="vs-card p-4 text-[12px] text-[var(--vs-fg-muted)] italic">
              {t("sup.no_history")}
            </div>
          ) : (
            <div className="vs-card p-4">
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  className="vs-input flex-1 min-w-[280px]"
                  value={datasetId}
                  onChange={(e) => setDatasetId(e.target.value)}
                >
                  {supplements.map((s) => (
                    <option key={s.dataset_id} value={s.dataset_id}>
                      {s.created_at} · rows={s.row_count} · id={s.dataset_id}
                    </option>
                  ))}
                </select>
                <button
                  className="vs-btn-ghost p-2 text-[#f48771]"
                  onClick={() => handleDelete(datasetId)}
                  disabled={!datasetId}
                  title={t("sup.delete_btn")}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          )}

          {previewSummary && (
            <>
              <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                <DetailChip
                  label={t("sup.stat_qa")}
                  value={String(typeCounts?.qa ?? 0)}
                  color="var(--vs-accent)"
                />
                <DetailChip
                  label={t("sup.stat_choice")}
                  value={String(typeCounts?.choice ?? 0)}
                  color="#c586c0"
                />
                <DetailChip
                  label={t("sup.stat_tf")}
                  value={String(typeCounts?.tf ?? 0)}
                  color="#dcb67a"
                />
                <DetailChip
                  label={t("sup.stat_tasks_total")}
                  value={String(previewSummary.stats.tasks_total ?? 0)}
                />
                <DetailChip
                  label={t("sup.stat_tasks_failed")}
                  value={String(previewSummary.stats.tasks_failed ?? 0)}
                  color="#f48771"
                />
                <DetailChip
                  label={t("sup.stat_total_rows")}
                  value={String(totalInDataset)}
                  color="#4ec9b0"
                />
              </div>

              {preview.length > 0 && (
                <div className="vs-card overflow-hidden">
                  <div className="px-4 py-2 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] flex items-center gap-2 text-[12px] text-[var(--vs-fg-muted)]">
                    <span>
                      {t("sup.preview_head", {
                        shown: String(preview.length),
                        total: String(totalInDataset),
                      })}
                    </span>
                  </div>
                  <div className="max-h-[420px] overflow-auto">
                    <table className="w-full border-collapse text-[12px]">
                      <thead className="sticky top-0 bg-[var(--vs-panel)]">
                        <tr>
                          <th className="px-2 py-[6px] text-left text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] font-semibold w-[50px]">
                            #
                          </th>
                          <th className="px-2 py-[6px] text-left text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] font-semibold w-[130px]">
                            {t("sup.col_issue")}
                          </th>
                          <th className="px-2 py-[6px] text-left text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] font-semibold w-[130px]">
                            {t("sup.col_qtype")}
                          </th>
                          <th className="px-2 py-[6px] text-left text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] font-semibold">
                            {t("sup.col_question")}
                          </th>
                          <th className="px-2 py-[6px] text-left text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] font-semibold w-[120px]">
                            {t("sup.col_answer")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.map((r, i) => (
                          <tr
                            key={i}
                            className="border-b border-[var(--vs-panel)] hover:bg-[var(--vs-hover)]"
                          >
                            <td className="px-2 py-[4px] font-mono text-[var(--vs-fg-subtle)] align-top">
                              {i + 1}
                            </td>
                            <td className="px-2 py-[4px] font-mono align-top text-[11px] text-[#c586c0]">
                              {String(r.issue_type ?? "")}
                            </td>
                            <td className="px-2 py-[4px] font-mono align-top text-[11px] text-[var(--vs-fg-muted)]">
                              {String(r.question_type ?? "")}
                            </td>
                            <td className="px-2 py-[4px] align-top text-[var(--vs-fg)] leading-[1.45]">
                              {String(r.question ?? "")}
                            </td>
                            <td className="px-2 py-[4px] align-top text-[var(--vs-fg)] truncate max-w-[200px]">
                              {String(r.answer ?? "")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function DetailChip({
  label,
  value,
  color = "var(--vs-accent)",
}: {
  label: string;
  value: string;
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
      <div className="text-[10px] text-[var(--vs-fg-subtle)] font-mono mt-0.5">
        {min} – {max}
      </div>
    </div>
  );
}

function MiniNum({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="number"
      className="vs-input font-mono text-center"
      min={0}
      max={20}
      step={1}
      value={value}
      onChange={(e) => onChange(Math.max(0, parseInt(e.target.value) || 0))}
    />
  );
}
