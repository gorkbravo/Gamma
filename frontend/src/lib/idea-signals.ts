// Signals for ideas (Workstream 12, I4a): pure helpers for the Idea view's
// "Signal and validation" section. A signal is data the user brought (a Script
// run or CSV rows); Gamma never runs a Script from here and nothing is routed.

import type {
  Idea,
  IdeaSignal,
  IdeaSignalInstrument,
  IdeaSignalOutputKind,
  IdeaSignalPayload,
  IdeaTrackingResponse,
  IdeaValidationSnapshot,
} from "./api/types";
import { parseResearchCsvText } from "./view-models/research";

/** The attached signal, if any. */
export function currentSignal(idea: Idea): IdeaSignal | null {
  const signals = idea.signals ?? [];
  const last = signals.at(-1);
  return last && last.current ? last : null;
}

/** "1 trial", "at least 4 trials". */
export function trialsText(count: number | null | undefined, lowerBound = false): string {
  if (count == null || !Number.isFinite(count)) return "Trials not recorded";
  const value = Math.max(0, Math.round(count));
  return `${lowerBound ? "at least " : ""}${value} ${value === 1 ? "trial" : "trials"}`;
}

/** "Trials 3", "Trials ≥ 4": the compact tag shown beside a performance figure. */
export function trialsTag(count: number | null | undefined, lowerBound = false): string {
  if (count == null || !Number.isFinite(count)) return "Trials N/A";
  return `Trials ${lowerBound ? "≥ " : ""}${Math.max(0, Math.round(count))}`;
}

export function signalSourceText(signal: IdeaSignal): string {
  return signal.source === "script" ? "Script" : "Import";
}

export function outputKindText(kind: IdeaSignalOutputKind): string {
  return { positions: "Positions", weights: "Weights", returns: "Returns" }[kind];
}

/** What the weight column means for this signal's book. */
export function weightBasisText(signal: IdeaSignal): string {
  return signal.output_kind === "weights" ? "of NAV" : "of gross";
}

/** "+60.0%" for a signed share. */
export function formatShare(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  const percent = value * 100;
  return `${percent > 0 ? "+" : ""}${percent.toFixed(1)}%`;
}

/** Cash left in a weights book (1 − Σw), or null for a positions book. */
export function cashShare(signal: IdeaSignal): number | null {
  if (signal.output_kind !== "weights") return null;
  return 1 - signal.legs.reduce((total, leg) => total + leg.weight, 0);
}

function text(value: unknown): string {
  return value == null ? "" : String(value);
}

/** The ids that pin the source exactly: script, revision, parameters, run; or the import's hash. */
export function sourceIdRows(signal: IdeaSignal): Array<[string, string]> {
  const ref = signal.source_ref ?? {};
  if (signal.source === "script") {
    const revision = text(ref.revision_number) ? `${text(ref.revision_number)} (${text(ref.revision_status)})` : text(ref.revision_status);
    return [
      ["Script", text(ref.script_title) || text(ref.script_id)],
      ["Revision", revision || "N/A"],
      ["Parameters", text(ref.parameters_sha256).slice(0, 12) || "None"],
      ["Run", text(ref.run_id)],
      ...(ref.sweep_id ? ([["Sweep point", `${text(ref.sweep_id).slice(0, 8)} · ${text(ref.sweep_point_index)}`]] as Array<[string, string]>) : []),
    ];
  }
  const columns = Array.isArray(ref.columns) ? (ref.columns as unknown[]).map(text).join(", ") : "";
  return [
    ["Content", text(ref.content_sha256).slice(0, 12)],
    ["Rows", text(ref.rows)],
    ["Columns", columns || "N/A"],
  ];
}

/** Per-leg cost from the latest tracking segment that holds the leg (the backend's cost model). */
export function legCost(
  tracking: IdeaTrackingResponse | null,
  key: string
): { bp: number | null; source: "leg" | "class" | null; assetClass: string | null } {
  const segments = tracking?.segments ?? [];
  for (let index = segments.length - 1; index >= 0; index -= 1) {
    const leg = segments[index].legs.find((item) => item.key === key);
    if (leg) return { bp: leg.cost_bp, source: leg.cost_source ?? "class", assetClass: leg.asset_class };
  }
  return { bp: null, source: null, assetClass: null };
}

/** "5 bp per unit of turnover", "No costs", "Costs as written by the script". */
export function validationCostText(validation: IdeaValidationSnapshot): string {
  if (validation.costs_included === true) return `Costs ${validation.cost_bps ?? 0} bp per unit of turnover`;
  if (validation.costs_included === false) return "No costs";
  return "Costs as written by the script";
}

/** "Walk-forward · 4 folds · anchored · train 60 / test 30". */
export function validationSplitText(validation: IdeaValidationSnapshot): string {
  return `Walk-forward · ${validation.folds.length} ${validation.folds.length === 1 ? "fold" : "folds"} · ${validation.window} · train ${validation.train_observations} / test ${validation.test_observations}`;
}

export interface SignalImportDraft {
  outputKind: IdeaSignalOutputKind;
  csv: string;
  dateColumn: string;
  valueColumn: string;
  valueKind: "return" | "level";
  label: string;
  instruments: Record<string, IdeaSignalInstrument>;
}

