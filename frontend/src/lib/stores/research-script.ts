import { get, writable } from "svelte/store";

import {
  acceptResearchScriptRevision,
  archiveResearchScript,
  cleanupResearchScriptStorage,
  compareResearchScriptRuns,
  createResearchScript,
  createResearchScriptRevision,
  createResearchScriptRun,
  createResearchScriptInputBundle,
  duplicateResearchScript,
  exportResearchScriptInput,
  getResearchScriptRuntimeCapabilities,
  getResearchScriptInputSnapshot,
  getResearchScriptInputPreview,
  listResearchScriptInputBundles,
  getResearchScriptStorageDiagnostics,
  getResearchScript,
  listResearchScriptRuns,
  listResearchScripts,
  rejectResearchScriptRevision,
  restoreResearchScript,
  type ExportResearchScriptInputPayload,
  type CreateResearchScriptRunPayload,
  type ResearchScriptInputPreview
} from "../api/research-scripts";
import type {
  ResearchScript,
  ResearchScriptParameterValue,
  ResearchScriptDetail,
  ResearchScriptInputSnapshot,
  ResearchScriptRevision,
  ResearchScriptRun,
  ResearchScriptRunComparison,
  ResearchScriptRuntimeCapabilities,
  ResearchScriptStorageDiagnostics
} from "../api/types";

