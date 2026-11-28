import { get, writable } from "svelte/store";
import { getJson, postJson } from "../api/client";
import type { DiagnosticReportResponse, SetupReport, SetupUpdateRequest, SetupUpdateResponse } from "../api/types";
import { queryCache } from "../query-cache";
import type { SetupChoices } from "../setup-wizard";
import { setBaseCurrency } from "./app";
import { lastError, setLoading } from "./runtime";
import { refreshSystemStatus } from "./system";

export const setupReport = writable<SetupReport | null>(null);
export const setupError = writable<string>("");

export interface SetupFinishResult {
  ok: boolean;
  lines: string[];
  error: string | null;
  currencyChanged: boolean;
  restartRequired: boolean;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function loadSetupReport(): Promise<SetupReport | null> {
  setLoading("setup", true);
  try {
    const report = await getJson<SetupReport>("/system/setup");
    setupReport.set(report);
    setupError.set("");
    return report;
  } catch (error) {
    // Un backend sin el endpoint (versión anterior) no debe bloquear el arranque.
    setupError.set(errorMessage(error));
    return null;
  } finally {
    setLoading("setup", false);
  }
}

export async function saveSetup(update: SetupUpdateRequest): Promise<SetupUpdateResponse | null> {
  setLoading("setup", true);
  try {
    const response = await postJson<SetupUpdateResponse>("/system/setup", update);
    setupReport.set(response);
    setupError.set("");
    return response;
  } catch (error) {
    setupError.set(errorMessage(error));
    return null;
  } finally {
    setLoading("setup", false);
  }
}

export interface SetupKeysResult {
  ok: boolean;
  lines: string[];
  error: string | null;
}

/**
 * Guarda claves de API en el .env que Gamma lee al arrancar. Un valor null o vacío borra la
 * variable. La respuesta nunca contiene los valores: solo el informe actualizado.
 */
export async function saveSetupKeys(keys: Record<string, string | null>): Promise<SetupKeysResult> {
  setLoading("setup", true);
  try {
    const response = await postJson<SetupUpdateResponse>("/system/setup/keys", { keys });
    setupReport.set(response);
    setupError.set("");
    return { ok: true, lines: response.lines, error: null };
  } catch (error) {
    return { ok: false, lines: [], error: errorMessage(error) };
  } finally {
    setLoading("setup", false);
  }
}

export interface DiagnosticReportRequest {
  note?: string | null;
  client?: Record<string, string>;
}

/** Informe de diagnóstico sin guardar, para que el tester lo lea antes de compartirlo. */
export async function previewDiagnosticReport(request: DiagnosticReportRequest): Promise<DiagnosticReportResponse> {
  return postJson<DiagnosticReportResponse>("/system/diagnostic-report/preview", request);
}

/** Guarda el informe en la carpeta local de informes; Gamma no lo envía a ningún sitio. */
export async function saveDiagnosticReport(request: DiagnosticReportRequest): Promise<DiagnosticReportResponse> {
  return postJson<DiagnosticReportResponse>("/system/diagnostic-report", request);
}

/** Salta el asistente: lo marca como completado sin cambiar ninguna preferencia. */
export async function skipSetup(): Promise<boolean> {
  return (await saveSetup({ complete: true })) != null;
}

/**
 * Aplica las elecciones del asistente en orden: primero la divisa base por la ruta de
 * Settings (vacía las vistas calculadas en la divisa anterior), después el resto en
 * /system/setup, que también marca el setup como completado.
 */
export async function finishSetup(choices: SetupChoices): Promise<SetupFinishResult> {
  const lines: string[] = [];
  let currencyChanged = false;
  if (choices.baseCurrency) {
    const response = await setBaseCurrency(choices.baseCurrency);
    if (!response) {
      return {
        ok: false,
        lines,
        error: get(lastError) || "Base currency could not be changed.",
        currencyChanged,
        restartRequired: false
      };
    }
    currencyChanged = true;
    lines.push(...response.lines);
  }
  const response = await saveSetup(choices.update);
  if (!response) {
    return {
      ok: false,
      lines,
      error: get(setupError) || "Setup could not be saved.",
      currencyChanged,
      restartRequired: false
    };
  }
  lines.push(...response.lines);
  queryCache.invalidate("/system/status");
  await refreshSystemStatus();
  return {
    ok: true,
    lines,
    error: null,
    currencyChanged,
    restartRequired: response.data_mode.restart_required
  };
}
