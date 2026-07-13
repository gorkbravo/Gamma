import type {
  FundamentalsDcfModel,
  FundamentalsDcfScenario,
  FundamentalsFiling,
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

export interface FundamentalsDcfDecisionGate {
  blocked: boolean;
  reasons: string[];
}

export interface FundamentalsStatementTrend {
  lineKey: string;
  label: string;
  unit: string;
  latestLabel: string;
  latestDisplay: string;
  priorLabel: string;
  priorDisplay: string;
  change: number | null;
  changeDisplay: string;
}

export interface FundamentalsAmendmentSummary {
  amendedPeriods: number;
  amendedCells: number;
  amendmentFilings: number;
  latestAmendmentDate: string | null;
}

export interface FundamentalsTerminalFraming {
  terminalGrowth: number | null;
  wacc: number | null;
  terminalValue: number | null;
  terminalValueShare: number | null;
  impliedTerminalFcfMultiple: number | null;
}

const DCF_BLOCKING_WARNING_PATTERNS = [
  "no normalized annual statement periods",
  "mapped annual revenue line",
  "annual income line `revenue` has no mapped",
  "mapped capital expenditures line",
  "annual cashflow line `capex` has no mapped",
  "mapped annual operating cash flow",
  "annual cashflow line `operating cash flow` has no mapped",
  "shares outstanding are unavailable",
  "mapped share-count line"
];

export function dcfDecisionGateFromWarnings(warnings: string[]): FundamentalsDcfDecisionGate {
  const reasons = warnings.reduce<string[]>((rows, warning) => {
    const text = warning.trim();
    const normalized = text.toLowerCase();
    if (!text || rows.includes(text)) {
      return rows;
    }
    if (DCF_BLOCKING_WARNING_PATTERNS.some((pattern) => normalized.includes(pattern))) {
      return [...rows, text];
    }
    return rows;
  }, []);
  return {
    blocked: reasons.length > 0,
    reasons
  };
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
  // Accept Excel-style accounting parens for negatives: "(1,234.50)" -> -1234.5
  const parenMatch = /^\((.*)\)$/.exec(trimmed);
  const body = parenMatch ? parenMatch[1] : trimmed;
  const numeric = Number(body.replace(/,/g, ""));
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return parenMatch ? -numeric : numeric;
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

export function statementTrends(
  view: FundamentalsStatementView | null,
  limit = 8
): FundamentalsStatementTrend[] {
  if (!view || limit <= 0) return [];
  const periodByKey = new Map(view.periods.map((period) => [period.period_key, period]));
  const order = new Map(view.periods.map((period, index) => [period.period_key, index]));
  return view.lines.reduce<FundamentalsStatementTrend[]>((rows, line) => {
    if (rows.length >= limit) return rows;
    const comparable = line.cells
      .filter((cell) => cell.value != null && Number.isFinite(cell.value))
      .sort((left, right) => (order.get(left.period_key) ?? 999) - (order.get(right.period_key) ?? 999));
    if (comparable.length < 2) return rows;
    const [latest, prior] = comparable;
    const latestValue = latest.value as number;
    const priorValue = prior.value as number;
    const change = line.unit === "percent" || line.unit === "ratio"
      ? latestValue - priorValue
      : priorValue === 0
        ? null
        : (latestValue - priorValue) / Math.abs(priorValue);
    const changeDisplay = change == null
      ? "N/A"
      : line.unit === "percent"
        ? `${change >= 0 ? "+" : ""}${(change * 100).toFixed(1)} pp`
        : line.unit === "ratio"
          ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}x`
          : `${change >= 0 ? "+" : ""}${(change * 100).toFixed(1)}%`;
    return [...rows, {
      lineKey: line.line_key,
      label: line.label,
      unit: line.unit,
      latestLabel: periodByKey.get(latest.period_key)?.label ?? latest.period_key,
      latestDisplay: latest.display_value ?? String(latestValue),
      priorLabel: periodByKey.get(prior.period_key)?.label ?? prior.period_key,
      priorDisplay: prior.display_value ?? String(priorValue),
      change,
      changeDisplay
    }];
  }, []);
}

export function amendmentSummary(
  view: FundamentalsStatementView | null,
  filings: FundamentalsFiling[] = []
): FundamentalsAmendmentSummary {
  const amendedPeriods = view?.periods.filter((period) => period.is_amendment).length ?? 0;
  const amendedCells = view?.lines.reduce(
    (count, line) => count + line.cells.filter((cell) => cell.is_amendment).length,
    0
  ) ?? 0;
  const amendmentRows = filings.filter((filing) => filing.is_amendment);
  const latestAmendmentDate = amendmentRows
    .map((filing) => filing.filing_date)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null;
  return {
    amendedPeriods,
    amendedCells,
    amendmentFilings: amendmentRows.length,
    latestAmendmentDate
  };
}

export function terminalValueFraming(
  scenario: FundamentalsDcfScenario | null
): FundamentalsTerminalFraming {
  const terminalGrowthRaw = scenario?.assumptions?.terminal_growth_pct;
  const waccRaw = scenario?.assumptions?.wacc_pct;
  const terminalGrowth = typeof terminalGrowthRaw === "number" ? terminalGrowthRaw : null;
  const wacc = typeof waccRaw === "number" ? waccRaw : null;
  const terminalValue = scenario?.summary?.terminal_value ?? null;
  const enterpriseValue = scenario?.summary?.enterprise_value ?? null;
  return {
    terminalGrowth,
    wacc,
    terminalValue,
    terminalValueShare:
      scenario?.summary?.discounted_terminal_value != null && enterpriseValue != null && enterpriseValue !== 0
        ? scenario.summary.discounted_terminal_value / enterpriseValue
        : null,
    impliedTerminalFcfMultiple:
      terminalGrowth != null && wacc != null && wacc > terminalGrowth
        ? (1 + terminalGrowth) / (wacc - terminalGrowth)
        : null
  };
}

export function snapshotDisplayName(name: string | null | undefined, createdAt: string | null | undefined) {
  const trimmed = String(name ?? "").trim();
  if (trimmed) {
    return trimmed;
  }
  if (!createdAt) {
    return "DCF snapshot";
  }
  return `Snapshot ${new Date(createdAt).toLocaleString("en-US", {
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
