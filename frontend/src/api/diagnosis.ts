import { api } from "./client";
import type {
  DiagnosisJob,
  DiagnosisReportDetail,
  DiagnosisReportSummary,
  EvalModel,
  FineTuneRow,
  FlowState,
  MergeBody,
  MergeResponse,
  OpenCompassRun,
  StartReportBody,
  StartSupplementBody,
  SupplementDataset,
} from "@/types";

export async function listOpenCompassRuns(
  projectId: string
): Promise<OpenCompassRun[]> {
  const { data } = await api.get(`/diagnosis/${projectId}/opencompass-runs`);
  return (data.runs as OpenCompassRun[]) ?? [];
}

export async function uploadEvalJson(
  projectId: string,
  file: File
): Promise<OpenCompassRun> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post(
    `/diagnosis/${projectId}/upload-eval`,
    fd,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data as OpenCompassRun;
}

export async function getEvalModels(
  projectId: string,
  resultFile: string
): Promise<EvalModel[]> {
  const { data } = await api.get(
    `/diagnosis/${projectId}/eval-models`,
    { params: { result_file: resultFile } }
  );
  return (data.models as EvalModel[]) ?? [];
}

// Reports
export async function startReport(
  projectId: string,
  body: StartReportBody
): Promise<string> {
  const { data } = await api.post(`/diagnosis/${projectId}/reports/start`, body);
  return data.job_id as string;
}

export async function listReports(
  projectId: string
): Promise<DiagnosisReportSummary[]> {
  const { data } = await api.get(`/diagnosis/${projectId}/reports`);
  return (data.reports as DiagnosisReportSummary[]) ?? [];
}

export async function getReport(
  projectId: string,
  reportId: string
): Promise<{ summary: DiagnosisReportSummary; report: DiagnosisReportDetail }> {
  const { data } = await api.get(
    `/diagnosis/${projectId}/reports/${encodeURIComponent(reportId)}`
  );
  return data;
}

export async function deleteReport(
  projectId: string,
  reportId: string
): Promise<void> {
  await api.delete(
    `/diagnosis/${projectId}/reports/${encodeURIComponent(reportId)}`
  );
}

// Supplements
export async function startSupplement(
  projectId: string,
  body: StartSupplementBody
): Promise<string> {
  const { data } = await api.post(
    `/diagnosis/${projectId}/supplements/start`,
    body
  );
  return data.job_id as string;
}

export async function listSupplements(
  projectId: string
): Promise<SupplementDataset[]> {
  const { data } = await api.get(`/diagnosis/${projectId}/supplements`);
  return (data.supplements as SupplementDataset[]) ?? [];
}

export async function getSupplement(
  projectId: string,
  datasetId: string,
  limit = 100
): Promise<{ summary: SupplementDataset; preview: FineTuneRow[]; total: number }> {
  const { data } = await api.get(
    `/diagnosis/${projectId}/supplements/${encodeURIComponent(datasetId)}`,
    { params: { limit } }
  );
  return data;
}

export async function deleteSupplement(
  projectId: string,
  datasetId: string
): Promise<void> {
  await api.delete(
    `/diagnosis/${projectId}/supplements/${encodeURIComponent(datasetId)}`
  );
}

// Merge + flow
export async function merge(
  projectId: string,
  body: MergeBody
): Promise<MergeResponse> {
  const { data } = await api.post(`/diagnosis/${projectId}/merge`, body);
  return data as MergeResponse;
}

export async function getFlowState(projectId: string): Promise<FlowState> {
  const { data } = await api.get(`/diagnosis/${projectId}/flow-state`);
  return (data.flow_state as FlowState) ?? {};
}

// Diagnosis jobs (shared for report+supplement)
export async function getDiagnosisJob(jobId: string): Promise<DiagnosisJob> {
  const { data } = await api.get(`/diagnosis/jobs/${jobId}`);
  return data as DiagnosisJob;
}

export async function cancelDiagnosisJob(jobId: string): Promise<DiagnosisJob> {
  const { data } = await api.post(`/diagnosis/jobs/${jobId}/cancel`);
  return data as DiagnosisJob;
}

export async function listDiagnosisJobs(
  projectId: string
): Promise<DiagnosisJob[]> {
  const { data } = await api.get(`/diagnosis/${projectId}/jobs`);
  return (data.jobs as DiagnosisJob[]) ?? [];
}
