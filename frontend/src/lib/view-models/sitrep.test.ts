import { describe, expect, it } from "vitest";
import {
  buildSitrepFollowUpCreatePayload,
  findSitrepFollowUpByRow,
  formatSitrepSectionAge,
  formatNewsReliabilityLabel,
  formatSitrepWindowLabel,
  isSitrepFollowUpSaved,
  oldestSitrepSection,
  parseSitrepFollowUps,
  removeSitrepFollowUp,
  resolveSitrepNewsEntityHandoff,
  resolveSitrepMarketHandoff,
  resolveSitrepTapeHandoff,
  type SitrepFollowUp,
  type SitrepHandoffRequest,
  type SitrepMarketHandoffProfile,
  type SitrepMarketHandoffRow,
  type SitrepTapeHandoffRow,
} from "./sitrep";

describe("sitrep handoff view model", () => {
  it.each<[SitrepMarketHandoffProfile, SitrepMarketHandoffRow, Partial<SitrepHandoffRequest>]>([
    [
      "indices",
      {
        id: "idx-n225",
        symbol: "^N225",
        proxySymbol: "EWJ",
        proxyLabel: "Japan ETF proxy",
        label: "Nikkei 225",
        group: "Japan",
        last: "69360.88",
        change: "-3000.00",
        secondary: "EWJ / Jun 26",
      },
      { targetTab: "equity_research", targetMode: "scope_analysis", symbol: "EWJ", label: "Japan ETF proxy", timeframe: "1Y" },
    ],
    [
      "fx",
      { id: "fx-eurusd", label: "EUR/USD", group: "", last: "1.08", change: "+0.1%", secondary: "" },
      { targetTab: "macro", targetMode: "snapshot", timeframe: "3M", region: "US", theme: "all" },
    ],
    [
      "yields",
      { id: "curve-10Y", label: "10Y", group: "", last: "4.50%", change: "+3bp", secondary: "4.47%" },
      { targetTab: "macro", targetMode: "rates_policy", timeframe: "3M", region: "US", theme: "all" },
    ],
    [
      "commodities",
      { id: "wti", label: "WTI Crude Oil", group: "Energy", last: "82.00", change: "+1.50", secondary: "Backwardation" },
      { targetTab: "commodities", targetMode: "energy", commodityId: "wti" },
    ],
    [
      "commodities",
      { id: "gold", label: "Gold", group: "Metals", last: "2400.00", change: "-4.00", secondary: "FRED proxy" },
      { targetTab: "commodities", targetMode: "metals", commodityId: "gold" },
    ],
  ])("maps %s market rows to the correct tab and mode", (profile, row, expected) => {
    expect(resolveSitrepMarketHandoff(profile, row)).toMatchObject(expected);
  });

  it("falls back to Equity Research overview when an index row has no proxy", () => {
    expect(
      resolveSitrepMarketHandoff("indices", {
        id: "idx-custom",
        symbol: "^CUSTOM",
        label: "Custom Index",
        group: "Global",
        last: "1000",
        change: "N/A",
        secondary: "N/A",
      })
    ).toMatchObject({
      targetTab: "equity_research",
      targetMode: "overview",
    });
  });

  it("maps equity rows to Research Scope Analysis with the selected symbol", () => {
    expect(
      resolveSitrepMarketHandoff("equities", {
        id: "equity-aapl",
        symbol: "AAPL",
        label: "AAPL",
        selectionLabel: "Apple Inc.",
        group: "Info Tech",
        last: "190.00",
        change: "+1.2%",
        secondary: "24.0%",
      })
    ).toMatchObject({
      targetTab: "equity_research",
      targetMode: "scope_analysis",
      symbol: "AAPL",
      label: "Apple Inc.",
      timeframe: "1Y",
    });
  });

  it("preserves explicit tape-row targets for cross-domain triage rows", () => {
    const row: SitrepTapeHandoffRow = {
      id: "pm-market-1",
      source: "kalshi",
      tone: "neutral",
      title: "Fed cut by June",
      detail: "42%",
      meta: "open",
      handoff: {
        targetTab: "prediction_markets",
        marketId: "market-1",
      },
    };

    expect(resolveSitrepTapeHandoff(row)).toEqual(row.handoff);
  });
});

