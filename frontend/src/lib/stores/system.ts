import { get, writable } from "svelte/store";
import { getJson, postJson } from "../api/client";
import type { DiagnosticsResponse, ProviderUsageResponse, SystemStatus } from "../api/types";
import { isAbortError } from "../request-coordinator";
import { queryCache } from "../query-cache";
import { beginLoading, endLoading, lastError, setError, setLoading } from "./runtime";

export const systemStatus = writable<SystemStatus | null>(null);
export const diagnostics = writable<DiagnosticsResponse | null>(null);
export const providerUsage = writable<ProviderUsageResponse | null>(null);
export const diagnosticsLog = writable<string[]>([]);

export async function refreshSystemStatus() {
  beginLoading("status");
  try {
    const response = await queryCache.query<SystemStatus>({
      scope: "system-status", key: "/system/status", staleTimeMs: 3_000,
      staleWhileRevalidate: false,
      fetcher: (signal) => getJson<SystemStatus>("/system/status", { signal }),
      onData: (status) => systemStatus.set(status)
    });
    lastError.set("");
    return response;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return null;
  } finally { endLoading("status"); }
}

export async function loadDiagnostics() {
  setLoading("diagnostics", true);
  try {
    const response = await getJson<DiagnosticsResponse>("/diagnostics");
    diagnostics.set(response);
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  }
  finally { setLoading("diagnostics", false); }
}

export async function loadProviderUsage() {
  beginLoading("providerUsage");
  try {
    const response = await queryCache.query<ProviderUsageResponse>({
      scope: "provider-usage", key: "/system/provider-usage", staleTimeMs: 15_000,
      fetcher: (signal) => getJson<ProviderUsageResponse>("/system/provider-usage", { signal }),
      onData: (usage) => providerUsage.set(usage)
    });
    lastError.set("");
    return response;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return null;
  } finally { endLoading("providerUsage"); }
}

export async function toggleConnection() {
  setLoading("status", true);
  try {
    const desiredConnected = !(get(systemStatus)?.connection.connected ?? false);
    const nextStatus = await postJson<SystemStatus>("/system/connection", {
      connected: desiredConnected
    });
    systemStatus.set(nextStatus);
    diagnostics.update((current) => current == null ? current : { ...current, connection: nextStatus.connection });
    queryCache.invalidate("/system/status");
    lastError.set("");
    return nextStatus;
  } catch (error) { setError(error); return null; }
  finally { setLoading("status", false); }
}

export async function setMarketDataMode(mode: string) {
  setLoading("status", true);
  try {
    const nextStatus = await postJson<SystemStatus>("/system/market-data-mode", { market_data_mode: mode });
    systemStatus.set(nextStatus);
    diagnostics.update((current) => current == null ? current : { ...current, market_data_mode: nextStatus.market_data_mode });
    queryCache.invalidate("/system/status");
    lastError.set("");
  } catch (error) { setError(error); }
  finally { setLoading("status", false); }
}
