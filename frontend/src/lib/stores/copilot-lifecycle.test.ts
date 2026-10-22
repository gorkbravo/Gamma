import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CopilotArtifact,
  CopilotDraftMutation,
  CopilotResearchCardResult,
  CopilotSessionDetail,
  CopilotSessionSummary
} from "../api/types";
import {
  activeCopilotArtifact,
  confirmCopilotMutation,
  rejectCopilotMutation,
  cancelCopilotRun,
  copilotActiveRun,
  loading,
  copilotOperatorResult,
  activeCopilotSession,
  archiveCopilotSession,
  copilotArtifactSaveState,
  copilotArtifacts,
  copilotLastSubmission,
  copilotRunningSessionIds,
  copilotSessionCreateError,
  copilotSessionCreating,
  copilotSessions,
  copilotThreads,
  createCopilotArtifact,
  deleteCopilotArtifact,
  deleteCopilotSession,
  duplicateCopilotArtifact,
  exportCopilotArtifact,
  lastError,
  loadActiveCopilotSession,
  loadCopilotResearchCard,
  loadCopilotSession,
  loadCopilotSessions,
  renameCopilotSession,
  restoreCopilotSession,
  retryCopilotTurn,
  selectCopilotArtifact,
  startNewCopilotSession,
  updateCopilotArtifact
} from "./app";

function response(body: unknown, status = 200, contentType = "application/json") {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": contentType }
  });
}

function session(sessionId: string, overrides: Partial<CopilotSessionSummary> = {}): CopilotSessionSummary {
  return {
    session_id: sessionId,
    title: `Session ${sessionId}`,
    created_at: "2026-07-24T10:00:00Z",
    updated_at: "2026-07-24T10:00:01Z",
    active_domain: "macro",
    active_context_fingerprint: "fp-macro",
    turn_count: 1,
    memo_count: 0,
    report_count: 0,
    artifact_count: 0,
    warnings: [],
    archived_at: null,
    ...overrides
  };
}

function artifact(
  artifactId: string,
  sessionId: string,
  overrides: Partial<CopilotArtifact> = {}
): CopilotArtifact {
  return {
    artifact_id: artifactId,
    session_id: sessionId,
    artifact_type: "memo",
    template: "concise_memo",
    title: `Artifact ${artifactId}`,
    body: "# Memo",
    source_turn_ids: ["turn-1"],
    source_memo_ids: [],
    source_snapshot_ids: ["snapshot-1"],
    unavailable_source_turn_ids: [],
    context_fingerprints: ["fp-macro"],
    source_backed_claims: [],
    inferred_claims: [],
    assumptions: [],
    missing_data: [],
    warnings: [],
    warning_provenance: [],
    tool_trace_summary: [],
    sources: [],
    provider_metadata: [],
    created_at: "2026-07-24T10:00:02Z",
    updated_at: "2026-07-24T10:00:02Z",
    source_provider: "gamma_copilot",
    origin: "test",
    transformation_note: "test",
    ...overrides
  };
}

function detail(
  summary: CopilotSessionSummary,
  artifacts: CopilotArtifact[] = []
): CopilotSessionDetail {
  return {
    session: { ...summary, artifact_count: artifacts.length },
    turns: [],
    memos: [],
    context_snapshots: [],
    artifacts,
    storage_warnings: []
  };
}

function cardResult(responseId: string, status: CopilotResearchCardResult["status"] = "ready"): CopilotResearchCardResult {
  return {
    domain: "macro",
    current_tab: "macro",
    status,
    provider: "openai_responses",
    model: "gpt-5.5",
    response_id: responseId,
    message: status === "ready" ? null : "The configured OpenAI account has no remaining quota.",
    card: null,
    sources: [],
    tool_traces: [],
    operator_events: [],
    warnings: []
  };
}

function ndjson(lines: unknown[]) {
  return new Response(lines.map((line) => JSON.stringify(line)).join("\n") + "\n", {
    status: 200,
    headers: { "content-type": "application/x-ndjson" }
  });
}

function runStream(result: CopilotResearchCardResult, init: RequestInit | undefined) {
  const payload = JSON.parse(String(init?.body ?? "{}")) as { run_id?: string };
  const runId = payload.run_id ?? "run_test";
  return ndjson([
    {
      run_id: runId,
      sequence: 0,
      event: "run.created",
      timestamp: "2026-07-25T10:00:00Z",
      data: { domain: "macro", provider: result.provider, model: result.model },
      result: null
    },
    {
      run_id: runId,
      sequence: 1,
      event: result.status === "ready" ? "completed" : "failed",
      timestamp: "2026-07-25T10:00:02Z",
      data: { status: result.status },
      result
    }
  ]);
}

