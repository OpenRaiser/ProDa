import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Play,
  Square,
  Loader2,
  Download,
  Save,
  ArrowRight,
  AlertCircle,
  FileJson,
} from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { usePageLabels } from "@/hooks/usePageLabels";
import {
  deleteUpload,
  inspectJson,
  listUploads,
  uploadFiles,
  startExtraction,
  getJob,
  cancelJob,
} from "@/api/extraction";
import {
  getKnowledgeCore,
  saveKnowledgeCore,
  saveJsonFields,
} from "@/api/projects";
import type {
  ExtractionJob,
  KnowledgeCore,
  L1Concept,
  L2Statement,
  L3Chain,
  UploadedFileMeta,
} from "@/types";
import { FileUploadZone } from "@/components/data/FileUploadZone";
import {
  DEFAULT_CFG,
  ExtractionConfigForm,
  type ExtractionCfg,
} from "@/components/data/ExtractionConfig";
import { EditableTable, type ColumnDef } from "@/components/data/EditableTable";
import { JobBanner } from "@/components/common/JobBanner";
import { reconcileFiltered, stripRid, withRid } from "@/lib/rowKey";

type LTab = "l1" | "l2" | "l3" | "export";

export function DataProcessing() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const project = useSession((s) => s.currentProject);
  const openTab = useSession((s) => s.openTab);
  const profiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);

  const [uploads, setUploads] = useState<UploadedFileMeta[]>([]);
  const [uploading, setUploading] = useState(false);
  const [availableJsonPaths, setAvailableJsonPaths] = useState<string[]>([]);
  const [jsonFields, setJsonFields] = useState<string[]>([]);
  const [cfg, setCfg] = useState<ExtractionCfg>(DEFAULT_CFG);
  const [job, setJob] = useState<ExtractionJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [launchError, setLaunchError] = useState("");

  const [core, setCore] = useState<KnowledgeCore | null>(null);
  const [dirty, setDirty] = useState(false);
  const [savingCore, setSavingCore] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [lTab, setLTab] = useState<LTab>("l3");

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const firstJsonUpload = useMemo(
    () => uploads.find((u) => u.ext === "json"),
    [uploads]
  );

  const refreshUploads = useCallback(async () => {
    if (!project) return;
    try {
      const list = await listUploads(project.id);
      setUploads(list);
    } catch {
      // ignore
    }
  }, [project]);

  const refreshCore = useCallback(async () => {
    if (!project) return;
    try {
      const c = await getKnowledgeCore(project.id);
      if (c) {
        setCore({
          ...c,
          l1_concepts: withRid(c.l1_concepts) as unknown as L1Concept[],
          l2_statements: withRid(c.l2_statements) as unknown as L2Statement[],
          l3_chains: withRid(c.l3_chains) as unknown as L3Chain[],
        });
      } else {
        setCore(null);
      }
      setDirty(false);
    } catch {
      // ignore
    }
  }, [project]);

  useEffect(() => {
    refreshUploads();
    refreshCore();
  }, [refreshUploads, refreshCore]);

  // When JSON file set changes, inspect paths
  useEffect(() => {
    (async () => {
      if (!project || !firstJsonUpload) {
        setAvailableJsonPaths([]);
        return;
      }
      try {
        const paths = await inspectJson(project.id, firstJsonUpload.file_id);
        setAvailableJsonPaths(paths);
      } catch {
        setAvailableJsonPaths([]);
      }
    })();
  }, [project, firstJsonUpload]);

  const handleUpload = async (files: FileList) => {
    if (!project) return;
    setUploading(true);
    try {
      await uploadFiles(project.id, Array.from(files));
      await refreshUploads();
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (fileId: string) => {
    if (!project) return;
    await deleteUpload(project.id, fileId);
    await refreshUploads();
  };

  const startPolling = useCallback(
    (jobId: string) => {
      if (pollTimer.current) clearInterval(pollTimer.current);
      pollTimer.current = setInterval(async () => {
        try {
          const j = await getJob(jobId);
          setJob(j);
          if (j.status === "done" || j.status === "error" || j.status === "cancelled") {
            if (pollTimer.current) {
              clearInterval(pollTimer.current);
              pollTimer.current = null;
            }
            if (j.status === "done" && j.result) {
              setCore({
                ...j.result,
                l1_concepts: withRid(j.result.l1_concepts) as unknown as L1Concept[],
                l2_statements: withRid(j.result.l2_statements) as unknown as L2Statement[],
                l3_chains: withRid(j.result.l3_chains) as unknown as L3Chain[],
              });
              setDirty(false);
              setLTab("l3");
            }
          }
        } catch {
          // ignore transient errors; keep polling
        }
      }, 900);
    },
    []
  );

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  const handleStart = async () => {
    if (!project) return;
    setLaunchError("");
    if (uploads.length === 0) {
      setLaunchError(t("dp.no_files"));
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
    await saveJsonFields(project.id, jsonFields).catch(() => void 0);

    setStarting(true);
    try {
      const jobId = await startExtraction(project.id, {
        file_ids: uploads.map((u) => u.file_id),
        json_fields: jsonFields,
        chunk_size: cfg.chunk_size,
        chunk_overlap: cfg.chunk_overlap,
        processing_mode: cfg.processing_mode,
        merge_threshold: cfg.merge_threshold,
        parallel_chunks: cfg.parallel_chunks,
        max_workers: cfg.max_workers,
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
        effective_mode: cfg.processing_mode,
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
      const j = await cancelJob(job.id);
      setJob(j);
    } catch {
      // ignore
    }
  };

  const handleSaveCore = async () => {
    if (!project || !core) return;
    setSavingCore(true);
    try {
      const cleaned: KnowledgeCore = {
        ...core,
        l1_concepts: stripRid(core.l1_concepts) as unknown as L1Concept[],
        l2_statements: stripRid(core.l2_statements) as unknown as L2Statement[],
        l3_chains: stripRid(core.l3_chains) as unknown as L3Chain[],
      };
      await saveKnowledgeCore(project.id, cleaned);
      setDirty(false);
      setSaveMsg(t("dp.saved_edits"));
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e: any) {
      setSaveMsg(e?.message ?? "Save failed");
    } finally {
      setSavingCore(false);
    }
  };

  const stats = core?.statistics ?? {};
  const running = job?.status === "pending" || job?.status === "running";

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1180px] mx-auto px-10 py-8 space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">{t("dp.title")}</h1>
          <p className="text-[13px] text-[var(--vs-fg-muted)] mt-1">{t("dp.desc")}</p>
        </div>

        {/* Upload */}
        <section>
          <h2 className="vs-panel-title mb-3">{t("dp.upload_title")}</h2>
          <FileUploadZone
            uploads={uploads}
            uploading={uploading}
            onUpload={handleUpload}
            onDelete={handleDelete}
            onRefresh={refreshUploads}
          />
        </section>

        {/* JSON fields */}
        {availableJsonPaths.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-2">
              <h2 className="vs-panel-title">{t("dp.json_fields")}</h2>
              <span className="text-[11px] text-[var(--vs-fg-subtle)]">
                {t("dp.json_fields_hint")}
              </span>
            </div>
            <div className="vs-card p-3 flex flex-wrap gap-[6px] max-h-[200px] overflow-auto">
              {availableJsonPaths.map((p) => {
                const selected = jsonFields.includes(p);
                return (
                  <button
                    key={p}
                    onClick={() =>
                      setJsonFields((prev) =>
                        selected ? prev.filter((x) => x !== p) : [...prev, p]
                      )
                    }
                    className={clsx(
                      "font-mono text-[12px] px-2 py-[3px] rounded-sm border",
                      selected
                        ? "bg-[var(--vs-accent-bg)] border-[var(--vs-accent)] text-white"
                        : "bg-[var(--vs-panel)] border-[var(--vs-border)] text-[var(--vs-fg)] hover:border-[var(--vs-accent)]"
                    )}
                  >
                    {p}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* Config */}
        <section>
          <h2 className="vs-panel-title mb-3">{t("dp.config_title")}</h2>
          <ExtractionConfigForm cfg={cfg} onChange={setCfg} />
        </section>

        {/* Start / Status */}
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
              {t("dp.extract")}
            </button>
            {running && (
              <button
                className="vs-btn-secondary flex items-center gap-2"
                onClick={handleCancel}
              >
                <Square size={12} />
                {t("dp.cancel_job")}
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
                pending: t("dp.job_pending"),
                running: t("dp.job_running"),
                done: t("dp.job_done"),
                error: t("dp.job_error"),
                cancelled: t("dp.job_cancelled"),
              }}
            />
          )}
        </section>

        {/* Results */}
        {core && (
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="vs-panel-title">{t("dp.results_title")}</h2>
              <div className="flex items-center gap-2">
                {saveMsg && (
                  <span className="text-[11px] text-[#4ec9b0]">{saveMsg}</span>
                )}
                {dirty && (
                  <span className="text-[11px] text-[#dcdcaa]">● unsaved</span>
                )}
                <button
                  className="vs-btn-secondary flex items-center gap-2"
                  onClick={handleSaveCore}
                  disabled={savingCore || !dirty}
                >
                  {savingCore ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Save size={13} />
                  )}
                  {t("dp.save_edits")}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Metric label={t("dp.stats_l3")} value={stats.total_chains ?? 0} color="#519aba" />
              <Metric label={t("dp.stats_l2")} value={stats.total_statements ?? 0} color="#c586c0" />
              <Metric label={t("dp.stats_l1")} value={stats.total_concepts ?? 0} color="#dcb67a" />
            </div>

            <LSubTabs value={lTab} onChange={setLTab}>
              <LSubTab id="l3" label={t("dp.tab_l3")} />
              <LSubTab id="l2" label={t("dp.tab_l2")} />
              <LSubTab id="l1" label={t("dp.tab_l1")} />
              <LSubTab id="export" label={t("dp.tab_export")} />
            </LSubTabs>

            {lTab === "l1" && (
              <L1View
                core={core}
                onUpdate={(rows) => {
                  setCore({ ...core, l1_concepts: rows });
                  setDirty(true);
                }}
              />
            )}
            {lTab === "l2" && (
              <L2View
                core={core}
                onUpdate={(rows) => {
                  setCore({ ...core, l2_statements: rows });
                  setDirty(true);
                }}
              />
            )}
            {lTab === "l3" && (
              <L3View
                core={core}
                onUpdate={(rows) => {
                  setCore({ ...core, l3_chains: rows });
                  setDirty(true);
                }}
              />
            )}
            {lTab === "export" && <ExportView core={core} />}
          </section>
        )}

        {/* Next actions */}
        {core && (
          <section>
            <h2 className="vs-panel-title mb-3">{t("dp.next_actions")}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <button
                className="vs-card p-4 flex items-center justify-between hover:border-[var(--vs-accent)] text-left"
                onClick={() => openTab(buildTab("benchmark"))}
              >
                <div>
                  <div className="text-[14px] text-[var(--vs-fg-strong)]">{t("dp.go_benchmark")}</div>
                  <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1 font-mono">
                    2_benchmark.py
                  </div>
                </div>
                <ArrowRight size={18} className="text-[var(--vs-accent)]" />
              </button>
              <button
                className="vs-card p-4 flex items-center justify-between hover:border-[var(--vs-accent)] text-left"
                onClick={() => openTab(buildTab("finetune"))}
              >
                <div>
                  <div className="text-[14px] text-[var(--vs-fg-strong)]">{t("dp.go_finetune")}</div>
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

// -------- Sub components --------

function Metric({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      className="vs-card p-4 border-l-[3px]"
      style={{ borderLeftColor: color }}
    >
      <div className="text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)]">
        {label}
      </div>
      <div className="text-[26px] font-light text-[var(--vs-fg-strong)] font-mono mt-1">
        {value}
      </div>
    </div>
  );
}

function LSubTabs({
  value,
  onChange,
  children,
}: {
  value: LTab;
  onChange: (v: LTab) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex border-b border-[var(--vs-border)]">
      {Array.isArray(children)
        ? children.map((ch: any) =>
            ch ? (
              <button
                key={ch.props.id}
                onClick={() => onChange(ch.props.id)}
                className={clsx(
                  "px-4 h-[32px] text-[12px] border-b-2",
                  value === ch.props.id
                    ? "border-[var(--vs-accent)] text-[var(--vs-fg-strong)]"
                    : "border-transparent text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg)]"
                )}
              >
                {ch.props.label}
              </button>
            ) : null
          )
        : null}
    </div>
  );
}

function LSubTab({ id, label }: { id: LTab; label: string }) {
  // rendered by LSubTabs; this stub is for prop-typed JSX
  return <span data-id={id} data-label={label} />;
}

function L1View({
  core,
  onUpdate,
}: {
  core: KnowledgeCore;
  onUpdate: (rows: L1Concept[]) => void;
}) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const rows = core.l1_concepts ?? [];
  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) =>
      JSON.stringify(r).toLowerCase().includes(s)
    );
  }, [q, rows]);

  const cols: ColumnDef<L1Concept>[] = [
    { key: "concept_id", title: "concept_id", readonly: true, width: "140px" },
    { key: "term", title: "term", width: "200px" },
    { key: "definition", title: "definition", type: "textarea" },
  ];

  return (
    <div className="space-y-3">
      <input
        className="vs-input max-w-[360px]"
        placeholder={t("common.search")}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <EditableTable<L1Concept>
        columns={cols}
        rows={filtered}
        onChange={(next) => {
          onUpdate(reconcileFiltered(rows, filtered, next));
        }}
        emptyTemplate={{ term: "", definition: "" }}
        addLabel={t("dp.add_row")}
      />
    </div>
  );
}

function L2View({
  core,
  onUpdate,
}: {
  core: KnowledgeCore;
  onUpdate: (rows: L2Statement[]) => void;
}) {
  const { t } = useI18n();
  const rows = core.l2_statements ?? [];
  const [chain, setChain] = useState<string>("__all__");
  const [q, setQ] = useState("");

  const chainIds = useMemo(() => {
    const s = new Set<string>();
    rows.forEach((r) => {
      if (r.parent_chain_id) s.add(r.parent_chain_id);
    });
    return Array.from(s).sort();
  }, [rows]);

  const filtered = useMemo(() => {
    let out = rows;
    if (chain !== "__all__") out = out.filter((r) => r.parent_chain_id === chain);
    if (q.trim()) {
      const s = q.toLowerCase();
      out = out.filter((r) => JSON.stringify(r).toLowerCase().includes(s));
    }
    return out;
  }, [chain, q, rows]);

  const cols: ColumnDef<L2Statement>[] = [
    { key: "statement_id", title: "stmt_id", readonly: true, width: "120px" },
    { key: "parent_chain_id", title: "parent_chain", width: "140px" },
    { key: "subject", title: "subject" },
    { key: "predicate", title: "predicate", width: "180px" },
    { key: "object", title: "object" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2">
          <span className="text-[11px] text-[var(--vs-fg-muted)]">
            {t("dp.chain_filter")}:
          </span>
          <select
            className="vs-input w-[180px]"
            value={chain}
            onChange={(e) => setChain(e.target.value)}
          >
            <option value="__all__">{t("common.all")}</option>
            {chainIds.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <input
          className="vs-input max-w-[360px]"
          placeholder={t("common.search")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <EditableTable<L2Statement>
        columns={cols}
        rows={filtered}
        onChange={(next) => {
          onUpdate(reconcileFiltered(rows, filtered, next));
        }}
        emptyTemplate={{
          parent_chain_id: chain === "__all__" ? (chainIds[0] ?? "") : chain,
          subject: "",
          predicate: "",
          object: "",
        }}
        addLabel={t("dp.add_row")}
      />
    </div>
  );
}

function L3View({
  core,
  onUpdate,
}: {
  core: KnowledgeCore;
  onUpdate: (rows: L3Chain[]) => void;
}) {
  const { t } = useI18n();
  const rows = core.l3_chains ?? [];
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) =>
      JSON.stringify(r).toLowerCase().includes(s)
    );
  }, [q, rows]);

  // Transform steps[] <-> steps_text in EditableTable via renderValue/parseValue
  const cols: ColumnDef<L3Chain>[] = [
    { key: "chain_id", title: "chain_id", readonly: true, width: "120px" },
    { key: "domain_context", title: "domain", width: "160px" },
    { key: "process_name", title: "process_name", width: "200px" },
    { key: "narrative_summary", title: "narrative_summary", type: "textarea" },
    {
      key: "steps",
      title: "steps (one per line)",
      type: "textarea",
      renderValue: (v) => (Array.isArray(v) ? v.join("\n") : String(v ?? "")),
      parseValue: (s) =>
        s
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
    },
  ];

  return (
    <div className="space-y-3">
      <input
        className="vs-input max-w-[360px]"
        placeholder={t("common.search")}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <EditableTable<L3Chain>
        columns={cols}
        rows={filtered}
        onChange={(next) => {
          onUpdate(reconcileFiltered(rows, filtered, next));
        }}
        emptyTemplate={{
          domain_context: "",
          process_name: "",
          narrative_summary: "",
          steps: [],
        }}
        addLabel={t("dp.add_row")}
      />
    </div>
  );
}

function ExportView({ core }: { core: KnowledgeCore }) {
  const { t } = useI18n();
  const jsonStr = useMemo(() => JSON.stringify(core, null, 2), [core]);

  const handleDownload = () => {
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "knowledge_core.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-3">
      <button
        onClick={handleDownload}
        className="vs-btn flex items-center gap-2"
      >
        <Download size={14} />
        {t("dp.download_json")}
      </button>
      <div className="flex items-center gap-2 text-[11px] text-[var(--vs-fg-muted)]">
        <FileJson size={12} />
        <span>Preview (read-only)</span>
      </div>
      <pre className="vs-card p-4 font-mono text-[12px] leading-[1.6] text-[var(--vs-fg)] overflow-auto max-h-[420px] whitespace-pre">
{jsonStr}
      </pre>
    </div>
  );
}
