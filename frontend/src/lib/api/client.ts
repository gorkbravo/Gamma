const runtimeBase =
  typeof window !== "undefined" ? window.__GAMMA_API_BASE__ : undefined;
const rawBase = runtimeBase ?? import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export const API_BASE = rawBase.replace(/\/+$/, "");

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw await httpError(response);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
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
    method: "DELETE"
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return (await response.json()) as T;
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
