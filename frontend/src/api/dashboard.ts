import { api } from "./client";
import type { ArtifactFile, ProjectDashboard } from "@/types";

export async function getDashboard(projectId: string): Promise<ProjectDashboard> {
  const { data } = await api.get(`/dashboard/${projectId}/dashboard`);
  return data as ProjectDashboard;
}

export async function getArtifact(
  projectId: string,
  relativePath: string
): Promise<ArtifactFile> {
  const { data } = await api.get(`/dashboard/${projectId}/artifact`, {
    params: { path: relativePath },
  });
  return data as ArtifactFile;
}

export function exportBundleUrl(projectId: string): string {
  return `/api/dashboard/${projectId}/export-bundle`;
}

export async function downloadExportBundle(
  projectId: string,
  paths: string[] | null
): Promise<void> {
  const res = await api.post(
    `/dashboard/${projectId}/export-bundle`,
    { paths },
    { responseType: "blob" }
  );
  const blob = res.data as Blob;
  const cd = String(res.headers["content-disposition"] || "");
  const m = /filename="([^"]+)"/.exec(cd);
  const filename = m ? m[1] : `pro-ide-export-${projectId}.zip`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
