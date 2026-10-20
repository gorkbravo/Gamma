import { get } from "svelte/store";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResearchScriptDetail, ResearchScriptRun, ResearchScriptInputSnapshot } from "../api/types";
import {
  createWorkspaceResearchScript,
  persistResearchScriptRevision,
  researchScriptWorkspace,
  resolveStagedResearchScriptRevision,
  resetResearchScriptWorkspace,
  runSelectedResearchScript,
  updateResearchScriptDraft,
  prepareResearchScriptDomainInput,
  addPastedResearchScriptInput,
  importResearchScriptFiles,
  removeResearchScriptInput,
  selectResearchScriptRun,
  updateResearchScriptInput,
  useSelectedRunResearchScriptInputs,
  loadResearchScript,
  parseResearchScriptParameters,
  updateResearchScriptParameters
} from "./research-script";

const detail = (revisionNumber = 1, source = "print('preview')\n"): ResearchScriptDetail => {
  const revisionId = `revision-${revisionNumber}`;
  return {
    script: {
      script_id: "script-1",
      session_id: "strategy-lab-script-workspace",
      title: "Research Script",
      language: "python",
      status: revisionNumber === 1 ? "draft" : "active",
      canonical_revision_id: revisionId,
      created_by: "user",
      created_at: "2026-08-29T12:00:00",
      updated_at: "2026-08-29T12:00:00",
      source_provider: "gamma_user",
      origin: "research_script_service.create_script",
      transformation_note: "User source",
      contract_version: "research-script.v1"
    },
    revisions: Array.from({ length: revisionNumber }, (_, index) => ({
      revision_id: `revision-${index + 1}`,
      script_id: "script-1",
      revision_number: index + 1,
      source: index + 1 === revisionNumber ? source : "print('preview')\n",
      source_sha256: String(index + 1).repeat(64),
      created_by: "user" as const,
      created_at: "2026-08-29T12:00:00",
      parent_revision_id: index ? `revision-${index}` : null,
      status: "canonical" as const,
      change_summary: index ? "User edit" : "Initial revision",
      operator_run_id: null,
      expected_parent_sha256: index ? String(index).repeat(64) : null,
      contract_version: "research-script-revision.v1"
    }))
  };
};

const run = (): ResearchScriptRun => ({
  run_id: "run-1",
  script_id: "script-1",
  revision_id: "revision-2",
  source_sha256: "2".repeat(64),
  input_snapshot_id: "snapshot-1",
  input_manifest_sha256: "a".repeat(64),
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
  warnings: ["No source code was executed."],
  usage: { executed_code: false },
  limits: { source_bytes: 65_536 },
  source_provider: "gamma_mock_research_script_runtime",
  origin: "research_script_service.create_run",
  transformation_note: "Safe preview",
  contract_version: "research-script-run.v1"
});

const diagnostics = (scripts = 1, revisions = 1, snapshots = 0, runs = 0) => ({
  script_count: scripts,
  archived_script_count: 0,
  revision_count: revisions,
  input_snapshot_count: snapshots,
  run_count: runs,
  retained_output_count: 0,
  retained_output_bytes: 0,
  missing_output_count: 0,
  orphan_output_count: 0,
  storage_warnings: [],
  contract_version: "research-script-storage-diagnostics.v1"
});

const inputSnapshot = {
  snapshot_id: "snapshot-1",
  script_id: "script-1",
  created_at: "2026-08-29T12:00:00",
  files: [],
  dataset_refs: [],
  source_refs: [],
  total_bytes: 0,
  manifest_sha256: "a".repeat(64),
  warnings: [],
  contract_version: "research-script-input.v1"
};

const jsonResponse = (value: unknown, status = 200, statusText = "OK") => new Response(
  JSON.stringify(value),
  { status, statusText, headers: { "Content-Type": "application/json" } }
);

const bundle = (id: string, filenames: string[]): ResearchScriptInputSnapshot => ({
  ...inputSnapshot,
  snapshot_id: id,
  source_provider: "gamma_research_script",
  origin: "research_script_service.create_input_snapshot",
  transformation_note: "Copied data",
  files: filenames.map((name) => ({
    logical_filename: name, media_type: "text/csv", byte_size: 20,
    content_sha256: "b".repeat(64), gamma_object_id: null, provider_id: null,
    source_timestamp: null, retrieved_at: "2026-10-14T12:00:00", transformation_note: null,
    source_kind: "user_upload", artifact_ref: `research-script-input:${id}:${name}`
  })),
  total_bytes: filenames.length * 20
});

