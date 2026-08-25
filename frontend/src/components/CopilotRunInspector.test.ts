import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type {
  CopilotDiagnostics,
  CopilotResearchCardResult,
  CopilotWorkingAnalysis
} from "../lib/api/types";
import CopilotRunInspector from "./CopilotRunInspector.svelte";

const capabilities = {
  structured_output: true,
  tool_use: true,
  streaming: true,
  reasoning: true,
  cancellation: true,
  provider_storage: true
};

const storage = {
  policy_version: "copilot.provider-storage.v1",
  requested: "disabled",
  effective: "disabled",
  status: "supported",
  reason: "Provider response storage is disabled; Gamma reconstructs continuation locally."
};

const resolution = {
  policy_version: "copilot.model-policy.v1",
  selected_profile: "standard",
  resolved_profile: "standard",
  selection_source: "user",
  status: "ready",
  provider: "openai_responses",
  model: "gpt-5.5",
  reasoning_mode: "reasoning",
  reasoning_effort: "medium" as const,
  orchestration_path: "responses_custom_loop",
  capabilities,
  routing_reason: "Standard was user-selected; routed through the baseline custom loop.",
  provider_storage: storage,
  degradation_reason: null
};

const diagnostics: CopilotDiagnostics = {
  provider_state: "configured",
  provider: "openai_responses",
  provider_label: "OpenAI Responses",
  model_policy_version: "copilot.model-policy.v1",
  profiles: [],
  default_resolution: resolution,
  operator_resolution: { ...resolution, orchestration_path: "gamma_custom_loop" },
  local_storage: "Gamma stores structured session continuity locally for replay.",
  provider_storage: storage,
  last_error: {
    category: "rate_limited",
    diagnostic_id: "cp6.rate_limited.0123456789ab",
    message: "The provider rate-limited this Copilot run.",
    guidance: "Wait briefly and retry.",
    retryable: true,
    created_at: "2026-07-25T10:00:00Z"
  }
};

const result: CopilotResearchCardResult = {
  domain: "macro",
  current_tab: "macro",
  status: "error",
  provider: "openai_responses",
  model: "gpt-5.5",
  response_id: null,
  message: diagnostics.last_error?.message ?? null,
  card: null,
  sources: [],
  tool_traces: [],
  operator_events: [],
  warnings: [],
  model_resolution: resolution,
  usage: {
    input_tokens: null,
    output_tokens: null,
    reasoning_tokens: null,
    total_tokens: null,
    cache_read_tokens: null,
    cache_write_tokens: null,
    provider_calls: 1,
    tool_calls: 0,
    raw: {}
  },
  observability: {
    selected_profile: "standard",
    resolved_provider: "openai_responses",
    resolved_model: "gpt-5.5",
    model_policy_version: "copilot.model-policy.v1",
    routing_reason: resolution.routing_reason,
    reasoning_mode: "reasoning",
    reasoning_effort: "medium",
    orchestration_path: "responses_custom_loop",
    total_latency_ms: 812,
    provider_latency_ms: 790,
    cancellation_outcome: null,
    cancellation_boundary: null,
    provider_error_category: "rate_limited",
    diagnostic_id: "cp6.rate_limited.0123456789ab"
  },
  safe_provider_error: diagnostics.last_error
};

const workingAnalysis: CopilotWorkingAnalysis = {
  analysis_id: "work_lmt",
  session_id: "session_lmt",
  run_id: "oprun_lmt",
  tool_id: "run_fundamentals_reverse_valuation",
  domain: "fundamentals",
  analysis_type: "reverse_valuation",
  title: "Lockheed Martin Corporation reverse valuation",
  status: "active",
  state_scope: "session_ephemeral",
  entity: { ticker: "LMT" },
  inputs: { ticker: "LMT" },
  outputs: { ticker: "LMT" },
  source_ids: ["fundamentals.reverse_valuation.analysis"],
  warnings: [],
  context_fingerprint: "fp_lmt",
  owning_tab: "fundamentals",
  owning_mode: "reverse_valuation",
  materialization: { durable: false },
  created_at: "2026-08-25T10:00:00Z",
  updated_at: "2026-08-25T10:00:00Z",
  expires_at: "2026-09-01T10:00:00Z",
  materialized_at: null,
  discarded_at: null,
  read_only_safety: { execution_enabled: false },
  source_provider: "gamma",
  origin: "tests",
  transformation_note: null,
  contract_version: "copilot.working-analysis.v1"
};

describe("CopilotRunInspector", () => {
  it("renders replayable routing, explicit unavailable metrics, and safe diagnostics", () => {
    const { body } = render(CopilotRunInspector, {
      props: { result, diagnostics, onClose: vi.fn() }
    });

    expect(body).toContain("Run inspector");
    expect(body).toContain("openai responses");
    expect(body).toContain("gpt-5.5");
    expect(body).toContain("812 ms");
    expect(body).toContain("790 ms");
    expect(body.match(/Unavailable/g)?.length ?? 0).toBeGreaterThanOrEqual(5);
    expect(body).toContain("Gamma stores structured session continuity locally for replay.");
    expect(body).toContain("Provider response storage is disabled");
    expect(body).toContain("cp6.rate_limited.0123456789ab");
    expect(body).toContain("Wait briefly and retry.");
    expect(body).not.toContain("stack trace");
    expect(body).not.toContain("authorization");
  });

  it("keeps diagnostic copy and close controls keyboard-native", () => {
    const { body } = render(CopilotRunInspector, {
      props: { result, diagnostics, onClose: vi.fn() }
    });
    const source = readFileSync(
      fileURLToPath(new URL("./CopilotRunInspector.svelte", import.meta.url)),
      "utf8"
    );

    expect(body).toContain(
      'aria-label="Copy diagnostic ID cp6.rate_limited.0123456789ab"'
    );
    expect(body).toContain('aria-label="Close Copilot run inspector"');
    // Both actions are native buttons, so Enter and Space activate the same
    // handlers exercised by pointer input.
    expect(source).toContain("on:click={copyDiagnosticId}");
    expect(source).toContain("on:click={onClose}");
    expect(source.match(/type="button"/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
  });

  it("shows temporary working state with owning-tab lifecycle controls", () => {
    const { body } = render(CopilotRunInspector, {
      props: {
        result,
        diagnostics,
        workingAnalyses: [workingAnalysis],
        onOpenWorkingAnalysis: vi.fn(),
        onDiscardWorkingAnalysis: vi.fn(),
        onClose: vi.fn()
      }
    });

    expect(body).toContain("Working analyses");
    expect(body).toContain("Temporary");
    expect(body).toContain("Lockheed Martin Corporation reverse valuation");
    expect(body).toContain("fundamentals / reverse valuation");
    expect(body).toContain("Opening does not save a DCF model");
    expect(body).toContain("Open in Fundamentals");
    expect(body).toContain("Discard");
  });
});
