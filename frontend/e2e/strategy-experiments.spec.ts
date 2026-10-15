import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

// This acceptance gate uses the real API, with a server restart between phases.
// output/verify_strategy_experiments.py runs both phases in mock or live TWS mode.
const api = process.env.GAMMA_EXPERIMENT_API;
const phase = process.env.GAMMA_EXPERIMENT_PHASE;
const title = process.env.GAMMA_EXPERIMENT_TITLE!;
const evidence = resolve(process.env.GAMMA_EXPERIMENT_EVIDENCE ?? "../output/playwright/strategy-experiments");
test.skip(!api, "Run through output/verify_strategy_experiments.py");
test.setTimeout(180_000);
test.use({ actionTimeout: 10_000 });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(({ api, token }) => {
    window.__GAMMA_API_BASE__ = api;
    window.__GAMMA_SESSION_TOKEN__ = token;
  }, { api: api!, token: process.env.GAMMA_EXPERIMENT_TOKEN! });
  await page.goto(`/e2e/strategy-experiments-harness.html${process.env.GAMMA_EXPERIMENT_LIVE === "1" ? "" : "?fixture=1"}`);
});

test("compose without validation and retain complete experiment", async ({ page }) => {
  test.skip(phase !== "capture");
  await page.getByLabel("Name", { exact: true }).fill(title);
  const composed = page.waitForResponse(r => r.url().endsWith("/research/strategy-lab/portfolio-compose"));
  await page.getByRole("button", { name: "Compose Portfolio", exact: true }).click();
  const response = await composed;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.portfolio_inputs.legs.map((l: { weight: number }) => l.weight)).toEqual([1, -1]);
  expect(result.risk_legs).toHaveLength(2);
  expect(result.returns_points.length).toBeGreaterThanOrEqual(60);
  if (process.env.GAMMA_EXPERIMENT_LIVE === "1") {
    expect(result.risk_legs.every((l: { source_provider: string }) => l.source_provider === "ibkr")).toBe(true);
  }
  const saved = page.waitForResponse(r => r.url().endsWith("/research/saved") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Save Experiment", exact: true }).click();
  const savedResponse = await saved;
  expect(savedResponse.status()).toBe(200);
  const item = await savedResponse.json();
  expect(item.payload.portfolio_inputs).toEqual(result.portfolio_inputs);
  expect(item.payload.risk_legs).toEqual(result.risk_legs);
  mkdirSync(evidence, { recursive: true });
  writeFileSync(resolve(evidence, "baseline.json"), JSON.stringify(item, null, 2));
  await expect(page.getByRole("status")).toContainText("Saved");
});

test("reopen after server restart, Risk, revised weights and shared-window comparison", async ({ page }) => {
  test.skip(phase !== "replay");
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.getByRole("tab", { name: "Saved Runs", exact: true }).click();
  const row = page.locator("tr").filter({ hasText: title });
  await row.getByRole("button", { name: "Reopen Experiment" }).click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(title);
  await expect(page.getByRole("status")).toContainText("Reopened");
  const riskResponse = page.waitForResponse(r => r.url().endsWith("/risk/compute"));
  await page.getByRole("button", { name: "Open In Risk" }).click();
  const risk = await riskResponse;
  expect(risk.status()).toBe(200);
  const riskPayload = risk.request().postDataJSON();
  expect(riskPayload.source_scope).toBe("research_book");
  expect(riskPayload.benchmark_symbol).toBe("SPY");
  const riskResult = await risk.json();
  expect(riskResult.source_scope).toBe("research_book");
  expect(riskResult.benchmark_return_points).toEqual(riskPayload.research_book_benchmark_points);
  await page.getByTestId("switch-view").click();
  const weights = page.locator("tbody input[type=number]");
  await weights.first().fill("2");
  const recomposed = page.waitForResponse(r => r.url().endsWith("/research/strategy-lab/portfolio-compose"));
  await page.getByRole("button", { name: "Compose Portfolio", exact: true }).click();
  const revisedResponse = await recomposed;
  expect(revisedResponse.status()).toBe(200);
  const revisedPayload = revisedResponse.request().postDataJSON();
  expect(revisedPayload.legs[0].weight).toBe(2);
  expect(revisedPayload.legs[0].object.provenance.retained_experiment).toBe(true);
  expect(revisedPayload.benchmark_object.return_points).toEqual(riskPayload.research_book_benchmark_points);
  const revised = await revisedResponse.json();
  await page.getByRole("tab", { name: "Saved Runs", exact: true }).click();
  const panel = page.getByRole("article", { name: "Saved experiment comparison" });
  await panel.getByRole("combobox", { name: "Baseline", exact: true }).selectOption({ label: title });
  const compared = page.waitForResponse(r => r.url().endsWith("/research/compare-scenario/analyze"));
  await panel.getByRole("button", { name: "Compare Runs" }).click();
  const comparedResponse = await compared;
  expect(comparedResponse.status()).toBe(200);
  const comparison = await comparedResponse.json();
  expect(comparison.aligned_observation_count).toBe(riskPayload.research_book_return_points.length);
  expect(comparison.left.metrics.total_return).not.toBe(comparison.right.metrics.total_return);
  await expect(panel).toContainText("shared observations");
  await expect(panel).not.toContainText("Benchmark histories differ");
  mkdirSync(evidence, { recursive: true });
  writeFileSync(resolve(evidence, "replay.json"), JSON.stringify({ risk: riskResult, revised, comparison }, null, 2));
  for (const width of [1440, 1000, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: resolve(evidence, `comparison-${width}.png`), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.getByRole("tab", { name: "Composer", exact: true }).click();
  // Changing the ticker must drop the old ticker's retained history.
  await page.getByPlaceholder("Ticker / contract id").first().fill("INVALID_GAMMA_TICKER");
  await page.getByPlaceholder("Ticker / contract id").first().blur();
  await page.route("**/research/strategy-lab/portfolio-compose", async route => {
    expect(route.request().postDataJSON().legs[0].object).toBeNull();
    await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Ticker history unavailable. Check the identifier." }) });
  });
  await page.getByRole("button", { name: "Compose Portfolio", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Ticker history unavailable");
  // El resultado conservado queda marcado como obsoleto frente al borrador actual.
  await expect(page.getByTestId("composition-stale")).toBeVisible();
  const retainedRisk = page.waitForResponse(r => r.url().endsWith("/risk/compute"));
  await page.getByRole("button", { name: "Open In Risk" }).click();
  const retainedRiskResponse = await retainedRisk;
  expect(retainedRiskResponse.status()).toBe(200);
  expect(retainedRiskResponse.request().postDataJSON().research_book_return_points).toEqual(revised.returns_points.map((p: { timestamp: string; value: number }) => ({ timestamp: p.timestamp, value: p.value })));
  expect(errors).toEqual([]);
});
