import { X, FileText, FileCode2 } from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";

export function TabBar() {
  const tabs = useSession((s) => s.openTabs);
  const activeTabId = useSession((s) => s.activeTabId);
  const setActiveTab = useSession((s) => s.setActiveTab);
  const closeTab = useSession((s) => s.closeTab);

  return (
    <div className="h-[35px] flex items-end bg-[var(--vs-sidebar)] overflow-x-auto overflow-y-hidden scrollbar-none">
      <div className="flex items-center h-full">
        {tabs.map((tab) => {
          const active = tab.id === activeTabId;
          const Icon = tab.fileName.endsWith(".py")
            ? FileCode2
            : FileText;
          const iconColor = tab.fileName.endsWith(".py")
            ? "text-[#519aba]"
            : tab.fileName.endsWith(".md")
            ? "text-[#519aba]"
            : "text-[#cbcb41]";
          return (
            <div
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                "group relative flex items-center gap-2 h-[35px] pl-3 pr-2",
                "border-r border-[var(--vs-sidebar)] cursor-pointer select-none",
                "text-[13px] whitespace-nowrap min-w-[120px] max-w-[240px]",
                active
                  ? "bg-[var(--vs-bg)] text-[var(--vs-fg-strong)]"
                  : "bg-[var(--vs-panel)] text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg)]"
              )}
              style={{
                borderTop: active
                  ? "1px solid #3794ff"
                  : "1px solid transparent",
              }}
              title={tab.fileName}
            >
              <Icon size={14} className={clsx(iconColor, "shrink-0")} />
              <span className="truncate flex-1">{tab.fileName}</span>
              {tab.closable ? (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  className={clsx(
                    "shrink-0 p-[2px] rounded-sm",
                    active
                      ? "hover:bg-[var(--vs-border)]"
                      : "opacity-0 group-hover:opacity-100 hover:bg-[var(--vs-border)]"
                  )}
                >
                  <X size={14} />
                </button>
              ) : (
                <span className="shrink-0 w-[18px] h-[18px]" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
