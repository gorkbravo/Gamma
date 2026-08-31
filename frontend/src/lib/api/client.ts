import { recordRequestMetric } from "../request-metrics";

const runtimeBase =
  typeof window !== "undefined" ? window.__GAMMA_API_BASE__ : undefined;
const rawBase = runtimeBase ?? import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const SESSION_HEADER = "X-Gamma-Session";

const SLOW_REQUEST_MS = 2_000;

export const API_BASE = rawBase.replace(/\/+$/, "");
export const WS_BASE = API_BASE.replace(/^http/i, "ws");

export interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function getJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await instrumentedFetch(path, () => fetch(`${API_BASE}${path}`, {
      headers: sessionHeaders(),
      signal: options.signal
    }));
  if (!response.ok) {
    throw await httpError(response);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(
  path: string,
  body: unknown,
  options: RequestOptions = {}
): Promise<T> {
  const timeoutMs = options.timeoutMs;
  const controller = timeoutMs ? new AbortController() : null;
  const abortFromCaller = () => controller?.abort(options.signal?.reason);
  options.signal?.addEventListener("abort", abortFromCaller, { once: true });
  if (options.signal?.aborted) abortFromCaller();
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let response: Response;
  try {
    response = await instrumentedFetch(path, () => fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...sessionHeaders()
      },
      body: JSON.stringify(body),
      signal: controller?.signal ?? options.signal
    }));
  } catch (error) {
    if (controller?.signal.aborted && !options.signal?.aborted) {
      throw new Error(`Request timed out after ${Math.round((timeoutMs ?? 0) / 1000)}s: ${path}`);
    }
    throw error;
  } finally {
    if (timer != null) {
      clearTimeout(timer);
    }
    options.signal?.removeEventListener("abort", abortFromCaller);
  }
  if (!response.ok) {
    throw await httpError(response);
  }
  return (await response.json()) as T;
}

export async function postNdjsonStream(
  path: string,
  body: unknown,
  onLine: (line: string) => void,
  options: RequestOptions = {}
): Promise<void> {
  const response = await instrumentedFetch(path, () =>
    fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...sessionHeaders()
      },
      body: JSON.stringify(body),
      signal: options.signal
    })
  );
  await consumeNdjsonResponse(response, path, onLine);
}

export async function getNdjsonStream(
  path: string,
  onLine: (line: string) => void,
  options: RequestOptions = {}
): Promise<void> {
  const response = await instrumentedFetch(path, () =>
    fetch(`${API_BASE}${path}`, {
      headers: sessionHeaders(),
      signal: options.signal
    })
  );
  await consumeNdjsonResponse(response, path, onLine);
}

async function consumeNdjsonResponse(
  response: Response,
  path: string,
  onLine: (line: string) => void
): Promise<void> {
  if (!response.ok) {
    throw await httpError(response);
  }
  if (!response.body) {
    throw new Error(`Streaming response body unavailable: ${path}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (line) {
        onLine(line);
      }
      newlineIndex = buffer.indexOf("\n");
    }
  }
  const tail = (buffer + decoder.decode()).trim();
  if (tail) {
    onLine(tail);
  }
}

async function instrumentedFetch(path: string, request: () => Promise<Response>): Promise<Response> {
  const key = requestMetricKey(path);
  const started = performance.now();
  recordRequestMetric(key, "network_request");
  try {
    const response = await request();
    const duration = performance.now() - started;
    recordRequestMetric(key, response.ok ? "network_success" : "network_error", duration);
    if (duration >= SLOW_REQUEST_MS) {
      recordRequestMetric(key, "slow_request", duration);
      console.warn(`[Gamma request] Slow request ${key}: ${Math.round(duration)}ms`);
    }
    return response;
  } catch (error) {
    recordRequestMetric(key, "network_error", performance.now() - started);
    throw error;
  }
}

function requestMetricKey(path: string): string {
  const [endpoint, query = ""] = path.split("?", 2);
  if (!query) return endpoint;
  const params = new URLSearchParams(query);
  params.delete("force_refresh");
  return `${endpoint}?${params.toString()}`;
}

export async function postText(path: string, body: unknown): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...sessionHeaders()
    },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return response.text();
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...sessionHeaders()
    },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return (await response.json()) as T;
}

export async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: sessionHeaders()
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return (await response.json()) as T;
}

export async function getText(path: string): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: sessionHeaders()
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return response.text();
}

export async function getBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: sessionHeaders()
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return response.blob();
}

function sessionHeaders(): Record<string, string> {
  const runtimeToken =
    typeof window !== "undefined" ? window.__GAMMA_SESSION_TOKEN__ : undefined;
  const token = runtimeToken ?? import.meta.env.VITE_GAMMA_SESSION_TOKEN ?? "";
  return token ? { [SESSION_HEADER]: token } : {};
}

async function httpError(response: Response): Promise<Error> {
  const fallback = `${response.status} ${response.statusText}`;
  const detail = await readErrorDetail(response);
  return new Error(detail ? `${fallback}: ${detail}` : fallback);
}

async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.toLowerCase().includes("application/json")) {
      const body = await response.json();
      return detailToString(body?.detail ?? body?.message ?? body);
    }
    const text = (await response.text()).trim();
    return text || null;
  } catch {
    return null;
  }
}

function detailToString(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "string") {
    return value.trim() || null;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
