import clsx from "clsx";
import {
  Files,
  Settings,
} from "lucide-react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";

const TOP_ITEMS = [
  { id: "explorer" as const, icon: Files, key: "activity.explorer" },
];

export function ActivityBar() {
  const { t } = useI18n();
  const activityView = useSession((s) => s.activityView);
  const setActivityView = useSession((s) => s.setActivityView);
  const toggleExplorer = useSession((s) => s.toggleExplorer);
  const explorerVisible = useSession((s) => s.explorerVisible);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);

  const onClickTop = (id: (typeof TOP_ITEMS)[number]["id"]) => {
    if (activityView === id && explorerVisible) {
      toggleExplorer();
    } else {
      if (!explorerVisible) toggleExplorer();
      setActivityView(id);
    }
  };

  return (
    <div
      className="w-[48px] shrink-0 flex flex-col items-center py-1 border-r"
      style={{
        backgroundColor: "var(--vs-sidebar)",
        borderColor: "var(--vs-border)",
      }}
    >
      {TOP_ITEMS.map((it) => {
        const Icon = it.icon;
        const active = activityView === it.id && explorerVisible;
        return (
          <button
            key={it.id}
            onClick={() => onClickTop(it.id)}
            title={t(it.key)}
            className={clsx(
              "relative w-[48px] h-[48px] flex items-center justify-center",
              "text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg-strong)] transition-colors"
            )}
          >
            {active && (
              <span
                className="absolute left-0 top-0 h-full w-[2px]"
                style={{ backgroundColor: "var(--vs-fg-strong)" }}
              />
            )}
            <Icon
              size={22}
              className={clsx(active && "text-[var(--vs-fg-strong)]")}
            />
          </button>
        );
      })}

      <div className="flex-1" />

      <button
        onClick={() => setConfigModalOpen(true)}
        title={t("activity.settings")}
        className="w-[48px] h-[48px] flex items-center justify-center text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg-strong)]"
      >
        <Settings size={22} />
      </button>
    </div>
  );
}
