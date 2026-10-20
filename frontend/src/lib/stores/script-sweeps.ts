import { get, writable } from "svelte/store";

import {
  createResearchScriptSweep,
  evaluateResearchScriptSweep,
  listResearchScriptSweeps,
  runResearchScriptSweepPoint,
  walkForwardResearchScriptSweep,
  type ScriptEvaluationTarget,
  type ScriptParameters,
  type ScriptSweep,
  type ScriptSweepEvaluation,
  type ScriptWalkForwardReport,
  type ScriptWalkForwardRequest
} from "../api/research-scripts";
import type { ResearchScriptParameterValue, ResearchScriptRun } from "../api/types";
import { recordResearchScriptRuns } from "./research-script";

export const MAX_SWEEP_POINTS = 24;

export interface ScriptSweepState {
  scriptId: string | null;
  sweeps: ScriptSweep[];
  selectedSweepId: string | null;
  /** Una línea por eje: "nombre = v1, v2, v3". */
  axesDraft: string;
  evaluationTarget: Required<Pick<ScriptEvaluationTarget, "target" | "execution_lag" | "cost_bps">> & { result_id: string };
  walkForwardConfig: Omit<ScriptWalkForwardRequest, "evaluation">;
  evaluation: ScriptSweepEvaluation | null;
  walkForward: ScriptWalkForwardReport | null;
  progress: { done: number; total: number; currentIndex: number | null } | null;
  stopRequested: boolean;
  loading: "list" | "create" | "run" | "evaluate" | "walk" | null;
  error: string;
  notice: string;
}

export const initialScriptSweepState = (): ScriptSweepState => ({
  scriptId: null,
  sweeps: [],
  selectedSweepId: null,
  axesDraft: "lookback = 5, 10, 20\nleverage = 1, 2",
  evaluationTarget: { target: "weight_book", result_id: "", execution_lag: 1, cost_bps: 0 },
  walkForwardConfig: { train_observations: 60, test_observations: 20, window: "rolling", selection_metric: "sharpe" },
  evaluation: null,
  walkForward: null,
  progress: null,
  stopRequested: false,
  loading: null,
  error: "",
  notice: ""
});

export const scriptSweeps = writable<ScriptSweepState>(initialScriptSweepState());

const messageOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

export function resetScriptSweeps() {
  scriptSweeps.set(initialScriptSweepState());
}

/** "5" -> 5, "true" -> true, "null" -> null, '"a"' -> "a"; cualquier otro texto se toma literal. */
export function parseSweepValue(token: string): ResearchScriptParameterValue {
  const text = token.trim();
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || ["string", "number", "boolean"].includes(typeof parsed)) {
      return parsed as ResearchScriptParameterValue;
    }
  } catch {
    // Texto sin comillas: se conserva como cadena exacta.
  }
  return text;
}

export type ParsedSweepAxes =
  | { ok: true; axes: Array<{ name: string; values: ResearchScriptParameterValue[] }>; points: number }
  | { ok: false; error: string };

export function parseSweepAxes(text: string): ParsedSweepAxes {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return { ok: false, error: "Define at least one axis, for example: lookback = 5, 10, 20" };
  const axes: Array<{ name: string; values: ResearchScriptParameterValue[] }> = [];
  for (const line of lines) {
    const separator = line.indexOf("=");
    if (separator <= 0) return { ok: false, error: `Use "name = value, value" on each line: ${line}` };
    const name = line.slice(0, separator).trim();
    const values = line.slice(separator + 1).split(",").map((item) => item.trim()).filter(Boolean).map(parseSweepValue);
    if (!/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(name)) return { ok: false, error: `Invalid parameter name: ${name}` };
    if (values.length < 2) return { ok: false, error: `Axis ${name} needs at least two values.` };
    axes.push({ name, values });
  }
  const points = axes.reduce((total, axis) => total * axis.values.length, 1);
  if (points > MAX_SWEEP_POINTS) return { ok: false, error: `${points} points exceed the ${MAX_SWEEP_POINTS}-point limit.` };
  return { ok: true, axes, points };
}

export function selectedSweep(state: ScriptSweepState): ScriptSweep | null {
  return state.sweeps.find((item) => item.sweep_id === state.selectedSweepId) ?? null;
}

export function updateSweepDraft(patch: Partial<Pick<ScriptSweepState, "axesDraft" | "evaluationTarget" | "walkForwardConfig">>) {
  scriptSweeps.update((state) => ({
    ...state,
    ...patch,
    // Cambiar la evaluación invalida los informes derivados de la anterior.
    ...(patch.evaluationTarget || patch.walkForwardConfig ? { walkForward: null } : {}),
    ...(patch.evaluationTarget ? { evaluation: null } : {}),
    error: "",
    notice: ""
  }));
}

export async function loadScriptSweeps(scriptId: string | null) {
  if (!scriptId) {
    resetScriptSweeps();
    return;
  }
  if (get(scriptSweeps).scriptId === scriptId && get(scriptSweeps).sweeps.length) return;
  scriptSweeps.update((state) => ({ ...initialScriptSweepState(), axesDraft: state.axesDraft, scriptId, loading: "list" }));
  try {
    const sweeps = await listResearchScriptSweeps(scriptId);
    scriptSweeps.update((state) => state.scriptId !== scriptId ? state : {
      ...state, sweeps, selectedSweepId: sweeps[0]?.sweep_id ?? null, loading: null
    });
  } catch (error) {
    scriptSweeps.update((state) => state.scriptId !== scriptId ? state : { ...state, loading: null, error: messageOf(error) });
  }
}

