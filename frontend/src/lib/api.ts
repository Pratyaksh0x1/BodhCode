import { useRateLimitStore } from "../store/rateLimitStore";
import { VITE_API_URL } from "./env";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body?: unknown;
  readonly retryAfter?: number;

  constructor(status: number, detail: string, body?: unknown, retryAfter?: number) {
    super(`API Error ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
    this.retryAfter = retryAfter;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${VITE_API_URL}${normalizedPath}`;

  const headers = new Headers(init?.headers);
  const method = (init?.method || "GET").toUpperCase();

  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (method !== "GET") {
    headers.set("X-Requested-With", "bodhcode");
  }

  const response = await fetch(url, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let detail = response.statusText || "Request failed";
    let body: unknown = undefined;
    try {
      const errorJson = (await response.json()) as { detail?: unknown };
      body = errorJson;
      if (typeof errorJson?.detail === "string") {
        detail = errorJson.detail;
      } else if (errorJson?.detail) {
        detail = JSON.stringify(errorJson.detail);
      }
    } catch {
      try {
        const text = await response.text();
        if (text) {
          detail = text;
          body = text;
        }
      } catch {
        // Fallback to statusText
      }
    }

    let retryAfter: number | undefined;
    if (response.status === 429) {
      const retryHeader = response.headers.get("Retry-After");
      retryAfter = retryHeader ? parseInt(retryHeader, 10) : 60;
      if (isNaN(retryAfter) || retryAfter <= 0) {
        retryAfter = 60;
      }
      useRateLimitStore.getState().triggerRateLimit(retryAfter, detail);
    }

    throw new ApiError(response.status, detail, body, retryAfter);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return (await response.json()) as T;
}
