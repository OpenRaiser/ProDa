export interface Project {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface LlmProfile {
  api_key: string;
  api_base: string;
  verified_models: string[];
  available_models: string[];
  configured: boolean;
  last_model: string;
}

export type LlmProfiles = Record<string, LlmProfile>;

export interface ProjectState {
  llm_profiles: LlmProfiles;
  selected_model: string;
  knowledge_core: unknown;
  benchmark_mcq: unknown[];
  finetune_data: unknown[];
  json_fields: string[];
}

export type PageId =
  | "welcome"
  | "data_processing"
  | "benchmark"
  | "finetune"
  | "fine_tuning"
  | "opencompass"
  | "results"
  | "llm_config";

export interface Tab {
  id: string;
  pageId: PageId;
  title: string;
  fileName: string;
  icon?: string;
  closable: boolean;
  dirty?: boolean;
}

export type Language = "zh" | "en";

export type ThemeId = "dark-plus" | "light-plus" | "one-dark";

export interface WorkflowStep {
  id: PageId;
  key: string;
  file: string;
  stepNumber?: number;
}

export interface UploadedFileMeta {
  file_id: string;
  filename: string;
  size: number;
  ext: string;
  stored_at: string;
}

export type ProcessingMode = "auto" | "merge" | "per_chunk";

export interface LlmCtx {
  provider: string;
  model: string;
  api_key: string;
  api_base: string;
}

export interface StartExtractionBody {
  file_ids: string[];
  json_fields: string[];
  chunk_size: number;
  chunk_overlap: number;
  processing_mode: ProcessingMode;
  merge_threshold: number;
  parallel_chunks: boolean;
  max_workers: number;
  llm: LlmCtx;
}

export type JobStatus = "pending" | "running" | "done" | "error" | "cancelled";

export interface ExtractionJob {
  id: string;
  project_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  total: number;
  done: number;
  effective_mode: ProcessingMode;
  result: KnowledgeCore | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface L1Concept {
  concept_id?: string;
  term: string;
  definition?: string;
  [key: string]: unknown;
}

export interface L2Statement {
  statement_id?: string;
  parent_chain_id?: string;
  subject: string;
  predicate: string;
  object: string;
  [key: string]: unknown;
}

export interface L3Chain {
  chain_id?: string;
  domain_context?: string;
  process_name?: string;
  narrative_summary?: string;
  steps: string[];
  [key: string]: unknown;
}

export interface KnowledgeCore {
  l1_concepts: L1Concept[];
  l2_statements: L2Statement[];
  l3_chains: L3Chain[];
  statistics?: {
    total_chains?: number;
    total_statements?: number;
    total_concepts?: number;
    text_length?: number;
    num_chunks?: number;
    processing_mode?: string;
  };
}

export interface MCQItem {
  sample_id?: string;
  chain_id?: string;
  domain_context?: string;
  process_name?: string;
  question: string;
  options: {
    A: string;
    B: string;
    C: string;
    D: string;
  };
  answer: string;
  explanation?: string;
  [key: string]: unknown;
}

export interface BenchmarkStats {
  submitted?: number;
  succeeded?: number;
  failed?: number;
  duplicates_dropped?: number;
  semantic_dedup_dropped?: number;
  refill_rounds?: number;
  adaptive_enabled?: boolean;
  initial_workers?: number;
  min_workers?: number;
  max_workers_seen?: number;
  final_workers?: number;
  worker_adjustments?: number;
  cancelled?: boolean;
}

export interface BenchmarkJob {
  id: string;
  project_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  total: number;
  done: number;
  chains?: number;
  questions_per_chain?: number;
  result: {
    mcqs: MCQItem[];
    stats: BenchmarkStats;
  } | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartBenchmarkBody {
  max_workers: number;
  questions_per_chain: number;
  temperature: number;
  retries: number;
  max_refill_rounds?: number;
  adaptive_concurrency?: boolean;
  llm: LlmCtx;
}

// ========== FineTune / Diagnosis (Phase 4) ==========

export type FineTuneQuestionType =
  | "qa"
  | "single_choice"
  | "multiple_choice"
  | "true_false";

export interface FineTuneRow {
  question_type?: FineTuneQuestionType | string;
  question?: string;
  answer?: string;
  options?: Record<string, string>;
  explanation?: string;
  l2_statement_id?: string;
  l2_statement_ids?: string[];
  linked_concepts?: string[];
  meta_style?: string;
  [key: string]: unknown;
}

export interface FineTuneStats {
  submitted?: number;
  succeeded_jobs?: number;
  failed_jobs?: number;
  refill_rounds?: number;
  adaptive_enabled?: boolean;
  initial_workers?: number;
  min_workers?: number;
  max_workers_seen?: number;
  final_workers?: number;
  worker_adjustments?: number;
  batch_size?: number;
  l2_window_size?: number;
  l1_topn?: number;
  empty_windows?: number;
  cancelled?: boolean;
}

export interface FineTuneJob {
  id: string;
  project_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  total: number;
  done: number;
  total_samples?: number;
  qa_ratio?: number;
  choice_ratio?: number;
  true_ratio?: number;
  result: {
    rows: FineTuneRow[];
    stats: FineTuneStats;
  } | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartFineTuneBody {
  total_samples: number;
  qa_ratio: number;
  choice_ratio: number;
  single_choice_ratio: number;
  true_ratio: number;
  author_notes: string;
  max_workers: number;
  retries: number;
  max_refill_rounds: number;
  adaptive_concurrency: boolean;
  batch_size: number;
  l2_window_size: number;
  l1_topn: number;
  allow_l2_reuse_after_exhausted: boolean;
  llm: LlmCtx;
}

export interface OpenCompassRun {
  source: "opencompass" | "uploaded";
  run_id: string;
  created_at: string;
  success: boolean;
  result_file: string;
}

export interface EvalModel {
  abbr: string;
  is_local: boolean;
  enabled: boolean;
}

export interface DiagnosisReportSummary {
  report_id: string;
  run_id: string;
  model_name: string;
  created_at: string;
  report_file: string;
  accuracy: number;
  total_samples: number;
  error_samples_count: number;
  diagnosis_model: string;
}

export interface DiagnosisReportDetail {
  model_name?: string;
  timestamp?: string;
  total_samples?: number;
  correct_samples?: number;
  error_samples_count?: number;
  accuracy?: number;
  subject_metrics?: Record<string, unknown>;
  error_patterns?: {
    by_subject?: Record<string, number>;
    [key: string]: unknown;
  };
  error_samples?: Array<Record<string, unknown>>;
  diagnosed_samples?: Array<Record<string, unknown>>;
  llm_diagnosis_issue_distribution?: Record<string, number>;
  recommendations?: unknown;
  [key: string]: unknown;
}

export interface DiagnosisJobExtra {
  kind?: "report" | "supplement";
  target_model?: string;
  run_id?: string;
  report_id?: string;
}

export interface DiagnosisJob {
  id: string;
  project_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  total: number;
  done: number;
  kind?: "report" | "supplement";
  target_model?: string;
  run_id?: string;
  report_id?: string;
  result:
    | {
        report_id?: string;
        report_file?: string;
        accuracy?: number;
        total_samples?: number;
        error_samples_count?: number;
        dataset_id?: string;
        data_file?: string;
        row_count?: number;
        stats?: SupplementStats;
      }
    | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartReportBody {
  result_file: string;
  target_model_abbr: string;
  run_id: string;
  max_diagnose: number;
  max_workers: number;
  temperature: number;
  max_tokens: number;
  retries: number;
  llm: LlmCtx;
}

export interface IssueWindowRow {
  qa: number;
  choice: number;
  tf: number;
}

export interface SupplementStats {
  tasks_total?: number;
  tasks_failed?: number;
  generated_rows?: number;
  type_counts?: { qa?: number; choice?: number; tf?: number };
  [key: string]: unknown;
}

export interface SupplementDataset {
  dataset_id: string;
  created_at: string;
  report_id: string;
  report_file: string;
  report_created_at?: string;
  data_file: string;
  row_count: number;
  issue_windows: {
    concept_gap: IssueWindowRow;
    capability_deficit: IssueWindowRow;
  };
  stats: SupplementStats;
}

export interface StartSupplementBody {
  report_id: string;
  max_error_samples: number;
  max_workers: number;
  max_tokens: number;
  retries: number;
  concept_gap: IssueWindowRow;
  capability_deficit: IssueWindowRow;
  llm: LlmCtx;
}

export interface MergeBody {
  dataset_id: string;
  target_total: number;
  diagnostic_ratio: number;
  mix_with_original: boolean;
  exclude_same_l2: boolean;
  fallback_random_if_insufficient: boolean;
  random_seed: number;
}

export interface MergeStats {
  target_total?: number;
  diagnostic_selected?: number;
  original_selected?: number;
  original_filtered_pool?: number;
  fallback_used?: number;
  [key: string]: unknown;
}

export interface FlowState {
  merged_ready?: boolean;
  merged_at?: string;
  merged_rows?: number;
  merged_file?: string;
  source_dataset_id?: string;
  source_report_id?: string;
  [key: string]: unknown;
}

export interface MergeResponse {
  merged_file: string;
  merged_count: number;
  stats: MergeStats;
  flow_state: FlowState;
}

export type FineTuneSection = "generate" | "diagnose" | "supplement" | "merge";

// ========== Phase 5 — Fine-Tuning (LLaMA-Factory) ==========

export interface EnvCheck {
  llamafactory_path: string;
  llamafactory_path_ok: boolean;
  cli: "llamafactory-cli" | "python_src";
  cuda_home: string;
  cuda_available: boolean;
  gpu_count: number;
  gpus: Array<{ index: number; name: string; memory_mb: number }>;
  torch_version: string;
  python: string;
  platform: string;
  model_root: string;
  model_root_ok: boolean;
  settings: Record<string, unknown>;
}

export interface EnvSettings {
  llamafactory_path?: string;
  model_root?: string;
  [key: string]: unknown;
}

export interface TrainDataset {
  name: string;
  source: "session" | "file";
  path: string;
  row_count: number;
  is_sharegpt: boolean;
}

export type FineTuningType = "lora" | "qlora" | "full";

export interface TrainingConfig {
  dataset_source: "session" | "file";
  dataset_path: string;
  dataset_name: string;

  model_path: string;
  template: string;

  finetuning_type: FineTuningType;
  lora_rank: number;
  lora_alpha: number;
  lora_dropout: number;

  learning_rate: number;
  warmup_ratio: number;
  num_train_epochs: number;
  per_device_train_batch_size: number;
  gradient_accumulation_steps: number;
  cutoff_len: number;
  max_samples: number;
  logging_steps: number;
  save_steps: number;

  nproc_per_node: number;
}

export interface TrainingSession {
  session_id: string;
  pid: number;
  status?: "running" | "finished" | "stopped_or_failed";
  cmd?: string[];
  log_path: string;
  cfg_path: string;
  output_dir: string;
  dataset_name: string;
  model_path: string;
  model_tag?: string;
  finetuning_type: FineTuningType;
  nproc_per_node?: number;
  master_port?: number;
  cuda_home?: string;
  started_at: number;
  ended_at?: number | null;
  alive?: boolean;
  lora_rank?: number;
  lora_alpha?: number;
  lora_dropout?: number;
  learning_rate?: number;
  warmup_ratio?: number;
  epochs?: number;
  batch_size?: number;
  grad_accum?: number;
  max_samples?: number;
  template?: string;
}

export interface TrainingMetricsPoint {
  idx: number;
  step: number;
  total_steps?: number;
  loss?: number;
  lr?: number;
}

export interface TrainingMetrics {
  source: "jsonl" | "stdout";
  points: TrainingMetricsPoint[];
}

export interface OutputTreeEntry {
  name: string;
  kind: "dir" | "file";
  size: number;
  step?: number;
}

export interface PreviewYamlResponse {
  yaml: string;
  output_dir: string;
  template: string;
  model_tag: string;
  dataset_tag: string;
}

export interface StartTrainingResponse {
  session_id: string;
  pid: number;
  active: TrainingSession;
}

// ========== Phase 6 — OpenCompass Evaluation ==========

export interface EvalEnvCheck {
  opencompass_path: string;
  opencompass_path_ok: boolean;
  cuda_home: string;
  cuda_available: boolean;
  gpu_count: number;
  gpus: Array<{ index: number; name: string; memory_mb: number }>;
  torch_version: string;
  python: string;
  platform: string;
  settings: { opencompass_path?: string; [k: string]: unknown };
}

export interface EvalBenchmark {
  source: "state" | "upload";
  name: string;
  path: string;
  row_count: number;
  mtime?: number;
}

export interface PeftCandidate {
  adapter_path: string;
  base_model: string;
  name: string;
  relative: string;
}

export interface FlowSuggestion {
  kind: "lora" | "full";
  path: string;
  peft_path: string;
  abbr: string;
}

export interface EvalModel {
  enabled: boolean;
  is_local: boolean;
  abbr: string;
  path: string;
  peft_path: string;
  api_key: string;
  api_base: string;
  temperature: number;
  max_out_len: number;
  query_per_second: number;
  num_procs: number;
  batch_size: number;
  num_gpus: number;
}

export interface EvalConfig {
  benchmark_source: "state" | "upload";
  benchmark_path: string;
  models: EvalModel[];
  max_samples: number | null;
  dataset_abbr: string;
  work_dir: string;
}

export interface EvalPreviewResponse {
  run_id: string;
  cfg_path: string;
  benchmark_json: string;
  work_dir: string;
  opencompass_dir: string;
  models: EvalModel[];
  row_count: number;
  yaml: string;
}

export interface EvalSession {
  run_id: string;
  pid: number;
  status?: "running" | "finished" | "stopped_or_failed";
  cfg_path: string;
  benchmark_json: string;
  work_dir: string;
  opencompass_dir: string;
  log_path: string;
  models: EvalModel[];
  created_at: string;
  started_at: number;
  ended_at?: number | null;
  alive?: boolean;
  result_file?: string;
  summary_file?: string;
  success?: boolean;
}

export interface LeaderboardRow {
  model: string;
  accuracy: number;
  rank: number;
  [k: string]: unknown;
}

export interface EvalVizPayload {
  leaderboard?: LeaderboardRow[];
  per_dataset?: Record<string, Record<string, number>>;
  raw?: unknown;
}

export interface EvalResult {
  run_id: string;
  status: "running" | "finished" | "stopped_or_failed";
  created_at: string;
  ended_at?: string;
  config_path?: string;
  benchmark_json: string;
  opencompass_dir: string;
  work_dir: string;
  models: EvalModel[];
  result: {
    success: boolean;
    returncode?: number | null;
    summary_file?: string;
    summary_data?: unknown;
  };
  viz?: EvalVizPayload;
}

export interface EvalSampleRow {
  model: string;
  idx: number;
  sample_id: string;
  question: string;
  options: Record<string, string> | unknown[];
  gold: string;
  prediction: string;
  pass: boolean;
  subject: string;
  process_name?: string;
  question_type: string;
  knowledge_node: string;
  explanation?: string;
}

export interface SampleFacets {
  models: string[];
  subjects: string[];
  question_types: string[];
}

export interface SampleAnnotation {
  sample_id: string;
  model: string;
  issue_type: "concept_gap" | "capability_deficit" | "unlabeled";
  note: string;
  created_at: string;
  updated_at: string;
}

// ========== Phase 7 — Workspace Results ==========

export type TimelineKind =
  | "train"
  | "eval"
  | "diag"
  | "supplement"
  | "merge";

export type TimelineStatus = "running" | "finished" | "stopped_or_failed" | "info";

export interface TimelineTarget {
  page?: string;
  session_id?: string;
  run_id?: string;
  report_id?: string;
  dataset_id?: string;
  finetune_section?: "generate" | "diagnose" | "supplement" | "merge";
}

export interface TimelineEvent {
  id: string;
  kind: TimelineKind;
  title: string;
  status: TimelineStatus | string;
  timestamp: number;
  target: TimelineTarget;
  metadata: Record<string, unknown>;
}

export interface ArtifactNode {
  name: string;
  kind: "dir" | "file";
  relative: string;
  size: number;
  mtime: number;
  file_count?: number;
  suffix?: string;
  is_text?: boolean;
  mime?: string;
  children?: ArtifactNode[];
}

export interface DashboardSummary {
  kc: { l1: number; l2: number; l3: number };
  benchmark: { count: number; by_type: Record<string, number> };
  finetune: { count: number; by_type: Record<string, number> };
  training: {
    total: number;
    finished: number;
    failed: number;
    running: number;
    latest_model_dir: string;
  };
  evaluation: {
    total: number;
    finished: number;
    failed: number;
    running: number;
    best_accuracy: number | null;
    best_model: string | null;
  };
  flow: Record<string, unknown>;
}

export interface ProjectDashboard {
  project: Project;
  summary: DashboardSummary;
  timeline: TimelineEvent[];
  artifacts: ArtifactNode;
}

export interface ArtifactFile {
  name: string;
  relative: string;
  kind: "file";
  size: number;
  mtime: number;
  suffix: string;
  is_text: boolean;
  mime: string;
  text: string | null;
  reason?: string;
}
