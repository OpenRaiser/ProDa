import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  Database,
  FileCode2,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Settings2,
  Square,
  TerminalSquare,
} from "lucide-react";
import clsx from "clsx";
import Editor from "@monaco-editor/react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { usePageLabels } from "@/hooks/usePageLabels";
import {
  cancelTraining,
  envCheck,
  envSettingsPut,
  getHistory,
  getOutputTree,
  listDatasets,
  listModels,
  previewYaml,
  startTraining,
} from "@/api/finetune_train";
import type {
  EnvCheck,
  FineTuningType,
  OutputTreeEntry,
  TrainDataset,
  TrainingConfig,
  TrainingSession,
} from "@/types";

const DEFAULT_CONFIG: TrainingConfig = {
  dataset_source: "session",
  dataset_path: "",
  dataset_name: "dataset",
  model_path: "",
  template: "",
  finetuning_type: "lora",
  lora_rank: 8,
  lora_alpha: 16,
  lora_dropout: 0.05,
  learning_rate: 5e-5,
  warmup_ratio: 0.03,
  num_train_epochs: 3.0,
  per_device_train_batch_size: 1,
  gradient_accumulation_steps: 8,
  cutoff_len: 2048,
  max_samples: 100000,
  logging_steps: 5,
  save_steps: 200,
  nproc_per_node: 1,
};

type ConfigTab = "general" | "lora" | "advanced";