describe("Copilot checkpoint 3 lifecycle stores", () => {
  const localValues = new Map<string, string>();

  beforeEach(() => {
    vi.unstubAllGlobals();
    localValues.clear();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => localValues.get(key) ?? null,
      setItem: (key: string, value: string) => localValues.set(key, value),
      removeItem: (key: string) => localValues.delete(key)
    });
    localStorage.setItem("gamma.copilot.session", "stale-session");
    copilotSessions.set([]);
    activeCopilotSession.set(null);
    copilotArtifacts.set([]);
    activeCopilotArtifact.set(null);
    copilotArtifactSaveState.set("idle");
    copilotRunningSessionIds.set([]);
    copilotLastSubmission.set(null);
    copilotSessionCreateError.set(null);
    copilotSessionCreating.set(false);
    lastError.set("");
  });

  it("reconciles a stale selected session to the authoritative active result", async () => {
    const fallback = session("fallback-session");
    const fallbackArtifact = artifact("artifact-fallback", fallback.session_id);
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/copilot/sessions/stale-session")) {
        return Promise.resolve(response({ detail: "not found" }, 404));
      }
      if (url.pathname.endsWith("/copilot/sessions")) {
        return Promise.resolve(response([fallback]));
      }
      if (url.pathname.endsWith("/copilot/sessions/fallback-session")) {
        return Promise.resolve(response(detail(fallback, [fallbackArtifact])));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const loaded = await loadActiveCopilotSession();

    expect(loaded?.session.session_id).toBe("fallback-session");
    expect(get(activeCopilotSession)?.session.session_id).toBe("fallback-session");
    expect(get(activeCopilotArtifact)?.artifact_id).toBe("artifact-fallback");
    expect(localStorage.getItem("gamma.copilot.session")).toBe("fallback-session");
  });

  it.each(["research_agent", "research_operator"])("retries a persisted %s request with its original Options evidence and authority", async (role) => {
    const summary = session("retry-options", { active_domain: "iv" });
    localStorage.setItem("gamma.copilot.session", summary.session_id);
    const retained = detail(summary);
    const context = { current_tab: "iv", workspace_mode: "research", iv_state: {
      surface: { symbol: "GOOGL", timestamp: "2026-09-03T12:00:00Z" },
      workbench: { selected_expiry: "20261120", legs: [{ strike: 340, premium: 18 }], detached: true }
    } };
    retained.turns = [{ turn_id: "failed-options", session_id: summary.session_id, domain: "iv",
      prompt: "Evaluate my exact 340/315 put spread", role, selected_scope_domains: ["iv"],
      selected_profile: "quick", context_snapshot_id: "snapshot-options", context_fingerprint: "original-options",
      result: { ...cardResult("failed-response", "error"), domain: "iv" }
    }] as CopilotSessionDetail["turns"];
    retained.context_snapshots = [{ snapshot_id: "snapshot-options", context_fingerprint: "original-options",
      domain: "iv", current_tab: "iv", workspace_mode: "research", summary: {}, source_ids: [], warnings: [],
      created_at: "2026-09-03T12:00:00Z", read_only_safety: {}, context_contract: {},
      request_context: { context, synthesis: null }, selected_scope_domains: ["iv"]
    }];
    activeCopilotSession.set(retained);
    const requests: Array<{ path: string; payload: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
      const path = new URL(input).pathname;
      if (path.endsWith("/stream")) {
        requests.push({ path, payload: JSON.parse(String(init?.body)) });
        return runStream({ ...cardResult("retry-response"), domain: "iv" }, init);
      }
      if (path.endsWith("/copilot/sessions")) return response([summary]);
      return response(retained);
    }));
    await retryCopilotTurn("failed-options");
    expect(requests).toHaveLength(1);
    expect(requests[0].path).toContain(role === "research_operator" ? "operator-plan/execute" : "research-card");
    expect(requests[0].payload).toMatchObject({ role, prompt: retained.turns[0].prompt,
      context_fingerprint: "original-options", selected_scope_domains: ["iv"], selected_profile: "quick", context });
  });

  it("continues an output-budget cut-off with the original prompt, context and an expanded budget (GUA-20261021-6)", async () => {
    const summary = session("retry-budget", { active_domain: "synthesis" });
    localStorage.setItem("gamma.copilot.session", summary.session_id);
    const retained = detail(summary);
    const context = { current_tab: "synthesis", workspace_mode: "research" };
    const synthesis = { active_tab: "copilot", included_scopes: [
      { domain: "commodities", label: "Commodities", context_fingerprint: "c1",
        context: { current_tab: "commodities", commodities_state: { workspace: null, viewed_instrument_ids: ["brent", "wti"] } } },
      { domain: "risk", label: "Risk", context_fingerprint: "r1", context: { current_tab: "risk" } }
    ] };
    retained.turns = [{ turn_id: "cut-turn", session_id: summary.session_id, domain: "synthesis",
      prompt: "Four-part Brent/WTI synthesis", role: "research_agent", selected_scope_domains: ["commodities", "risk"],
      selected_profile: "auto", context_snapshot_id: "snapshot-cut", context_fingerprint: "original-synthesis",
      result: { ...cardResult("cut-response", "incomplete"), message: "OpenAI ended the response early: max_output_tokens." }
    }] as CopilotSessionDetail["turns"];
    retained.context_snapshots = [{ snapshot_id: "snapshot-cut", context_fingerprint: "original-synthesis",
      domain: "synthesis", current_tab: "synthesis", workspace_mode: "research", summary: {}, source_ids: [], warnings: [],
      created_at: "2026-10-21T10:40:00Z", read_only_safety: {}, context_contract: {},
      request_context: { context, synthesis }, selected_scope_domains: ["commodities", "risk"]
    }];
    activeCopilotSession.set(retained);
    const requests: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
      const path = new URL(input).pathname;
      if (path.endsWith("/stream")) {
        requests.push(JSON.parse(String(init?.body)));
        return runStream({ ...cardResult("continued-response"), domain: "synthesis" }, init);
      }
      if (path.endsWith("/copilot/sessions")) return response([summary]);
      return response(retained);
    }));
    await retryCopilotTurn("cut-turn");
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      prompt: "Four-part Brent/WTI synthesis",
      output_budget: "expanded",
      context_fingerprint: "original-synthesis",
      context,
      synthesis
    });
  });

  it("refuses retry when the original context snapshot is missing", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(await retryCopilotTurn("missing-turn")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(lastError)).toContain("original request context is unavailable");
  });

  it("keeps selected-session continuity through search, rename, archive, and restore", async () => {
    const initial = session("session-a");
    activeCopilotSession.set(detail(initial));
    copilotSessions.set([initial]);
    localStorage.setItem("gamma.copilot.session", initial.session_id);
    const renamed = session("session-a", {
      title: "Renamed session",
      updated_at: "2026-07-24T10:00:03Z"
    });
    const archived = { ...renamed, archived_at: "2026-07-24T10:00:04Z" };
    const restored = { ...archived, archived_at: null, updated_at: "2026-07-24T10:00:05Z" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response([initial]))
      .mockResolvedValueOnce(response(renamed))
      .mockResolvedValueOnce(response(archived))
      .mockResolvedValueOnce(response(restored));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotSessions({ search: "Renamed", includeArchived: true });
    await renameCopilotSession(initial.session_id, "Renamed session", initial.updated_at);
    await archiveCopilotSession(initial.session_id);
    await restoreCopilotSession(initial.session_id);

    expect(get(activeCopilotSession)?.session).toEqual(restored);
    expect(localStorage.getItem("gamma.copilot.session")).toBe("session-a");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("search=Renamed");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      title: "Renamed session",
      expected_updated_at: initial.updated_at
    });
  });

  it("creates, autosaves, duplicates, exports, and deletes artifacts from authoritative responses", async () => {
    const summary = session("session-artifacts");
    const created = artifact("memo-created", summary.session_id);
    const edited = {
      ...created,
      title: "Edited memo",
      body: "# Edited",
      updated_at: "2026-07-24T10:00:03Z"
    };
    const duplicated = artifact("memo-copy", summary.session_id, {
      title: "Edited memo copy",
      source_turn_ids: created.source_turn_ids
    });
    activeCopilotSession.set(detail(summary));
    copilotSessions.set([summary]);
    localStorage.setItem("gamma.copilot.session", summary.session_id);
    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/copilot/sessions/session-artifacts/artifacts") && init?.method === "POST") {
        return Promise.resolve(response(created));
      }
      if (url.pathname.endsWith("/copilot/sessions/session-artifacts")) {
        const nextArtifacts = get(copilotArtifacts).some((item) => item.artifact_id === duplicated.artifact_id)
          ? [created, duplicated]
          : [created];
        return Promise.resolve(response(detail(summary, nextArtifacts)));
      }
      if (url.pathname.endsWith("/copilot/artifacts/memo-created") && init?.method === "PATCH") {
        return Promise.resolve(response(edited));
      }
      if (url.pathname.endsWith("/copilot/artifacts/memo-created/duplicate")) {
        copilotArtifacts.update((items) => [...items, duplicated]);
        return Promise.resolve(response(duplicated));
      }
      if (url.pathname.endsWith("/copilot/artifacts/memo-created/export")) {
        return Promise.resolve(response("# Exported memo", 200, "text/markdown"));
      }
      if (url.pathname.endsWith("/copilot/artifacts/memo-copy") && init?.method === "DELETE") {
        return Promise.resolve(response({
          deleted_id: duplicated.artifact_id,
          deleted_type: "artifact",
          recoverable: true,
          archived_path: "trash/memo-copy",
          deleted_counts: { artifacts: 1 }
        }));
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await createCopilotArtifact({
      artifactType: "memo",
      template: "concise_memo",
      sourceTurnIds: ["turn-1"]
    });
    expect(get(activeCopilotArtifact)?.artifact_id).toBe("memo-created");

    await updateCopilotArtifact(created.artifact_id, {
      title: "Edited memo",
      body: "# Edited",
      expectedUpdatedAt: created.updated_at
    });
    expect(get(copilotArtifactSaveState)).toBe("saved");
    expect(get(activeCopilotArtifact)?.body).toBe("# Edited");

    await duplicateCopilotArtifact(created.artifact_id, "Edited memo copy");
    selectCopilotArtifact(duplicated.artifact_id);
    expect(get(activeCopilotArtifact)?.artifact_id).toBe("memo-copy");
    expect(await exportCopilotArtifact(created.artifact_id)).toBe("# Exported memo");
    await deleteCopilotArtifact(duplicated.artifact_id);
    expect(get(copilotArtifacts).some((item) => item.artifact_id === duplicated.artifact_id)).toBe(false);
  });

  it("reconciles selection after a confirmed session deletion", async () => {
    const selected = session("session-selected");
    const fallback = session("session-fallback");
    copilotSessions.set([selected, fallback]);
    activeCopilotSession.set(detail(selected));
    localStorage.setItem("gamma.copilot.session", selected.session_id);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({
        deleted_id: selected.session_id,
        deleted_type: "session",
        recoverable: true,
        archived_path: "trash/session-selected",
        deleted_counts: { sessions: 1 }
      }))
      .mockResolvedValueOnce(response(detail(fallback)));
    vi.stubGlobal("fetch", fetchMock);

    await deleteCopilotSession(selected.session_id);

    expect(get(activeCopilotSession)?.session.session_id).toBe(fallback.session_id);
    expect(localStorage.getItem("gamma.copilot.session")).toBe(fallback.session_id);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "confirm_session_id=session-selected"
    );
  });

  it("surfaces autosave failure and clears it after an authoritative retry", async () => {
    const summary = session("session-retry");
    const original = artifact("memo-retry", summary.session_id);
    const recovered = {
      ...original,
      body: "# Recovered",
      updated_at: "2026-07-24T10:00:05Z"
    };
    copilotArtifacts.set([original]);
    activeCopilotArtifact.set(original);
    activeCopilotSession.set(detail(summary, [original]));
    localStorage.setItem("gamma.copilot.session", summary.session_id);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ detail: "disk unavailable" }, 500))
      .mockResolvedValueOnce(response(detail(summary, [original])))
      .mockResolvedValueOnce(response(recovered));
    vi.stubGlobal("fetch", fetchMock);

    const failed = await updateCopilotArtifact(original.artifact_id, {
      body: "# Recovered",
      expectedUpdatedAt: original.updated_at
    });
    expect(failed).toBeNull();
    expect(get(copilotArtifactSaveState)).toBe("error");
    expect(get(activeCopilotArtifact)?.body).toBe(original.body);

    const retried = await updateCopilotArtifact(original.artifact_id, {
      body: "# Recovered",
      expectedUpdatedAt: original.updated_at
    });
    expect(retried?.body).toBe("# Recovered");
    expect(get(copilotArtifactSaveState)).toBe("saved");
    expect(get(activeCopilotArtifact)?.updated_at).toBe(recovered.updated_at);
  });
});

