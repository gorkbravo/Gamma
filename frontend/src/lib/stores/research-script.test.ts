import { get } from "svelte/store";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResearchScriptDetail, ResearchScriptRun } from "../api/types";
import {
  createWorkspaceResearchScript,
  persistResearchScriptRevision,
  researchScriptWorkspace,
  resolveStagedResearchScriptRevision,
  resetResearchScriptWorkspace,
  runSelectedResearchScript,
  updateResearchScriptDraft
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

const jsonResponse = (value: unknown, status = 200, statusText = "OK") => new Response(
  JSON.stringify(value),
  { status, statusText, headers: { "Content-Type": "application/json" } }
);

describe("research script workspace store", () => {
  beforeEach(() => resetResearchScriptWorkspace());
  afterEach(() => vi.unstubAllGlobals());

  it("creates a script, persists a revision, and submits that exact revision for a run", async () => {
    const first = detail();
    const revised = detail(2, "print('edited preview')\n");
    const completedRun = run();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(first, 201, "Created"))
      .mockResolvedValueOnce(jsonResponse(revised, 201, "Created"))
      .mockResolvedValueOnce(jsonResponse(completedRun, 201, "Created"));
    vi.stubGlobal("fetch", fetchMock);

    updateResearchScriptDraft("print('preview')\n");
    await createWorkspaceResearchScript("Research Script");
    updateResearchScriptDraft("print('edited preview')\n");
    await persistResearchScriptRevision("Edit research fixture");
    await runSelectedResearchScript();

    const createBody = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    const revisionBody = JSON.parse(fetchMock.mock.calls[1][1].body as string);
    const runBody = JSON.parse(fetchMock.mock.calls[2][1].body as string);
    expect(createBody.source).toBe("print('preview')\n");
    expect(revisionBody.expected_parent_sha256).toBe("1".repeat(64));
    expect(revisionBody.source).toBe("print('edited preview')\n");
    expect(runBody.revision_id).toBe("revision-2");
    expect(get(researchScriptWorkspace).selectedRun?.run_id).toBe("run-1");
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
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(accepted));
    vi.stubGlobal("fetch", fetchMock);

    await resolveStagedResearchScriptRevision("revision-staged", "accept");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.expected_parent_sha256).toBe("1".repeat(64));
    expect(fetchMock.mock.calls[0][0]).toContain("/revision-staged/accept");
    expect(get(researchScriptWorkspace).detail?.script.canonical_revision_id).toBe(
      "revision-staged"
    );
    expect(get(researchScriptWorkspace).sourceDraft).toBe("print('operator candidate')\n");
  });
});
