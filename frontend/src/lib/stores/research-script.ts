import { get, writable } from "svelte/store";

import {
  acceptResearchScriptRevision,
  createResearchScript,
  createResearchScriptRevision,
  createResearchScriptRun,
  getResearchScriptRuntimeCapabilities,
  getResearchScript,
  listResearchScriptRuns,
  listResearchScripts,
  rejectResearchScriptRevision
} from "../api/research-scripts";
import type {
  ResearchScript,
  ResearchScriptDetail,
  ResearchScriptRevision,
  ResearchScriptRun,
  ResearchScriptRuntimeCapabilities
} from "../api/types";

export const DEFAULT_RESEARCH_SCRIPT_SOURCE = `# Gamma Research Script
# Save an immutable revision before running it in the configured bounded runtime.

def research(inputs):
    return {"status": "preview"}
`;

export interface ResearchScriptWorkspaceState {
  initialized: boolean;
  scripts: ResearchScript[];
  detail: ResearchScriptDetail | null;
  sourceDraft: string;
  selectedRevisionId: string | null;
  runs: ResearchScriptRun[];
  selectedRun: ResearchScriptRun | null;
  capabilities: ResearchScriptRuntimeCapabilities | null;
  inputFilename: string;
  inputContent: string;
  loading: "list" | "load" | "create" | "save" | "run" | "decision" | null;
  error: string;
  notice: string;
}

export const initialResearchScriptWorkspaceState = (): ResearchScriptWorkspaceState => ({
  initialized: false,
  scripts: [],
  detail: null,
  sourceDraft: DEFAULT_RESEARCH_SCRIPT_SOURCE,
  selectedRevisionId: null,
  runs: [],
  selectedRun: null,
  capabilities: null,
  inputFilename: "",
  inputContent: "",
  loading: null,
  error: "",
  notice: ""
});

export const researchScriptWorkspace = writable<ResearchScriptWorkspaceState>(
  initialResearchScriptWorkspaceState()
);

const messageOf = (error: unknown) => error instanceof Error ? error.message : String(error);

function canonicalRevision(detail: ResearchScriptDetail | null): ResearchScriptRevision | null {
  if (!detail) return null;
  return detail.revisions.find(
    (revision) => revision.revision_id === detail.script.canonical_revision_id
  ) ?? null;
}

function setBusy(loading: ResearchScriptWorkspaceState["loading"]) {
  researchScriptWorkspace.update((state) => ({ ...state, loading, error: "", notice: "" }));
}

export function resetResearchScriptWorkspace() {
  researchScriptWorkspace.set(initialResearchScriptWorkspaceState());
}

export function updateResearchScriptDraft(sourceDraft: string) {
  researchScriptWorkspace.update((state) => ({ ...state, sourceDraft, error: "", notice: "" }));
}

export function updateResearchScriptInput(inputFilename: string, inputContent: string) {
  researchScriptWorkspace.update((state) => ({ ...state, inputFilename, inputContent }));
}

export async function initializeResearchScriptWorkspace() {
  if (get(researchScriptWorkspace).initialized) return;
  setBusy("list");
  try {
    const [response, capabilities] = await Promise.all([
      listResearchScripts(),
      getResearchScriptRuntimeCapabilities()
    ]);
    researchScriptWorkspace.update((state) => ({
      ...state,
      initialized: true,
      scripts: response.items,
      capabilities,
      loading: null
    }));
    if (response.items.length) {
      await loadResearchScript(response.items[0].script_id);
    }
  } catch (error) {
    researchScriptWorkspace.update((state) => ({
      ...state,
      initialized: true,
      loading: null,
      error: messageOf(error)
    }));
  }
}

