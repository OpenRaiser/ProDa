import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import {
  Activity,
  Archive,
  BarChart3,
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  Clipboard,
  Copy,
  Download,
  FileCode2,
  FileJson,
  FileText,
  Folder,
  FolderOpen,
  GitMerge,
  Loader2,
  Package,
  RefreshCw,
  ScrollText,
  Sparkles,
  Stethoscope,
  X,
} from "lucide-react";
import clsx from "clsx";
import Editor from "@monaco-editor/react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/hooks/useToast";
import { usePageLabels } from "@/hooks/usePageLabels";
import {
  downloadExportBundle,
  getArtifact,
  getDashboard,
} from "@/api/dashboard";
import type {
  ArtifactFile,
  ArtifactNode,
  FineTuneSection,
  PageId,
  ProjectDashboard,
  TimelineEvent,
  TimelineKind,
} from "@/types";

const KIND_META: Record<
  TimelineKind,
  { icon: typeof Sparkles; color: string; label: string }
> = {
  train: { icon: Sparkles, color: "#c586c0", label: "train" },
  eval: { icon: BarChart3, color: "var(--vs-accent)", label: "eval" },
  diag: { icon: Stethoscope, color: "#dcb67a", label: "diag" },
  supplement: { icon: Package, color: "#4ec9b0", label: "supp" },
  merge: { icon: GitMerge, color: "var(--vs-fg-muted)", label: "merge" },
};

const STATUS_COLOR: Record<string, string> = {
  running: "var(--vs-accent)",
  finished: "#4ec9b0",
  stopped_or_failed: "#f48771",
  info: "var(--vs-fg-muted)",
};

