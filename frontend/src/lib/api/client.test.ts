import { afterEach, describe, expect, it, vi } from "vitest";

import { API_BASE, SESSION_WS_SUBPROTOCOL, getBlob, getJson, postJson, sessionWebSocketProtocols } from "./client";

describe("sessionWebSocketProtocols", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("offers the session subprotocol and the token as base64url", () => {
    // Debe coincidir con la decodificación de src/api/session_auth.py.
    expect(sessionWebSocketProtocols("expected-session")).toEqual([
      SESSION_WS_SUBPROTOCOL,
      "gamma.session.token.ZXhwZWN0ZWQtc2Vzc2lvbg"
    ]);
  });

  it("produces a valid subprotocol token for any token text", () => {
    const [, tokenProtocol] = sessionWebSocketProtocols("<dev-only token> ñ/+=");
    expect(tokenProtocol).toMatch(/^gamma\.session\.token\.[A-Za-z0-9_-]+$/);
    const encoded = tokenProtocol.slice("gamma.session.token.".length).replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(encoded + "=".repeat((4 - (encoded.length % 4)) % 4)), (c) => c.charCodeAt(0));
    expect(new TextDecoder().decode(bytes)).toBe("<dev-only token> ñ/+=");
  });

  it("uses the runtime token injected by the desktop shell", () => {
    // El entorno de tests es node: se simula el window de la WebView de Tauri.
    vi.stubGlobal("window", { __GAMMA_SESSION_TOKEN__: "abc123" });
    expect(sessionWebSocketProtocols()).toEqual([SESSION_WS_SUBPROTOCOL, "gamma.session.token.YWJjMTIz"]);
  });
});

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
