import type {
  AttributionResponse,
  AttributionTarget,
  CreateSensitivityExperimentBody,
  Filters,
  Job,
  NetworkResponse,
  SensitivityExperiment,
} from "./types";
export class ApiError extends Error {
  code: string;
  details: unknown;
  status?: number;
  constructor(
    message: string,
    code: string,
    details?: unknown,
    status?: number,
  ) {
    super(message);
    this.code = code;
    this.details = details;
    this.status = status;
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      "Không thể kết nối dịch vụ local. Kiểm tra API đang chạy rồi thử lại.",
      "NETWORK_ERROR",
    );
  }
  if (!response.ok) {
    let data: {
      message?: string;
      detail?: string;
      code?: string;
      details?: unknown;
    } = {};
    try {
      data = await response.json();
    } catch {
      /* HTTP error without JSON */
    }
    throw new ApiError(
      data.message ?? data.detail ?? `Yêu cầu thất bại (${response.status}).`,
      data.code ?? "HTTP_ERROR",
      data.details,
      response.status,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
export const post = <T>(path: string, body: unknown, options: RequestInit = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body), ...options });
export function createAttribution(
  jobId: string,
  sourcePredictionId: string,
  target: AttributionTarget,
  idempotencyKey?: string,
  signal?: AbortSignal,
) {
  return post<AttributionResponse>(
    `/quick-analysis/${jobId}/attribution`,
    { source_prediction_id: sourcePredictionId, target },
    {
      signal,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    },
  );
}

export function getAttribution(attributionId: string, signal?: AbortSignal) {
  return api<AttributionResponse>(`/attributions/${attributionId}`, { signal });
}

export function cancelAttribution(attributionId: string) {
  return post<{ attribution_id: string; status: string }>(
    `/attributions/${attributionId}/cancel`,
    {},
  );
}

export function getNetwork(
  datasetId: string,
  labelSource = "effective",
  runId?: string | null,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ label_source: labelSource });
  if (runId) params.set("run_id", runId);
  return api<NetworkResponse>(`/datasets/${datasetId}/network?${params.toString()}`, { signal });
}
export function getNetworkEvidence(
  networkId: string,
  selectionType: 'node' | 'edge' | 'community',
  selectionId: string,
  page = 1,
  pageSize = 10,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ selection_type: selectionType, selection_id: selectionId, page: String(page), page_size: String(pageSize) });
  return api<{items: import('./types').Item[]; total: number; page: number; page_size: number; scope_token: string}>(`/networks/${encodeURIComponent(networkId)}/evidence?${params}`, {signal});
}

export function filterBody(filters: Filters, all = false) {
  const f = all
    ? {
        run_id: filters.run_id,
        label_source: filters.label_source,
        scope: "all" as const,
      }
    : { ...filters, scope: "filtered" as const };
  return Object.fromEntries(
    Object.entries(f)
      .filter(([k, v]) => v !== "" && !["page", "page_size"].includes(k))
      .map(([k, v]) => [k, ["sentiment", "topic"].includes(k) ? Number(v) : v]),
  );
}
export function query(filters: Partial<Filters>) {
  return new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();
}
export function createSensitivityExperiment(
  itemId: string,
  body: CreateSensitivityExperimentBody,
  idempotencyKey: string,
) {
  return api<SensitivityExperiment>(
    `/items/${encodeURIComponent(itemId)}/sensitivity-experiments`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    },
  );
}
export function getSensitivityExperiment(experimentId: string) {
  return api<SensitivityExperiment>(
    `/sensitivity-experiments/${encodeURIComponent(experimentId)}`,
  );
}
export function cancelJob(jobId: string) {
  return post<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {});
}
export function retryJob(jobId: string) {
  return post<Job>(`/jobs/${encodeURIComponent(jobId)}/retry`, {});
}
