import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import { setupReportFixture } from "../lib/setup-wizard.fixture";
import SetupWizard from "./SetupWizard.svelte";

const handlers = {
  onClose: () => {},
  onSkip: async () => true,
  onFinish: async () => ({ ok: true, lines: [], error: null, currencyChanged: false, restartRequired: false }),
  onTestConnection: async () => {},
  onRetry: () => {}
};

describe("SetupWizard", () => {
  it("renders an accessible modal that opens on the data-mode choice", () => {
    const { body } = render(SetupWizard, {
      props: { ...handlers, report: setupReportFixture(), status: null, firstRun: true }
    });

    expect(body).toContain('role="dialog"');
    expect(body).toContain('aria-modal="true"');
    expect(body).toContain('aria-labelledby="setup-title"');
    expect(body).toContain("First-run setup");
    expect(body).toContain("How do you want to start?");
    expect(body).toContain('aria-current="step"');
    // Demo omite el paso Broker.
    expect(body).not.toContain("Broker");
    expect(body).toContain('name="setup-data-mode"');
    expect(body).toContain("Skip setup");
    expect(body).toContain("Next: Preferences");
    expect(body).toContain("never places orders");
  });

  it("locks the mode choice when the environment fixes it", () => {
    const report = setupReportFixture({
      data_mode: { ...setupReportFixture().data_mode, source: "environment", locked_by: "MOCK_DATA" },
      warnings: ["The saved live preference is ignored because MOCK_DATA is set in the environment."]
    });
    const { body } = render(SetupWizard, { props: { ...handlers, report, status: null, firstRun: false } });

    expect(body).toMatch(/<fieldset[^>]*disabled/);
    expect(body).toContain("Set by MOCK_DATA in the environment or .env file.");
    expect(body).toContain("is ignored because MOCK_DATA");
    expect(body).not.toContain("Skip setup");
  });

  it("can open directly on the SEC identity step and says what needs it", () => {
    const { body } = render(SetupWizard, {
      props: { ...handlers, report: setupReportFixture(), status: null, firstRun: false, initialStep: "identity" }
    });

    expect(body).toContain("SEC EDGAR identity");
    expect(body).toContain('autocomplete="email"');
    expect(body).toContain("Required for Fundamentals");
    expect(body).not.toContain("development identity");
  });

  it("states loading and failure without a draft", () => {
    const loading = render(SetupWizard, { props: { ...handlers, report: null, loading: true } });
    expect(loading.body).toContain("Reading setup status");
    expect(loading.body).toContain("LOADING...");

    const failed = render(SetupWizard, { props: { ...handlers, report: null, loadError: "HTTP 500" } });
    expect(failed.body).toContain("Setup unavailable");
    expect(failed.body).toContain("HTTP 500");
    expect(failed.body).toContain("Retry");
  });
});
