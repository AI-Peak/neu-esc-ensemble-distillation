export type Task = "sentiment" | "topic";
export type Label = { id: number; key: string; name: string };
export type Model = {
  available: boolean;
  reason: string | null;
  model_id: string | null;
  model_version: string | null;
  schema_id: string;
  backbone?: string | null;
  setup?: string | null;
  preprocessing?: {
    kind: string;
    equivalence?: string;
  } | null;
  provenance?: {
    seed: number;
    best_epoch: number;
    oof_status?: string;
  } | null;
};
export type Profile = {
  id: string;
  schema_id: string;
  name: string;
  description: string;
  sentiment: Label[];
  topic: Label[];
  model: Model;
};
export type Dataset = {
  skipped_count?: number;
  id: string;
  name: string;
  profile: string;
  schema_id: string;
  created_at: string;
  updated_at: string;
  item_count: number;
  processed_count: number;
  reviewed_count: number;
  partial_review_count: number;
  latest_run_id: string | null;
};
export type Prediction = {
  execution_identity?: Record<string, unknown>;
  item_id?: string;
  revision_id?: string;
  id?: string;
  run_id?: string;
  created_at?: string;
  model_id: string;
  model_version: string;
  schema_id: string;
  sentiment: { label_id: number; scores: number[] };
  topic: { label_id: number; scores: number[] };
  token_count_before_truncation: number;
  truncated: boolean;
  warnings: string[];
  duration_ms: number;
};
export type Review = {
  revision: number;
  status: "unreviewed" | "confirmed" | "corrected";
  label_id: number | null;
  note: string;
  source_prediction_id?: string | null;
  created_at: string;
  task?: Task;
  input_revision?: number;
  revision_id?: string;
};
export type ReviewSignalFilter =
  | "all"
  | "model_uncertain"
  | "sentiment_uncertain"
  | "topic_uncertain"
  | "truncated"
  | "pending_signal_review";
export const REVIEW_SIGNAL_VALUES: readonly ReviewSignalFilter[] = [
  "all",
  "model_uncertain",
  "sentiment_uncertain",
  "topic_uncertain",
  "truncated",
  "pending_signal_review",
] as const;
export const normalizeReviewSignalFilter = (
  value: unknown,
): ReviewSignalFilter => {
  for (const candidate of REVIEW_SIGNAL_VALUES) {
    if (value === candidate) return candidate;
  }
  return "all";
};
export type ReviewRelation =
  | "unreviewed"
  | "current_prediction"
  | "manual"
  | "other_prediction";
