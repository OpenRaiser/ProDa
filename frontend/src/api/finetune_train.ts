import { api } from "./client";
import type {
  EnvCheck,
  EnvSettings,
  OutputTreeEntry,
  PreviewYamlResponse,
  StartTrainingResponse,
  TrainDataset,
  TrainingConfig,
  TrainingMetrics,
  TrainingSession,
} from "@/types";

export async function envCheck(): Promise<EnvCheck> {
  const { data } = await api.get("/finetune_train/env/check");
  return data as EnvCheck;
}

export async function envSettingsGet(): Promise<EnvSettings> {
  const { data } = await api.get("/finetune_train/env/settings");
  return (data.settings as EnvSettings) ?? {};
}

export async function envSettingsPut(
  payload: EnvSettings
): Promise<EnvSettings> {
  const { data } = await api.put("/finetune_train/env/settings", payload);
  return (data.settings as EnvSettings) ?? {};
}

export async function listDatasets(projectId: string): Promise<TrainDataset[]> {
  const { data } = await api.get(`/finetune_train/${projectId}/datasets`);
  return (data.datasets as TrainDataset[]) ?? [];
}

export async function listModels(
  projectId: string
): Promise<{ model_root: string; models: string[] }> {
  const { data } = await api.get(`/finetune_train/${projectId}/models`);
  return data;
}

export async function previewYaml(
  projectId: string,
  config: TrainingConfig
): Promise<PreviewYamlResponse> {
  const { data } = await api.post(
    `/finetune_train/${projectId}/preview-yaml`,
    { config }
  );
  return data as PreviewYamlResponse;
}

export async function startTraining(
  projectId: string,
  config: TrainingConfig,
  yamlOverride = ""
): Promise<StartTrainingResponse> {
  const { data } = await api.post(`/finetune_train/${projectId}/start`, {
    config,
    yaml_override: yamlOverride,
  });
  return data as StartTrainingResponse;
}

export async function cancelTraining(projectId: string): Promise<{
  cancelled: boolean;
  pid: number;
  kill_report: Record<string, unknown>;
}> {
  const { data } = await api.post(`/finetune_train/${projectId}/cancel`);
  return data;
}

export async function getActive(
  projectId: string
): Promise<TrainingSession | null> {
  const { data } = await api.get(`/finetune_train/${projectId}/active`);
  return (data.active as TrainingSession | null) ?? null;
}

export async function getHistory(
  projectId: string
): Promise<TrainingSession[]> {
  const { data } = await api.get(`/finetune_train/${projectId}/history`);
  return (data.history as TrainingSession[]) ?? [];
}

export async function getLogs(
  projectId: string,
  sessionId: string,
  tail = 500
): Promise<{ log_path: string; text: string }> {
  const { data } = await api.get(
    `/finetune_train/${projectId}/sessions/${encodeURIComponent(
      sessionId
    )}/logs`,
    { params: { tail } }
  );
  return data;
}

export async function getMetrics(
  projectId: string,
  sessionId: string,
  maxPoints = 4000
): Promise<TrainingMetrics> {
  const { data } = await api.get(
    `/finetune_train/${projectId}/sessions/${encodeURIComponent(
      sessionId
    )}/metrics`,
    { params: { max_points: maxPoints } }
  );
  return data as TrainingMetrics;
}

export async function getOutputTree(
  projectId: string,
  sessionId: string
): Promise<{ output_dir: string; exists: boolean; entries: OutputTreeEntry[] }> {
  const { data } = await api.get(
    `/finetune_train/${projectId}/sessions/${encodeURIComponent(
      sessionId
    )}/output-tree`
  );
  return data;
}

export function logsStreamUrl(projectId: string, sessionId: string): string {
  return `/api/finetune_train/${projectId}/sessions/${encodeURIComponent(
    sessionId
  )}/logs/stream`;
}
