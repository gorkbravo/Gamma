import { afterEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import type { DiagnosticsResponse } from "../api/types";
import { diagnostics, loadDiagnostics, systemStatus, toggleConnection } from "./system";

afterEach(() => {
  vi.unstubAllGlobals();
  systemStatus.set(null);
  diagnostics.set(null);
});

describe("system connection actions", () => {
  it("posts a desired connection state instead of a toggle request", async () => {
    systemStatus.set({
      healthy: true,
      app_name: "Gamma API",
      backend: "fastapi",
      mock_mode: false,
      base_currency: "USD",
      market_data_mode: "delayed",
      connection: {
        connected: false,
        status_text: "Status: Disconnected",
        action_text: "Connect to IBKR",
        action_enabled: true,
        active_account: null
      },
      cached_symbols: []
    });
    const nextStatus = {
      ...get(systemStatus)!,
      connection: {
        ...get(systemStatus)!.connection,
        connected: true,
        status_text: "Status: Connected",
        action_text: "Disconnect"
      }
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(nextStatus), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await toggleConnection();

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/system/connection");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      connected: true
    });
    expect(get(systemStatus)?.connection.connected).toBe(true);
  });

  it("returns an explicit diagnostics result so action feedback can distinguish failure", async () => {
    const payload = {
      generated_at: "2026-07-27T10:00:00Z",
      mock_mode: true
    } as unknown as DiagnosticsResponse;
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify(payload), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          })
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ detail: "unavailable" }), {
            status: 503,
            statusText: "Service Unavailable",
            headers: { "Content-Type": "application/json" }
          })
        )
    );

    await expect(loadDiagnostics()).resolves.toEqual(payload);
    await expect(loadDiagnostics()).resolves.toBeNull();
  });
});