describe("Copilot new chat", () => {
  const localValues = new Map<string, string>();

  beforeEach(() => {
    vi.unstubAllGlobals();
    localValues.clear();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => localValues.get(key) ?? null,
      setItem: (key: string, value: string) => localValues.set(key, value),
      removeItem: (key: string) => localValues.delete(key)
    });
    copilotSessions.set([]);
    activeCopilotSession.set(null);
    copilotArtifacts.set([]);
    activeCopilotArtifact.set(null);
    copilotArtifactSaveState.set("idle");
    copilotRunningSessionIds.set([]);
    copilotLastSubmission.set(null);
    copilotSessionCreateError.set(null);
    copilotSessionCreating.set(false);
    lastError.set("");
  });

  it("creates and selects an authoritative blank session while another unarchived session exists", async () => {
    const existing = session("session-existing");
    const blank = session("session-blank", {
      title: "New Copilot Session",
      turn_count: 0,
      active_domain: null,
      active_context_fingerprint: null
    });
    copilotSessions.set([existing]);
    activeCopilotSession.set(detail(existing));
    localStorage.setItem("gamma.copilot.session", existing.session_id);
    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/copilot/sessions") && init?.method === "POST") {
        return Promise.resolve(response(blank));
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const created = await startNewCopilotSession();

    expect(created?.session_id).toBe("session-blank");
    expect(localStorage.getItem("gamma.copilot.session")).toBe("session-blank");
    expect(get(activeCopilotSession)?.session.session_id).toBe("session-blank");
    expect(get(activeCopilotSession)?.turns).toEqual([]);
    expect(get(copilotArtifacts)).toEqual([]);
    expect(get(activeCopilotArtifact)).toBeNull();
    expect(get(copilotThreads).synthesis.entries).toEqual([]);
    // The previous conversation stays available as an inactive session.
    expect(get(copilotSessions).map((item) => item.session_id)).toEqual([
      "session-blank",
      "session-existing"
    ]);
    expect(get(copilotSessionCreateError)).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates exactly one blank session when new chat is activated twice", async () => {
    const blank = session("session-blank", { turn_count: 0 });
    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/copilot/sessions") && init?.method === "POST") {
        return Promise.resolve(response(blank));
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const [first, second] = await Promise.all([startNewCopilotSession(), startNewCopilotSession()]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first?.session_id).toBe("session-blank");
    expect(second?.session_id).toBe("session-blank");
    expect(get(copilotSessions).filter((item) => item.session_id === "session-blank")).toHaveLength(1);
    expect(get(copilotSessionCreating)).toBe(false);
  });

  it("reports an honest error and keeps the current selection when creation fails", async () => {
    const existing = session("session-existing");
    copilotSessions.set([existing]);
    activeCopilotSession.set(detail(existing));
    localStorage.setItem("gamma.copilot.session", existing.session_id);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ detail: "Copilot persistence is not configured." }, 400))
    );

    const created = await startNewCopilotSession();

    expect(created).toBeNull();
    expect(get(copilotSessionCreateError)).toContain("Copilot persistence is not configured.");
    expect(get(copilotSessionCreating)).toBe(false);
    expect(localStorage.getItem("gamma.copilot.session")).toBe("session-existing");
    expect(get(activeCopilotSession)?.session.session_id).toBe("session-existing");
  });

  it("stays on an honest empty workspace when nothing is selected and no session exists", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/copilot/sessions")) {
        return Promise.resolve(response([]));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const loaded = await loadActiveCopilotSession();

    expect(loaded).toBeNull();
    expect(get(activeCopilotSession)).toBeNull();
    expect(get(lastError)).toBe("");
    // No id is invented for a workspace the user has not started yet.
    expect(localStorage.getItem("gamma.copilot.session")).toBeNull();
  });

  it("drops the previous conversation's in-memory thread when another session is selected", async () => {
    const previous = session("session-previous");
    const target = session("session-target");
    copilotSessions.set([previous, target]);
    localStorage.setItem("gamma.copilot.session", previous.session_id);
    copilotThreads.update((current) => ({
      ...current,
      macro: {
        domain: "macro",
        contextFingerprint: "fp-macro",
        latestResponseId: "resp_previous",
        entries: [
          {
            entryId: "entry-previous",
            turnIndex: 1,
            prompt: "Belongs to the previous conversation.",
            continuedFromResponseId: null,
            result: cardResult("resp_previous")
          }
        ]
      }
    }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detail(target))));

    await loadCopilotSession(target.session_id, { makeActive: true });

    // Threads are conversation-scoped; the newly selected session renders from
    // its own persisted turns instead of inheriting the previous transcript.
    expect(get(copilotThreads).macro.entries).toEqual([]);
    expect(get(copilotThreads).synthesis.entries).toEqual([]);
    expect(get(activeCopilotSession)?.session.session_id).toBe("session-target");
    expect(get(copilotLastSubmission)).toBeNull();
  });

  it("keeps the in-memory thread when the already-selected session is reloaded", async () => {
    const selected = session("session-selected");
    localStorage.setItem("gamma.copilot.session", selected.session_id);
    copilotThreads.update((current) => ({
      ...current,
      macro: {
        domain: "macro",
        contextFingerprint: "fp-macro",
        latestResponseId: "resp_live",
        entries: [
          {
            entryId: "entry-live",
            turnIndex: 1,
            prompt: "Still the selected conversation.",
            continuedFromResponseId: null,
            result: cardResult("resp_live")
          }
        ]
      }
    }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detail(selected))));

    await loadCopilotSession(selected.session_id, { makeActive: true });

    expect(get(copilotThreads).macro.entries).toHaveLength(1);
  });

  it("adopts the newest unarchived session when nothing has been selected yet", async () => {
    const archived = session("session-archived", { archived_at: "2026-07-24T09:00:00Z" });
    const newest = session("session-newest");
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/copilot/sessions")) {
        return Promise.resolve(response([archived, newest]));
      }
      if (url.pathname.endsWith("/copilot/sessions/session-newest")) {
        return Promise.resolve(response(detail(newest)));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const loaded = await loadActiveCopilotSession();

    expect(loaded?.session.session_id).toBe("session-newest");
    expect(localStorage.getItem("gamma.copilot.session")).toBe("session-newest");
  });
});

