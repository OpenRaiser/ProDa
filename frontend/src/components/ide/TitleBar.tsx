import { useEffect, useRef, useState } from "react";
import {
  Languages,
  LogOut,
  ChevronDown,
} from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { usePageLabels } from "@/hooks/usePageLabels";
import { WORKFLOW_STEPS } from "@/lib/workflow";
import { getOptions } from "@/api/llm";
import type { ThemeId } from "@/types";

const THEMES: Array<{ id: ThemeId; label: string }> = [
  { id: "dark-plus", label: "Dark+" },
  { id: "light-plus", label: "Light+" },
  { id: "one-dark", label: "One Dark" },
];

interface MenuItem {
  label?: string;
  onClick?: () => void;
  shortcut?: string;
  separator?: boolean;
  disabled?: boolean;
  /** Informational row (e.g. keyboard shortcut list), not clickable. */
  readonly?: boolean;
}

function TopMenu({
  label,
  items,
}: {
  label: string;
  items: MenuItem[];
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        className={clsx(
          "px-2 py-[3px] rounded-sm text-[12px]",
          open ? "titlebar-btn-active" : "titlebar-btn"
        )}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-[1px] z-50 min-w-[220px] bg-[var(--vs-sidebar)] border border-[var(--vs-border)] rounded-sm shadow-popover py-1">
          {items.map((it, i) => {
            if (it.separator) {
              return (
                <div
                  key={i}
                  className="my-1 border-t border-[var(--vs-border)]"
                />
              );
            }
            if (it.readonly) {
              return (
                <div
                  key={i}
                  className="px-3 py-[4px] text-[12px] text-[var(--vs-fg-muted)] flex items-center justify-between"
                >
                  <span>{it.label}</span>
                  {it.shortcut && (
                    <span className="text-[11px] text-[var(--vs-fg-subtle)] font-mono ml-4">
                      {it.shortcut}
                    </span>
                  )}
                </div>
              );
            }
            return (
              <button
                key={i}
                disabled={it.disabled}
                onClick={() => {
                  if (it.disabled) return;
                  it.onClick?.();
                  setOpen(false);
                }}
                className={clsx(
                  "w-full flex items-center justify-between px-3 py-[4px] text-[12px] text-left",
                  it.disabled
                    ? "text-[var(--vs-fg-subtle)] cursor-not-allowed"
                    : "text-[var(--vs-fg)] hover:bg-[var(--vs-accent-bg)] hover:text-white"
                )}
              >
                <span>{it.label}</span>
                {it.shortcut && (
                  <span className="text-[11px] text-[var(--vs-fg-subtle)] font-mono ml-4">
                    {it.shortcut}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function TitleBar() {
  const { t, toggleLanguage, language } = useI18n();
  const { buildTab } = usePageLabels();
  const currentProject = useSession((s) => s.currentProject);
  const setCurrentProject = useSession((s) => s.setCurrentProject);
  const llmProfiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const setSelectedModel = useSession((s) => s.setSelectedModel);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);
  const closeAllTabs = useSession((s) => s.closeAllTabs);
  const openTab = useSession((s) => s.openTab);
  const toggleExplorer = useSession((s) => s.toggleExplorer);
  const setCommandPaletteOpen = useSession((s) => s.setCommandPaletteOpen);
  const theme = useSession((s) => s.theme);
  const setTheme = useSession((s) => s.setTheme);

  const [options, setOptions] = useState<{ key: string; label: string }[]>([]);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);

  useEffect(() => {
    getOptions(llmProfiles)
      .then(setOptions)
      .catch(() => setOptions([]));
  }, [llmProfiles]);

  const selectedLabel =
    options.find((o) => o.key === selectedModel)?.label ?? t("titlebar.no_model");

  const hasProject = !!currentProject;

  const fileItems: MenuItem[] = [
    {
      label: t("menu.file_welcome"),
      onClick: () => openTab(buildTab("welcome")),
    },
    {
      label: t("menu.file_close_project"),
      onClick: () => {
        setCurrentProject(null);
        closeAllTabs();
      },
      disabled: !hasProject,
    },
    { separator: true },
    {
      label: t("menu.file_llm_config"),
      onClick: () => setConfigModalOpen(true),
    },
  ];

  const viewItems: MenuItem[] = [
    {
      label: t("menu.view_palette"),
      onClick: () => setCommandPaletteOpen(true),
      shortcut: "Ctrl+Shift+P",
    },
    {
      label: t("menu.view_toggle_explorer"),
      onClick: toggleExplorer,
      shortcut: "Ctrl+B",
    },
    {
      label: t("menu.view_toggle_lang"),
      onClick: toggleLanguage,
    },
    { separator: true },
    {
      label: `${t("menu.view_theme")} — ${THEMES.find((x) => x.id === theme)?.label ?? "?"}`,
      readonly: true,
    },
    ...THEMES.map((th) => ({
      label: `  ${theme === th.id ? "●" : "○"}  ${th.label}`,
      onClick: () => setTheme(th.id),
    })),
  ];

  const goItems: MenuItem[] = [
    {
      label: t("menu.go_quickopen"),
      onClick: () => setCommandPaletteOpen(true),
      shortcut: "Ctrl+P",
    },
    { separator: true },
    ...WORKFLOW_STEPS.map((step) => ({
      label: `${step.stepNumber}. ${t(step.key)}`,
      onClick: () => openTab(buildTab(step.id)),
      disabled: !hasProject,
    })),
  ];

  const helpItems: MenuItem[] = [
    { label: t("menu.help_shortcuts"), readonly: true },
    { label: "Ctrl+Shift+P", shortcut: t("menu.view_palette"), readonly: true },
    { label: "Ctrl+P", shortcut: t("menu.go_quickopen"), readonly: true },
    { label: "Ctrl+B", shortcut: t("menu.view_toggle_explorer"), readonly: true },
    { separator: true },
    { label: t("menu.help_about"), readonly: true },
    { label: t("menu.help_about_version"), readonly: true },
  ];

  return (
    <div
      className="flex items-center h-[35px] text-[var(--vs-fg)] text-[12px] select-none border-b"
      style={{
        WebkitAppRegion: "drag",
        backgroundColor: "var(--vs-panel)",
        borderColor: "var(--vs-border)",
      } as React.CSSProperties}
    >
      {/* Left: logo (panda + ProDa wordmark). Dark themes use a lighter
          variant so the navy "Da" stays readable against dark background. */}
      <div className="flex items-center pl-3 shrink-0">
        <img
          src={theme === "light-plus" ? "/proda-logo.png" : "/proda-logo-dark.png"}
          alt={t("app.title")}
          className="h-[22px] w-auto rounded-sm"
          draggable={false}
        />
      </div>

      <nav
        className="flex items-center gap-0 ml-4"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <TopMenu label={t("menu.file")} items={fileItems} />
        <TopMenu label={t("menu.view")} items={viewItems} />
        <TopMenu label={t("menu.go")} items={goItems} />
        <TopMenu label={t("menu.help")} items={helpItems} />
      </nav>

      {/* Center: breadcrumb / project */}
      <div className="flex-1 flex items-center justify-center">
        <div className="px-3 py-[2px] rounded-sm bg-[var(--vs-panel)] text-[12px] text-[var(--vs-fg)] max-w-[480px] truncate">
          {currentProject
            ? `${currentProject.name}  —  ProDa`
            : "ProDa"}
        </div>
      </div>

      {/* Right: model + config + lang + exit */}
      <div
        className="flex items-center gap-1 pr-2"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        {/* Model selector */}
        <div className="relative">
          <button
            onClick={() => setModelDropdownOpen((v) => !v)}
            onBlur={() => setTimeout(() => setModelDropdownOpen(false), 150)}
            className={clsx(
              "flex items-center gap-1 px-2 py-[3px] rounded-sm text-[12px]",
              "titlebar-btn border border-transparent"
            )}
            title={t("titlebar.model_label")}
          >
            <span className="text-[var(--vs-fg-muted)]">{t("titlebar.model_label")}:</span>
            <span
              className={clsx(
                "max-w-[180px] truncate",
                selectedModel
                  ? "text-[var(--vs-fg-strong)]"
                  : "text-[var(--vs-fg-muted)]"
              )}
            >
              {selectedLabel}
            </span>
            <ChevronDown size={12} />
          </button>
          {modelDropdownOpen && (
            <div className="absolute right-0 top-full mt-1 z-50 min-w-[240px] max-h-[320px] overflow-auto bg-[var(--vs-sidebar)] border border-[var(--vs-border)] rounded-sm shadow-popover">
              {options.length === 0 ? (
                <div className="px-3 py-2 text-[12px] text-[var(--vs-fg-muted)]">
                  {t("titlebar.no_model")}
                </div>
              ) : (
                options.map((o) => (
                  <button
                    key={o.key}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setSelectedModel(o.key);
                      setModelDropdownOpen(false);
                    }}
                    className={clsx(
                      "w-full text-left px-3 py-[6px] text-[12px] hover:bg-[var(--vs-accent-bg)]",
                      selectedModel === o.key && "bg-[var(--vs-selected)] text-white"
                    )}
                  >
                    {o.label}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <button
          onClick={toggleLanguage}
          className="px-2 py-[3px] rounded-sm text-[12px] flex items-center gap-1 titlebar-btn"
          title={language === "zh" ? "Switch to English" : "切换到中文"}
        >
          <Languages size={14} />
          <span>{t("titlebar.language")}</span>
        </button>
        {currentProject && (
          <button
            onClick={() => {
              setCurrentProject(null);
              closeAllTabs();
            }}
            className="p-[5px] rounded-sm titlebar-btn"
            title={t("titlebar.exit_project")}
          >
            <LogOut size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
