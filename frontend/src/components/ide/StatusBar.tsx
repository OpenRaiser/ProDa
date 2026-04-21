import type { LucideIcon } from "lucide-react";
import {
  CheckCircle2,
  Cpu,
  Folder,
  WifiOff,
  Radio,
  GitBranch,
  AlertCircle,
  Palette,
  ScrollText,
  Sparkles,
} from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import type { ThemeId, TrainingMetricsPoint } from "@/types";

const THEME_CYCLE: ThemeId[] = ["dark-plus", "light-plus", "one-dark"];
const THEME_LABEL: Record<ThemeId, string> = {
  "dark-plus": "Dark+",
  "light-plus": "Light+",
  "one-dark": "One Dark",
};

export function StatusBar() {
  const { t, language } = useI18n();
  const currentProject = useSession((s) => s.currentProject);
  const selectedModel = useSession((s) => s.selectedModel);
  const backendOnline = useSession((s) => s.backendOnline);
  const setConfigModalOpen = useSession((s) => s.setConfigModalOpen);
  const toggleLanguage = useSession((s) => s.toggleLanguage);
  const activeTraining = useSession((s) => s.activeTrainingSession);
  const trainingMetrics = useSession((s) => s.trainingMetrics);
  const setTrainingPanelTab = useSession((s) => s.setTrainingPanelTab);
  const activeEval = useSession((s) => s.activeEvalSession);
  const evalLogs = useSession((s) => s.evalLogs);
  const setEvalPanelTab = useSession((s) => s.setEvalPanelTab);
  const theme = useSession((s) => s.theme);
  const setTheme = useSession((s) => s.setTheme);

  const modelShort = selectedModel ? selectedModel.split("::").slice(-1)[0] : "";
  const trainingLabel = buildTrainingLabel(activeTraining, trainingMetrics);
  const evalLabel = buildEvalLabel(activeEval, evalLogs);

  return (
    <div
      className="h-[22px] flex items-center justify-between px-0 text-[11px] text-white select-none"
      style={{
        backgroundColor: backendOnline
          ? "var(--vs-statusbar)"
          : "var(--vs-statusbar-offline)",
      }}
    >
      <div className="flex items-center h-full">
        <StatusItem
          icon={backendOnline ? Radio : WifiOff}
          label={
            backendOnline
              ? t("statusbar.connected")
              : t("statusbar.disconnected")
          }
        />
        <StatusItem icon={GitBranch} label="main" />
        <StatusItem
          icon={Folder}
          label={currentProject?.name ?? t("statusbar.no_project")}
          muted={!currentProject}
        />
      </div>
      <div className="flex items-center h-full">
        {activeTraining && (
          <StatusItem
            icon={Sparkles}
            label={trainingLabel}
            onClick={() => setTrainingPanelTab("metrics")}
          />
        )}
        {activeEval && (
          <StatusItem
            icon={ScrollText}
            label={evalLabel}
            onClick={() => setEvalPanelTab("progress")}
          />
        )}
        <StatusItem
          icon={Cpu}
          label={modelShort || t("statusbar.no_model")}
          muted={!modelShort}
          onClick={() => setConfigModalOpen(true)}
        />
        <StatusItem
          icon={Palette}
          label={THEME_LABEL[theme]}
          onClick={() => {
            const idx = THEME_CYCLE.indexOf(theme);
            const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
            setTheme(next);
          }}
        />
        <StatusItem label={`UTF-8`} />
        <StatusItem label="LF" />
        <StatusItem label={language === "zh" ? "中文" : "EN"} onClick={toggleLanguage} />
        <StatusItem
          icon={currentProject ? CheckCircle2 : AlertCircle}
          label={t("statusbar.ready")}
        />
      </div>
    </div>
  );
}

function buildTrainingLabel(
  active: ReturnType<typeof useSession.getState>["activeTrainingSession"],
  points: TrainingMetricsPoint[]
): string {
  if (!active) return "";
  const alive = active.alive === true;
  const last = points[points.length - 1];
  const step = last?.step ?? 0;
  const total = last?.total_steps as number | undefined;
  const loss = last?.loss;
  const parts: string[] = [alive ? "training" : "finished"];
  if (step) parts.push(`step ${step}${total ? `/${total}` : ""}`);
  if (loss !== undefined) parts.push(`loss ${loss.toFixed(3)}`);
  return parts.join(" · ");
}

function buildEvalLabel(
  active: ReturnType<typeof useSession.getState>["activeEvalSession"],
  logs: string[]
): string {
  if (!active) return "";
  const alive = active.alive === true;
  const parts: string[] = [alive ? "evaluating" : "eval finished"];
  // Best-effort progress pickup from log
  for (let i = logs.length - 1; i >= 0; i--) {
    const m = /(\d+)\s*\/\s*(\d+)/.exec(logs[i]);
    if (m) {
      parts.push(`${m[1]}/${m[2]}`);
      break;
    }
  }
  const modelList = (active.models || [])
    .map((m) => (typeof m === "string" ? m : m?.abbr ?? ""))
    .filter(Boolean);
  if (modelList.length) parts.push(modelList.join(", "));
  return parts.join(" · ");
}

function StatusItem({
  icon: Icon,
  label,
  muted,
  onClick,
}: {
  icon?: LucideIcon;
  label: string;
  muted?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "h-full px-2 flex items-center gap-1 hover:bg-white/10",
        muted && "opacity-75"
      )}
    >
      {Icon && <Icon size={12} />}
      <span className="truncate max-w-[260px]">{label}</span>
    </button>
  );
}
