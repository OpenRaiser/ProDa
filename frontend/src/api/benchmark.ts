import { api } from "./client";
import type { BenchmarkJob, StartBenchmarkBody } from "@/types";

export async function startBenchmark(
  projectId: string,
  body: StartBenchmarkBody
): Promise<string> {
  const { data } = await api.post(`/benchmark/${projectId}/start`, body);
  return data.job_id as string;
}

export async function getBenchmarkJob(jobId: string): Promise<BenchmarkJob> {
  const { data } = await api.get(`/benchmark/jobs/${jobId}`);
  return data as BenchmarkJob;
}

export async function cancelBenchmarkJob(
  jobId: string
): Promise<BenchmarkJob> {
  const { data } = await api.post(`/benchmark/jobs/${jobId}/cancel`);
  return data as BenchmarkJob;
}

export async function listBenchmarkJobs(
  projectId: string
): Promise<BenchmarkJob[]> {
  const { data } = await api.get(`/benchmark/${projectId}/jobs`);
  return data.jobs as BenchmarkJob[];
}
