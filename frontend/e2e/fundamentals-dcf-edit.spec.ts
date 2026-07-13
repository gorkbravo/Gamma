import { expect, test } from "@playwright/test";

test("Fundamentals company search accepts real input and selects a visible result", async ({ page }) => {
  await page.goto("/e2e/fundamentals-dcf-harness.html");

  const search = page.getByRole("combobox", { name: "Company search" });
  await search.fill("AAPL");
  await expect(search).toHaveAttribute("aria-expanded", "true");
  const result = page.getByRole("option", { name: /AAPL.*APPLE INC/i });
  await expect(result).toBeVisible();
  await result.click();

  await expect
    .poll(() => page.evaluate(() => window.__gammaFundamentalsSelections.at(-1)))
    .toBe("AAPL");
});

test("MSFT-style Fundamentals DCF edits stay targetable, saveable, and recoverable", async ({ page }) => {
  await page.goto("/e2e/fundamentals-dcf-harness.html");

  const saveButton = page.getByRole("button", { name: "Recalculate + Save" });
  await expect(page.getByRole("heading", { name: "Bear / Base / Bull" })).toBeVisible();
  await expect(saveButton).toBeDisabled();

  const wacc = page.getByLabel("WACC (base scenario)");
  const terminalGrowth = page.getByLabel("Terminal growth (base scenario)");
  const revenueGrowth2026 = page.getByLabel("Revenue growth 2026");
  const ebitMargin2028 = page.getByLabel("EBIT margin 2028");
  const revenueProjection2026 = page.getByLabel("Revenue projection 2026");

  await expect(wacc).toHaveAttribute("title", "Editable DCF assumption: WACC (base scenario)");
  await expect(terminalGrowth).toHaveAttribute("title", "Editable DCF assumption: Terminal growth (base scenario)");
  await expect(revenueGrowth2026).toHaveAttribute("title", "Editable DCF assumption: Revenue growth 2026");
  await expect(ebitMargin2028).toHaveAttribute("title", "Editable DCF assumption: EBIT margin 2028");
  await expect(revenueProjection2026).toHaveAttribute("title", "Editable DCF projection override: Revenue projection 2026");
  await expect(revenueProjection2026.locator("xpath=ancestor::td[contains(@class, 'sheet-cell-edit')]")).toBeVisible();

  await revenueGrowth2026.fill("13.5");
  await expect(page.getByText("Pending recalculation")).toBeVisible();
  await expect(saveButton).toBeEnabled();

  await revenueGrowth2026.blur();
  await wacc.fill("8.7");
  await wacc.blur();
  await revenueProjection2026.fill("310,500,000,000");
  await revenueProjection2026.blur();
  await saveButton.click();

  await expect(page.getByText("Pending recalculation")).toBeHidden();
  await expect(saveButton).toBeDisabled();

  await expect
    .poll(() =>
      page.evaluate(() => {
        const save = window.__gammaDcfSaves.at(-1);
        return save
          ? {
              ticker: save.ticker,
              growth2026: save.payload.scenarios.base.assumptions.revenue_growth_pct[0],
              wacc: save.payload.scenarios.base.assumptions.wacc_pct,
              revenueOverride2026: save.payload.scenarios.base.overrides.revenue[0]
            }
          : null;
      })
    )
    .toEqual({
      ticker: "MSFT",
      growth2026: 0.135,
      wacc: 0.087,
      revenueOverride2026: 310_500_000_000
    });

  await terminalGrowth.fill("3.4");
  await expect(page.getByText("Pending recalculation")).toBeVisible();
  await expect(saveButton).toBeEnabled();
  await terminalGrowth.blur();
  await saveButton.click();
  await expect(saveButton).toBeDisabled();

  await page.getByRole("button", { name: "Load" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__gammaDcfSnapshotLoads.at(-1)))
    .toEqual({ ticker: "MSFT", snapshotId: "msft-base-before-edit" });
});
