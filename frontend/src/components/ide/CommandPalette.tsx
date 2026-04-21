import { useEffect, useMemo, useRef, useState } from "react";
import { Clock, Search } from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import type { ThemeId } from "@/types";

const THEME_OPTIONS: Array<{ id: ThemeId; label: string }> = [
  { id: "dark-plus", label: "Dark+" },
  { id: "light-plus", label: "Light+" },
  { id: "one-dark", label: "One Dark" },
];
import { useI18n } from "@/hooks/useI18n";
import { WORKFLOW_STEPS } from "@/lib/workflow";
import { usePageLabels } from "@/hooks/usePageLabels";

interface Command {
  id: string;
  label: string;
  hint?: string;
  recent?: boolean;
  run: () => void;
}

export function CommandPalette() {
  const open = useSession((s) => s.commandPaletteOpen);
  const setOpen = useSession((s) => s.setCommandPaletteOpen);
  const openTab = useSession((s) => s.openTab);
  const currentProject = useSession((s) => s.currentProject);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);
  const toggleLanguage = useSession((s) => s.toggleLanguage);
  const setCurrentProject = useSession((s) => s.setCurrentProject);
  const closeAllTabs = useSession((s) => s.closeAllTabs);
  const recentPageIds = useSession((s) => s.recentPageIds);
  const recentArtifacts = useSession((s) => s.recentArtifacts);
  const setPreselectedArtifactPath = useSession(
    (s) => s.setPreselectedArtifactPath
  );
  const theme = useSession((s) => s.theme);
  const setTheme = useSession((s) => s.setTheme);
  const { t } = useI18n();
  const { buildTab, pageTitle } = usePageLabels();

  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // All commands (independent of recency)
  const allCommands: Command[] = useMemo(() => {
    const cmds: Command[] = [
      {
        id: "open_welcome",
        label: t("command.open_welcome"),
        hint: "welcome.md",
        run: () => openTab(buildTab("welcome")),
      },
      {
        id: "open_settings",
        label: t("command.open_settings"),
        hint: "settings.json",
        run: () => setConfigModalOpen(true),
      },
      {
        id: "toggle_language",
        label: t("command.toggle_language"),
        run: () => toggleLanguage(),
      },
      ...THEME_OPTIONS.map((th) => ({
        id: `theme_${th.id}`,
        label: `${t("menu.view_theme")}: ${th.label}${theme === th.id ? " ●" : ""}`,
        run: () => setTheme(th.id),
      })),
    ];
    if (currentProject) {
      for (const step of WORKFLOW_STEPS) {
        cmds.push({
          id: `open_${step.id}`,
          label: `Go: ${t(step.key)}`,
          hint: step.file,
          run: () => openTab(buildTab(step.id)),
        });
      }
      cmds.push({
        id: "close_project",
        label: t("command.close_project"),
        run: () => {
          setCurrentProject(null);
          closeAllTabs();
        },
      });
    }
    return cmds;
  }, [t, currentProject, openTab, buildTab, setConfigModalOpen, toggleLanguage, setCurrentProject, closeAllTabs, theme, setTheme]);

  // Recent items (pages + artifacts) rendered as pseudo-commands at top of empty list.
  const recentCommands: Command[] = useMemo(() => {
    const list: Command[] = [];
    for (const id of recentPageIds) {
      list.push({
        id: `recent_page:${id}`,
        label: pageTitle(id),
        hint: t(`page.${id}.file`, `${id}.py`),
        recent: true,
        run: () => openTab(buildTab(id)),
      });
    }
    if (currentProject) {
      for (const a of recentArtifacts) {
        if (a.projectId !== currentProject.id) continue;
        list.push({
          id: `recent_artifact:${a.path}`,
          label: a.label,
          hint: a.hint || a.path,
          recent: true,
          run: () => {
            setPreselectedArtifactPath(a.path);
            openTab(buildTab("results"));
          },
        });
      }
    }
    return list;
  }, [
    recentPageIds,
    recentArtifacts,
    currentProject,
    openTab,
    buildTab,
    pageTitle,
    t,
    setPreselectedArtifactPath,
  ]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) {
      // Empty query: show Recent items first, then full commands (de-duped)
      const recentIds = new Set(recentCommands.map((c) => c.id));
      return [
        ...recentCommands,
        ...allCommands.filter((c) => !recentIds.has(c.id)),
      ];
    }
    const pool = [...recentCommands, ...allCommands];
    return pool.filter((c) =>
      (c.label + " " + (c.hint ?? "")).toLowerCase().includes(s)
    );
  }, [q, allCommands, recentCommands]);

  useEffect(() => {
    if (open) {
      setQ("");
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  useEffect(() => {
    setCursor(0);
  }, [q]);

  if (!open) return null;

  const runAt = (i: number) => {
    const cmd = filtered[i];
    if (!cmd) return;
    cmd.run();
    setOpen(false);
  };

  return (
    <div
      className="fixed inset-0 z-[100] pt-[80px] flex items-start justify-center bg-black/20"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-[620px] max-w-[90vw] bg-[var(--vs-sidebar)] rounded-sm shadow-popover border border-[var(--vs-border)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-3 h-[36px] border-b border-[var(--vs-border)]">
          <Search size={14} className="text-[var(--vs-fg-muted)]" />
          <input
            ref={inputRef}
            className="flex-1 bg-transparent text-[13px] outline-none text-[var(--vs-fg)] placeholder:text-[var(--vs-fg-subtle)]"
            placeholder={t("command.placeholder")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
              else if (e.key === "ArrowDown") {
                e.preventDefault();
                setCursor((c) => Math.min(c + 1, filtered.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                runAt(cursor);
              }
            }}
          />
        </div>
        <div className="max-h-[340px] overflow-auto">
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-[12px] text-[var(--vs-fg-muted)]">
              No matching commands
            </div>
          ) : (
            filtered.map((c, i) => {
              const showRecentHeader =
                !q.trim() &&
                c.recent &&
                (i === 0 || !filtered[i - 1]?.recent);
              const showAllHeader =
                !q.trim() && !c.recent && filtered[i - 1]?.recent;
              return (
                <div key={c.id}>
                  {showRecentHeader && (
                    <div className="px-3 py-[4px] text-[10px] uppercase tracking-wider text-[var(--vs-fg-muted)] bg-[var(--vs-sidebar)]">
                      {t("command.recent_header")}
                    </div>
                  )}
                  {showAllHeader && (
                    <div className="px-3 py-[4px] mt-1 text-[10px] uppercase tracking-wider text-[var(--vs-fg-muted)] bg-[var(--vs-sidebar)] border-t border-[var(--vs-border)]">
                      {t("command.all_commands_header")}
                    </div>
                  )}
                  <button
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => runAt(i)}
                    className={clsx(
                      "w-full flex items-center px-3 py-[6px] text-[13px] text-left gap-2",
                      i === cursor
                        ? "bg-[var(--vs-accent-bg)] text-white"
                        : "hover:bg-[var(--vs-hover)]"
                    )}
                  >
                    {c.recent && (
                      <Clock
                        size={11}
                        className="text-[var(--vs-fg-muted)] shrink-0"
                      />
                    )}
                    <span className="flex-1 truncate">{c.label}</span>
                    {c.hint && (
                      <span className="text-[11px] text-[var(--vs-fg-muted)] truncate max-w-[260px]">
                        {c.hint}
                      </span>
                    )}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