describe("Copilot composer submission acceptance", () => {
  const localValues = new Map<string, string>();

  beforeEach(() => {
    vi.unstubAllGlobals();
    localValues.clear();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => localValues.get(key) ?? null,
      setItem: (key: string, value: string) => localValues.set(key, value),
      removeItem: (key: string) => localValues.delete(key)
    });
    localStorage.setItem("gamma.copilot.session", "session-run");
    copilotSessions.set([]);
    activeCopilotSession.set(null);
    copilotRunningSessionIds.set([]);
    copilotLastSubmission.set(null);
    copilotThreads.update((current) => ({ ...current, macro: { ...current.macro, entries: [] } }));
    lastError.set("");
  });

  it("marks an accepted agent submission even when the run ends in a quota error", async () => {
    const quotaResult = cardResult("resp_quota", "error");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url, init) => Promise.resolve(runStream(quotaResult, init)))
    );

    const settled = await loadCopilotResearchCard("macro", "Map the active macro setup.");

    expect(settled?.status).toBe("error");
    const submission = get(copilotLastSubmission);
    expect(submission?.accepted).toBe(true);
    expect(submission?.rejectedReason).toBeNull();
    expect(submission?.prompt).toBe("Map the active macro setup.");
    expect(submission?.role).toBe("research_agent");
    expect(submission?.sessionId).toBe("session-run");
    // The persisted turn keeps the prompt reachable through Retry.
    expect(get(copilotThreads).macro.entries.at(-1)?.prompt).toBe("Map the active macro setup.");
    expect(get(copilotRunningSessionIds)).toEqual([]);
  });

  it("does not accept a submission the server never acknowledged", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Failed to fetch")));

    await loadCopilotResearchCard("macro", "Map the active macro setup.");

    const submission = get(copilotLastSubmission);
    expect(submission?.accepted).toBe(false);
    expect(submission?.rejectedReason).toContain("Failed to fetch");
    expect(get(copilotRunningSessionIds)).toEqual([]);
  });

  it("keeps a running indicator on the source session and never cancels it on switch", async () => {
    const other = session("session-other");
    const result = cardResult("resp_switch");
    const terminal: { release: (() => void) | null } = { release: null };
    const encoder = new TextEncoder();
    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/copilot/research-card/stream")) {
        const payload = JSON.parse(String(init?.body ?? "{}")) as { run_id: string };
        let stage = 0;
        const body = new ReadableStream<Uint8Array>({
          pull(controller) {
            if (stage === 0) {
              stage = 1;
              controller.enqueue(
                encoder.encode(
                  JSON.stringify({
                    run_id: payload.run_id,
                    sequence: 0,
                    event: "run.created",
                    timestamp: "2026-07-25T10:00:00Z",
                    data: { domain: "macro", provider: "openai_responses" },
                    result: null
                  }) + "\n"
                )
              );
              return;
            }
            return new Promise<void>((resolve) => {
              terminal.release = () => {
                controller.enqueue(
                  encoder.encode(
                    JSON.stringify({
                      run_id: payload.run_id,
                      sequence: 1,
                      event: "completed",
                      timestamp: "2026-07-25T10:00:02Z",
                      data: { status: "ready" },
                      result
                    }) + "\n"
                  )
                );
                controller.close();
                resolve();
              };
            });
          }
        });
        return Promise.resolve(new Response(body, { status: 200 }));
      }
      if (url.pathname.endsWith("/copilot/sessions/session-other")) {
        return Promise.resolve(response(detail(other)));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const running = loadCopilotResearchCard("macro", "Keep streaming while I switch.");
    await vi.waitFor(() => expect(get(copilotRunningSessionIds)).toEqual(["session-run"]));
    await vi.waitFor(() => expect(get(copilotLastSubmission)?.accepted).toBe(true));

    await loadCopilotSession("session-other", { makeActive: true });
    // Switching conversations must not cancel the server-owned run.
    expect(get(copilotRunningSessionIds)).toEqual(["session-run"]);
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes("/cancel"))
    ).toBe(false);

    terminal.release?.();
    await running;

    expect(get(copilotRunningSessionIds)).toEqual([]);
    // The settled turn belongs to its own session, not the one now on screen.
    expect(get(copilotThreads).macro.entries).toEqual([]);
  });
});