/** Columns of the pasted CSV, the parse warnings, and the instrument columns (all but the date). */
export function importColumns(draft: Pick<SignalImportDraft, "csv" | "dateColumn">): {
  columns: string[];
  instrumentColumns: string[];
  rows: Array<Record<string, string>>;
  warnings: string[];
} {
  if (!draft.csv.trim()) return { columns: [], instrumentColumns: [], rows: [], warnings: [] };
  const parsed = parseResearchCsvText(draft.csv);
  const rows = parsed.rows.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, String(value ?? "")])));
  return {
    columns: parsed.columns,
    instrumentColumns: parsed.columns.filter((column) => column !== draft.dateColumn),
    rows,
    warnings: parsed.warnings,
  };
}

/** The first column whose name looks like a date, else the first column. */
export function guessDateColumn(columns: string[]): string {
  return columns.find((column) => /date|day|time/i.test(column)) ?? columns[0] ?? "";
}

/** The request body for an import, or the reason it cannot be sent yet. */
export function buildImportPayload(draft: SignalImportDraft): { payload: IdeaSignalPayload | null; reason: string } {
  const { columns, instrumentColumns, rows } = importColumns(draft);
  if (!rows.length) return { payload: null, reason: "Paste CSV rows with a header" };
  if (!draft.dateColumn || !columns.includes(draft.dateColumn)) return { payload: null, reason: "Choose the date column" };
  if (draft.outputKind === "returns") {
    if (!draft.valueColumn || !columns.includes(draft.valueColumn)) return { payload: null, reason: "Choose the returns column" };
    return {
      payload: {
        source: "import",
        output_kind: "returns",
        label: draft.label.trim() || null,
        rows,
        date_column: draft.dateColumn,
        value_column: draft.valueColumn,
        value_kind: draft.valueKind,
      },
      reason: "",
    };
  }
  if (!instrumentColumns.length) return { payload: null, reason: "Add one column per instrument" };
  const instruments: Record<string, IdeaSignalInstrument> = {};
  for (const column of instrumentColumns) {
    const mapping = draft.instruments[column];
    const symbol = (mapping?.symbol ?? column).trim();
    if (!symbol) return { payload: null, reason: `Give ${column} a ticker or CoinGecko id` };
    instruments[column] = { symbol, entity_type: mapping?.entity_type ?? "equity" };
  }
  return {
    payload: {
      source: "import",
      output_kind: draft.outputKind,
      label: draft.label.trim() || null,
      rows,
      date_column: draft.dateColumn,
      columns: instrumentColumns,
      instruments,
    },
    reason: "",
  };
}

export interface SignalScriptDraft {
  outputKind: "weights" | "returns";
  runId: string;
  resultId: string;
  label: string;
  /** One instrument per line: "research:asset = SPY etf". */
  instrumentMap: string;
  sweepId: string;
  trainObservations: string;
  testObservations: string;
  window: "anchored" | "rolling";
}

/** "research:asset = SPY etf" lines → the instrument map; invalid lines are reported. */
export function parseInstrumentMap(textValue: string): { instruments: Record<string, IdeaSignalInstrument>; errors: string[] } {
  const instruments: Record<string, IdeaSignalInstrument> = {};
  const errors: string[] = [];
  textValue
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line, index) => {
      const match = /^(.+?)\s*=\s*(\S+)(?:\s+(equity|etf|crypto))?$/i.exec(line);
      if (!match) {
        errors.push(`Line ${index + 1}: use "instrument id = TICKER [equity|etf|crypto]"`);
        return;
      }
      instruments[match[1].trim()] = {
        symbol: match[2],
        entity_type: (match[3]?.toLowerCase() as IdeaSignalInstrument["entity_type"]) ?? "equity",
      };
    });
  return { instruments, errors };
}

/** The request body for a Script run, or the reason it cannot be sent yet. */
export function buildScriptPayload(draft: SignalScriptDraft): { payload: IdeaSignalPayload | null; reason: string } {
  const runId = draft.runId.trim();
  if (!runId) return { payload: null, reason: "Paste the run id from Strategy Lab" };
  const { instruments, errors } = parseInstrumentMap(draft.instrumentMap);
  if (errors.length) return { payload: null, reason: errors[0] };
  let validation: IdeaSignalPayload["validation"] = null;
  if (draft.sweepId.trim()) {
    const train = Number(draft.trainObservations);
    const test = Number(draft.testObservations);
    if (!Number.isInteger(train) || train < 1 || !Number.isInteger(test) || test < 1) {
      return { payload: null, reason: "Give the walk-forward train and test lengths in observations" };
    }
    validation = { sweep_id: draft.sweepId.trim(), train_observations: train, test_observations: test, window: draft.window };
  }
  return {
    payload: {
      source: "script",
      output_kind: draft.outputKind,
      label: draft.label.trim() || null,
      run_id: runId,
      result_id: draft.outputKind === "returns" && draft.resultId.trim() ? draft.resultId.trim() : null,
      instruments,
      validation,
    },
    reason: "",
  };
}
