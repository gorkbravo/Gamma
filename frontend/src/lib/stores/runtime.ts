import { writable } from "svelte/store";

export const lastError = writable<string>("");

export const loading = writable<Record<string, boolean>>({
  status: false, diagnostics: false, providerUsage: false, diagnosticsAction: false,
  portfolio: false, portfolioAction: false, researchOverview: false, research: false,
  strategyLab: false, strategyLabHandoff: false, compareScenario: false, savedResearch: false,
  macro: false, macroHistory: false, news: false, commodities: false, maritime: false,
  prediction: false, predictionDetail: false, crypto: false, cryptoDetail: false,
  cryptoPortfolio: false, fundamentals: false, fundamentalsSave: false, copilot: false,
  risk: false, iv: false, ivSession: false
});

const loadingActivityCounts = new Map<string, number>();

export function setLoading(key: string, value: boolean): void {
  loading.update((current) => ({ ...current, [key]: value }));
}

export function beginLoading(key: string): void {
  const next = (loadingActivityCounts.get(key) ?? 0) + 1;
  loadingActivityCounts.set(key, next);
  setLoading(key, true);
}

export function endLoading(key: string): void {
  const next = Math.max(0, (loadingActivityCounts.get(key) ?? 1) - 1);
  if (next === 0) loadingActivityCounts.delete(key);
  else loadingActivityCounts.set(key, next);
  setLoading(key, next > 0);
}

export function setError(error: unknown): void {
  lastError.set(error instanceof Error ? error.message : String(error));
}
