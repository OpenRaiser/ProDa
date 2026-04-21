import clsx from "clsx";
import {
  Folder,
  Sparkles,
  Stethoscope,
  Plus,
  GitMerge,
  type LucideIcon,
} from "lucide-react";
import { useSession } from "@/store/useSession";
import { useI18n } from "@/hooks/useI18n";
import type { FineTuneSection } from "@/types";
import { GenerateView } from "@/pages/finetune/GenerateView";
import { DiagnoseView } from "@/pages/finetune/DiagnoseView";
import { SupplementView } from "@/pages/finetune/SupplementView";
import { MergeView } from "@/pages/finetune/MergeView";

interface Segment {
  id: FineTuneSection;
  labelKey: string;
  fileName: string;
  icon: LucideIcon;
}

const SEGMENTS: Segment[] = [
  { id: "generate", labelKey: "ft.seg_generate", fileName: "generate.py", icon: Sparkles },
  { id: "diagnose", labelKey: "ft.seg_diagnose", fileName: "diagnose.py", icon: Stethoscope },
  { id: "supplement", labelKey: "ft.seg_supplement", fileName: "supplement.py", icon: Plus },
  { id: "merge", labelKey: "ft.seg_merge", fileName: "merge.py", icon: GitMerge },
];

export function FineTune() {
  const { t } = useI18n();
  const section = useSession((s) => s.finetuneSection);
  const setSection = useSession((s) => s.setFinetuneSection);

  return (
    <div className="h-full w-full flex flex-col bg-[var(--vs-bg)]">
      {/* Breadcrumb-style segmented control — matches VSCode editor breadcrumb feel */}
      <div className="flex items-center gap-[2px] h-[28px] px-4 border-b border-[var(--vs-border)] bg-[var(--vs-sidebar)] shrink-0">
        <Folder size={13} className="text-[#dcb67a] mr-1" />
        <span className="text-[12px] text-[var(--vs-fg-muted)] mr-2">finetune</span>
        <span className="text-[12px] text-[var(--vs-fg-subtle)] mr-2">›</span>
        {SEGMENTS.map((seg) => {
          const active = section === seg.id;
          const Icon = seg.icon;
          return (
            <button
              key={seg.id}
              onClick={() => setSection(seg.id)}
              className={clsx(
                "px-2 h-[22px] flex items-center gap-1.5 text-[12px] rounded-sm transition-colors",
                active
                  ? "bg-[var(--vs-selected)] text-white"
                  : "text-[var(--vs-fg)] hover:bg-[var(--vs-hover)]"
              )}
              title={seg.fileName}
            >
              <Icon size={12} className={active ? "text-[var(--vs-accent)]" : "text-[var(--vs-fg-muted)]"} />
              <span>{t(seg.labelKey)}</span>
            </button>
          );
        })}
        <div className="ml-auto text-[11px] text-[var(--vs-fg-subtle)] font-mono">
          {SEGMENTS.find((s) => s.id === section)?.fileName}
        </div>
      </div>

      {/* Sub-view */}
      <div className="flex-1 overflow-hidden">
        {section === "generate" && <GenerateView />}
        {section === "diagnose" && <DiagnoseView />}
        {section === "supplement" && <SupplementView />}
        {section === "merge" && <MergeView />}
      </div>
    </div>
  );
}
