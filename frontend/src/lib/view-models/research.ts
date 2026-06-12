import type {
  EquityResearchMode,
  CommodityCurveSnapshot,
  CommodityInstrument,
  CommodityMarketSummary,
  CommodityPriceHistory,
  CommodityWorkspaceResponse,
  GammaResearchObject,
  IvSurface,
  MacroContextState,
  MacroEventsResponse,
  MacroSnapshot,
  ResearchConstituent,
  ResearchCoverage,
  ResearchObjectReturnPoint,
  ResearchOverviewMetricId,
  ResearchOverviewNode,
  ResearchOverviewResponse,
  ResearchOverviewSortId,
  ResearchResult,
  SavedResearchItem,
  StrategyLabHandoffDefaultSide,
  StrategyLabHandoffEnvelope,
  StrategyLabResolvedHandoff,
  StrategyLabPortfolioLegInput,
  StrategyLabMode,
  StrategyLabPortfolioLegAssetClass,
  StrategyLabResult,
  ResearchStructure,
  ResearchWeightPoint
} from "../api/types";
import type { ChainRow, StrategyOptionType } from "./iv";

export type { EquityResearchMode, StrategyLabMode } from "../api/types";

export type ResearchMode = "overview" | "scope_analysis" | "strategy_lab" | "compare_scenario" | "saved_research";
export type ResearchSurface = "legacy" | "equity" | "strategy";
export type ResearchSurfaceMode = ResearchMode | EquityResearchMode | StrategyLabMode;
export type ResearchSurfaceModeKind =
  | "overview"
  | "scope_analysis"
  | "equity_comparables"
  | "equity_scenario_context"
  | "equity_saved"
  | "strategy_composer"
  | "strategy_backtest"
  | "strategy_regime"
  | "strategy_imports"
  | "strategy_saved"
  | "legacy_strategy"
  | "legacy_compare"
  | "legacy_saved"
  | "unknown";

export function classifyResearchSurfaceMode(
  surface: ResearchSurface,
  mode: ResearchSurfaceMode
): ResearchSurfaceModeKind {
  if (mode === "overview") {
    return "overview";
  }
  if (mode === "scope_analysis") {
    return "scope_analysis";
  }

  if (surface === "equity") {
    if (mode === "comparables") return "equity_comparables";
    if (mode === "scenario_context") return "equity_scenario_context";
    if (mode === "saved_equity_research") return "equity_saved";
    return "unknown";
  }

  if (surface === "strategy") {
    if (mode === "composer") return "strategy_composer";
    if (mode === "backtest_analyze") return "strategy_backtest";
    if (mode === "regime_stress") return "strategy_regime";
    if (mode === "imports") return "strategy_imports";
    if (mode === "saved_runs") return "strategy_saved";
    return "unknown";
  }

  if (mode === "strategy_lab") return "legacy_strategy";
  if (mode === "compare_scenario") return "legacy_compare";
  if (mode === "saved_research") return "legacy_saved";
  return "unknown";
}

export interface SyntheticPositionDraft {
  symbol: string;
  weight: number;
}

export interface ParsedResearchCsv {
  columns: string[];
  rows: Array<Record<string, string>>;
  warnings: string[];
}

export interface ResearchCompareOption {
  id: string;
  label: string;
  objectType: string;
  source: "scope" | "strategy" | "saved";
}

export interface StrategyComposerObjectOption {
  id: string;
  label: string;
  object: GammaResearchObject;
  defaultWeight: number;
}

export type StrategyPortfolioAssetClass = "equity" | "etf" | "commodity" | "prediction_contract" | "crypto" | "custom_stream";
export type StrategyPortfolioValueKind = "return" | "level";

export interface StrategyPortfolioDraftLeg {
  id: string;
  label: string;
  assetClass: StrategyPortfolioAssetClass;
  identifier: string;
  weight: number;
  valueKind: StrategyPortfolioValueKind;
  historyText: string;
  objectOptionId: string;
}

export interface StrategyPortfolioDraftSummary {
  legCount: number;
  grossExposure: number;
  netExposure: number;
  longExposure: number;
  shortExposure: number;
  inlineHistoryLegs: number;
  objectLegs: number;
  listedIdentifierLegs: number;
  warnings: string[];
}

export interface SavedScopeDraft {
  scopeType: "single_ticker" | "synthetic_portfolio";
  primarySymbol: string;
  benchmarkSymbol: string;
  lookbackDays: number;
  syntheticText: string;
}

export function defaultStrategyPortfolioDraftLeg(index: number): StrategyPortfolioDraftLeg {
  return {
    id: `draft-leg-${index}`,
    label: "",
    assetClass: "equity",
    identifier: "",
    weight: index === 1 ? 0.6 : index === 2 ? -0.4 : 0.1,
    valueKind: "return",
    historyText: "",
    objectOptionId: ""
  };
}

export function buildPredictionMarketStrategyHandoff(
  market: {
    market_id: string;
    venue: string;
    title: string;
    provider_market_id: string;
    provider_condition_id: string | null;
    provider_event_id: string | null;
    provider_series_id: string | null;
    probability_label: string | null;
    status: string;
    category: string | null;
    source_provider: string;
    origin: string;
    retrieved_at: string | null;
    end_time: string | null;
    freshness?: { status: string; is_stale: boolean; is_broken: boolean; reason: string | null } | null;
  },
  options: { sourceMode?: string | null; defaultWeight?: number; defaultSide?: StrategyLabHandoffDefaultSide } = {}
): StrategyLabHandoffEnvelope {
  const defaultSide = options.defaultSide === "long_no" ? "long_no" : "long_yes";
  const transformation = defaultSide === "long_no" ? "long_no_probability_return" : "long_yes_probability_return";
  const warnings = [
    "Prediction-market contracts enter Strategy Lab as research proxies, not executable positions.",
    `Resolver will default to ${transformation} unless the user edits the draft.`
  ];
  if (market.status !== "open") {
    warnings.push("Selected contract is not open; use only for historical research.");
  }
  if (market.freshness?.is_stale || market.freshness?.is_broken) {
    warnings.push(`Selected contract freshness is ${market.freshness.status}; resolver will re-check history.`);
  }

  return {
    source_tab: "prediction_markets",
    source_mode: options.sourceMode ?? "detail",
    intended_target_tab: "strategy_lab",
    intended_target_mode: "composer",
    selected_entity: {
      entity_type: "prediction_market_contract",
      label: market.title,
      normalized_id: market.market_id,
      provider_id: market.provider_market_id,
      native_id: market.provider_condition_id ?? market.provider_market_id,
      metadata: {
        venue: market.venue,
        status: market.status,
        category: market.category,
        probability_label: market.probability_label,
        end_time: market.end_time,
        provider_event_id: market.provider_event_id,
        provider_series_id: market.provider_series_id
      }
    },
    resolver_capability: "return_leg",
    asset_class: "prediction_market",
    value_kind: "probability",
    default_side: defaultSide,
    default_weight: options.defaultWeight ?? 0.1,
    selected_timeframe: null,
    provider: market.source_provider || market.venue,
    source: {
      origin: market.origin,
      retrieved_at: market.retrieved_at,
      venue: market.venue
    },
    warnings,
    normalized_ids: {
      market_id: market.market_id,
      provider_market_id: market.provider_market_id
    },
    timestamp: new Date().toISOString()
  };
}

