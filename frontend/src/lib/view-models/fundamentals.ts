import type {
  FundamentalsDcfModel,
  FundamentalsDcfScenario,
  FundamentalsFinancials,
  FundamentalsReference,
  FundamentalsReverseValuationDriver,
  FundamentalsSourceTrace,
  FundamentalsStatementView
} from "../api/types";
import type { FundamentalsDcfSavePayload } from "../stores/app";

export type FundamentalsMode = "overview" | "financials" | "peers" | "dcf" | "reverse_valuation" | "reference";
export type FundamentalsStatementBasis = "annual" | "quarterly";
export type FundamentalsStatementKind = "income" | "balance" | "cashflow" | "ratios";

export const fundamentalsModes: Array<{ id: FundamentalsMode; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "financials", label: "Financials" },
  { id: "peers", label: "Peers" },
  { id: "dcf", label: "DCF" },
  { id: "reverse_valuation", label: "Reverse Valuation" },
  { id: "reference", label: "Reference / Filings" }
];

export interface FundamentalsDcfDraftScenario {
  assumptions: Record<string, unknown>;
  overrides: Record<string, Array<number | null>>;
}

export interface FundamentalsDcfDraft {
  activeScenarioId: string;
  projectionYears: number[];
  scenarios: Record<string, FundamentalsDcfDraftScenario>;
}

export function statementViewForSelection(
  financials: FundamentalsFinancials | null,
  basis: FundamentalsStatementBasis,
  statementKind: FundamentalsStatementKind
): FundamentalsStatementView | null {
  if (!financials) {
    return null;
  }
  if (basis === "annual") {
    if (statementKind === "income") return financials.annual_income_statement;
    if (statementKind === "balance") return financials.annual_balance_sheet;
    if (statementKind === "cashflow") return financials.annual_cash_flow_statement;
    return financials.annual_ratio_view;
  }
  if (statementKind === "income") return financials.quarterly_income_statement;
  if (statementKind === "balance") return financials.quarterly_balance_sheet;
  if (statementKind === "cashflow") return financials.quarterly_cash_flow_statement;
  return financials.quarterly_ratio_view;
}

export function findDcfScenario(
  model: FundamentalsDcfModel | null,
  scenarioId: string | null | undefined
): FundamentalsDcfScenario | null {
  if (!model) {
    return null;
  }
  const requested = String(scenarioId ?? model.active_scenario_id).trim().toLowerCase();
  return (
    model.scenarios.find((scenario) => scenario.scenario_id === requested) ??
    model.scenarios.find((scenario) => scenario.scenario_id === model.active_scenario_id) ??
    model.scenarios[0] ??
    null
  );
}

export function createDcfDraft(model: FundamentalsDcfModel | null): FundamentalsDcfDraft {
  if (!model) {
    return {
      activeScenarioId: "base",
      projectionYears: [],
      scenarios: {}
    };
  }

  return {
    activeScenarioId: model.active_scenario_id,
    projectionYears: [...model.projection_years],
    scenarios: Object.fromEntries(
      model.scenarios.map((scenario) => [
        scenario.scenario_id,
        {
          assumptions: structuredCloneValue(scenario.assumptions),
          overrides: structuredCloneValue(scenario.overrides)
        }
      ])
    )
  };
}

export function setDraftActiveScenario(
  draft: FundamentalsDcfDraft,
  scenarioId: string
): FundamentalsDcfDraft {
  return {
    ...draft,
    activeScenarioId: scenarioId
  };
}

export function updateDraftAssumptionSeriesValue(
  draft: FundamentalsDcfDraft,
  scenarioId: string,
  key: string,
  index: number,
  value: number | null
): FundamentalsDcfDraft {
  const scenario = draft.scenarios[scenarioId];
  if (!scenario) {
    return draft;
  }
  const current = Array.isArray(scenario.assumptions[key]) ? [...(scenario.assumptions[key] as Array<number | null>)] : [];
  while (current.length < draft.projectionYears.length) {
    current.push(null);
  }
  current[index] = value;
  return {
    ...draft,
    scenarios: {
      ...draft.scenarios,
      [scenarioId]: {
        ...scenario,
        assumptions: {
          ...scenario.assumptions,
          [key]: current
        }
      }
    }
  };
}

export function updateDraftScalarAssumption(
  draft: FundamentalsDcfDraft,
  scenarioId: string,
  key: string,
  value: number | null
): FundamentalsDcfDraft {
  const scenario = draft.scenarios[scenarioId];
  if (!scenario) {
    return draft;
  }
  return {
    ...draft,
    scenarios: {
      ...draft.scenarios,
      [scenarioId]: {
        ...scenario,
        assumptions: {
          ...scenario.assumptions,
          [key]: value
        }
      }
    }
  };
}

export function updateDraftOverride(
  draft: FundamentalsDcfDraft,
  scenarioId: string,
  lineKey: string,
  index: number,
  value: number | null
): FundamentalsDcfDraft {
  const scenario = draft.scenarios[scenarioId];
  if (!scenario) {
    return draft;
  }
  const nextOverrides = { ...scenario.overrides };
  const current = [...(nextOverrides[lineKey] ?? [])];
  while (current.length < draft.projectionYears.length) {
    current.push(null);
  }
  current[index] = value;
  if (current.every((item) => item == null)) {
    delete nextOverrides[lineKey];
  } else {
    nextOverrides[lineKey] = current;
  }
  return {
    ...draft,
    scenarios: {
      ...draft.scenarios,
      [scenarioId]: {
        ...scenario,
        overrides: nextOverrides
      }
    }
  };
}

export function buildDcfSavePayload(draft: FundamentalsDcfDraft): FundamentalsDcfSavePayload {
  return {
    activeScenarioId: draft.activeScenarioId,
    projectionYears: [...draft.projectionYears],
    scenarios: Object.fromEntries(
      Object.entries(draft.scenarios).map(([scenarioId, scenario]) => [
        scenarioId,
        {
          assumptions: structuredCloneValue(scenario.assumptions),
          overrides: structuredCloneValue(scenario.overrides)
        }
      ])
    )
  };
}

export function normalizePeerTickers(focalTicker: string, peerTickers: string[]) {
  const focal = focalTicker.trim().toUpperCase();
  const ordered = peerTickers
    .map((ticker) => ticker.trim().toUpperCase())
    .filter((ticker) => ticker.length > 0 && ticker !== focal);
  return [...new Set(ordered)];
}

export function parseEditableNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const numeric = Number(trimmed.replace(/,/g, ""));
  return Number.isFinite(numeric) ? numeric : null;
}

export function driverTone(driver: FundamentalsReverseValuationDriver | null | undefined) {
  if (!driver || !driver.success || driver.gap_to_base == null) {
    return "";
  }
  return driver.gap_to_base >= 0 ? "warning" : "positive";
}

export function sourceTracesForStatement(
  reference: FundamentalsReference | null,
  basis: FundamentalsStatementBasis,
  statementKind: FundamentalsStatementKind
): FundamentalsSourceTrace[] {
  const traces = reference?.inspection?.traces ?? [];
  return traces.filter((trace) => trace.basis === basis && trace.statement === statementKind);
}

export function snapshotDisplayName(name: string | null | undefined, createdAt: string | null | undefined) {
  const trimmed = String(name ?? "").trim();
  if (trimmed) {
    return trimmed;
  }
  if (!createdAt) {
    return "DCF snapshot";
  }
  return `Snapshot ${new Date(createdAt).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  })}`;
}

function structuredCloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
