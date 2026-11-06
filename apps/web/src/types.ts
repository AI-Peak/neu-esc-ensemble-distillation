export type Task = "sentiment" | "topic";
export type Label = { id: number; key: string; name: string };
export type Model = {
  available: boolean;
  reason: string | null;
  model_id: string | null;
  model_version: string | null;
  schema_id: string;
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
  id?: string;
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
  stale: boolean;
  error: string | null;
};
export type ItemPage = {
  items: Item[];
  total: number;
  page: number;
  page_size: number;
  run_id: string | null;
};
export type Filters = {
  run_id: string;
  label_source: "effective" | "ai";
  q: string;
  sentiment: string;
  topic: string;
  review_status: string;
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
  sort: "source_row",
  direction: "asc",
  page: 1,
  page_size: 25,
};
export type Summary = {
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
  status: string;
  total: number;
  completed: number;
  failed: number;
  cancel_requested: boolean;
  error: string | null;
  result?: Item | Prediction | null;
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
export const reviewName = (item: Item) => {
  const n = Object.values(item.reviews).filter(
    (r) => r && r.status !== "unreviewed",
  ).length;
  return n === 2 ? "Đã rà soát" : n === 1 ? "Duyệt một phần" : "Chưa rà soát";
};