export function buildEquityStrategyHandoff(
  equity: {
    symbol: string;
    label?: string | null;
    provider?: string | null;
    sourceProvider?: string | null;
    origin?: string | null;
    retrievedAt?: string | null;
  },
  options: { sourceMode?: string | null; defaultWeight?: number } = {}
): StrategyLabHandoffEnvelope {
  const symbol = equity.symbol.trim().toUpperCase();
  const label = (equity.label ?? symbol).trim() || symbol;
  const provider = equity.sourceProvider || equity.provider || null;
  const defaultWeight = options.defaultWeight ?? 0.1;
  const isShort = Number.isFinite(defaultWeight) && defaultWeight < 0;
  const warnings = [
    "Equity Research handoffs enter Strategy Lab as read-only research return streams, not execution instructions.",
    "Resolver will load listed-market history and preserve provider coverage warnings before composing."
  ];
  if (isShort) {
    warnings.push(
      "Negative weight marks this as a short research leg; Strategy Lab normalizes signed exposures by gross exposure."
    );
  }
  return {
    source_tab: "equity_research",
    source_mode: options.sourceMode ?? "scope_analysis",
    intended_target_tab: "strategy_lab",
    intended_target_mode: "composer",
    selected_entity: {
      entity_type: "equity_symbol",
      label,
      normalized_id: symbol,
      provider_id: symbol,
      native_id: symbol,
      metadata: {
        symbol,
        asset_class: "equity"
      }
    },
    resolver_capability: "return_leg",
    asset_class: "equity",
    value_kind: "return",
    default_side: isShort ? "short" : "long",
    default_weight: defaultWeight,
    selected_timeframe: null,
    provider,
    source: {
      origin: equity.origin ?? null,
      retrieved_at: equity.retrievedAt ?? null
    },
    warnings,
    normalized_ids: {
      symbol
    },
    timestamp: new Date().toISOString()
  };
}

export function buildCommodityStrategyHandoff(
  commodity: {
    instrument: CommodityInstrument;
    summary?: CommodityMarketSummary | null;
    history?: CommodityPriceHistory | null;
    curve?: CommodityCurveSnapshot | null;
    workspace?: CommodityWorkspaceResponse | null;
    provider?: string | null;
    sourceMode?: string | null;
  },
  options: { sourceMode?: string | null; defaultWeight?: number } = {}
): StrategyLabHandoffEnvelope {
  const instrument = commodity.instrument;
  const history = commodity.history ?? null;
  const curve = commodity.curve ?? null;
  const workspace = commodity.workspace ?? null;
  const provider = commodity.provider || history?.source_provider || instrument.source_provider || workspace?.source_provider || null;
  const sourceMode = options.sourceMode ?? commodity.sourceMode ?? "overview";
  const warnings = [
    "Commodity handoffs enter Strategy Lab as read-only research return streams, not execution instructions.",
    "Resolver will convert loaded commodity price/proxy history to returns and preserve futures, spot, proxy, and provider caveats.",
    "Commodity rows are not roll-adjusted futures strategies and do not model executable PnL."
  ];
  if (!history?.points.length) {
    warnings.push("Selected commodity has no loaded price history; resolver may attach it as reference-only.");
  } else if (history.points.length < 6) {
    warnings.push("Selected commodity history is sparse; resolver may reject it as reference-only.");
  }
  if (workspace?.coverage.coverage_status && workspace.coverage.coverage_status !== "live") {
    warnings.push(`Commodity coverage is ${workspace.coverage.coverage_status}; review provider/source limitations.`);
  }
  if (curve?.warnings.length) {
    warnings.push(...curve.warnings.slice(0, 3));
  }

  return {
    source_tab: "commodities",
    source_mode: sourceMode,
    intended_target_tab: "strategy_lab",
    intended_target_mode: "composer",
    selected_entity: {
      entity_type: "commodity_instrument",
      label: instrument.name,
      normalized_id: instrument.instrument_id,
      provider_id: instrument.front_symbol ?? instrument.provider_symbols[provider ?? ""] ?? instrument.symbol,
      native_id: instrument.front_symbol ?? instrument.symbol,
      metadata: {
        symbol: instrument.symbol,
        family: instrument.family,
        subgroup: instrument.subgroup,
        quote_unit: instrument.quote_unit,
        currency: instrument.currency,
        exchange: instrument.exchange,
        front_symbol: instrument.front_symbol,
        curve_state: commodity.summary?.curve_state ?? curve?.shape_label ?? null,
        history_points: history?.points.length ?? 0
      }
    },
    resolver_capability: "return_leg",
    asset_class: "commodity",
    value_kind: "price",
    default_side: "long",
    default_weight: options.defaultWeight ?? 0.1,
    selected_timeframe: history?.points.length
      ? {
          label: "Loaded commodity history",
          start: history.points[0]?.timestamp ?? null,
          end: history.points.at(-1)?.timestamp ?? null
        }
      : null,
    provider,
    source: {
      origin: history?.origin ?? instrument.origin ?? workspace?.origin ?? null,
      retrieved_at: history?.retrieved_at ?? instrument.retrieved_at ?? workspace?.retrieved_at ?? null,
      coverage_status: workspace?.coverage.coverage_status ?? null,
      source_provider: workspace?.source_provider ?? provider
    },
    warnings,
    normalized_ids: {
      instrument_id: instrument.instrument_id,
      symbol: instrument.symbol
    },
    timestamp: new Date().toISOString()
  };
}

export function buildMacroStrategyLensHandoff(
  macro: {
    context: MacroContextState;
    snapshot?: MacroSnapshot | null;
    events?: MacroEventsResponse | null;
  },
  options: { sourceMode?: MacroContextState["mode"] | null } = {}
): StrategyLabHandoffEnvelope {
  const context = macro.context;
  const snapshot = macro.snapshot ?? null;
  const events = macro.events ?? null;
  const sourceMode = options.sourceMode ?? context.mode;
  const themeLabel = context.theme === "all" ? "All macro" : context.theme.replace(/_/g, " ");
  const modeLabel = sourceMode.replace(/_/g, " ");
  const comparisonLabel = context.comparisonRegion ? ` vs ${context.comparisonRegion}` : "";
  const lensId = [
    "macro",
    context.region.toLowerCase(),
    context.timeframe.toLowerCase(),
    context.theme,
    sourceMode,
    context.comparisonRegion?.toLowerCase() ?? "none"
  ].join(":");
  const nextEvent = (events?.events ?? snapshot?.upcoming_events ?? [])[0] ?? null;
  const warnings = [
    "Macro handoffs enter Strategy Lab as read-only lenses, not weighted portfolio legs.",
    "Resolver will preserve region, timeframe, theme, mode, comparison, event, and provider context.",
    "Macro lenses annotate Strategy Lab interpretation; they do not create executable signals, orders, or rebalance rules."
  ];
  if (context.region === "Global") {
    warnings.push("Global Macro is a light V1 comparative lens; some analytics reuse US-first coverage.");
  } else if (context.region === "EU") {
    warnings.push("EU Macro coverage is lighter than the US-first Macro implementation.");
  }
  if (snapshot?.warnings.length) {
    warnings.push(...snapshot.warnings.slice(0, 3));
  }

  return {
    source_tab: "macro",
    source_mode: sourceMode,
    intended_target_tab: "strategy_lab",
    intended_target_mode: "lens",
    selected_entity: {
      entity_type: "macro_lens",
      label: `${context.region}${comparisonLabel} ${themeLabel} lens (${context.timeframe}, ${modeLabel})`,
      normalized_id: lensId,
      provider_id: snapshot?.source_provider ?? null,
      native_id: lensId,
      metadata: {
        region: context.region,
        timeframe: context.timeframe,
        theme: context.theme,
        mode: sourceMode,
        comparison_region: context.comparisonRegion,
        focus_count: snapshot?.focus_items?.length ?? 0,
        snapshot_card_count: snapshot?.snapshot_cards?.length ?? 0,
        divergence_count: snapshot?.top_divergences?.length ?? 0,
        event_count: events?.events?.length ?? snapshot?.upcoming_events?.length ?? 0,
        next_event_title: nextEvent?.title ?? null,
        next_event_at: nextEvent?.scheduled_at ?? null
      }
    },
    resolver_capability: "lens",
    asset_class: "macro",
    value_kind: "context",
    default_side: "none",
    default_weight: null,
    selected_timeframe: {
      label: context.timeframe,
      start: null,
      end: snapshot?.retrieved_at ?? null
    },
    provider: snapshot?.source_provider ?? null,
    source: {
      origin: snapshot?.origin ?? null,
      retrieved_at: snapshot?.retrieved_at ?? null,
      source_provider: snapshot?.source_provider ?? null,
      transformation_note: snapshot?.transformation_note ?? null
    },
    warnings,
    normalized_ids: {
      macro_lens_id: lensId,
      region: context.region,
      timeframe: context.timeframe,
      theme: context.theme,
      mode: sourceMode
    },
    timestamp: new Date().toISOString()
  };
}

