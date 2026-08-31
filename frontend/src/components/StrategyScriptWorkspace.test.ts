import { render } from "svelte/server";
import { describe, expect, it } from "vitest";

import type { ResearchScriptOutput, ResearchScriptRun } from "../lib/api/types";
import { initialResearchScriptWorkspaceState } from "../lib/stores/research-script";
import StrategyScriptWorkspace from "./StrategyScriptWorkspace.svelte";

const output = (
  kind: ResearchScriptOutput["kind"],
  overrides: Partial<ResearchScriptOutput> = {}
): ResearchScriptOutput => ({
  output_id: `output-${kind}`,
  kind,
  sequence: 1,
  media_type: "text/plain",
  byte_size: 12,
  created_at: "2026-08-29T12:00:00",
  artifact_ref: null,
  provider_native_ref: null,
  text: null,
  metric_name: null,
  metric_value: null,
  unit: null,
  columns: [],
  rows: [],
  filename: null,
  alt_text: null,
  source_provider: "gamma_mock_research_script_runtime",
  origin: "mock_research_script_runtime",
  transformation_note: "Typed mock fixture",
  generated: true,
  contract_version: "research-script-output.v1",
  ...overrides
});

const run = (overrides: Partial<ResearchScriptRun> = {}): ResearchScriptRun => ({
  run_id: "run-1",
  script_id: "script-1",
  revision_id: "revision-1",
  source_sha256: "a".repeat(64),
  input_snapshot_id: "snapshot-1",
  input_manifest_sha256: "b".repeat(64),
  input_file_count: 0,
  input_total_bytes: 0,
  runtime_provider: "gamma_mock_research_script_runtime",
  runtime_kind: "mock_safe_preview",
  provider_container_id: null,
  provider_response_id: "mock-response",
  status: "completed",
  started_at: "2026-08-29T12:00:00",
  completed_at: "2026-08-29T12:00:00",
  outputs: [],
  source_refs: [],
  warnings: ["Safe preview only: no source code was executed."],
  usage: { executed_code: false, network_access: false },
  limits: { source_bytes: 65_536 },
  source_provider: "gamma_mock_research_script_runtime",
  origin: "research_script_service.create_run",
  transformation_note: "Normalized deterministic mock outputs.",
  contract_version: "research-script-run.v1",
  ...overrides
});

const activeDetail = () => ({
  script: {
    script_id: "script-1",
    session_id: "session-1",
    title: "Research Script",
    language: "python" as const,
    status: "active" as const,
    canonical_revision_id: "revision-1",
    created_by: "user" as const,
    created_at: "2026-08-29T12:00:00",
    updated_at: "2026-08-29T12:00:00",
    source_provider: "gamma_user",
    origin: "test",
    transformation_note: null,
    contract_version: "research-script.v1"
  },
  revisions: [{
    revision_id: "revision-1",
    script_id: "script-1",
    revision_number: 1,
    source: "print('bounded')\n",
    source_sha256: "a".repeat(64),
    created_by: "user" as const,
    created_at: "2026-08-29T12:00:00",
    parent_revision_id: null,
    status: "canonical" as const,
    change_summary: "User source",
    operator_run_id: null,
    expected_parent_sha256: null,
    contract_version: "research-script-revision.v1"
  }]
});

