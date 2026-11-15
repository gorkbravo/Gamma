// Ideas criteria (Workstream 12, checkpoint I2): pure helpers for the criteria
// panel, the Board columns, the notification center and Sitrep "Your ideas".
//
// The backend evaluates; nothing here fetches. ``describeCriterion`` mirrors
// ``describe_criterion`` in src/application/idea_criteria.py for the live
// label preview; the server generates the stored label when the user leaves
// the label untouched, so the two can only differ in a preview.

import type {
  IdeaCriterion,
  IdeaCriterionCadence,
  IdeaCriterionCondition,
  IdeaCriterionKind,
  IdeaCriterionState,
  IdeaCriterionWindow,
  IdeaNotification,
  IdeaObservableDefinition,
  IdeaObservableRef,
} from "./api/types";

export const CRITERION_KINDS: readonly IdeaCriterionKind[] = ["invalidate", "confirm", "review"];
export const CRITERION_KIND_LABELS: Record<IdeaCriterionKind, string> = {
  invalidate: "Invalidate",
  confirm: "Confirm",
  review: "Review",
};

export const CONDITION_LABELS: Record<IdeaCriterionCondition, string> = {
  above: "Above",
  below: "Below",
  crosses_above: "Crosses above",
  crosses_below: "Crosses below",
  change_over_window: "Change over window",
  date_reached: "Date reached",
  event_occurs: "Resolves Yes",
};

export const CADENCE_LABELS: Record<IdeaCriterionCadence, string> = {
  on_open: "On open",
  daily_close: "Daily close",
  intraday: "Intraday",
};

export const CRITERION_STATE_LABELS: Record<IdeaCriterionState, string> = {
  pending: "Pending",
  holding: "Holding",
  triggered: "Triggered",
  unavailable: "Unavailable",
  stale: "Stale",
};

export const CRITERION_WINDOWS: ReadonlyArray<{ id: IdeaCriterionWindow; label: string }> = [
  { id: "1d", label: "1 day" },
  { id: "5d", label: "5 days" },
  { id: "1m", label: "1 month" },
  { id: "3m", label: "3 months" },
  { id: "6m", label: "6 months" },
  { id: "1y", label: "1 year" },
];
const WINDOW_LABELS = Object.fromEntries(CRITERION_WINDOWS.map((item) => [item.id, item.label])) as Record<string, string>;

/** Board and notification order: what needs attention first. */
export const CRITERION_STATE_ORDER: readonly IdeaCriterionState[] = ["triggered", "unavailable", "stale", "holding", "pending"];

export const THRESHOLD_CONDITIONS: readonly IdeaCriterionCondition[] = [
  "above",
  "below",
  "crosses_above",
  "crosses_below",
  "change_over_window",
];

/**
 * Tag tone for a state. A trigger is coloured by what it means for the thesis:
 * an invalidation is negative, a confirmation positive, a review a caution.
 * Unavailable and stale are cautions; holding and pending stay neutral.
 */
export function criterionStateTone(state: IdeaCriterionState, kind: IdeaCriterionKind): "" | "positive" | "negative" | "warning" {
  if (state === "triggered") return kind === "invalidate" ? "negative" : kind === "confirm" ? "positive" : "warning";
  if (state === "unavailable" || state === "stale") return "warning";
  return "";
}

export function needsThreshold(condition: IdeaCriterionCondition): boolean {
  return THRESHOLD_CONDITIONS.includes(condition);
}

/** Display unit of an observable reference; macro series carry their own unit per series. */
export function observableValueUnit(definition: IdeaObservableDefinition | null, ref: Pick<IdeaObservableRef, "params">): string {
  if (!definition) return "number";
  if (definition.observable_id === "macro_series") {
    const option = definition.params[0]?.options.find((item) => item.value === ref.params.series_id);
    return option?.unit ?? "number";
  }
  return definition.value_unit;
}

export function observableChangeUnit(definition: IdeaObservableDefinition | null, ref: Pick<IdeaObservableRef, "params">): "percent" | "points" {
  if (!definition) return "percent";
  if (definition.observable_id === "macro_series") {
    const unit = observableValueUnit(definition, ref);
    return unit === "percent" || unit === "bp" ? "points" : "percent";
  }
  return definition.change_unit;
}