export function buildOptionsStrategyHandoff(
  option: {
    surface: IvSurface;
    row: ChainRow;
    optionType: StrategyOptionType;
    sourceMode?: string | null;
  },
  options: { sourceMode?: string | null } = {}
): StrategyLabHandoffEnvelope {
  const surface = option.surface;
  const row = option.row;
  const optionType = option.optionType;
  const right = optionType === "call" ? "C" : "P";
  const premium = optionType === "call" ? row.callMidpoint : row.putMidpoint;
  const iv = optionType === "call" ? row.callIv : row.putIv;
  const delta = optionType === "call" ? row.callDelta : row.putDelta;
  const openInterest = optionType === "call" ? row.callOpenInterest : row.putOpenInterest;
  const volume = optionType === "call" ? row.callVolume : row.putVolume;
  const priceSource = optionType === "call" ? row.callPriceSource : row.putPriceSource;
  const contractId = optionType === "call" ? row.pair.call_contract_id : row.pair.put_contract_id;
  const normalizedId = [
    "iv",
    surface.symbol.trim().toUpperCase(),
    row.expiry,
    right,
    Number(row.strike).toString()
  ].join(":");
  const label = `${surface.symbol.trim().toUpperCase()} ${row.expiry} ${row.strike} ${right}`;
  const warnings = [
    "Options handoffs enter Strategy Lab as read-only volatility overlays, not weighted return legs.",
    "The current Options workspace has snapshot contract prices, IV, Greeks, and chain quality but no durable option-contract price history for return-stream composition.",
    "This overlay does not create executable option orders, strategy signals, broker mutations, or rebalance behavior."
  ];
  if (premium == null || !Number.isFinite(premium) || premium <= 0) {
    warnings.push("Selected option side has no usable premium; Strategy Lab will keep it as context only.");
  }
  if (iv == null || !Number.isFinite(iv) || iv <= 0) {
    warnings.push("Selected option side has no usable implied volatility; review source quality before using this context.");
  }
  if (surface.delayed) {
    warnings.push("Options surface is delayed; treat the overlay as historical/provider context.");
  }
  if (surface.quality?.interpolation_ratio != null && surface.quality.interpolation_ratio > 0.35) {
    warnings.push("Options surface uses substantial interpolation; inspect source quality before relying on the overlay.");
  }
  if (surface.warnings.length) {
    warnings.push(...surface.warnings.slice(0, 3));
  }

  return {
    source_tab: "iv",
    source_mode: options.sourceMode ?? option.sourceMode ?? "chain",
    intended_target_tab: "strategy_lab",
    intended_target_mode: "composer",
    selected_entity: {
      entity_type: "option_contract",
      label,
      normalized_id: normalizedId,
      provider_id: contractId,
      native_id: contractId ?? normalizedId,
      metadata: {
        symbol: surface.symbol.trim().toUpperCase(),
        expiry: row.expiry,
        right,
        option_type: optionType,
        strike: row.strike,
        spot: surface.spot,
        days_to_expiry: row.pair.days_to_expiry,
        premium,
        price_source: priceSource,
        implied_volatility: iv,
        blended_implied_volatility: row.blendedIv,
        delta,
        open_interest: openInterest,
        volume,
        moneyness: row.moneyness,
        distance_pct: row.distancePct,
        straddle_midpoint: row.straddleMidpoint,
        implied_move_pct: row.impliedMovePct,
        snapshot_timestamp: surface.timestamp,
        freshness_label: surface.freshness_label,
        delayed: surface.delayed,
        surface_model: surface.surface_model ?? "linear",
        quality: surface.quality
          ? {
              expected_surface_cells: surface.quality.expected_surface_cells,
              observed_surface_cells: surface.quality.observed_surface_cells,
              interpolated_surface_cells: surface.quality.interpolated_surface_cells,
              interpolation_ratio: surface.quality.interpolation_ratio,
              contracts_with_bid_ask: surface.quality.contracts_with_bid_ask,
              contracts_with_provider_greeks: surface.quality.contracts_with_provider_greeks,
              contracts_with_derived_greeks: surface.quality.contracts_with_derived_greeks
            }
          : null
      }
    },
    resolver_capability: "overlay",
    asset_class: "other",
    value_kind: "context",
    default_side: "none",
    default_weight: null,
    selected_timeframe: surface.timestamp
      ? {
          label: `Options snapshot ${surface.symbol.trim().toUpperCase()}`,
          start: null,
          end: surface.timestamp
        }
      : null,
    provider: surface.source_provider,
    source: {
      origin: surface.origin,
      retrieved_at: surface.retrieved_at,
      source_provider: surface.source_provider,
      freshness_label: surface.freshness_label,
      transformation_note: surface.transformation_note,
      market_data_mode: surface.collection?.market_data_mode ?? null,
      depth_preset: surface.collection?.depth_preset ?? null
    },
    warnings,
    normalized_ids: {
      symbol: surface.symbol.trim().toUpperCase(),
      option_contract_id: normalizedId,
      provider_contract_id: contractId ?? "",
      expiry: row.expiry,
      right,
      strike: Number(row.strike).toString()
    },
    timestamp: new Date().toISOString()
  };
}

export function strategyResolvedHandoffToDraftLeg(
  resolved: StrategyLabResolvedHandoff,
  index: number
): StrategyPortfolioDraftLeg | null {
  const leg = resolved.composer_draft_leg;
  if (!leg) {
    return null;
  }
  return {
    ...defaultStrategyPortfolioDraftLeg(index),
    label: leg.label,
    assetClass: normalizeDraftAssetClass(leg.asset_class),
    identifier: leg.identifier,
    weight: leg.weight,
    valueKind: leg.value_kind,
    historyText: strategyDraftHistoryText(leg.return_points),
    objectOptionId: ""
  };
}

function normalizeDraftAssetClass(assetClass: StrategyLabPortfolioLegAssetClass): StrategyPortfolioAssetClass {
  if (assetClass === "prediction_contract") return "prediction_contract";
  if (assetClass === "equity") return "equity";
  if (assetClass === "etf") return "etf";
  if (assetClass === "commodity") return "commodity";
  if (assetClass === "crypto") return "crypto";
  return "custom_stream";
}

function strategyDraftHistoryText(points: ResearchObjectReturnPoint[]) {
  const rows = points.map((point) => `${point.timestamp},${point.value}`);
  return ["date,value", ...rows].join("\n");
}

