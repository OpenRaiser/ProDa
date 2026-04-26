import { useEffect, useRef } from "react";
import { useSession } from "@/store/useSession";
import { getActive, getMetrics, logsStreamUrl } from "@/api/finetune_train";
import { subscribeSSE, type SSEHandle } from "@/lib/sse";

/**
 * Global training watcher. Mount once in IdeShell.
 * - Polls `/active` every 6s to detect new / finished sessions.
 * - Subscribes to SSE log stream for the active session.
 * - Polls metrics every 3s while a session is active.
 */
export function useTrainingWatcher() {
  const currentProject = useSession((s) => s.currentProject);
  const active = useSession((s) => s.activeTrainingSession);
  const setActive = useSession((s) => s.setActiveTrainingSession);
  const appendLog = useSession((s) => s.appendTrainingLog);
  const setMetrics = useSession((s) => s.setTrainingMetrics);

  const sseRef = useRef<SSEHandle | null>(null);
  const metricsTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll active session
  useEffect(() => {
    if (!currentProject) {
      setActive(null);
      return;
    }

    let cancelled = false;
    const pid = currentProject.id;

    const tick = async () => {
      try {
        const a = await getActive(pid);
        if (cancelled) return;
        if (a) {
          setActive(a);
          return;
        }
        // Preserve the last session in UI after it finishes, so logs/metrics
        // remain visible until user starts another run or switches project.
        const prev = useSession.getState().activeTrainingSession;
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

  // SSE subscription (lifecycle tied to active session id)
  useEffect(() => {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
    if (!currentProject || !active || !active.session_id) return;
    if (!active.alive) return;

    const url = logsStreamUrl(currentProject.id, active.session_id);
    sseRef.current = subscribeSSE(url, {
      onMessage: (line) => appendLog(line),
      onEnd: () => {
        /* session finished on backend */
      },
    });

    return () => {
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
    };
  }, [currentProject, active?.session_id, active?.alive, appendLog]);

  // Metrics polling
  useEffect(() => {
    if (metricsTimer.current) {
      clearInterval(metricsTimer.current);
      metricsTimer.current = null;
    }
    if (!currentProject || !active || !active.session_id) {
      setMetrics([]);
      return;
    }

    let cancelled = false;
    const pid = currentProject.id;
    const sid = active.session_id;

    const tick = async () => {
      try {
        const m = await getMetrics(pid, sid, 4000);
        if (cancelled) return;
        setMetrics(m.points ?? []);
      } catch {
        /* ignore */
      }
    };
    tick();
    // Poll faster while alive; once finished we stop (below effect deps will re-fire)
    metricsTimer.current = setInterval(tick, active.alive ? 3000 : 12000);

    return () => {
      cancelled = true;
      if (metricsTimer.current) {
        clearInterval(metricsTimer.current);
        metricsTimer.current = null;
      }
    };
  }, [currentProject, active?.session_id, active?.alive, setMetrics]);
}