describe("sitrep follow-ups", () => {
  const tapeRow: SitrepTapeHandoffRow = {
    id: "evt-cpi",
    source: "Event",
    tone: "warning",
    title: "CPI release",
    detail: "Inflation / US",
    meta: "in 3d",
    handoff: { targetTab: "macro", targetMode: "events_regimes" },
  };

  const savedFollowUp: SitrepFollowUp = {
    id: "backend-uuid-1",
    row_id: "evt-cpi",
    source: "Event",
    tone: "warning",
    title: "CPI release",
    detail: "Inflation / US",
    meta: "in 3d",
    note: "",
    status: "open",
    handoff: { targetTab: "macro", targetMode: "events_regimes" },
    saved_at: "2026-07-12T00:00:00Z",
  };

  it("matches saved follow-ups by their originating row id", () => {
    expect(isSitrepFollowUpSaved([savedFollowUp], "evt-cpi")).toBe(true);
    expect(isSitrepFollowUpSaved([savedFollowUp], "other-row")).toBe(false);
    expect(findSitrepFollowUpByRow([savedFollowUp], "evt-cpi")?.id).toBe("backend-uuid-1");
    expect(findSitrepFollowUpByRow([savedFollowUp], "missing")).toBeNull();
  });

  it("builds a backend create payload from a triage row", () => {
    expect(buildSitrepFollowUpCreatePayload(tapeRow)).toEqual({
      row_id: "evt-cpi",
      title: "CPI release",
      source: "Event",
      tone: "warning",
      detail: "Inflation / US",
      meta: "in 3d",
      handoff: { targetTab: "macro", targetMode: "events_regimes" },
    });
  });

  it("removes follow-ups by backend id", () => {
    expect(removeSitrepFollowUp([savedFollowUp], "backend-uuid-1")).toHaveLength(0);
    expect(removeSitrepFollowUp([savedFollowUp], "missing")).toHaveLength(1);
  });

  it("parses legacy localStorage payloads for backend migration", () => {
    const legacy = JSON.stringify([
      {
        id: "evt-cpi",
        source: "Event",
        tone: "warning",
        title: "CPI release",
        detail: "Inflation / US",
        meta: "in 3d",
        handoff: { targetTab: "macro", targetMode: "events_regimes" },
        saved_at: "2026-07-12T00:00:00Z",
      },
    ]);
    const parsed = parseSitrepFollowUps(legacy);
    expect(parsed).toHaveLength(1);
    expect(parsed[0]).toMatchObject({
      id: "evt-cpi",
      row_id: "evt-cpi",
      title: "CPI release",
      note: "",
      status: "open",
      saved_at: "2026-07-12T00:00:00Z",
      handoff: { targetTab: "macro", targetMode: "events_regimes" },
    });
  });

  it("rejects malformed persisted payloads instead of throwing", () => {
    expect(parseSitrepFollowUps(null)).toEqual([]);
    expect(parseSitrepFollowUps("not json")).toEqual([]);
    expect(parseSitrepFollowUps('{"id":"x"}')).toEqual([]);
    expect(
      parseSitrepFollowUps(
        JSON.stringify([
          { id: "", title: "no id" },
          { id: "valid", title: "Valid row", handoff: { targetMode: "snapshot" } },
          { id: "valid", title: "Duplicate id" },
          42,
        ])
      )
    ).toEqual([
      {
        id: "valid",
        row_id: "valid",
        source: "",
        tone: "neutral",
        title: "Valid row",
        detail: "",
        meta: "",
        note: "",
        status: "open",
        handoff: null,
        saved_at: new Date(0).toISOString(),
        resolved_at: null,
      },
    ]);
  });
});

describe("sitrep window labels", () => {
  it("appends the change window to column labels", () => {
    expect(formatSitrepWindowLabel("CHG", "3M")).toBe("CHG (3M)");
    expect(formatSitrepWindowLabel("Move", "3m")).toBe("Move (3M)");
    expect(formatSitrepWindowLabel("CHG", null)).toBe("CHG");
    expect(formatSitrepWindowLabel("CHG", "  ")).toBe("CHG");
  });
});

describe("sitrep section clocks", () => {
  it("finds the oldest valid loaded section and formats its age", () => {
    expect(oldestSitrepSection([
      { id: "news", label: "News", retrievedAt: "2026-07-13T11:58:00Z" },
      { id: "macro", label: "Macro", retrievedAt: "2026-07-13T08:00:00Z" },
      { id: "missing", label: "Missing", retrievedAt: null },
      { id: "broken", label: "Broken", retrievedAt: "not-a-date" },
    ])).toEqual({ id: "macro", label: "Macro", retrievedAt: "2026-07-13T08:00:00Z" });

    const now = new Date("2026-07-13T12:00:00Z");
    expect(formatSitrepSectionAge("2026-07-13T11:59:30Z", now)).toBe("<1m old");
    expect(formatSitrepSectionAge("2026-07-13T11:15:00Z", now)).toBe("45m old");
    expect(formatSitrepSectionAge("2026-07-12T09:00:00Z", now)).toBe("27h old");
    expect(formatSitrepSectionAge(null, now)).toBe("N/A");
  });
});

describe("sitrep news enrichment", () => {
  it("routes listed entities to a grounded Equity Research scope", () => {
    expect(resolveSitrepNewsEntityHandoff({ label: "Apple", entity_type: "company", symbol: "aapl" })).toEqual({
      targetTab: "equity_research",
      targetMode: "scope_analysis",
      symbol: "AAPL",
      label: "Apple",
      timeframe: "1Y",
    });
    expect(resolveSitrepNewsEntityHandoff({ label: "Federal Reserve", entity_type: "central_bank" })).toBeNull();
  });

  it("formats only known source-quality labels", () => {
    expect(formatNewsReliabilityLabel("official")).toBe("OFFICIAL");
    expect(formatNewsReliabilityLabel("major_outlet")).toBe("OUTLET");
    expect(formatNewsReliabilityLabel("unknown")).toBe("");
  });
});