export function Results() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const toast = useToast();
  const project = useSession((s) => s.currentProject);
  const openTab = useSession((s) => s.openTab);
  const setFinetuneSection = useSession((s) => s.setFinetuneSection);
  const setPreselectedEvalRunId = useSession((s) => s.setPreselectedEvalRunId);
  const setPreselectedTrainSessionId = useSession(
    (s) => s.setPreselectedTrainSessionId
  );
  const pushRecentArtifact = useSession((s) => s.pushRecentArtifact);
  const preselectedArtifactPath = useSession((s) => s.preselectedArtifactPath);
  const setPreselectedArtifactPath = useSession(
    (s) => s.setPreselectedArtifactPath
  );

  const [data, setData] = useState<ProjectDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [timelineFilter, setTimelineFilter] = useState<"all" | TimelineKind>(
    "all"
  );
  const [timelineQuery, setTimelineQuery] = useState("");
  const [previewPath, setPreviewPath] = useState<string>("");
  const [previewFile, setPreviewFile] = useState<ArtifactFile | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [bundleDownloading, setBundleDownloading] = useState(false);

  const refresh = useCallback(async () => {
    if (!project) return;
    setLoading(true);
    try {
      const d = await getDashboard(project.id);
      setData(d);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filteredTimeline = useMemo(() => {
    const list = data?.timeline ?? [];
    const q = timelineQuery.trim().toLowerCase();
    return list.filter((e) => {
      if (timelineFilter !== "all" && e.kind !== timelineFilter) return false;
      if (q && !JSON.stringify(e).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [data, timelineFilter, timelineQuery]);

  const handleTimelineClick = (e: TimelineEvent) => {
    const target = e.target;
    if (!target) return;
    const page = target.page as PageId | undefined;
    if (!page) return;
    if (page === "opencompass" && target.run_id) {
      setPreselectedEvalRunId(target.run_id);
    }
    if (page === "fine_tuning" && target.session_id) {
      setPreselectedTrainSessionId(target.session_id);
    }
    if (page === "finetune" && target.finetune_section) {
      setFinetuneSection(target.finetune_section as FineTuneSection);
    }
    openTab(buildTab(page));
  };

  const handlePreview = useCallback(
    async (node: ArtifactNode) => {
      if (!project) return;
      if (node.kind === "dir") return;
      setPreviewPath(node.relative);
      setPreviewLoading(true);
      try {
        const f = await getArtifact(project.id, node.relative);
        setPreviewFile(f);
        // Track for Ctrl+P "Recent" picker
        pushRecentArtifact({
          path: node.relative,
          projectId: project.id,
          label: node.name,
          hint: node.relative.includes("/")
            ? node.relative.slice(0, node.relative.lastIndexOf("/"))
            : "",
        });
      } catch (err: unknown) {
        const e = err as { message?: string };
        setPreviewFile({
          name: node.name,
          relative: node.relative,
          kind: "file",
          size: node.size,
          mtime: node.mtime,
          suffix: node.suffix ?? "",
          is_text: false,
          mime: node.mime ?? "",
          text: null,
          reason: e?.message ?? "load failed",
        });
      } finally {
        setPreviewLoading(false);
      }
    },
    [project, pushRecentArtifact]
  );

  // When user picks a recent artifact from Ctrl+P, open it automatically on mount.
  useEffect(() => {
    if (!preselectedArtifactPath || !project) return;
    // Build a minimal node stub and reuse handlePreview
    const path = preselectedArtifactPath;
    setPreselectedArtifactPath(null);
    const baseName = path.split(/[\\/]/).pop() || path;
    const suffix = baseName.includes(".")
      ? `.${baseName.split(".").pop()}`
      : "";
    handlePreview({
      name: baseName,
      kind: "file",
      relative: path,
      size: 0,
      mtime: 0,
      suffix,
      is_text: true,
      mime: "",
    } as ArtifactNode);
  }, [preselectedArtifactPath, project, handlePreview, setPreselectedArtifactPath]);

  const handleExportBundle = async () => {
    if (!project) return;
    setBundleDownloading(true);
    try {
      await downloadExportBundle(project.id, null);
      toast.success(t("results.export_done"));
    } catch (e: unknown) {
      const err = e as { message?: string };
      toast.error(t("results.export_failed"), {
        description: err?.message ?? "",
      });
    } finally {
      setBundleDownloading(false);
    }
  };

  const summary = data?.summary;
  const best = summary?.evaluation.best_accuracy;
  const summaryChips: Array<{ icon: typeof Sparkles; label: string; value: string }> =
    summary
      ? [
          {
            icon: FileText,
            label: "KC",
            value: `L1 ${summary.kc.l1} · L2 ${summary.kc.l2} · L3 ${summary.kc.l3}`,
          },
          {
            icon: FileJson,
            label: "MCQ",
            value: String(summary.benchmark.count),
          },
          {
            icon: Clipboard,
            label: "FT",
            value: `${summary.finetune.count}${
              summary.flow?.merged_ready ? " (merged ✓)" : ""
            }`,
          },
          {
            icon: Sparkles,
            label: "Train",
            value: `${summary.training.finished}/${summary.training.total}`,
          },
          {
            icon: BarChart3,
            label: "Eval",
            value: `${summary.evaluation.finished}/${summary.evaluation.total}${
              best !== null && best !== undefined
                ? ` · best ${best.toFixed(1)}%`
                : ""
            }`,
          },
        ]
      : [];

  return (
    <div className="h-full w-full flex flex-col bg-[var(--vs-bg)]">
      {/* Top summary bar */}
      <div className="h-[30px] shrink-0 flex items-center gap-3 px-4 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] text-[12px]">
        <span className="text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] font-semibold">
          workspace
        </span>
        {loading ? (
          <Loader2 size={12} className="animate-spin text-[var(--vs-fg-muted)]" />
        ) : (
          <div className="flex items-center gap-4 overflow-hidden">
            {summaryChips.map((c, i) => (
              <span
                key={i}
                className="flex items-center gap-1.5 text-[11px] text-[var(--vs-fg)] font-mono whitespace-nowrap"
              >
                <c.icon size={11} className="text-[var(--vs-fg-muted)]" />
                <span className="text-[var(--vs-fg-muted)]">{c.label}</span>
                {c.value}
              </span>
            ))}
          </div>
        )}
        <button
          className="ml-auto vs-btn-ghost px-2 h-[22px] flex items-center gap-1 text-[11px]"
          onClick={refresh}
          disabled={loading}
        >
          <RefreshCw size={11} />
          {t("common.refresh")}
        </button>
        <button
          className="vs-btn-ghost px-2 h-[22px] flex items-center gap-1 text-[11px]"
          onClick={handleExportBundle}
          disabled={bundleDownloading || !data}
        >
          {bundleDownloading ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <Archive size={11} />
          )}
          {t("results.export_bundle")}
        </button>
      </div>

      {/* Main 2-pane split */}
      <div className="flex-1 min-h-0">
        <PanelGroup direction="horizontal" autoSaveId="pro-ide-results">
          <Panel defaultSize={50} minSize={28}>
            <TimelinePanel
              events={filteredTimeline}
              totalEvents={data?.timeline.length ?? 0}
              filter={timelineFilter}
              query={timelineQuery}
              onFilter={setTimelineFilter}
              onQuery={setTimelineQuery}
              onPick={handleTimelineClick}
              flow={summary?.flow ?? {}}
            />
          </Panel>
          <PanelResizeHandle className="w-[1px] bg-[var(--vs-sidebar)] hover:bg-[var(--vs-statusbar)] transition-colors" />
          <Panel defaultSize={50} minSize={28}>
            <ArtifactsPanel
              root={data?.artifacts}
              onPreview={handlePreview}
              onDownload={(node) => {
                if (!project) return;
                const link = document.createElement("a");
                link.href = `/api/dashboard/${project.id}/artifact?path=${encodeURIComponent(
                  node.relative
                )}`;
                link.download = node.name;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }}
              selectedPath={previewPath}
            />
          </Panel>
        </PanelGroup>
      </div>

      {previewFile && (
        <ArtifactModal
          file={previewFile}
          loading={previewLoading}
          onClose={() => {
            setPreviewFile(null);
            setPreviewPath("");
          }}
        />
      )}
    </div>
  );
}

// =============== Timeline ===============

function TimelinePanel({
  events,
  totalEvents,
  filter,
  query,
  onFilter,
  onQuery,
  onPick,
  flow,
}: {
  events: TimelineEvent[];
  totalEvents: number;
  filter: "all" | TimelineKind;
  query: string;
  onFilter: (v: "all" | TimelineKind) => void;
  onQuery: (v: string) => void;
  onPick: (e: TimelineEvent) => void;
  flow: Record<string, unknown>;
}) {
  const { t } = useI18n();
  const activeTraining = useSession((s) => s.activeTrainingSession);
  const activeEval = useSession((s) => s.activeEvalSession);

  return (
    <div className="h-full flex flex-col bg-[var(--vs-bg)] overflow-hidden">
      <div className="h-[30px] flex items-center gap-2 px-3 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] shrink-0">
        <Activity size={12} className="text-[var(--vs-accent)]" />
        <span className="text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] font-semibold">
          {t("results.timeline_title")}
        </span>
        <span className="text-[10px] text-[var(--vs-fg-subtle)] font-mono">
          {events.length} / {totalEvents}
        </span>
      </div>

      {/* Filters */}
      <div className="px-3 py-2 border-b border-[var(--vs-border)] flex items-center gap-2 flex-wrap shrink-0">
        <select
          className="vs-input h-[24px] py-0 text-[11px] w-[100px]"
          value={filter}
          onChange={(e) => onFilter(e.target.value as typeof filter)}
        >
          <option value="all">{t("results.filter_all")}</option>
          {(["train", "eval", "diag", "supplement", "merge"] as TimelineKind[]).map(
            (k) => (
              <option key={k} value={k}>
                {KIND_META[k].label}
              </option>
            )
          )}
        </select>
        <input
          className="vs-input h-[24px] py-0 text-[11px] flex-1 min-w-[120px]"
          placeholder={t("results.timeline_search_ph")}
          value={query}
          onChange={(e) => onQuery(e.target.value)}
        />
      </div>

      <div className="flex-1 overflow-auto">
        {/* Live indicators for any active job */}
        {(activeTraining?.alive || activeEval?.alive) && (
          <div className="px-3 py-2 border-b border-[var(--vs-border)] bg-[color:var(--vs-sidebar)]/50 space-y-1">
            {activeTraining?.alive && (
              <LiveRow
                icon={Sparkles}
                color="#c586c0"
                label="training"
                text={`${activeTraining.dataset_name ?? "?"} → ${
                  activeTraining.model_tag ?? "?"
                }`}
              />
            )}
            {activeEval?.alive && (
              <LiveRow
                icon={BarChart3}
                color="var(--vs-accent)"
                label="evaluating"
                text={`run ${activeEval.run_id}`}
              />
            )}
          </div>
        )}

        {events.length === 0 ? (
          <div className="p-4 text-[12px] text-[var(--vs-fg-muted)] italic">
            {t("results.timeline_empty")}
          </div>
        ) : (
          <div className="relative pl-8 pr-3 py-2">
            {/* vertical connector line */}
            <div className="absolute left-[18px] top-0 bottom-0 w-[1px] bg-[var(--vs-border)]" />
            {events.map((e) => (
              <TimelineRow key={e.id} event={e} onPick={onPick} />
            ))}
          </div>
        )}

        {flow && Object.keys(flow).length > 0 && (
          <div className="mx-3 my-3 vs-card p-3">
            <div className="vs-panel-title mb-2">{t("results.flow_state_title")}</div>
            <div className="text-[11px] font-mono text-[var(--vs-fg)] space-y-0.5">
              {flow.merged_ready ? (
                <div className="flex items-center gap-2">
                  <Circle size={8} className="text-[#4ec9b0] fill-[#4ec9b0]" />
                  merged_ready · {String(flow.merged_rows ?? "?")} rows
                </div>
              ) : null}
              {flow.last_trained_model_dir ? (
                <div className="flex items-center gap-2 truncate">
                  <Circle size={8} className="text-[#c586c0] fill-[#c586c0]" />
                  last_train: {String(flow.last_trained_model_dir)}
                </div>
              ) : null}
              {flow.last_training_outcome ? (
                <div className="flex items-center gap-2 text-[var(--vs-fg-muted)]">
                  <Circle size={8} className="text-[var(--vs-fg-muted)]" />
                  last_outcome: {String(flow.last_training_outcome)}
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function LiveRow({
  icon: Icon,
  color,
  label,
  text,
}: {
  icon: typeof Sparkles;
  color: string;
  label: string;
  text: string;
}) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span
        className="w-[6px] h-[6px] rounded-full animate-pulse shrink-0"
        style={{ backgroundColor: color }}
      />
      <Icon size={11} style={{ color }} className="shrink-0" />
      <span className="uppercase tracking-wider text-[10px]" style={{ color }}>
        {label}
      </span>
      <span className="truncate font-mono text-[var(--vs-fg)]">{text}</span>
    </div>
  );
}

function TimelineRow({
  event,
  onPick,
}: {
  event: TimelineEvent;
  onPick: (e: TimelineEvent) => void;
}) {
  const meta = KIND_META[event.kind] ?? {
    icon: Circle,
    color: "var(--vs-fg-muted)",
    label: event.kind,
  };
  const StatusIcon = meta.icon;
  const statusColor = STATUS_COLOR[event.status] ?? "var(--vs-fg-muted)";
  const when = event.timestamp
    ? new Date(event.timestamp * 1000).toISOString().slice(0, 19).replace("T", " ")
    : "—";

  return (
    <div
      className="group relative -ml-[22px] pl-[22px] py-[6px] cursor-pointer hover:bg-[var(--vs-hover)] rounded-sm"
      onClick={() => onPick(event)}
    >
      {/* node dot */}
      <div
        className="absolute left-[12px] top-[12px] w-[12px] h-[12px] rounded-full border-2 bg-[var(--vs-bg)]"
        style={{ borderColor: meta.color }}
      />
      <div className="flex items-start gap-2 text-[12px]">
        <StatusIcon size={12} style={{ color: meta.color }} className="mt-[2px] shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider font-semibold"
                  style={{ color: meta.color }}>
              {meta.label}
            </span>
            <span
              className="text-[10px] px-1 rounded-sm font-mono"
              style={{
                color: statusColor,
                border: `1px solid ${statusColor}55`,
                backgroundColor: `${statusColor}11`,
              }}
            >
              {event.status}
            </span>
            <span className="text-[10px] text-[var(--vs-fg-subtle)] font-mono ml-auto shrink-0">
              {when}
            </span>
          </div>
          <div className="text-[12px] text-[var(--vs-fg)] truncate mt-0.5">
            {event.title}
          </div>
        </div>
      </div>
    </div>
  );
}

// =============== Artifacts tree ===============

function ArtifactsPanel({
  root,
  onPreview,
  onDownload,
  selectedPath,
}: {
  root: ArtifactNode | undefined;
  onPreview: (node: ArtifactNode) => void;
  onDownload: (node: ArtifactNode) => void;
  selectedPath: string;
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set<string>([""])
  );

  useEffect(() => {
    // Auto-expand top-level dir initially
    if (root && root.kind === "dir" && root.children?.length) {
      setExpanded((prev) => {
        const next = new Set(prev);
        next.add("");
        return next;
      });
    }
  }, [root]);

  const toggle = (rel: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(rel)) next.delete(rel);
      else next.add(rel);
      return next;
    });
  };

  return (
    <div className="h-full flex flex-col bg-[var(--vs-bg)] overflow-hidden">
      <div className="h-[30px] flex items-center gap-2 px-3 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] shrink-0">
        <FolderOpen size={12} className="text-[#dcb67a]" />
        <span className="text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] font-semibold">
          {t("results.artifacts_title")}
        </span>
        <span className="text-[10px] text-[var(--vs-fg-subtle)] font-mono">
          {root && root.kind === "dir" ? `${root.file_count ?? 0} files` : ""}
        </span>
      </div>
      <div className="flex-1 overflow-auto py-1">
        {root ? (
          <ArtifactTreeNode
            node={root}
            depth={0}
            expanded={expanded}
            onToggle={toggle}
            onPreview={onPreview}
            onDownload={onDownload}
            selectedPath={selectedPath}
          />
        ) : (
          <div className="p-4 text-[12px] text-[var(--vs-fg-muted)] italic">
            {t("common.loading")}
          </div>
        )}
      </div>
    </div>
  );
}

function humanBytes(n: number): string {
  if (!n) return "0B";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u += 1;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)}${units[u]}`;
}

function fileIconFor(name: string, suffix: string | undefined) {
  const lc = (suffix || name.split(".").pop() || "").toLowerCase();
  if (lc === "json" || lc === "jsonl") return { Icon: FileJson, color: "#cbcb41" };
  if (lc === "yaml" || lc === "yml") return { Icon: FileText, color: "#cbcb41" };
  if (lc === "py") return { Icon: FileCode2, color: "#519aba" };
  if (lc === "log" || lc === "txt") return { Icon: ScrollText, color: "var(--vs-fg-muted)" };
  return { Icon: FileText, color: "var(--vs-fg-muted)" };
}

function ArtifactTreeNode({
  node,
  depth,
  expanded,
  onToggle,
  onPreview,
  onDownload,
  selectedPath,
}: {
  node: ArtifactNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (rel: string) => void;
  onPreview: (node: ArtifactNode) => void;
  onDownload: (node: ArtifactNode) => void;
  selectedPath: string;
}) {
  const [copied, setCopied] = useState(false);
  const isDir = node.kind === "dir";
  const isOpen = isDir && expanded.has(node.relative);
  const isSelected = !isDir && node.relative === selectedPath;
  const { Icon, color } = isDir
    ? { Icon: isOpen ? FolderOpen : Folder, color: "#dcb67a" }
    : fileIconFor(node.name, node.suffix);
  const indent = 8 + depth * 14;

  const handleCopyPath = (e: React.MouseEvent) => {
    e.stopPropagation();
    const value = node.relative || node.name;
    try {
      navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore — older browsers */
    }
  };

  return (
    <>
      <div
        className={clsx(
          "group flex items-center gap-1 pr-2 h-[22px] cursor-pointer select-none hover:bg-[var(--vs-hover)]",
          isSelected &&
            "bg-[var(--vs-hover)] ring-1 ring-inset ring-[var(--vs-accent)]"
        )}
        style={{ paddingLeft: indent }}
        onClick={() => {
          if (isDir) onToggle(node.relative);
          else onPreview(node);
        }}
      >
        {isDir ? (
          isOpen ? (
            <ChevronDown size={11} className="text-[var(--vs-fg-muted)] shrink-0" />
          ) : (
            <ChevronRight size={11} className="text-[var(--vs-fg-muted)] shrink-0" />
          )
        ) : (
          <span className="w-[11px] shrink-0" />
        )}
        <Icon size={13} style={{ color }} className="shrink-0" />
        <span className="truncate text-[12px] text-[var(--vs-fg)] flex-1">
          {node.name}
        </span>
        <span className="text-[10px] text-[var(--vs-fg-subtle)] font-mono shrink-0">
          {isDir
            ? node.file_count
              ? `${node.file_count} · ${humanBytes(node.size)}`
              : ""
            : humanBytes(node.size)}
        </span>
        <button
          className="opacity-0 group-hover:opacity-100 p-0.5 text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg-strong)] shrink-0"
          onClick={handleCopyPath}
          title={copied ? "copied" : "copy relative path"}
        >
          {copied ? (
            <Check size={11} className="text-[#4ec9b0]" />
          ) : (
            <Copy size={11} />
          )}
        </button>
        {!isDir && (
          <button
            className="opacity-0 group-hover:opacity-100 p-0.5 text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg-strong)] shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              onDownload(node);
            }}
            title="Download"
          >
            <Download size={11} />
          </button>
        )}
      </div>
      {isDir && isOpen && node.children && (
        <>
          {node.children.map((child) => (
            <ArtifactTreeNode
              key={child.relative}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onPreview={onPreview}
              onDownload={onDownload}
              selectedPath={selectedPath}
            />
          ))}
        </>
      )}
    </>
  );
}

// =============== Monaco preview modal ===============

function languageFor(suffix: string | undefined): string {
  const s = (suffix || "").toLowerCase().replace(".", "");
  if (s === "json" || s === "jsonl") return "json";
  if (s === "yaml" || s === "yml") return "yaml";
  if (s === "py") return "python";
  if (s === "md") return "markdown";
  return "plaintext";
}

function ArtifactModal({
  file,
  loading,
  onClose,
}: {
  file: ArtifactFile;
  loading: boolean;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === containerRef.current) onClose();
      }}
    >
      <div
        ref={containerRef}
        className="absolute inset-0 flex items-center justify-center"
      >
        <div className="w-[min(1100px,calc(100vw-48px))] h-[min(720px,calc(100vh-48px))] vs-card overflow-hidden flex flex-col shadow-2xl">
          <div className="h-[32px] flex items-center px-3 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] shrink-0">
            <FileJson size={13} className="text-[#cbcb41] mr-2" />
            <span className="text-[12px] text-[var(--vs-fg)] font-mono truncate">
              {file.relative}
            </span>
            <span className="ml-2 text-[10px] text-[var(--vs-fg-subtle)] font-mono">
              {humanBytes(file.size)}
              {file.mime && ` · ${file.mime}`}
            </span>
            <button
              className="ml-auto text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg-strong)]"
              onClick={onClose}
            >
              <X size={14} />
            </button>
          </div>
          <div className="flex-1 min-h-0">
            {loading ? (
              <div className="h-full flex items-center justify-center text-[var(--vs-fg-muted)] text-[12px]">
                <Loader2 size={13} className="animate-spin mr-2" />
                {t("common.loading")}
              </div>
            ) : file.text !== null ? (
              <Editor
                value={file.text}
                language={languageFor(file.suffix)}
                theme="vs-dark"
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 12,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  folding: true,
                }}
              />
            ) : (
              <div className="h-full flex items-center justify-center flex-col gap-2 text-[12px] text-[var(--vs-fg-muted)]">
                <Package size={22} />
                <div>{file.reason ?? t("results.preview_binary")}</div>
                <div className="font-mono text-[11px] text-[var(--vs-fg-subtle)]">
                  {file.relative}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
