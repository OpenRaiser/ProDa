import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  FileCode2,
  FileText,
  FolderOpen,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  ScrollText,
  Search,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import Editor from "@monaco-editor/react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { usePageLabels } from "@/hooks/usePageLabels";
import {
  cancelEval,
  getFlowSuggestion,
  listBenchmarks,
  listEvalHistory,
  listPeftCandidates,
  ocEnvCheck,
  ocEnvSettingsPut,
  previewConfig,
  startEval,
  uploadBenchmark,
} from "@/api/opencompass";
import type {
  EvalBenchmark,
  EvalConfig,
  EvalEnvCheck,
  EvalModel,
  EvalSession,
  FlowSuggestion,
  PeftCandidate,
} from "@/types";
import { LeaderboardView } from "@/pages/opencompass/LeaderboardView";
import { ComparisonView } from "@/pages/opencompass/ComparisonView";
import { SamplesView } from "@/pages/opencompass/SamplesView";

type ResultTab = "leaderboard" | "comparison" | "samples";

function blankLocalModel(abbr = "local-m1"): EvalModel {
  return {
    enabled: true,
    is_local: true,
    abbr,
    path: "",
    peft_path: "",
    api_key: "",
    api_base: "",
    temperature: 0.0,
    max_out_len: 15,
    query_per_second: 4,
    num_procs: 4,
    batch_size: 1,
    num_gpus: 1,
  };
}

function blankApiModel(abbr = "api-m1"): EvalModel {
  return {
    ...blankLocalModel(abbr),
    is_local: false,
    max_out_len: 50,
    num_gpus: 0,
  };
}