export function FineTuning() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const project = useSession((s) => s.currentProject);
  const openTab = useSession((s) => s.openTab);
  const active = useSession((s) => s.activeTrainingSession);
  const preselectedSessionId = useSession((s) => s.preselectedTrainSessionId);
  const setPreselectedSessionId = useSession((s) => s.setPreselectedTrainSessionId);

  const [env, setEnv] = useState<EnvCheck | null>(null);
  const [envLoading, setEnvLoading] = useState(false);
  const [envEdit, setEnvEdit] = useState({ llamafactory_path: "", model_root: "" });
  const [envSaving, setEnvSaving] = useState(false);

  const [datasets, setDatasets] = useState<TrainDataset[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [modelRoot, setModelRoot] = useState("");
  const [history, setHistory] = useState<TrainingSession[]>([]);

  const [cfg, setCfg] = useState<TrainingConfig>(DEFAULT_CONFIG);
  const [configTab, setConfigTab] = useState<ConfigTab>("general");

  const [yamlText, setYamlText] = useState<string>("");
  const [yamlEdited, setYamlEdited] = useState(false);
  const [previewing, setPreviewing] = useState(false);

  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState("");
  const [canceling, setCanceling] = useState(false);

  const [outputTree, setOutputTree] = useState<OutputTreeEntry[]>([]);

  // Refresh env + discovery
  const refreshEnv = useCallback(async () => {
    setEnvLoading(true);
    try {
      const e = await envCheck();
      setEnv(e);
      setEnvEdit((prev) => ({
        llamafactory_path: prev.llamafactory_path || e.llamafactory_path,
        model_root: prev.model_root || e.model_root,
      }));
    } catch {
      /* ignore */
    } finally {
      setEnvLoading(false);
    }
  }, []);

  const refreshDiscovery = useCallback(async () => {
    if (!project) return;
    try {
      const [dsList, mRes, hist] = await Promise.all([
        listDatasets(project.id),
        listModels(project.id),
        getHistory(project.id),
      ]);
      setDatasets(dsList);
      setModels(mRes.models);
      setModelRoot(mRes.model_root);
      setHistory(hist);
      setCfg((prev) => {
        let next = prev;
        if (!next.model_path && mRes.models[0]) {
          next = { ...next, model_path: mRes.models[0] };
        }
        if (
          next.dataset_source === "session" &&
          !dsList.some((d) => d.source === "session")
        ) {
          const fileDs = dsList.find((d) => d.source === "file");
          if (fileDs) {
            next = {
              ...next,
              dataset_source: "file",
              dataset_path: fileDs.path,
              dataset_name: fileDs.name,
            };
          }
        } else if (next.dataset_source === "session") {
          const sessionDs = dsList.find((d) => d.source === "session");
          if (sessionDs) next = { ...next, dataset_name: sessionDs.name };
        }
        return next;
      });
    } catch {
      /* ignore */
    }
  }, [project]);

  useEffect(() => {
    refreshEnv();
  }, [refreshEnv]);

  useEffect(() => {
    refreshDiscovery();
  }, [refreshDiscovery]);

  // Keep history fresh when active session changes
  useEffect(() => {
    if (!project) return;
    getHistory(project.id)
      .then(setHistory)
      .catch(() => {});
  }, [project, active?.session_id, active?.alive]);

  // Load checkpoint tree when an active session exists
  useEffect(() => {
    if (!project || !active?.session_id) {
      setOutputTree([]);
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await getOutputTree(project.id, active.session_id);
        if (!cancelled) setOutputTree(res.entries);
      } catch {
        /* ignore */
      }
    };
    tick();
    const iv = setInterval(tick, 10_000);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [project, active?.session_id]);

  const handleEnvSave = async () => {
    setEnvSaving(true);
    try {
      await envSettingsPut({
        llamafactory_path: envEdit.llamafactory_path,
        model_root: envEdit.model_root,
      });
      await refreshEnv();
      await refreshDiscovery();
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLaunchError(err?.message ?? "Save failed");
    } finally {
      setEnvSaving(false);
    }
  };

  const handlePreview = useCallback(async () => {
    if (!project) return;
    setPreviewing(true);
    try {
      const res = await previewYaml(project.id, cfg);
      setYamlText(res.yaml);
      setYamlEdited(false);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLaunchError(err?.message ?? "Preview failed");
    } finally {
      setPreviewing(false);
    }
  }, [project, cfg]);

  // Auto-preview when cfg changes (debounced)
  useEffect(() => {
    if (!project) return;
    if (yamlEdited) return;
    const timer = setTimeout(handlePreview, 350);
    return () => clearTimeout(timer);
  }, [cfg, project, yamlEdited, handlePreview]);

  const handleLaunch = async () => {
    if (!project) return;
    setLaunchError("");
    setLaunching(true);
    try {
      await startTraining(project.id, cfg, yamlEdited ? yamlText : "");
      // Active session will be picked up by watcher within 6s.
      const hist = await getHistory(project.id);
      setHistory(hist);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLaunchError(err?.message ?? "Launch failed");
    } finally {
      setLaunching(false);
    }
  };

  const handleCancel = async () => {
    if (!project) return;
    setCanceling(true);
    try {
      await cancelTraining(project.id);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLaunchError(err?.message ?? "Cancel failed");
    } finally {
      setCanceling(false);
    }
  };

  const running = active?.alive === true;
  const envOk = !!env?.llamafactory_path_ok && !!env?.model_root_ok;
  const canLaunch =
    !!project &&
    envOk &&
    !running &&
    !launching &&
    !!cfg.model_path &&
    (cfg.dataset_source === "session"
      ? datasets.some((d) => d.source === "session")
      : !!cfg.dataset_path);

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1280px] mx-auto px-10 py-6 space-y-6">
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">
            {t("ftune.title")}
          </h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("ftune.desc")}</p>
        </div>

        {/* Env banner */}
        <EnvBanner
          env={env}
          loading={envLoading}
          edit={envEdit}
          onEditChange={setEnvEdit}
          onRefresh={refreshEnv}
          onSave={handleEnvSave}
          saving={envSaving}
        />

        {/* Active training banner (when any) */}
        {active && (
          <ActiveSessionBanner
            active={active}
            onCancel={handleCancel}
            canceling={canceling}
          />
        )}

        {/* Dataset + Model */}
        <section>
          <h2 className="vs-panel-title mb-3">{t("ftune.data_model_title")}</h2>
          <div className="vs-card p-4 space-y-4">
            {/* Dataset */}
            <div>
              <label className="vs-label flex items-center gap-2">
                <Database size={11} />
                {t("ftune.dataset")}
              </label>
              <select
                className="vs-input"
                value={
                  cfg.dataset_source === "session"
                    ? "session::current-session-data"
                    : `file::${cfg.dataset_path}`
                }
                onChange={(e) => {
                  const [kind, rest] = e.target.value.split("::");
                  if (kind === "session") {
                    const name =
                      datasets.find((d) => d.source === "session")?.name ??
                      "current-session-data";
                    setCfg({
                      ...cfg,
                      dataset_source: "session",
                      dataset_path: "",
                      dataset_name: name,
                    });
                  } else {
                    const ds = datasets.find(
                      (d) => d.source === "file" && d.path === rest
                    );
                    setCfg({
                      ...cfg,
                      dataset_source: "file",
                      dataset_path: rest,
                      dataset_name: ds?.name ?? "dataset",
                    });
                  }
                }}
              >
                {datasets.length === 0 && (
                  <option>{t("ftune.no_datasets")}</option>
                )}
                {datasets.map((d) => (
                  <option
                    key={`${d.source}::${d.path || d.name}`}
                    value={
                      d.source === "session"
                        ? "session::current-session-data"
                        : `file::${d.path}`
                    }
                  >
                    [{d.source}] {d.name} · {d.row_count} rows
                    {d.is_sharegpt ? " · sharegpt" : ""}
                  </option>
                ))}
              </select>
              <label className="vs-label mt-3">
                {t("ftune.dataset_name")}
              </label>
              <input
                className="vs-input"
                value={cfg.dataset_name}
                onChange={(e) =>
                  setCfg({ ...cfg, dataset_name: e.target.value })
                }
              />
            </div>

            {/* Model */}
            <div>
              <label className="vs-label flex items-center gap-2">
                <Cpu size={11} />
                {t("ftune.base_model")}
                {modelRoot && (
                  <span className="text-[10px] text-[var(--vs-fg-subtle)] normal-case tracking-normal font-mono">
                    · root={modelRoot}
                  </span>
                )}
              </label>
              {models.length === 0 ? (
                <div className="text-[12px] text-[#dcdcaa]">
                  {t("ftune.no_models", { root: modelRoot })}
                </div>
              ) : (
                <select
                  className="vs-input"
                  value={cfg.model_path}
                  onChange={(e) =>
                    setCfg({ ...cfg, model_path: e.target.value, template: "" })
                  }
                >
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              )}
              <label className="vs-label mt-3">
                {t("ftune.template")}
              </label>
              <input
                className="vs-input font-mono"
                value={cfg.template}
                onChange={(e) => setCfg({ ...cfg, template: e.target.value })}
                placeholder={t("ftune.template_placeholder")}
              />
            </div>
          </div>
        </section>

        {/* Training config tabs */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="vs-panel-title">{t("ftune.config_title")}</h2>
            <div className="flex gap-1">
              {(["general", "lora", "advanced"] as ConfigTab[]).map((c) => (
                <button
                  key={c}
                  onClick={() => setConfigTab(c)}
                  className={clsx(
                    "px-3 h-[24px] text-[12px] rounded-sm",
                    configTab === c
                      ? "bg-[var(--vs-selected)] text-white"
                      : "text-[var(--vs-fg)] hover:bg-[var(--vs-hover)]"
                  )}
                >
                  {t(`ftune.tab_${c}`)}
                </button>
              ))}
            </div>
          </div>
          <div className="vs-card p-4">
            {configTab === "general" && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <FTSelect
                  label={t("ftune.finetuning_type")}
                  value={cfg.finetuning_type}
                  onChange={(v) =>
                    setCfg({ ...cfg, finetuning_type: v as FineTuningType })
                  }
                  options={[
                    { v: "lora", t: "LoRA" },
                    { v: "qlora", t: "QLoRA (4-bit)" },
                    { v: "full", t: t("ftune.full_ft") },
                  ]}
                />
                <FTNum
                  label={t("ftune.epochs")}
                  value={cfg.num_train_epochs}
                  step={0.5}
                  min={0.1}
                  max={20}
                  onChange={(v) => setCfg({ ...cfg, num_train_epochs: v })}
                />
                <FTNum
                  label={t("ftune.lr")}
                  value={cfg.learning_rate}
                  step={1e-5}
                  min={1e-7}
                  max={1e-2}
                  onChange={(v) => setCfg({ ...cfg, learning_rate: v })}
                />
                <FTNum
                  label={t("ftune.warmup_ratio")}
                  value={cfg.warmup_ratio}
                  step={0.005}
                  min={0}
                  max={0.3}
                  onChange={(v) => setCfg({ ...cfg, warmup_ratio: v })}
                />
                <FTNum
                  label={t("ftune.batch_size")}
                  value={cfg.per_device_train_batch_size}
                  step={1}
                  min={1}
                  max={64}
                  onChange={(v) =>
                    setCfg({ ...cfg, per_device_train_batch_size: v })
                  }
                />
                <FTNum
                  label={t("ftune.grad_accum")}
                  value={cfg.gradient_accumulation_steps}
                  step={1}
                  min={1}
                  max={64}
                  onChange={(v) =>
                    setCfg({ ...cfg, gradient_accumulation_steps: v })
                  }
                />
                <FTNum
                  label={t("ftune.nproc")}
                  value={cfg.nproc_per_node}
                  step={1}
                  min={1}
                  max={8}
                  onChange={(v) => setCfg({ ...cfg, nproc_per_node: v })}
                />
              </div>
            )}
            {configTab === "lora" && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {cfg.finetuning_type === "full" ? (
                  <div className="col-span-3 text-[12px] text-[#dcdcaa]">
                    {t("ftune.lora_disabled_full")}
                  </div>
                ) : (
                  <>
                    <FTNum
                      label={t("ftune.lora_rank")}
                      value={cfg.lora_rank}
                      step={1}
                      min={1}
                      max={256}
                      onChange={(v) => setCfg({ ...cfg, lora_rank: v })}
                    />
                    <FTNum
                      label={t("ftune.lora_alpha")}
                      value={cfg.lora_alpha}
                      step={1}
                      min={1}
                      max={512}
                      onChange={(v) => setCfg({ ...cfg, lora_alpha: v })}
                    />
                    <FTNum
                      label={t("ftune.lora_dropout")}
                      value={cfg.lora_dropout}
                      step={0.01}
                      min={0}
                      max={0.9}
                      onChange={(v) => setCfg({ ...cfg, lora_dropout: v })}
                    />
                  </>
                )}
              </div>
            )}
            {configTab === "advanced" && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <FTNum
                  label={t("ftune.cutoff_len")}
                  value={cfg.cutoff_len}
                  step={128}
                  min={128}
                  max={32768}
                  onChange={(v) => setCfg({ ...cfg, cutoff_len: v })}
                />
                <FTNum
                  label={t("ftune.max_samples")}
                  value={cfg.max_samples}
                  step={100}
                  min={10}
                  max={10_000_000}
                  onChange={(v) => setCfg({ ...cfg, max_samples: v })}
                />
                <FTNum
                  label={t("ftune.logging_steps")}
                  value={cfg.logging_steps}
                  step={1}
                  min={1}
                  max={10000}
                  onChange={(v) => setCfg({ ...cfg, logging_steps: v })}
                />
                <FTNum
                  label={t("ftune.save_steps")}
                  value={cfg.save_steps}
                  step={10}
                  min={1}
                  max={100000}
                  onChange={(v) => setCfg({ ...cfg, save_steps: v })}
                />
              </div>
            )}
          </div>
        </section>

        {/* YAML preview */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="vs-panel-title">{t("ftune.yaml_title")}</h2>
            <div className="flex items-center gap-2 text-[11px] text-[var(--vs-fg-muted)]">
              {previewing && <Loader2 size={11} className="animate-spin" />}
              {yamlEdited && (
                <span className="text-[#dcdcaa]">● edited</span>
              )}
              <button
                className="vs-btn-ghost px-2 h-[22px] flex items-center gap-1"
                onClick={() => {
                  setYamlEdited(false);
                  handlePreview();
                }}
                title={t("ftune.regen_yaml")}
              >
                <RefreshCw size={11} />
                {t("ftune.regen_yaml")}
              </button>
            </div>
          </div>
          <div className="vs-card overflow-hidden">
            <div className="px-4 py-2 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] flex items-center gap-2 text-[12px]">
              <FileText size={13} className="text-[#cbcb41]" />
              <span className="text-[var(--vs-fg)] font-mono">
                {cfg.dataset_name}_{cfg.model_path.split(/[\\/]/).pop() || "model"}.yaml
              </span>
              <span className="ml-auto text-[11px] text-[var(--vs-fg-subtle)]">
                {t("ftune.yaml_editable")}
              </span>
            </div>
            <div style={{ height: 320 }}>
              <Editor
                value={yamlText}
                language="yaml"
                theme="vs-dark"
                onChange={(v) => {
                  setYamlText(v ?? "");
                  setYamlEdited(true);
                }}
                options={{
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
              title={
                !envOk
                  ? t("ftune.need_env")
                  : running
                  ? t("ftune.already_running")
                  : !cfg.model_path
                  ? t("ftune.need_model")
                  : ""
              }
            >
              {launching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              {t("ftune.launch")}
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
                {t("ftune.cancel")}
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

        {/* Training console (inline: metrics + log) */}
        {active && <TrainingConsole outputTree={outputTree} />}

        {/* History */}
        <HistoryList
          history={history}
          highlightedSessionId={preselectedSessionId}
          onHighlightConsumed={() => setPreselectedSessionId(null)}
        />

        {/* Next step */}
        {history.some((h) => h.status === "finished") && (
          <section>
            <h2 className="vs-panel-title mb-3">{t("dp.next_actions")}</h2>
            <button
              className="vs-card p-4 flex items-center justify-between w-full hover:border-[var(--vs-accent)] text-left"
              onClick={() => openTab(buildTab("opencompass"))}
            >
              <div>
                <div className="text-[14px] text-[var(--vs-fg-strong)]">
                  {t("ftune.go_eval")}
                </div>
                <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1 font-mono">
                  6_opencompass.py
                </div>
              </div>
              <TerminalSquare size={18} className="text-[var(--vs-accent)]" />
            </button>
          </section>
        )}
      </div>
    </div>
  );
}

// =========== Sub-components ===========

function EnvBanner({
  env,
  loading,
  edit,
  onEditChange,
  onRefresh,
  onSave,
  saving,
}: {
  env: EnvCheck | null;
  loading: boolean;
  edit: { llamafactory_path: string; model_root: string };
  onEditChange: (v: { llamafactory_path: string; model_root: string }) => void;
  onRefresh: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const allOk = !!env?.llamafactory_path_ok && !!env?.model_root_ok;
  return (
    <section>
      <div
        className={clsx(
          "vs-card p-4",
          !allOk && "border-[#dcdcaa]/50 bg-[#dcdcaa]/5"
        )}
      >
        <div className="flex items-start gap-3 flex-wrap">
          {allOk ? (
            <CheckCircle2 size={18} className="text-[#4ec9b0] shrink-0 mt-0.5" />
          ) : (
            <Settings2 size={18} className="text-[#dcdcaa] shrink-0 mt-0.5" />
          )}
          <div className="flex-1 min-w-[240px] space-y-1">
            <div className="text-[13px] text-[var(--vs-fg-strong)]">
              {allOk ? t("ftune.env_ok") : t("ftune.env_setup_required")}
            </div>
            {env && (
              <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono space-y-0.5">
                <div>
                  LLaMA-Factory: {env.llamafactory_path_ok ? "✓" : "✗"}{" "}
                  <span className="text-[var(--vs-fg-subtle)]">{env.llamafactory_path}</span>
                </div>
                <div>
                  Model root: {env.model_root_ok ? "✓" : "✗"}{" "}
                  <span className="text-[var(--vs-fg-subtle)]">{env.model_root}</span>
                </div>
                <div>
                  GPU: {env.gpu_count} ·{" "}
                  {env.gpus.map((g) => `${g.name} (${g.memory_mb}MB)`).join(", ") ||
                    "—"}
                </div>
                <div>
                  CUDA: {env.cuda_home || "—"} · torch {env.torch_version || "—"}{" "}
                  · {env.cli} · Python {env.python}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 self-start">
            <button
              className="vs-btn-ghost px-2 h-[26px] flex items-center gap-1 text-[12px]"
              onClick={onRefresh}
              disabled={loading}
            >
              {loading ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              {t("common.refresh")}
            </button>
            <button
              className="vs-btn-ghost px-2 h-[26px] flex items-center gap-1 text-[12px]"
              onClick={() => setExpanded((v) => !v)}
            >
              <Settings2 size={12} />
              {t("ftune.configure_paths")}
            </button>
          </div>
        </div>
        {expanded && (
          <div className="mt-3 border-t border-[var(--vs-border)] pt-3 space-y-2">
            <div>
              <label className="vs-label">LLaMA-Factory path</label>
              <input
                className="vs-input font-mono"
                value={edit.llamafactory_path}
                onChange={(e) =>
                  onEditChange({ ...edit, llamafactory_path: e.target.value })
                }
              />
            </div>
            <div>
              <label className="vs-label">Model root</label>
              <input
                className="vs-input font-mono"
                value={edit.model_root}
                onChange={(e) =>
                  onEditChange({ ...edit, model_root: e.target.value })
                }
              />
            </div>
            <button
              className="vs-btn flex items-center gap-2"
              onClick={onSave}
              disabled={saving}
            >
              {saving ? (
                <Loader2 size={13} className="animate-spin" />
              ) : null}
              {t("ftune.save_paths")}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function ActiveSessionBanner({
  active,
  onCancel,
  canceling,
}: {
  active: TrainingSession;
  onCancel: () => void;
  canceling: boolean;
}) {
  const { t } = useI18n();
  const alive = active.alive === true;
  return (
    <div
      className={clsx(
        "vs-card p-3 flex items-center gap-3 flex-wrap",
        alive
          ? "border-[color:var(--vs-accent)]/50 bg-[color:var(--vs-accent)]/5"
          : "border-[color:var(--vs-fg-subtle)]/50 bg-[color:var(--vs-fg-subtle)]/5"
      )}
    >
      {alive ? (
        <Loader2 size={14} className="text-[var(--vs-accent)] animate-spin shrink-0" />
      ) : (
        <CheckCircle2 size={14} className="text-[#4ec9b0] shrink-0" />
      )}
      <div className="flex-1 min-w-[200px] text-[12px]">
        <div className="text-[var(--vs-fg-strong)]">
          {alive ? t("ftune.session_running") : t("ftune.session_finished")}{" "}
          <span className="text-[var(--vs-fg-muted)] font-mono">
            pid={active.pid} · {active.dataset_name} → {active.model_tag}
          </span>
        </div>
        <div className="text-[11px] text-[var(--vs-fg-subtle)] font-mono truncate">
          {active.output_dir}
        </div>
      </div>
      {alive && (
        <button
          className="vs-btn-secondary flex items-center gap-2"
          onClick={onCancel}
          disabled={canceling}
        >
          {canceling ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Square size={12} />
          )}
          {t("ftune.cancel")}
        </button>
      )}
    </div>
  );
}

function TrainingConsole({ outputTree }: { outputTree: OutputTreeEntry[] }) {
  const { t } = useI18n();
  const metrics = useSession((s) => s.trainingMetrics);
  const logs = useSession((s) => s.trainingLogs);
  const [tab, setTab] = useState<"metrics" | "log" | "outputs">("metrics");
  const logBoxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (tab !== "log") return;
    const el = logBoxRef.current;
    if (!el) return;
    // Auto-scroll only if near bottom
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [logs, tab]);

  const latestLoss = useMemo(() => {
    for (let i = metrics.length - 1; i >= 0; i -= 1) {
      if (metrics[i].loss !== undefined) return metrics[i].loss as number;
    }
    return null;
  }, [metrics]);
  const latestLr = useMemo(() => {
    for (let i = metrics.length - 1; i >= 0; i -= 1) {
      if (metrics[i].lr !== undefined) return metrics[i].lr as number;
    }
    return null;
  }, [metrics]);
  const latestStep = metrics.length ? metrics[metrics.length - 1].step : 0;
  const totalSteps = metrics.length
    ? (metrics[metrics.length - 1].total_steps as number | undefined)
    : undefined;

  return (
    <section>
      <h2 className="vs-panel-title mb-3">{t("ftune.console_title")}</h2>
      <div className="vs-card overflow-hidden">
        <div className="h-[30px] flex items-center gap-0 px-2 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)]">
          {(["metrics", "log", "outputs"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={clsx(
                "px-3 h-full text-[11px] uppercase tracking-wider border-b-2",
                tab === k
                  ? "border-[var(--vs-accent)] text-[var(--vs-fg-strong)]"
                  : "border-transparent text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg)]"
              )}
            >
              {t(`ftune.console_tab_${k}`)}
            </button>
          ))}
          <div className="ml-auto text-[11px] text-[var(--vs-fg-muted)] font-mono pr-2">
            step {latestStep}
            {totalSteps ? `/${totalSteps}` : ""}
            {latestLoss !== null && ` · loss ${latestLoss.toFixed(4)}`}
            {latestLr !== null && ` · lr ${latestLr.toExponential(2)}`}
          </div>
        </div>
        {tab === "metrics" && (
          <div className="p-3 grid grid-cols-1 md:grid-cols-2 gap-4">
            <MetricChart
              title={t("ftune.loss_chart")}
              data={metrics.filter((p) => p.loss !== undefined)}
              dataKey="loss"
              color="var(--vs-accent)"
            />
            <MetricChart
              title={t("ftune.lr_chart")}
              data={metrics.filter((p) => p.lr !== undefined)}
              dataKey="lr"
              color="#c586c0"
            />
          </div>
        )}
        {tab === "log" && (
          <div
            ref={logBoxRef}
            className="p-3 max-h-[420px] overflow-auto font-mono text-[11px] text-[var(--vs-fg)] whitespace-pre-wrap"
          >
            {logs.length === 0 ? (
              <div className="text-[var(--vs-fg-muted)] italic">
                {t("ftune.log_waiting")}
              </div>
            ) : (
              logs.map((line, i) => (
                <div key={i}>{line}</div>
              ))
            )}
          </div>
        )}
        {tab === "outputs" && (
          <div className="p-3">
            {outputTree.length === 0 ? (
              <div className="text-[12px] text-[var(--vs-fg-muted)] italic">
                {t("ftune.outputs_empty")}
              </div>
            ) : (
              <div className="space-y-0.5">
                {outputTree.map((e) => (
                  <div
                    key={e.name}
                    className="flex items-center gap-2 text-[12px] text-[var(--vs-fg)] font-mono"
                  >
                    <FileCode2
                      size={12}
                      className={clsx(
                        "shrink-0",
                        e.kind === "dir" ? "text-[#dcb67a]" : "text-[#519aba]"
                      )}
                    />
                    <span className="flex-1 truncate">{e.name}</span>
                    {e.step !== undefined && (
                      <span className="text-[10px] text-[var(--vs-fg-subtle)]">
                        step {e.step}
                      </span>
                    )}
                    {e.kind === "file" && (
                      <span className="text-[10px] text-[var(--vs-fg-subtle)]">
                        {(e.size / 1024).toFixed(1)} KB
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function MetricChart({
  title,
  data,
  dataKey,
  color,
}: {
  title: string;
  data: import("@/types").TrainingMetricsPoint[];
  dataKey: "loss" | "lr";
  color: string;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] mb-2">
        {title}
      </div>
      {data.length === 0 ? (
        <div className="h-[160px] flex items-center justify-center text-[11px] text-[var(--vs-fg-subtle)] italic">
          no data yet
        </div>
      ) : (
        <div style={{ width: "100%", height: 160 }}>
          <ResponsiveContainer>
            <LineChart
              data={data}
              margin={{ top: 6, right: 10, left: -10, bottom: 0 }}
            >
              <CartesianGrid stroke="var(--vs-border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="step"
                stroke="var(--vs-fg-subtle)"
                fontSize={10}
                tickMargin={3}
              />
              <YAxis stroke="var(--vs-fg-subtle)" fontSize={10} width={50} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--vs-sidebar)",
                  border: "1px solid #3c3c3c",
                  fontSize: 11,
                }}
                labelStyle={{ color: "var(--vs-fg)" }}
                itemStyle={{ color: "var(--vs-fg)" }}
              />
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function HistoryList({
  history,
  highlightedSessionId,
  onHighlightConsumed,
}: {
  history: TrainingSession[];
  highlightedSessionId?: string | null;
  onHighlightConsumed?: () => void;
}) {
  const { t } = useI18n();
  const highlightRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!highlightedSessionId) return;
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    const timer = setTimeout(() => onHighlightConsumed?.(), 2500);
    return () => clearTimeout(timer);
  }, [highlightedSessionId, onHighlightConsumed]);

  if (history.length === 0) {
    return (
      <section>
        <h2 className="vs-panel-title mb-3">{t("ftune.history_title")}</h2>
        <div className="vs-card p-4 text-[12px] text-[var(--vs-fg-muted)] italic">
          {t("ftune.no_history")}
        </div>
      </section>
    );
  }
  return (
    <section>
      <h2 className="vs-panel-title mb-3">{t("ftune.history_title")}</h2>
      <div className="vs-card p-3 space-y-1">
        {history.slice(0, 15).map((h) => {
          const statusColor =
            h.status === "finished"
              ? "#4ec9b0"
              : h.status === "running"
              ? "var(--vs-accent)"
              : "#f48771";
          const ts = h.started_at
            ? new Date(h.started_at * 1000).toISOString().slice(0, 19).replace("T", " ")
            : "—";
          const isHighlighted = highlightedSessionId === h.session_id;
          return (
            <div
              key={h.session_id}
              ref={isHighlighted ? highlightRef : null}
              className={clsx(
                "flex items-center gap-3 px-2 py-1 text-[12px] rounded-sm transition-colors",
                isHighlighted
                  ? "bg-[var(--vs-accent-bg)] outline outline-1 outline-[var(--vs-accent)]"
                  : "hover:bg-[var(--vs-hover)]"
              )}
            >
              <span
                className="w-[6px] h-[6px] rounded-full shrink-0"
                style={{ backgroundColor: statusColor }}
              />
              <span className="font-mono text-[var(--vs-fg-muted)] w-[130px] shrink-0 text-[11px]">
                {h.status ?? "?"}
              </span>
              <span className="font-mono text-[var(--vs-fg-subtle)] text-[11px] shrink-0 w-[180px]">
                {ts}
              </span>
              <span className="truncate text-[var(--vs-fg)]">
                {h.dataset_name} → {h.model_tag ?? h.model_path}{" "}
                <span className="text-[var(--vs-fg-subtle)]">({h.finetuning_type})</span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// Small reusable controls

function FTSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ v: string; t: string }>;
}) {
  return (
    <div>
      <label className="vs-label">{label}</label>
      <select
        className="vs-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.v} value={o.v}>
            {o.t}
          </option>
        ))}
      </select>
    </div>
  );
}

function FTNum({
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
        onChange={(e) => {
          const v = Number.parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
      />
    </div>
  );
}
