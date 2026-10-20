import type {
  SetupCoverageSource,
  SetupDataMode,
  SetupReport,
  SetupUpdateRequest,
  SystemStatus
} from "./api/types";

/*
 * Modelo de vista del asistente de primer arranque. Funciones puras: el componente
 * SetupWizard.svelte solo pinta lo que estas funciones deciden, y los tests cubren aquí
 * los pasos, la validación y qué se envía al backend.
 */

export type SetupStepId = "mode" | "broker" | "preferences" | "sources" | "identity" | "review";

export interface SetupDraft {
  dataMode: SetupDataMode;
  baseCurrency: string;
  marketDataMode: string;
  secName: string;
  secEmail: string;
  // El usuario pidió borrar la identidad SEC guardada.
  clearSecIdentity: boolean;
}

export interface SetupChange {
  label: string;
  from: string;
  to: string;
  note: string | null;
}

export interface SetupChoices {
  // La divisa se aplica por /system/base-currency para reutilizar la invalidación de vistas.
  baseCurrency: string | null;
  update: SetupUpdateRequest;
}

const STEP_LABELS: Record<SetupStepId, string> = {
  mode: "Data mode",
  broker: "Broker",
  preferences: "Preferences",
  sources: "Data sources",
  identity: "SEC identity",
  review: "Review"
};

// Misma validación básica que el backend (src/services/setup_store.py).
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const SEC_NAME_MAX = 80;
export const SEC_EMAIL_MAX = 120;

export function setupSteps(dataMode: SetupDataMode): SetupStepId[] {
  return dataMode === "live"
    ? ["mode", "broker", "preferences", "sources", "identity", "review"]
    : ["mode", "preferences", "sources", "identity", "review"];
}

export function stepLabel(step: SetupStepId): string {
  return STEP_LABELS[step];
}

/** Paso inicial pedido al abrir el asistente (p. ej. "identity" desde Fundamentals); 0 si no aplica. */
export function initialStepIndex(steps: SetupStepId[], requested: SetupStepId | null): number {
  if (!requested) return 0;
  const index = steps.indexOf(requested);
  return index >= 0 ? index : 0;
}

/** El backend responde 428 cuando falta la identidad SEC; el mensaje de error empieza por el estado. */
export function isSecIdentityMissingError(message: string | null | undefined): boolean {
  return typeof message === "string" && message.startsWith("428");
}

export function initialDraft(report: SetupReport, status: SystemStatus | null): SetupDraft {
  return {
    dataMode: report.data_mode.preference ?? report.data_mode.current,
    baseCurrency: status?.base_currency ?? report.base_currency.current,
    marketDataMode: status?.market_data_mode ?? report.market_data_mode.current,
    secName: report.sec_identity.source === "setup" ? report.sec_identity.name ?? "" : "",
    secEmail: report.sec_identity.source === "setup" ? report.sec_identity.email ?? "" : "",
    clearSecIdentity: false
  };
}

/** Devuelve un mensaje de error o null. Los dos campos vacíos significan "no cambiar". */
export function validateSecIdentity(name: string, email: string): string | null {
  const cleanName = collapseSpaces(name);
  const cleanEmail = email.trim();
  if (!cleanName && !cleanEmail) return null;
  if (cleanName.length < 2) return "Enter your name (at least 2 characters).";
  if (cleanName.length > SEC_NAME_MAX) return `Name must have at most ${SEC_NAME_MAX} characters.`;
  if (!EMAIL_PATTERN.test(cleanEmail) || cleanEmail.length > SEC_EMAIL_MAX) return "Enter a valid email address.";
  return null;
}

export function secIdentityLocked(report: SetupReport): boolean {
  return report.sec_identity.source === "environment";
}

export function dataModeLocked(report: SetupReport): boolean {
  return report.data_mode.locked_by != null;
}

export function restartNeeded(report: SetupReport, draft: SetupDraft): boolean {
  return !dataModeLocked(report) && draft.dataMode !== report.data_mode.current;
}

function collapseSpaces(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(" ");
}

function secIdentityChanged(report: SetupReport, draft: SetupDraft): boolean {
  if (secIdentityLocked(report) || draft.clearSecIdentity) return false;
  const name = collapseSpaces(draft.secName);
  const email = draft.secEmail.trim();
  if (!name && !email) return false;
  return name !== (report.sec_identity.name ?? "") || email !== (report.sec_identity.email ?? "");
}

