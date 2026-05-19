import { describe, expect, it } from "vitest";
import {
  resolveSitrepMarketHandoff,
  resolveSitrepTapeHandoff,
  type SitrepHandoffRequest,
  type SitrepMarketHandoffProfile,
  type SitrepMarketHandoffRow,
  type SitrepTapeHandoffRow,
} from "./sitrep";

describe("sitrep handoff view model", () => {
  it.each<[SitrepMarketHandoffProfile, SitrepMarketHandoffRow, Partial<SitrepHandoffRequest>]>([
    [
      "indices",
      { id: "idx-spx", label: "S&P 500", group: "US", last: "5000", change: "+1", secondary: "SPX" },
      { targetTab: "equity_research", targetMode: "overview" },
    ],
    [
      "fx",
      { id: "fx-eurusd", label: "EUR/USD", group: "", last: "1.08", change: "+0.1%", secondary: "" },
      { targetTab: "macro", targetMode: "snapshot" },
    ],
    [
      "yields",
      { id: "curve-10Y", label: "10Y", group: "", last: "4.50%", change: "+3bp", secondary: "4.47%" },
      { targetTab: "macro", targetMode: "rates_policy" },
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
