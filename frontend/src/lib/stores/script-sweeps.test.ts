import { get } from "svelte/store";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ScriptSweep } from "../api/research-scripts";
import type { ResearchScriptRun } from "../api/types";
import { researchScriptWorkspace, resetResearchScriptWorkspace } from "./research-script";
import {
  createScriptSweep,
  parseSweepAxes,
  parseSweepValue,
  pendingSweepPoints,
  resetScriptSweeps,
  runSweepPoints,
  scriptSweeps,
  stopSweepRun,
  updateSweepDraft
} from "./script-sweeps";

const sweep = (): ScriptSweep => ({
  sweep_id: "sweep-1", script_id: "script-1", revision_id: "revision-1", source_sha256: "a".repeat(64),
  input_snapshot_id: "snapshot-1", input_manifest_sha256: "b".repeat(64), base_parameters: { leverage: 1 },
  axes: [{ name: "lookback", values: [5, 10, 20] }],
  points: [5, 10, 20].map((lookback, index) => ({ index, parameters: { leverage: 1, lookback }, parameters_sha256: String(index).repeat(64) })),
  definition_sha256: "d".repeat(64), created_at: "2026-10-20T12:00:00", created_by: "user",
  origin: "research_script_service.create_sweep", transformation_note: null, contract_version: "research-script-sweep.v1"
});

const run = (index: number, status: ResearchScriptRun["status"] = "completed", runId = `run-${index}`): ResearchScriptRun => ({
  run_id: runId, script_id: "script-1", revision_id: "revision-1", source_sha256: "a".repeat(64),
  input_snapshot_id: "snapshot-1", input_manifest_sha256: "b".repeat(64), input_file_count: 0, input_total_bytes: 0,
  runtime_provider: "fixture", runtime_kind: "fixture", provider_container_id: null, provider_response_id: null,
  status, started_at: `2026-10-20T12:0${index}:00`, completed_at: `2026-10-20T12:0${index}:00`, outputs: [], source_refs: [],
  warnings: [], usage: {}, limits: {}, source_provider: "fixture", origin: "test", transformation_note: null,
  contract_version: "research-script-run.v1", parameters: { lookback: 5 }, parameters_sha256: String(index).repeat(64),
  sweep_id: "sweep-1", sweep_point_index: index
});

const jsonResponse = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { "Content-Type": "application/json" }
});

describe("script sweep store", () => {
  beforeEach(() => { resetScriptSweeps(); resetResearchScriptWorkspace(); });
  afterEach(() => vi.unstubAllGlobals());

  it("parses one axis per line with JSON scalars and plain text", () => {
    expect(parseSweepValue("5")).toBe(5);
    expect(parseSweepValue("true")).toBe(true);
    expect(parseSweepValue("null")).toBeNull();
    expect(parseSweepValue("\"spy\"")).toBe("spy");
    expect(parseSweepValue("spy")).toBe("spy");
    expect(parseSweepAxes("lookback = 5, 10, 20\nmode = fast, slow")).toEqual({
      ok: true, points: 6, axes: [{ name: "lookback", values: [5, 10, 20] }, { name: "mode", values: ["fast", "slow"] }]
    });
    expect(parseSweepAxes("lookback = 5")).toMatchObject({ ok: false, error: expect.stringContaining("two values") });
    expect(parseSweepAxes("1bad = 1, 2")).toMatchObject({ ok: false, error: expect.stringContaining("Invalid") });
    expect(parseSweepAxes("a = 1,2,3,4,5\nb = 1,2,3,4,5")).toMatchObject({ ok: false, error: expect.stringContaining("24-point") });
  });

  it("treats a point as pending until its latest run completed", () => {
    const runs = [run(0, "failed", "run-0b"), run(0), run(1), run(2, "timed_out")];
    expect(pendingSweepPoints(sweep(), runs)).toEqual([0, 2]);
    expect(pendingSweepPoints(sweep(), [])).toEqual([0, 1, 2]);
  });

  it("sends axes separately from fixed parameters and never duplicates an axis in the base", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(sweep(), 201));
    vi.stubGlobal("fetch", fetchMock);
    updateSweepDraft({ axesDraft: "lookback = 5, 10, 20" });
    await createScriptSweep({ scriptId: "script-1", revisionId: "revision-1", inputSnapshotId: "snapshot-1",
      baseParameters: { lookback: 7, leverage: 1 } });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({ revision_id: "revision-1", input_snapshot_id: "snapshot-1", base_parameters: { leverage: 1 },
      axes: [{ name: "lookback", values: [5, 10, 20] }] });
    expect(get(scriptSweeps).selectedSweepId).toBe("sweep-1");
  });

  it("runs points one at a time, stops between points and records retained runs", async () => {
    scriptSweeps.set({ ...get(scriptSweeps), scriptId: "script-1", sweeps: [sweep()], selectedSweepId: "sweep-1" });
    researchScriptWorkspace.update((state) => ({ ...state, detail: { script: { script_id: "script-1" } } as never }));
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => { stopSweepRun(); return jsonResponse(run(0)); })
      .mockResolvedValueOnce(jsonResponse({ sweep_id: "sweep-1", points: [] }));
    vi.stubGlobal("fetch", fetchMock);
    updateSweepDraft({ evaluationTarget: { target: "weight_book", result_id: "", execution_lag: 2, cost_bps: 5 } });
    await runSweepPoints([0, 1, 2]);
    expect(fetchMock.mock.calls[0][0]).toContain("/script-sweeps/sweep-1/points/0/run");
    expect(fetchMock.mock.calls[1][0]).toContain("/script-sweeps/sweep-1/evaluate");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({ target: "weight_book", execution_lag: 2, cost_bps: 5 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(get(scriptSweeps).notice).toContain("Stopped after 1 of 3");
    expect(get(researchScriptWorkspace).runs.map((item) => item.run_id)).toEqual(["run-0"]);
    expect(get(researchScriptWorkspace).selectedRun).toBeNull();
  });
});