export function parseStrategyPortfolioHistoryText(text: string): {
  points: ResearchObjectReturnPoint[];
  warnings: string[];
} {
  const trimmed = text.trim();
  if (!trimmed) {
    return { points: [], warnings: [] };
  }
  const parsed = parseResearchCsvText(trimmed.includes("\n") ? trimmed : `date,value\n${trimmed}`);
  const columns = parsed.columns;
  const dateColumn = columns.find((column) => /^date|time|timestamp$/i.test(column)) ?? columns[0] ?? "date";
  const valueColumn =
    columns.find((column) => /return|value|level|nav|prob|price/i.test(column) && column !== dateColumn) ??
    columns.find((column) => column !== dateColumn) ??
    columns[1] ??
    "value";
  const warnings = [...parsed.warnings];
  const points: ResearchObjectReturnPoint[] = [];
  parsed.rows.forEach((row, index) => {
    const timestamp = String(row[dateColumn] ?? "").trim();
    const rawValue = String(row[valueColumn] ?? "").trim();
    const value = parsePortfolioHistoryNumber(rawValue);
    if (!timestamp || value == null) {
      warnings.push(`Inline history row ${index + 2} is missing a usable date or value.`);
      return;
    }
    points.push({ timestamp, value });
  });
  return { points, warnings };
}

function parsePortfolioHistoryNumber(value: string): number | null {
  const raw = value.trim();
  if (!raw) {
    return null;
  }
  const isPercent = raw.endsWith("%");
  const normalized = Number(raw.replace(/%$/, "").replaceAll(",", ""));
  if (!Number.isFinite(normalized)) {
    return null;
  }
  return isPercent ? normalized / 100 : normalized;
}

export function summarizeStrategyPortfolioDraft(legs: StrategyPortfolioDraftLeg[]): StrategyPortfolioDraftSummary {
  const active = legs.filter((leg) => Number.isFinite(Number(leg.weight)) && Number(leg.weight) !== 0);
  const grossExposure = active.reduce((sum, leg) => sum + Math.abs(Number(leg.weight)), 0);
  const longExposure = active.filter((leg) => Number(leg.weight) > 0).reduce((sum, leg) => sum + Number(leg.weight), 0);
  const shortExposure = active.filter((leg) => Number(leg.weight) < 0).reduce((sum, leg) => sum + Math.abs(Number(leg.weight)), 0);
  const inlineHistoryLegs = active.filter((leg) => leg.historyText.trim()).length;
  const objectLegs = active.filter((leg) => leg.objectOptionId).length;
  const listedIdentifierLegs = active.filter((leg) => !leg.objectOptionId && !leg.historyText.trim() && leg.identifier.trim()).length;
  const warnings: string[] = [];
  if (!active.length) {
    warnings.push("Add at least one non-zero portfolio leg.");
  }
  const missing = active.filter((leg) => !leg.objectOptionId && !leg.identifier.trim() && !leg.historyText.trim());
  if (missing.length) {
    warnings.push(`${missing.length} active leg(s) need an object, identifier, or inline history.`);
  }
  if (grossExposure > 0 && Math.abs(longExposure - shortExposure) < 0.05 * grossExposure) {
    warnings.push("Net exposure is close to market neutral; performance will be dominated by relative leg moves.");
  }
  return {
    legCount: active.length,
    grossExposure,
    netExposure: longExposure - shortExposure,
    longExposure,
    shortExposure,
    inlineHistoryLegs,
    objectLegs,
    listedIdentifierLegs,
    warnings
  };
}

export function buildStrategyPortfolioLegInputs(
  legs: StrategyPortfolioDraftLeg[],
  objectOptions: StrategyComposerObjectOption[]
): { legs: StrategyLabPortfolioLegInput[]; warnings: string[] } {
  const objectById = new Map(objectOptions.map((option) => [option.id, option.object]));
  const warnings: string[] = [];
  const inputs: StrategyLabPortfolioLegInput[] = [];
  for (const leg of legs) {
    const weight = Number(leg.weight);
    if (!Number.isFinite(weight) || weight === 0) {
      continue;
    }
    const selectedObject = leg.objectOptionId ? objectById.get(leg.objectOptionId) ?? null : null;
    if (leg.objectOptionId && !selectedObject) {
      warnings.push(`${leg.label || leg.objectOptionId} is no longer available as a Strategy Lab object.`);
      continue;
    }
    const parsedHistory = parseStrategyPortfolioHistoryText(leg.historyText);
    warnings.push(...parsedHistory.warnings.map((warning) => `${leg.label || leg.identifier || leg.id}: ${warning}`));
    if (!selectedObject && !parsedHistory.points.length && !leg.identifier.trim()) {
      warnings.push(`${leg.label || leg.id} needs an object, identifier, or inline history.`);
      continue;
    }
    inputs.push({
      label: leg.label.trim() || selectedObject?.display_name || leg.identifier.trim().toUpperCase() || leg.id,
      asset_class: leg.assetClass,
      identifier: leg.identifier.trim().toUpperCase(),
      weight,
      value_kind: leg.valueKind,
      return_points: parsedHistory.points,
      object: selectedObject
    });
  }
  return { legs: inputs, warnings };
}

export interface ResearchPreviewRow {
  symbol: string;
  inputWeight: number;
  normalizedWeight: number;
}

export interface WeightSummary {
  totalWeight: number;
  normalizedTopWeight: number | null;
  top5Weight: number | null;
  concentrationHhi: number | null;
  effectivePositions: number | null;
}

export interface ResearchTreemapRect {
  node: ResearchOverviewNode;
  x: number;
  y: number;
  width: number;
  height: number;
  size: number;
  metricValue: number | null;
}

export interface ResearchTreemapTile {
  node: ResearchOverviewNode;
  rect: TreemapRect;
  metricWeight: number;
  metricValue: number | null;
  colorValue: number | null;
}

export interface ResearchTreemapSection {
  label: string;
  rect: TreemapRect;
  tiles: ResearchTreemapTile[];
  metricWeight: number;
  nodeCount: number;
}

export interface TreemapRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function parseSyntheticText(text: string): SyntheticPositionDraft[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [symbol, weight] = line.split(/[\s,:]+/);
      return {
        symbol: (symbol ?? "").trim().toUpperCase(),
        weight: Number(weight)
      };
    })
    .filter((item) => item.symbol);
}

export function parseResearchCsvText(text: string): ParsedResearchCsv {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) {
    return { columns: [], rows: [], warnings: ["Paste CSV rows before analyzing a strategy."] };
  }

  const columns = parseCsvLine(lines[0] ?? "").map((column) => column.trim()).filter(Boolean);
  if (!columns.length) {
    return { columns: [], rows: [], warnings: ["CSV header row is empty."] };
  }

  const warnings: string[] = [];
  const rows = lines.slice(1).map((line, index) => {
    const values = parseCsvLine(line);
    if (values.length !== columns.length) {
      warnings.push(`Row ${index + 2} has ${values.length} cells; expected ${columns.length}.`);
    }
    return Object.fromEntries(columns.map((column, columnIndex) => [column, values[columnIndex] ?? ""]));
  });

  if (!rows.length) {
    warnings.push("CSV has a header but no data rows.");
  }
  return { columns, rows, warnings };
}

function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}

export function buildResearchCompareOptions(
  scopeResult: ResearchResult | null,
  strategyResult: StrategyLabResult | null,
  savedItems: SavedResearchItem[]
): ResearchCompareOption[] {
  const options: ResearchCompareOption[] = [];
  if (scopeResult?.performance_points?.length) {
    options.push({
      id: "scope:latest",
      label: scopeResult.scope_type === "single_ticker" ? `Scope: ${scopeResult.primary_symbol ?? "Single Ticker"}` : "Scope: Synthetic Basket",
      objectType: "scope_analysis",
      source: "scope"
    });
  }
  if (strategyResult?.returns_points?.length) {
    options.push({
      id: "strategy:latest",
      label: `Strategy: ${strategyResult.name}`,
      objectType: "strategy_lab",
      source: "strategy"
    });
  }
  for (const item of savedItems) {
    if (!savedResearchHasReturnStream(item)) {
      continue;
    }
    options.push({
      id: `saved:${item.id}`,
      label: `Saved: ${item.title}`,
      objectType: item.object_type,
      source: "saved"
    });
  }
  return options;
}