it.each(["pending", "applied"])("continues %s approvals with the original run and explicit Operator role", async (status) => {
  const summary = session("session9");
  localStorage.setItem("gamma.copilot.session", "session9");
  activeCopilotSession.set(detail(summary));
  const requests: Array<{url: string; body: Record<string, unknown>}> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/runs/run9/decision/stream")) {
      requests.push({ url, body: JSON.parse(String(init?.body)) });
      return ndjson([
        { run_id: "run9", sequence: 9, event: "run.resumed", data: {}, timestamp: "2026-10-04T12:00:00Z" },
        { run_id: "run9", sequence: 10, event: "completed", data: {}, result: cardResult("response9"), timestamp: "2026-10-04T12:00:01Z" }
      ]);
    }
    if (url.includes("/sessions/session9")) return response(detail(summary));
    return response([summary]);
  }));
  const mutation = { mutation_id:"mutation9", run_id:"run9", workflow_id:"run9", session_id:"session9",
    confirmation_token:"token9", context_fingerprint:"fingerprint9", proposal_hash:"hash9", status } as CopilotDraftMutation;
  await confirmCopilotMutation(mutation);
  expect(requests).toHaveLength(1);
  expect(requests[0].body).toEqual({ mutation_id:"mutation9", user_session_id:"session9", role:"research_operator",
    decision:status === "pending" ? "approve" : "recover", confirmation_token:"token9",
    context_fingerprint:"fingerprint9", proposal_hash:"hash9" });
  expect(get(copilotOperatorResult)?.response_id).toBe("response9");
});