describe("StrategyScriptWorkspace", () => {
  it("renders the safe-runtime boundary and every typed output shape", () => {
    const selectedRun = run({
      outputs: [
        output("log", { text: "Validated immutable source" }),
        output("summary", { output_id: "output-summary", text: "Generated summary" }),
        output("metric", { metric_name: "Source bytes", metric_value: 144, unit: "bytes" }),
        output("table", {
          media_type: "application/json",
          columns: ["field", "value"],
          rows: [{ field: "executed", value: false }]
        }),
        output("image", { media_type: "image/svg+xml", filename: "preview.svg", alt_text: "Preview chart" }),
        output("file", { media_type: "application/json", filename: "manifest.json", artifact_ref: "artifact:manifest" }),
        output("warning", { text: "Mock warning" }),
        output("error", { text: "Mock failure detail" })
      ]
    });
    const snapshot = {
      ...initialResearchScriptWorkspaceState(),
      initialized: true,
      runs: [selectedRun],
      selectedRun
    };

    const { body } = render(StrategyScriptWorkspace, { props: { snapshot } });

    expect(body).toContain("Mock / Safe Preview");
    expect(body).toContain("Python source is persisted and SHA-256 bound");
    expect(body).toContain("Validated immutable source");
    expect(body).toContain("Generated summary");
    expect(body).toContain("Source bytes");
    expect(body).toContain("executed");
    expect(body).toContain("IMAGE ARTIFACT");
    expect(body).toContain("preview.svg");
    expect(body).toContain("manifest.json");
    expect(body).toContain("Mock warning");
    expect(body).toContain("Mock failure detail");
  });

  it("renders loading, empty, validation failure, and terminal failure states", () => {
    const loading = render(StrategyScriptWorkspace, {
      props: { snapshot: { ...initialResearchScriptWorkspaceState(), loading: "run" } }
    }).body;
    const empty = render(StrategyScriptWorkspace, {
      props: { snapshot: initialResearchScriptWorkspaceState() }
    }).body;
    const failedRun = run({ status: "failed", outputs: [output("error", { text: "Runtime fixture failed" })] });
    const failed = render(StrategyScriptWorkspace, {
      props: {
        snapshot: {
          ...initialResearchScriptWorkspaceState(),
          error: "The canonical source changed.",
          runs: [failedRun],
          selectedRun: failedRun
        }
      }
    }).body;

    expect(loading).toContain("Preparing a deterministic mock result");
    expect(empty).toContain("No run selected");
    expect(failed).toContain("Action failed");
    expect(failed).toContain("The canonical source changed.");
    expect(failed).toContain("Runtime fixture failed");
  });

  it("keeps canonical source visible while exposing a staged Operator diff", () => {
    const canonicalSource = "print('canonical user source')\n";
    const candidateSource = "print('operator candidate')\nprint('warning')\n";
    const snapshot = {
      ...initialResearchScriptWorkspaceState(),
      initialized: true,
      sourceDraft: canonicalSource,
      selectedRevisionId: "revision-canonical",
      detail: {
        script: {
          script_id: "script-1",
          session_id: "session-1",
          title: "Research Script",
          language: "python" as const,
          status: "active" as const,
          canonical_revision_id: "revision-canonical",
          created_by: "user" as const,
          created_at: "2026-08-29T12:00:00",
          updated_at: "2026-08-29T12:01:00",
          source_provider: "gamma_user",
          origin: "test",
          transformation_note: null,
          contract_version: "research-script.v1"
        },
        revisions: [
          {
            revision_id: "revision-canonical",
            script_id: "script-1",
            revision_number: 1,
            source: canonicalSource,
            source_sha256: "a".repeat(64),
            created_by: "user" as const,
            created_at: "2026-08-29T12:00:00",
            parent_revision_id: null,
            status: "canonical" as const,
            change_summary: "User source",
            operator_run_id: null,
            expected_parent_sha256: null,
            contract_version: "research-script-revision.v1"
          },
          {
            revision_id: "revision-staged",
            script_id: "script-1",
            revision_number: 2,
            source: candidateSource,
            source_sha256: "b".repeat(64),
            created_by: "operator" as const,
            created_at: "2026-08-29T12:01:00",
            parent_revision_id: "revision-canonical",
            status: "staged" as const,
            change_summary: "Add explicit warning",
            operator_run_id: "oprun-1",
            expected_parent_sha256: "a".repeat(64),
            contract_version: "research-script-revision.v1"
          }
        ]
      }
    };

    const { body } = render(StrategyScriptWorkspace, { props: { snapshot } });

    expect(body).toContain("Staged source diff");
    expect(body).toContain("Canonical editor source is unchanged");
    expect(body).toContain("Add explicit warning");
    expect(body).toContain("Accept candidate");
    expect(body).toContain("Reject");
    expect(body).toContain("operator candidate");
  });

  it("renders Slice 5 data bridge, lifecycle, comparison, cost, and recovery states", () => {
    const selectedRun = run({
      usage: {
        executed_code: true,
        input_tokens: 100,
        output_tokens: 50,
        estimated_token_cost_usd: 0.00008
      }
    });
    const comparisonRun = run({ run_id: "run-2", started_at: "2026-08-29T13:00:00" });
    const snapshot = {
      ...initialResearchScriptWorkspaceState(),
      initialized: true,
      scripts: [activeDetail().script],
      detail: activeDetail(),
      sourceDraft: "print('bounded')\n",
      selectedRevisionId: "revision-1",
      runs: [selectedRun, comparisonRun],
      selectedRun,
      preparedInputSnapshot: {
        snapshot_id: "snapshot-1",
        script_id: "script-1",
        created_at: "2026-08-29T12:00:00",
        files: [{
          logical_filename: "spy.csv",
          media_type: "text/csv",
          byte_size: 20,
          content_sha256: "b".repeat(64),
          gamma_object_id: "SPY",
          provider_id: "gamma_market_data",
          source_timestamp: null,
          retrieved_at: "2026-08-29T12:00:00",
          transformation_note: "Bounded equity export",
          source_kind: "gamma_state" as const
        }],
        dataset_refs: [{ domain: "equity_history", object_id: "SPY" }],
        source_refs: [{ provider: "gamma_market_data" }],
        total_bytes: 20,
        manifest_sha256: "b".repeat(64),
        warnings: [],
        contract_version: "research-script-input.v1"
      },
      runComparison: {
        base_run_id: "run-1",
        comparison_run_id: "run-2",
        same_revision: true,
        same_input_snapshot: true,
        status_changed: false,
        duration_delta_seconds: 0,
        input_token_delta: 0,
        output_token_delta: 0,
        output_count_delta: 0,
        warning_count_delta: 0,
        metric_deltas: [],
        contract_version: "research-script-run-comparison.v1"
      },
      diagnostics: {
        script_count: 1,
        archived_script_count: 0,
        revision_count: 1,
        input_snapshot_count: 1,
        run_count: 2,
        retained_output_count: 4,
        retained_output_bytes: 2048,
        missing_output_count: 0,
        orphan_output_count: 1,
        storage_warnings: ["One recoverable orphan was found."],
        contract_version: "research-script-storage-diagnostics.v1"
      }
    };

    const { body } = render(StrategyScriptWorkspace, { props: { snapshot } });

    expect(body).toContain("Prepare Gamma snapshot");
    expect(body).toContain("spy.csv");
    expect(body).toContain("gamma_state");
    expect(body).toContain("Duplicate");
    expect(body).toContain("Archive");
    expect(body).toContain("Recover / reload");
    expect(body).toContain("Export auditable run bundle");
    expect(body).toContain("Comparison between the selected Research Script runs");
    expect(body).toContain("Same immutable revision");
    expect(body).toMatch(/Input tokens<\/span><strong[^>]*>100<\/strong>/);
    expect(body).toMatch(/Output tokens<\/span><strong[^>]*>50<\/strong>/);
    expect(body).toContain("Token cost estimate");
    expect(body).toContain("$0.000080");
    expect(body).toContain("Clean orphaned outputs");
    expect(body).toContain("One recoverable orphan was found.");
  });
});
