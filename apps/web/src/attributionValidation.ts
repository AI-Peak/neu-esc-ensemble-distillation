import type { AttributionResponse, AttributionTarget, Item, Prediction, Profile } from "./types";

export type AttributionSource = {
  jobId: string;
  item: Item;
  prediction: Prediction;
  profile: Profile;
};

export function defaultAttributionTarget(prediction: Prediction, profile: Profile): AttributionTarget {
  const label = profile.sentiment.find((candidate) => candidate.id === prediction.sentiment.label_id);
  if (!label) throw new Error("Nhãn cảm xúc không thuộc hệ nhãn đang xem.");
  return ["positive", "negative"].includes(label.key.toLowerCase())
    ? { kind: "polarity_margin" }
    : { kind: "label_score", label_id: label.id };
}

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
};
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const integer = (value: unknown): value is number => finite(value) && Number.isInteger(value);
const invalid = () => { throw new Error("Kết quả đóng góp không khớp nguồn hoặc có số/vị trí không hợp lệ. Hãy phân tích lại câu."); };

export async function validateAttribution(
  value: AttributionResponse,
  source: AttributionSource,
  target: AttributionTarget,
): Promise<void> {
  const { item, prediction, profile, jobId } = source;
  const actual = value.source;
  const identity = prediction.execution_identity;
  if (!actual || !identity || !value.method || !value.coverage || !value.aggregate) return invalid();
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(item.text))))
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
  if (actual.source_job_id !== jobId || actual.source_prediction_id !== prediction.id ||
      actual.item_id !== item.id || actual.revision_id !== item.revision_id ||
      actual.run_id !== prediction.run_id || actual.text_hash !== hash ||
      actual.profile_id !== profile.id || actual.schema_id !== profile.schema_id ||
      actual.schema_id !== prediction.schema_id || actual.model_id !== prediction.model_id ||
      actual.model_version !== prediction.model_version ||
      canonical(actual.execution_identity) !== canonical(identity) ||
      identity.profile !== profile.id || identity.schema_id !== prediction.schema_id ||
      identity.model_id !== prediction.model_id || identity.model_version !== prediction.model_version ||
      identity.mode !== "cpu-fp32-eval" ||
      !/^[a-f0-9]{64}$/.test(String(identity.manifest_sha256)) ||
      !/^[a-f0-9]{64}$/.test(String(identity.preprocessing_sha256)) ||
      canonical(value.method.target) !== canonical(target)) return invalid();
  const { method, coverage, aggregate, groups } = value;
  if (method.unit !== "percentage_points" || method.id !== "permutation_shapley" ||
      !integer(method.seed) || !integer(method.requested_permutations) || method.requested_permutations < 1 ||
      method.completed_permutations !== method.requested_permutations ||
      !integer(method.evaluated_coalitions) || method.evaluated_coalitions < 2 ||
      !method.version || !method.grouping_version || !method.baseline_policy ||
      coverage.mapping_status !== "exact" || coverage.truncated !== false ||
      !integer(coverage.input_token_count) || coverage.input_token_count < 3 ||
      !Array.isArray(groups) || groups.length === 0 || coverage.analyzed_spans !== groups.length ||
      !Array.isArray(coverage.explained_token_indices)) return invalid();
  // Intl.Segmenter preserves combining marks, surrogate pairs, emoji modifiers and ZWJ clusters.
  const Segmenter = (Intl as unknown as { Segmenter: new (locale: string, options: { granularity: string }) => {
    segment(text: string): Iterable<{ index: number; segment: string }>;
  } }).Segmenter;
  if (!Segmenter) return invalid();
  const boundaries = new Set([0, item.text.length]);
  for (const segment of new Segmenter("vi", { granularity: "grapheme" }).segment(item.text)) {
    boundaries.add(segment.index);
    boundaries.add(segment.index + segment.segment.length);
  }
  const ids = new Set<string>();
  const tokens = new Set<number>();
  let lastEnd = 0;
  let previousToken = 0;
  let sum = 0;
  for (const group of groups) {
    if (!group || typeof group.id !== "string" || !group.id || ids.has(group.id) ||
        !finite(group.contribution) || !integer(group.start_utf16) || !integer(group.end_utf16) ||
        group.start_utf16 < lastEnd || group.end_utf16 <= group.start_utf16 ||
        !boundaries.has(group.start_utf16) || !boundaries.has(group.end_utf16) ||
        item.text.slice(group.start_utf16, group.end_utf16) !== group.text ||
        !Array.isArray(group.token_indices) || group.token_indices.length === 0) return invalid();
    ids.add(group.id);
    lastEnd = group.end_utf16;
    for (const token of group.token_indices) {
      if (!integer(token) || token < 1 || token >= coverage.input_token_count - 1 || tokens.has(token) || token <= previousToken) return invalid();
      tokens.add(token);
      previousToken = token;
    }
    sum += group.contribution;
  }
  const explained = coverage.explained_token_indices;
  if (tokens.size !== explained.length || new Set(explained).size !== explained.length ||
      explained.some((token) => !integer(token) || !tokens.has(token)) ||
      coverage.fixed_token_policy !== "special_tokens_only" || tokens.size !== coverage.input_token_count - 2) return invalid();
  const { baseline_value: baseline, total_contribution: total, target_output: output, additivity_residual: residual } = aggregate;
  if (![sum, baseline, total, output, residual].every(finite) || residual < 0 || residual > 1e-6 ||
      Math.abs(sum - total) > 1e-6 || Math.abs(baseline + total - output) > 1e-6 ||
      Math.abs(Math.abs(baseline + total - output) - residual) > 1e-6 ||
      (aggregate.hidden_groups_contribution !== undefined && !finite(aggregate.hidden_groups_contribution))) return invalid();
  let expected: number;
  if (target.kind === "label_score") {
    if (!profile.sentiment.some((label) => label.id === target.label_id)) return invalid();
    expected = 100 * prediction.sentiment.scores[profile.sentiment.findIndex((label) => label.id === target.label_id)];
  } else {
    const positive = profile.sentiment.find((label) => label.key.toLowerCase() === "positive");
    const negative = profile.sentiment.find((label) => label.key.toLowerCase() === "negative");
    if (!positive || !negative) return invalid();
    expected = 100 * (prediction.sentiment.scores[profile.sentiment.indexOf(positive)] - prediction.sentiment.scores[profile.sentiment.indexOf(negative)]);
  }
  if (!finite(expected) || Math.abs(output - expected) > (target.kind === "polarity_margin" ? 0.002 : 0.001)) return invalid();
}
