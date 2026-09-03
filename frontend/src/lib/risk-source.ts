import type { RiskResult } from "./api/types";
import type { RiskSourceScope } from "./risk-workspace";

export type RiskSourceId = "portfolio" | "research" | "strategy_lab_book";

export interface RiskSourceOption {
  id: RiskSourceId;
  label: string;
}

const SCOPE_BY_ID: Record<RiskSourceId, RiskSourceScope> = {
  portfolio: "portfolio",
  research: "research",
  strategy_lab_book: "research_book",
};

const ID_BY_SCOPE: Record<RiskSourceScope, RiskSourceId> = {
  portfolio: "portfolio",
  research: "research",
  research_book: "strategy_lab_book",
};

export function riskSourceScopeFor(id: RiskSourceId): RiskSourceScope {
  return SCOPE_BY_ID[id] ?? "portfolio";
}

/**
 * The selector identity a computed result belongs to, or null when the backend
 * reported a scope this build does not know how to render.
 */
export function riskSourceIdForScope(scope: string | null | undefined): RiskSourceId | null {
  if (scope == null) return null;
  return ID_BY_SCOPE[scope as RiskSourceScope] ?? null;
}

export interface RiskSourceViewState {
  /** Source identity the visible panels were actually computed from. */
  rendered: RiskSourceId;
  renderScope: RiskSourceScope;
  /** True when the selector no longer describes the visible result. */
  pendingRecompute: boolean;
}

/**
 * Render identity follows the result, not the selector. A risk pass computed
 * from one source must never be drawn with another source's holdings, movers
 * or concentration rows, so the selector is treated as intent for the next
 * compute and the result is treated as fact about the current one.
 */
export function resolveRiskSourceView(input: {
  selected: RiskSourceId;
  result: Pick<RiskResult, "source_scope"> | null;
}): RiskSourceViewState {
  const fromResult = input.result ? riskSourceIdForScope(input.result.source_scope) : null;
  const rendered = fromResult ?? input.selected;
  return {
    rendered,
    renderScope: riskSourceScopeFor(rendered),
    pendingRecompute: fromResult != null && fromResult !== input.selected,
  };
}

/**
 * The selector value to adopt when a result arrives, so the control matches the
 * computation that produced the visible screen. Returns null when the current
 * selection already matches or the result's source is not offered here.
 */
export function adoptRiskSourceFromResult(input: {
  selected: RiskSourceId;
  available: RiskSourceOption[];
  result: Pick<RiskResult, "source_scope"> | null;
}): RiskSourceId | null {
  if (!input.result) return null;
  const fromResult = riskSourceIdForScope(input.result.source_scope);
  if (!fromResult || fromResult === input.selected) return null;
  return input.available.some((source) => source.id === fromResult) ? fromResult : null;
}
