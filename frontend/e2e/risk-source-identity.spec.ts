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
    .toEqual({ sourceScope: "portfolio", riskSourceLabel: "Live account portfolio", symbols: ["ACCTONLY", "ACCTMINOR"] });
});

test("the Load Strategy Book shortcut recomputes rather than only reselecting", async ({ page }) => {
  await page.goto("/e2e/risk-handoff-harness.html");

  await page.getByLabel("Source").selectOption("portfolio");
  await page.getByRole("button", { name: "Load Strategy Book" }).click();

  await expect(page.getByLabel("Source")).toHaveValue("strategy_lab_book");
  await expect
    .poll(() => page.evaluate(() => window.__gammaRiskComputes.at(-1)))
    .toEqual({ sourceScope: "research_book", riskSourceLabel: "BOOKLEG Gold vs Duration", symbols: [] });
});
