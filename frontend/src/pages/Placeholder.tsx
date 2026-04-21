import { Construction, FileCode2, ArrowRight } from "lucide-react";
import type { PageId } from "@/types";
import { useI18n } from "@/hooks/useI18n";
import { WORKFLOW_STEPS } from "@/lib/workflow";

const FEATURES: Partial<Record<PageId, string[]>> = {
  data_processing: [
    "文档上传 (PDF / TXT / MD / DOCX / JSON)",
    "JSON 字段筛选与分块配置",
    "L1 概念 / L2 关系 / L3 推理链路抽取",
    "表格浏览、编辑与导出",
  ],
  benchmark: [
    "基于 L3 推理链生成选择题 Benchmark",
    "目标问题数 / 并发度 / 重试策略",
    "预览、导出、历史缓存",
  ],
  finetune: [
    "QA / 单选 / 多选 / 判断题比例配置",
    "L2 窗口采样 / L1 Top-N 约束",
    "并行生成、断点续跑、结果审核",
    "诊断报告模式（OpenCompass 错误样本）",
  ],
  fine_tuning: [
    "LLaMA-Factory 集成",
    "ShareGPT 格式转换 + 预览",
    "训练参数 / 配置文件生成",
    "训练启动 + 实时日志",
    "训练历史与产出模型追踪",
  ],
  opencompass: [
    "项目 Benchmark / 自定义 Benchmark 评测",
    "本地模型 / API 模型",
    "自动探测 LoRA / PEFT / 最新二轮模型",
    "实时日志 + 可视化榜单 + 对比",
  ],
  results: [
    "Benchmark / FineTune 数据规模统计",
    "OpenCompass 历史运行一览",
    "详情查看与下载",
  ],
};

export function Placeholder({ pageId }: { pageId: PageId }) {
  const { t } = useI18n();
  const step = WORKFLOW_STEPS.find((s) => s.id === pageId);
  const features = FEATURES[pageId] ?? [];

  return (
    <div className="h-full w-full overflow-auto bg-[var(--vs-bg)]">
      <div className="max-w-[900px] mx-auto px-12 py-10">
        <div className="flex items-center gap-3 mb-6">
          <FileCode2 size={28} className="text-[#519aba]" />
          <div>
            <h1 className="text-[22px] font-light text-[var(--vs-fg-strong)]">
              {step ? t(step.key) : pageId}
            </h1>
            {step && (
              <div className="font-mono text-[12px] text-[var(--vs-fg-muted)] mt-1">
                {step.file}
              </div>
            )}
          </div>
        </div>

        <div className="vs-card p-6 border-dashed">
          <div className="flex items-center gap-2 text-[#dcdcaa] mb-3">
            <Construction size={18} />
            <span className="text-[14px] font-semibold">
              {t("placeholder.coming_soon")}
            </span>
          </div>
          <div className="text-[13px] text-[var(--vs-fg)] mb-3">
            {t("placeholder.will_have")}
          </div>
          <ul className="space-y-2">
            {features.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px]">
                <ArrowRight
                  size={14}
                  className="mt-0.5 shrink-0 text-[var(--vs-accent)]"
                />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
