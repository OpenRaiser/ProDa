import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  FlaskConical,
  Gauge,
  Info,
  Package,
  ScrollText,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useProblems, type Problem } from "@/hooks/useProblems";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";

const BASE_TABS = [
  { id: "problems", icon: AlertCircle, label: "PROBLEMS" },
  { id: "output", icon: Activity, label: "OUTPUT" },
  { id: "ports", icon: Package, label: "PORTS" },
] as const;

const TRAINING_TABS = [
  { id: "finetune_log", icon: Sparkles, label: "FINETUNE LOG" },
  { id: "finetune_metrics", icon: FlaskConical, label: "FINETUNE METRICS" },
] as const;

const EVAL_TABS = [
  { id: "opencompass_log", icon: ScrollText, label: "OPENCOMPASS LOG" },
  { id: "opencompass_progress", icon: Gauge, label: "OPENCOMPASS PROGRESS" },
] as const;

type BaseId = (typeof BASE_TABS)[number]["id"];
type TrainingId = (typeof TRAINING_TABS)[number]["id"];
type EvalId = (typeof EVAL_TABS)[number]["id"];
type TabId = BaseId | TrainingId | EvalId;

export function BottomPanel() {
  const { t } = useI18n();
  const backendOnline = useSession((s) => s.backendOnline);
  const currentProject = useSession((s) => s.currentProject);
  const active = useSession((s) => s.activeTrainingSession);
  const logs = useSession((s) => s.trainingLogs);
  const metrics = useSession((s) => s.trainingMetrics);
  const trainingPanelTab = useSession((s) => s.trainingPanelTab);
  const setTrainingPanelTab = useSession((s) => s.setTrainingPanelTab);
  const evalSession = useSession((s) => s.activeEvalSession);
  const evalLogs = useSession((s) => s.evalLogs);
  const evalPanelTab = useSession((s) => s.evalPanelTab);
  const setEvalPanelTab = useSession((s) => s.setEvalPanelTab);
  const problems = useProblems();

  const [active_, setActive] = useState<TabId>("output");
  const prevSessionId = useRef<string | null>(null);
  const prevEvalRunId = useRef<string | null>(null);
  const logBoxRef = useRef<HTMLDivElement | null>(null);
  const evalLogBoxRef = useRef<HTMLDivElement | null>(null);

  const sessionAlive = active?.alive === true;
  const evalAlive = evalSession?.alive === true;
  const showTrainingTabs = !!active;
  const showEvalTabs = !!evalSession;

  // When a new training session starts, auto-focus the LOG tab once.
  useEffect(() => {
    if (!active) {
      prevSessionId.current = null;
      return;
    }
    if (prevSessionId.current !== active.session_id && sessionAlive) {
      prevSessionId.current = active.session_id;
      setActive("finetune_log");
    }
  }, [active?.session_id, sessionAlive, active]);

  // Focus eval tabs when a new eval run starts
  useEffect(() => {
    if (!evalSession) {
      prevEvalRunId.current = null;
      return;
    }
    if (prevEvalRunId.current !== evalSession.run_id && evalAlive) {
      prevEvalRunId.current = evalSession.run_id;
      setActive("opencompass_log");
    }
  }, [evalSession?.run_id, evalAlive, evalSession]);

  // External triggers (e.g. StatusBar click)
  useEffect(() => {
    if (trainingPanelTab) {
      setActive(trainingPanelTab === "log" ? "finetune_log" : "finetune_metrics");
      setTrainingPanelTab(null);
    }
  }, [trainingPanelTab, setTrainingPanelTab]);

  useEffect(() => {
    if (evalPanelTab) {
      setActive(
        evalPanelTab === "log" ? "opencompass_log" : "opencompass_progress"
      );
      setEvalPanelTab(null);
    }
  }, [evalPanelTab, setEvalPanelTab]);

  // If training tabs disappear while selected, fall back to OUTPUT.
  useEffect(() => {
    if (
      !showTrainingTabs &&
      (active_ === "finetune_log" || active_ === "finetune_metrics")
    ) {
      setActive("output");
    }
    if (
      !showEvalTabs &&
      (active_ === "opencompass_log" || active_ === "opencompass_progress")
    ) {
      setActive("output");
    }
  }, [showTrainingTabs, showEvalTabs, active_]);

  // Auto-scroll log tab
  useEffect(() => {
    if (active_ !== "finetune_log") return;
    const el = logBoxRef.current;
    if (!el) return;
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [logs, active_]);

  useEffect(() => {
    if (active_ !== "opencompass_log") return;
    const el = evalLogBoxRef.current;
    if (!el) return;
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [evalLogs, active_]);

  const tabs = useMemo(() => {
    const items: Array<
      (typeof BASE_TABS)[number] | (typeof TRAINING_TABS)[number] | (typeof EVAL_TABS)[number]
    > = [...BASE_TABS];
    if (showTrainingTabs) items.push(...TRAINING_TABS);
    if (showEvalTabs) items.push(...EVAL_TABS);
    return items;
  }, [showTrainingTabs, showEvalTabs]);

  const lossPoints = useMemo(
    () => metrics.filter((p) => p.loss !== undefined),
    [metrics]
  );
  const lrPoints = useMemo(
    () => metrics.filter((p) => p.lr !== undefined),
    [metrics]
  );
  const latestStep = metrics.length ? metrics[metrics.length - 1].step : 0;
  const totalSteps = metrics.length
    ? (metrics[metrics.length - 1].total_steps as number | undefined)
    : undefined;

  return (
    <div className="h-full flex flex-col bg-[var(--vs-bg)] border-t border-[var(--vs-sidebar)]">
      <div className="h-[30px] flex items-center gap-0 px-2 text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] bg-[var(--vs-sidebar)]">
        {tabs.map((tab) => {
          const isActive = active_ === tab.id;
          const isTraining =
            tab.id === "finetune_log" || tab.id === "finetune_metrics";
          const isEval =
            tab.id === "opencompass_log" || tab.id === "opencompass_progress";
          const pulse =
            (isTraining && sessionAlive) || (isEval && evalAlive);
          const accent = isTraining
            ? "#c586c0"
            : isEval
            ? "var(--vs-accent)"
            : "var(--vs-accent)";
          return (
            <button
              key={tab.id}
              onClick={() => setActive(tab.id as TabId)}
              className={clsx(
                "px-3 h-full flex items-center gap-1.5 border-b-2",
                isActive
                  ? ""
                  : "border-transparent text-[var(--vs-fg-muted)] hover:text-[var(--vs-fg)]"
              )}
              style={
                isActive
                  ? { borderBottomColor: accent, color: "#ffffff" }
                  : undefined
              }
            >
              <tab.icon
                size={12}
                style={pulse ? { color: accent } : undefined}
              />
              {tab.label}
              {tab.id === "problems" && problems.length > 0 && (
                <span
                  className="ml-1 px-1.5 rounded-full text-[10px] font-semibold"
                  style={{
                    backgroundColor:
                      problems.some((p) => p.severity === "error")
                        ? "#f48771"
                        : problems.some((p) => p.severity === "warning")
                        ? "#dcdcaa"
                        : "var(--vs-accent)",
                    color: "var(--vs-bg)",
                  }}
                >
                  {problems.length}
                </span>
              )}
              {pulse && (
                <span
                  className="ml-1 w-[6px] h-[6px] rounded-full animate-pulse"
                  style={{ backgroundColor: accent }}
                />
              )}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-auto p-3 font-mono text-[12px] text-[var(--vs-fg)] bg-[var(--vs-bg)]">
        {active_ === "output" && (
          <div className="space-y-1">
            <Line_
              tag="INFO"
              color="text-[var(--vs-accent)]"
            >
              ProDa frontend started on http://localhost:5173
            </Line_>
            <Line_
              tag={backendOnline ? "INFO" : "WARN"}
              color={backendOnline ? "text-[#4ec9b0]" : "text-[#dcdcaa]"}
            >
              Backend: {backendOnline ? "connected" : "disconnected"}{" "}
              (http://localhost:8001)
            </Line_>
            {currentProject ? (
              <Line_ tag="INFO" color="text-[var(--vs-accent)]">
                Active project: {currentProject.name} ({currentProject.id})
              </Line_>
            ) : (
              <Line_ tag="INFO" color="text-[var(--vs-fg-muted)]">
                No project opened. Use Welcome page to create or open one.
              </Line_>
            )}
          </div>
        )}
        {active_ === "problems" && <ProblemsList problems={problems} />}
        {active_ === "ports" && (
          <div className="text-[var(--vs-fg-muted)]">
            <div className="grid grid-cols-4 gap-4 font-sans text-[11px] uppercase tracking-wider mb-2">
              <span>Port</span>
              <span>Process</span>
              <span>Forwarded Address</span>
              <span>Visibility</span>
            </div>
            <div className="grid grid-cols-4 gap-4 font-sans text-[12px] text-[var(--vs-fg)]">
              <span>5173</span>
              <span>vite</span>
              <span>http://localhost:5173</span>
              <span>Private</span>
            </div>
            <div className="grid grid-cols-4 gap-4 font-sans text-[12px] text-[var(--vs-fg)]">
              <span>8001</span>
              <span>uvicorn</span>
              <span>http://localhost:8001</span>
              <span>Private</span>
            </div>
          </div>
        )}
        {active_ === "finetune_log" && (
          <div
            ref={logBoxRef}
            className="h-full overflow-auto whitespace-pre-wrap leading-[1.45] text-[11px]"
          >
            {active && (
              <div className="text-[var(--vs-fg-muted)] mb-2 text-[11px]">
                session <span className="text-white">{active.session_id}</span>{" "}
                · pid={active.pid} ·{" "}
                <span
                  className={
                    sessionAlive ? "text-[#4ec9b0]" : "text-[var(--vs-fg-subtle)]"
                  }
                >
                  {sessionAlive ? "running" : "finished"}
                </span>
              </div>
            )}
            {logs.length === 0 ? (
              <div className="text-[var(--vs-fg-muted)] italic">
                {t("ftune.log_waiting")}
              </div>
            ) : (
              logs.map((line, i) => <div key={i}>{line}</div>)
            )}
          </div>
        )}
        {active_ === "finetune_metrics" && (
          <div className="space-y-4">
            <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono">
              step {latestStep}
              {totalSteps ? `/${totalSteps}` : ""}
              {lossPoints.length > 0 && ` · loss ${(lossPoints[lossPoints.length - 1].loss ?? 0).toFixed(4)}`}
              {lrPoints.length > 0 && ` · lr ${(lrPoints[lrPoints.length - 1].lr ?? 0).toExponential(2)}`}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MiniChart title="Loss" data={lossPoints} dataKey="loss" color="var(--vs-accent)" />
              <MiniChart title="Learning rate" data={lrPoints} dataKey="lr" color="#c586c0" />
            </div>
          </div>
        )}
        {active_ === "opencompass_log" && (
          <div
            ref={evalLogBoxRef}
            className="h-full overflow-auto whitespace-pre-wrap leading-[1.45] text-[11px]"
          >
            {evalSession && (
              <div className="text-[var(--vs-fg-muted)] mb-2 text-[11px]">
                run <span className="text-white">{evalSession.run_id}</span> · pid=
                {evalSession.pid} ·{" "}
                <span
                  className={evalAlive ? "text-[#4ec9b0]" : "text-[var(--vs-fg-subtle)]"}
                >
                  {evalAlive ? "running" : "finished"}
                </span>
              </div>
            )}
            {evalLogs.length === 0 ? (
              <div className="text-[var(--vs-fg-muted)] italic">{t("bottompanel.waiting_eval_output")}</div>
            ) : (
              evalLogs.map((line, i) => <div key={i}>{line}</div>)
            )}
          </div>
        )}
        {active_ === "opencompass_progress" && (
          <EvalProgressPanel />
        )}
      </div>
    </div>
  );
}

function EvalProgressPanel() {
  const evalSession = useSession((s) => s.activeEvalSession);
  const evalLogs = useSession((s) => s.evalLogs);

  // Parse from log tail for lightweight progress; OpenCompass doesn't emit
  // structured metrics, so we grep for common cues.
  const { current, total, dataset, recent } = useMemo(() => {
    let current = 0;
    let total = 0;
    let dataset = "";
    for (let i = evalLogs.length - 1; i >= 0; i--) {
      const l = evalLogs[i];
      const m = /(?:Evaluating|Running|Progress)[^0-9]*?(\d+)\s*\/\s*(\d+)/i.exec(l);
      if (m) {
        current = parseInt(m[1]);
        total = parseInt(m[2]);
        break;
      }
    }
    for (let i = evalLogs.length - 1; i >= 0; i--) {
      const l = evalLogs[i];
      const m = /task[_\s]?name[^a-zA-Z]*([A-Za-z0-9_\-]+)/i.exec(l);
      if (m) {
        dataset = m[1];
        break;
      }
    }
    const recent = evalLogs.slice(-5).join("\n");
    return { current, total, dataset, recent };
  }, [evalLogs]);

  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  return (
    <div className="space-y-3">
      <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono">
        {evalSession ? (
          <>
            run {evalSession.run_id} · pid={evalSession.pid}
            {dataset && ` · dataset=${dataset}`}
            {total > 0 && ` · ${current}/${total}`}
          </>
        ) : (
          "no active eval"
        )}
      </div>
      <div className="h-[8px] bg-[var(--vs-panel)] rounded-sm overflow-hidden">
        <div
          className="h-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: "var(--vs-accent)" }}
        />
      </div>
      <div className="text-[11px] text-[var(--vs-fg-subtle)]">
        {pct}% {total > 0 ? `(${current}/${total})` : ""}
      </div>
      {recent && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--vs-fg-heading)] mb-1">
            recent
          </div>
          <pre className="whitespace-pre-wrap text-[11px] text-[var(--vs-fg)] leading-[1.4]">
            {recent}
          </pre>
        </div>
      )}
    </div>
  );
}

function MiniChart({
  title,
  data,
  dataKey,
  color,
}: {
  title: string;
  data: import("@/types").TrainingMetricsPoint[];
  dataKey: "loss" | "lr";
  color: string;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--vs-fg-heading)] mb-1">
        {title}
      </div>
      {data.length === 0 ? (
        <div className="h-[160px] flex items-center justify-center text-[11px] text-[var(--vs-fg-subtle)] italic">
          no data yet
        </div>
      ) : (
        <div style={{ width: "100%", height: 160 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 6, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid stroke="var(--vs-border)" strokeDasharray="3 3" />
              <XAxis dataKey="step" stroke="var(--vs-fg-subtle)" fontSize={10} tickMargin={3} />
              <YAxis stroke="var(--vs-fg-subtle)" fontSize={10} width={50} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--vs-sidebar)",
                  border: "1px solid #3c3c3c",
                  fontSize: 11,
                }}
                labelStyle={{ color: "var(--vs-fg)" }}
                itemStyle={{ color: "var(--vs-fg)" }}
              />
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function Line_({
  tag,
  color,
  children,
}: {
  tag: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-2">
      <span className={clsx("shrink-0 font-semibold", color)}>[{tag}]</span>
      <span>{children}</span>
    </div>
  );
}

function ProblemsList({ problems }: { problems: Problem[] }) {
  const { t } = useI18n();
  if (problems.length === 0) {
    return <div className="text-[#4ec9b0]">{t("bottompanel.no_problems")}</div>;
  }
  return (
    <div className="space-y-1 font-sans">
      {problems.map((p) => {
        const { Icon, color } =
          p.severity === "error"
            ? { Icon: XCircle, color: "#f48771" }
            : p.severity === "warning"
            ? { Icon: AlertTriangle, color: "#dcdcaa" }
            : { Icon: Info, color: "var(--vs-accent)" };
        return (
          <div
            key={p.id}
            className="flex items-start gap-2 px-2 py-1 text-[12px] hover:bg-[var(--vs-hover)] rounded-sm"
          >
            <Icon size={13} style={{ color }} className="mt-[2px] shrink-0" />
            <span className="flex-1 text-[var(--vs-fg)]">{p.message}</span>
            {p.action && (
              <button
                onClick={p.action.run}
                className="text-[var(--vs-accent)] hover:underline text-[11px] shrink-0 ml-2"
              >
                {p.action.label} →
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
