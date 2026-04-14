import { afterEach, describe, expect, it, vi } from "vitest";

import { getJson, postJson } from "./client";

describe("api client errors", () => {
  afterEach(() => {
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
});
