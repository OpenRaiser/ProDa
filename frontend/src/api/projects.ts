import { api } from "./client";
import type {
  KnowledgeCore,
  MCQItem,
  Project,
  ProjectState,
} from "@/types";

export async function listProjects(): Promise<{
  projects: Project[];
  last_opened_project_id: string;
}> {
  const { data } = await api.get("/projects");
  return data;
}

export async function createProject(
  name: string,
  description = ""
): Promise<Project> {
  const { data } = await api.post("/projects", { name, description });
  return data;
}

export async function getProject(
  id: string
): Promise<{ project: Project; state: ProjectState }> {
  const { data } = await api.get(`/projects/${id}`);
  return data;
}

export async function renameProject(
  id: string,
  name: string,
  description = ""
): Promise<Project> {
  const { data } = await api.put(`/projects/${id}`, { name, description });
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/projects/${id}`);
}

export async function openProject(
  id: string
): Promise<{ project: Project; state: ProjectState }> {
  const { data } = await api.post(`/projects/${id}/open`);
  return data;
}

export async function saveProjectState(
  id: string,
  state: Partial<ProjectState>
): Promise<void> {
  await api.put(`/projects/${id}/state`, { state });
}

export async function getKnowledgeCore(
  id: string
): Promise<KnowledgeCore | null> {
  const { data } = await api.get(`/projects/${id}/knowledge-core`);
  return data.knowledge_core as KnowledgeCore | null;
}

export async function saveKnowledgeCore(
  id: string,
  core: KnowledgeCore | null
): Promise<void> {
  await api.put(`/projects/${id}/knowledge-core`, {
    knowledge_core: core,
  });
}

export async function saveJsonFields(
  id: string,
  fields: string[]
): Promise<void> {
  await api.put(`/projects/${id}/json-fields`, { json_fields: fields });
}

export async function getBenchmark(id: string): Promise<MCQItem[]> {
  const { data } = await api.get(`/projects/${id}/benchmark`);
  return (data.benchmark_mcq as MCQItem[]) ?? [];
}

export async function saveBenchmark(
  id: string,
  rows: MCQItem[]
): Promise<void> {
  await api.put(`/projects/${id}/benchmark`, { benchmark_mcq: rows });
}
