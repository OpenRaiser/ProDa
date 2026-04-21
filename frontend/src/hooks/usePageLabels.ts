import type { PageId, Tab } from "@/types";
import { useI18n } from "./useI18n";
import { WORKFLOW_STEPS } from "@/lib/workflow";

export function usePageLabels() {
  const { t } = useI18n();

  const pageTitle = (pageId: PageId): string => {
    switch (pageId) {
      case "welcome":
        return "Welcome";
      case "llm_config":
        return t("llm.title");
      default: {
        const step = WORKFLOW_STEPS.find((s) => s.id === pageId);
        return step ? t(step.key) : pageId;
      }
    }
  };

  const pageFile = (pageId: PageId): string => {
    return t(`page.${pageId}.file`, `${pageId}.py`);
  };

  const buildTab = (pageId: PageId): Tab => ({
    id: pageId,
    pageId,
    title: pageTitle(pageId),
    fileName: pageFile(pageId),
    closable: pageId !== "welcome",
  });

  return { pageTitle, pageFile, buildTab };
}
