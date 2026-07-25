import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CopilotArtifact,
  CopilotResearchCardResult,
  CopilotSessionDetail,
  CopilotSessionSummary
} from "../api/types";
import {
  activeCopilotArtifact,
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