function fixed(value: number, digits: number): string {
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function significant(value: number, digits: number): string {
  return Number(value.toPrecision(digits)).toLocaleString("en-US", { maximumFractionDigits: 12 });
}

/** Same rules as ObservableRegistry.format_value on the server. */
export function formatObservableValue(unit: string, value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  switch (unit) {
    case "percent":
      return `${fixed(value, 2)}%`;
    case "probability":
      return `${fixed(value, 1)}%`;
    case "bp":
      return `${fixed(value, 0)} bp`;
    case "points":
      return `${fixed(value, 2)} pts`;
    case "price":
      return Math.abs(value) >= 1 ? fixed(value, 2) : fixed(value, 4);
    case "fx":
      return fixed(value, 4);
    case "usd":
      return Math.abs(value) >= 1 ? `$${fixed(value, 2)}` : `$${fixed(value, 6)}`;
    default:
      return Math.abs(value) < 1 ? significant(value, 4) : fixed(value, 2);
  }
}

function plainNumber(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString("en-US");
  if (Math.abs(value) >= 100) return fixed(value, 2);
  return Math.abs(value) < 1 ? significant(value, 4) : fixed(value, 2);
}

/** Plain-language label from the rule; mirrors describe_criterion on the server. */
export function describeCriterion(options: {
  observableLabel: string;
  condition: IdeaCriterionCondition;
  threshold: number | null;
  window: IdeaCriterionWindow | null;
  changeUnit?: "percent" | "points";
  formatThreshold?: (value: number) => string;
}): string {
  const subject = options.observableLabel.trim() || "Observable";
  const threshold = options.threshold;
  const shown = threshold == null ? "N/A" : options.formatThreshold ? options.formatThreshold(threshold) : plainNumber(threshold);
  switch (options.condition) {
    case "above":
    case "below":
    case "crosses_above":
    case "crosses_below":
      return `${subject} ${CONDITION_LABELS[options.condition].toLowerCase()} ${shown}`;
    case "change_over_window": {
      const magnitude = Math.abs(threshold ?? 0);
      const verb = (threshold ?? 0) > 0 ? "rises" : "falls";
      const unit = (options.changeUnit ?? "percent") === "percent" ? "%" : " pts";
      return `${subject} ${verb} ${plainNumber(magnitude)}${unit} over ${WINDOW_LABELS[options.window ?? ""] ?? options.window ?? ""}`;
    }
    case "date_reached":
      return `${subject} reached`;
    case "event_occurs":
      return `${subject} resolves Yes`;
  }
}

/** The label the server would give an observable reference when the form leaves it blank. */
export function defaultObservableLabel(definition: IdeaObservableDefinition | null, params: Record<string, string>): string {
  if (!definition) return "";
  const id = definition.observable_id;
  const option = (name: string) => definition.params.find((param) => param.name === name)?.options.find((item) => item.value === params[name]);
  if (id === "equity_close") return params.symbol ? `${params.symbol.trim().toUpperCase()} close` : "";
  if (id === "option_atm_iv") return params.symbol ? `${params.symbol.trim().toUpperCase()} ATM IV` : "";
  if (id === "option_skew") return params.symbol ? `${params.symbol.trim().toUpperCase()} skew` : "";
  if (id === "macro_series") return option("series_id")?.label.replace(" (needs TWS)", "") ?? "";
  if (id === "prediction_probability") return params.market_id ? `${params.market_id.trim()} probability` : "";
  if (id === "crypto_price") return params.token_id ? `${params.token_id.trim().toLowerCase()} price` : "";
  if (id === "commodity_price") return option("instrument_id") ? `${option("instrument_id")!.label} price` : "";
  if (id === "commodity_spread") return option("spread_id")?.label ?? "";
  if (id === "calendar_date") return params.date ?? "";
  if (id === "macro_event") return params.title || params.event_id || "";
  if (id === "script_signal") {
    const title = option("script_id")?.label;
    return title ? `${title}${params.result_id ? ` · ${params.result_id}` : ""}` : "";
  }
  return definition.label;
}

export function paramsComplete(definition: IdeaObservableDefinition | null, params: Record<string, string>): boolean {
  if (!definition) return false;
  return definition.params.every((param) => !param.required || Boolean(params[param.name]?.trim()));
}

/** Observables for the picker: the registry's order (no-TWS first), grouped. */
export function groupObservables(definitions: IdeaObservableDefinition[]): Array<{ group: string; items: IdeaObservableDefinition[] }> {
  const groups: Array<{ group: string; items: IdeaObservableDefinition[] }> = [];
  for (const definition of [...definitions].sort((left, right) => left.order - right.order)) {
    const existing = groups.find((item) => item.group === definition.group);
    if (existing) existing.items.push(definition);
    else groups.push({ group: definition.group, items: [definition] });
  }
  return groups;
}

/** A session date (``YYYY-MM-DDT00:00:00``) or an instant, shortened to its calendar date. */
export function shortDate(value: string | null | undefined): string {
  if (!value) return "N/A";
  return value.slice(0, 10);
}

/** What the "Now" cell says: the latest value and its date, or why there is none. */
export function criterionNowText(criterion: IdeaCriterion): { value: string; detail: string } {
  const evaluation = criterion.last_evaluation;
  if (!evaluation) return { value: "N/A", detail: "Not evaluated yet" };
  const value = evaluation.value_display ?? (evaluation.state === "unavailable" ? "N/A" : "N/A");
  const detail = evaluation.as_of ? shortDate(evaluation.as_of) : "";
  return { value, detail };
}

/** Board column: non-zero state counts in attention order. */
export function criteriaSummary(counts: Partial<Record<IdeaCriterionState, number>> | undefined): Array<{ state: IdeaCriterionState; count: number }> {
  return CRITERION_STATE_ORDER.map((state) => ({ state, count: counts?.[state] ?? 0 })).filter((item) => item.count > 0);
}

/** Whole days from ``today`` to ``reviewDate`` (both calendar dates); negative when overdue. */
export function daysToReview(reviewDate: string | null | undefined, today: Date = new Date()): number | null {
  if (!reviewDate) return null;
  const [year, month, day] = reviewDate.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return null;
  const target = Date.UTC(year, month - 1, day);
  const start = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.round((target - start) / 86_400_000);
}

export function daysToReviewText(days: number | null): string {
  if (days == null) return "N/A";
  if (days === 0) return "Today";
  if (days > 0) return `${days}d`;
  return `${-days}d overdue`;
}

/** One-line description of a notification for the center and Sitrep. */
export function notificationDetail(item: IdeaNotification): string {
  if (item.kind === "review_due") {
    if (item.days_overdue == null || item.days_overdue <= 0) return "Review due today";
    return `Review due ${item.review_date} · ${item.days_overdue}d overdue`;
  }
  const parts = [item.value_display ?? "N/A"];
  if (item.first_met_at) parts.push(`first met ${shortDate(item.first_met_at)}`);
  return parts.join(" · ");
}

export function notificationTone(item: IdeaNotification): "" | "positive" | "negative" | "warning" {
  if (item.kind === "review_due") return "warning";
  return criterionStateTone("triggered", item.criterion_kind ?? "review");
}