it.each(["approve", "reject"])("tracks %s continuation, Stop and session ownership without a new submission", async (decision) => {
  const summary = session("session9");
  localStorage.setItem("gamma.copilot.session", "session9");
  activeCopilotSession.set(detail(summary));
  const originalSubmission = get(copilotLastSubmission);
  let finish!: (value: Response) => void;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/decision/stream")) return new Promise<Response>((resolve) => { finish = resolve; });
    if (url.endsWith("/cancel")) return response({ run_id: "run9", cancelled: true });
    if (url.includes("/sessions/other")) return response(detail(session("other")));
    return response([summary]);
  });
  vi.stubGlobal("fetch", fetchMock);
  const mutation = { mutation_id: "mutation9", run_id: "run9", workflow_id: "run9", session_id: "session9", status: "pending" } as CopilotDraftMutation;
  const continuation = decision === "approve" ? confirmCopilotMutation(mutation) : rejectCopilotMutation(mutation);
  expect(get(loading).copilot).toBe(true);
  expect(get(copilotRunningSessionIds)).toContain("session9");
  expect(get(copilotActiveRun)?.runId).toBe("run9");
  await cancelCopilotRun();
  expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/runs/run9/cancel"))).toBe(true);
  const otherResult = cardResult("other-response");
  copilotOperatorResult.set(otherResult);
  localStorage.setItem("gamma.copilot.session", "other");
  activeCopilotSession.set(detail(session("other")));
  finish(ndjson([{ run_id: "run9", sequence: 12, event: "cancelled", data: {}, timestamp: "2026-10-04T12:00:01Z", result: cardResult("response9", "cancelled") }]));
  await continuation;
  expect(get(copilotOperatorResult)).toEqual(otherResult);
  expect(get(copilotLastSubmission)).toEqual(originalSubmission);
  expect(get(copilotRunningSessionIds)).not.toContain("session9");
  expect(get(copilotActiveRun)).toBeNull();
  expect(get(loading).copilot).toBe(false);
});

