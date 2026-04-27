import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, MessageSquare, RefreshCw, Send, Square, X } from "lucide-react";
import clsx from "clsx";
import { useI18n } from "@/hooks/useI18n";
import {
  listChatModels,
  loadChatModel,
  stopChatGeneration,
  streamChatCompletion,
  unloadChatModel,
} from "@/api/finetune_chat";
import type {
  FineTuneChatCandidate,
  FineTuneChatMessage,
  FineTuneChatStreamRequest,
} from "@/types";

interface ChatParams {
  temperature: number;
  top_p: number;
  top_k: number;
  max_new_tokens: number;
  repetition_penalty: number;
}

const DEFAULT_PARAMS: ChatParams = {
  temperature: 0.7,
  top_p: 0.9,
  top_k: 50,
  max_new_tokens: 512,
  repetition_penalty: 1.0,
};

export function ModelChatModal({
  projectId,
  open,
  onClose,
}: {
  projectId?: string;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [models, setModels] = useState<FineTuneChatCandidate[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelsError, setModelsError] = useState("");

  const [sessionId, setSessionId] = useState("");
  const [targetPath, setTargetPath] = useState("");

  const [loadingModel, setLoadingModel] = useState(false);
  const [loadedSignature, setLoadedSignature] = useState("");
  const [loadInfo, setLoadInfo] = useState("");
  const [loadError, setLoadError] = useState("");

  const [messages, setMessages] = useState<FineTuneChatMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [chatError, setChatError] = useState("");
  const [chatInfo, setChatInfo] = useState("");
  const [sending, setSending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const loadingModelsRef = useRef(false);

  const [params, setParams] = useState<ChatParams>(DEFAULT_PARAMS);

  const current = useMemo(
    () => models.find((m) => m.session_id === sessionId) ?? null,
    [models, sessionId]
  );

  const targetOptions = useMemo(() => {
    if (!current) return [];
    return [
      {
        key: current.default_target_path,
        label: t("ftune.chat_target_output_dir"),
      },
      ...current.checkpoints.map((c) => ({
        key: c.path,
        label: `${t("ftune.chat_target_checkpoint")} · ${c.name}`,
      })),
    ];
  }, [current, t]);

  const refreshModels = useCallback(async () => {
    if (!projectId || loadingModelsRef.current) return;
    loadingModelsRef.current = true;
    setLoadingModels(true);
    setModelsError("");
    try {
      const rows = await listChatModels(projectId);
      setModels(rows);
      setSessionId((prev) => {
        const next = prev && rows.some((x) => x.session_id === prev)
          ? prev
          : rows[0]?.session_id ?? "";
        const pick = rows.find((x) => x.session_id === next);
        setTargetPath((old) => {
          const validTargets = [
            pick?.default_target_path,
            ...(pick?.checkpoints ?? []).map((c) => c.path),
          ].filter(Boolean);
          return old && validTargets.includes(old) ? old : pick?.default_target_path ?? "";
        });
        if (next !== prev) {
          setLoadedSignature("");
          setLoadInfo("");
        }
        return next;
      });
    } catch (e: unknown) {
      const err = e as { message?: string };
      setModelsError(err?.message ?? t("ftune.chat_err_load_models"));
    } finally {
      loadingModelsRef.current = false;
      setLoadingModels(false);
    }
  }, [projectId, t]);

  useEffect(() => {
    if (!open) return;
    void refreshModels();
    // Intentionally depend only on open/projectId. `t` changes identity every render
    // through useI18n(), and including refreshModels here would re-fetch in a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId]);

  useEffect(() => {
    if (!current) return;
    if (!targetPath || !targetOptions.some((opt) => opt.key === targetPath)) {
      setTargetPath(current.default_target_path);
    }
  }, [current, targetOptions, targetPath]);

  const handleLoad = async () => {
    if (!projectId || !sessionId || !targetPath) return;
    setLoadingModel(true);
    setLoadError("");
    try {
      const res = await loadChatModel(projectId, {
        session_id: sessionId,
        target_path: targetPath,
      });
      setLoadedSignature(res.signature);
      setLoadInfo(
        res.already_loaded ? t("ftune.chat_loaded_reuse") : t("ftune.chat_loaded_ok")
      );
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLoadError(err?.message ?? t("ftune.chat_err_load_model"));
    } finally {
      setLoadingModel(false);
    }
  };

  const handleUnload = async () => {
    if (!projectId) return;
    setLoadingModel(true);
    setLoadError("");
    try {
      await unloadChatModel(projectId);
      setLoadedSignature("");
      setLoadInfo(t("ftune.chat_unloaded"));
    } catch (e: unknown) {
      const err = e as { message?: string };
      setLoadError(err?.message ?? t("ftune.chat_err_unload"));
    } finally {
      setLoadingModel(false);
    }
  };

  const ensureLoaded = async () => {
    if (!projectId || !sessionId || !targetPath) {
      throw new Error(t("ftune.chat_need_model"));
    }
    if (loadedSignature) return;
    const res = await loadChatModel(projectId, {
      session_id: sessionId,
      target_path: targetPath,
    });
    setLoadedSignature(res.signature);
    setLoadInfo(
      res.already_loaded ? t("ftune.chat_loaded_reuse") : t("ftune.chat_loaded_ok")
    );
  };

  const handleStop = () => {
    const ctl = abortRef.current;
    abortRef.current = null;
    setSending(false);
    if (projectId) {
      stopChatGeneration(projectId).catch(() => {});
    }
    ctl?.abort();
  };

  const handleSend = async () => {
    if (!projectId || sending) return;
    const text = prompt.trim();
    if (!text) return;
    setChatError("");
    setPrompt("");

    const userMsg: FineTuneChatMessage = { role: "user", content: text };
    const historyRaw = [...messages, userMsg];
    const estimatedContextTokens = 8192;
    const reserveForOutput = Math.max(256, params.max_new_tokens);
    const budget = Math.max(1200, estimatedContextTokens - reserveForOutput - 256);
    const { kept: history, dropped } = truncateMessagesForContext(historyRaw, budget);
    setMessages([...history, { role: "assistant", content: "" }]);
    setSending(true);
    setChatInfo(
      dropped > 0
        ? t("ftune.chat_history_truncated", { count: String(dropped) })
        : ""
    );

    try {
      await ensureLoaded();
      const controller = new AbortController();
      abortRef.current = controller;

      const payload: FineTuneChatStreamRequest = {
        session_id: sessionId,
        target_path: targetPath,
        messages: history,
        ...params,
        max_history_turns: 36,
        max_context_chars: 24000,
      };

      await streamChatCompletion(projectId, payload, {
        signal: controller.signal,
        onMeta: (meta) => {
          const droppedByBackend = Number(meta.dropped_messages ?? 0);
          if (droppedByBackend > 0) {
            setChatInfo(
              t("ftune.chat_history_truncated_backend", {
                count: String(droppedByBackend),
              })
            );
          }
        },
        onToken: (token) => {
          setMessages((prev) => {
            const next = [...prev];
            for (let i = next.length - 1; i >= 0; i -= 1) {
              if (next[i].role === "assistant") {
                next[i] = { ...next[i], content: next[i].content + token };
                break;
              }
            }
            return next;
          });
        },
        onError: (msg) => {
          setChatError(msg || t("ftune.chat_err_stream"));
        },
      });
    } catch (e: unknown) {
      const err = e as { message?: string; name?: string };
      if (err?.name !== "AbortError") {
        setChatError(err?.message ?? t("ftune.chat_err_stream"));
      }
    } finally {
      abortRef.current = null;
      setSending(false);
    }
  };

  const closeModal = () => {
    if (sending) handleStop();
    onClose();
  };

  const canSend = !!projectId && !!sessionId && !!targetPath && !sending;

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] bg-black/60 flex items-center justify-center p-6"
      onClick={closeModal}
    >
      <div
        className="w-full max-w-[1240px] h-[82vh] bg-[var(--vs-bg)] border border-[var(--vs-border)] rounded-md shadow-xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="h-[42px] border-b border-[var(--vs-border)] px-4 flex items-center gap-2">
          <MessageSquare size={14} className="text-[var(--vs-accent)]" />
          <span className="text-[13px] text-[var(--vs-fg-strong)]">
            {t("ftune.chat_title")}
          </span>
          <span className="text-[11px] text-[var(--vs-fg-muted)] font-mono">
            {t("ftune.chat_subtitle")}
          </span>
          <button
            className="ml-auto p-1 text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg)]"
            onClick={closeModal}
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[360px_1fr]">
          <div className="border-r border-[var(--vs-border)] p-3 space-y-3 overflow-auto">
            <div className="flex items-center justify-between">
              <div className="text-[12px] text-[var(--vs-fg-strong)]">
                {t("ftune.chat_model_source")}
              </div>
              <button
                className="vs-btn-ghost h-[24px] px-2 text-[11px] flex items-center gap-1"
                onClick={refreshModels}
                disabled={loadingModels}
              >
                {loadingModels ? (
                  <Loader2 size={11} className="animate-spin" />
                ) : (
                  <RefreshCw size={11} />
                )}
                {t("common.refresh")}
              </button>
            </div>

            <div>
              <label className="vs-label">{t("ftune.chat_pick_run")}</label>
              <select
                className="vs-input"
                value={sessionId}
                onChange={(e) => {
                  const sid = e.target.value;
                  setSessionId(sid);
                  const pick = models.find((m) => m.session_id === sid);
                  setTargetPath(pick?.default_target_path ?? "");
                  setLoadedSignature("");
                  setLoadInfo("");
                }}
              >
                <option value="">{t("ftune.chat_pick_run_ph")}</option>
                {models.map((m) => (
                  <option key={m.session_id} value={m.session_id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="vs-label">{t("ftune.chat_pick_target")}</label>
              <select
                className="vs-input font-mono"
                value={targetPath}
                onChange={(e) => {
                  setTargetPath(e.target.value);
                  setLoadedSignature("");
                  setLoadInfo("");
                }}
              >
                <option value="">{t("ftune.chat_pick_target_ph")}</option>
                {targetOptions.map((opt) => (
                  <option key={opt.key} value={opt.key}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                className="vs-btn h-[28px] text-[12px] flex items-center justify-center gap-1"
                onClick={handleLoad}
                disabled={!sessionId || !targetPath || loadingModel}
              >
                {loadingModel ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <MessageSquare size={12} />
                )}
                {t("ftune.chat_load_model")}
              </button>
              <button
                className="vs-btn-secondary h-[28px] text-[12px]"
                onClick={handleUnload}
                disabled={loadingModel}
              >
                {t("ftune.chat_unload_model")}
              </button>
            </div>

            {loadInfo && (
              <div className="text-[11px] text-[#4ec9b0] font-mono">
                {loadInfo}
              </div>
            )}
            {(loadError || modelsError) && (
              <div className="text-[11px] text-[#f48771] font-mono">
                {loadError || modelsError}
              </div>
            )}

            <div className="border-t border-[var(--vs-border)] pt-3 space-y-2">
              <div className="text-[12px] text-[var(--vs-fg-strong)]">
                {t("ftune.chat_gen_params")}
              </div>
              <NumInput
                label={t("ftune.chat_temperature")}
                value={params.temperature}
                min={0}
                max={2}
                step={0.01}
                onChange={(v) => setParams((p) => ({ ...p, temperature: v }))}
              />
              <NumInput
                label={t("ftune.chat_max_new_tokens")}
                value={params.max_new_tokens}
                min={1}
                max={4096}
                step={1}
                onChange={(v) =>
                  setParams((p) => ({ ...p, max_new_tokens: Math.round(v) }))
                }
              />
              <NumInput
                label={t("ftune.chat_top_p")}
                value={params.top_p}
                min={0.01}
                max={1}
                step={0.01}
                onChange={(v) => setParams((p) => ({ ...p, top_p: v }))}
              />
              <NumInput
                label={t("ftune.chat_top_k")}
                value={params.top_k}
                min={0}
                max={200}
                step={1}
                onChange={(v) =>
                  setParams((p) => ({ ...p, top_k: Math.round(v) }))
                }
              />
              <NumInput
                label={t("ftune.chat_repetition_penalty")}
                value={params.repetition_penalty}
                min={0.8}
                max={2}
                step={0.01}
                onChange={(v) =>
                  setParams((p) => ({ ...p, repetition_penalty: v }))
                }
              />
            </div>
          </div>

          <div className="flex flex-col min-h-0">
            <div className="flex-1 overflow-auto p-4 space-y-3">
              {messages.length === 0 ? (
                <div className="text-[12px] text-[var(--vs-fg-muted)] italic">
                  {t("ftune.chat_empty")}
                </div>
              ) : (
                messages.map((m, idx) => (
                  <div
                    key={`${m.role}-${idx}`}
                    className={clsx(
                      "rounded px-3 py-2 text-[12px] leading-[1.5] whitespace-pre-wrap",
                      m.role === "user"
                        ? "bg-[var(--vs-selected)]/45 border border-[var(--vs-border)]"
                        : "bg-[var(--vs-panel)] border border-[var(--vs-border)]"
                    )}
                  >
                    <div className="text-[10px] uppercase tracking-wider text-[var(--vs-fg-subtle)] mb-1">
                      {m.role === "user" ? t("ftune.chat_role_user") : t("ftune.chat_role_assistant")}
                    </div>
                    <div className="text-[var(--vs-fg)]">{m.content || t("ftune.chat_streaming")}</div>
                  </div>
                ))
              )}
            </div>

            <div className="border-t border-[var(--vs-border)] p-3 space-y-2">
              {chatInfo && (
                <div className="text-[11px] text-[#dcdcaa] font-mono">{chatInfo}</div>
              )}
              {chatError && (
                <div className="text-[11px] text-[#f48771] font-mono">{chatError}</div>
              )}
              <textarea
                className="vs-input min-h-[84px] font-mono"
                placeholder={t("ftune.chat_prompt_ph")}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <div className="flex items-center gap-2 justify-between">
                <button
                  className="vs-btn-ghost h-[28px] px-2 text-[12px]"
                  onClick={() => {
                    setMessages([]);
                    setChatError("");
                    setChatInfo("");
                  }}
                  disabled={sending}
                >
                  {t("ftune.chat_clear")}
                </button>
                <div className="flex items-center gap-2">
                  {sending && (
                    <button
                      className="vs-btn-secondary h-[28px] px-3 text-[12px] flex items-center gap-1"
                      onClick={handleStop}
                    >
                      <Square size={12} />
                      {t("ftune.chat_stop")}
                    </button>
                  )}
                  <button
                    className="vs-btn h-[28px] px-3 text-[12px] flex items-center gap-1"
                    onClick={handleSend}
                    disabled={!canSend || !prompt.trim()}
                  >
                    {sending ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <Send size={12} />
                    )}
                    {t("ftune.chat_send")}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function NumInput({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="vs-label">{label}</label>
      <input
        className="vs-input font-mono"
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => {
          const v = Number.parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
      />
    </div>
  );
}

function truncateMessagesForContext(
  messages: FineTuneChatMessage[],
  tokenBudget: number
): { kept: FineTuneChatMessage[]; dropped: number } {
  const budget = Math.max(200, tokenBudget);
  const estimateTokens = (text: string) => Math.ceil((text || "").length / 4);
  const systemRows = messages.filter((m) => m.role === "system");
  const nonSystem = messages.filter((m) => m.role !== "system");

  const kept: FineTuneChatMessage[] = [];
  if (systemRows.length > 0) kept.push(systemRows[systemRows.length - 1]);

  let spent = kept.reduce((s, m) => s + estimateTokens(m.content), 0);
  let dropped = Math.max(0, systemRows.length - (systemRows.length > 0 ? 1 : 0));

  for (let i = nonSystem.length - 1; i >= 0; i -= 1) {
    const msg = nonSystem[i];
    const cost = estimateTokens(msg.content);
    if (spent + cost > budget && kept.length > 0) {
      dropped += 1;
      continue;
    }
    kept.splice(kept.length > 0 && kept[0].role === "system" ? 1 : 0, 0, msg);
    spent += cost;
  }
  return { kept, dropped };
}
