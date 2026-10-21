import { render } from "svelte/server";
import { describe, expect, it } from "vitest";

import type { ScriptSweep, ScriptSweepEvaluation, ScriptWalkForwardReport } from "../lib/api/research-scripts";
import { initialScriptSweepState } from "../lib/stores/script-sweeps";
import ScriptParameterSweep from "./ScriptParameterSweep.svelte";

const sweep: ScriptSweep = {
  sweep_id: "sweep-1", script_id: "script-1", revision_id: "revision-1", source_sha256: "a".repeat(64),
  input_snapshot_id: "snapshot-1", input_manifest_sha256: "b".repeat(64), base_parameters: { leverage: 1 },
  axes: [{ name: "lookback", values: [5, 20] }],
  points: [5, 20].map((lookback, index) => ({ index, parameters: { leverage: 1, lookback }, parameters_sha256: String(index).repeat(64) })),
  definition_sha256: "d".repeat(64), created_at: "2026-10-20T12:00:00", created_by: "user",
  origin: "research_script_service.create_sweep", transformation_note: null, contract_version: "research-script-sweep.v1"
};

const timing = { enforced_by_gamma: false, note: "Return timing is declared by the script." };

const evaluation: ScriptSweepEvaluation = {
  contract_version: "gamma-script-sweep-evaluation.v1", sweep_id: "sweep-1", definition_sha256: "d".repeat(64),
  trials: 2, ready_points: 1, evaluation: { target: "returns_result", result_id: "strategy", timing },
  common_window: { start: "2026-01-05", end: "2026-08-14", observations: 159 },
  in_sample_label: "Full common-window metrics are in-sample and descriptive. Points are listed in sweep order, not ranked.",
  warnings: ["1 of 2 points are not ready; they still count as trials."],
  points: [
    { index: 0, parameters: { leverage: 1, lookback: 5 }, parameters_sha256: "0".repeat(64), run_id: "run-0", run_status: "completed",
      state: "ready", reason: null, coverage: { start: "2026-01-05", end: "2026-08-14", observations: 159 },
      metrics: { observations: 159, total_return: 0.12, annual_volatility: 0.08, sharpe_ratio: 1.4, max_drawdown: -0.05 } },
    { index: 1, parameters: { leverage: 1, lookback: 20 }, parameters_sha256: "1".repeat(64), run_id: "run-1", run_status: "failed",
      state: "run_failed", reason: "Latest run ended failed; rerun the point.", coverage: null, metrics: null }
  ]
};

const walk: ScriptWalkForwardReport = {
  contract_version: "gamma-script-walk-forward.v1", sweep_id: "sweep-1", definition_sha256: "d".repeat(64), report_sha256: "e".repeat(64),
  trials: 2, config: { train_observations: 60, test_observations: 20, window: "rolling", selection_metric: "sharpe", tie_break: "lowest point index" },
  evaluation: { target: "weight_book", execution_lag: 1, cost_bps: 5, timing: { enforced_by_gamma: true, execution_lag: 1, note: "Gamma applies each dated weight decision only from a later return period." } },
  common_window: { start: "2026-01-05", end: "2026-08-14", observations: 159 },
  folds: [{ fold: 1, train_start: "2026-01-05", train_end: "2026-03-30", train_observations: 60, test_start: "2026-03-31", test_end: "2026-04-27",
    test_observations: 20, partial: false, selected_point: 1, selected_parameters: { leverage: 1, lookback: 20 },
    selected_train_metric: 2.1, train_metrics: { "0": 1.1, "1": 2.1 }, test_return: -0.01, causal: true }],
  selection_frequency: { "1": 1 },
  out_of_sample: { observations: 20, total_return: -0.01, sharpe_ratio: -0.4, max_drawdown: -0.03, selection_metric_value: -0.4, rows: [] },
  in_sample_selected_mean_metric: 2.1,
  in_sample_reference: { point_index: 1, metric: "sharpe", value: 1.9, parameters: { leverage: 1, lookback: 20 },
    label: "In-sample reference: chosen with every observation. Descriptive only; not a validation result." },
  causality: { rule: "Each fold selects with training observations only.", verified: true },
  warnings: []
};

const baseProps = {
  scriptId: "script-1", revisionId: "revision-1", revisionNumber: 3, inputSnapshotId: "snapshot-1",
  baseParameters: { leverage: 1 }, runs: []
};

describe("ScriptParameterSweep", () => {
  it("shows unranked in-sample comparison with every trial and the author-timing caveat", () => {
    const { body } = render(ScriptParameterSweep, { props: { ...baseProps,
      snapshot: { ...initialScriptSweepState(), scriptId: "script-1", sweeps: [sweep], selectedSweepId: "sweep-1", evaluation } } });
    expect(body).toContain("not ranked");
    expect(body).toMatch(/Trials <strong[^>]*>2<\/strong>/);
    expect(body).toContain("Run failed");
    expect(body).toContain("Return timing is declared by the script.");
    expect(body.indexOf("lookback=5")).toBeLessThan(body.indexOf("lookback=20"));
    expect(body).not.toMatch(/best|winner|optimal/i);
    expect(body).toContain("Walk-forward needs every point run");
  });

  it("leads with out-of-sample evidence and labels the in-sample optimum as not validation", () => {
    const { body } = render(ScriptParameterSweep, { props: { ...baseProps,
      snapshot: { ...initialScriptSweepState(), scriptId: "script-1", sweeps: [sweep], selectedSweepId: "sweep-1", walkForward: walk } } });
    expect(body.indexOf("OOS total return")).toBeLessThan(body.indexOf("In-sample reference · not validation"));
    expect(body).toContain("Causal timing verified");
    expect(body).toContain("execution lag of 1 period");
    expect(body).toContain("-1.00%");
    expect(body).toContain("nothing saved");
  });

  it("explains that a sweep needs an exact input bundle", () => {
    const { body } = render(ScriptParameterSweep, { props: { ...baseProps, inputSnapshotId: null, snapshot: initialScriptSweepState() } });
    expect(body).toContain("Prepare an input bundle first");
  });
});
