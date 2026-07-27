import { expect, test, type Page } from "@playwright/test";

const harness = "/e2e/portfolio-harness.html";

test("Portfolio exposes mock provenance and independent partial/degraded states", async ({ page }) => {
  await page.goto(harness);

  await expect(page.getByText("Demo portfolio", { exact: true })).toBeVisible();
  const status = page.getByLabel("Portfolio status");
  await expect(status.getByText("Partial quote snapshot", { exact: true })).toBeVisible();
  await expect(status.getByText("Local history is degraded", { exact: true })).toBeVisible();
  await expect(status.getByText("Cash 0% benchmark fallback", { exact: true })).toBeVisible();
  await expect(page.locator(".source-line")).toContainText("MOCK / DEMO");
  await expect(page.locator(".source-line")).toContainText("Mocked");
  await expect(page.getByText("Raw provider diagnostic detail remains in the console.")).toBeHidden();

  const sapRow = page.getByRole("row").filter({ hasText: "SAP" });
  await expect(sapRow.getByText("Missing", { exact: true })).toBeVisible();
});

test("Portfolio distinguishes filter-empty from an empty account", async ({ page }) => {
  await page.goto(harness);

  const filter = page.getByLabel("Filter portfolio positions");
  await filter.fill("ZZZZ");
  await expect(page.getByText("No positions match this filter", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear filter" }).click();
  await expect(page.getByRole("cell", { name: "LMT", exact: true })).toBeVisible();

  await page.goto(`${harness}?scenario=empty`);
  await expect(page.getByText("Account has no positions", { exact: true })).toBeVisible();
  await expect(page.getByText("No positions match this filter", { exact: true })).toBeHidden();
});

test("Portfolio clear-history flow cancels safely and confirms explicitly", async ({ page }) => {
  await page.goto(harness);

  await page.getByRole("button", { name: "Clear Local History" }).click();
  const dialog = page.getByRole("dialog", { name: "Clear local portfolio history?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("History clear cancelled. The local snapshot trail was not changed.")).toBeVisible();
  await expect.poll(() => eventCount(page, "clear_history")).toBe(0);

  await page.getByRole("button", { name: "Clear Local History" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm Clear" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(
    page.getByText("Local history was cleared and the prior trail was archived when present.")
  ).toBeVisible();
  await expect.poll(() => eventCount(page, "clear_history")).toBe(1);
});

test("Portfolio keeps operational detail inside Diagnostics", async ({ page }) => {
  await page.goto(harness);

  await expect(page.getByRole("heading", { name: "System Event Log" })).toBeHidden();
  await page.getByRole("button", { name: "Open Diagnostics" }).click();
  await expect(page.getByRole("heading", { name: "System Event Log" })).toBeVisible();
  await expect(page.getByText("Raw provider diagnostic detail remains in the console.").first()).toBeVisible();

  await page.getByRole("button", { name: "Run Diagnostics" }).click();
  await expect.poll(() => eventCount(page, "run_diagnostics")).toBe(1);
  await expect(page.getByText("Diagnostics run completed.")).toBeVisible();
});

test("Portfolio preserves benchmark and timeframe across refresh and remount", async ({ page }) => {
  await page.goto(harness);

  const benchmark = page.getByLabel("Portfolio performance benchmark");
  const timeframe = page.getByLabel("Portfolio performance timeframe");
  await benchmark.fill("QQQ");
  await benchmark.press("Enter");
  await timeframe.selectOption("3y");

  await expect.poll(() => latestPerformanceRequest(page)).toEqual({
    benchmarkSymbol: "QQQ",
    lookbackDays: 756
  });

  await page.getByRole("button", { name: "Refresh", exact: true }).first().click();
  await expect(benchmark).toHaveValue("QQQ");
  await expect(timeframe).toHaveValue("3y");

  await page.reload();
  await expect(page.getByLabel("Portfolio performance benchmark")).toHaveValue("QQQ");
  await expect(page.getByLabel("Portfolio performance timeframe")).toHaveValue("3y");
});

test("Portfolio remains contained and operable at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(harness);

  await expect(page.getByRole("heading", { name: "Portfolio Performance" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "MOCK / DEMO" })).toBeVisible();
  await expect(page.getByLabel("Filter portfolio positions")).toBeVisible();
  const layout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    hasMojibake: document.body.innerText.includes("\u00c2"),
    keyWidths: Object.fromEntries(
      [".view", ".workspace-grid", ".primary-column", ".table-panel", ".table-wrap", ".messages-panel"].map(
        (selector) => {
          const element = document.querySelector<HTMLElement>(selector);
          return [
            selector,
            element
              ? {
                  width: Math.round(element.getBoundingClientRect().width),
                  scrollWidth: element.scrollWidth,
                  minWidth: getComputedStyle(element).minWidth,
                  gridTemplateColumns: getComputedStyle(element).gridTemplateColumns
                }
              : null
          ];
        }
      )
    )
  }));
  expect(layout.viewport).toBe(390);
  expect(layout.documentWidth).toBe(390);
  expect(layout.hasMojibake).toBe(false);
  for (const selector of [".view", ".workspace-grid", ".primary-column", ".table-panel", ".messages-panel"]) {
    expect(layout.keyWidths[selector]?.width, selector).toBeLessThanOrEqual(390);
  }
  expect(layout.keyWidths[".table-wrap"]?.width).toBeLessThanOrEqual(390);
  expect(layout.keyWidths[".table-wrap"]?.scrollWidth).toBeGreaterThan(
    layout.keyWidths[".table-wrap"]?.width ?? 0
  );
});

async function eventCount(page: Page, type: string) {
  return page.evaluate(
    (eventType) => window.__gammaPortfolioEvents.filter((event) => event.type === eventType).length,
    type
  );
}

async function latestPerformanceRequest(page: Page) {
  return page.evaluate(() => {
    const event = [...window.__gammaPortfolioEvents]
      .reverse()
      .find((candidate) => candidate.type === "reload_performance");
    return event?.payload ?? null;
  });
}
