// Attach to idea (Workstream 12, I4c): pure builders for what Strategy Lab and
// Risk hand to an idea. Each target says what it attaches and how; the shared
// AttachToIdea picker only chooses the idea. The backend recomputes every
// attach (a snapshot or a signal), so nothing here sends figures as truth.

import type { IdeaAttachedBook, IdeaSignalPayload, StrategyLabCompositionResult, StrategyLabResult } from "./api/types";
import { parseResearchCsvText } from "./view-models/research";

export interface IdeaAttachTarget {
  /** "Backtest snapshot", "Risk snapshot", "Signal". */
  kindLabel: string;
  /** The result's name, shown in the picker. */
  label: string;
  /** One sentence: what the idea will receive. */
  summary: string;
  /** Runs the attach for ``ideaId``; resolves to null on success or the reason it failed. */
  attach: (ideaId: string) => Promise<string | null>;
}

export type AttachRequest =
  | { kind: "test" | "risk"; book: IdeaAttachedBook }
  | { kind: "signal"; payload: IdeaSignalPayload };

export type AttachRunner = (ideaId: string, request: AttachRequest) => Promise<string | null>;

const PRICEABLE = new Set(["equity", "etf", "crypto"]);

/** A composer result's legs as an attachable book, or why it cannot be one. */
export function compositionBook(
  result: StrategyLabCompositionResult | null | undefined,
  source: IdeaAttachedBook["source"]
): { book: IdeaAttachedBook | null; reason: string } {
  const inputs = result?.portfolio_inputs;
  if (!result || !inputs?.legs?.length) return { book: null, reason: "Compose a portfolio first." };
  const blocked = inputs.legs.filter((leg) => !PRICEABLE.has(String(leg.asset_class)) || !String(leg.identifier ?? "").trim());
  if (blocked.length) {
    const names = blocked.map((leg) => leg.label || leg.identifier || leg.asset_class).slice(0, 3).join(", ");
    return { book: null, reason: `Ideas prices equity, ETF and crypto legs from provider closes; ${names} cannot be attached.` };
  }
  if (inputs.legs.every((leg) => !leg.weight)) return { book: null, reason: "The book holds no exposure." };
  return {
    book: {
      source,
      label: (inputs.name || result.name || "Strategy Lab book").slice(0, 160),
      benchmark: inputs.benchmark_symbol ?? null,
      lookback_days: inputs.lookback_days ?? null,
      legs: inputs.legs.map((leg) => ({
        entity_type: String(leg.asset_class) as "equity" | "etf" | "crypto",
        symbol: String(leg.identifier).trim(),
        weight: Number(leg.weight),
        label: leg.label || null,
      })),
    },
    reason: "",
  };
}

/** A Script-derived Strategy Lab result as a signal attach (the run is read again; nothing runs). */
export function scriptSignalPayload(result: StrategyLabResult | null | undefined): IdeaSignalPayload | null {
  const provenance = (result?.analytical_provenance ?? null) as Record<string, unknown> | null;
  const runId = provenance ? String(provenance.run_id ?? "").trim() : "";
  if (!provenance || !runId) return null;
  const weightBook = provenance.target === "weight_book";
  return {
    source: "script",
    output_kind: weightBook ? "weights" : "returns",
    run_id: runId,
    result_id: weightBook ? null : String(provenance.result_id ?? "") || null,
    label: result?.name ?? null,
  };
}

/** An imported CSV analysis as a returns signal: validation only, read with the same import rules. */
export function importedReturnsPayload(
  result: StrategyLabResult | null | undefined,
  csvText: string,
  dateColumn: string,
  valueColumn: string
): IdeaSignalPayload | null {
  if (!result || result.source_provider !== "uploaded_csv") return null;
  const parsed = parseResearchCsvText(csvText);
  if (!parsed.rows.length || !parsed.columns.includes(dateColumn) || !parsed.columns.includes(valueColumn)) return null;
  return {
    source: "import",
    output_kind: "returns",
    label: result.name,
    rows: parsed.rows.map((row) => ({ [dateColumn]: String(row[dateColumn] ?? ""), [valueColumn]: String(row[valueColumn] ?? "") })),
    date_column: dateColumn,
    value_column: valueColumn,
    value_kind: result.value_kind === "level" ? "level" : "return",
  };
}

export interface StrategyLabAttachInput {
  composition: StrategyLabCompositionResult | null;
  result: StrategyLabResult | null;
  csvText: string;
  dateColumn: string;
  valueColumn: string;
}

/** What "Attach to idea" does on Strategy Lab's result panel, or why it is unavailable. */
export function strategyLabAttachTarget(input: StrategyLabAttachInput, run: AttachRunner): { target: IdeaAttachTarget | null; reason: string } {
  if (input.composition?.portfolio_inputs) {
    const { book, reason } = compositionBook(input.composition, "strategy_lab");
    if (!book) return { target: null, reason };
    return {
      target: {
        kindLabel: "Backtest snapshot",
        label: book.label,
        summary: "Gamma backtests these legs again and keeps the snapshot in the idea, in-sample with no costs; it counts as a trial.",
        attach: (ideaId) => run(ideaId, { kind: "test", book }),
      },
      reason: "",
    };
  }
  const script = scriptSignalPayload(input.result);
  if (script) {
    return {
      target: {
        kindLabel: "Signal",
        label: input.result?.name ?? "Script run",
        summary:
          script.output_kind === "weights"
            ? "The run's latest weights become the idea's signal and drive its tracking; Gamma reads the retained run and does not rerun it."
            : "The run's return stream becomes the idea's signal for validation only; it does not drive tracking.",
        attach: (ideaId) => run(ideaId, { kind: "signal", payload: script }),
      },
      reason: "",
    };
  }
  const imported = importedReturnsPayload(input.result, input.csvText, input.dateColumn, input.valueColumn);
  if (imported) {
    return {
      target: {
        kindLabel: "Signal",
        label: input.result?.name ?? "Imported returns",
        summary: "The imported returns become the idea's signal for validation only, read with the same import rules; they do not drive tracking.",
        attach: (ideaId) => run(ideaId, { kind: "signal", payload: imported }),
      },
      reason: "",
    };
  }
  return { target: null, reason: input.result ? "This result has no source Ideas can attach again." : "Analyze or compose a strategy first." };
}

/** What "Attach to idea" does on Risk when it shows a Strategy Lab research book. */
export function riskAttachTarget(composition: StrategyLabCompositionResult | null | undefined, run: AttachRunner): { target: IdeaAttachTarget | null; reason: string } {
  const { book, reason } = compositionBook(composition, "risk_tab");
  if (!book) return { target: null, reason: composition ? reason : "Open a Strategy Lab research book in Risk first." };
  return {
    target: {
      kindLabel: "Risk snapshot",
      label: book.label,
      summary: "Gamma runs Risk on this book again (95% one-day VaR, expected shortfall, stress replay) and keeps the snapshot in the idea.",
      attach: (ideaId) => run(ideaId, { kind: "risk", book }),
    },
    reason: "",
  };
}