export function savedResearchHasReturnStream(item: SavedResearchItem) {
  const payload = item.payload ?? {};
  const candidates = [payload];
  for (const key of ["result", "strategy_result", "analysis", "payload"]) {
    const nested = (payload as Record<string, unknown>)[key];
    if (isPlainRecord(nested)) {
      candidates.push(nested);
    }
  }
  return candidates.some((candidate) =>
    ["returns_points", "return_points", "performance_points", "portfolio_return_points"].some((key) =>
      Array.isArray((candidate as Record<string, unknown>)[key])
    )
  );
}

export function buildStrategyComposerObjects(
  scopeResult: ResearchResult | null,
  strategyResult: StrategyLabResult | null,
  savedItems: SavedResearchItem[]
): StrategyComposerObjectOption[] {
  const options: StrategyComposerObjectOption[] = [];
  const scopeObject = buildResearchObjectFromScopeResult(scopeResult);
  if (scopeObject) {
    options.push({ id: "latest_scope", label: scopeObject.display_name, object: scopeObject, defaultWeight: 0.5 });
  }
  const strategyObject = buildResearchObjectFromStrategyResult(strategyResult);
  if (strategyObject) {
    options.push({ id: "latest_strategy", label: strategyObject.display_name, object: strategyObject, defaultWeight: 0.5 });
  }
  for (const item of savedItems) {
    const restored = hydrateStrategyLabResultFromSaved(item);
    const object = buildResearchObjectFromStrategyResult(restored);
    if (object) {
      options.push({
        id: `saved:${item.id}`,
        label: `Saved: ${item.title}`,
        object: { ...object, object_id: `saved:${item.id}` },
        defaultWeight: 0.25
      });
    }
  }
  return options;
}

export function classifySavedResearchSurface(item: SavedResearchItem): "equity" | "strategy" | "unknown" {
  if (["scope_analysis", "equity_scope", "equity_screen"].includes(item.object_type)) {
    return "equity";
  }
  if (
    ["strategy_lab", "strategy_return_stream", "strategy_composition"].includes(item.object_type) ||
    savedResearchHasReturnStream(item)
  ) {
    return "strategy";
  }
  return "unknown";
}

export function buildResearchObjectFromScopeResult(result: ResearchResult | null): GammaResearchObject | null {
  const returnPoints = normalizeResearchObjectReturnPoints(result?.performance_points);
  if (!result || !returnPoints.length) {
    return null;
  }

  const symbols = (result.weights ?? []).map((weight) => weight.symbol).filter(Boolean);
  const start = returnPoints[0]?.timestamp ?? null;
  const end = returnPoints[returnPoints.length - 1]?.timestamp ?? null;
  const displayName =
    result.scope_type === "single_ticker"
      ? result.primary_symbol ?? symbols[0] ?? "Equity Scope"
      : "Synthetic Basket";
  const signature = buildDeterministicSignature({
    weights: normalizeWeightSignature(result.weights),
    return_points: normalizeReturnPointSignature(returnPoints)
  });

  return {
    object_id: ["equity_scope", result.scope_type, symbols.join(","), start, end, signature].filter(Boolean).join(":"),
    object_type: "equity_scope",
    display_name: displayName,
    source_tab: "equity_research",
    source_mode: "scope_analysis",
    resolver_capabilities: ["return_leg", "benchmark"],
    symbols,
    constituents: copyRecords(result.constituents),
    weights: copyRecords(result.weights),
    available_start: start,
    available_end: end,
    provider_summary: result.history_source_label ?? result.source_provider ?? null,
    provenance: {
      source_provider: result.source_provider ?? null,
      freshness_label: result.freshness_label ?? null
    },
    warnings: result.warnings ?? [],
    return_points: returnPoints
  };
}

export function buildResearchObjectFromStrategyResult(result: StrategyLabResult | null): GammaResearchObject | null {
  const returnPoints = normalizeResearchObjectReturnPoints(result?.returns_points);
  if (!result || !returnPoints.length) {
    return null;
  }

  const start = returnPoints[0]?.timestamp ?? null;
  const end = returnPoints[returnPoints.length - 1]?.timestamp ?? null;
  const signature = buildDeterministicSignature({
    return_points: normalizeReturnPointSignature(returnPoints)
  });
  return {
    object_id: ["strategy_return_stream", result.name, start, end, signature].filter(Boolean).join(":"),
    object_type: "strategy_return_stream",
    display_name: result.name || "Strategy Return Stream",
    source_tab: "strategy_lab",
    source_mode: "imports",
    resolver_capabilities: ["return_leg", "benchmark"],
    symbols: [],
    constituents: [],
    weights: [],
    available_start: start,
    available_end: end,
    provider_summary: result.source_provider ?? null,
    provenance: {
      source_provider: result.source_provider,
      retrieved_at: result.retrieved_at,
      origin: result.origin,
      freshness_label: result.freshness_label
    },
    warnings: result.warnings ?? [],
    return_points: returnPoints
  };
}

export function savedResearchScopeDraft(item: SavedResearchItem): SavedScopeDraft | null {
  if (item.object_type !== "scope_analysis") {
    return null;
  }
  const payload = item.payload ?? {};
  const builder = isPlainRecord(payload.builder_state) ? payload.builder_state : {};
  const rawScopeType = String(builder.scope_type ?? payload.scope_type ?? "");
  const scopeType = rawScopeType === "synthetic_portfolio" ? "synthetic_portfolio" : "single_ticker";
  const benchmarkSymbol = String(builder.benchmark_symbol ?? payload.benchmark_symbol ?? "SPY").trim().toUpperCase() || "SPY";
  const lookbackDays = Number(builder.lookback_days ?? payload.lookback_days ?? 252);

  if (scopeType === "single_ticker") {
    const primarySymbol = String(builder.primary_symbol ?? payload.primary_symbol ?? firstWeightSymbol(payload)).trim().toUpperCase();
    return primarySymbol
      ? {
          scopeType,
          primarySymbol,
          benchmarkSymbol,
          lookbackDays: Number.isFinite(lookbackDays) && lookbackDays > 0 ? lookbackDays : 252,
          syntheticText: ""
        }
      : null;
  }

  const syntheticText =
    typeof builder.synthetic_text === "string" && builder.synthetic_text.trim()
      ? builder.synthetic_text.trim()
      : weightsToSyntheticText(payload.weights);
  return syntheticText
    ? {
        scopeType,
        primarySymbol: "",
        benchmarkSymbol,
        lookbackDays: Number.isFinite(lookbackDays) && lookbackDays > 0 ? lookbackDays : 252,
        syntheticText
      }
    : null;
}

export function savedResearchCanReloadScope(item: SavedResearchItem) {
  return savedResearchScopeDraft(item) !== null;
}

