import { useSession } from "@/store/useSession";
import { Welcome } from "@/pages/Welcome";
import { Placeholder } from "@/pages/Placeholder";
import { LlmConfigPage } from "@/pages/LlmConfigPage";
import { DataProcessing } from "@/pages/DataProcessing";
import { Benchmark } from "@/pages/Benchmark";
import { FineTune } from "@/pages/FineTune";
import { FineTuning } from "@/pages/FineTuning";
import { OpenCompass } from "@/pages/OpenCompass";
import { Results } from "@/pages/Results";
import { useI18n } from "@/hooks/useI18n";

export function EditorArea() {
  const { t } = useI18n();
  const tabs = useSession((s) => s.openTabs);
  const activeTabId = useSession((s) => s.activeTabId);
  const active = tabs.find((t) => t.id === activeTabId);
  if (!active) {
    return (
      <div className="h-full w-full flex items-center justify-center text-[var(--vs-fg-subtle)] text-[13px]">
        {t("editor.no_active_tab")}
      </div>
    );
  }

  switch (active.pageId) {
    case "welcome":
      return <Welcome />;
    case "llm_config":
      return <LlmConfigPage />;
    case "data_processing":
      return <DataProcessing />;
    case "benchmark":
      return <Benchmark />;
    case "finetune":
      return <FineTune />;
    case "fine_tuning":
      return <FineTuning />;
    case "opencompass":
      return <OpenCompass />;
    case "results":
      return <Results />;
    default:
      return <Placeholder pageId={active.pageId} />;
  }
}