export const DEFAULT_RESEARCH_SCRIPT_SOURCE = `# Write ordinary Python. Read added datasets using their filenames.
# Example: prices = pandas.read_csv("spy-prices.csv")

print("Hello World")
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
  preparedInputSnapshot: ResearchScriptInputSnapshot | null;
  inputBundles: ResearchScriptInputSnapshot[];
  selectedRunInputSnapshot: ResearchScriptInputSnapshot | null;
  inputPreview: ResearchScriptInputPreview | null;
  previewLoading: boolean;
  previewError: string;
  runComparison: ResearchScriptRunComparison | null;
  diagnostics: ResearchScriptStorageDiagnostics | null;
  includeArchived: boolean;
  inputFilename: string;
  inputContent: string;
  /** E5: objeto JSON plano que el servidor entrega como gamma_parameters.json; "{}" = sin parámetros. */
  parametersDraft: string;
  loading: "list" | "load" | "create" | "save" | "run" | "decision" | "input" | "lifecycle" | "compare" | "cleanup" | null;
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
  preparedInputSnapshot: null,
  inputBundles: [],
  selectedRunInputSnapshot: null,
  inputPreview: null,
  previewLoading: false,
  previewError: "",
  runComparison: null,
  diagnostics: null,
  includeArchived: false,
  inputFilename: "",
  inputContent: "",
  parametersDraft: "{}",
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

async function refreshStorageDiagnostics() {
  try {
    const diagnostics = await getResearchScriptStorageDiagnostics();
    researchScriptWorkspace.update((state) => ({ ...state, diagnostics }));
  } catch {
    // Diagnostics are a recovery aid. A temporary diagnostics failure must not
    // erase or relabel the successful durable mutation that preceded it.
  }
}

export function resetResearchScriptWorkspace() {
  researchScriptWorkspace.set(initialResearchScriptWorkspaceState());
}

export function updateResearchScriptDraft(sourceDraft: string) {
  researchScriptWorkspace.update((state) => ({ ...state, sourceDraft, error: "", notice: "" }));
}

export type ParsedResearchScriptParameters =
  | { ok: true; values: Record<string, ResearchScriptParameterValue> }
  | { ok: false; error: string };

/** Validación local mínima; el servidor canoniza, aplica los límites completos y calcula el hash. */
export function parseResearchScriptParameters(text: string): ParsedResearchScriptParameters {
  const trimmed = text.trim();
  if (!trimmed) return { ok: true, values: {} };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    return { ok: false, error: `Parameters must be valid JSON: ${messageOf(error)}` };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, error: "Parameters must be a flat JSON object, for example {\"lookback\": 20}." };
  }
  for (const [name, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (value !== null && typeof value === "object") {
      return { ok: false, error: `Parameter "${name}" must be a number, text, boolean or null.` };
    }
  }
  return { ok: true, values: parsed as Record<string, ResearchScriptParameterValue> };
}

export function updateResearchScriptParameters(parametersDraft: string) {
  researchScriptWorkspace.update((state) => ({ ...state, parametersDraft, error: "", notice: "" }));
}

export function useSelectedRunResearchScriptParameters() {
  researchScriptWorkspace.update((state) => ({
    ...state,
    parametersDraft: JSON.stringify(state.selectedRun?.parameters ?? {}, null, 2),
    notice: state.selectedRun?.parameters ? "Loaded the selected run's parameters for the next run." : "The selected run had no parameters."
  }));
}

/** Incorpora ejecuciones creadas fuera del botón Run (puntos de un barrido) sin perder la selección. */
export function recordResearchScriptRuns(runs: ResearchScriptRun[], options: { select?: boolean } = {}) {
  if (!runs.length) return;
  researchScriptWorkspace.update((state) => {
    if (!state.detail || runs.some((run) => run.script_id !== state.detail?.script.script_id)) return state;
    const ids = new Set(runs.map((run) => run.run_id));
    return {
      ...state,
      runs: [...runs].reverse().concat(state.runs.filter((run) => !ids.has(run.run_id))),
      selectedRun: options.select ? runs[runs.length - 1] : state.selectedRun
    };
  });
}

export function updateResearchScriptInput(inputFilename: string, inputContent: string) {
  researchScriptWorkspace.update((state) => ({
    ...state,
    inputFilename,
    inputContent,
    error: "",
    notice: ""
  }));
}

export async function initializeResearchScriptWorkspace() {
  if (get(researchScriptWorkspace).initialized) return;
  setBusy("list");
  try {
    const state = get(researchScriptWorkspace);
    const [response, capabilities, diagnostics] = await Promise.all([
      listResearchScripts(state.includeArchived),
      getResearchScriptRuntimeCapabilities(),
      getResearchScriptStorageDiagnostics()
    ]);
    researchScriptWorkspace.update((state) => ({
      ...state,
      initialized: true,
      scripts: response.items,
      capabilities,
      diagnostics,
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
      preparedInputSnapshot: null,
      inputBundles: [],
      selectedRunInputSnapshot: null,
      inputPreview: null,
      runComparison: null,
      loading: null,
      notice: "Script created with immutable revision 1."
    }));
    await refreshStorageDiagnostics();
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
    const [detail, runResponse, inputBundles] = await Promise.all([
      getResearchScript(scriptId),
      listResearchScriptRuns(scriptId),
      listResearchScriptInputBundles(scriptId)
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
      // Los parámetros de la ejecución más reciente son el punto de partida de la siguiente.
      parametersDraft: JSON.stringify(runResponse.items[0]?.parameters ?? {}, null, 2),
      preparedInputSnapshot: inputBundles[0] ?? null,
      inputBundles,
      selectedRunInputSnapshot: null,
      inputPreview: null,
      inputFilename: "",
      inputContent: "",
      runComparison: null,
      loading: null
    }));
    if (runResponse.items[0]) selectResearchScriptRun(runResponse.items[0].run_id);
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
    await refreshStorageDiagnostics();
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
  if (state.inputContent || state.inputFilename.trim()) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Add the pasted input to the bundle, or clear it, before running." }));
    return null;
  }
  const parameters = parseResearchScriptParameters(state.parametersDraft);
  if (!parameters.ok) {
    researchScriptWorkspace.update((current) => ({ ...current, error: parameters.error }));
    return null;
  }
  setBusy("run");
  try {
    const run = await createResearchScriptRun(state.detail.script.script_id, {
      revision_id: revision.revision_id,
      input_snapshot_id: state.preparedInputSnapshot?.snapshot_id,
      input_files: [],
      ...(Object.keys(parameters.values).length ? { parameters: parameters.values } : {})
    });
    researchScriptWorkspace.update((current) => ({
      ...current,
      runs: [run, ...current.runs.filter((item) => item.run_id !== run.run_id)],
      selectedRun: run,
      preparedInputSnapshot: state.preparedInputSnapshot,
      runComparison: null,
      loading: null,
      notice: run.status === "completed"
        ? state.capabilities?.executes_source
          ? "Immutable research run completed."
          : "Safe-preview run completed."
        : `Research run ended: ${run.status}.`
    }));
    try {
      const inputSnapshot = await getResearchScriptInputSnapshot(run.input_snapshot_id);
      researchScriptWorkspace.update((current) => (
        current.selectedRun?.run_id === run.run_id
          ? { ...current, selectedRunInputSnapshot: inputSnapshot,
            // Adding data can finish while the retained manifest is being fetched.
            // Never overwrite newer inputs with the just-finished run's snapshot.
            preparedInputSnapshot: current.preparedInputSnapshot?.snapshot_id === state.preparedInputSnapshot?.snapshot_id
              ? inputSnapshot : current.preparedInputSnapshot,
            inputBundles: current.inputBundles.some(item => item.snapshot_id === inputSnapshot.snapshot_id)
              ? current.inputBundles : [inputSnapshot, ...current.inputBundles] }
          : current
      ));
    } catch (error) {
      researchScriptWorkspace.update((current) => ({
        ...current,
        error: `The run was retained, but its input manifest could not be reloaded: ${messageOf(error)}`
      }));
    }
    await refreshStorageDiagnostics();
    return run;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export function selectResearchScriptRun(runId: string) {
  const run = get(researchScriptWorkspace).runs.find((item) => item.run_id === runId);
  if (!run) return;
  researchScriptWorkspace.update((state) => ({
    ...state,
    selectedRun: run,
    runComparison: null,
    selectedRunInputSnapshot: null
  }));
  void getResearchScriptInputSnapshot(run.input_snapshot_id)
    .then((snapshot) => {
      researchScriptWorkspace.update((state) => (
        state.selectedRun?.run_id === run.run_id
          ? { ...state, selectedRunInputSnapshot: snapshot }
          : state
      ));
    })
    .catch((error) => {
      researchScriptWorkspace.update((state) => ({ ...state, error: messageOf(error) }));
    });
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
  if (state.sourceDraft !== canonical.source) {
    researchScriptWorkspace.update((current) => ({ ...current,
      error: "Save your canonical edits before accepting or rejecting an Operator candidate." }));
    return null;
  }
  setBusy("decision");
  try {
    const acceptedInputs = decision === "accept" && candidate.input_snapshot_id
      ? await getResearchScriptInputSnapshot(candidate.input_snapshot_id) : null;
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
      ...(acceptedInputs ? { preparedInputSnapshot: acceptedInputs } : {}),
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

export async function prepareResearchScriptDomainInput(
  payload: Omit<ExportResearchScriptInputPayload, "additional_input_files">
) {
  const state = get(researchScriptWorkspace);
  if (state.loading) return null;
  if (!state.detail) {
    researchScriptWorkspace.update((current) => ({
      ...current,
      error: "Create or load a script before exporting Gamma data."
    }));
    return null;
  }
  setBusy("input");
  try {
    const snapshot = await exportResearchScriptInput(state.detail.script.script_id, {
      ...payload,
      base_snapshot_id: state.preparedInputSnapshot?.snapshot_id
    });
    researchScriptWorkspace.update((current) => ({
      ...current,
      preparedInputSnapshot: snapshot,
      inputBundles: [snapshot, ...current.inputBundles].slice(0, 100),
      inputPreview: null,
      loading: null,
      notice: `Prepared immutable input snapshot ${snapshot.manifest_sha256.slice(0, 12)} with ${snapshot.files.length} file${snapshot.files.length === 1 ? "" : "s"}.`
    }));
    await refreshStorageDiagnostics();
    return snapshot;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

type InputFilePayload = NonNullable<CreateResearchScriptRunPayload["input_files"]>[number];

async function editResearchScriptInputBundle(
  inputFiles: InputFilePayload[],
  retainedFilenames?: string[],
  clearPaste = false
) {
  const state = get(researchScriptWorkspace);
  if (state.loading) return null;
  if (!state.detail) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Create or load a script before adding inputs." }));
    return null;
  }
  setBusy("input");
  try {
    const snapshot = await createResearchScriptInputBundle(state.detail.script.script_id, {
      base_snapshot_id: state.preparedInputSnapshot?.snapshot_id,
      retained_filenames: retainedFilenames,
      input_files: inputFiles
    });
    researchScriptWorkspace.update((current) => ({
      ...current,
      preparedInputSnapshot: snapshot,
      inputBundles: [snapshot, ...current.inputBundles].slice(0, 100),
      inputPreview: null,
      previewError: "",
      inputFilename: clearPaste ? "" : current.inputFilename,
      inputContent: clearPaste ? "" : current.inputContent,
      loading: null,
      notice: `Input bundle ready: ${snapshot.files.length} file${snapshot.files.length === 1 ? "" : "s"}.`
    }));
    await refreshStorageDiagnostics();
    return snapshot;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

const inputMediaType = (filename: string) => filename.toLowerCase().endsWith(".csv")
  ? "text/csv" : filename.toLowerCase().endsWith(".json") ? "application/json" : "text/plain";

export async function addPastedResearchScriptInput() {
  const state = get(researchScriptWorkspace);
  if (!state.inputFilename.trim()) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Name the pasted input before adding it." }));
    return null;
  }
  return editResearchScriptInputBundle([{
    logical_filename: state.inputFilename.trim(),
    media_type: inputMediaType(state.inputFilename),
    content: state.inputContent,
    source_kind: "user_upload"
  }], undefined, true);
}

export async function importResearchScriptFiles(files: File[]) {
  const state = get(researchScriptWorkspace);
  if (!files.length || state.loading) return null;
  if (!state.detail) {
    researchScriptWorkspace.update((current) => ({ ...current, error: "Create or load a script before importing files." }));
    return null;
  }
  const limits = state.capabilities?.active_limits;
  const names = [...(state.preparedInputSnapshot?.files.map((file) => file.logical_filename) ?? []), ...files.map((file) => file.name)];
  try {
    if (names.length > (limits?.input_files ?? 20)) throw new Error("Input bundle exceeds the file-count limit.");
    if (new Set(names.map(name => name.trim().toLowerCase())).size !== names.length) throw new Error("Input filenames must be unique. Remove the existing file before replacing it.");
    if (files.some((file) => !/\.(csv|json|txt)$/i.test(file.name))) throw new Error("Import UTF-8 CSV, JSON or TXT files.");
    if (files.some((file) => file.size > (limits?.individual_input_bytes ?? 20 * 1024 * 1024))) throw new Error("An input file exceeds the per-file size limit.");
    if ((state.preparedInputSnapshot?.total_bytes ?? 0) + files.reduce((total, file) => total + file.size, 0) > (limits?.total_input_bytes ?? 64 * 1024 * 1024)) throw new Error("Input bundle exceeds the total size limit.");
    setBusy("input");
    const inputFiles: InputFilePayload[] = [];
    for (const file of files) {
      // Preserve UTF-8 bytes, including a BOM, rather than silently converting an encoding.
      const content = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
      inputFiles.push({ logical_filename: file.name, media_type: inputMediaType(file.name), content, source_kind: "user_upload" });
    }
    const current = get(researchScriptWorkspace);
    if (current.detail?.script.script_id !== state.detail.script.script_id ||
        current.preparedInputSnapshot?.snapshot_id !== state.preparedInputSnapshot?.snapshot_id) {
      throw new Error("The selected script or bundle changed during import. Select the intended script and import again.");
    }
    researchScriptWorkspace.update((current) => ({ ...current, loading: null }));
    return editResearchScriptInputBundle(inputFiles);
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: `Import failed: ${messageOf(error)}` }));
    return null;
  }
}

export function removeResearchScriptInput(filename: string) {
  const snapshot = get(researchScriptWorkspace).preparedInputSnapshot;
  if (!snapshot) return null;
  return editResearchScriptInputBundle([], snapshot.files.filter((file) => file.logical_filename !== filename).map((file) => file.logical_filename));
}

export function useSelectedRunResearchScriptInputs() {
  researchScriptWorkspace.update((state) => state.loading || !state.selectedRunInputSnapshot ? state : ({
    ...state,
    preparedInputSnapshot: state.selectedRunInputSnapshot,
    inputBundles: state.inputBundles.some(item => item.snapshot_id === state.selectedRunInputSnapshot?.snapshot_id)
      ? state.inputBundles : [state.selectedRunInputSnapshot, ...state.inputBundles].slice(0, 100),
    inputPreview: null,
    notice: "Selected the historical run's frozen inputs for the next run."
  }));
}

export function selectResearchScriptInputBundle(snapshotId: string) {
  researchScriptWorkspace.update((state) => {
    if (state.loading) return state;
    const bundle = state.inputBundles.find(item => item.snapshot_id === snapshotId);
    if (!bundle) return state;
    return { ...state, preparedInputSnapshot: bundle, inputPreview: null, previewError: "",
      notice: "Selected a retained input bundle for the next run." };
  });
}

let previewRequest = 0;
export async function previewResearchScriptInput(filename: string) {
  const snapshot = get(researchScriptWorkspace).preparedInputSnapshot;
  if (!snapshot) return;
  const request = ++previewRequest;
  researchScriptWorkspace.update((state) => ({ ...state, inputPreview: null, previewLoading: true, previewError: "" }));
  try {
    const preview = await getResearchScriptInputPreview(snapshot.snapshot_id, filename);
    researchScriptWorkspace.update((state) => request !== previewRequest ? state : ({
      ...state,
      inputPreview: state.preparedInputSnapshot?.snapshot_id === snapshot.snapshot_id ? preview : null,
      previewLoading: false
    }));
  } catch (error) {
    researchScriptWorkspace.update((state) => request !== previewRequest ? state : ({
      ...state, previewLoading: false,
      previewError: state.preparedInputSnapshot?.snapshot_id === snapshot.snapshot_id ? messageOf(error) : ""
    }));
  }
}

export async function duplicateWorkspaceResearchScript(title?: string) {
  const state = get(researchScriptWorkspace);
  if (!state.detail) return null;
  setBusy("lifecycle");
  try {
    const detail = await duplicateResearchScript(state.detail.script.script_id, title);
    researchScriptWorkspace.update((current) => ({
      ...current,
      scripts: [detail.script, ...current.scripts],
      detail,
      sourceDraft: canonicalRevision(detail)?.source ?? current.sourceDraft,
      selectedRevisionId: detail.script.canonical_revision_id,
      runs: [],
      selectedRun: null,
      preparedInputSnapshot: null,
      inputBundles: [],
      selectedRunInputSnapshot: null,
      inputPreview: null,
      inputFilename: "",
      inputContent: "",
      runComparison: null,
      loading: null,
      notice: "Created an explicit duplicate with a new script and revision identity."
    }));
    await refreshStorageDiagnostics();
    return detail;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export async function setWorkspaceResearchScriptArchived(archived: boolean) {
  const state = get(researchScriptWorkspace);
  if (!state.detail) return null;
  setBusy("lifecycle");
  try {
    const detail = await (archived ? archiveResearchScript : restoreResearchScript)(
      state.detail.script.script_id
    );
    const response = await listResearchScripts(state.includeArchived);
    const nextActive = response.items.find((item) => item.status !== "archived");
    researchScriptWorkspace.update((current) => ({
      ...current,
      scripts: response.items,
      detail: archived && !state.includeArchived ? null : detail,
      sourceDraft: archived && !state.includeArchived ? DEFAULT_RESEARCH_SCRIPT_SOURCE : current.sourceDraft,
      selectedRevisionId: archived && !state.includeArchived ? null : current.selectedRevisionId,
      runs: archived && !state.includeArchived ? [] : current.runs,
      selectedRun: archived && !state.includeArchived ? null : current.selectedRun,
      preparedInputSnapshot: null,
      inputBundles: [],
      selectedRunInputSnapshot: null,
      inputPreview: null,
      runComparison: null,
      loading: null,
      notice: archived ? "Archived the script without deleting revisions or retained runs." : "Restored the script."
    }));
    if (archived && !state.includeArchived && nextActive) {
      await loadResearchScript(nextActive.script_id);
    }
    await refreshStorageDiagnostics();
    return detail;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export async function setResearchScriptArchivedVisibility(includeArchived: boolean) {
  researchScriptWorkspace.update((state) => ({ ...state, includeArchived }));
  setBusy("list");
  try {
    const response = await listResearchScripts(includeArchived);
    researchScriptWorkspace.update((state) => ({
      ...state,
      scripts: response.items,
      loading: null,
      notice: includeArchived ? "Archived scripts are visible." : "Archived scripts are hidden."
    }));
  } catch (error) {
    researchScriptWorkspace.update((state) => ({ ...state, loading: null, error: messageOf(error) }));
  }
}

export async function compareSelectedResearchScriptRun(comparisonRunId: string) {
  const state = get(researchScriptWorkspace);
  if (!state.selectedRun || !comparisonRunId || state.selectedRun.run_id === comparisonRunId) {
    researchScriptWorkspace.update((current) => ({ ...current, runComparison: null }));
    return null;
  }
  setBusy("compare");
  try {
    const comparison = await compareResearchScriptRuns(state.selectedRun.run_id, comparisonRunId);
    researchScriptWorkspace.update((current) => ({
      ...current,
      runComparison: comparison,
      loading: null,
      notice: "Compared the selected retained runs."
    }));
    return comparison;
  } catch (error) {
    researchScriptWorkspace.update((current) => ({ ...current, loading: null, error: messageOf(error) }));
    return null;
  }
}

export async function cleanupResearchScriptRetainedOutputs() {
  setBusy("cleanup");
  try {
    const diagnostics = await cleanupResearchScriptStorage();
    researchScriptWorkspace.update((state) => ({
      ...state,
      diagnostics,
      loading: null,
      notice: "Retained-output cleanup completed without deleting referenced run artifacts."
    }));
    return diagnostics;
  } catch (error) {
    researchScriptWorkspace.update((state) => ({ ...state, loading: null, error: messageOf(error) }));
    return null;
  }
}

export async function refreshResearchScriptWorkspace() {
  const state = get(researchScriptWorkspace);
  if (!state.detail) return initializeResearchScriptWorkspace();
  const [detail, diagnostics] = await Promise.all([
    loadResearchScript(state.detail.script.script_id),
    getResearchScriptStorageDiagnostics()
  ]);
  researchScriptWorkspace.update((current) => ({
    ...current,
    diagnostics,
    notice: detail ? "Recovered persisted script, revisions, inputs, and runs from Gamma storage." : current.notice
  }));
  return detail;
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
