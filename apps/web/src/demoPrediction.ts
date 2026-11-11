import type { Prediction, Profile, Task } from "./types";

/** Treat API data as untrusted: a missing score is never a zero score. */
export function validDemoTask(prediction: Prediction | null, profile: Profile, task: Task): boolean {
  if (!prediction || !profile.id || prediction.schema_id !== profile.schema_id || profile.model?.schema_id !== profile.schema_id ||
      !prediction.model_id || !prediction.model_version ||
      (profile.model?.model_id && prediction.model_id !== profile.model.model_id) ||
      (profile.model?.model_version && prediction.model_version !== profile.model.model_version)) return false;
  const data = prediction[task];
  const labels = profile[task];
  return !!data && Array.isArray(data.scores) && Array.isArray(labels) && labels.length > 0 &&
    data.scores.length === labels.length &&
    Number.isInteger(data.label_id) && labels.some(label => label.id === data.label_id) &&
    labels.every(label => Number.isInteger(label.id) && label.id >= 0 && label.id < data.scores.length) &&
    data.scores.every(score => typeof score === "number" && Number.isFinite(score) && score >= 0 && score <= 1) &&
    Math.abs(data.scores.reduce((sum, score) => sum + score, 0) - 1) <= .001 &&
    data.label_id === data.scores.reduce((best, score, id, scores) => score > scores[best] ? id : best, 0);
}
