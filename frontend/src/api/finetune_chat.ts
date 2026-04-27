import { api } from "./client";
import type {
  FineTuneChatCandidate,
  FineTuneChatLoadRequest,
  FineTuneChatLoadResponse,
  FineTuneChatStreamRequest,
} from "@/types";

export async function listChatModels(
  projectId: string
): Promise<FineTuneChatCandidate[]> {
  const { data } = await api.get(`/finetune_chat/${projectId}/models`);
  return (data.items as FineTuneChatCandidate[]) ?? [];
}

export async function loadChatModel(
  projectId: string,
  payload: FineTuneChatLoadRequest
): Promise<FineTuneChatLoadResponse> {
  const { data } = await api.post(`/finetune_chat/${projectId}/load`, payload);
  return data as FineTuneChatLoadResponse;
}

export async function unloadChatModel(projectId: string): Promise<boolean> {
  const { data } = await api.post(`/finetune_chat/${projectId}/unload`);
  return Boolean(data?.released);
}

export async function stopChatGeneration(projectId: string): Promise<boolean> {
  const { data } = await api.post(`/finetune_chat/${projectId}/chat/stop`);
  return Boolean(data?.stopped);
}

export async function streamChatCompletion(
  projectId: string,
  payload: FineTuneChatStreamRequest,
  handlers: {
    onToken: (token: string) => void;
    onMeta?: (meta: Record<string, unknown>) => void;
    onError?: (message: string) => void;
    signal?: AbortSignal;
  }
): Promise<void> {
  const response = await fetch(
    `/api/finetune_chat/${encodeURIComponent(projectId)}/chat/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: handlers.signal,
    }
  );
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error("No stream body");
  }

  const decoder = new TextDecoder("utf-8");
  const reader = response.body.getReader();
  let buffer = "";

  const parseEventBlock = (block: string) => {
    const lines = block.split("\n");
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    const rawData = dataLines.join("\n");
    return { eventName, rawData };
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf("\n\n");
    while (sep >= 0) {
      const block = buffer.slice(0, sep).trim();
      buffer = buffer.slice(sep + 2);
      if (block.length > 0) {
        const { eventName, rawData } = parseEventBlock(block);
        if (eventName === "error") {
          try {
            const parsed = JSON.parse(rawData) as { error?: string };
            handlers.onError?.(parsed.error || "stream error");
          } catch {
            handlers.onError?.(rawData || "stream error");
          }
          return;
        }
        if (eventName === "end") {
          return;
        }
        if (eventName === "meta") {
          try {
            const parsed = JSON.parse(rawData) as Record<string, unknown>;
            handlers.onMeta?.(parsed);
          } catch {
            handlers.onMeta?.({});
          }
          continue;
        }
        if (rawData) {
          try {
            const parsed = JSON.parse(rawData) as { token?: string };
            if (parsed.token) handlers.onToken(parsed.token);
          } catch {
            handlers.onToken(rawData);
          }
        }
      }
      sep = buffer.indexOf("\n\n");
    }
  }
}
