import { getBlob, getJson, postJson } from "./client";
import type {
  StrategyLabResult,
  ResearchScriptDetail,
  ResearchScriptInputSnapshot,
  ResearchScriptListResponse,
  ResearchScriptRun,
  ResearchScriptRunComparison,
  ResearchScriptRunListResponse,
  ResearchScriptParameterValue,
  ResearchScriptRuntimeCapabilities,
  ResearchScriptStorageDiagnostics
} from "./types";

export interface ScriptAnalyticalItem {
  result: { result_id: string; name: string; kind: string; meaning: string; [key: string]: unknown };
  mapping: Record<string, unknown> | null;
  preview_sha256: string;
  can_open: boolean;
  unsupported_reason: string | null;
}
/** Opciones del libro causal de pesos; forman parte del hash de la vista previa. */
export interface ScriptBookOptions { execution_lag: number; cost_bps: number }
export interface ScriptWeightBookRebalance {
  decision_date: string; effective_period_start: string; effective_period_end: string; turnover: number;
  cost_fraction: number; gross_exposure: number; net_exposure: number; cash_weight: number;
}
export interface ScriptWeightBook {
  book_id: "weight_book"; options: ScriptBookOptions; weight_result_ids: string[]; return_result_ids: string[];
  instruments: string[]; preview_sha256: string; can_open: boolean; unsupported_reason: string | null;
  mapping: (Record<string, unknown> & {
    rows: Array<{ date: string; value: number }>; assumptions: string[];
    details: { calendar_start: string; calendar_end: string; trimmed_observations: Record<string, number>;
      rebalances: ScriptWeightBookRebalance[]; superseded_decisions: string[]; ignored_decisions: string[];
      total_turnover: number; total_cost_fraction: number; max_gross_exposure: number; warnings: string[] };
  }) | null;
}
export interface ScriptAnalyticalReport {
  run_id: string; execution_status: string; executes_source: boolean;
  artifacts: Array<{ output_id: string; valid: boolean; eligible: boolean; errors: string[]; warnings: string[];
    provenance: Record<string, unknown>; instruments?: Record<string, unknown>[]; results: ScriptAnalyticalItem[];
    weight_book?: ScriptWeightBook | null }>;
}
export const DEFAULT_BOOK_OPTIONS: ScriptBookOptions = { execution_lag: 1, cost_bps: 0 };
export const inspectScriptAnalytics = (runId: string, options: ScriptBookOptions = DEFAULT_BOOK_OPTIONS) => getJson<ScriptAnalyticalReport>(
  `/research/strategy-lab/script-runs/${encodeURIComponent(runId)}/analytics?execution_lag=${encodeURIComponent(options.execution_lag)}&cost_bps=${encodeURIComponent(options.cost_bps)}`
);
export const openScriptAnalytics = (
  runId: string, outputId: string, resultId: string, previewHash: string,
  book?: ScriptBookOptions
) => postJson<StrategyLabResult>(
  `/research/strategy-lab/script-runs/${encodeURIComponent(runId)}/analytics/open`,
  book
    ? { output_id: outputId, result_id: resultId, preview_sha256: previewHash, target: "weight_book", ...book }
    : { output_id: outputId, result_id: resultId, preview_sha256: previewHash }
);

