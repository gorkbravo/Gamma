import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { CopilotWorkingAnalysis } from "../lib/api/types";
import { evidenceValue, retainedEvidenceModes, retainedEvidenceTarget, retainedEvidenceTools } from "../lib/retained-evidence";
import { resolveWorkingAnalysisTarget } from "../lib/copilot-workspace";
import RetainedWorkingEvidence from "./RetainedWorkingEvidence.svelte";

function fixture(): CopilotWorkingAnalysis {
  return {
    analysis_id: "work_123", session_id: "session", run_id: "run", tool_id: "run_macro_series_analysis",
    domain: "macro", analysis_type: "retained_evidence", title: "US CPI — retained analysis", status: "active",
    state_scope: "session_ephemeral", entity: { normalized_id: "us-cpi-yoy" }, inputs: { timeframe: "1Y", region: "US" },
    outputs: { result: { title: "US CPI", observations: 12, unit: "pct", change: 0.2, latest: { value: 2.5 } }, sources: [{ provider: "fred", retrieved_at: "2026-01-01T00:00:00Z" }] },
    source_ids: ["macro.cpi"], warnings: ["Monthly observations; no interpolation."], context_fingerprint: null,
    owning_tab: "macro", owning_mode: "snapshot", materialization: { target_tab: "macro", target_mode: "snapshot", durable: false, payload_contract: "copilot.retained-evidence.v1" },
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", expires_at: "2099-01-01T00:00:00Z",
    materialized_at: null, discarded_at: null, read_only_safety: {}, source_provider: "fred", origin: "fixture",
    transformation_note: "Original dated evidence; opening does not refresh.", contract_version: "copilot.working-analysis.v1"
  };
}

describe("Checkpoint 8 retained evidence", () => {
  it("accepts exactly the supported owning-tab contracts", () => {
    for (const [tab, mode] of Object.entries(retainedEvidenceModes)) {
      const row = { ...fixture(), tool_id: Object.keys(retainedEvidenceTools).find(tool => retainedEvidenceTools[tool] === tab)!, owning_tab: tab, owning_mode: mode, materialization: { ...fixture().materialization, target_tab: tab, target_mode: mode } };
      expect(resolveWorkingAnalysisTarget(row)).toEqual({ analysisId: row.analysis_id, tab, mode, retainedEvidence: true });
    }
  });
  it("rejects expired, discarded, durable, malformed and mismatched snapshots", () => {
    const row = fixture();
    for (const invalid of [
      { ...row, status: "discarded" }, { ...row, expires_at: "2020-01-01T00:00:00" },
      { ...row, expires_at: "invalid" }, { ...row, owning_tab: "portfolio" },
      { ...row, tool_id: "run_crypto_token_analysis" },
      { ...row, materialization: { ...row.materialization, target_mode: "deep_dive" } },
      { ...row, materialization: { ...row.materialization, durable: true } }, { ...row, outputs: {} }
    ]) expect(retainedEvidenceTarget(invalid)).toBeNull();
  });
  it("renders dated evidence and warnings, withholding expired numbers", () => {
    const row = fixture();
    const body = render(RetainedWorkingEvidence, { props: { analysis: row } }).body;
    expect(body).toContain("TEMPORARY"); expect(body).toContain(evidenceValue(2.5));
    expect(body).toContain("Monthly observations; no interpolation.");
    expect(body).toContain("2026-01-01"); expect(body).toContain("Return to workspace");
    expect(body).toContain("Inputs and assumptions");
    const expired = render(RetainedWorkingEvidence, { props: { analysis: { ...row, status: "expired" } } }).body;
    expect(expired).toContain("expired or unavailable"); expect(expired).not.toContain(evidenceValue(2.5));
  });
  it("preserves zero and distinguishes fractions, percentage points and unavailable numbers", () => {
    expect(evidenceValue(0)).toBe("0"); expect(evidenceValue(null)).toBe("N/A");
    expect(evidenceValue(NaN)).toBe("N/A"); expect(evidenceValue(0.12, "total_return")).toBe("12.00%");
    expect(evidenceValue(2.5, "change_pct")).toBe("2.50%");
  });
});
