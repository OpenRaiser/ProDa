import { FileJson, ExternalLink } from "lucide-react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";

export function LlmConfigPage() {
  const { t } = useI18n();
  const profiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);

  const snapshot = {
    selected_model: selectedModel,
    profiles: Object.fromEntries(
      Object.entries(profiles).map(([k, v]) => [
        k,
        {
          configured: v.configured,
          last_model: v.last_model,
          verified_models: v.verified_models,
          api_key: v.api_key ? "***" + v.api_key.slice(-4) : "",
          api_base: v.api_base,
        },
      ])
    ),
  };

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[900px] mx-auto px-12 py-8">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <FileJson size={22} className="text-[#cbcb41]" />
            <h1 className="text-[20px] font-light text-[var(--vs-fg-strong)]">
              settings.json
            </h1>
          </div>
          <button
            className="vs-btn flex items-center gap-2"
            onClick={() => setConfigModalOpen(true)}
          >
            <ExternalLink size={14} />
            {t("llm.title")}
          </button>
        </div>

        <pre className="vs-card p-5 font-mono text-[12.5px] leading-[1.7] text-[var(--vs-fg)] overflow-auto whitespace-pre">
{JSON.stringify(snapshot, null, 2)}
        </pre>

        <div className="text-[12px] text-[var(--vs-fg-muted)] mt-4">
          Click "{t("llm.title")}" to configure provider credentials, test
          connectivity, and save verified models. Keys are never displayed in
          plain text here.
        </div>
      </div>
    </div>
  );
}