export type TaskReviewSignal = {
  state: "flagged" | "clear" | "unavailable";
  top1_label_id: number | null;
  top2_label_id: number | null;
  top1: number | null;
  top2: number | null;
  margin: number | null;
  reasons: string[];
  review_relation: ReviewRelation;
};
export type ReviewSignals = {
  policy_id: string;
  policy_hash: string;
  experimental: boolean;
  prediction_id: string | null;
  sentiment: TaskReviewSignal;
  topic: TaskReviewSignal;
  truncated: boolean | null;
  pending_signal_review: boolean;
};
export type ReviewPolicy = {
  id: string;
  hash: string;
  experimental: boolean;
  schema_id: string;
  sentiment: { top1_min: number; margin_min: number };
  topic: { top1_min: number; margin_min: number };
};
export type Item = {
  id: string;
  dataset_id: string;
  revision_id: string;
  revision: number;
  source_row: number;
  text: string;
  metadata: Record<string, unknown>;
  reference: Partial<Record<Task, { label_id: number; source: string }>>;
  prediction: Prediction | null;
  reviews: Record<Task, Review | null>;
  effective: Record<Task, number | null>;
  review_signals?: ReviewSignals;
  stale: boolean;
  error: string | null;
};
export type RevisionScope = "current" | "run";
export type AttentionTopic = {
  topic_id: number;
  topic_count: number;
  eligible_count: number;
  negative_count: number;
  toxic_count: number | null;
  negative_rate: number | null;
  missing_sentiment_count: number;
  small_sample: boolean;
};
export type Attention = {
  ranking_rule: string;
  small_sample_threshold: number;
  negative_label_id: number;
  toxic_label_id: number | null;
  filtered_count: number;
  eligible_count: number;
  missing_topic_count: number;
  missing_sentiment_with_topic_count: number;
  topics: AttentionTopic[];
};
export type ItemPage = {
  scope_token?: string;
  dataset_id?: string;
  label_source?: string;
  items: Item[];
  total: number;
  page: number;
  page_size: number;
  run_id: string | null;
  resolved_run_id: string | null;
  revision_scope: RevisionScope;
  run_status: string | null;
};
export type Filters = {
  run_id: string;
  label_source: "effective" | "ai";
  q: string;
  sentiment: string;
  topic: string;
  review_status: string;
  review_signal: ReviewSignalFilter;
  sort: string;
  direction: "asc" | "desc";
  page: number;
  page_size: number;
};
export const defaultFilters: Filters = {
  run_id: "",
  label_source: "effective",
  q: "",
  sentiment: "",
  topic: "",
  review_status: "all",
  review_signal: "all",
  sort: "source_row",
  direction: "asc",
  page: 1,
  page_size: 25,
};
export type Summary = {
  scope_token?: string;
  dataset_id?: string;
  total: number;
  processed: number;
  reviewed: number;
  partial_review: number;
  unreviewed: number;
  truncated: number;
  errors: number;
  sentiment: { label_id: number; count: number }[];
  topic: { label_id: number; count: number }[];
  cross: { sentiment: number; topic: number; count: number }[];
  denominator: Record<Task | "cross", number>;
  run_id: string | null;
  label_source: string;
  resolved_run_id: string | null;
  revision_scope: RevisionScope;
  run_status: string | null;
  attention: Attention;
  review_policy?: ReviewPolicy;
};
export type Run = {
  id: string;
  dataset_id: string;
  model_id: string;
  model_version: string;
  status: string;
  total: number;
  completed: number;
  failed: number;
  job_id: string;
  created_at: string;
};
export type Job = {
  id: string;
  run_id: string;
  kind?: "analysis" | "quick" | "sensitivity";
  status: string;
  total: number;
  completed: number;
  failed: number;
  cancel_requested: boolean;
  error: string | null;
  result?: Item | Prediction | null;
};
export type SensitivityScoreDelta = {
  label_id: number;
  before: number;
  after: number;
  delta: number;
};
export type SensitivityTaskComparison = {
  baseline_label_id: number;
  variant_label_id: number;
  scores: SensitivityScoreDelta[];
};
export type SensitivityExperimentError = {
  code: string;
  message: string;
};
export type SensitivityExperimentResult = {
  baseline: { text: string; prediction: Prediction };
  variant: { text: string; prediction: Prediction };
  model_input_equal: boolean;
  comparison: Record<Task, SensitivityTaskComparison>;
  warnings: string[];
};
export type SensitivityExperiment = {
  experiment_id: string;
  job_id: string;
  status: string;
  completed: number;
  total: number;
  failed: number;
  cancel_requested: boolean;
  source_stale: boolean;
  active_model_changed: boolean;
  source: {
    item_id: string;
    revision_id: string;
    revision: number;
    text_sha256: string;
    selected_run_id: string | null;
    resolved_run_id: string | null;
    prediction_id: string | null;
  };
  selection: {
    start_utf16: number;
    end_utf16: number;
    text: string;
  };
  baseline_text: string;
  variant_text: string;
  execution: {
    profile: string;
    schema_id: string;
    model_id: string;
    model_version: string;
    manifest_sha256: string;
    preprocessing_sha256: string;
    mode: string;
    baseline_recomputed: boolean;
    source_model_changed: boolean;
  };
  expires_at: string | null;
  error: SensitivityExperimentError | null;
  result: SensitivityExperimentResult | null;
};
export type CreateSensitivityExperimentBody = {
  revision_id: string;
  expected_revision: number;
  text_sha256: string;
  run_id: string | null;
  source_prediction_id: string | null;
  selection: {
    start_utf16: number;
    end_utf16: number;
    text: string;
  };
};
export type Preview = {
  preview_id: string;
  columns: string[];
  rows: Record<string, string>[];
  total_rows: number;
  delimiter: string;
  issues: { row: number; code: string; message: string }[];
  expires_at: string;
};
export const labelName = (
  profile: Profile | undefined,
  task: Task,
  id: number | null | undefined,
) =>
  id == null
    ? "Chưa có nhãn"
    : (profile?.[task].find((l) => l.id === id)?.name ?? `Nhãn ${id}`);