export function hydrateStrategyLabResultFromSaved(item: SavedResearchItem): StrategyLabResult | null {
  if (item.object_type !== "strategy_lab") {
    return null;
  }
  const payload = item.payload ?? {};
  if (!isPlainRecord(payload.metrics) || !Array.isArray(payload.returns_points)) {
    return null;
  }
  return {
    name: String(payload.name ?? item.title ?? "Saved Strategy"),
    value_kind: String(payload.value_kind ?? "return"),
    benchmark_column: typeof payload.benchmark_column === "string" ? payload.benchmark_column : null,
    benchmark_value_kind: String(payload.benchmark_value_kind ?? "return"),
    metrics: payload.metrics as unknown as StrategyLabResult["metrics"],
    returns_points: payload.returns_points as StrategyLabResult["returns_points"],
    equity_curve_points: Array.isArray(payload.equity_curve_points) ? (payload.equity_curve_points as StrategyLabResult["equity_curve_points"]) : [],
    drawdown_points: Array.isArray(payload.drawdown_points) ? (payload.drawdown_points as StrategyLabResult["drawdown_points"]) : [],
    benchmark_points: Array.isArray(payload.benchmark_points) ? (payload.benchmark_points as StrategyLabResult["benchmark_points"]) : [],
    benchmark_equity_curve_points: Array.isArray(payload.benchmark_equity_curve_points)
      ? (payload.benchmark_equity_curve_points as StrategyLabResult["benchmark_equity_curve_points"])
      : [],
    rolling_points: Array.isArray(payload.rolling_points) ? (payload.rolling_points as StrategyLabResult["rolling_points"]) : [],
    monthly_returns: Array.isArray(payload.monthly_returns) ? (payload.monthly_returns as StrategyLabResult["monthly_returns"]) : [],
    annual_returns: Array.isArray(payload.annual_returns) ? (payload.annual_returns as StrategyLabResult["annual_returns"]) : [],
    warnings: Array.isArray(payload.warnings) ? (payload.warnings as string[]) : item.warnings,
    source_provider: String(payload.source_provider ?? item.source_provider ?? "uploaded_csv"),
    retrieved_at: String(payload.retrieved_at ?? item.retrieved_at ?? item.updated_at),
    origin: String(payload.origin ?? item.origin ?? "saved_research_store"),
    transformation_note:
      typeof payload.transformation_note === "string" ? payload.transformation_note : item.transformation_note,
    freshness_label: String(payload.freshness_label ?? "derived")
  };
}

export function savedResearchCanReloadStrategy(item: SavedResearchItem) {
  return hydrateStrategyLabResultFromSaved(item) !== null;
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function copyRecords<T extends object>(items: T[] | null | undefined): Record<string, unknown>[] {
  return (items ?? []).map((item) => ({ ...(item as Record<string, unknown>) }));
}

function normalizeResearchObjectReturnPoints(
  points: ResearchObjectReturnPoint[] | null | undefined
): ResearchObjectReturnPoint[] {
  return (points ?? []).map((point) => ({
    timestamp: point.timestamp,
    value: point.value
  }));
}

function normalizeWeightSignature(weights: ResearchWeightPoint[] | null | undefined) {
  const normalizedWeights = (weights ?? [])
    .map((weight) => ({
      symbol: weight.symbol.trim().toUpperCase(),
      weight: normalizeSignatureNumber(weight.weight)
    }))
    .filter((weight) => weight.symbol && weight.weight !== null);
  const total = normalizedWeights.reduce((sum, weight) => sum + (weight.weight ?? 0), 0);
  return normalizedWeights
    .map((weight) => ({
      symbol: weight.symbol,
      weight: total > 0 && weight.weight !== null ? normalizeSignatureNumber(weight.weight / total) : weight.weight
    }))
    .sort((left, right) => left.symbol.localeCompare(right.symbol));
}

function normalizeReturnPointSignature(points: ResearchObjectReturnPoint[] | null | undefined) {
  return (points ?? []).map((point) => ({
    timestamp: point.timestamp,
    value: normalizeSignatureNumber(point.value)
  }));
}

function normalizeSignatureNumber(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }
  const normalized = Number(value.toPrecision(12));
  return Object.is(normalized, -0) ? 0 : normalized;
}

