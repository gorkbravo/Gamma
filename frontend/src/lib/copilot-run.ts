import type { CopilotRunEvent } from "./api/types";

export type CopilotRunPhase = "pending" | "streaming" | "completed" | "failed" | "cancelled";

export interface CopilotRunToolNote {
  toolName: string;
  state: "running" | "done";
  summary: string | null;
  sourceIds: string[];
}

export interface CopilotRunState {
  runId: string;
  phase: CopilotRunPhase;
  domain: string | null;
  provider: string | null;
  model: string | null;
  /** Raw streamed text; provisional until the schema-valid final result lands. */
  provisionalText: string;
  toolNotes: CopilotRunToolNote[];
  warnings: string[];
  usage: Record<string, number> | null;
  lastSequence: number;
  terminalEvent: "completed" | "failed" | "cancelled" | null;
  /** Refusal message, incomplete reason, or failure message when present. */
  statusDetail: string | null;
  /** Wire-shape final result from the terminal event; normalize before use. */
  rawResult: unknown | null;
}

const TERMINAL_EVENTS = new Set(["completed", "failed", "cancelled"]);

export function createCopilotRunState(runId: string): CopilotRunState {
  return {
    runId,
    phase: "pending",
    domain: null,
    provider: null,
    model: null,
    provisionalText: "",
    toolNotes: [],
    warnings: [],
    usage: null,
    lastSequence: -1,
    terminalEvent: null,
    statusDetail: null,
    rawResult: null
  };
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Fold one run event into the run state.
 *
 * Enforces the run contract on the client side: events for other runs are
 * ignored, sequence ids must be strictly increasing (duplicates and stale
 * replays are dropped), and the first terminal event wins — anything after it
 * is a no-op so finalization stays idempotent.
 */
export function reduceCopilotRunEvent(state: CopilotRunState, event: CopilotRunEvent): CopilotRunState {
  if (event.run_id !== state.runId) {
    return state;
  }
  if (typeof event.sequence !== "number" || event.sequence <= state.lastSequence) {
    return state;
  }
  if (state.terminalEvent != null) {
    return state;
  }

  const next: CopilotRunState = { ...state, lastSequence: event.sequence };
  const data = event.data ?? {};

  switch (event.event) {
    case "run.created":
      next.phase = "streaming";
      next.domain = asString(data.domain);
      next.provider = asString(data.provider);
      next.model = asString(data.model);
      return next;
    case "text.delta":
      next.phase = "streaming";
      next.provisionalText = state.provisionalText + (asString(data.delta) ?? "");
      return next;
    case "tool.call":
      next.toolNotes = [
        ...state.toolNotes,
        {
          toolName: asString(data.tool_name) ?? "tool",
          state: "running",
          summary: null,
          sourceIds: []
        }
      ];
      return next;
    case "tool.result": {
      const toolName = asString(data.tool_name) ?? "tool";
      const sourceIds = Array.isArray(data.source_ids)
        ? data.source_ids.filter((item): item is string => typeof item === "string")
        : [];
      const summary = asString(data.summary);
      const index = state.toolNotes.findIndex(
        (note) => note.state === "running" && note.toolName === toolName
      );
      if (index >= 0) {
        next.toolNotes = state.toolNotes.map((note, i) =>
          i === index ? { ...note, state: "done" as const, summary, sourceIds } : note
        );
      } else {
        next.toolNotes = [...state.toolNotes, { toolName, state: "done", summary, sourceIds }];
      }
      return next;
    }
    case "warning": {
      const message = asString(data.message);
      next.warnings = message ? [...state.warnings, message] : state.warnings;
      return next;
    }
    case "usage": {
      const usage: Record<string, number> = {};
      for (const [key, value] of Object.entries(data)) {
        if (typeof value === "number" && Number.isFinite(value)) {
          usage[key] = value;
        }
      }
      next.usage = usage;
      return next;
    }
    case "refusal":
      next.statusDetail = asString(data.message) ?? "The model refused the request.";
      return next;
    case "incomplete":
      next.statusDetail = asString(data.reason)
        ? `Response ended early: ${asString(data.reason)}`
        : "Response ended early.";
      return next;
    case "confirmation.needed":
      next.statusDetail = asString(data.message) ?? "Confirmation required before continuing.";
      return next;
    case "completed":
    case "failed":
    case "cancelled":
      next.phase = event.event === "completed" ? "completed" : event.event === "failed" ? "failed" : "cancelled";
      next.terminalEvent = event.event;
      next.rawResult = event.result ?? null;
      if (event.event === "failed") {
        next.statusDetail = asString(data.message) ?? state.statusDetail ?? "Copilot run failed.";
      }
      if (event.event === "cancelled") {
        next.statusDetail =
          asString(data.reason) === "timeout" ? "Copilot run timed out." : "Copilot run cancelled.";
      }
      return next;
    default:
      return next;
  }
}

export function isTerminalCopilotRunEvent(event: CopilotRunEvent): boolean {
  return TERMINAL_EVENTS.has(event.event);
}