export const activeJob = (status: string) =>
  ["queued", "pending", "running", "loading_model", "cancelling"].includes(
    status,
  );
export const date = (v: string) =>
  new Date(v).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export type AttributionTarget =
  | { kind: "polarity_margin" }
  | { kind: "label_score"; label_id: number };

export type AttributionGroup = {
  id: string;
  text: string;
  start_utf16: number;
  end_utf16: number;
  token_indices: number[];
  contribution: number;
};

export type AttributionAggregate = {
  baseline_value: number;
  total_contribution: number;
  target_output: number;
  additivity_residual: number;
  hidden_groups_contribution?: number;
};

export type AttributionMethod = {
  id: string;
  version: string;
  grouping_version: string;
  baseline_policy: string;
  target: AttributionTarget;
  unit: string;
  seed: number;
  requested_permutations: number;
  completed_permutations: number;
  evaluated_coalitions: number;
};

export type AttributionCoverage = {
  truncated: boolean;
  input_token_count: number;
  mapping_status: string;
  analyzed_spans: number;
  fixed_token_policy: string;
  explained_token_indices: number[];
};

export type AttributionResponse = {
  attribution_id: string;
  status: "queued" | "running" | "completed" | "cancelled" | "failed" | "unsupported";
  source?: {
    source_job_id: string;
    source_prediction_id: string;
    item_id: string;
    revision_id: string;
    run_id: string;
    text_hash: string;
    profile_id: string;
    schema_id: string;
    model_id: string;
    model_version: string;
    execution_identity?: Record<string, unknown>;
  };
  method?: AttributionMethod | null;
  coverage?: AttributionCoverage | null;
  groups: AttributionGroup[];
  aggregate?: AttributionAggregate | null;
  progress: {
    completed_batches: number;
    total_batches: number;
  };
  error?: {
    code: string;
    message: string;
  } | null;
};

export type NetworkNode = {
  id: string;
  label: string;
  count: number;
  community: number;
  x: number;
  y: number;
  item_ids: string[];
};

export type NetworkEdge = {
  id: string;
  source: string;
  target: string;
  weight: number;
  item_ids: string[];
};

export type NetworkCommunity = {
  id: number;
  label: string;
  color: string;
  count: number;
  members: string[];
  item_ids: string[];
};

export type NetworkResponse = {
  network_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  filter_signature: string;
  network_version: string;
  params: Record<string, unknown>;
  scope_item_count: number;
  error?: {code: string; message: string} | null;
  dataset_id: string;
  scope_token: string;
  label_source: string;
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  communities: NetworkCommunity[];
  total_nodes: number;
  total_edges: number;
  source_item_count: number;
};
export const reviewName = (item: Item) => {
  const n = Object.values(item.reviews).filter(
    (r) => r && r.status !== "unreviewed",
  ).length;
  return n === 2 ? "Đã rà soát" : n === 1 ? "Duyệt một phần" : "Chưa rà soát";
};
