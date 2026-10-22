import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { MacroEventsResponse, MacroSnapshot } from "../lib/api/types";
import MacroEventsRegimes from "./MacroEventsRegimes.svelte";

const BLS_WARNING =
  "Macro calendar: BLS release dates (CPI, PPI, Employment Situation, JOLTS) were not requested because no contact name and email is configured; bls.gov blocks automated requests that carry no contact details. Add your name and email in Setup (Settings > Run Setup) to load them.";

describe("MacroEventsRegimes calendar", () => {
  it("names each missing official calendar above the event list", () => {
    const events: MacroEventsResponse = { region: "US", events: [], warnings: [BLS_WARNING] };

    const { body } = render(MacroEventsRegimes, { props: { snapshot: null, events } });

    expect(body).toContain("BLS release dates (CPI, PPI, Employment Situation, JOLTS) were not requested");
    expect(body).not.toContain("Macro calendar:");
  });

  it("falls back to the snapshot's calendar warnings and ignores unrelated ones", () => {
    // Solo los campos que lee el componente; el resto del snapshot no interviene.
    const snapshot = {
      warnings: [
        "Global mode is a light comparative lens in V1.",
        "Macro calendar: BEA release schedule unavailable (HTTP 403 from www.bea.gov).",
      ],
      upcoming_events: [],
      event_studies: [],
      top_divergences: [],
    } as unknown as MacroSnapshot;

    const { body } = render(MacroEventsRegimes, { props: { snapshot, events: null } });

    expect(body).toContain("BEA release schedule unavailable (HTTP 403 from www.bea.gov).");
    expect(body).not.toContain("light comparative lens");
  });
});