// ---- E5: barridos de parámetros y validación walk-forward ----
export type ScriptParameters = Record<string, ResearchScriptParameterValue>;
export interface ScriptSweep {
  sweep_id: string; script_id: string; revision_id: string; source_sha256: string;
  input_snapshot_id: string; input_manifest_sha256: string; base_parameters: ScriptParameters;
  axes: Array<{ name: string; values: ResearchScriptParameterValue[] }>;
  points: Array<{ index: number; parameters: ScriptParameters; parameters_sha256: string }>;
  definition_sha256: string; created_at: string; created_by: string; origin: string;
  transformation_note: string | null; contract_version: string;
}
export interface ScriptEvaluationTarget {
  target: "returns_result" | "weight_book"; result_id?: string; execution_lag?: number; cost_bps?: number;
}
export interface ScriptDescriptiveMetrics {
  observations: number; start?: string; end?: string; total_return?: number | null; annual_return?: number | null;
  annual_volatility?: number | null; sharpe_ratio?: number | null; max_drawdown?: number | null;
}
export interface ScriptSweepEvaluationPoint {
  index: number; parameters: ScriptParameters; parameters_sha256: string; run_id: string | null;
  run_status: string | null; state: string; reason: string | null;
  coverage: { start: string; end: string; observations: number } | null; metrics: ScriptDescriptiveMetrics | null;
}
export interface ScriptSweepEvaluation {
  contract_version: string; sweep_id: string; definition_sha256: string; trials: number; ready_points: number;
  evaluation: ScriptEvaluationTarget & { timing: { enforced_by_gamma: boolean; note: string; execution_lag?: number } };
  common_window: { start: string; end: string; observations: number } | null; in_sample_label: string; warnings: string[];
  points: ScriptSweepEvaluationPoint[];
}
export interface ScriptWalkForwardFold {
  fold: number; train_start: string; train_end: string; train_observations: number; test_start: string; test_end: string;
  test_observations: number; partial: boolean; selected_point: number; selected_parameters: ScriptParameters;
  selected_train_metric: number | null; train_metrics: Record<string, number | null>; test_return: number; causal: boolean;
}
export interface ScriptWalkForwardReport {
  contract_version: string; sweep_id: string; definition_sha256: string; report_sha256: string; trials: number;
  config: { train_observations: number; test_observations: number; window: "anchored" | "rolling"; selection_metric: "sharpe" | "total_return"; tie_break: string };
  evaluation: ScriptSweepEvaluation["evaluation"];
  common_window: { start: string; end: string; observations: number };
  folds: ScriptWalkForwardFold[]; selection_frequency: Record<string, number>;
  out_of_sample: ScriptDescriptiveMetrics & { selection_metric_value: number | null; rows: Array<{ date: string; value: number }> };
  in_sample_selected_mean_metric: number | null;
  in_sample_reference: { point_index: number | null; metric: string; value: number | null; label: string; parameters: ScriptParameters | null };
  causality: { rule: string; verified: boolean }; warnings: string[];
}
export interface ScriptWalkForwardRequest {
  evaluation: ScriptEvaluationTarget; train_observations: number; test_observations: number;
  window: "anchored" | "rolling"; selection_metric: "sharpe" | "total_return";
}
export const createResearchScriptSweep = (scriptId: string, payload: {
  revision_id: string; input_snapshot_id: string; base_parameters: ScriptParameters;
  axes: Array<{ name: string; values: ResearchScriptParameterValue[] }>;
}) => postJson<ScriptSweep>(`/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/sweeps`, payload);
export const listResearchScriptSweeps = (scriptId: string) =>
  getJson<ScriptSweep[]>(`/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/sweeps`);
export const runResearchScriptSweepPoint = (sweepId: string, index: number) => postJson<ResearchScriptRun>(
  `/research/strategy-lab/script-sweeps/${encodeURIComponent(sweepId)}/points/${index}/run`, {}, { timeoutMs: 130_000 });
export const evaluateResearchScriptSweep = (sweepId: string, evaluation: ScriptEvaluationTarget) =>
  postJson<ScriptSweepEvaluation>(`/research/strategy-lab/script-sweeps/${encodeURIComponent(sweepId)}/evaluate`, evaluation);
export const walkForwardResearchScriptSweep = (sweepId: string, request: ScriptWalkForwardRequest) =>
  postJson<ScriptWalkForwardReport>(`/research/strategy-lab/script-sweeps/${encodeURIComponent(sweepId)}/walk-forward`, request);

export interface CreateResearchScriptPayload {
  session_id: string;
  title: string;
  source: string;
}

export interface CreateResearchScriptRevisionPayload {
  source: string;
  expected_parent_sha256: string;
  change_summary?: string;
}

export interface CreateResearchScriptRunPayload {
  revision_id: string;
  input_snapshot_id?: string;
  parameters?: Record<string, ResearchScriptParameterValue>;
  input_files?: Array<{
    logical_filename: string;
    media_type: string;
    content: string;
    source_kind: "user_upload";
  }>;
}

export interface ExportResearchScriptInputPayload {
  domain: string;
  preview_id?: string;
  outcome_id?: string;
  object_id: string;
  logical_filename: string;
  region?: string;
  timeframe?: string;
  lookback_days?: number;
  frequency?: "daily" | "weekly" | "monthly";
  additional_input_files?: CreateResearchScriptRunPayload["input_files"];
  base_snapshot_id?: string;
}

export interface ResearchScriptInputPreview {
  logical_filename: string;
  media_type: string;
  byte_size: number;
  text: string;
  truncated: boolean;
}

export const createResearchScriptInputBundle = (
  scriptId: string,
  payload: {
    base_snapshot_id?: string;
    retained_filenames?: string[];
    input_files?: CreateResearchScriptRunPayload["input_files"];
  }
) => postJson<ResearchScriptInputSnapshot>(
  `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/inputs`, payload
);

export const listResearchScriptInputBundles = (scriptId: string) =>
  getJson<ResearchScriptInputSnapshot[]>(
    `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/inputs`
  );

export const getResearchScriptInputPreview = (snapshotId: string, filename: string) =>
  getJson<ResearchScriptInputPreview>(
    `/research/strategy-lab/script-inputs/${encodeURIComponent(snapshotId)}/preview?filename=${encodeURIComponent(filename)}`
  );

export interface ResearchScriptRevisionDecisionPayload {
  expected_parent_sha256: string;
}

export const listResearchScripts = (includeArchived = false) =>
  getJson<ResearchScriptListResponse>(
    `/research/strategy-lab/scripts${includeArchived ? "?include_archived=true" : ""}`
  );

export const getResearchScriptRuntimeCapabilities = () =>
  getJson<ResearchScriptRuntimeCapabilities>(
    "/research/strategy-lab/scripts/runtime-capabilities"
  );

