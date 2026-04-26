import { useEffect, useRef } from "react";
import { useSession } from "@/store/useSession";
import { evalLogsStreamUrl, getActiveEval } from "@/api/opencompass";
import { subscribeSSE, type SSEHandle } from "@/lib/sse";

/**
 * Global eval watcher: polls /active every 6s, subscribes to SSE log stream
 * while a run is active. Mirror of useTrainingWatcher — kept separate so
 * training + eval can run concurrently.
 */
export function useEvalWatcher() {
  const currentProject = useSession((s) => s.currentProject);
  const active = useSession((s) => s.activeEvalSession);
  const setActive = useSession((s) => s.setActiveEvalSession);
  const appendLog = useSession((s) => s.appendEvalLog);

  const sseRef = useRef<SSEHandle | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!currentProject) {
      setActive(null);
      return;
    }
    let cancelled = false;
    const pid = currentProject.id;

    const tick = async () => {
      try {
        const a = await getActiveEval(pid);
        if (cancelled) return;
        if (a) {
          setActive(a);
          return;
        }
        // Keep the last finished run visible for log/progress inspection.
        const prev = useSession.getState().activeEvalSession;
        if (prev) {
          setActive({
            ...prev,
            alive: false,
            status:
              prev.status && prev.status !== "running"
                ? prev.status
                : "finished",
          });
        } else {
          setActive(null);
        }
      } catch {
        /* ignore */
      }
    };

    tick();
    pollTimer.current = setInterval(tick, 6000);
    return () => {
      cancelled = true;
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    };
  }, [currentProject, setActive]);

  useEffect(() => {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
    if (!currentProject || !active || !active.run_id) return;
    if (!active.alive) return;

    const url = evalLogsStreamUrl(currentProject.id, active.run_id);
    sseRef.current = subscribeSSE(url, {
      onMessage: (line) => appendLog(line),
    });

    return () => {
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
    };
  }, [currentProject, active?.run_id, active?.alive, appendLog]);
}
