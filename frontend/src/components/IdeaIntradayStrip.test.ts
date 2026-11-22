import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Idea } from "../lib/api/types";
import { INTRADAY_VIEW } from "../lib/idea-intraday.fixture";
import IdeaIntradayStrip from "./IdeaIntradayStrip.svelte";

const IDEA = { idea_id: "i1", title: "AAPL over MSFT", stance: "relative", status: "active" } as unknown as Idea;

describe("IdeaIntradayStrip", () => {
  it("labels the layer hypothetical and shows quality, gaps and the latest marks", () => {
    const { body } = render(IdeaIntradayStrip, { props: { idea: IDEA, view: INTRADAY_VIEW } });
    expect(body).toContain("Intraday");
    expect(body).toContain("Hypothetical, not executed");
    expect(body).toContain("Delayed");
    expect(body).toContain("Recording");
    expect(body).toContain("as of 15:25 UTC · 3 marks · 1 gap");
    expect(body).toContain("+1.23%");
    expect(body).toContain("vs close 2026-11-09");
    expect(body).toContain("Intraday drawdown");
    expect(body).toContain("-0.40%");
    expect(body).toContain("15:05–15:25");
    expect(body).toContain("TWS disconnected");
    expect(body).toContain("Latest IBKR marks");
    expect(body).toContain("No price for MSFT.");
    // Dos sesiones guardadas: selector de día.
    expect(body).toContain('aria-label="Intraday session (UTC day)"');
  });

  it("says why there is nothing to show, in the same place", () => {
    const empty = {
      ...INTRADAY_VIEW,
      available: false,
      status: "no_marks" as const,
      status_reason: "No IBKR marks yet. Gamma records them every 5 minutes while Trader Workstation is connected.",
      sessions: [],
    };
    const { body } = render(IdeaIntradayStrip, { props: { idea: IDEA, view: empty } });
    expect(body).toContain("Hypothetical, not executed");
    expect(body).toContain("No IBKR marks yet");
    expect(body).not.toContain("Latest IBKR marks");
    const demo = render(IdeaIntradayStrip, {
      props: { idea: IDEA, view: { ...empty, status: "demo" as const, status_reason: "Demo mode: no IBKR marks." } },
    }).body;
    expect(demo).toContain("Demo mode: no IBKR marks.");
  });

  it("shows a carried leg as its last close and a frozen session without the recording tag", () => {
    const frozen = {
      ...INTRADAY_VIEW,
      status: "idle" as const,
      tws_connected: false,
      summary: { ...INTRADAY_VIEW.summary, quality: "frozen" as const, qualities: ["frozen" as const] },
      legs: [{ ...INTRADAY_VIEW.legs[0], carried: true, quality: null, field: null }],
      sessions: ["2026-11-14"],
    };
    const { body } = render(IdeaIntradayStrip, { props: { idea: IDEA, view: frozen } });
    expect(body).toContain("Frozen");
    expect(body).toContain("Last close");
    expect(body).toContain("market closed");
    expect(body).not.toContain("Recording");
    expect(body).not.toContain("Intraday session (UTC day)");
  });
});
