import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  FolderPlus,
  FolderOpen,
  FileCode2,
  BookOpen,
  Sparkles,
  Trash2,
  ChevronRight,
  Keyboard,
} from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/hooks/useToast";
import { usePageLabels } from "@/hooks/usePageLabels";
import { WORKFLOW_STEPS } from "@/lib/workflow";
import {
  createProject,
  deleteProject,
  listProjects,
  openProject,
} from "@/api/projects";
import type { Project } from "@/types";

export function Welcome() {
  const { t } = useI18n();
  const { buildTab } = usePageLabels();
  const toast = useToast();
  const currentProject = useSession((s) => s.currentProject);
  const setCurrentProject = useSession((s) => s.setCurrentProject);
  const projects = useSession((s) => s.projects);
  const setProjects = useSession((s) => s.setProjects);
  const openTab = useSession((s) => s.openTab);
  const setCommandPaletteOpen = useSession((s) => s.setCommandPaletteOpen);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);
  const closeAllTabs = useSession((s) => s.closeAllTabs);
  const theme = useSession((s) => s.theme);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [createError, setCreateError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const res = await listProjects();
      setProjects(res.projects);
    } catch {
      // ignore
    }
  };
  useEffect(() => {
    refresh();
  }, []);

  const handleCreate = async () => {
    if (!newName.trim()) {
      setCreateError(t("welcome.empty_name"));
      return;
    }
    setBusy(true);
    try {
      const project = await createProject(newName.trim(), newDesc.trim());
      setCurrentProject(project);
      await refresh();
      setNewName("");
      setNewDesc("");
      setShowCreate(false);
      setCreateError("");
    } catch (e: any) {
      setCreateError(e?.message ?? "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const handleOpen = async (p: Project) => {
    setBusy(true);
    try {
      const res = await openProject(p.id);
      setCurrentProject(res.project);
      await refresh();
    } catch {
      setCurrentProject(p);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (p: Project) => {
    if (!confirm(t("welcome.delete_confirm", { name: p.name }))) return;
    setBusy(true);
    try {
      await deleteProject(p.id);
      if (currentProject?.id === p.id) {
        setCurrentProject(null);
        // Close all workflow tabs (they reference the deleted project).
        closeAllTabs();
      }
      await refresh();
    } catch {
      // ignore
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[1100px] mx-auto px-12 py-10">
        {/* Hero */}
        <div className="flex items-center gap-4 mb-2">
          <img
            src={theme === "light-plus" ? "/proda-logo.png" : "/proda-logo-dark.png"}
            alt={t("app.title")}
            className="h-[52px] w-auto rounded-sm"
            draggable={false}
          />
          <div>
            <p className="text-[13px] text-[var(--vs-fg-muted)]">
              {t("welcome.subtitle")}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-10 mt-10">
          {/* Start */}
          <section>
            <h2 className="text-[14px] font-semibold text-[var(--vs-fg-strong)] mb-4 flex items-center gap-2">
              <Sparkles size={16} className="text-[#dcb67a]" />
              {t("welcome.start")}
            </h2>
            <div className="space-y-1">
              <StartLink
                icon={FolderPlus}
                onClick={() => setShowCreate(true)}
                label={t("welcome.new_project")}
              />
              <StartLink
                icon={Keyboard}
                onClick={() => setCommandPaletteOpen(true)}
                label={`${t("command.title")}  (Ctrl+Shift+P)`}
              />
              <StartLink
                icon={BookOpen}
                onClick={() => setConfigModalOpen(true)}
                label={t("titlebar.config")}
              />
            </div>

            {showCreate && (
              <div className="mt-6 vs-card p-4">
                <div className="space-y-3">
                  <div>
                    <label className="vs-label">
                      {t("welcome.create_placeholder")}
                    </label>
                    <input
                      className="vs-input"
                      autoFocus
                      value={newName}
                      placeholder={t("welcome.create_placeholder")}
                      onChange={(e) => setNewName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleCreate();
                      }}
                    />
                  </div>
                  <div>
                    <label className="vs-label">
                      {t("welcome.desc_placeholder")}
                    </label>
                    <textarea
                      className="vs-input min-h-[64px] resize-none"
                      value={newDesc}
                      onChange={(e) => setNewDesc(e.target.value)}
                    />
                  </div>
                  {createError && (
                    <div className="text-[12px] text-[#f48771]">{createError}</div>
                  )}
                  <div className="flex justify-end gap-2">
                    <button
                      className="vs-btn-secondary"
                      onClick={() => {
                        setShowCreate(false);
                        setCreateError("");
                      }}
                    >
                      {t("welcome.cancel")}
                    </button>
                    <button
                      className="vs-btn"
                      disabled={busy}
                      onClick={handleCreate}
                    >
                      {t("welcome.create")}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Recent */}
          <section>
            <h2 className="text-[14px] font-semibold text-[var(--vs-fg-strong)] mb-4 flex items-center gap-2">
              <FolderOpen size={16} className="text-[#dcb67a]" />
              {t("welcome.recent")}
            </h2>
            <div className="space-y-1 max-h-[320px] overflow-auto pr-2">
              {projects.length === 0 ? (
                <div className="text-[13px] text-[var(--vs-fg-muted)] italic">
                  {t("welcome.no_recent")}
                </div>
              ) : (
                projects.slice(0, 12).map((p) => (
                  <div
                    key={p.id}
                    className={clsx(
                      "group flex items-center justify-between px-3 py-2 rounded-sm",
                      "hover:bg-[var(--vs-hover)] cursor-pointer",
                      currentProject?.id === p.id &&
                        "bg-[var(--vs-hover)] ring-1 ring-inset ring-[var(--vs-accent)]"
                    )}
                    onClick={() => handleOpen(p)}
                    title={p.description || p.name}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-[13px] text-[var(--vs-accent)] hover:underline truncate">
                        <FolderOpen size={14} className="shrink-0 text-[#dcb67a]" />
                        <span className="truncate">{p.name}</span>
                      </div>
                      <div className="text-[11px] text-[var(--vs-fg-subtle)] truncate mt-0.5">
                        {p.id} · {String(p.updated_at ?? "").slice(0, 19)}
                      </div>
                    </div>
                    <button
                      className="opacity-0 group-hover:opacity-100 p-1 rounded-sm hover:bg-[var(--vs-border)] text-[var(--vs-fg-muted)] hover:text-[#f48771]"
                      title="Delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(p);
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Walkthrough — clickable shortcuts into each stage. First card
             adapts to whether a project is open (create-first → configure LLM). */}
        <section className="mt-14">
          <h2 className="text-[14px] font-semibold text-[var(--vs-fg-strong)] mb-4 flex items-center gap-2">
            <BookOpen size={16} className="text-[#c586c0]" />
            {t("welcome.walkthrough")}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(() => {
              // If a project is open, step 1 = configure LLM; else step 1 = create project.
              // This unblocks the "can't reach step 2" trap the user hit earlier.
              const firstCard = currentProject
                ? {
                    k: "welcome.walk_1",
                    hint: t("titlebar.config"),
                    onClick: () => setConfigModalOpen(true),
                    needsProject: false,
                  }
                : {
                    k: "welcome.walk_new_project",
                    hint: t("welcome.walk_new_project_hint"),
                    onClick: () => setShowCreate(true),
                    needsProject: false,
                  };
              const cards = [
                firstCard,
                {
                  k: "welcome.walk_2",
                  hint: t("workflow.step1"),
                  onClick: () => openTab(buildTab("data_processing")),
                  needsProject: true,
                },
                {
                  k: "welcome.walk_3",
                  hint: `${t("workflow.step2")} / ${t("workflow.step3")}`,
                  onClick: () => openTab(buildTab("benchmark")),
                  needsProject: true,
                },
                {
                  k: "welcome.walk_4",
                  hint: `${t("workflow.step5")} / ${t("workflow.step6")}`,
                  onClick: () => openTab(buildTab("fine_tuning")),
                  needsProject: true,
                },
              ];
              return cards.map((w, i) => {
                const blocked = w.needsProject && !currentProject;
                const handleClick = () => {
                  if (blocked) {
                    // Guide the user instead of silent failure — open create form
                    // AND surface a toast explaining why.
                    toast.info(t("welcome.walk_need_project"), {
                      description: t("welcome.walk_need_project_desc"),
                    });
                    setShowCreate(true);
                    return;
                  }
                  w.onClick();
                };
                return (
                  <button
                    key={w.k}
                    onClick={handleClick}
                    className={clsx(
                      "vs-card p-4 text-left transition-colors group cursor-pointer",
                      blocked
                        ? "opacity-70 hover:border-[#dcdcaa]"
                        : "hover:border-[var(--vs-accent)]"
                    )}
                    title={blocked ? t("welcome.walk_need_project") : ""}
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-7 h-7 shrink-0 rounded-full bg-[var(--vs-accent-bg)] text-white text-[12px] font-semibold flex items-center justify-center">
                        {i + 1}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] text-[var(--vs-fg-strong)]">
                          {t(w.k)}
                        </div>
                        <div className="text-[11px] text-[var(--vs-fg-muted)] mt-1">
                          {w.hint}
                        </div>
                        {blocked && (
                          <div className="text-[11px] text-[#dcdcaa] mt-1">
                            ↳ {t("welcome.walk_need_project")}
                          </div>
                        )}
                      </div>
                      <ChevronRight
                        size={14}
                        className="text-[var(--vs-fg-subtle)] group-hover:text-[var(--vs-accent)] mt-1"
                      />
                    </div>
                  </button>
                );
              });
            })()}
          </div>
        </section>

        {/* Workflow quick links (shown when project open) */}
        {currentProject && (
          <section className="mt-12">
            <h2 className="text-[14px] font-semibold text-[var(--vs-fg-strong)] mb-4 flex items-center gap-2">
              <FileCode2 size={16} className="text-[#519aba]" />
              Workflow · {currentProject.name}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {WORKFLOW_STEPS.map((step) => (
                <button
                  key={step.id}
                  className="group vs-card px-3 py-2 flex items-center gap-2 hover:bg-[var(--vs-hover)] text-left"
                  onClick={() => openTab(buildTab(step.id))}
                >
                  <FileCode2
                    size={16}
                    className="text-[#519aba] shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] text-[var(--vs-fg-strong)] truncate">
                      {t(step.key)}
                    </div>
                    <div className="text-[11px] text-[var(--vs-fg-muted)] truncate">
                      {step.file}
                    </div>
                  </div>
                  <ChevronRight
                    size={14}
                    className="text-[var(--vs-fg-subtle)] group-hover:text-[var(--vs-accent)]"
                  />
                </button>
              ))}
            </div>
          </section>
        )}

        <div className="mt-14 text-[11px] text-[var(--vs-fg-subtle)] text-center">
          {t("welcome.tip_shortcut")}{" "}
          <kbd className="px-1.5 py-0.5 border border-[var(--vs-border)] rounded-sm text-[var(--vs-fg)] bg-[var(--vs-panel)]">
            Ctrl+Shift+P
          </kbd>{" "}
          {t("welcome.tip_shortcut_cont")}
        </div>
      </div>
    </div>
  );
}

function StartLink({
  icon: Icon,
  label,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 text-[13px] text-[var(--vs-accent)] hover:underline py-1"
    >
      <Icon size={15} className="text-[var(--vs-fg)]" />
      <span>{label}</span>
    </button>
  );
}
