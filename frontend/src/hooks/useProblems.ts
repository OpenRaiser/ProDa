import { useEffect, useMemo, useState } from "react";
import { useSession } from "@/store/useSession";
import { usePageLabels } from "@/hooks/usePageLabels";
import { envCheck as ftEnvCheck } from "@/api/finetune_train";
import { ocEnvCheck } from "@/api/opencompass";
import type { EnvCheck, EvalEnvCheck } from "@/types";

export type ProblemSeverity = "error" | "warning" | "info";

export interface Problem {
  id: string;
  severity: ProblemSeverity;
  message: string;
  action?: { label: string; run: () => void };
}

/**
 * Aggregates real workspace-health signals for the PROBLEMS bottom panel.
 * Replaces the previous hardcoded "No problems detected" stub with actual
 * actionable items surfaced from the backend + UI state.
 */
export function useProblems(): Problem[] {
  const currentProject = useSession((s) => s.currentProject);
  const backendOnline = useSession((s) => s.backendOnline);
  const llmProfiles = useSession((s) => s.llmProfiles);
  const selectedModel = useSession((s) => s.selectedModel);
  const openTab = useSession((s) => s.openTab);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);
  const { buildTab } = usePageLabels();

  const [envTrain, setEnvTrain] = useState<EnvCheck | null>(null);
  const [envEval, setEnvEval] = useState<EvalEnvCheck | null>(null);

  // Only poll env when backend is up; avoid noise when disconnected.
  useEffect(() => {
    if (!backendOnline) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const [t, e] = await Promise.all([
          ftEnvCheck().catch(() => null),
          ocEnvCheck().catch(() => null),
        ]);
        if (cancelled) return;
        setEnvTrain(t);
        setEnvEval(e);
      } catch {
        /* ignore */
      }
    };
    tick();
    const iv = setInterval(tick, 30_000);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [backendOnline]);

  return useMemo(() => {
    const problems: Problem[] = [];

    if (!backendOnline) {
      problems.push({
        id: "backend-offline",
        severity: "error",
        message: "Backend disconnected — cannot reach http://127.0.0.1:8001",
      });
      return problems; // nothing else is meaningful while backend is down
    }

    if (!currentProject) {
      problems.push({
        id: "no-project",
        severity: "info",
        message: "No project opened — create or open one to start",
        action: {
          label: "Open Welcome",
          run: () => openTab(buildTab("welcome")),
        },
      });
    }

    const anyConfigured = Object.values(llmProfiles).some(
      (p) => p.configured
    );
    if (!anyConfigured) {
      problems.push({
        id: "no-llm",
        severity: "warning",
        message: "No LLM provider configured — data generation / diagnosis unavailable",
        action: {
          label: "LLM Config",
          run: () => setConfigModalOpen(true),
        },
      });
    } else if (!selectedModel) {
      problems.push({
        id: "no-model",
        severity: "info",
        message: "A model is configured but none is selected in the top bar",
        action: {
          label: "Choose model",
          run: () => setConfigModalOpen(true),
        },
      });
    }

    if (envTrain && !envTrain.llamafactory_path_ok) {
      problems.push({
        id: "no-llama-factory",
        severity: "info",
        message: `LLaMA-Factory not found at ${envTrain.llamafactory_path} — training unavailable`,
        action: {
          label: "Configure path",
          run: () => openTab(buildTab("fine_tuning")),
        },
      });
    }
    if (envTrain && !envTrain.model_root_ok) {
      problems.push({
        id: "no-model-root",
        severity: "info",
        message: `Model root not found at ${envTrain.model_root} — no base models for training`,
        action: {
          label: "Configure path",
          run: () => openTab(buildTab("fine_tuning")),
        },
      });
    }
    if (envEval && !envEval.opencompass_path_ok) {
      problems.push({
        id: "no-opencompass",
        severity: "info",
        message: `OpenCompass not found at ${envEval.opencompass_path} — evaluation unavailable`,
        action: {
          label: "Configure path",
          run: () => openTab(buildTab("opencompass")),
        },
      });
    }

    return problems;
  }, [
    backendOnline,
    currentProject,
    llmProfiles,
    selectedModel,
    envTrain,
    envEval,
    openTab,
    setConfigModalOpen,
    buildTab,
  ]);
}
