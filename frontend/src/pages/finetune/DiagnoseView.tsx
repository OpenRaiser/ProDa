import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileJson,
  Loader2,
  Play,
  RefreshCw,
  Square,
  Trash2,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import Editor from "@monaco-editor/react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import {
  cancelDiagnosisJob,
  deleteReport,
  getDiagnosisJob,
  getEvalModels,
  getReport,
  listDiagnosisJobs,
  listOpenCompassRuns,
  listReports,
  startReport,
  uploadEvalJson,
} from "@/api/diagnosis";
import type {
  DiagnosisJob,
  DiagnosisReportDetail,
  DiagnosisReportSummary,
  EvalModel,
  OpenCompassRun,
} from "@/types";
import { JobBanner } from "@/components/common/JobBanner";

export function DiagnoseView() {
  const { t } = useI18n();
  const project = useSession((s) => s.currentProject);
  const profiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);

  const [runs, setRuns] = useState<OpenCompassRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [models, setModels] = useState<EvalModel[]>([]);
  const [targetModel, setTargetModel] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  // Params
  const [maxDiagnose, setMaxDiagnose] = useState(300);
  const [maxWorkers, setMaxWorkers] = useState(8);
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [retries, setRetries] = useState(3);

  const [job, setJob] = useState<DiagnosisJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [launchError, setLaunchError] = useState("");

  const [history, setHistory] = useState<DiagnosisReportSummary[]>([]);
  const [pickedReport, setPickedReport] = useState<string>("");
  const [reportDetail, setReportDetail] =
    useState<DiagnosisReportDetail | null>(null);
  const [reportSummary, setReportSummary] =
    useState<DiagnosisReportSummary | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const refreshRuns = useCallback(async () => {
    if (!project) return;
    try {
      const list = await listOpenCompassRuns(project.id);
      setRuns(list);
      setSelectedRun((prev) => prev || list[0]?.result_file || "");
    } catch {
      /* ignore */
    }
    // Intentionally exclude selectedRun: we use functional setState so this
    // callback stays stable across re-renders and doesn't re-fetch on every pick.
  }, [project]);

  const refreshHistory = useCallback(async () => {
    if (!project) return;
    try {
      const list = await listReports(project.id);
      setHistory(list);
      setPickedReport((prev) => prev || list[0]?.report_id || "");
    } catch {
      /* ignore */
    }
  }, [project]);

  useEffect(() => {
    refreshRuns();
    refreshHistory();
  }, [refreshRuns, refreshHistory]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  // Adopt a running "report" job on mount
  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    (async () => {
      try {
        const jobs = await listDiagnosisJobs(project.id);
        const running = jobs.find(
          (j) =>
            j.kind === "report" &&
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

  // Load models when selectedRun changes
  useEffect(() => {
    if (!project || !selectedRun) {
      setModels([]);
      setTargetModel("");
      return;
    }
    let cancel = false;
    (async () => {
      try {
        const ms = await getEvalModels(project.id, selectedRun);
        if (cancel) return;
        setModels(ms);
        setTargetModel(ms[0]?.abbr ?? "");
      } catch {
        if (!cancel) {
          setModels([]);
          setTargetModel("");
        }
      }
    })();
    return () => {
      cancel = true;
    };
  }, [project, selectedRun]);

  // Load report detail when pickedReport changes
  useEffect(() => {
    if (!project || !pickedReport) {
      setReportDetail(null);
      setReportSummary(null);
      return;
    }
    let cancel = false;
    setLoadingReport(true);
    (async () => {
      try {
        const { summary, report } = await getReport(project.id, pickedReport);
        if (cancel) return;
        setReportDetail(report);
        setReportSummary(summary);
      } catch {
        if (!cancel) {
          setReportDetail(null);
          setReportSummary(null);
        }
      } finally {
        if (!cancel) setLoadingReport(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [project, pickedReport]);

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
          await refreshHistory();
          if (j.result?.report_id) setPickedReport(j.result.report_id);
        }
      } catch {
        /* ignore */
      }
    }, 900);
  };

  const handleUpload = async (file: File) => {
    if (!project) return;
    setUploadError("");
    setUploading(true);
    try {
      const run = await uploadEvalJson(project.id, file);
      await refreshRuns();
      setSelectedRun(run.result_file);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setUploadError(err?.message ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleStart = async () => {
    if (!project) return;
    setLaunchError("");
    if (!selectedRun) {
      setLaunchError(t("diag.need_run"));
      return;
    }
    if (!targetModel) {
      setLaunchError(t("diag.need_target_model"));
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

    const run = runs.find((r) => r.result_file === selectedRun);
    setStarting(true);
    try {
      const jobId = await startReport(project.id, {
        result_file: selectedRun,
        target_model_abbr: targetModel,
        run_id: run?.run_id ?? "run",
        max_diagnose: maxDiagnose,
        max_workers: maxWorkers,
        temperature,
        max_tokens: maxTokens,
        retries,
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
        kind: "report",
        target_model: targetModel,
        run_id: run?.run_id,
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

  const handleDelete = async (reportId: string) => {
    if (!project) return;
    if (!window.confirm(t("diag.delete_confirm"))) return;
    try {
      await deleteReport(project.id, reportId);
      if (pickedReport === reportId) setPickedReport("");
      await refreshHistory();
    } catch {
      /* ignore */
    }
  };

  const handleDownload = () => {
    if (!reportDetail) return;
    const blob = new Blob([JSON.stringify(reportDetail, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${reportSummary?.report_id ?? "diagnostic_report"}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const running = job?.status === "pending" || job?.status === "running";

  const issueDist = useMemo(() => {
    const map =
      (reportDetail?.llm_diagnosis_issue_distribution as Record<
        string,
        number
      >) ?? {};
    const entries = Object.entries(map).map(([k, v]) => ({
      key: k,
      value: Number(v) || 0,
    }));
    entries.sort((a, b) => b.value - a.value);
    return entries;
  }, [reportDetail]);

  const subjectDist = useMemo(() => {
    const bySubject =
      (reportDetail?.error_patterns?.by_subject as
        | Record<string, number>
        | undefined) ?? {};
    return Object.entries(bySubject)
      .map(([subject, count]) => ({ subject, count: Number(count) || 0 }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 20);
  }, [reportDetail]);

  const issueMax = Math.max(1, ...issueDist.map((e) => e.value));
  const subjectMax = Math.max(1, ...subjectDist.map((e) => e.count));

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1280px] mx-auto px-10 py-6 space-y-6">
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">{t("diag.title")}</h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("diag.desc")}</p>
        </div>

        {/* Run / Upload row */}
        <section>
          <h2 className="vs-panel-title mb-3">{t("diag.run_picker_title")}</h2>
          <div className="vs-card p-4 space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex-1 min-w-[280px]">
                <label className="vs-label">{t("diag.pick_run")}</label>
                <select
                  className="vs-input w-full"
                  value={selectedRun}
                  onChange={(e) => setSelectedRun(e.target.value)}
                >
                  <option value="">{t("diag.no_runs")}</option>
                  {runs.map((r) => (
                    <option key={r.result_file} value={r.result_file}>
                      [{r.source}] {r.run_id} · {r.created_at}{" "}
                      {r.success ? "" : "· failed"}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={refreshRuns}
                className="vs-btn-ghost self-end h-[32px] flex items-center gap-1"
                title={t("common.refresh")}
              >
                <RefreshCw size={13} />
              </button>
              <div className="self-end flex flex-col gap-1">
                <label className="vs-label mb-0">
                  {t("diag.upload_title")}
                </label>
                <button
                  className="vs-btn-secondary flex items-center gap-2 h-[32px]"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Upload size={13} />
                  )}
                  {t("diag.upload_btn")}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleUpload(f);
                    e.target.value = "";
                  }}
                />
              </div>
            </div>
            {uploadError && (
              <div className="text-[12px] text-[#f48771] flex items-center gap-1">
                <AlertCircle size={12} />
                {uploadError}
              </div>
            )}
            {selectedRun && (
              <div>
                <label className="vs-label">{t("diag.pick_target")}</label>
                {models.length === 0 ? (
                  <div className="text-[12px] text-[#dcdcaa]">
                    {t("diag.no_local_model")}
                  </div>
                ) : (
                  <select
                    className="vs-input w-full max-w-[400px]"
                    value={targetModel}
                    onChange={(e) => setTargetModel(e.target.value)}
                  >
                    {models.map((m) => (
                      <option key={m.abbr} value={m.abbr}>
                        {m.abbr}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Params */}
        {selectedRun && targetModel && (
          <section>
            <h2 className="vs-panel-title mb-3">{t("diag.config_title")}</h2>
            <div className="vs-card p-4">
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                <NumField
                  label={t("diag.max_diagnose")}
                  value={maxDiagnose}
                  min={0}
                  max={200000}
                  step={10}
                  onChange={setMaxDiagnose}
                />
                <NumField
                  label={t("diag.max_workers")}
                  value={maxWorkers}
                  min={1}
                  max={64}
                  step={1}
                  onChange={setMaxWorkers}
                />
                <NumField
                  label={t("diag.temperature")}
                  value={temperature}
                  min={0}
                  max={1.5}
                  step={0.1}
                  precision={2}
                  onChange={setTemperature}
                />
                <NumField
                  label={t("diag.max_tokens")}
                  value={maxTokens}
                  min={64}
                  max={16384}
                  step={64}
                  onChange={setMaxTokens}
                />
                <NumField
                  label={t("diag.retries")}
                  value={retries}
                  min={0}
                  max={10}
                  step={1}
                  onChange={setRetries}
                />
              </div>
            </div>
          </section>
        )}

        {/* Start / Cancel / Job banner */}
        {selectedRun && targetModel && (
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
                {t("diag.start")}
              </button>
              {running && (
                <button
                  className="vs-btn-secondary flex items-center gap-2"
                  onClick={handleCancel}
                  title={t("diag.cancel_warn")}
                >
                  <Square size={12} />
                  {t("diag.cancel")}
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
                  pending: t("diag.job_pending"),
                  running: t("diag.job_running"),
                  done: t("diag.job_done"),
                  error: t("diag.job_error"),
                  cancelled: t("diag.job_cancelled"),
                }}
              />
            )}
          </section>
        )}

        {/* History */}
        <section className="space-y-3">
          <h2 className="vs-panel-title">{t("diag.history_title")}</h2>
          {history.length === 0 ? (
            <div className="vs-card p-4 text-[12px] text-[var(--vs-fg-muted)] italic">
              {t("diag.no_history")}
            </div>
          ) : (
            <div className="vs-card p-4">
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  className="vs-input flex-1 min-w-[280px]"
                  value={pickedReport}
                  onChange={(e) => setPickedReport(e.target.value)}
                >
                  {history.map((h) => (
                    <option key={h.report_id} value={h.report_id}>
                      {h.created_at} · {h.model_name} · acc=
                      {(h.accuracy * 100).toFixed(1)}% · errs=
                      {h.error_samples_count}
                    </option>
                  ))}
                </select>
                <button
                  className="vs-btn-ghost p-2 text-[#f48771]"
                  onClick={() => handleDelete(pickedReport)}
                  disabled={!pickedReport}
                  title={t("diag.delete_btn")}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Report detail */}
        {pickedReport && (
          <section className="space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="vs-panel-title">{t("diag.detail_title")}</h2>
              {reportDetail && (
                <button
                  className="vs-btn flex items-center gap-2"
                  onClick={handleDownload}
                >
                  <Download size={13} />
                  {t("diag.download")}
                </button>
              )}
            </div>

            {loadingReport && (
              <div className="vs-card p-4 text-[12px] text-[var(--vs-fg-muted)] flex items-center gap-2">
                <Loader2 size={13} className="animate-spin" />
                {t("common.loading")}
              </div>
            )}

            {!loadingReport && reportDetail && reportSummary && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <DetailChip
                    label={t("diag.metric_acc")}
                    value={`${((reportDetail.accuracy ?? 0) * 100).toFixed(
                      2
                    )}%`}
                    color="#4ec9b0"
                  />
                  <DetailChip
                    label={t("diag.metric_total")}
                    value={String(reportDetail.total_samples ?? 0)}
                  />
                  <DetailChip
                    label={t("diag.metric_error")}
                    value={String(reportDetail.error_samples_count ?? 0)}
                    color="#f48771"
                  />
                  <DetailChip
                    label={t("diag.metric_model")}
                    value={String(reportDetail.model_name ?? "-")}
                    color="#c586c0"
                  />
                </div>

                {issueDist.length > 0 && (
                  <div className="vs-card p-4">
                    <div className="vs-panel-title mb-3">
                      {t("diag.issue_dist_title")}
                    </div>
                    <div className="space-y-1">
                      {issueDist.map((e) => (
                        <BarRow
                          key={e.key}
                          label={e.key}
                          value={e.value}
                          max={issueMax}
                          color="var(--vs-accent)"
                        />
                      ))}
                    </div>
                  </div>
                )}

                {subjectDist.length > 0 && (
                  <div className="vs-card p-4">
                    <div className="vs-panel-title mb-3">
                      {t("diag.subject_dist_title")}
                    </div>
                    <div className="space-y-1">
                      {subjectDist.map((e) => (
                        <BarRow
                          key={e.subject}
                          label={e.subject}
                          value={e.count}
                          max={subjectMax}
                          color="#dcb67a"
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Monaco JSON viewer */}
                <div className="vs-card overflow-hidden">
                  <div className="px-4 py-2 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] flex items-center gap-2">
                    <FileJson size={13} className="text-[#cbcb41]" />
                    <span className="text-[12px] text-[var(--vs-fg)] font-mono">
                      {reportSummary.report_id}.json
                    </span>
                    <span className="ml-auto text-[11px] text-[var(--vs-fg-subtle)]">
                      {t("diag.json_readonly")}
                    </span>
                  </div>
                  <div style={{ height: 420 }}>
                    <Editor
                      value={JSON.stringify(reportDetail, null, 2)}
                      language="json"
                      theme="vs-dark"
                      options={{
                        readOnly: true,
                        minimap: { enabled: false },
                        fontSize: 12,
                        folding: true,
                        lineNumbers: "on",
                        scrollBeyondLastLine: false,
                        wordWrap: "on",
                      }}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-2 text-[11px] text-[#4ec9b0]">
                  <CheckCircle2 size={12} />
                  <span>
                    {t("diag.go_supplement_hint", {
                      id: reportSummary.report_id,
                    })}
                  </span>
                </div>
              </>
            )}
          </section>
        )}
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

function BarRow({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="flex items-center gap-2">
      <div
        className="text-[11px] text-[var(--vs-fg)] truncate font-mono"
        style={{ width: 180 }}
        title={label}
      >
        {label}
      </div>
      <div className="flex-1 h-[14px] bg-[var(--vs-panel)] rounded-sm overflow-hidden relative">
        <div
          className="h-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color, opacity: 0.75 }}
        />
      </div>
      <div
        className="text-[11px] text-[var(--vs-fg)] font-mono text-right"
        style={{ width: 60 }}
      >
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
      <label className="vs-label">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="number"
          className={clsx("vs-input font-mono")}
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number.parseFloat(e.target.value) || 0)}
        />
      </div>
      <div className="text-[10px] text-[var(--vs-fg-subtle)] font-mono mt-0.5">
        {min} – {max}
        {precision > 0 ? ` · ${value.toFixed(precision)}` : ""}
      </div>
    </div>
  );
}