export function OpenCompass() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const project = useSession((s) => s.currentProject);
  const openTab = useSession((s) => s.openTab);
  const active = useSession((s) => s.activeEvalSession);

  const [env, setEnv] = useState<EvalEnvCheck | null>(null);
  const [envLoading, setEnvLoading] = useState(false);
  const [envEdit, setEnvEdit] = useState({ opencompass_path: "" });
  const [envExpanded, setEnvExpanded] = useState(false);
  const [envSaving, setEnvSaving] = useState(false);

  const [benchmarks, setBenchmarks] = useState<EvalBenchmark[]>([]);
  const [models, setModels] = useState<EvalModel[]>([blankLocalModel()]);
  const [maxSamples, setMaxSamples] = useState<number | "">("");
  const [datasetAbbr, setDatasetAbbr] = useState("proda_bench");
  const [workDir, setWorkDir] = useState("");
  const [benchmarkSource, setBenchmarkSource] = useState<"state" | "upload">("state");
  const [benchmarkPath, setBenchmarkPath] = useState("");

  const [previewYaml, setPreviewYaml] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState("");

  const [launching, setLaunching] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [launchError, setLaunchError] = useState("");

  const [peftCards, setPeftCards] = useState<PeftCandidate[]>([]);
  const [peftOpen, setPeftOpen] = useState(false);
  const [flowSuggestion, setFlowSuggestion] = useState<FlowSuggestion | null>(
    null
  );

  const [history, setHistory] = useState<EvalSession[]>([]);
  const [pickedRun, setPickedRun] = useState<string>("");
  const [resultTab, setResultTab] = useState<ResultTab>("leaderboard");
  const preselectedRun = useSession((s) => s.preselectedEvalRunId);
  const setPreselectedRun = useSession((s) => s.setPreselectedEvalRunId);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const cfg: EvalConfig = {
    benchmark_source: benchmarkSource,
    benchmark_path: benchmarkPath,
    models,
    max_samples: maxSamples === "" ? null : Number(maxSamples),
    dataset_abbr: datasetAbbr,
    work_dir: workDir,
  };

  // ----- Refreshers -----

  const refreshEnv = useCallback(async () => {
    setEnvLoading(true);
    try {
      const e = await ocEnvCheck();
      setEnv(e);
      setEnvEdit((prev) => ({
        opencompass_path: prev.opencompass_path || e.opencompass_path,
      }));
    } catch {
      /* ignore */
    } finally {
      setEnvLoading(false);
    }
  }, []);

  const refreshBenchmarks = useCallback(async () => {
    if (!project) return;
    try {
      const list = await listBenchmarks(project.id);
      setBenchmarks(list);
      if (list.length && benchmarkSource === "upload" && !benchmarkPath) {
        const upload = list.find((b) => b.source === "upload");
        if (upload) setBenchmarkPath(upload.path);
      }
    } catch {
      /* ignore */
    }
  }, [project, benchmarkSource, benchmarkPath]);

  const refreshHistory = useCallback(async () => {
    if (!project) return;
    try {
      const hist = await listEvalHistory(project.id);
      setHistory(hist);
      if (hist.length && !pickedRun) setPickedRun(hist[0].run_id);
    } catch {
      /* ignore */
    }
  }, [project, pickedRun]);

  const refreshFlow = useCallback(async () => {
    if (!project) return;
    try {
      const s = await getFlowSuggestion(project.id);
      setFlowSuggestion(s);
    } catch {
      /* ignore */
    }
  }, [project]);

  useEffect(() => {
    refreshEnv();
  }, [refreshEnv]);
  useEffect(() => {
    refreshBenchmarks();
    refreshHistory();
    refreshFlow();
  }, [refreshBenchmarks, refreshHistory, refreshFlow]);

  // Consume preselect (from Phase 7 timeline click) once, then clear it.
  useEffect(() => {
    if (preselectedRun) {
      setPickedRun(preselectedRun);
      setPreselectedRun(null);
    }
  }, [preselectedRun, setPreselectedRun]);

  // Auto-refresh history when active session flips
  useEffect(() => {
    refreshHistory();
  }, [active?.run_id, active?.alive, refreshHistory]);

  // Debounced preview — skip if models are incomplete
  useEffect(() => {
    if (!project) return;
    const anyComplete = models.some(
      (m) => m.enabled && m.abbr && (m.is_local ? m.path : m.path && m.api_key)
    );
    if (!anyComplete) {
      setPreviewYaml("");
      setPreviewError("");
      return;
    }
    setPreviewing(true);
    const timer = setTimeout(async () => {
      try {
        const res = await previewConfig(project.id, cfg);
        setPreviewYaml(res.yaml);
        setPreviewError("");
      } catch (e: unknown) {
        const err = e as {
          message?: string;
          response?: { data?: { detail?: unknown } };
        };
        const detail = err?.response?.data?.detail;
        let msg: string;
        if (Array.isArray(detail)) msg = JSON.stringify(detail);
        else if (typeof detail === "string") msg = detail;
        else if (detail && typeof detail === "object") msg = JSON.stringify(detail);
        else msg = err?.message ?? "Preview failed";
        setPreviewYaml("");
        setPreviewError(msg);
      } finally {
        setPreviewing(false);
      }
    }, 450);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    project,
    benchmarkSource,
    benchmarkPath,
    JSON.stringify(models),
    maxSamples,
    datasetAbbr,
    workDir,
  ]);

  // ----- Handlers -----

  const handleEnvSave = async () => {
    setEnvSaving(true);
    try {
      await ocEnvSettingsPut({ opencompass_path: envEdit.opencompass_path });
      await refreshEnv();
    } finally {
      setEnvSaving(false);
    }
  };

  const handleUploadBenchmark = async (file: File) => {
    if (!project) return;
    try {
      const up = await uploadBenchmark(project.id, file);
      await refreshBenchmarks();
      setBenchmarkSource("upload");
      setBenchmarkPath(up.path);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLaunchError(err?.message ?? "Upload failed");
    }
  };

  const handleScanPeft = async () => {
    if (!project) return;
    setPeftOpen(true);
    try {
      const list = await listPeftCandidates(project.id);
      setPeftCards(list);
    } catch {
      /* ignore */
    }
  };

  const handleAddFromPeft = (p: PeftCandidate) => {
    setModels((prev) => [
      ...prev,
      {
        ...blankLocalModel(
          `${p.name}_trained`.replace(/[^A-Za-z0-9_-]+/g, "_")
        ),
        path: p.base_model || p.adapter_path,
        peft_path: p.base_model ? p.adapter_path : "",
      },
    ]);
    setPeftOpen(false);
  };

  const handleApplyFlowSuggestion = () => {
    if (!flowSuggestion) return;
    setModels((prev) => [
      ...prev,
      {
        ...blankLocalModel(
          (flowSuggestion.abbr || "latest_trained").replace(
            /[^A-Za-z0-9_-]+/g,
            "_"
          )
        ),
        path: flowSuggestion.path,
        peft_path: flowSuggestion.peft_path,
      },
    ]);
  };

  const handleLaunch = async () => {
    if (!project) return;
    setLaunchError("");
    setLaunching(true);
    try {
      await startEval(project.id, cfg);
      await refreshHistory();
    } catch (e: unknown) {
      const err = e as {
        message?: string;
        response?: { data?: { detail?: unknown } };
      };
      const detail = err?.response?.data?.detail;
      let msg: string;
      if (Array.isArray(detail)) msg = JSON.stringify(detail);
      else if (typeof detail === "string") msg = detail;
      else if (detail && typeof detail === "object") msg = JSON.stringify(detail);
      else msg = err?.message ?? "Launch failed";
      setLaunchError(msg);
    } finally {
      setLaunching(false);
    }
  };

  const handleCancel = async () => {
    if (!project) return;
    setCanceling(true);
    try {
      await cancelEval(project.id);
    } catch {
      /* ignore */
    } finally {
      setCanceling(false);
    }
  };

  const running = active?.alive === true;
  const envOk = !!env?.opencompass_path_ok;
  const anyEnabled = models.some((m) => m.enabled);
  const canLaunch = !!project && envOk && anyEnabled && !running && !launching;

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1280px] mx-auto px-10 py-6 space-y-6">
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">{t("oc.title")}</h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("oc.desc")}</p>
        </div>

        {/* Env banner */}
        <section>
          <div
            className={clsx(
              "vs-card p-4",
              !envOk && "border-[#dcdcaa]/50 bg-[#dcdcaa]/5"
            )}
          >
            <div className="flex items-start gap-3 flex-wrap">
              {envOk ? (
                <CheckCircle2
                  size={18}
                  className="text-[#4ec9b0] shrink-0 mt-0.5"
                />
              ) : (
                <Settings2
                  size={18}
                  className="text-[#dcdcaa] shrink-0 mt-0.5"
                />
              )}
              <div className="flex-1 min-w-[240px] space-y-1">
                <div className="text-[13px] text-[var(--vs-fg-strong)]">
                  {envOk ? t("oc.env_ok") : t("oc.env_setup_required")}
                </div>
                {env && (
                  <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono space-y-0.5">
                    <div>
                      OpenCompass: {env.opencompass_path_ok ? "✓" : "✗"}{" "}
                      <span className="text-[var(--vs-fg-subtle)]">
                        {env.opencompass_path}
                      </span>
                    </div>
                    <div>
                      GPU: {env.gpu_count} ·{" "}
                      {env.gpus
                        .map((g) => `${g.name} (${g.memory_mb}MB)`)
                        .join(", ") || "—"}
                    </div>
                    <div>
                      CUDA: {env.cuda_home || "—"} · torch{" "}
                      {env.torch_version || "—"} · Python {env.python}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 self-start">
                <button
                  className="vs-btn-ghost px-2 h-[26px] flex items-center gap-1 text-[12px]"
                  onClick={refreshEnv}
                  disabled={envLoading}
                >
                  {envLoading ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <RefreshCw size={12} />
                  )}
                  {t("common.refresh")}
                </button>
                <button
                  className="vs-btn-ghost px-2 h-[26px] flex items-center gap-1 text-[12px]"
                  onClick={() => setEnvExpanded((v) => !v)}
                >
                  <Settings2 size={12} />
                  {t("oc.configure_path")}
                </button>
              </div>
            </div>
            {envExpanded && (
              <div className="mt-3 border-t border-[var(--vs-border)] pt-3 space-y-2">
                <div>
                  <label className="vs-label">OpenCompass path</label>
                  <input
                    className="vs-input font-mono"
                    value={envEdit.opencompass_path}
                    onChange={(e) =>
                      setEnvEdit({ opencompass_path: e.target.value })
                    }
                  />
                </div>
                <button
                  className="vs-btn flex items-center gap-2"
                  onClick={handleEnvSave}
                  disabled={envSaving}
                >
                  {envSaving && <Loader2 size={13} className="animate-spin" />}
                  {t("oc.save_path")}
                </button>
              </div>
            )}
          </div>
        </section>

        {/* Active banner */}
        {active && (
          <div
            className={clsx(
              "vs-card p-3 flex items-center gap-3 flex-wrap",
              running
                ? "border-[color:var(--vs-accent)]/50 bg-[color:var(--vs-accent)]/5"
                : "border-[color:var(--vs-fg-subtle)]/50 bg-[color:var(--vs-fg-subtle)]/5"
            )}
          >
            {running ? (
              <Loader2
                size={14}
                className="text-[var(--vs-accent)] animate-spin shrink-0"
              />
            ) : (
              <CheckCircle2 size={14} className="text-[#4ec9b0] shrink-0" />
            )}
            <div className="flex-1 min-w-[200px] text-[12px]">
              <div className="text-[var(--vs-fg-strong)]">
                {running ? t("oc.session_running") : t("oc.session_finished")}{" "}
                <span className="text-[var(--vs-fg-muted)] font-mono">
                  pid={active.pid} · run {active.run_id}
                </span>
              </div>
              <div className="text-[11px] text-[var(--vs-fg-subtle)] font-mono truncate">
                {active.work_dir}
              </div>
            </div>
            {running && (
              <button
                className="vs-btn-secondary flex items-center gap-2"
                onClick={handleCancel}
                disabled={canceling}
              >
                {canceling ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Square size={12} />
                )}
                {t("oc.cancel")}
              </button>
            )}
          </div>
        )}

        {/* Benchmark */}
        <section>
          <h2 className="vs-panel-title mb-3">{t("oc.benchmark_title")}</h2>
          <div className="vs-card p-4 space-y-3">
            <div className="flex items-center gap-4 flex-wrap">
              <label className="flex items-center gap-2 text-[13px]">
                <input
                  type="radio"
                  className="accent-[var(--vs-accent)]"
                  checked={benchmarkSource === "state"}
                  onChange={() => setBenchmarkSource("state")}
                />
                {t("oc.from_state")}
              </label>
              <label className="flex items-center gap-2 text-[13px]">
                <input
                  type="radio"
                  className="accent-[var(--vs-accent)]"
                  checked={benchmarkSource === "upload"}
                  onChange={() => setBenchmarkSource("upload")}
                />
                {t("oc.from_upload")}
              </label>
              <button
                className="vs-btn-ghost px-2 h-[28px] flex items-center gap-1 text-[12px] ml-auto"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={12} />
                {t("oc.upload_json")}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleUploadBenchmark(f);
                  e.target.value = "";
                }}
              />
            </div>
            {benchmarkSource === "state" ? (
              <div className="text-[12px] text-[var(--vs-fg-muted)] font-mono">
                {benchmarks.find((b) => b.source === "state") ? (
                  <>
                    <Database
                      size={11}
                      className="inline text-[#4ec9b0] mr-1"
                    />
                    state.benchmark_mcq ·{" "}
                    {
                      benchmarks.find((b) => b.source === "state")?.row_count
                    }{" "}
                    {t("oc.rows")}
                  </>
                ) : (
                  <span className="text-[#dcdcaa]">
                    {t("oc.no_state_benchmark")}
                  </span>
                )}
              </div>
            ) : (
              <select
                className="vs-input"
                value={benchmarkPath}
                onChange={(e) => setBenchmarkPath(e.target.value)}
              >
                <option value="">{t("oc.pick_upload")}</option>
                {benchmarks
                  .filter((b) => b.source === "upload")
                  .map((b) => (
                    <option key={b.path} value={b.path}>
                      {b.name} · {b.row_count} {t("oc.rows")}
                    </option>
                  ))}
              </select>
            )}
          </div>
        </section>

        {/* Models table */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="vs-panel-title">{t("oc.models_title")}</h2>
            <div className="flex gap-1">
              <button
                className="vs-btn-ghost px-2 h-[24px] flex items-center gap-1 text-[12px]"
                onClick={handleScanPeft}
              >
                <Search size={11} />
                {t("oc.scan_peft")}
              </button>
              <button
                className="vs-btn-ghost px-2 h-[24px] flex items-center gap-1 text-[12px]"
                onClick={() =>
                  setModels((prev) => [
                    ...prev,
                    blankLocalModel(`local-m${prev.length + 1}`),
                  ])
                }
              >
                <Plus size={11} />
                {t("oc.add_local")}
              </button>
              <button
                className="vs-btn-ghost px-2 h-[24px] flex items-center gap-1 text-[12px]"
                onClick={() =>
                  setModels((prev) => [
                    ...prev,
                    blankApiModel(`api-m${prev.length + 1}`),
                  ])
                }
              >
                <Plus size={11} />
                {t("oc.add_api")}
              </button>
            </div>
          </div>
          {flowSuggestion && (
            <div className="mb-3 vs-card p-3 border-[color:var(--vs-accent)]/50 bg-[color:var(--vs-accent)]/5 flex items-start gap-3">
              <Sparkles
                size={14}
                className="text-[var(--vs-accent)] shrink-0 mt-0.5"
              />
              <div className="flex-1 min-w-[200px]">
                <div className="text-[12px] text-[var(--vs-fg-strong)]">
                  {t("oc.flow_suggest_title")}
                </div>
                <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono mt-0.5">
                  {flowSuggestion.kind === "lora" ? (
                    <>
                      base: {flowSuggestion.path} · lora:{" "}
                      {flowSuggestion.peft_path}
                    </>
                  ) : (
                    <>path: {flowSuggestion.path}</>
                  )}
                </div>
              </div>
              <button
                className="vs-btn-secondary flex items-center gap-2 text-[12px]"
                onClick={handleApplyFlowSuggestion}
              >
                <Plus size={12} />
                {t("oc.flow_suggest_apply")}
              </button>
            </div>
          )}
          <div className="vs-card overflow-hidden">
            <table className="w-full text-[12px] border-collapse">
              <thead className="bg-[var(--vs-sidebar)] text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)]">
                <tr>
                  <th className="px-2 py-1 text-left w-[42px]">on</th>
                  <th className="px-2 py-1 text-left w-[90px]">type</th>
                  <th className="px-2 py-1 text-left w-[170px]">abbr</th>
                  <th className="px-2 py-1 text-left">path / model id</th>
                  <th className="px-2 py-1 text-left">peft_path / api_base</th>
                  <th className="px-2 py-1 text-left w-[100px]">api_key</th>
                  <th className="px-2 py-1 text-left w-[48px]">bs</th>
                  <th className="px-2 py-1 text-left w-[48px]">gpu</th>
                  <th className="px-2 py-1 text-center w-[36px]"></th>
                </tr>
              </thead>
              <tbody>
                {models.map((m, i) => (
                  <tr
                    key={i}
                    className="border-t border-[var(--vs-panel)] hover:bg-[var(--vs-hover)] group"
                  >
                    <td className="px-2 py-1">
                      <input
                        type="checkbox"
                        checked={m.enabled}
                        className="accent-[var(--vs-accent)]"
                        onChange={(e) => {
                          const next = [...models];
                          next[i] = { ...m, enabled: e.target.checked };
                          setModels(next);
                        }}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <select
                        className="vs-input h-[24px] py-0 text-[12px]"
                        value={m.is_local ? "local" : "api"}
                        onChange={(e) => {
                          const is_local = e.target.value === "local";
                          const next = [...models];
                          next[i] = {
                            ...m,
                            is_local,
                            num_gpus: is_local ? Math.max(1, m.num_gpus) : 0,
                            max_out_len: is_local ? 15 : 50,
                          };
                          setModels(next);
                        }}
                      >
                        <option value="local">local</option>
                        <option value="api">api</option>
                      </select>
                    </td>
                    <td className="px-2 py-1">
                      <input
                        className="vs-input h-[24px] py-0 font-mono text-[12px]"
                        value={m.abbr}
                        onChange={(e) => {
                          const next = [...models];
                          next[i] = { ...m, abbr: e.target.value };
                          setModels(next);
                        }}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        className="vs-input h-[24px] py-0 font-mono text-[12px]"
                        value={m.path}
                        placeholder={
                          m.is_local ? "/path/to/base-model" : "gpt-4o-mini"
                        }
                        onChange={(e) => {
                          const next = [...models];
                          next[i] = { ...m, path: e.target.value };
                          setModels(next);
                        }}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        className="vs-input h-[24px] py-0 font-mono text-[12px]"
                        value={m.is_local ? m.peft_path : m.api_base}
                        placeholder={
                          m.is_local
                            ? "(optional) /path/to/lora"
                            : "(optional) https://api.xxx.com"
                        }
                        onChange={(e) => {
                          const next = [...models];
                          next[i] = m.is_local
                            ? { ...m, peft_path: e.target.value }
                            : { ...m, api_base: e.target.value };
                          setModels(next);
                        }}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        className="vs-input h-[24px] py-0 font-mono text-[12px]"
                        type={m.is_local ? "text" : "password"}
                        disabled={m.is_local}
                        value={m.is_local ? "" : m.api_key}
                        placeholder={m.is_local ? "—" : "sk-..."}
                        onChange={(e) => {
                          const next = [...models];
                          next[i] = { ...m, api_key: e.target.value };
                          setModels(next);
                        }}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="number"
                        min={1}
                        max={128}
                        className="vs-input h-[24px] py-0 font-mono text-[12px]"
                        value={m.batch_size}
                        onChange={(e) => {
                          const next = [...models];
                          next[i] = {
                            ...m,
                            batch_size: Math.max(
                              1,
                              parseInt(e.target.value) || 1
                            ),
                          };
                          setModels(next);
                        }}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="number"
                        min={0}
                        max={16}
                        disabled={!m.is_local}
                        className="vs-input h-[24px] py-0 font-mono text-[12px]"
                        value={m.num_gpus}
                        onChange={(e) => {
                          const next = [...models];
                          next[i] = {
                            ...m,
                            num_gpus: Math.max(
                              0,
                              parseInt(e.target.value) || 0
                            ),
                          };
                          setModels(next);
                        }}
                      />
                    </td>
                    <td className="px-2 py-1 text-center">
                      <button
                        className="p-1 text-[var(--vs-fg-muted)] hover:text-[#f48771] opacity-0 group-hover:opacity-100"
                        onClick={() =>
                          setModels((prev) => prev.filter((_, k) => k !== i))
                        }
                        title={t("oc.remove_model")}
                      >
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {peftOpen && (
            <PeftPickerCard
              items={peftCards}
              onPick={handleAddFromPeft}
              onClose={() => setPeftOpen(false)}
            />
          )}
        </section>

        {/* Eval params */}
        <section>
          <h2 className="vs-panel-title mb-3">{t("oc.eval_params_title")}</h2>
          <div className="vs-card p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="vs-label">{t("oc.max_samples")}</label>
              <input
                type="number"
                className="vs-input font-mono"
                min={1}
                placeholder={t("oc.max_samples_ph")}
                value={maxSamples}
                onChange={(e) => {
                  const v = e.target.value;
                  setMaxSamples(v === "" ? "" : Math.max(1, parseInt(v) || 1));
                }}
              />
            </div>
            <div>
              <label className="vs-label">{t("oc.dataset_abbr")}</label>
              <input
                className="vs-input font-mono"
                value={datasetAbbr}
                onChange={(e) => setDatasetAbbr(e.target.value)}
              />
            </div>
            <div>
              <label className="vs-label">{t("oc.work_dir")}</label>
              <input
                className="vs-input font-mono"
                placeholder={t("oc.work_dir_ph")}
                value={workDir}
                onChange={(e) => setWorkDir(e.target.value)}
              />
            </div>
          </div>
        </section>

        {/* Config preview */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="vs-panel-title">{t("oc.config_preview_title")}</h2>
            <div className="flex items-center gap-2 text-[11px] text-[var(--vs-fg-muted)]">
              {previewing && <Loader2 size={11} className="animate-spin" />}
              {previewError && (
                <span className="text-[#f48771]">{previewError}</span>
              )}
            </div>
          </div>
          <div className="vs-card overflow-hidden">
            <div className="px-4 py-2 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] flex items-center gap-2 text-[12px]">
              <FileText size={13} className="text-[#cbcb41]" />
              <span className="text-[var(--vs-fg)] font-mono">
                eval_config.py
              </span>
              <span className="ml-auto text-[11px] text-[var(--vs-fg-subtle)]">
                {t("oc.config_readonly")}
              </span>
            </div>
            <div style={{ height: 280 }}>
              <Editor
                value={previewYaml}
                language="python"
                theme="vs-dark"
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 12,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                }}
              />
            </div>
          </div>
        </section>

        {/* Launch */}
        <section className="space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <button
              className="vs-btn flex items-center gap-2"
              onClick={handleLaunch}
              disabled={!canLaunch}
            >
              {launching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              {t("oc.launch")}
            </button>
            {running && (
              <button
                className="vs-btn-secondary flex items-center gap-2"
                onClick={handleCancel}
                disabled={canceling}
              >
                {canceling ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Square size={12} />
                )}
                {t("oc.cancel")}
              </button>
            )}
            {launchError && (
              <span className="text-[12px] text-[#f48771] flex items-center gap-1">
                <AlertCircle size={12} />
                {launchError}
              </span>
            )}
          </div>
        </section>

        {/* Results */}
        {history.length > 0 && (
          <section>
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <h2 className="vs-panel-title">{t("oc.results_title")}</h2>
              <div className="flex items-center gap-2">
                <select
                  className="vs-input w-[360px]"
                  value={pickedRun}
                  onChange={(e) => setPickedRun(e.target.value)}
                >
                  {history.map((h) => (
                    <option key={h.run_id} value={h.run_id}>
                      {h.run_id} · {h.status ?? "?"} ·{" "}
                      {(h.models || [])
                        .map((m) =>
                          typeof m === "string" ? m : m?.abbr ?? ""
                        )
                        .filter(Boolean)
                        .join(", ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="vs-card overflow-hidden">
              <div className="h-[30px] flex items-center gap-0 px-2 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)]">
                {(["leaderboard", "comparison", "samples"] as ResultTab[]).map(
                  (tab) => (
                    <button
                      key={tab}
                      onClick={() => setResultTab(tab)}
                      className={clsx(
                        "px-3 h-full text-[11px] uppercase tracking-wider border-b-2",
                        resultTab === tab
                          ? "border-[var(--vs-accent)] text-[var(--vs-fg-strong)]"
                          : "border-transparent text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg)]"
                      )}
                    >
                      {t(`oc.tab_${tab}`)}
                    </button>
                  )
                )}
              </div>
              {pickedRun && (
                <div className="p-3">
                  {resultTab === "leaderboard" && (
                    <LeaderboardView projectId={project?.id} runId={pickedRun} />
                  )}
                  {resultTab === "comparison" && (
                    <ComparisonView projectId={project?.id} runId={pickedRun} />
                  )}
                  {resultTab === "samples" && (
                    <SamplesView projectId={project?.id} runId={pickedRun} />
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {/* Next action */}
        {history.some((h) => h.status === "finished") && (
          <section>
            <h2 className="vs-panel-title mb-3">{t("dp.next_actions")}</h2>
            <button
              className="vs-card p-4 flex items-center justify-between w-full hover:border-[var(--vs-accent)] text-left"
              onClick={() => openTab(buildTab("finetune"))}
            >
              <div>
                <div className="text-[14px] text-[var(--vs-fg-strong)]">
                  {t("oc.go_diagnose")}
                </div>
                <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1 font-mono">
                  3_finetune.py &gt; diagnose.py
                </div>
              </div>
              <ScrollText size={18} className="text-[var(--vs-accent)]" />
            </button>
          </section>
        )}
      </div>
    </div>
  );
}

function PeftPickerCard({
  items,
  onPick,
  onClose,
}: {
  items: PeftCandidate[];
  onPick: (p: PeftCandidate) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="mt-3 vs-card p-3 border-[color:var(--vs-accent)]/50">
      <div className="flex items-center gap-2 mb-2">
        <FolderOpen size={13} className="text-[#dcb67a]" />
        <span className="vs-panel-title">{t("oc.peft_title")}</span>
        <button
          className="ml-auto vs-btn-ghost px-2 h-[22px] text-[11px]"
          onClick={onClose}
        >
          {t("common.cancel")}
        </button>
      </div>
      {items.length === 0 ? (
        <div className="text-[12px] text-[var(--vs-fg-muted)] italic">
          {t("oc.peft_empty")}
        </div>
      ) : (
        <div className="space-y-1">
          {items.map((p) => (
            <div
              key={p.adapter_path}
              className="flex items-center gap-2 px-2 py-1 text-[12px] font-mono hover:bg-[var(--vs-hover)] rounded-sm"
            >
              <FileCode2
                size={12}
                className="text-[#519aba] shrink-0"
              />
              <span className="truncate flex-1">{p.relative}</span>
              <span className="text-[10px] text-[var(--vs-fg-subtle)] truncate max-w-[220px]">
                base: {p.base_model || "—"}
              </span>
              <button
                className="vs-btn-ghost px-2 h-[20px] text-[11px]"
                onClick={() => onPick(p)}
              >
                <Plus size={10} className="inline mr-1" />
                {t("oc.peft_add")}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
