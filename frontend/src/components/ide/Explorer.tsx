import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  FolderOpen,
  Folder,
  Plus,
  RefreshCw,
  Settings2,
} from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { WORKFLOW_STEPS } from "@/lib/workflow";
import { usePageLabels } from "@/hooks/usePageLabels";
import { listProjects, openProject } from "@/api/projects";
import type { FineTuneSection, Project } from "@/types";

const FINETUNE_CHILDREN: Array<{
  id: FineTuneSection;
  file: string;
  labelKey: string;
}> = [
  { id: "generate", file: "generate.py", labelKey: "ft.seg_generate" },
  { id: "diagnose", file: "diagnose.py", labelKey: "ft.seg_diagnose" },
  { id: "supplement", file: "supplement.py", labelKey: "ft.seg_supplement" },
  { id: "merge", file: "merge.py", labelKey: "ft.seg_merge" },
];

function SectionHeader({
  title,
  actions,
  open,
  onToggle,
}: {
  title: string;
  actions?: React.ReactNode;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className="group flex items-center justify-between pl-2 pr-1 h-[22px] cursor-pointer select-none hover:bg-[var(--vs-hover)]"
      onClick={onToggle}
    >
      <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] font-semibold">
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {title}
      </div>
      <div className="flex items-center opacity-0 group-hover:opacity-100">
        {actions}
      </div>
    </div>
  );
}

