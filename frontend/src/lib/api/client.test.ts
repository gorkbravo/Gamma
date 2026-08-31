import { afterEach, describe, expect, it, vi } from "vitest";

import { API_BASE, getBlob, getJson, postJson } from "./client";

describe("api client errors", () => {
  afterEach(() => {
    if (typeof window !== "undefined") {
      delete window.__GAMMA_SESSION_TOKEN__;
    }
    vi.unstubAllGlobals();
  });

  it("includes FastAPI JSON detail in failed GET requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Macro provider unavailable" }), {
          status: 503,
          statusText: "Service Unavailable",
          headers: { "Content-Type": "application/json" }
        })
      )
    );

    await expect(getJson("/macro/snapshot")).rejects.toThrow(
      "503 Service Unavailable: Macro provider unavailable"
    );
  });

  it("includes text response bodies in failed POST requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("bad request detail", {
          status: 400,
          statusText: "Bad Request",
          headers: { "Content-Type": "text/plain" }
        })
      )
    );

    await expect(postJson("/research/analyze", {})).rejects.toThrow(
      "400 Bad Request: bad request detail"
    );
  });

  it("sends the runtime Gamma session token with API requests", async () => {
    vi.stubGlobal("window", { __GAMMA_SESSION_TOKEN__: "runtime-session" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await postJson("/research/analyze", {});

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/research/analyze`,
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-Gamma-Session": "runtime-session"
        })
      })
    );
  });

  it("authenticates retained artifact downloads", async () => {
    vi.stubGlobal("window", { __GAMMA_SESSION_TOKEN__: "runtime-session" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("artifact-bytes", {
        status: 200,
        headers: { "Content-Type": "application/octet-stream" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const blob = await getBlob("/research/scripts/runs/run-1/outputs/chart.svg");

    expect(await blob.text()).toBe("artifact-bytes");
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/research/scripts/runs/run-1/outputs/chart.svg`,
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Gamma-Session": "runtime-session"
        })
      })
    );
  });
});
