import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import StatusRail from "./StatusRail.svelte";

describe("StatusRail", () => {
  it("renders compact provider usage diagnostics in settings", () => {
    const { body } = render(StatusRail, {
      props: {
        status: {
          healthy: true,
          app_name: "Gamma API",
          backend: "fastapi",
          mock_mode: true,
          base_currency: "USD",
          market_data_mode: "delayed",
          connection: {
            connected: true,
            status_text: "Status: Mock",
            action_text: "Mock Mode",
            action_enabled: false,
            active_account: "DU123"
          },
          cached_symbols: []
        },
        providerUsage: {
          generated_at: "2026-05-16T12:00:00Z",
          providers: [
            {
              provider_id: "mock",
              call_count: 4,
              success_count: 3,
              unavailable_count: 1,
              error_count: 0,
              cache_hit_count: 1,
              cache_miss_count: 2,
              average_duration_ms: 3.25,
              last_status: "success",
              last_message: null,
              last_error: null,
              last_called_at: "2026-05-16T12:00:00Z",
              endpoints: ["research_history.load_history"]
            }
          ],
          recent_calls: [],
          total_calls: 4,
          source_provider: "gamma",
          origin: "provider_usage_ledger.snapshot",
          transformation_note: "Fixture"
        },
        workspaceMode: "research",
        settingsOpen: true,
        onToggleConnection: vi.fn(),
        onBaseCurrencyChange: vi.fn(),
        onMarketDataModeChange: vi.fn(),
        onRefresh: vi.fn(),
        onChangeView: vi.fn()
      }
    });

    expect(body).toContain("Provider Usage");
    expect(body).toContain("mock");
    expect(body).toContain("4 calls");
    expect(body).toContain("3 ok");
    expect(body).toContain("1 unavailable");
  });
});
