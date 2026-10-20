import { test, expect, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";

// Ejecutar antes tests/script_e5_browser_server.py. Validación, libro de pesos, comparación y walk-forward
// son reales; los artefactos del runtime son fixtures deterministas derivados de los parámetros (no hay Python).
const api = process.env.GAMMA_E5_BROWSER_API;
test.skip(!api, "Requires the explicitly pinned E5 fixture server");
test.setTimeout(90_000);
const shots = "../output/playwright/script-e5";

async function setText(page: Page, label: string, value: string) {
  const field = page.getByLabel(label, { exact: true });
  await field.fill(value);
}

test.beforeEach(async ({ page }) => {
  await page.goto(`/e2e/script-e5-harness.html?api=${encodeURIComponent(api!)}`);
  await expect(page.getByLabel("Loaded script")).toBeEnabled();
  mkdirSync(shots, { recursive: true });
});

for (const width of [1440, 1000, 390]) {
  test(`parameters, causal weight book, sweep and walk-forward at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const noOverflow = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);

    // Parámetros separados del código: un JSON inválido bloquea la ejecución.
    await setText(page, "Run parameters JSON", "[1, 2]");
    await expect(page.getByText("flat JSON object", { exact: false })).toBeVisible();
    await expect(page.getByRole("button", { name: "Run immutable revision" })).toBeDisabled();
    await setText(page, "Run parameters JSON", '{"lookback": 10, "leverage": 1.5}');
    await expect(page.getByText("2 parameters →", { exact: false })).toBeVisible();
    const runResponse = page.waitForResponse((r) => /\/scripts\/[^/]+\/runs$/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Run immutable revision" }).click();
    const run = await (await runResponse).json();
    expect(run.parameters).toEqual({ leverage: 1.5, lookback: 10 });
    await expect(page.getByText(run.parameters_sha256.slice(0, 12), { exact: true })).toBeVisible();

    // Libro causal de pesos: opciones ligadas al hash de la vista previa y apertura temporal.
    await page.getByRole("button", { name: "Inspect analytical output", exact: true }).click();
    const book = page.getByLabel("Causal weight book");
    await expect(book.getByText("Book returns", { exact: true })).toBeVisible();
    await page.getByLabel("Book cost in basis points per unit turnover").fill("5");
    await page.getByLabel("Book cost in basis points per unit turnover").blur();
    await expect(book.getByRole("button", { name: "Open causal book in Strategy Lab" })).toBeDisabled();
    await book.getByRole("button", { name: "Apply" }).click();
    await expect(book.getByText("Options changed", { exact: false })).toHaveCount(0);
    await page.screenshot({ path: `${shots}/book-${width}.png`, fullPage: true });
    const opened = page.waitForResponse((r) => r.url().endsWith("/analytics/open"));
    await book.getByRole("button", { name: "Open causal book in Strategy Lab" }).click();
    const analysis = await (await opened).json();
    expect(analysis.analytical_provenance.target).toBe("weight_book");
    expect(analysis.analytical_provenance.book_options).toEqual({ execution_lag: 1, cost_bps: 5 });
    await expect(page.getByRole("tab", { name: "Backtest", exact: true })).toHaveAttribute("aria-selected", "true");
    expect(await noOverflow()).toBe(true);
    await page.getByRole("tab", { name: "Script", exact: true }).click();

    // Barrido: misma revisión y mismas entradas; 6 puntos que solo cambian los parámetros.
    await setText(page, "Sweep axes", "lookback = 5, 10, 20\nleverage = 1, 2");
    await expect(page.getByText("6 points · other run parameters stay fixed")).toBeVisible();
    await page.getByRole("button", { name: "Create sweep" }).click();
    await page.getByRole("button", { name: /Run (all|remaining) 6 points/ }).click();
    const comparison = page.getByLabel("Sweep comparison");
    await expect(comparison.getByText("not ranked", { exact: false })).toBeVisible({ timeout: 30_000 });
    const rows = comparison.locator("tbody tr");
    await expect(rows).toHaveCount(6);
    await expect(rows.first()).toContainText("leverage=1 · lookback=5");
    await expect(comparison.getByText("Ready", { exact: true })).toHaveCount(6);
    // Ningún punto se marca como ganador; la única mención es la advertencia sobre elegir el mejor de N.
    await expect(comparison.locator("tbody").getByText(/best|winner|optimal/i)).toHaveCount(0);
    await expect(comparison.getByText(/picking the best of 6 trials/)).toBeVisible();
    await page.screenshot({ path: `${shots}/sweep-${width}.png`, fullPage: true });

    // Walk-forward: selección solo con entrenamiento, resultado fuera de muestra primero.
    await page.getByLabel("Training observations per fold").fill("60");
    await page.getByLabel("Test observations per fold").fill("20");
    await page.getByLabel("Test observations per fold").blur();
    const walkResponse = page.waitForResponse((r) => r.url().endsWith("/walk-forward"));
    await page.getByRole("button", { name: "Run walk-forward" }).click();
    const walk = await (await walkResponse).json();
    expect(walk.causality.verified).toBe(true);
    expect(walk.trials).toBe(6);
    const result = page.getByLabel("Walk-forward result");
    await expect(result.getByText("OOS total return")).toBeVisible();
    await expect(result.getByText("Causal timing verified", { exact: false })).toBeVisible();
    await expect(result.getByText("In-sample reference · not validation")).toBeVisible();
    await expect(result.locator("tbody tr")).toHaveCount(walk.folds.length);
    const download = page.waitForEvent("download");
    await result.getByRole("button", { name: "Export walk-forward JSON" }).click();
    const exported = JSON.parse(readFileSync((await (await download).path())!, "utf-8"));
    expect(exported.report_sha256).toBe(walk.report_sha256);
    expect(await noOverflow()).toBe(true);
    await result.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${shots}/walk-forward-${width}.png`, fullPage: true });
  });
}
