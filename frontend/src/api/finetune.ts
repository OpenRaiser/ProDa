import { api } from "./client";
import type {
  FineTuneJob,
  FineTuneRow,
  StartFineTuneBody,
} from "@/types";

export async function getFineTuneData(projectId: string): Promise<FineTuneRow[]> {
  const { data } = await api.get(`/projects/${projectId}/finetune`);
  return (data.finetune_data as FineTuneRow[]) ?? [];
}

export async function saveFineTuneData(
  projectId: string,
  rows: FineTuneRow[]
): Promise<void> {
  await api.put(`/projects/${projectId}/finetune`, { finetune_data: rows });
}

export async function startFineTune(
  projectId: string,
  body: StartFineTuneBody
): Promise<string> {
  const { data } = await api.post(`/finetune/${projectId}/start`, body);
  return data.job_id as string;
}

export async function getFineTuneJob(jobId: string): Promise<FineTuneJob> {
  const { data } = await api.get(`/finetune/jobs/${jobId}`);
  return data as FineTuneJob;
}

export async function cancelFineTuneJob(jobId: string): Promise<FineTuneJob> {
  const { data } = await api.post(`/finetune/jobs/${jobId}/cancel`);
  return data as FineTuneJob;
}

export async function listFineTuneJobs(projectId: string): Promise<FineTuneJob[]> {
  const { data } = await api.get(`/finetune/${projectId}/jobs`);
  return (data.jobs as FineTuneJob[]) ?? [];
}
