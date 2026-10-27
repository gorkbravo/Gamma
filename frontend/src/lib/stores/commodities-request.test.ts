import { get } from "svelte/store";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearFrontendQueryCache,
  commoditiesRequestedInstrumentId,
  commoditiesWorkspace,
  loadCommoditiesWorkspace,
  requestCommodityInstrument
} from "./app";

function ok(body: unknown) {
  return { ok: true, status: 200, statusText: "OK", async json() { return body; } };
}

function requestedInstrument(fetchMock: ReturnType<typeof vi.fn>, call = 0) {
  const init = fetchMock.mock.calls[call]?.[1] as RequestInit | undefined;
  return JSON.parse(String(init?.body ?? "{}")).selected_instrument_id;
}

describe("Commodities requested instrument (wrong-market header, 2026-10-21)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearFrontendQueryCache();
    commoditiesRequestedInstrumentId.set(null);
    commoditiesWorkspace.set(null);
  });

  it("loads the drilled instrument on tab open instead of the default WTI and clears the request after", async () => {
    let seenWhileLoading: string | null = null;
    const fetchMock = vi.fn(async () => {
      seenWhileLoading = get(commoditiesRequestedInstrumentId);
      return ok({ mode: "overview", selected_instrument_id: "brent" });
    });
    vi.stubGlobal("fetch", fetchMock);

    requestCommodityInstrument("Brent");
    await loadCommoditiesWorkspace({ mode: "overview" });

    expect(requestedInstrument(fetchMock)).toBe("brent");
    expect(seenWhileLoading).toBe("brent");
    expect(get(commoditiesRequestedInstrumentId)).toBeNull();
    expect(get(commoditiesWorkspace)?.selected_instrument_id).toBe("brent");
  });

  it("an explicit selection wins over a pending request", async () => {
    const fetchMock = vi.fn(async () => ok({ mode: "overview", selected_instrument_id: "gold" }));
    vi.stubGlobal("fetch", fetchMock);

    requestCommodityInstrument("brent");
    await loadCommoditiesWorkspace({ mode: "overview", selectedInstrumentId: "gold" });

    expect(requestedInstrument(fetchMock)).toBe("gold");
    expect(get(commoditiesRequestedInstrumentId)).toBeNull();
  });
});
