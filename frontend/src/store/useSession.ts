import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  BenchmarkJob,
  EvalSession,
  ExtractionJob,
  FineTuneSection,
  KnowledgeCore,
  Language,
  LlmProfiles,
  PageId,
  Project,
  Tab,
  ThemeId,
  TrainingMetricsPoint,
  TrainingSession,
} from "@/types";

interface SessionState {
  // i18n
  language: Language;
  setLanguage: (l: Language) => void;
  toggleLanguage: () => void;

  // project
  currentProject: Project | null;
  projects: Project[];
  setCurrentProject: (p: Project | null) => void;
  setProjects: (p: Project[]) => void;

  // llm
  llmProfiles: LlmProfiles;
  selectedModel: string;
  setLlmProfiles: (p: LlmProfiles) => void;
  setSelectedModel: (key: string) => void;

  // tabs
  openTabs: Tab[];
  activeTabId: string | null;
  openTab: (tab: Tab) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  closeAllTabs: () => void;

  // ui
  explorerVisible: boolean;
  toggleExplorer: () => void;
  activityView: "explorer" | "workflow" | "settings";
  setActivityView: (v: SessionState["activityView"]) => void;
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (v: boolean) => void;
  configModalOpen: boolean;
  setConfigModalOpen: (v: boolean) => void;

  // backend health
  backendOnline: boolean;
  setBackendOnline: (v: boolean) => void;

  // Phase 4 — FineTune sub-section
  finetuneSection: FineTuneSection;
  setFinetuneSection: (s: FineTuneSection) => void;

  // Phase 5 — training session (shared across FineTuning page, BottomPanel, StatusBar)
  activeTrainingSession: TrainingSession | null;
  setActiveTrainingSession: (s: TrainingSession | null) => void;
  trainingLogs: string[];
  appendTrainingLog: (line: string) => void;
  clearTrainingLogs: () => void;
  trainingMetrics: TrainingMetricsPoint[];
  setTrainingMetrics: (points: TrainingMetricsPoint[]) => void;
  trainingPanelTab: "log" | "metrics" | null;
  setTrainingPanelTab: (v: "log" | "metrics" | null) => void;

  // Phase 6 — active OpenCompass eval session (shared with BottomPanel / StatusBar)
  activeEvalSession: EvalSession | null;
  setActiveEvalSession: (s: EvalSession | null) => void;
  evalLogs: string[];
  appendEvalLog: (line: string) => void;
  clearEvalLogs: () => void;
  evalPanelTab: "log" | "progress" | null;
  setEvalPanelTab: (v: "log" | "progress" | null) => void;

  // Phase 7 — navigation preselect (Results timeline → respective phase tab)
  preselectedEvalRunId: string | null;
  preselectedTrainSessionId: string | null;
  setPreselectedEvalRunId: (v: string | null) => void;
  setPreselectedTrainSessionId: (v: string | null) => void;

  // Phase 1 — extraction job (not persisted; survives tab switches within session)
  extractionJob: ExtractionJob | null;
  setExtractionJob: (j: ExtractionJob | null) => void;

  // Phase 2 — benchmark job (not persisted; survives tab switches)
  benchmarkJob: BenchmarkJob | null;
  setBenchmarkJob: (j: BenchmarkJob | null) => void;

  // Shared knowledge-core cache (not persisted; enables instant cross-tab KC awareness)
  knowledgeCoreCache: KnowledgeCore | null;
  setKnowledgeCoreCache: (c: KnowledgeCore | null) => void;

