import type { ErrorResponse } from "./types";

const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_URL);
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly payload?: ErrorResponse,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(toApiUrl(path), {
    ...options,
    headers: buildHeaders(options.headers),
  });

  if (!response.ok) {
    throw await toApiError(response);
  }

  return response.json() as Promise<T>;
}

function normalizeApiBaseUrl(value: string | undefined): string {
  return (value ?? "").replace(/\/+$/, "");
}

function toApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

function buildHeaders(input?: HeadersInit): Headers {
  const headers = new Headers(input);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }
  return headers;
}

async function toApiError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = (await response.json().catch(() => undefined)) as ErrorResponse | undefined;
    return new ApiError(response.status, payload?.detail ?? response.statusText, payload);
  }

  const detail = await response.text().catch(() => response.statusText);
  return new ApiError(response.status, detail || response.statusText);
}