it("reconnects approval by event cursor without resubmitting its decision", async () => {
  localStorage.setItem("gamma.copilot.session", "session9");
  activeCopilotSession.set(detail(session("session9")));
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input); urls.push(url);
    if (url.endsWith("/decision/stream")) return ndjson([{ run_id: "run9", sequence: 9, event: "run.resumed", data: {}, timestamp: "2026-10-04T12:00:00Z" }]);
    if (url.includes("/events?after_sequence=9")) return ndjson([{ run_id: "run9", sequence: 10, event: "completed", data: {}, result: cardResult("response9"), timestamp: "2026-10-04T12:00:01Z" }]);
    if (url.includes("/sessions/session9")) return response(detail(session("session9")));
    return response([session("session9")]);
  }));
  await confirmCopilotMutation({ mutation_id: "mutation9", run_id: "run9", workflow_id: "run9", session_id: "session9", status: "applied" } as CopilotDraftMutation);
  expect(urls.filter(url => url.endsWith("/decision/stream"))).toHaveLength(1);
  expect(urls.some(url => url.includes("/events?after_sequence=9"))).toBe(true);
  expect(get(copilotOperatorResult)?.response_id).toBe("response9");
});

it("keeps persisted interrupted approval after reconnect exhaustion", async () => {
  localStorage.setItem("gamma.copilot.session", "session9");
  const persisted = { ...detail(session("session9")), turns: [{ turn_id: "original", result: cardResult("response9", "interrupted") }] } as CopilotSessionDetail;
  activeCopilotSession.set(persisted);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/runs/")) throw new Error("Transport unavailable");
    if (url.includes("/sessions/session9")) return response(persisted);
    return response([persisted.session]);
  }));
  expect(await confirmCopilotMutation({ mutation_id: "mutation9", run_id: "run9", workflow_id: "run9", session_id: "session9", status: "applied" } as CopilotDraftMutation)).toBeNull();
  expect(get(activeCopilotSession)?.turns[0].turn_id).toBe("original");
  expect(get(lastError)).toContain("Transport unavailable");
  expect(get(loading).copilot).toBe(false);
  expect(get(copilotActiveRun)).toBeNull();
});

