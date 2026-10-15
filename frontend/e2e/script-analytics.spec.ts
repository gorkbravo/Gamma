import { test, expect } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";

// Run tests/script_analytics_browser_server.py. Real server validation/analytics;
// runtime artifacts are deterministic fixtures, never executed Python evidence.
const api = process.env.GAMMA_E4_BROWSER_API;
test.skip(!api, "Requires the explicitly pinned E4 fixture server");
test.beforeEach(async ({ page }) => {
  await page.addInitScript(api => { window.__GAMMA_API_BASE__ = api; }, api!);
  await page.goto("/e2e/script-analytics-harness.html");
  await expect(page.getByLabel("Loaded script")).toBeEnabled();
});

for (const width of [1440, 1000, 390]) {
  test(`retained preview, temporary open and separate save at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByLabel("Loaded script").selectOption({ label: "E4 valid fixture" });
    await page.getByRole("button", { name: "Inspect analytical output", exact: true }).click();
    await expect(page.getByText("Valid analytical contract · executed run")).toBeVisible();
    const open = page.getByRole("button", { name: "Open temporary Strategy Lab analysis", exact: true });
    await expect(open).toHaveCount(4);
    await expect(open.nth(1)).toBeDisabled();
    await page.getByText("Inspect exact result, mapping, coverage and assumptions").first().click();
    await expect(page.getByText('"conversion": "percent / 100"', { exact: false }).first()).toBeVisible();
    mkdirSync("../output/playwright/script-e4", { recursive: true });
    await page.screenshot({ path: `../output/playwright/script-e4/preview-${width}.png`, fullPage: true });
    const before = (await (await request.get(`${api}/research/saved`)).json()).items.length;
    const response = page.waitForResponse(r => r.url().endsWith("/analytics/open"));
    await open.first().click();
    const analytical = await (await response).json();
    expect(analytical.analytical_provenance.result_id).toBe("returns");
    await expect(page.getByRole("tab", { name: "Backtest", exact: true })).toHaveAttribute("aria-selected", "true");
    expect((await (await request.get(`${api}/research/saved`)).json()).items.length).toBe(before);
    await page.getByText("Script source, inputs and analytical mapping", { exact: true }).click();
    await page.screenshot({ path: `../output/playwright/script-e4/analysis-${width}.png`, fullPage: true });
    const save = page.waitForResponse(r => r.url().endsWith("/research/saved") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Save Strategy", exact: true }).click();
    const saved = await (await save).json();
    expect(saved.payload.analytical_provenance).toEqual(analytical.analytical_provenance);
    await page.getByRole("tab", { name: "Saved Runs", exact: true }).click();
    await expect(page.getByText(saved.title, { exact: true }).first()).toBeVisible();
    const row = page.locator("tr").filter({ hasText: saved.title }).first();
    await row.getByRole("button", { name: "Load Strategy", exact: true }).click();
    await page.getByRole("tab", { name: "Backtest", exact: true }).click();
    await expect(page.getByText("Script source, inputs and analytical mapping", { exact: true })).toBeVisible();
    const downloaded = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export analysis JSON", exact: true }).click();
    const file = await downloaded;
    const exported = JSON.parse(readFileSync((await file.path())!, "utf-8"));
    expect(exported.analytical_provenance).toEqual(analytical.analytical_provenance);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

for (const width of [1440, 1000, 390]) test(`invalid output, safe preview, stale selection and unavailable target stay standalone at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.getByLabel("Loaded script").selectOption({ label: "E4 invalid optional output" });
  await page.getByRole("button", { name: "Inspect analytical output", exact: true }).click();
  await expect(page.getByText("Invalid optional output · handoff unavailable")).toBeVisible();
  await expect(page.getByText("Standalone retained log", { exact: true })).toBeVisible();
  await page.screenshot({ path: `../output/playwright/script-e4/invalid-${width}.png`, fullPage: true });
  await page.getByLabel("Loaded script").selectOption({ label: "E4 safe preview" });
  await expect(page.getByText("Invalid optional output · handoff unavailable")).toHaveCount(0);
  await page.getByRole("button", { name: "Inspect analytical output", exact: true }).click();
  await expect(page.getByText("Execution: completed · non-executing preview")).toBeVisible();
  const open = page.getByRole("button", { name: "Open temporary Strategy Lab analysis", exact: true });
  for (let i = 0; i < 4; i++) await expect(open.nth(i)).toBeDisabled();
  await page.screenshot({ path: `../output/playwright/script-e4/safe-preview-${width}.png`, fullPage: true });
  await page.getByLabel("Loaded script").selectOption({ label: "E4 valid fixture" });
  await page.getByRole("button", { name: "Inspect analytical output", exact: true }).click();
  // A target going away after preview fails explicitly, preserving Script state.
  await page.route("**/analytics/open", route => route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: ["Strategy Lab owning service unavailable"] }) }));
  await open.first().click();
  await expect(page.getByRole("alert")).toContainText("unavailable");
  await expect(page.getByRole("tab", { name: "Script", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.screenshot({ path: `../output/playwright/script-e4/unavailable-${width}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("late validation response cannot rebind another selected run", async ({ page }) => {
  await page.getByLabel("Loaded script").selectOption({ label: "E4 valid fixture" });
  let release!: () => void;
  let reached!: () => void;
  const started = new Promise<void>(resolve => { reached = resolve; });
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/analytics", async route => { reached(); await gate; await route.continue(); });
  await page.getByRole("button", { name: "Inspect analytical output", exact: true }).click();
  await started;
  await page.getByLabel("Loaded script").selectOption({ label: "E4 invalid optional output" });
  const response = page.waitForResponse(r => r.url().endsWith("/analytics"));
  release();
  await response;
  await expect(page.getByRole("button", { name: "Inspect analytical output", exact: true })).toBeEnabled();
  await expect(page.getByText("Valid analytical contract · executed run")).toHaveCount(0);
});
