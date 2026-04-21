import { api } from "./client";
import type { LlmProfiles } from "@/types";

export async function getDefaults(): Promise<{ profiles: LlmProfiles }> {
  const { data } = await api.get("/llm/defaults");
  return data;
}

export async function testConnectivity(payload: {
  provider: string;
  api_key: string;
  api_base: string;
  model_name: string;
}): Promise<{ ok: boolean; models: string[]; error: string }> {
  const { data } = await api.post("/llm/test", payload);
  return data;
}

export async function normalize(profiles: LlmProfiles): Promise<LlmProfiles> {
  const { data } = await api.post("/llm/normalize", { profiles });
  return data.profiles;
}

export async function getOptions(
  profiles: LlmProfiles
): Promise<{ key: string; label: string }[]> {
  const { data } = await api.post("/llm/options", { profiles });
  return data.options;
}

export async function parseModel(
  key: string
): Promise<{ provider: string; model: string }> {
  const { data } = await api.post("/llm/parse", { key });
  return data;
}
