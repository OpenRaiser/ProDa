import type { PageId, WorkflowStep } from "@/types";

export const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "data_processing",
    key: "workflow.step1",
    file: "1_data_processing.py",
    stepNumber: 1,
  },
  {
    id: "benchmark",
    key: "workflow.step2",
    file: "2_benchmark.py",
    stepNumber: 2,
  },
  {
    id: "finetune",
    key: "workflow.step3",
    file: "3_finetune.py",
    stepNumber: 3,
  },
  {
    id: "fine_tuning",
    key: "workflow.step5",
    file: "5_fine_tuning.py",
    stepNumber: 5,
  },
  {
    id: "opencompass",
    key: "workflow.step6",
    file: "6_opencompass.py",
    stepNumber: 6,
  },
  {
    id: "results",
    key: "workflow.step7",
    file: "7_results.py",
    stepNumber: 7,
  },
  {
    id: "one_click_deploy",
    key: "workflow.step8",
    file: "8_one_click_deploy.py",
    stepNumber: 8,
  },
];

export function findWorkflowStep(id: PageId): WorkflowStep | undefined {
  return WORKFLOW_STEPS.find((s) => s.id === id);
}
