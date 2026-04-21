import { useEffect } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { TitleBar } from "./TitleBar";
import { ActivityBar } from "./ActivityBar";
import { Explorer } from "./Explorer";
import { TabBar } from "./TabBar";
import { StatusBar } from "./StatusBar";
import { CommandPalette } from "./CommandPalette";
import { BottomPanel } from "./BottomPanel";
import { EditorArea } from "./EditorArea";
import { LlmConfigModal } from "@/components/modals/LlmConfigModal";
import { Toaster } from "@/components/common/Toaster";
import { useSession } from "@/store/useSession";
import { api } from "@/api/client";
import { useTrainingWatcher } from "@/hooks/useTrainingWatcher";
import { useEvalWatcher } from "@/hooks/useEvalWatcher";

export function IdeShell() {
  const explorerVisible = useSession((s) => s.explorerVisible);
  const setCommandPaletteOpen = useSession((s) => s.setCommandPaletteOpen);
  const setBackendOnline = useSession((s) => s.setBackendOnline);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+Shift+P or Cmd+Shift+P → command palette
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      // Ctrl+P (without shift) → also open palette (like VSCode quick-open)
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      // Ctrl+B → toggle explorer
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "b") {
        e.preventDefault();
        useSession.getState().toggleExplorer();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [setCommandPaletteOpen]);

  // Training watcher — global poller + SSE subscription for active training session
  useTrainingWatcher();
  // Eval watcher — same pattern for OpenCompass eval runs
  useEvalWatcher();

  // Apply theme to <html data-theme> on mount + whenever it changes.
  const theme = useSession((s) => s.theme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme || "dark-plus";
  }, [theme]);

  // Health polling
  useEffect(() => {
    const ping = async () => {
      try {
        await api.get("/health", { timeout: 3000 });
        setBackendOnline(true);
      } catch {
        setBackendOnline(false);
      }
    };
    ping();
    const iv = setInterval(ping, 8000);
    return () => clearInterval(iv);
  }, [setBackendOnline]);

  return (
    <div className="h-screen w-screen flex flex-col bg-[var(--vs-bg)] text-[var(--vs-fg)]">
      <TitleBar />
      <div className="flex-1 flex min-h-0">
        <ActivityBar />
        <div className="flex-1 min-w-0">
          <PanelGroup direction="horizontal" autoSaveId="pro-ide-main">
            {explorerVisible && (
              <>
                <Panel
                  id="sidebar"
                  defaultSize={18}
                  minSize={12}
                  maxSize={40}
                  order={1}
                >
                  <Explorer />
                </Panel>
                <PanelResizeHandle className="w-[1px] bg-[var(--vs-sidebar)] hover:bg-[var(--vs-statusbar)] transition-colors" />
              </>
            )}
            <Panel id="main" defaultSize={82} minSize={40} order={2}>
              <PanelGroup direction="vertical" autoSaveId="pro-ide-main-vert">
                <Panel id="editor" defaultSize={72} minSize={30} order={1}>
                  <div className="h-full flex flex-col bg-[var(--vs-bg)]">
                    <TabBar />
                    <div className="flex-1 min-h-0 overflow-hidden">
                      <EditorArea />
                    </div>
                  </div>
                </Panel>
                <PanelResizeHandle className="h-[1px] bg-[var(--vs-sidebar)] hover:bg-[var(--vs-statusbar)] transition-colors" />
                <Panel
                  id="bottom"
                  defaultSize={28}
                  minSize={10}
                  maxSize={70}
                  order={2}
                >
                  <BottomPanel />
                </Panel>
              </PanelGroup>
            </Panel>
          </PanelGroup>
        </div>
      </div>
      <StatusBar />
      <CommandPalette />
      <LlmConfigModal />
      <Toaster />
    </div>
  );
}
