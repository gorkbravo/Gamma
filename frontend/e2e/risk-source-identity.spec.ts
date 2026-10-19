import { expect, test } from "@playwright/test";

// GUA-20260903-7: a Strategy Lab handoff computes the research book but leaves
// the Risk source control untouched, so account movers and concentration rows
// render under a research-book header. Distinctive symbols make the mix visible.

test("a research-book result never renders live-account rows", async ({ page }) => {
  await page.goto("/e2e/risk-handoff-harness.html");

  const source = page.getByLabel("Source");
  await expect(source).toHaveValue("strategy_lab_book");
  await expect(page.getByText("BOOKLEG Gold vs Duration").first()).toBeVisible();

  await expect(page.getByText("ACCTONLY")).toHaveCount(0);
  await expect(page.getByText("ACCTMINOR")).toHaveCount(0);
  await expect(page.getByText("Compute to analyze")).toHaveCount(0);
});

test("moving the selector announces the pending source instead of mixing books", async ({ page }) => {
  await page.goto("/e2e/risk-handoff-harness.html");

  await page.getByLabel("Source").selectOption("portfolio");

  await expect(page.getByText(/Showing BOOKLEG Gold vs Duration\. Compute to analyze Live account portfolio\./)).toBeVisible();
  await expect(page.getByText("ACCTONLY")).toHaveCount(0);
  await expect(page.getByText("ACCTMINOR")).toHaveCount(0);
});

test("computing after a selector change requests the newly selected source", async ({ page }) => {
  await page.goto("/e2e/risk-handoff-harness.html");

  await page.getByLabel("Source").selectOption("portfolio");
  await page.getByRole("button", { name: "Compute Core" }).click();

  await expect
    .poll(() => page.evaluate(() => window.__gammaRiskComputes.at(-1)))
    .toMatchObject({ sourceScope: "portfolio", riskSourceLabel: "Live account portfolio", symbols: ["ACCTONLY", "ACCTMINOR"] });
});

test("the Load Strategy Book shortcut recomputes rather than only reselecting", async ({ page }) => {
  await page.goto("/e2e/risk-handoff-harness.html");

  await page.getByLabel("Source").selectOption("portfolio");
  // Valores de cuenta en los controles: el atajo debe recalcular con los del libro.
  await page.getByLabel("Benchmark", { exact: true }).fill("SPY");
  await page.getByLabel("Lookback").selectOption("252");
  await page.getByRole("button", { name: "Load Strategy Book" }).click();

  await expect(page.getByLabel("Source")).toHaveValue("strategy_lab_book");
  await expect
    .poll(() => page.evaluate(() => window.__gammaRiskComputes.at(-1)))
    .toEqual({
      sourceScope: "research_book",
      riskSourceLabel: "BOOKLEG Gold vs Duration",
      symbols: [],
      benchmarkSymbol: "QQQ",
      lookbackDays: 126,
    });
});

// Revisión 2026-10-15: sin snapshot de cuenta el libro queda seleccionado desde el
// montaje y nunca hay cambio de fuente, así que Risk conservaba SPY/252D.
test("without an account snapshot the book's benchmark and lookback drive the next compute", async ({ page }) => {
  await page.goto("/e2e/risk-handoff-harness.html?snapshot=none");

  await expect(page.getByLabel("Source")).toHaveValue("strategy_lab_book");
  await expect(page.getByLabel("Benchmark", { exact: true })).toHaveValue("QQQ");
  await expect(page.getByLabel("Lookback")).toHaveValue("126");

  await page.getByRole("button", { name: "Compute Core" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__gammaRiskComputes.at(-1)))
    .toMatchObject({ sourceScope: "research_book", benchmarkSymbol: "QQQ", lookbackDays: 126 });
});

// Revisión 2026-10-15: un segundo traspaso con el libro ya seleccionado no adoptaba
// el benchmark ni el lookback del experimento nuevo.
test("a second handoff adopts the new book's controls but keeps edits made on the same book", async ({ page }) => {
  await page.goto("/e2e/risk-handoff-harness.html");

  await expect(page.getByLabel("Benchmark", { exact: true })).toHaveValue("QQQ");
  await page.getByLabel("Benchmark", { exact: true }).fill("TLT");
  await page.getByRole("button", { name: "Compute Core" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__gammaRiskComputes.at(-1)))
    .toMatchObject({ riskSourceLabel: "BOOKLEG Gold vs Duration", benchmarkSymbol: "TLT", lookbackDays: 126 });

  await page.getByTestId("second-handoff").click();
  await expect(page.getByLabel("Source")).toHaveValue("strategy_lab_book");
  await expect(page.getByLabel("Benchmark", { exact: true })).toHaveValue("IWM");
  await expect(page.getByLabel("Lookback")).toHaveValue("504");

  await page.getByRole("button", { name: "Compute Core" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__gammaRiskComputes.at(-1)))
    .toMatchObject({ riskSourceLabel: "BOOKLEG Copper Curve", benchmarkSymbol: "IWM", lookbackDays: 504 });
});