function buildDeterministicSignature(value: unknown) {
  let hash = 2166136261;
  for (const char of stableCompactJson(value)) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function stableCompactJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableCompactJson).join(",")}]`;
  }
  if (isPlainRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableCompactJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function firstWeightSymbol(payload: Record<string, unknown>) {
  const weights = payload.weights;
  if (!Array.isArray(weights)) {
    return "";
  }
  const first = weights.find(isPlainRecord);
  return first ? String(first.symbol ?? "") : "";
}

function weightsToSyntheticText(weights: unknown) {
  if (!Array.isArray(weights)) {
    return "";
  }
  return weights
    .filter(isPlainRecord)
    .map((weight) => {
      const symbol = String(weight.symbol ?? "").trim().toUpperCase();
      const value = Number(weight.weight);
      return symbol && Number.isFinite(value) && value > 0 ? `${symbol} ${value.toFixed(4)}` : "";
    })
    .filter(Boolean)
    .join("\n");
}

export function normalizeSyntheticText(text: string): string {
  const parsed = parseSyntheticText(text).filter((item) => Number.isFinite(item.weight) && item.weight > 0);
  const total = parsed.reduce((sum, item) => sum + item.weight, 0);
  if (total <= 0) {
    return text;
  }
  return parsed
    .map((item) => `${item.symbol} ${(item.weight / total).toFixed(4)}`)
    .join("\n");
}

export function buildPreviewRows(
  scopeType: "single_ticker" | "synthetic_portfolio",
  primarySymbol: string,
  parsedSynthetic: SyntheticPositionDraft[]
): ResearchPreviewRow[] {
  if (scopeType === "single_ticker") {
    const symbol = primarySymbol.trim().toUpperCase();
    return symbol ? [{ symbol, inputWeight: 1, normalizedWeight: 1 }] : [];
  }

  const valid = parsedSynthetic.filter((item) => item.symbol && Number.isFinite(item.weight) && item.weight > 0);
  const totalWeight = valid.reduce((sum, item) => sum + item.weight, 0);
  return valid.map((item) => ({
    symbol: item.symbol,
    inputWeight: item.weight,
    normalizedWeight: totalWeight > 0 ? item.weight / totalWeight : 0
  }));
}

export function doesResearchDraftMatchResult(
  result: ResearchResult | null,
  draft: {
    scopeType: "single_ticker" | "synthetic_portfolio";
    primarySymbol: string;
    benchmarkSymbol: string;
  },
  previewRows: ResearchPreviewRow[]
): boolean {
  if (!result) {
    return false;
  }

  const normalizedBenchmark = draft.benchmarkSymbol.trim().toUpperCase() || "SPY";
  if (result.scope_type !== draft.scopeType || result.benchmark_symbol !== normalizedBenchmark) {
    return false;
  }

  if (draft.scopeType === "single_ticker") {
    return (result.primary_symbol ?? "") === (draft.primarySymbol.trim().toUpperCase() || "");
  }

  const normalizedPreview = [...previewRows]
    .map((row) => ({
      symbol: row.symbol,
      weight: Number(row.normalizedWeight.toFixed(4))
    }))
    .sort((left, right) => left.symbol.localeCompare(right.symbol));
  const normalizedResult = [...(result.weights ?? [])]
    .map((row) => ({
      symbol: row.symbol,
      weight: Number(row.weight.toFixed(4))
    }))
    .sort((left, right) => left.symbol.localeCompare(right.symbol));

  if (normalizedPreview.length !== normalizedResult.length) {
    return false;
  }

  return normalizedPreview.every((row, index) => {
    const candidate = normalizedResult[index];
    return candidate != null && candidate.symbol === row.symbol && Math.abs(candidate.weight - row.weight) < 1e-4;
  });
}

export function deriveStructureFromWeights(weights: ResearchWeightPoint[]): ResearchStructure {
  const summary = summarizeWeights(weights);
  return {
    total_weight: summary.totalWeight || null,
    top_weight: summary.normalizedTopWeight,
    top5_weight: summary.top5Weight,
    concentration_hhi: summary.concentrationHhi,
    effective_positions: summary.effectivePositions,
    aligned_symbol_count: weights.length
  };
}

export function deriveCoverageFromResearchResult(result: ResearchResult | null): ResearchCoverage {
  if (!result) {
    return {
      available_symbols: [],
      missing_symbols: [],
      benchmark_overlap_count: 0
    };
  }

  const available = result.weights?.map((item) => item.symbol) ?? [];
  const allSnapshotSymbols =
    result.snapshot?.positions
      ?.map((position) => position.symbol)
      .filter((symbol) => !String(symbol ?? "").startsWith("CASH")) ?? [];

  return {
    available_symbols: available,
    missing_symbols: allSnapshotSymbols.filter((symbol) => !available.includes(symbol)),
    benchmark_overlap_count: 0
  };
}

export function deriveConstituentsFromResearchResult(result: ResearchResult | null): ResearchConstituent[] {
  if (!result?.weights?.length) {
    return [];
  }

  return result.weights.map((weight) => ({
    symbol: weight.symbol,
    weight: weight.weight,
    instrument_id: weight.instrument_id,
    display_symbol: weight.display_symbol,
    total_return: null,
    annual_vol: null,
    max_drawdown: null,
    weighted_return: null
  }));
}

export function hasPopulatedStructure(structure: ResearchStructure | null | undefined): boolean {
  return Boolean(structure && (structure.aligned_symbol_count > 0 || structure.total_weight != null));
}

export function hasPopulatedCoverage(coverage: ResearchCoverage | null | undefined): boolean {
  return Boolean(
    coverage &&
      (coverage.available_symbols.length > 0 ||
        coverage.missing_symbols.length > 0 ||
        coverage.benchmark_overlap_count > 0)
  );
}

export function summarizeWeights(weights: ResearchWeightPoint[]): WeightSummary {
  if (!weights.length) {
    return {
      totalWeight: 0,
      normalizedTopWeight: null,
      top5Weight: null,
      concentrationHhi: null,
      effectivePositions: null
    };
  }
  const absoluteWeights = weights.map((item) => Math.abs(item.weight));
  const totalWeight = absoluteWeights.reduce((sum, value) => sum + value, 0);
  if (totalWeight <= 0) {
    return {
      totalWeight,
      normalizedTopWeight: null,
      top5Weight: null,
      concentrationHhi: null,
      effectivePositions: null
    };
  }
  const normalized = absoluteWeights.map((value) => value / totalWeight);
  const hhi = normalized.reduce((sum, value) => sum + value * value, 0);
  return {
    totalWeight,
    normalizedTopWeight: Math.max(...normalized),
    top5Weight: normalized.sort((left, right) => right - left).slice(0, 5).reduce((sum, value) => sum + value, 0),
    concentrationHhi: hhi,
    effectivePositions: hhi > 0 ? 1 / hhi : null
  };
}

export function getResearchOverviewMetricValue(
  node: ResearchOverviewNode,
  metricId: ResearchOverviewMetricId
): number | null {
  switch (metricId) {
    case "return":
      return node.metrics.total_return;
    case "volatility":
      return node.metrics.annual_volatility;
    case "beta":
      return node.metrics.beta;
    case "drawdown":
      return node.metrics.max_drawdown;
    case "relative_return":
      return node.metrics.relative_return;
  }
}

export function formatResearchOverviewMetricValue(
  value: number | null | undefined,
  metricId: ResearchOverviewMetricId
) {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  if (metricId === "beta") {
    return value.toFixed(2);
  }
  return `${(value * 100).toFixed(1)}%`;
}

interface ResearchSortMetricConfig {
  label: string;
  direction: "asc" | "desc";
  extractor: (node: ResearchOverviewNode) => number | null | undefined;
  weightTransform?: (value: number) => number;
}

const RESEARCH_SORT_METRIC_CONFIG: Record<ResearchOverviewSortId, ResearchSortMetricConfig> = {
  market_cap_desc: {
    label: "Market Cap",
    direction: "desc",
    extractor: (node) => node.market_cap_usd
  },
  universe_weight_desc: {
    label: "Universe Weight",
    direction: "desc",
    extractor: (node) => node.weight ?? node.size
  },
  return_desc: {
    label: "Return",
    direction: "desc",
    extractor: (node) => node.metrics.total_return
  },
  volatility_desc: {
    label: "Volatility",
    direction: "desc",
    extractor: (node) => node.metrics.annual_volatility
  },
  beta_desc: {
    label: "Beta",
    direction: "desc",
    extractor: (node) => node.metrics.beta
  },
  drawdown_desc: {
    label: "Drawdown",
    direction: "desc",
    extractor: (node) => node.metrics.max_drawdown,
    weightTransform: (value) => Math.abs(value)
  }
};

export function researchSortMetricLabel(sortBy: ResearchOverviewSortId) {
  return RESEARCH_SORT_METRIC_CONFIG[sortBy]?.label ?? "Market Cap";
}

export function getResearchOverviewSortValue(
  node: ResearchOverviewNode,
  sortBy: ResearchOverviewSortId
): number | null {
  const extracted = RESEARCH_SORT_METRIC_CONFIG[sortBy]?.extractor(node);
  return extracted == null || !Number.isFinite(extracted) ? null : extracted;
}

export function formatResearchOverviewSortValue(
  value: number | null | undefined,
  sortBy: ResearchOverviewSortId
): string {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  switch (sortBy) {
    case "market_cap_desc": {
      const absolute = Math.abs(value);
      if (absolute >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
      if (absolute >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
      if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
      return `$${value.toFixed(0)}`;
    }
    case "universe_weight_desc":
      return value >= 1_000_000 ? formatResearchOverviewSortValue(value, "market_cap_desc") : value.toFixed(2);
    case "beta_desc":
      return value.toFixed(2);
    case "return_desc":
      return formatResearchOverviewMetricValue(value, "return");
    case "volatility_desc":
      return formatResearchOverviewMetricValue(value, "volatility");
    case "drawdown_desc":
      return formatResearchOverviewMetricValue(value, "drawdown");
  }
}

function sortMetricWeightMap(nodes: ResearchOverviewNode[], sortBy: ResearchOverviewSortId) {
  const config = RESEARCH_SORT_METRIC_CONFIG[sortBy] ?? RESEARCH_SORT_METRIC_CONFIG.market_cap_desc;
  const rawValues = nodes.map((node) => {
    const value = getResearchOverviewSortValue(node, sortBy);
    return value == null ? null : config.weightTransform ? config.weightTransform(value) : value;
  });
  const validValues = rawValues.filter((value): value is number => value != null && Number.isFinite(value));
  if (!validValues.length) {
    return nodes.map((node) => (Number.isFinite(node.size) && node.size > 0 ? node.size : 1));
  }
  const allEqual = validValues.every((value) => value === validValues[0]);
  if (allEqual) {
    return nodes.map((_, index) => (rawValues[index] == null ? 0 : 1));
  }
  if (config.direction === "asc") {
    const maxValue = Math.max(...validValues);
    return rawValues.map((value) => (value == null ? 0 : Math.max(maxValue - value, 0) + 1));
  }
  const minValue = Math.min(...validValues);
  const shift = minValue <= 0 ? Math.abs(minValue) + 1 : 0;
  return rawValues.map((value) => (value == null ? 0 : value + shift));
}

function sumWeights(weights: number[]) {
  return weights.reduce((sum, weight) => sum + Math.max(weight, 0), 0);
}

function chooseSplitIndex(weights: number[]) {
  const total = sumWeights(weights);
  if (weights.length <= 1 || total <= 0) {
    return 1;
  }
  let running = 0;
  let bestIndex = 1;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < weights.length - 1; index += 1) {
    running += Math.max(weights[index], 0);
    const distance = Math.abs(total / 2 - running);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index + 1;
    }
  }
  return bestIndex;
}

function layoutWeightedRects(weights: number[], rect: TreemapRect): TreemapRect[] {
  if (!weights.length) {
    return [];
  }
  if (weights.length === 1) {
    return [rect];
  }

  const total = sumWeights(weights);
  if (total <= 0) {
    const equalShare = rect.width / weights.length;
    return weights.map((_, index) => ({
      x: rect.x + equalShare * index,
      y: rect.y,
      width: equalShare,
      height: rect.height
    }));
  }

  const splitIndex = chooseSplitIndex(weights);
  const firstWeights = weights.slice(0, splitIndex);
  const secondWeights = weights.slice(splitIndex);
  const ratio = sumWeights(firstWeights) / total;

  if (rect.width >= rect.height) {
    const firstWidth = rect.width * ratio;
    return [
      ...layoutWeightedRects(firstWeights, { x: rect.x, y: rect.y, width: firstWidth, height: rect.height }),
      ...layoutWeightedRects(secondWeights, {
        x: rect.x + firstWidth,
        y: rect.y,
        width: rect.width - firstWidth,
        height: rect.height
      })
    ];
  }

  const firstHeight = rect.height * ratio;
  return [
    ...layoutWeightedRects(firstWeights, { x: rect.x, y: rect.y, width: rect.width, height: firstHeight }),
    ...layoutWeightedRects(secondWeights, {
      x: rect.x,
      y: rect.y + firstHeight,
      width: rect.width,
      height: rect.height - firstHeight
    })
  ];
}

function sectionLayoutWeights(sectionWeights: number[]) {
  const total = sumWeights(sectionWeights);
  if (total <= 0) {
    return sectionWeights.map(() => 1);
  }
  return sectionWeights.map((weight) => Math.max(weight, 0));
}

export function treemapRectStyle(rect: TreemapRect) {
  return `left:${rect.x}%; top:${rect.y}%; width:${rect.width}%; height:${rect.height}%;`;
}

export function treemapArea(rect: TreemapRect) {
  return rect.width * rect.height;
}

export function treemapDensityClass(rect: TreemapRect, parent?: TreemapRect) {
  const parentScale = parent ? (parent.width * parent.height) / 10000 : 1;
  const area = treemapArea(rect) * parentScale;
  const parentMinSide = Math.min(parent?.width ?? 100, parent?.height ?? 100);
  const minSide = (Math.min(rect.width, rect.height) * parentMinSide) / 100;
  if (area >= 150 && minSide >= 8) {
    return "hero";
  }
  if (area >= 55 && minSide >= 4.5) {
    return "major";
  }
  if (area >= 15 && minSide >= 2.2) {
    return "minor";
  }
  return "micro";
}

export function buildResearchTreemapSections(
  overview: ResearchOverviewResponse | null,
  colorMetric: ResearchOverviewMetricId,
  sortBy: ResearchOverviewSortId = "market_cap_desc"
): ResearchTreemapSection[] {
  const nodes = (overview?.nodes ?? []).filter((node) => node.level === "instrument");
  const weightMap = sortMetricWeightMap(nodes, sortBy);
  const grouped = new Map<string, Array<{ node: ResearchOverviewNode; metricWeight: number; metricValue: number | null }>>();

  nodes.forEach((node, index) => {
    const label = node.group ?? node.sector ?? "Other";
    const rows = grouped.get(label) ?? [];
    rows.push({
      node,
      metricWeight: Math.max(weightMap[index] ?? 0, 0),
      metricValue: getResearchOverviewSortValue(node, sortBy)
    });
    grouped.set(label, rows);
  });

  const sections = Array.from(grouped.entries())
    .map(([label, rows]) => {
      const sortedRows = rows
        .slice()
        .sort(
          (left, right) =>
            right.metricWeight - left.metricWeight ||
            (left.node.sort_rank ?? Number.POSITIVE_INFINITY) - (right.node.sort_rank ?? Number.POSITIVE_INFINITY) ||
            left.node.label.localeCompare(right.node.label)
        );
      return {
        label,
        rows: sortedRows,
        metricWeight: sumWeights(sortedRows.map((row) => row.metricWeight))
      };
    })
    .filter((section) => section.rows.length > 0)
    .sort((left, right) => right.metricWeight - left.metricWeight || left.label.localeCompare(right.label));

  if (!sections.length) {
    return [];
  }

  const sectionRects = layoutWeightedRects(
    sectionLayoutWeights(sections.map((section) => (section.metricWeight > 0 ? section.metricWeight : 1))),
    { x: 0, y: 0, width: 100, height: 100 }
  );

  return sections.map<ResearchTreemapSection>((section, sectionIndex) => {
    const tileRects = layoutWeightedRects(
      section.rows.map((row) => (row.metricWeight > 0 ? row.metricWeight : 1)),
      { x: 0, y: 0, width: 100, height: 100 }
    );
    return {
      label: section.label,
      rect: sectionRects[sectionIndex],
      metricWeight: section.metricWeight,
      nodeCount: section.rows.length,
      tiles: section.rows.map<ResearchTreemapTile>((row, tileIndex) => ({
        node: row.node,
        metricWeight: row.metricWeight,
        metricValue: row.metricValue,
        colorValue: getResearchOverviewMetricValue(row.node, colorMetric),
        rect: tileRects[tileIndex]
      }))
    };
  });
}

export function buildResearchTreemapLayout(
  overview: ResearchOverviewResponse | null,
  metricId: ResearchOverviewMetricId
): ResearchTreemapRect[] {
  const nodes = (overview?.nodes ?? [])
    .filter((node) => node.level === "instrument")
    .map((node) => ({
      node,
      size: Number.isFinite(node.size) && node.size > 0 ? node.size : 1,
      metricValue: getResearchOverviewMetricValue(node, metricId)
    }))
    .sort((left, right) => {
      const groupCompare = String(left.node.group ?? "").localeCompare(String(right.node.group ?? ""));
      if (groupCompare !== 0) {
        return groupCompare;
      }
      return right.size - left.size || left.node.label.localeCompare(right.node.label);
    });

  const rects: ResearchTreemapRect[] = [];
  layoutTreemapItems(nodes, 0, 0, 100, 100, rects);
  return rects;
}

function layoutTreemapItems(
  items: Array<{ node: ResearchOverviewNode; size: number; metricValue: number | null }>,
  x: number,
  y: number,
  width: number,
  height: number,
  rects: ResearchTreemapRect[]
) {
  if (!items.length || width <= 0 || height <= 0) {
    return;
  }

  if (items.length === 1) {
    const item = items[0];
    rects.push({
      node: item.node,
      x,
      y,
      width,
      height,
      size: item.size,
      metricValue: item.metricValue
    });
    return;
  }

  const total = items.reduce((sum, item) => sum + item.size, 0);
  if (total <= 0) {
    return;
  }

  const splitIndex = findBalancedTreemapSplit(items, total);
  const leftItems = items.slice(0, splitIndex);
  const rightItems = items.slice(splitIndex);
  const leftTotal = leftItems.reduce((sum, item) => sum + item.size, 0);
  const leftRatio = leftTotal / total;

  if (width >= height) {
    const leftWidth = width * leftRatio;
    layoutTreemapItems(leftItems, x, y, leftWidth, height, rects);
    layoutTreemapItems(rightItems, x + leftWidth, y, width - leftWidth, height, rects);
  } else {
    const topHeight = height * leftRatio;
    layoutTreemapItems(leftItems, x, y, width, topHeight, rects);
    layoutTreemapItems(rightItems, x, y + topHeight, width, height - topHeight, rects);
  }
}

function findBalancedTreemapSplit(
  items: Array<{ node: ResearchOverviewNode; size: number; metricValue: number | null }>,
  total: number
) {
  let bestIndex = 1;
  let bestDistance = Number.POSITIVE_INFINITY;
  let running = 0;
  for (let index = 0; index < items.length - 1; index += 1) {
    running += items[index].size;
    const distance = Math.abs(total / 2 - running);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index + 1;
    }
  }
  return bestIndex;
}