export const getResearchScript = (scriptId: string) =>
  getJson<ResearchScriptDetail>(`/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}`);

export const createResearchScript = (payload: CreateResearchScriptPayload) =>
  postJson<ResearchScriptDetail>("/research/strategy-lab/scripts", payload);

export const duplicateResearchScript = (scriptId: string, title?: string) =>
  postJson<ResearchScriptDetail>(
    `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/duplicate`,
    { title: title?.trim() || null }
  );

export const archiveResearchScript = (scriptId: string) =>
  postJson<ResearchScriptDetail>(
    `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/archive`,
    {}
  );

export const restoreResearchScript = (scriptId: string) =>
  postJson<ResearchScriptDetail>(
    `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/restore`,
    {}
  );

export const exportResearchScriptInput = (
  scriptId: string,
  payload: ExportResearchScriptInputPayload
) => postJson<ResearchScriptInputSnapshot>(
  `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/inputs/export`,
  payload
);

export const createResearchScriptRevision = (
  scriptId: string,
  payload: CreateResearchScriptRevisionPayload
) => postJson<ResearchScriptDetail>(
  `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/revisions`,
  payload
);

export const acceptResearchScriptRevision = (
  scriptId: string,
  revisionId: string,
  payload: ResearchScriptRevisionDecisionPayload
) => postJson<ResearchScriptDetail>(
  `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/revisions/${encodeURIComponent(revisionId)}/accept`,
  payload
);

export const rejectResearchScriptRevision = (
  scriptId: string,
  revisionId: string,
  payload: ResearchScriptRevisionDecisionPayload
) => postJson<ResearchScriptDetail>(
  `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/revisions/${encodeURIComponent(revisionId)}/reject`,
  payload
);

export const createResearchScriptRun = (
  scriptId: string,
  payload: CreateResearchScriptRunPayload
) => postJson<ResearchScriptRun>(
  `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/runs`,
  payload,
  { timeoutMs: 130_000 }
);

export const listResearchScriptRuns = (scriptId: string) =>
  getJson<ResearchScriptRunListResponse>(
    `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/runs`
  );

export const getResearchScriptRun = (runId: string) =>
  getJson<ResearchScriptRun>(`/research/strategy-lab/script-runs/${encodeURIComponent(runId)}`);

export const getResearchScriptInputSnapshot = (snapshotId: string) =>
  getJson<ResearchScriptInputSnapshot>(
    `/research/strategy-lab/script-inputs/${encodeURIComponent(snapshotId)}`
  );

export const compareResearchScriptRuns = (baseRunId: string, comparisonRunId: string) =>
  getJson<ResearchScriptRunComparison>(
    `/research/strategy-lab/script-runs/compare?base_run_id=${encodeURIComponent(baseRunId)}&comparison_run_id=${encodeURIComponent(comparisonRunId)}`
  );

export const getResearchScriptStorageDiagnostics = () =>
  getJson<ResearchScriptStorageDiagnostics>(
    "/research/strategy-lab/scripts/storage-diagnostics"
  );

export const cleanupResearchScriptStorage = () =>
  postJson<ResearchScriptStorageDiagnostics>(
    "/research/strategy-lab/scripts/storage-diagnostics/cleanup",
    {}
  );

export const fetchResearchScriptOutput = (runId: string, outputId: string) =>
  getBlob(
    `/research/strategy-lab/script-runs/${encodeURIComponent(runId)}/outputs/${encodeURIComponent(outputId)}`
  );

export const fetchResearchScriptRunExport = (runId: string) =>
  getBlob(`/research/strategy-lab/script-runs/${encodeURIComponent(runId)}/export`);

export interface ScriptDatasetDefinition { domain: string; label: string; limitations: string }
export interface ScriptDatasetSelection { object_id: string; label: string; region?: string; outcome_id?: string }
export interface ScriptDatasetSearch { items: ScriptDatasetSelection[]; warnings: string[]; status: string; limitations?: string }
export interface ScriptDatasetPreview {
  preview_id: string; byte_size: number; sha256: string;
  fields: Array<{ name: string; type: string; unit: string | null }>;
  sources: string[]; retrieval_times: string[]; states: string[]; units: string[]; frequencies: string[];
  coverage_start: string | null; coverage_end: string | null; warnings: string[]; limitations: string; field_notes: string; cache_status: string;
}
export const listScriptDatasets = () => getJson<ScriptDatasetDefinition[]>("/research/strategy-lab/script-datasets");
export const searchScriptDatasets = (domain: string, query: string) => getJson<ScriptDatasetSearch>(
  `/research/strategy-lab/script-datasets/search?domain=${encodeURIComponent(domain)}&query=${encodeURIComponent(query)}`);
export const previewScriptDataset = (scriptId: string, payload: ExportResearchScriptInputPayload) => postJson<ScriptDatasetPreview>(
  `/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}/dataset-preview`, payload, { timeoutMs: 120_000 });
