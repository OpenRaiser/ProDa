/**
 * Lightweight EventSource wrapper: auto-reconnect with capped backoff,
 * message handler, terminal "end" event, and clean disposal.
 */

export interface SSEOptions {
  onMessage: (line: string) => void;
  onEnd?: (reason: string) => void;
  onError?: (err: Event) => void;
  onOpen?: () => void;
  minDelayMs?: number;
  maxDelayMs?: number;
}

export interface SSEHandle {
  close: () => void;
}

export function subscribeSSE(url: string, opts: SSEOptions): SSEHandle {
  const minDelay = opts.minDelayMs ?? 1000;
  const maxDelay = opts.maxDelayMs ?? 10_000;
  let closed = false;
  let delay = minDelay;
  let es: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    if (closed) return;
    es = new EventSource(url, { withCredentials: false });
    es.onopen = () => {
      delay = minDelay;
      opts.onOpen?.();
    };
    es.onmessage = (ev) => {
      if (typeof ev.data === "string") opts.onMessage(ev.data);
    };
    es.addEventListener("end", (ev: MessageEvent) => {
      const reason =
        typeof ev.data === "string" ? ev.data : "server-end";
      closed = true;
      cleanup();
      opts.onEnd?.(reason);
    });
    es.onerror = (err) => {
      opts.onError?.(err);
      // Don't spin: close current and schedule a reconnect (browser's own retry is fine too,
      // but closing gives us a cleaner state).
      try {
        es?.close();
      } catch {
        /* ignore */
      }
      es = null;
      if (closed) return;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(open, delay);
      delay = Math.min(maxDelay, Math.floor(delay * 1.8));
    };
  };

  const cleanup = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    try {
      es?.close();
    } catch {
      /* ignore */
    }
    es = null;
  };

  open();

  return {
    close: () => {
      closed = true;
      cleanup();
    },
  };
}