export async function createWorkspaceResearchScript(title: string) {
  const state = get(researchScriptWorkspace);
  const normalizedTitle = title.trim();
  if (!normalizedTitle) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "A script title is required." }));
    return null;
  }
  if (!state.sourceDraft.trim()) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Python source is required." }));
    return null;
  }
  setBusy("create");
  try {
    const detail = await createResearchScript({
      session_id: "strategy-lab-script-workspace",
      title: normalizedTitle,
      source: state.sourceDraft
    });
    researchScriptWorkspace.update((current) => ({
      ...current,
      initialized: true,
      scripts: [detail.script, ...current.scripts.filter((item) => item.script_id !== detail.script.script_id)],
      detail,
      selectedRevisionId: detail.script.canonical_revision_id,
      runs: [],
      selectedRun: null,
      loading: null,
      notice: "Script created with immutable revision 1."
    }));
    return detail;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export async function loadResearchScript(scriptId: string) {
  if (!scriptId) return null;
  setBusy("load");
  try {
    const [detail, runResponse] = await Promise.all([
      getResearchScript(scriptId),
      listResearchScriptRuns(scriptId)
    ]);
    const revision = canonicalRevision(detail);
    researchScriptWorkspace.update((state) => ({
      ...state,
      scripts: [detail.script, ...state.scripts.filter((item) => item.script_id !== scriptId)],
      detail,
      sourceDraft: revision?.source ?? state.sourceDraft,
      selectedRevisionId: revision?.revision_id ?? null,
      runs: runResponse.items,
      selectedRun: runResponse.items[0] ?? null,
      loading: null
    }));
    return detail;
  } catch (error) {
    researchScriptWorkspace.update((state) => ({ ...state, loading: null, error: messageOf(error) }));
    return null;
  }
}

export function selectResearchScriptRevision(revisionId: string) {
  researchScriptWorkspace.update((state) => {
    const revision = state.detail?.revisions.find((item) => item.revision_id === revisionId);
    if (!revision) return state;
    return {
      ...state,
      selectedRevisionId: revision.revision_id,
      sourceDraft: revision.source,
      error: "",
      notice: `Loaded immutable revision ${revision.revision_number}.`
    };
  });
}

export async function persistResearchScriptRevision(changeSummary = "User-edited Script workspace revision") {
  const state = get(researchScriptWorkspace);
  const detail = state.detail;
  const parent = canonicalRevision(detail);
  if (!detail || !parent) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Create or load a script before saving." }));
    return null;
  }
  if (!state.sourceDraft.trim()) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Python source is required." }));
    return null;
  }
  if (state.sourceDraft === parent.source) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "The editor already matches the canonical revision." }));
    return null;
  }
  setBusy("save");
  try {
    const next = await createResearchScriptRevision(detail.script.script_id, {
      source: state.sourceDraft,
      expected_parent_sha256: parent.source_sha256,
      change_summary: changeSummary
    });
    researchScriptWorkspace.update((current) => ({
      ...current,
      scripts: [next.script, ...current.scripts.filter((item) => item.script_id !== next.script.script_id)],
      detail: next,
      selectedRevisionId: next.script.canonical_revision_id,
      loading: null,
      notice: `Saved immutable revision ${next.revisions.at(-1)?.revision_number ?? ""}.`
    }));
    return next;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export async function runSelectedResearchScript() {
  const state = get(researchScriptWorkspace);
  if (!state.detail || !state.selectedRevisionId) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Select an immutable revision before running." }));
    return null;
  }
  const revision = state.detail.revisions.find((item) => item.revision_id === state.selectedRevisionId);
  if (!revision || revision.source !== state.sourceDraft) {
    researchScriptWorkspace.update((current) => ({
      ...current,
      error: "Save the edited source as a revision, or reload the selected revision, before running."
    }));
    return null;
  }
  if (state.inputContent && !state.inputFilename.trim()) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Name the optional text input before running." }));
    return null;
  }
  setBusy("run");
  try {
    const inputFiles = state.inputFilename.trim()
      ? [{
          logical_filename: state.inputFilename.trim(),
          media_type: "text/plain",
          content: state.inputContent,
          source_kind: "user_upload" as const
        }]
      : [];
    const run = await createResearchScriptRun(state.detail.script.script_id, {
      revision_id: revision.revision_id,
      input_files: inputFiles
    });
    researchScriptWorkspace.update((current) => ({
      ...current,
      runs: [run, ...current.runs.filter((item) => item.run_id !== run.run_id)],
      selectedRun: run,
      loading: null,
      notice: run.status === "completed"
        ? state.capabilities?.executes_source
          ? "Immutable research run completed."
          : "Safe-preview run completed."
        : `Research run ended: ${run.status}.`
    }));
    return run;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export function selectResearchScriptRun(runId: string) {
  researchScriptWorkspace.update((state) => ({
    ...state,
    selectedRun: state.runs.find((run) => run.run_id === runId) ?? state.selectedRun
  }));
}

export async function resolveStagedResearchScriptRevision(
  revisionId: string,
  decision: "accept" | "reject"
) {
  const state = get(researchScriptWorkspace);
  const detail = state.detail;
  const canonical = canonicalRevision(detail);
  const candidate = detail?.revisions.find((item) => item.revision_id === revisionId);
  if (!detail || !canonical || !candidate || candidate.status !== "staged") {
    researchScriptWorkspace.update((current) => ({
      ...current,
      error: "The staged Operator candidate is no longer available. Reload the script."
    }));
    return null;
  }
  setBusy("decision");
  try {
    const next = await (
      decision === "accept" ? acceptResearchScriptRevision : rejectResearchScriptRevision
    )(
      detail.script.script_id,
      candidate.revision_id,
      { expected_parent_sha256: canonical.source_sha256 }
    );
    const nextCanonical = canonicalRevision(next);
    researchScriptWorkspace.update((current) => ({
      ...current,
      scripts: [
        next.script,
        ...current.scripts.filter((item) => item.script_id !== next.script.script_id)
      ],
      detail: next,
      selectedRevisionId: nextCanonical?.revision_id ?? null,
      sourceDraft: nextCanonical?.source ?? current.sourceDraft,
      loading: null,
      notice: decision === "accept"
        ? `Accepted Operator candidate as canonical revision ${nextCanonical?.revision_number ?? ""}.`
        : "Rejected Operator candidate; canonical user source was preserved."
    }));
    return next;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({
      ...current,
      loading: null,
      error: messageOf(error)
    }));
    return null;
  }
}

export async function openMaterializedResearchScript(options: {
  scriptId: string;
  revisionId: string;
  selectedRunId: string | null;
}) {
  await initializeResearchScriptWorkspace();
  const detail = await loadResearchScript(options.scriptId);
  if (!detail) return null;
  const targetRevision = detail.revisions.find(
    (item) => item.revision_id === options.revisionId
  );
  if (targetRevision?.status === "canonical") {
    selectResearchScriptRevision(targetRevision.revision_id);
  }
  if (options.selectedRunId) {
    selectResearchScriptRun(options.selectedRunId);
  }
  researchScriptWorkspace.update((state) => ({
    ...state,
    notice: targetRevision?.status === "staged"
      ? "Loaded canonical source with an Operator candidate awaiting explicit accept or reject."
      : "Loaded the materialized Research Script working analysis."
  }));
  return detail;
}
