import { writable } from "svelte/store";
import type { StrategyLeg } from "./view-models/iv";

export interface OptionsWorkspaceDraft {
  symbol: string;
  selectedExpiry: string | null;
  strategySymbol: string | null;
  legs: StrategyLeg[];
  contracts: number;
  notice: string;
  workingAnalysisId: string | null;
}

// Session-local editing state. Navigating to Copilot must not discard the
// structure that supplied its evidence or create a durable saved strategy.
export const optionsWorkspaceDraft = writable<OptionsWorkspaceDraft | null>(null);

export function restoreOptionsWorkspaceDraft(draft: OptionsWorkspaceDraft | null, symbol: string) {
  if (!draft || draft.symbol.trim().toUpperCase() !== symbol.trim().toUpperCase()) return null;
  return structuredClone(draft);
}
