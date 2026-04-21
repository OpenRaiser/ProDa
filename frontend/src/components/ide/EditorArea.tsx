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

export function EditorArea() {
  const tabs = useSession((s) => s.openTabs);
  const activeTabId = useSession((s) => s.activeTabId);
  const active = tabs.find((t) => t.id === activeTabId);
  if (!active) {
    return (
      <div className="h-full w-full flex items-center justify-center text-[var(--vs-fg-subtle)] text-[13px]">
        No active tab
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
