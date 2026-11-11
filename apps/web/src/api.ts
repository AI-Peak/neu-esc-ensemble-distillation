import type {
  CreateSensitivityExperimentBody,
  Filters,
  Job,
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
export const post = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
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
