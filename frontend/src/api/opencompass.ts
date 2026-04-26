import { api } from "./client";
import type {
  EvalBenchmark,
  EvalConfig,
  EvalEnvCheck,
  EvalPreviewResponse,
  EvalResult,
  EvalSampleRow,
  EvalSession,
  FlowSuggestion,
  PeftCandidate,
  SampleAnnotation,
  SampleFacets,
} from "@/types";

export async function ocEnvCheck(): Promise<EvalEnvCheck> {
  const { data } = await api.get("/opencompass/env/check");
  return data as EvalEnvCheck;
}

export async function ocEnvSettingsPut(payload: {
  opencompass_path?: string;
}): Promise<Record<string, unknown>> {
  const { data } = await api.put("/opencompass/env/settings", payload);
  return data.settings;
}

export async function listBenchmarks(projectId: string): Promise<EvalBenchmark[]> {
  const { data } = await api.get(`/opencompass/${projectId}/benchmarks`);
  return (data.benchmarks as EvalBenchmark[]) ?? [];
}

export async function uploadBenchmark(
  projectId: string,
  file: File
): Promise<EvalBenchmark> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post(
    `/opencompass/${projectId}/upload-benchmark`,
    fd,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data as EvalBenchmark;
}

export async function listPeftCandidates(
  projectId: string
): Promise<PeftCandidate[]> {
  const { data } = await api.get(`/opencompass/${projectId}/peft-candidates`);
  return (data.candidates as PeftCandidate[]) ?? [];
}

export async function getFlowSuggestion(
  projectId: string
): Promise<FlowSuggestion | null> {
  const { data } = await api.get(`/opencompass/${projectId}/flow-suggestion`);
  return (data.suggestion as FlowSuggestion | null) ?? null;
}

export async function previewConfig(
  projectId: string,
  config: EvalConfig
): Promise<EvalPreviewResponse> {
  const { data } = await api.post(
    `/opencompass/${projectId}/preview-config`,
    config
  );
  return data as EvalPreviewResponse;
}

export async function startEval(
  projectId: string,
  config: EvalConfig
): Promise<{ run_id: string; pid: number; active: EvalSession }> {
  const { data } = await api.post(`/opencompass/${projectId}/start`, {
    config,
  });
  return data;
}

export async function cancelEval(projectId: string): Promise<Record<string, unknown>> {
  const { data } = await api.post(`/opencompass/${projectId}/cancel`);
  return data;
}

export async function getActiveEval(
  projectId: string
): Promise<EvalSession | null> {
  const { data } = await api.get(`/opencompass/${projectId}/active`);
  return (data.active as EvalSession | null) ?? null;
}

export async function listEvalHistory(projectId: string): Promise<EvalSession[]> {
  const { data } = await api.get(`/opencompass/${projectId}/history`);
  return (data.history as EvalSession[]) ?? [];
}

export async function getEvalRun(
  projectId: string,
  runId: string
): Promise<EvalResult> {
  const { data } = await api.get(
    `/opencompass/${projectId}/runs/${encodeURIComponent(runId)}`
  );
  return data as EvalResult;
}

export async function deleteEvalRun(
  projectId: string,
  runId: string
): Promise<{ deleted: boolean; run_id: string }> {
  const { data } = await api.delete(
    `/opencompass/${projectId}/runs/${encodeURIComponent(runId)}`
  );
  return data;
}

export async function getRunSamples(
  projectId: string,
  runId: string,
  opts: {
    model?: string;
    status?: "pass" | "fail";
    subject?: string;
    question_type?: string;
    limit?: number;
    offset?: number;
  } = {}
): Promise<{
  total: number;
  offset: number;
  limit: number;
  rows: EvalSampleRow[];
  facets: SampleFacets;
}> {
  const { data } = await api.get(
    `/opencompass/${projectId}/runs/${encodeURIComponent(runId)}/samples`,
    { params: opts }
  );
  return data;
}

export async function getAnnotations(
  projectId: string,
  runId: string
): Promise<SampleAnnotation[]> {
  const { data } = await api.get(
    `/opencompass/${projectId}/runs/${encodeURIComponent(runId)}/annotations`
  );
  return (data.annotations as SampleAnnotation[]) ?? [];
}

export async function putAnnotation(
  projectId: string,
  runId: string,
  payload: { sample_id: string; model: string; issue_type: string; note?: string }
): Promise<SampleAnnotation[]> {
  const { data } = await api.put(
    `/opencompass/${projectId}/runs/${encodeURIComponent(runId)}/annotations`,
    payload
  );
  return (data.annotations as SampleAnnotation[]) ?? [];
}

export function evalLogsStreamUrl(projectId: string, runId: string): string {
  return `/api/opencompass/${projectId}/runs/${encodeURIComponent(
    runId
  )}/logs/stream`;
}

export async function getEvalLogs(
  projectId: string,
  runId: string,
  tail = 500
): Promise<{ log_path: string; text: string }> {
  const { data } = await api.get(
    `/opencompass/${projectId}/runs/${encodeURIComponent(runId)}/logs`,
    { params: { tail } }
  );
  return data;
}