export function Explorer() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const currentProject = useSession((s) => s.currentProject);
  const setCurrentProject = useSession((s) => s.setCurrentProject);
  const projects = useSession((s) => s.projects);
  const setProjects = useSession((s) => s.setProjects);
  const openTab = useSession((s) => s.openTab);
  const activeTabId = useSession((s) => s.activeTabId);
  const setActivityView = useSession((s) => s.setActivityView);
  const activityView = useSession((s) => s.activityView);
  const closeAllTabs = useSession((s) => s.closeAllTabs);

  const [projectOpen, setProjectOpen] = useState(true);
  const [workflowOpen, setWorkflowOpen] = useState(true);
  const [recentOpen, setRecentOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [finetuneExpanded, setFinetuneExpanded] = useState(true);
  const [fineTuningExpanded, setFineTuningExpanded] = useState(true);
  const [openCompassExpanded, setOpenCompassExpanded] = useState(true);
  const finetuneSection = useSession((s) => s.finetuneSection);
  const setFinetuneSection = useSession((s) => s.setFinetuneSection);
  const activeTraining = useSession((s) => s.activeTrainingSession);
  const setTrainingPanelTab = useSession((s) => s.setTrainingPanelTab);
  const activeEval = useSession((s) => s.activeEvalSession);
  const setEvalPanelTab = useSession((s) => s.setEvalPanelTab);

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await listProjects();
      setProjects(res.projects);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const title =
    activityView === "workflow"
      ? t("activity.workflow")
      : t("explorer.title");

  return (
    <div
      className="w-full h-full text-[var(--vs-fg)] flex flex-col overflow-hidden"
      style={{ backgroundColor: "var(--vs-sidebar)" }}
    >
      {/* Panel title */}
      <div className="h-[35px] flex items-center justify-between pl-5 pr-2 text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] font-semibold">
        <span>{title}</span>
        <div className="flex items-center gap-1">
          <button
            className="p-1 hover:bg-[var(--vs-hover)] rounded-sm"
            title={t("explorer.new_project")}
            onClick={() => openTab(buildTab("welcome"))}
          >
            <Plus size={14} />
          </button>
          <button
            className="p-1 hover:bg-[var(--vs-hover)] rounded-sm"
            title={t("explorer.refresh")}
            onClick={refresh}
          >
            <RefreshCw
              size={14}
              className={clsx(loading && "animate-spin")}
            />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {/* Current project */}
        <SectionHeader
          title={t("explorer.current_project")}
          open={projectOpen}
          onToggle={() => setProjectOpen(!projectOpen)}
          actions={
            currentProject && (
              <button
                className="p-[2px] hover:bg-[var(--vs-selected)] hover:text-white rounded-sm"
                title={t("explorer.close_current")}
                onClick={(e) => {
                  e.stopPropagation();
                  setCurrentProject(null);
                  closeAllTabs();
                }}
              >
                <Settings2 size={12} />
              </button>
            )
          }
        />
        {projectOpen && (
          <div className="pb-1">
            {currentProject ? (
              <div className="pl-4">
                <div className="vs-tree-item">
                  <FolderOpen
                    size={14}
                    className="text-[#dcb67a] shrink-0"
                  />
                  <span className="truncate">{currentProject.name}</span>
                </div>
                <div className="pl-4">
                  <div
                    className={clsx(
                      "vs-tree-item",
                      activeTabId === "welcome" && "vs-tree-item-active"
                    )}
                    onClick={() => openTab(buildTab("welcome"))}
                  >
                    <FileText
                      size={14}
                      className="text-[#519aba] shrink-0"
                    />
                    <span>welcome.md</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="pl-6 py-1 text-[12px] text-[var(--vs-fg-muted)] italic">
                {t("explorer.no_project")}
              </div>
            )}
          </div>
        )}

        <div className="vs-divider my-1" />

        {/* Workflow */}
        <SectionHeader
          title={t("explorer.workflow")}
          open={workflowOpen}
          onToggle={() => setWorkflowOpen(!workflowOpen)}
        />
        {workflowOpen && (
          <div className="pl-4 pb-2">
            {WORKFLOW_STEPS.map((step) => {
              const active = activeTabId === step.id;
              const isFinetune = step.id === "finetune";
              const isFineTuning = step.id === "fine_tuning";
              const isOpenCompass = step.id === "opencompass";
              const showExpander =
                isFinetune ||
                (isFineTuning && !!activeTraining) ||
                (isOpenCompass && !!activeEval);
              const expanded = isFinetune
                ? finetuneExpanded
                : isFineTuning
                ? fineTuningExpanded
                : isOpenCompass
                ? openCompassExpanded
                : false;
              const toggleExpanded = isFinetune
                ? () => setFinetuneExpanded((v) => !v)
                : isFineTuning
                ? () => setFineTuningExpanded((v) => !v)
                : isOpenCompass
                ? () => setOpenCompassExpanded((v) => !v)
                : () => {};
              return (
                <div key={step.id}>
                  <div
                    className={clsx(
                      "vs-tree-item",
                      active && "vs-tree-item-active",
                      !currentProject && "opacity-50 cursor-not-allowed"
                    )}
                    title={t(step.key)}
                    onClick={() => {
                      if (!currentProject) return;
                      openTab(buildTab(step.id));
                    }}
                  >
                    {showExpander ? (
                      <button
                        type="button"
                        className="p-0 m-0 bg-transparent border-0 text-current shrink-0 hover:text-[var(--vs-fg-strong)]"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpanded();
                        }}
                        title={expanded ? t("explorer.collapse") : t("explorer.expand")}
                      >
                        {expanded ? (
                          <ChevronDown size={12} />
                        ) : (
                          <ChevronRight size={12} />
                        )}
                      </button>
                    ) : (
                      <span className="w-[12px] shrink-0" />
                    )}
                    <FileCode2 size={14} className="text-[#519aba] shrink-0" />
                    <span className="truncate flex-1">{t(step.key)}</span>
                    {isFineTuning && activeTraining?.alive && (
                      <span
                        className="w-[6px] h-[6px] rounded-full bg-[#c586c0] animate-pulse"
                        title={t("ftune.explorer_active")}
                      />
                    )}
                    {isOpenCompass && activeEval?.alive && (
                      <span
                        className="w-[6px] h-[6px] rounded-full bg-[var(--vs-accent)] animate-pulse"
                        title={t("oc.explorer_active")}
                      />
                    )}
                  </div>
                  {isFinetune && finetuneExpanded && (
                    <div className="pl-4">
                      {FINETUNE_CHILDREN.map((child) => {
                        const childActive =
                          activeTabId === "finetune" &&
                          finetuneSection === child.id;
                        return (
                          <div
                            key={child.id}
                            className={clsx(
                              "vs-tree-item",
                              childActive && "vs-tree-item-active",
                              !currentProject && "opacity-50 cursor-not-allowed"
                            )}
                            onClick={() => {
                              if (!currentProject) return;
                              setFinetuneSection(child.id);
                              openTab(buildTab("finetune"));
                            }}
                            title={t(child.labelKey)}
                          >
                            <FileCode2
                              size={13}
                              className="text-[#6e9fd2] shrink-0"
                            />
                            <span className="truncate">{t(child.labelKey)}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {isFineTuning && fineTuningExpanded && activeTraining && (
                    <div className="pl-4">
                      <div
                        className="vs-tree-item"
                        title={activeTraining.cfg_path}
                        onClick={() => {
                          if (!currentProject) return;
                          openTab(buildTab("fine_tuning"));
                        }}
                      >
                        <FileText size={13} className="text-[#cbcb41] shrink-0" />
                        <span className="truncate">train_config.yaml</span>
                      </div>
                      <div
                        className="vs-tree-item"
                        title={activeTraining.log_path}
                        onClick={() => {
                          if (!currentProject) return;
                          openTab(buildTab("fine_tuning"));
                          setTrainingPanelTab("log");
                        }}
                      >
                        <FileText size={13} className="text-[var(--vs-fg-muted)] shrink-0" />
                        <span className="truncate">training.log</span>
                        {activeTraining.alive && (
                          <span className="w-[6px] h-[6px] rounded-full bg-[#c586c0] animate-pulse ml-auto" />
                        )}
                      </div>
                      <div
                        className="vs-tree-item"
                        title={activeTraining.output_dir}
                        onClick={() => {
                          if (!currentProject) return;
                          openTab(buildTab("fine_tuning"));
                        }}
                      >
                        <Folder size={13} className="text-[#dcb67a] shrink-0" />
                        <span className="truncate">
                          {activeTraining.model_tag ?? "output"}/
                        </span>
                      </div>
                    </div>
                  )}
                  {isOpenCompass && openCompassExpanded && activeEval && (
                    <div className="pl-4">
                      <div
                        className="vs-tree-item"
                        title={activeEval.cfg_path}
                        onClick={() => {
                          if (!currentProject) return;
                          openTab(buildTab("opencompass"));
                        }}
                      >
                        <FileText size={13} className="text-[#cbcb41] shrink-0" />
                        <span className="truncate">eval_config.py</span>
                      </div>
                      <div
                        className="vs-tree-item"
                        title={activeEval.log_path}
                        onClick={() => {
                          if (!currentProject) return;
                          openTab(buildTab("opencompass"));
                          setEvalPanelTab("log");
                        }}
                      >
                        <FileText size={13} className="text-[var(--vs-fg-muted)] shrink-0" />
                        <span className="truncate">eval.log</span>
                        {activeEval.alive && (
                          <span className="w-[6px] h-[6px] rounded-full bg-[var(--vs-accent)] animate-pulse ml-auto" />
                        )}
                      </div>
                      <div
                        className="vs-tree-item"
                        title={activeEval.work_dir}
                        onClick={() => {
                          if (!currentProject) return;
                          openTab(buildTab("opencompass"));
                        }}
                      >
                        <Folder size={13} className="text-[#dcb67a] shrink-0" />
                        <span className="truncate">
                          runs/{activeEval.run_id}/
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            <div
              className={clsx(
                "vs-tree-item",
                activeTabId === "llm_config" && "vs-tree-item-active"
              )}
              onClick={() => openTab(buildTab("llm_config"))}
            >
              <span className="w-[12px] shrink-0" />
              <FileText size={14} className="text-[#cbcb41] shrink-0" />
              <span>settings.json</span>
            </div>
          </div>
        )}

        <div className="vs-divider my-1" />

        {/* Recent projects */}
        <SectionHeader
          title={t("welcome.recent")}
          open={recentOpen}
          onToggle={() => setRecentOpen(!recentOpen)}
        />
        {recentOpen && (
          <div className="pl-4 pb-4">
            {projects.length === 0 ? (
              <div className="pl-2 py-1 text-[12px] text-[var(--vs-fg-muted)] italic">
                {t("welcome.no_recent")}
              </div>
            ) : (
              projects.slice(0, 10).map((p) => {
                const isCurrent = currentProject?.id === p.id;
                return (
                  <div
                    key={p.id}
                    className={clsx(
                      "vs-tree-item",
                      isCurrent && "vs-tree-item-active"
                    )}
                    onClick={async () => {
                      try {
                        const res = await openProject(p.id);
                        setCurrentProject(res.project);
                      } catch {
                        setCurrentProject(p);
                      }
                      openTab(buildTab("welcome"));
                      refresh();
                    }}
                    title={p.name}
                  >
                    <Folder
                      size={14}
                      className="text-[#dcb67a] shrink-0"
                    />
                    <span className="truncate">{p.name}</span>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
