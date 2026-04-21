import { api } from "./client";
import type {
  ExtractionJob,
  StartExtractionBody,
  UploadedFileMeta,
} from "@/types";

export async function uploadFiles(
  projectId: string,
  files: File[]
): Promise<UploadedFileMeta[]> {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  const { data } = await api.post(
    `/extraction/${projectId}/upload`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data.files as UploadedFileMeta[];
}

export async function listUploads(
  projectId: string
): Promise<UploadedFileMeta[]> {
  const { data } = await api.get(`/extraction/${projectId}/uploads`);
  return data.files as UploadedFileMeta[];
}

export async function deleteUpload(
  projectId: string,
  fileId: string
): Promise<void> {
  await api.delete(`/extraction/${projectId}/uploads/${fileId}`);
}

export async function inspectJson(
  projectId: string,
  fileId: string
): Promise<string[]> {
  const { data } = await api.post(
    `/extraction/${projectId}/inspect-json`,
    { file_id: fileId }
  );
  return data.paths as string[];
}

export async function startExtraction(
  projectId: string,
  body: StartExtractionBody
): Promise<string> {
  const { data } = await api.post(`/extraction/${projectId}/start`, body);
  return data.job_id as string;
}

export async function getJob(jobId: string): Promise<ExtractionJob> {
  const { data } = await api.get(`/extraction/jobs/${jobId}`);
  return data as ExtractionJob;
}

export async function cancelJob(jobId: string): Promise<ExtractionJob> {
  const { data } = await api.post(`/extraction/jobs/${jobId}/cancel`);
  return data as ExtractionJob;
}

export async function listProjectJobs(
  projectId: string
): Promise<ExtractionJob[]> {
  const { data } = await api.get(`/extraction/${projectId}/jobs`);
  return data.jobs as ExtractionJob[];
}