export function selectScriptSweep(sweepId: string) {
  scriptSweeps.update((state) => ({ ...state, selectedSweepId: sweepId || null, evaluation: null, walkForward: null, error: "", notice: "" }));
}

export async function createScriptSweep(options: {
  scriptId: string; revisionId: string; inputSnapshotId: string; baseParameters: ScriptParameters;
}) {
  const parsed = parseSweepAxes(get(scriptSweeps).axesDraft);
  if (!parsed.ok) {
    scriptSweeps.update((state) => ({ ...state, error: parsed.error }));
    return null;
  }
  // Los ejes sustituyen a los parámetros base del mismo nombre; el servidor no admite duplicados.
  const base = Object.fromEntries(Object.entries(options.baseParameters).filter(([name]) => !parsed.axes.some((axis) => axis.name === name)));
  scriptSweeps.update((state) => ({ ...state, loading: "create", error: "", notice: "" }));
  try {
    const sweep = await createResearchScriptSweep(options.scriptId, {
      revision_id: options.revisionId, input_snapshot_id: options.inputSnapshotId, base_parameters: base, axes: parsed.axes
    });
    scriptSweeps.update((state) => ({
      ...state, scriptId: options.scriptId, sweeps: [sweep, ...state.sweeps], selectedSweepId: sweep.sweep_id,
      evaluation: null, walkForward: null, loading: null,
      notice: `Sweep created with ${sweep.points.length} points over one revision and one input bundle.`
    }));
    return sweep;
  } catch (error) {
    scriptSweeps.update((state) => ({ ...state, loading: null, error: messageOf(error) }));
    return null;
  }
}

/** Puntos cuya última ejecución no terminó: son los que "Run remaining" vuelve a lanzar. */
export function pendingSweepPoints(sweep: ScriptSweep, runs: ResearchScriptRun[]): number[] {
  const latest = new Map<number, ResearchScriptRun>();
  for (const run of runs) {
    if (run.sweep_id === sweep.sweep_id && typeof run.sweep_point_index === "number" && !latest.has(run.sweep_point_index)) {
      latest.set(run.sweep_point_index, run);
    }
  }
  return sweep.points.filter((point) => latest.get(point.index)?.status !== "completed").map((point) => point.index);
}

export async function runSweepPoints(indexes: number[]) {
  const sweep = selectedSweep(get(scriptSweeps));
  if (!sweep || !indexes.length) return;
  scriptSweeps.update((state) => ({
    ...state, loading: "run", stopRequested: false, error: "", notice: "",
    progress: { done: 0, total: indexes.length, currentIndex: indexes[0] }, evaluation: null, walkForward: null
  }));
  const completed: ResearchScriptRun[] = [];
  try {
    for (const [position, index] of indexes.entries()) {
      if (get(scriptSweeps).stopRequested) break;
      scriptSweeps.update((state) => ({ ...state, progress: { done: position, total: indexes.length, currentIndex: index } }));
      const run = await runResearchScriptSweepPoint(sweep.sweep_id, index);
      completed.push(run);
      recordResearchScriptRuns([run]);
    }
  } catch (error) {
    scriptSweeps.update((state) => ({ ...state, error: messageOf(error) }));
  }
  const stopped = get(scriptSweeps).stopRequested && completed.length < indexes.length;
  scriptSweeps.update((state) => ({
    ...state, loading: null, stopRequested: false, progress: null,
    notice: stopped
      ? `Stopped after ${completed.length} of ${indexes.length} points; the remaining points were not run.`
      : state.error ? state.notice : `${completed.length} point run${completed.length === 1 ? "" : "s"} retained.`
  }));
  if (completed.length) await evaluateSelectedSweep();
}

export function stopSweepRun() {
  scriptSweeps.update((state) => (state.loading === "run" ? { ...state, stopRequested: true } : state));
}

function evaluationPayload(state: ScriptSweepState): ScriptEvaluationTarget {
  const target = state.evaluationTarget;
  return target.target === "weight_book"
    ? { target: "weight_book", execution_lag: target.execution_lag, cost_bps: target.cost_bps }
    : { target: "returns_result", result_id: target.result_id.trim() };
}

export async function evaluateSelectedSweep() {
  const state = get(scriptSweeps);
  const sweep = selectedSweep(state);
  if (!sweep) return null;
  if (state.evaluationTarget.target === "returns_result" && !state.evaluationTarget.result_id.trim()) {
    scriptSweeps.update((current) => ({ ...current, error: "Enter the result_id of the returns result to compare." }));
    return null;
  }
  scriptSweeps.update((current) => ({ ...current, loading: "evaluate", error: "" }));
  try {
    const evaluation = await evaluateResearchScriptSweep(sweep.sweep_id, evaluationPayload(state));
    scriptSweeps.update((current) => current.selectedSweepId !== sweep.sweep_id ? { ...current, loading: null } : {
      ...current, evaluation, loading: null
    });
    return evaluation;
  } catch (error) {
    scriptSweeps.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export async function runSelectedWalkForward() {
  const state = get(scriptSweeps);
  const sweep = selectedSweep(state);
  if (!sweep) return null;
  scriptSweeps.update((current) => ({ ...current, loading: "walk", error: "", walkForward: null }));
  try {
    const walkForward = await walkForwardResearchScriptSweep(sweep.sweep_id, {
      ...state.walkForwardConfig, evaluation: evaluationPayload(state)
    });
    scriptSweeps.update((current) => current.selectedSweepId !== sweep.sweep_id ? { ...current, loading: null } : {
      ...current, walkForward, loading: null
    });
    return walkForward;
  } catch (error) {
    scriptSweeps.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}
