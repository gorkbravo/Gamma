import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CopilotArtifact, CopilotSessionDetail, CopilotSessionSummary } from "../api/types";
import {
  activeCopilotArtifact,
  activeCopilotSession,
  archiveCopilotSession,
  copilotArtifactSaveState,
  copilotArtifacts,
  copilotSessions,
  createCopilotArtifact,
  deleteCopilotArtifact,
  deleteCopilotSession,
  duplicateCopilotArtifact,
  exportCopilotArtifact,
  loadActiveCopilotSession,
  loadCopilotSessions,
  renameCopilotSession,
  restoreCopilotSession,
  selectCopilotArtifact,
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
