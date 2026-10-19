import { test, expect } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { CommodityCurveCapture } from "../src/lib/commodity-captures";

const api = process.env.GAMMA_CURVES_API, phase = process.env.GAMMA_CURVES_PHASE;
const directory = resolve(process.env.GAMMA_CURVES_EVIDENCE ?? "../output/playwright/commodity-curves");
test.skip(!api, "Run via output/verify_commodity_curves.py");
test.setTimeout(180_000); test.use({ actionTimeout: 15_000 });
test.beforeEach(async ({ page }) => {
  await page.addInitScript(({ api, token }) => { window.__GAMMA_API_BASE__ = api; window.__GAMMA_SESSION_TOKEN__ = token; },
    { api: api!, token: process.env.GAMMA_CURVES_TOKEN! });
  await page.goto("/e2e/commodity-curves-harness.html");
});

test("retain two displayed curves and an exact calendar pair", async ({ page }) => {
  test.skip(phase !== "capture");
  const panel = page.getByRole("article", { name: "Commodity curve history" });
  await expect(panel.getByRole("button", { name: "Save Current Curve" })).toBeEnabled({ timeout: 90_000 });
  const captures: CommodityCurveCapture[] = [];
  for (let i = 0; i < 2; i++) {
    if (i) {
      // La segunda captura debe ser otra observación: el mismo as_of cuenta una sola vez en la historia,
      // y el proveedor de muestra fija as_of al segundo, así que se refresca hasta que cambie.
      const first = captures[0].payload;
      let asOf = first.curve.as_of;
      for (let attempt = 0; attempt < 20 && asOf === first.curve.as_of; attempt++) {
        if (attempt) await page.waitForTimeout(500);
        const refreshed = page.waitForResponse(r => r.url().endsWith("/commodities/workspace"));
        await page.getByRole("button", { name: "Refresh", exact: true }).click();
        const workspace = await refreshed;
        expect(workspace.status()).toBe(200);
        const body = await workspace.json() as { curves: Array<{ instrument_id: string; as_of: string }> };
        asOf = body.curves.find(curve => curve.instrument_id === first.instrument.instrument_id)?.as_of ?? asOf;
      }
      expect(asOf, "the refreshed curve must be a new observation").not.toBe(first.curve.as_of);
    }
    const saved = page.waitForResponse(r => r.url().endsWith("/commodities/curve-captures") && r.request().method() === "POST");
    await panel.getByRole("button", { name: "Save Current Curve" }).click();
    const response = await saved;
    expect(response.status()).toBe(200);
    const capture = await response.json();
    expect(capture.payload).toEqual(response.request().postDataJSON());
    if (process.env.GAMMA_CURVES_LIVE === "1") expect(capture.payload.curve.nodes.filter((n: { price: number | null }) => n.price != null).every((n: { source_provider: string }) => n.source_provider === "ibkr")).toBe(true);
    captures.push(capture);
    await expect(panel.getByRole("status")).toContainText("Saved");
  }
  await panel.getByLabel("Spread name").fill("Acceptance exact WTI pair");
  const tracked = page.waitForResponse(r => r.url().endsWith("/commodities/calendar-spreads") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Track Calendar Spread" }).click();
  const response = await tracked;
  expect(response.status()).toBe(200);
  mkdirSync(directory, { recursive: true });
  writeFileSync(resolve(directory, "capture.json"), JSON.stringify({ captures, spread: await response.json() }, null, 2));
});

test("reopen after restart, compare exact contracts and replay the retained pair", async ({ page }) => {
  test.skip(phase !== "replay");
  const evidence = JSON.parse(readFileSync(resolve(directory, "capture.json"), "utf8"));
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  const panel = page.getByRole("article", { name: "Commodity curve history" });
  await panel.getByRole("combobox", { name: "Comparison capture", exact: true }).selectOption(evidence.captures[1].id);
  const reopened = page.waitForResponse(r => r.url().endsWith(`/commodities/curve-captures/${evidence.captures[1].id}`));
  await panel.getByRole("button", { name: "Reopen Capture" }).click();
  expect(await (await reopened).json()).toEqual(evidence.captures[1]);
  await expect(panel).toContainText("Retained CL curve");
  await panel.getByRole("combobox", { name: "Baseline capture", exact: true }).selectOption(evidence.captures[0].id);
  const compared = page.waitForResponse(r => r.url().endsWith("/commodities/curve-captures/compare"));
  await panel.getByRole("button", { name: "Compare Captures" }).click();
  const comparedResponse = await compared;
  expect(comparedResponse.status()).toBe(200);
  const comparison = await comparedResponse.json();
  expect(comparison.rows.some((r: { status: string }) => r.status === "matched")).toBe(true);
  await panel.getByRole("combobox", { name: "Saved calendar spread", exact: true }).selectOption(evidence.spread.id);
  const historical = page.waitForResponse(r => r.url().endsWith(`/commodities/calendar-spreads/${evidence.spread.id}/history`));
  await panel.getByRole("button", { name: "Load Spread History" }).click();
  const history = await (await historical).json();
  expect(history.points).toHaveLength(2);
  expect(history.spread).toEqual(evidence.spread);
  // Un punto cuyas patas difieren en campo de precio, retraso o frescura se etiqueta
  // mixed_quote_evidence (conserva el valor); con datos de muestra ambas patas comparten evidencia.
  const accepted = process.env.GAMMA_CURVES_LIVE === "1" ? ["observed", "mixed_quote_evidence"] : ["observed"];
  expect(history.points.every((p: { status: string; value: number | null }) => accepted.includes(p.status) && p.value != null)).toBe(true);
  let gapCaptureId = "";
  if (process.env.GAMMA_CURVES_LIVE !== "1") {
    // Exercise a roll-shaped gap with sample data only. Live evidence remains untouched.
    const rolled = structuredClone(evidence.captures[1].payload);
    rolled.curve.nodes.shift(); rolled.curve.nodes[0].contract.is_front_month = true;
    // Observación posterior: con el mismo as_of contaría como un nuevo guardado de la misma observación.
    const observed = rolled.curve.as_of;
    rolled.curve.as_of = new Date(Date.parse(/(Z|[+-]\d{2}:\d{2})$/.test(observed) ? observed : `${observed}Z`) + 60_000).toISOString();
    const missing = await page.request.post(`${api}/commodities/curve-captures`, {
      headers: { "X-Gamma-Session": process.env.GAMMA_CURVES_TOKEN! }, data: rolled
    });
    expect(missing.status()).toBe(200);
    const gapCapture = await missing.json();
    gapCaptureId = gapCapture.id;
    await panel.getByRole("button", { name: "Refresh Saved" }).click();
    await panel.getByRole("combobox", { name: "Comparison capture", exact: true }).selectOption(gapCapture.id);
    const gapResponse = page.waitForResponse(r => r.url().endsWith("/commodities/curve-captures/compare"));
    await panel.getByRole("button", { name: "Compare Captures" }).click();
    expect((await (await gapResponse).json()).rows[0].status).toBe("absent_from_comparison");
    await expect(panel).toContainText("contract not in capture");
    await expect(panel).toContainText("absent from comparison");
    await expect(panel).not.toContainText("share observation time");
  }
  for (const width of [1440, 1000, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await panel.screenshot({ path: resolve(directory, `history-${width}.png`) });
    expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    const overflow = await page.evaluate(() => ({ width: innerWidth, page: document.documentElement.scrollWidth, elements: [...document.querySelectorAll("body *")].map(el => ({ tag: el.tagName, cls: el.className, right: el.getBoundingClientRect().right, width: el.getBoundingClientRect().width })).filter(el => el.right > innerWidth + 1).slice(0, 20) }));
    expect(overflow.page <= overflow.width, JSON.stringify(overflow)).toBe(true);
  }
  writeFileSync(resolve(directory, "replay.json"), JSON.stringify({ comparison, history, pageErrors: errors }, null, 2));
  await page.route("**/commodities/curve-captures/compare", route => route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: "Capture units differ." }) }));
  await panel.getByRole("button", { name: "Compare Captures" }).click();
  await expect(panel.getByRole("alert")).toContainText("Capture units differ");
  await page.unroute("**/commodities/curve-captures/compare");
  if (gapCaptureId) {
    // Borrado en dos pasos, solo con datos de muestra: el primer clic arma la confirmación.
    const comparisonSelect = panel.getByRole("combobox", { name: "Comparison capture", exact: true });
    await comparisonSelect.selectOption(gapCaptureId);
    await panel.getByRole("button", { name: "Delete Capture", exact: true }).click();
    const deleted = page.waitForResponse(r => r.url().endsWith(`/commodities/curve-captures/${gapCaptureId}`) && r.request().method() === "DELETE");
    await panel.getByRole("button", { name: "Confirm Delete Capture" }).click();
    expect((await deleted).status()).toBe(200);
    await expect(panel.getByRole("status")).toContainText("Deleted the retained curve capture");
    await expect(comparisonSelect.locator(`option[value="${gapCaptureId}"]`)).toHaveCount(0);
    // La captura origen del spread no se borra mientras el spread exista (409 visible).
    await comparisonSelect.selectOption(evidence.spread.payload.source_capture_id);
    await panel.getByRole("button", { name: "Delete Capture", exact: true }).click();
    await panel.getByRole("button", { name: "Confirm Delete Capture" }).click();
    await expect(panel.getByRole("alert")).toContainText("delete those spreads first");
    await expect(comparisonSelect.locator(`option[value="${evidence.spread.payload.source_capture_id}"]`)).toHaveCount(1);
  }
  expect(errors).toEqual([]);
});
