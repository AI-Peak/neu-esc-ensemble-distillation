import type { Filters } from "./types";
export class ApiError extends Error {
  code: string;
  details: unknown;
  constructor(message: string, code: string, details?: unknown) {
    super(message);
    this.code = code;
    this.details = details;
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
    ? { run_id: filters.run_id, label_source: filters.label_source }
    : filters;
  return Object.fromEntries(
    Object.entries(f)
      .filter(([k, v]) => v !== "" && !["page", "page_size"].includes(k))
      .map(([k, v]) => [k, ["sentiment", "topic"].includes(k) ? Number(v) : v]),
  );
}
export function query(filters: Filters) {
  return new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();
}
