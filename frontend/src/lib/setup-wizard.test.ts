import { describe, expect, it } from "vitest";
import type { SystemStatus } from "./api/types";
import { setupReportFixture } from "./setup-wizard.fixture";
import {
  buildSetupChoices,
  closesOnFinish,
  coverageSourceLabel,
  draftChanges,
  initialDraft,
  initialStepIndex,
  isSecIdentityMissingError,
  lostCapabilities,
  restartNeeded,
  setupSteps,
  validateSecIdentity
} from "./setup-wizard";

const status: SystemStatus = {
  healthy: true,
  app_name: "Gamma API",
  backend: "fastapi",
  mock_mode: true,
  base_currency: "EUR",
  market_data_mode: "delayed",
  connection: { connected: true, status_text: "Status: Mock", action_text: "Mock Mode", action_enabled: false, active_account: null },
  cached_symbols: []
};

describe("setup wizard view model", () => {
  it("adds the broker step only for live data", () => {
    expect(setupSteps("demo")).toEqual(["mode", "preferences", "sources", "identity", "review"]);
    expect(setupSteps("live")).toEqual(["mode", "broker", "preferences", "sources", "identity", "review"]);
  });

  it("starts from the saved preference and only pre-fills an identity the user saved", () => {
    const report = setupReportFixture({
      data_mode: { ...setupReportFixture().data_mode, preference: "live" },
      sec_identity: {
        status: "configured",
        source: "setup",
        locked_by: null,
        name: "Ada Tester",
        email: "ada@example.com",
        detail: ""
      }
    });
    expect(initialDraft(report, status)).toEqual({
      dataMode: "live",
      baseCurrency: "EUR",
      marketDataMode: "delayed",
      secName: "Ada Tester",
      secEmail: "ada@example.com",
      clearSecIdentity: false
    });
    const environment = setupReportFixture({
      sec_identity: { ...report.sec_identity, source: "environment", name: null, email: null }
    });
    expect(initialDraft(environment, status).secName).toBe("");
  });

  it("validates the SEC identity like the backend and treats empty as unchanged", () => {
    expect(validateSecIdentity("", "")).toBeNull();
    expect(validateSecIdentity("A", "a@example.com")).toMatch(/at least 2/);
    expect(validateSecIdentity("Ada Tester", "not-an-email")).toMatch(/valid email/);
    expect(validateSecIdentity("  Ada   Tester ", " ada@example.com ")).toBeNull();
  });

  it("sends only changed fields and routes the currency through Settings", () => {
    const report = setupReportFixture();
    const draft = {
      ...initialDraft(report, status),
      dataMode: "live" as const,
      baseCurrency: "USD",
      marketDataMode: "auto",
      secName: " Ada  Tester",
      secEmail: "ada@example.com "
    };
    expect(buildSetupChoices(report, status, draft)).toEqual({
      baseCurrency: "USD",
      update: {
        complete: true,
        data_mode: "live",
        market_data_mode: "auto",
        sec_identity: { name: "Ada Tester", email: "ada@example.com" }
      }
    });
    expect(restartNeeded(report, draft)).toBe(true);

    const unchanged = buildSetupChoices(report, status, initialDraft(report, status));
    expect(unchanged).toEqual({ baseCurrency: null, update: { complete: true, data_mode: "demo" } });
  });

  it("never sends a data mode or identity that the environment fixes", () => {
    const report = setupReportFixture({
      data_mode: { ...setupReportFixture().data_mode, source: "environment", locked_by: "MOCK_DATA" },
      sec_identity: {
        status: "configured",
        source: "environment",
        locked_by: "GAMMA_SEC_USER_NAME / GAMMA_SEC_USER_EMAIL",
        name: null,
        email: null,
        detail: ""
      }
    });
    const draft = { ...initialDraft(report, status), dataMode: "live" as const, secName: "Ada", secEmail: "a@b.co" };
    const choices = buildSetupChoices(report, status, draft);
    expect(choices.update.data_mode).toBeUndefined();
    expect(choices.update.sec_identity).toBeUndefined();
    expect(restartNeeded(report, draft)).toBe(false);
  });

  it("explains the consequences of each change for the review step", () => {
    const report = setupReportFixture({
      sec_identity: { status: "configured", source: "setup", locked_by: null, name: "Ada", email: "a@b.co", detail: "" }
    });
    const draft = { ...initialDraft(report, status), dataMode: "live" as const, baseCurrency: "GBP", clearSecIdentity: true };
    const changes = draftChanges(report, status, draft);
    expect(changes.map((change) => change.label)).toEqual(["Data mode", "Base currency", "SEC identity"]);
    expect(changes[0].note).toMatch(/restart/i);
    expect(changes[1].note).toMatch(/portfolio history/);
    expect(changes[2].to).toBe("Not set");
    expect(buildSetupChoices(report, status, draft).update.clear_sec_identity).toBe(true);
  });

  it("opens on a requested step only when that step exists for the mode", () => {
    expect(initialStepIndex(setupSteps("demo"), "identity")).toBe(3);
    expect(initialStepIndex(setupSteps("live"), "identity")).toBe(4);
    expect(initialStepIndex(setupSteps("demo"), "broker")).toBe(0);
    expect(initialStepIndex(setupSteps("demo"), null)).toBe(0);
  });

  it("recognizes the backend's missing-identity response", () => {
    expect(isSecIdentityMissingError("428 Precondition Required: SEC EDGAR needs your name")).toBe(true);
    expect(isSecIdentityMissingError("500 Internal Server Error")).toBe(false);
    expect(isSecIdentityMissingError(null)).toBe(false);
  });

  it("lists the capabilities lost by an empty SEC identity, a missing broker and unavailable tabs", () => {
    const report = setupReportFixture();
    const demoDraft = initialDraft(report, status);
    expect(lostCapabilities(report, demoDraft).map((item) => item.id)).toEqual(["sec_identity"]);
    expect(lostCapabilities(report, demoDraft)[0].capability).toMatch(/Fundamentals, Copilot company lookup/);

    const filled = { ...demoDraft, secName: "Ada Tester", secEmail: "ada@example.com" };
    expect(lostCapabilities(report, filled)).toEqual([]);

    const live = setupReportFixture({
      data_mode: { ...report.data_mode, current: "live" },
      ibkr: { ...report.ibkr, status: "disconnected" }
    });
    const liveDraft = { ...initialDraft(live, status), dataMode: "live" as const };
    expect(lostCapabilities(live, liveDraft).map((item) => item.id)).toEqual([
      "sec_identity",
      "broker",
      "coverage:commodities"
    ]);
    expect(lostCapabilities(live, liveDraft)[1].fix).toContain("IB_AUTO_CONNECT=true");

    const saved = setupReportFixture({
      sec_identity: { status: "configured", source: "setup", locked_by: null, name: "Ada", email: "a@b.co", detail: "" }
    });
    const clearing = { ...initialDraft(saved, status), clearSecIdentity: true };
    expect(lostCapabilities(saved, clearing).map((item) => item.id)).toEqual(["sec_identity"]);
    const environment = setupReportFixture({
      sec_identity: { ...saved.sec_identity, source: "environment", status: "configured" }
    });
    expect(lostCapabilities(environment, initialDraft(environment, status))).toEqual([]);
  });

  it("closes on Finish unless there is a restart or a note to read", () => {
    expect(closesOnFinish({ restartRequired: false, lines: [] })).toBe(true);
    expect(closesOnFinish({ restartRequired: true, lines: [] })).toBe(false);
    expect(closesOnFinish({ restartRequired: false, lines: ["SEC identity saved for Fundamentals."] })).toBe(false);
  });

  it("labels coverage sources in product language", () => {
    expect(coverageSourceLabel("broker")).toBe("IBKR");
    expect(coverageSourceLabel("unavailable")).toBe("Unavailable");
  });
});