it("reconnects after initial decision transport loss past the original pause cursor", async () => {
  localStorage.setItem("gamma.copilot.session", "session9");
  activeCopilotSession.set(detail(session("session9")));
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input); urls.push(url);
    if (url.includes("/recovery?")) return response({ last_sequence: 8, status: "awaiting_confirmation" });
    if (url.endsWith("/decision/stream")) throw new Error("Connection lost before first event");
    if (url.includes("/events?after_sequence=8")) return ndjson([
      { run_id: "run9", sequence: 9, event: "run.resumed", data: {}, timestamp: "2026-10-04T12:00:00Z" },
      { run_id: "run9", sequence: 10, event: "completed", data: {}, result: cardResult("response9"), timestamp: "2026-10-04T12:00:01Z" }
    ]);
    if (url.includes("/sessions/session9")) return response(detail(session("session9")));
    return response([session("session9")]);
  }));
  await confirmCopilotMutation({ mutation_id: "mutation9", run_id: "run9", workflow_id: "run9", session_id: "session9", status: "pending" } as CopilotDraftMutation);
  expect(urls.filter(url => url.endsWith("/decision/stream"))).toHaveLength(1);
  expect(urls.some(url => url.includes("/events?after_sequence=8"))).toBe(true);
  expect(get(copilotOperatorResult)?.response_id).toBe("response9");
});

it("refuses a new-run Retry for an interrupted approval", async () => {
  const summary = session("session9");
  const result = cardResult("response9", "interrupted");
  result.operator_events = [{ payload: { mutation: { run_id: "run9", workflow_id: "run9" } } }] as unknown as CopilotResearchCardResult["operator_events"];
  activeCopilotSession.set({ ...detail(summary), turns: [{ turn_id: "turn9", result }] } as CopilotSessionDetail);
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  expect(await retryCopilotTurn("turn9")).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(get(lastError)).toContain("original approval run");
});
