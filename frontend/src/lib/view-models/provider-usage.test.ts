import { describe, expect, it } from "vitest";
import type { ProviderUsageResponse, ProviderUsageSummary } from "../api/types";
import { buildProviderHealthView, buildProviderUsageView, providerUsageRowDetail } from "./provider-usage";

function summary(provider_id: string, call_count: number, overrides: Partial<ProviderUsageSummary> = {}): ProviderUsageSummary {
  return {
    provider_id,
    call_count,
    success_count: call_count,
    unavailable_count: 0,
    error_count: 0,
    cache_hit_count: 0,
    cache_miss_count: 0,
    average_duration_ms: 12,
    last_status: "success",
    last_message: null,
    last_error: null,
    last_called_at: "2026-10-21T10:32:00Z",
    endpoints: [],
    ...overrides
  };
}

function usage(providers: ProviderUsageSummary[], overrides: Partial<ProviderUsageResponse> = {}): ProviderUsageResponse {
  return {
    generated_at: "2026-10-21T10:32:00Z",
    providers,
    health: [],
    recent_calls: [],
    total_calls: providers.reduce((sum, row) => sum + row.call_count, 0),
    source_provider: "gamma",
    origin: "provider_usage_ledger.snapshot",
    transformation_note: null,
    ...overrides
  };
}

describe("provider usage view (GUA-20260903-10)", () => {
  it("lists every provider, not just the four most recent, and the rows sum to the total", () => {
    const view = buildProviderUsageView(
      usage([
        summary("yfinance", 28),
        summary("ibkr", 98),
        summary("rss", 3),
        summary("unavailable_news", 3),
        summary("fred", 240, { success_count: 237, error_count: 3, http_request_count: 236 }),
        summary("treasury", 12),
        summary("polymarket", 40),
        summary("kalshi", 30),
        summary("eia", 26),
        summary("unattributed", 20)
      ])
    );

    expect(view.rows).toHaveLength(10);
    expect(view.total).toBe(500);
    expect(view.rowSum).toBe(500);
    expect(view.headline).toBe("500 calls");
    expect(view.failed).toBe(3);
    expect(view.rows[0].providerId).toBe("fred");
    expect(view.rows.at(-1)?.label).toBe("Unattributed");
    expect(view.rows.find((row) => row.providerId === "fred")?.tone).toBe("warning");
    expect(providerUsageRowDetail(view.rows[0])).toBe("237 ok · 3 failed · 236 HTTP · 12 ms avg");
  });

  it("never lets calls vanish: an unreconciled remainder becomes an unattributed row", () => {
    const view = buildProviderUsageView(usage([summary("ibkr", 98)], { total_calls: 132 }));

    expect(view.rowSum).toBe(132);
    expect(view.rows.map((row) => [row.label, row.calls])).toEqual([
      ["ibkr", 98],
      ["Unattributed", 34]
    ]);
  });

  it("explains a full retention window against the lifetime count", () => {
    const full = buildProviderUsageView(
      usage([summary("fred", 2000)], { lifetime_calls: 3456, retained_limit: 2000 })
    );
    expect(full.headline).toBe("2,000 calls");
    expect(full.windowNote).toBe("Last 2,000 of 3,456 calls since backend startup.");

    expect(buildProviderUsageView(usage([summary("fred", 3)], { lifetime_calls: 3 })).windowNote).toBeNull();
    expect(buildProviderUsageView(null).rows).toEqual([]);
  });

  it("lists every provider needing attention and summarizes the rest", () => {
    const health = buildProviderHealthView(
      usage([], {
        health: [
          {
            provider_id: "fred",
            display_name: "fred",
            health_status: "degraded",
            health_label: "Degraded",
            expected_when: "",
            reason: "HTTP 400 Bad Request from api.stlouisfed.org/fred/series/observations",
            action_label: null,
            call_count: 3,
            success_count: 0,
            unavailable_count: 0,
            error_count: 3,
            last_called_at: null
          },
          ...["yfinance", "ibkr"].map((provider_id) => ({
            provider_id,
            display_name: provider_id,
            health_status: "healthy",
            health_label: "Healthy",
            expected_when: "",
            reason: "",
            action_label: null,
            call_count: 1,
            success_count: 1,
            unavailable_count: 0,
            error_count: 0,
            last_called_at: null
          }))
        ]
      })
    );

    expect(health.attention.map((row) => row.provider_id)).toEqual(["fred"]);
    expect(health.summary).toBe("2 healthy");
  });
});
