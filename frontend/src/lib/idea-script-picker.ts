// Script run picker for the idea signal form (Workstream 12, I4c). Reads the
// existing read-only Strategy Lab listings; it never starts a run.

import { getJson } from "./api/client";

export interface PickerScript {
  script_id: string;
  title: string;
  status: string;
}

export interface PickerRun {
  run_id: string;
  revision_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  parameters_sha256: string | null;
  sweep_id: string | null;
  sweep_point_index: number | null;
  runtime_kind: string;
}

export interface PickerSweep {
  sweep_id: string;
  created_at: string;
  points: Array<{ index: number }>;
  axes: Array<{ name: string; values: unknown[] }>;
}

const BASE = "/research/strategy-lab";

export async function loadPickerScripts(): Promise<PickerScript[]> {
  const response = await getJson<{ items: PickerScript[] }>(`${BASE}/scripts`);
  return response.items ?? [];
}

export async function loadPickerRuns(scriptId: string): Promise<PickerRun[]> {
  const response = await getJson<{ items: PickerRun[] }>(`${BASE}/scripts/${encodeURIComponent(scriptId)}/runs`);
  return response.items ?? [];
}

export async function loadPickerSweeps(scriptId: string): Promise<PickerSweep[]> {
  return (await getJson<PickerSweep[]>(`${BASE}/scripts/${encodeURIComponent(scriptId)}/sweeps`)) ?? [];
}

/** "2026-11-10 14:02 · sweep point 2 · parameters ae8f1836" for a run option. */
export function runOptionLabel(run: PickerRun): string {
  const when = (run.completed_at ?? run.started_at ?? "").replace("T", " ").slice(0, 16);
  const parts = [when ? `${when} UTC` : run.run_id.slice(0, 8)];
  if (run.sweep_id && run.sweep_point_index != null) parts.push(`sweep point ${run.sweep_point_index}`);
  if (run.parameters_sha256) parts.push(`parameters ${run.parameters_sha256.slice(0, 8)}`);
  if (run.status !== "completed") parts.push(run.status.replace(/_/g, " "));
  else if (run.runtime_kind === "mock_safe_preview") parts.push("safe preview");
  return parts.join(" · ");
}

/** Only completed runs whose Python executed can become a signal; a safe preview is not a calculation. */
export function runSelectable(run: PickerRun): boolean {
  return run.status === "completed" && run.runtime_kind !== "mock_safe_preview";
}

/** "Sweep 86c63d12 · 6 points · lookback × leverage". */
export function sweepOptionLabel(sweep: PickerSweep): string {
  const axes = sweep.axes.map((axis) => axis.name).join(" × ");
  return `Sweep ${sweep.sweep_id.slice(0, 8)} · ${sweep.points.length} points${axes ? ` · ${axes}` : ""}`;
}