  // Global toast notifications
  toasts: Toast[];
  pushToast: (t: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;

  // Recent navigation (Ctrl+P picker shortlist)
  recentPageIds: PageId[];
  recentArtifacts: RecentArtifact[];
  pushRecentArtifact: (a: Omit<RecentArtifact, "ts">) => void;
  clearRecents: () => void;

  // Phase 7 — preselect artifact in Results (consumed + cleared by Results page)
  preselectedArtifactPath: string | null;
  setPreselectedArtifactPath: (v: string | null) => void;

  // IDE theme (skins the shell only — page content stays in vs.bg dark)
  theme: ThemeId;
  setTheme: (v: ThemeId) => void;
}

export interface RecentArtifact {
  path: string; // relative to project dir
  projectId: string;
  label: string; // usually basename
  hint?: string; // parent dir for disambiguation
  ts: number;
}

const MAX_RECENT_PAGES = 8;
const MAX_RECENT_ARTIFACTS = 10;

export interface Toast {
  id: string;
  severity: "success" | "error" | "info" | "warning";
  title: string;
  description?: string;
  /** ms; 0 = persistent (user must dismiss). Defaults: success/info 4000, warning 5000, error 0. */
  timeout?: number;
}

const MAX_LOG_LINES = 800;
const MAX_METRIC_POINTS = 2000;

const defaultProfiles: LlmProfiles = {
  openai: {
    api_key: "",
    api_base: "",
    verified_models: [],
    available_models: [],
    configured: false,
    last_model: "",
  },
  anthropic: {
    api_key: "",
    api_base: "",
    verified_models: [],
    available_models: [],
    configured: false,
    last_model: "",
  },
  deepseek: {
    api_key: "",
    api_base: "",
    verified_models: [],
    available_models: [],
    configured: false,
    last_model: "",
  },
};

export const useSession = create<SessionState>()(
  persist(
    (set, get) => ({
      language: "zh",
      setLanguage: (l) => set({ language: l }),
      toggleLanguage: () =>
        set({ language: get().language === "zh" ? "en" : "zh" }),

      currentProject: null,
      projects: [],
      setCurrentProject: (p) => set({ currentProject: p }),
      setProjects: (p) => set({ projects: p }),

      llmProfiles: defaultProfiles,
      selectedModel: "",
      setLlmProfiles: (p) => set({ llmProfiles: p }),
      setSelectedModel: (key) => set({ selectedModel: key }),

      openTabs: [
        {
          id: "welcome",
          pageId: "welcome",
          title: "Welcome",
          fileName: "welcome.md",
          closable: false,
        },
      ],
      activeTabId: "welcome",
      openTab: (tab) => {
        const tabs = get().openTabs;
        if (tabs.some((t) => t.id === tab.id)) {
          set({ activeTabId: tab.id });
        } else {
          set({ openTabs: [...tabs, tab], activeTabId: tab.id });
        }
        // Track in recent list (welcome excluded — user sees it on launch, noise)
        if (tab.pageId !== "welcome") {
          const prev = get().recentPageIds.filter((id) => id !== tab.pageId);
          const next = [tab.pageId, ...prev].slice(0, MAX_RECENT_PAGES);
          set({ recentPageIds: next });
        }
      },
      closeTab: (id) => {
        const tabs = get().openTabs;
        const idx = tabs.findIndex((t) => t.id === id);
        if (idx < 0) return;
        const target = tabs[idx];
        if (!target.closable) return;
        const next = tabs.filter((t) => t.id !== id);
        let nextActive = get().activeTabId;
        if (nextActive === id) {
          nextActive = next[idx]?.id ?? next[idx - 1]?.id ?? next[0]?.id ?? null;
        }
        set({ openTabs: next, activeTabId: nextActive });
      },
      setActiveTab: (id) => set({ activeTabId: id }),
      closeAllTabs: () =>
        set({
          openTabs: [
            {
              id: "welcome",
              pageId: "welcome",
              title: "Welcome",
              fileName: "welcome.md",
              closable: false,
            },
          ],
          activeTabId: "welcome",
        }),

      explorerVisible: true,
      toggleExplorer: () => set({ explorerVisible: !get().explorerVisible }),
      activityView: "explorer",
      setActivityView: (v) => set({ activityView: v }),
      commandPaletteOpen: false,
      setCommandPaletteOpen: (v) => set({ commandPaletteOpen: v }),
      configModalOpen: false,
      setConfigModalOpen: (v) => set({ configModalOpen: v }),

      backendOnline: false,
      setBackendOnline: (v) => set({ backendOnline: v }),

      finetuneSection: "generate",
      setFinetuneSection: (s) => set({ finetuneSection: s }),

      activeTrainingSession: null,
      setActiveTrainingSession: (s) => {
        const prev = get().activeTrainingSession;
        // Reset transient state when switching sessions
        if (!s || !prev || prev.session_id !== s.session_id) {
          set({
            activeTrainingSession: s,
            trainingLogs: [],
            trainingMetrics: [],
          });
        } else {
          set({ activeTrainingSession: s });
        }
      },
      trainingLogs: [],
      appendTrainingLog: (line) => {
        const cur = get().trainingLogs;
        const next = cur.length >= MAX_LOG_LINES
          ? [...cur.slice(cur.length - MAX_LOG_LINES + 1), line]
          : [...cur, line];
        set({ trainingLogs: next });
      },
      clearTrainingLogs: () => set({ trainingLogs: [] }),
      trainingMetrics: [],
      setTrainingMetrics: (points) =>
        set({
          trainingMetrics:
            points.length > MAX_METRIC_POINTS
              ? points.slice(-MAX_METRIC_POINTS)
              : points,
        }),
      trainingPanelTab: null,
      setTrainingPanelTab: (v) => set({ trainingPanelTab: v }),

      activeEvalSession: null,
      setActiveEvalSession: (s) => {
        const prev = get().activeEvalSession;
        if (!s || !prev || prev.run_id !== s.run_id) {
          set({ activeEvalSession: s, evalLogs: [] });
        } else {
          set({ activeEvalSession: s });
        }
      },
      evalLogs: [],
      appendEvalLog: (line) => {
        const cur = get().evalLogs;
        const next =
          cur.length >= MAX_LOG_LINES
            ? [...cur.slice(cur.length - MAX_LOG_LINES + 1), line]
            : [...cur, line];
        set({ evalLogs: next });
      },
      clearEvalLogs: () => set({ evalLogs: [] }),
      evalPanelTab: null,
      setEvalPanelTab: (v) => set({ evalPanelTab: v }),

      preselectedEvalRunId: null,
      preselectedTrainSessionId: null,
      setPreselectedEvalRunId: (v) => set({ preselectedEvalRunId: v }),
      setPreselectedTrainSessionId: (v) => set({ preselectedTrainSessionId: v }),

      extractionJob: null,
      setExtractionJob: (j) => set({ extractionJob: j }),

      benchmarkJob: null,
      setBenchmarkJob: (j) => set({ benchmarkJob: j }),

      knowledgeCoreCache: null,
      setKnowledgeCoreCache: (c) => set({ knowledgeCoreCache: c }),

      toasts: [],
      pushToast: (t) => {
        const id =
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        set({ toasts: [...get().toasts, { id, ...t }] });
      },
      dismissToast: (id) =>
        set({ toasts: get().toasts.filter((x) => x.id !== id) }),

      recentPageIds: [],
      recentArtifacts: [],
      pushRecentArtifact: (a) => {
        const now = Date.now();
        const prev = get().recentArtifacts.filter(
          (x) => !(x.path === a.path && x.projectId === a.projectId)
        );
        const next = [{ ...a, ts: now }, ...prev].slice(
          0,
          MAX_RECENT_ARTIFACTS
        );
        set({ recentArtifacts: next });
      },
      clearRecents: () => set({ recentPageIds: [], recentArtifacts: [] }),

      preselectedArtifactPath: null,
      setPreselectedArtifactPath: (v) => set({ preselectedArtifactPath: v }),

      theme: "dark-plus",
      setTheme: (v) => {
        if (typeof document !== "undefined") {
          document.documentElement.dataset.theme = v;
        }
        set({ theme: v });
      },
    }),
    {
      name: "pro-ide-session",
      partialize: (s) => ({
        language: s.language,
        currentProject: s.currentProject,
        llmProfiles: s.llmProfiles,
        selectedModel: s.selectedModel,
        openTabs: s.openTabs,
        activeTabId: s.activeTabId,
        explorerVisible: s.explorerVisible,
        activityView: s.activityView,
        finetuneSection: s.finetuneSection,
        recentPageIds: s.recentPageIds,
        recentArtifacts: s.recentArtifacts,
        theme: s.theme,
      }),
      onRehydrateStorage: () => (state) => {
        // Apply persisted theme to <html data-theme> on load.
        if (state && typeof document !== "undefined") {
          // Migrate legacy theme ids (from earlier iterations) to current set.
          const valid: ThemeId[] = ["dark-plus", "light-plus", "one-dark"];
          const t = valid.includes(state.theme as ThemeId)
            ? state.theme
            : "dark-plus";
          state.theme = t as ThemeId;
          document.documentElement.dataset.theme = t;
        }
      },
    }
  )
);
