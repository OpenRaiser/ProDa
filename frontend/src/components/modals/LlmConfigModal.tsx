import { useEffect, useState } from "react";
import { X, CheckCircle2, XCircle, Loader2, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import { normalize, testConnectivity } from "@/api/llm";
import type { LlmProfiles } from "@/types";

type Provider = "openai" | "anthropic" | "deepseek";
const PROVIDERS: Provider[] = ["openai", "anthropic", "deepseek"];

export function LlmConfigModal() {
  const open = useSession((s) => s.configModalOpen);
  const setOpen = useSession((s) => s.setConfigModalOpen);
  const profiles = useSession((s) => s.llmProfiles);
  const setProfiles = useSession((s) => s.setLlmProfiles);
  const { t } = useI18n();

  const [provider, setProvider] = useState<Provider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [modelName, setModelName] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "failed" | "testing">("idle");
  const [error, setError] = useState("");
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [saveMsg, setSaveMsg] = useState("");
  const [testedCreds, setTestedCreds] = useState<
    { apiKey: string; apiBase: string; modelName: string } | null
  >(null);

  useEffect(() => {
    if (!open) return;
    const p = profiles[provider] ?? { api_key: "", api_base: "", last_model: "" };
    setApiKey(String(p.api_key ?? ""));
    setApiBase(String(p.api_base ?? ""));
    setModelName(String(p.last_model ?? ""));
    setStatus("idle");
    setError("");
    setAvailableModels([]);
    setSaveMsg("");
    setTestedCreds(null);
  }, [open, provider, profiles]);

  // If any field diverges from what was last tested, invalidate the OK badge.
  useEffect(() => {
    if (!testedCreds) return;
    if (
      testedCreds.apiKey !== apiKey ||
      testedCreds.apiBase !== apiBase ||
      testedCreds.modelName !== modelName.trim()
    ) {
      setStatus("idle");
    }
  }, [apiKey, apiBase, modelName, testedCreds]);

  if (!open) return null;

  const current = profiles[provider] ?? {
    verified_models: [],
    configured: false,
  };

  const handleTest = async () => {
    setStatus("testing");
    setError("");
    try {
      const res = await testConnectivity({
        provider,
        api_key: apiKey,
        api_base: apiBase,
        model_name: modelName,
      });
      if (res.ok) {
        setStatus("ok");
        setAvailableModels(res.models);
        setTestedCreds({
          apiKey,
          apiBase,
          modelName: modelName.trim(),
        });
      } else {
        setStatus("failed");
        setError(res.error);
        setTestedCreds(null);
      }
    } catch (e: any) {
      setStatus("failed");
      setError(e?.message ?? "Unknown error");
      setTestedCreds(null);
    }
  };

  const credsMatchTested =
    !!testedCreds &&
    testedCreds.apiKey === apiKey &&
    testedCreds.apiBase === apiBase &&
    testedCreds.modelName === modelName.trim();

  const handleSave = async () => {
    if (status !== "ok" || !credsMatchTested) {
      setSaveMsg(t("llm.save_need_test"));
      return;
    }
    const next: LlmProfiles = JSON.parse(JSON.stringify(profiles));
    const verified = Array.from(
      new Set([...(next[provider]?.verified_models ?? []), modelName.trim()])
    )
      .filter(Boolean)
      .sort();
    const available = Array.from(
      new Set([...(availableModels ?? []), ...verified])
    )
      .filter(Boolean)
      .sort();
    next[provider] = {
      api_key: apiKey,
      api_base: apiBase,
      verified_models: verified,
      available_models: available,
      configured: verified.length > 0,
      last_model: modelName.trim(),
    };
    try {
      const normalized = await normalize(next);
      setProfiles(normalized);
      setSaveMsg(t("llm.saved"));
    } catch (e: any) {
      setSaveMsg(e?.message ?? "Save failed");
    }
  };

  const handleRemove = async (model: string) => {
    const next: LlmProfiles = JSON.parse(JSON.stringify(profiles));
    const p = next[provider];
    if (!p) return;
    p.verified_models = p.verified_models.filter((m) => m !== model);
    p.available_models = p.available_models.filter((m) => m !== model);
    p.configured = p.verified_models.length > 0;
    if (p.last_model === model) p.last_model = "";
    const normalized = await normalize(next);
    setProfiles(normalized);
  };

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-[620px] max-w-[90vw] max-h-[86vh] overflow-hidden bg-[var(--vs-sidebar)] border border-[var(--vs-border)] rounded-sm shadow-popover flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-[42px] border-b border-[var(--vs-border)]">
          <div className="text-[13px] font-semibold text-[var(--vs-fg-strong)]">
            {t("llm.title")}
          </div>
          <button
            className="p-1 rounded-sm hover:bg-[var(--vs-border)]"
            onClick={() => setOpen(false)}
          >
            <X size={16} />
          </button>
        </div>

        {/* Provider tabs */}
        <div className="flex border-b border-[var(--vs-border)]">
          {PROVIDERS.map((p) => {
            const ready = !!profiles[p]?.configured;
            const active = provider === p;
            return (
              <button
                key={p}
                onClick={() => setProvider(p)}
                className={clsx(
                  "px-4 h-[32px] text-[12px] border-b-2",
                  active
                    ? "border-[var(--vs-accent)] text-[var(--vs-fg-strong)]"
                    : "border-transparent text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg)]"
                )}
              >
                {p}
                {ready && (
                  <CheckCircle2
                    size={12}
                    className="inline ml-2 text-[#4ec9b0]"
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-5 space-y-4">
          {current.verified_models?.length > 0 ? (
            <div className="text-[12px] text-[#4ec9b0]">
              ✓ {current.verified_models.length} verified models
            </div>
          ) : (
            <div className="text-[12px] text-[#dcdcaa]">
              No verified model yet for {provider}
            </div>
          )}

          <div>
            <label className="vs-label">{t("llm.api_key")}</label>
            <input
              className="vs-input"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          <div>
            <label className="vs-label">{t("llm.api_base")}</label>
            <input
              className="vs-input"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder={
                provider === "openai"
                  ? "https://api.openai.com/v1"
                  : provider === "deepseek"
                  ? "https://api.deepseek.com"
                  : "https://api.anthropic.com"
              }
            />
          </div>

          <div>
            <label className="vs-label">{t("llm.model_name")}</label>
            <input
              className="vs-input font-mono"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder={
                provider === "openai"
                  ? "gpt-4o-mini"
                  : provider === "deepseek"
                  ? "deepseek-chat"
                  : "claude-3-5-sonnet-20241022"
              }
            />
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              className="vs-btn-secondary flex items-center gap-2"
              onClick={handleTest}
              disabled={status === "testing"}
            >
              {status === "testing" && (
                <Loader2 size={14} className="animate-spin" />
              )}
              {status === "testing" ? t("llm.testing") : t("llm.test")}
            </button>
            <button className="vs-btn" onClick={handleSave}>
              {t("llm.save")}
            </button>
            {status === "ok" && (
              <span className="flex items-center gap-1 text-[12px] text-[#4ec9b0]">
                <CheckCircle2 size={14} />
                {t("llm.status_ok")}
              </span>
            )}
            {status === "failed" && (
              <span
                className="flex items-center gap-1 text-[12px] text-[#f48771] truncate max-w-[260px]"
                title={error}
              >
                <XCircle size={14} />
                {t("llm.status_failed")}: {error}
              </span>
            )}
          </div>

          {saveMsg && (
            <div className="text-[12px] text-[#dcdcaa]">{saveMsg}</div>
          )}

          {current.verified_models?.length > 0 && (
            <div>
              <label className="vs-label">Verified Models</label>
              <div className="space-y-1">
                {current.verified_models.map((m) => (
                  <div
                    key={m}
                    className="flex items-center justify-between px-2 py-[4px] rounded-sm bg-[var(--vs-bg)] hover:bg-[var(--vs-hover)] group"
                  >
                    <span className="font-mono text-[12px] text-[var(--vs-fg)]">{m}</span>
                    <button
                      className="opacity-0 group-hover:opacity-100 p-1 rounded-sm hover:bg-[var(--vs-border)] text-[#f48771]"
                      onClick={() => handleRemove(m)}
                      title={t("llm.remove")}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