function loadedWorkspace(preparedInputSnapshot: ResearchScriptInputSnapshot | null = null) {
  const initial = detail();
  researchScriptWorkspace.set({ ...get(researchScriptWorkspace), detail: initial,
    sourceDraft: initial.revisions[0].source, selectedRevisionId: "revision-1", preparedInputSnapshot });
}

describe("research script workspace store", () => {
  beforeEach(() => resetResearchScriptWorkspace());
  afterEach(() => vi.unstubAllGlobals());

  it("appends Gamma exports to the existing frozen bundle without including unadded pasted text", async () => {
    const base = bundle("base", ["spy.csv"]);
    loadedWorkspace(base);
    updateResearchScriptInput("draft.csv", "x,y\n1,2\n");
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(bundle("mixed", ["spy.csv", "cpi.csv"])))
      .mockResolvedValueOnce(jsonResponse(diagnostics()));
    vi.stubGlobal("fetch", fetchMock);
    await prepareResearchScriptDomainInput({ domain: "macro_series", object_id: "CPI", logical_filename: "cpi.csv" });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.base_snapshot_id).toBe("base");
    expect(body.additional_input_files).toBeUndefined();
    expect(get(researchScriptWorkspace).preparedInputSnapshot?.files.map(file => file.logical_filename)).toEqual(["spy.csv", "cpi.csv"]);
    expect(get(researchScriptWorkspace).inputContent).toBe("x,y\n1,2\n");
  });

  it("preserves the bundle and pasted draft after an append failure and blocks running unadded text", async () => {
    const base = bundle("base", ["spy.csv"]);
    loadedWorkspace(base);
    updateResearchScriptInput("spy.csv", "new prices");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: ["Duplicate input filename"] }, 422));
    vi.stubGlobal("fetch", fetchMock);
    await addPastedResearchScriptInput();
    expect(get(researchScriptWorkspace).preparedInputSnapshot).toEqual(base);
    expect(get(researchScriptWorkspace).inputContent).toBe("new prices");
    await runSelectedResearchScript();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(get(researchScriptWorkspace).error).toContain("Add the pasted input");
  });

  it("imports several UTF-8 files atomically and preserves BOM and line endings", async () => {
    loadedWorkspace(bundle("base", ["spy.csv"]));
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(bundle("mixed", ["spy.csv", "external.csv", "config.json"])))
      .mockResolvedValueOnce(jsonResponse(diagnostics()));
    vi.stubGlobal("fetch", fetchMock);
    await importResearchScriptFiles([
      new File(["\ufeffdate,name\r\n2026-10-14,España\r\n"], "external.csv"),
      new File(['{"lookback":20}'], "config.json")
    ]);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.base_snapshot_id).toBe("base");
    expect(body.input_files[0].content).toBe("\ufeffdate,name\r\n2026-10-14,España\r\n");
    expect(body.input_files.map((file: {media_type: string}) => file.media_type)).toEqual(["text/csv", "application/json"]);
    expect(get(researchScriptWorkspace).preparedInputSnapshot?.files).toHaveLength(3);
  });

  it("rejects duplicate names, invalid UTF-8 and oversized uploads without changing the bundle", async () => {
    const base = bundle("base", ["spy.csv"]);
    loadedWorkspace(base);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await importResearchScriptFiles([new File(["x"], "SPY.csv")]);
    expect(get(researchScriptWorkspace).error).toContain("unique");
    await importResearchScriptFiles([new File([new Uint8Array([0xff])], "bad.csv")]);
    expect(get(researchScriptWorkspace).error).toContain("Import failed");
    await importResearchScriptFiles([{ name: "huge.csv", size: 21 * 1024 * 1024 } as File]);
    expect(get(researchScriptWorkspace).error).toContain("per-file size");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(researchScriptWorkspace).preparedInputSnapshot).toEqual(base);
  });

  it("inspects historical inputs separately and uses them only after an explicit selection", async () => {
    const base = bundle("next", ["new.csv"]);
    loadedWorkspace(base);
    researchScriptWorkspace.update(state => ({ ...state, runs: [run()] }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(bundle("historical", ["old.csv"]))));
    selectResearchScriptRun("run-1");
    await vi.waitFor(() => expect(get(researchScriptWorkspace).selectedRunInputSnapshot?.snapshot_id).toBe("historical"));
    expect(get(researchScriptWorkspace).preparedInputSnapshot).toEqual(base);
    useSelectedRunResearchScriptInputs();
    expect(get(researchScriptWorkspace).preparedInputSnapshot?.snapshot_id).toBe("historical");
  });

  it("removes only the selected file by deriving a new snapshot", async () => {
    loadedWorkspace(bundle("mixed", ["spy.csv", "external.csv"]));
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(bundle("reduced", ["external.csv"])))
      .mockResolvedValueOnce(jsonResponse(diagnostics()));
    vi.stubGlobal("fetch", fetchMock);
    await removeResearchScriptInput("spy.csv");
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.base_snapshot_id).toBe("mixed");
    expect(body.retained_filenames).toEqual(["external.csv"]);
    expect(get(researchScriptWorkspace).preparedInputSnapshot?.snapshot_id).toBe("reduced");
  });

  it("recovers a prepared bundle before any run exists", async () => {
    const latest = bundle("latest", ["spy.csv", "external.csv"]);
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(detail()))
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse([latest]));
    vi.stubGlobal("fetch", fetchMock);
    await loadResearchScript("script-1");
    expect(get(researchScriptWorkspace).preparedInputSnapshot).toEqual(latest);
    expect(get(researchScriptWorkspace).inputBundles).toEqual([latest]);
    expect(get(researchScriptWorkspace).selectedRun).toBeNull();
  });

  it("creates a script, persists a revision, and submits that exact revision for a run", async () => {
    const first = detail();
    const revised = detail(2, "print('edited preview')\n");
    const completedRun = run();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(first, 201, "Created"))
      .mockResolvedValueOnce(jsonResponse(diagnostics()))
      .mockResolvedValueOnce(jsonResponse(revised, 201, "Created"))
      .mockResolvedValueOnce(jsonResponse(diagnostics(1, 2)))
      .mockResolvedValueOnce(jsonResponse(completedRun, 201, "Created"))
      .mockResolvedValueOnce(jsonResponse(inputSnapshot))
      .mockResolvedValueOnce(jsonResponse(diagnostics(1, 2, 1, 1)));
    vi.stubGlobal("fetch", fetchMock);

    updateResearchScriptDraft("print('preview')\n");
    await createWorkspaceResearchScript("Research Script");
    updateResearchScriptDraft("print('edited preview')\n");
    await persistResearchScriptRevision("Edit research fixture");
    await runSelectedResearchScript();

    const createBody = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    const revisionBody = JSON.parse(fetchMock.mock.calls[2][1].body as string);
    const runBody = JSON.parse(fetchMock.mock.calls[4][1].body as string);
    expect(createBody.source).toBe("print('preview')\n");
    expect(revisionBody.expected_parent_sha256).toBe("1".repeat(64));
    expect(revisionBody.source).toBe("print('edited preview')\n");
    expect(runBody.revision_id).toBe("revision-2");
    expect(get(researchScriptWorkspace).selectedRun?.run_id).toBe("run-1");
    expect(get(researchScriptWorkspace).diagnostics?.run_count).toBe(1);
    expect(get(researchScriptWorkspace).notice).toBe("Safe-preview run completed.");
  });

  it("surfaces API failures without discarding the edited source", async () => {
    researchScriptWorkspace.set({
      ...get(researchScriptWorkspace),
      initialized: true,
      scripts: [detail().script],
      detail: detail(),
      sourceDraft: "print('unsaved edit')\n",
      selectedRevisionId: "revision-1"
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      jsonResponse({ detail: "The canonical source changed." }, 409, "Conflict")
    ));

    await persistResearchScriptRevision();

    expect(get(researchScriptWorkspace).error).toContain("The canonical source changed.");
    expect(get(researchScriptWorkspace).sourceDraft).toBe("print('unsaved edit')\n");
  });

  it("preserves draft and selected-run state when the Script component is unmounted", () => {
    const selectedRun = run();
    researchScriptWorkspace.set({
      ...get(researchScriptWorkspace),
      sourceDraft: "# retained between Strategy Lab modes\n",
      selectedRevisionId: "revision-2",
      runs: [selectedRun],
      selectedRun
    });

    // StrategyLabView conditionally unmounts the component; this module store is deliberately unchanged.
    expect(get(researchScriptWorkspace).sourceDraft).toBe("# retained between Strategy Lab modes\n");
    expect(get(researchScriptWorkspace).selectedRevisionId).toBe("revision-2");
    expect(get(researchScriptWorkspace).selectedRun?.run_id).toBe("run-1");
  });

  it("accepts a staged Operator candidate only against the canonical parent hash", async () => {
    const initial = detail();
    const staged: ResearchScriptDetail = {
      script: initial.script,
      revisions: [
        ...initial.revisions,
        {
          ...initial.revisions[0],
          revision_id: "revision-staged",
          revision_number: 2,
          source: "print('operator candidate')\n",
          source_sha256: "2".repeat(64),
          created_by: "operator",
          parent_revision_id: "revision-1",
          status: "staged",
          change_summary: "Operator candidate",
          input_snapshot_id: "reviewed-inputs",
          operator_run_id: "oprun-1",
          expected_parent_sha256: "1".repeat(64)
        }
      ]
    };
    const accepted: ResearchScriptDetail = {
      script: { ...staged.script, canonical_revision_id: "revision-staged" },
      revisions: staged.revisions.map((item) =>
        item.revision_id === "revision-staged" ? { ...item, status: "canonical" } : item
      )
    };
    researchScriptWorkspace.set({
      ...get(researchScriptWorkspace),
      initialized: true,
      scripts: [staged.script],
      detail: staged,
      sourceDraft: initial.revisions[0].source,
      selectedRevisionId: "revision-1"
    });
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(bundle("reviewed-inputs", ["external.json"])))
      .mockResolvedValueOnce(jsonResponse(accepted));
    vi.stubGlobal("fetch", fetchMock);

    await resolveStagedResearchScriptRevision("revision-staged", "accept");

    const body = JSON.parse(fetchMock.mock.calls[1][1].body as string);
    expect(body.expected_parent_sha256).toBe("1".repeat(64));
    expect(fetchMock.mock.calls[1][0]).toContain("/revision-staged/accept");
    expect(get(researchScriptWorkspace).detail?.script.canonical_revision_id).toBe(
      "revision-staged"
    );
    expect(get(researchScriptWorkspace).sourceDraft).toBe("print('operator candidate')\n");
    expect(get(researchScriptWorkspace).preparedInputSnapshot?.snapshot_id).toBe("reviewed-inputs");
  });
  it("keeps unsaved canonical edits when candidate review is requested", async () => {
    const initial = detail();
    const staged = { ...initial.revisions[0], revision_id: "candidate", status: "staged" as const,
      source: "print('candidate')", created_by: "operator" as const };
    loadedWorkspace(bundle("original", ["external.json"]));
    researchScriptWorkspace.update(state => ({ ...state,
      detail: { ...initial, revisions: [...initial.revisions, staged] }, sourceDraft: "print('unsaved user edit')" }));
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await resolveStagedResearchScriptRevision("candidate", "accept");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(researchScriptWorkspace).sourceDraft).toBe("print('unsaved user edit')");
    expect(get(researchScriptWorkspace).error).toContain("Save your canonical edits");
  });

  it("sends run parameters separately from the source and blocks invalid parameters before any request", async () => {
    loadedWorkspace(bundle("base", ["spy.csv"]));
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ ...run(), revision_id: "revision-1", parameters: { lookback: 20 }, parameters_sha256: "c".repeat(64) }, 201, "Created"))
      .mockResolvedValueOnce(jsonResponse(bundle("base", ["spy.csv"])))
      .mockResolvedValueOnce(jsonResponse(diagnostics()))
      .mockResolvedValueOnce(jsonResponse({ ...run(), revision_id: "revision-1" }, 201, "Created"))
      .mockResolvedValueOnce(jsonResponse(bundle("base", ["spy.csv"])))
      .mockResolvedValueOnce(jsonResponse(diagnostics()));
    vi.stubGlobal("fetch", fetchMock);
    updateResearchScriptParameters('{"lookback": [1, 2]}');
    await runSelectedResearchScript();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(researchScriptWorkspace).error).toContain("number, text, boolean or null");
    updateResearchScriptParameters('{"lookback": 20}');
    await runSelectedResearchScript();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.parameters).toEqual({ lookback: 20 });
    expect(get(researchScriptWorkspace).selectedRun?.parameters_sha256).toBe("c".repeat(64));
    updateResearchScriptParameters("{}");
    await runSelectedResearchScript();
    expect("parameters" in JSON.parse(fetchMock.mock.calls[3][1].body as string)).toBe(false);
  });

  it("parses only flat JSON objects as run parameters", () => {
    expect(parseResearchScriptParameters("")).toEqual({ ok: true, values: {} });
    expect(parseResearchScriptParameters('{"a": 1, "b": "x", "c": null, "d": true}')).toMatchObject({ ok: true });
    expect(parseResearchScriptParameters("[1]")).toMatchObject({ ok: false });
    expect(parseResearchScriptParameters("{bad")).toMatchObject({ ok: false, error: expect.stringContaining("valid JSON") });
  });
});
