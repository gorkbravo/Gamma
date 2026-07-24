import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FrontendQueryCache, stableQueryKey } from "./query-cache";
import { requestMetrics, resetRequestMetrics } from "./request-metrics";

describe("FrontendQueryCache", () => {
  beforeEach(() => resetRequestMetrics());

  it("normalizes parameter order and reuses fresh data", async () => {
    const cache = new FrontendQueryCache();
    const fetcher = vi.fn().mockResolvedValue({ value: 1 });
    const key = stableQueryKey("/example", { z: 2, a: 1 });
    expect(key).toBe(stableQueryKey("/example", { a: 1, z: 2 }));
    await cache.query({ scope: "example", key, staleTimeMs: 1000, fetcher });
    const cached = await cache.query({ scope: "example", key, staleTimeMs: 1000, fetcher });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(cached).toEqual({ value: 1 });
    expect(get(requestMetrics).totals.cache_hit).toBe(1);
  });

  it("keeps stale usable data when refresh fails", async () => {
    const cache = new FrontendQueryCache();
    const key = "/example";
    await cache.query({ scope: "example", key, staleTimeMs: 0, fetcher: async () => ({ value: 1, warnings: [] }) });
    const result = await cache.query<{ value: number; warnings: string[] }>({
      scope: "example",
      key,
      staleTimeMs: -1,
      forceRefresh: true,
      fetcher: async () => { throw new Error("provider unavailable"); }
    });
    expect(result.value).toBe(1);
    expect(result.warnings[0]).toContain("showing the most recent usable cached payload");
  });

  it("does not let an older scope request commit after latest-wins cancellation", async () => {
    const cache = new FrontendQueryCache();
    const committed: number[] = [];
    let resolveOld!: (value: { value: number }) => void;
    const old = cache.query<{ value: number }>({
      scope: "workspace",
      key: "/workspace?id=old",
      staleTimeMs: 0,
      fetcher: () => new Promise((resolve) => { resolveOld = resolve; }),
      onData: (data) => committed.push(data.value)
    });
    const latest = cache.query<{ value: number }>({
      scope: "workspace",
      key: "/workspace?id=new",
      staleTimeMs: 0,
      fetcher: async () => ({ value: 2 }),
      onData: (data) => committed.push(data.value)
    });
    resolveOld({ value: 1 });
    await Promise.allSettled([old, latest]);
    expect(committed).toEqual([2]);
  });
});