export function dataModeLabel(mode: SetupDataMode): string {
  return mode === "demo" ? "Demo" : "Live data";
}

/** Cambios que se aplicarán al terminar; alimenta el paso de revisión. */
export function draftChanges(report: SetupReport, status: SystemStatus | null, draft: SetupDraft): SetupChange[] {
  const changes: SetupChange[] = [];
  const savedMode = report.data_mode.preference ?? report.data_mode.current;
  if (!dataModeLocked(report) && draft.dataMode !== savedMode) {
    changes.push({
      label: "Data mode",
      from: dataModeLabel(savedMode),
      to: dataModeLabel(draft.dataMode),
      note: restartNeeded(report, draft) ? "Takes effect after Gamma restarts." : null
    });
  } else if (restartNeeded(report, draft)) {
    changes.push({
      label: "Data mode",
      from: dataModeLabel(report.data_mode.current),
      to: dataModeLabel(draft.dataMode),
      note: "Already saved; takes effect after Gamma restarts."
    });
  }
  const currentCurrency = status?.base_currency ?? report.base_currency.current;
  if (draft.baseCurrency !== currentCurrency) {
    changes.push({
      label: "Base currency",
      from: currentCurrency,
      to: draft.baseCurrency,
      note: "Archives local portfolio history, which is stored per currency."
    });
  }
  const currentMarket = status?.market_data_mode ?? report.market_data_mode.current;
  if (draft.dataMode === "live" && draft.marketDataMode !== currentMarket) {
    changes.push({ label: "Market data", from: currentMarket, to: draft.marketDataMode, note: null });
  }
  if (draft.clearSecIdentity && report.sec_identity.source === "setup") {
    changes.push({ label: "SEC identity", from: report.sec_identity.name ?? "Saved", to: "Not set", note: null });
  } else if (secIdentityChanged(report, draft)) {
    changes.push({
      label: "SEC identity",
      from: report.sec_identity.source === "setup" ? report.sec_identity.name ?? "Saved" : "Not set",
      to: collapseSpaces(draft.secName),
      note: null
    });
  }
  return changes;
}

/** Traduce el borrador a llamadas al backend: solo campos cambiados, más la marca de completado. */
export function buildSetupChoices(report: SetupReport, status: SystemStatus | null, draft: SetupDraft): SetupChoices {
  const update: SetupUpdateRequest = { complete: true };
  if (!dataModeLocked(report) && draft.dataMode !== (report.data_mode.preference ?? null)) {
    update.data_mode = draft.dataMode;
  }
  const currentMarket = status?.market_data_mode ?? report.market_data_mode.current;
  if (draft.dataMode === "live" && draft.marketDataMode !== currentMarket) {
    update.market_data_mode = draft.marketDataMode;
  }
  if (draft.clearSecIdentity && report.sec_identity.source === "setup") {
    update.clear_sec_identity = true;
  } else if (secIdentityChanged(report, draft)) {
    update.sec_identity = { name: collapseSpaces(draft.secName), email: draft.secEmail.trim() };
  }
  const currentCurrency = status?.base_currency ?? report.base_currency.current;
  return {
    baseCurrency: draft.baseCurrency !== currentCurrency ? draft.baseCurrency : null,
    update
  };
}

export function coverageSourceLabel(source: SetupCoverageSource): string {
  switch (source) {
    case "sample":
      return "Sample";
    case "public":
      return "Public";
    case "broker":
      return "IBKR";
    case "mixed":
      return "Mixed";
    case "model":
      return "Model";
    default:
      return "Unavailable";
  }
}

/**
 * Tono semántico para la fuente. La columna dice de dónde salen los datos, no si el proveedor
 * responde ahora: colorear "IBKR" en verde con TWS desconectado sugeriría salud que no consta.
 * Solo "Unavailable" lleva color, porque esa pestaña no mostrará datos.
 */
export function coverageSourceTone(source: SetupCoverageSource): "warning" | "neutral" {
  return source === "unavailable" ? "warning" : "neutral";
}

export function lockedNote(variable: string | null): string | null {
  return variable ? `Set by ${variable} in the environment or .env file.` : null;
}
