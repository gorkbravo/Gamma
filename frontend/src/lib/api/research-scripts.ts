import { getJson, postJson } from "./client";
import type {
  ResearchScriptDetail,
  ResearchScriptListResponse,
  ResearchScriptRun,
  ResearchScriptRunListResponse,
  ResearchScriptRuntimeCapabilities
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
  input_files?: Array<{
    logical_filename: string;
    media_type: string;
    content: string;
    source_kind: "user_upload";
  }>;
}

export interface ResearchScriptRevisionDecisionPayload {
  expected_parent_sha256: string;
}

export const listResearchScripts = () =>
  getJson<ResearchScriptListResponse>("/research/strategy-lab/scripts");

export const getResearchScriptRuntimeCapabilities = () =>
  getJson<ResearchScriptRuntimeCapabilities>(
    "/research/strategy-lab/scripts/runtime-capabilities"
  );

export const getResearchScript = (scriptId: string) =>
  getJson<ResearchScriptDetail>(`/research/strategy-lab/scripts/${encodeURIComponent(scriptId)}`);

export const createResearchScript = (payload: CreateResearchScriptPayload) =>
  postJson<ResearchScriptDetail>("/research/strategy-lab/scripts", payload);

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

export const researchScriptOutputDownloadUrl = (runId: string, outputId: string) =>
  `/research/strategy-lab/script-runs/${encodeURIComponent(runId)}/outputs/${encodeURIComponent(outputId)}`;
