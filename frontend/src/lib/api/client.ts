const runtimeBase =
  typeof window !== "undefined" ? window.__GAMMA_API_BASE__ : undefined;
const rawBase = runtimeBase ?? import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const SESSION_HEADER = "X-Gamma-Session";

export const API_BASE = rawBase.replace(/\/+$/, "");
export const WS_BASE = API_BASE.replace(/^http/i, "ws");

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: sessionHeaders()
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
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
  return (await response.json()) as T;
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
