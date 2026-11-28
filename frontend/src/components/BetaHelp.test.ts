import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import GettingStartedDialog from "./GettingStartedDialog.svelte";
import ReportProblemDialog from "./ReportProblemDialog.svelte";

// Beta (2026-11-28): guía con nota de privacidad y «Report a problem». La interacción
// (copiar, guardar, vista previa con retardo) la cubre e2e/beta-help.spec.ts.
describe("ReportProblemDialog", () => {
  it("renders a modal that says nothing is sent and waits for the preview", () => {
    const { body } = render(ReportProblemDialog, { props: { onClose: () => {} } });

    expect(body).toContain('role="dialog"');
    expect(body).toContain('aria-modal="true"');
    expect(body).toContain('aria-labelledby="report-problem-title"');
    expect(body).toContain("Report a problem");
    expect(body).toContain("Gamma does not send it anywhere.");
    expect(body).toContain('maxlength="2000"');
    expect(body).toContain("Building the report");
    expect(body).toContain("Copy report");
    expect(body).toContain("Save report");
  });
});

describe("GettingStartedDialog", () => {
  it("walks through the main workflows with the real control names", () => {
    const { body } = render(GettingStartedDialog, { props: { onClose: () => {} } });

    expect(body).toContain("Getting started");
    expect(body).toContain('aria-pressed="true"');
    for (const control of ["Pin to idea", "Compose Portfolio", "Open In Risk", "Attach to idea", "Operator"]) {
      expect(body).toContain(control);
    }
    expect(body).toContain("never places");
  });

  it("states what stays local and what leaves the computer", () => {
    const { body } = render(GettingStartedDialog, {
      props: { onClose: () => {}, initialSection: "privacy", envFilePath: "C:/Gamma/.env" }
    });

    expect(body).toContain("no accounts, analytics or crash reporting");
    expect(body).toContain("C:/Gamma/.env");
    expect(body).toContain("plain text");
    expect(body).toContain("sec.gov and bls.gov");
    expect(body).toContain("GAMMA_COPILOT_STORE_RESPONSES=false");
    expect(body).toContain(String.raw`%APPDATA%\com.gamma.shell\runtime`);
  });

  it("matches the store setting and app-data folder the code actually uses", () => {
    const readme = readFileSync(fileURLToPath(new URL("../../../README.md", import.meta.url)), "utf8");
    const tauri = readFileSync(fileURLToPath(new URL("../../src-tauri/tauri.conf.json", import.meta.url)), "utf8");

    expect(readme).toContain("GAMMA_COPILOT_STORE_RESPONSES=false");
    expect(JSON.parse(tauri).identifier).toBe("com.gamma.shell");
  });
});
