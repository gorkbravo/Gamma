import { getBlob, getJson, postJson } from "./client";
import type {
  ResearchScriptDetail,
  ResearchScriptInputSnapshot,
  ResearchScriptListResponse,
  ResearchScriptRun,
  ResearchScriptRunComparison,
  ResearchScriptRunListResponse,
  ResearchScriptRuntimeCapabilities,
  ResearchScriptStorageDiagnostics
} from "./types";

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
  input_files?: Array<{
    logical_filename: string;
    media_type: string;
    content: string;
    source_kind: "user_upload";
  }>;
}

export interface ExportResearchScriptInputPayload {
  domain: "equity_history" | "macro_series" | "saved_research";
  object_id: string;
  logical_filename: string;
  region?: string;
  timeframe?: string;
  lookback_days?: number;
  frequency?: "daily" | "weekly" | "monthly";
  additional_input_files?: CreateResearchScriptRunPayload["input_files"];
}

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
