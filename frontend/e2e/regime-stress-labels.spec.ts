import { expect, test } from "@playwright/test";

// GUA-20260903-11: over a multi-year sample, "Jun 24" does not say which June,
// and ROLL RET / VOL / BETA / CORR did not say what horizon they measure.

test("regime stress dates carry the year and rolling metrics name their window", async ({ page }) => {
  await page.goto("/e2e/strategy-composer-harness.html?mode=regime_stress");

  const regimePanel = page.locator("article.panel", { hasText: "Recent Regime Read" });
  await expect(regimePanel).toContainText("63-observation window over daily returns");

  const drawdownPanel = page.locator("article.panel", { hasText: "Worst Drawdowns" });
  await expect(drawdownPanel.locator("tbody tr").first()).toContainText(/\d{4}/);

  await expect(regimePanel.getByRole("columnheader", { name: "Roll Ret" })).toHaveAttribute(
    "title",
    "Compounded return over a 63-observation window over daily returns"
  );
  await expect(regimePanel.getByRole("columnheader", { name: "Beta" })).toHaveAttribute(
    "title",
    "Beta versus benchmark over a 63-observation window over daily returns"
  );
});
