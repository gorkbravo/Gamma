import { expect, test } from "@playwright/test";

// GUA-20260903-9: the composer draft lived in component state, so leaving the tab
// — including the trip to Risk that the draft's own result triggered — reset the
// builder to the default QQQ/SPY template.

test("an edited composer draft survives leaving and returning to Strategy Lab", async ({ page }) => {
  await page.goto("/e2e/strategy-composer-harness.html");

  const name = page.getByLabel("Name");
  const benchmark = page.getByLabel("Benchmark");
  await expect(name).toHaveValue("Strategy Lab Portfolio");

  await name.fill("Gold vs Duration");
  await benchmark.fill("IEF");
  const firstIdentifier = page.getByPlaceholder("Ticker / contract id").first();
  await firstIdentifier.fill("GLD");
  await firstIdentifier.blur();

  await page.getByTestId("toggle-mount").click();
  await expect(page.getByTestId("away")).toBeVisible();
  await page.getByTestId("toggle-mount").click();

  await expect(page.getByLabel("Name")).toHaveValue("Gold vs Duration");
  await expect(page.getByLabel("Benchmark")).toHaveValue("IEF");
  await expect(page.getByPlaceholder("Ticker / contract id").first()).toHaveValue("GLD");
});

test("a removed leg stays removed across the round trip", async ({ page }) => {
  await page.goto("/e2e/strategy-composer-harness.html");

  const identifiers = page.getByPlaceholder("Ticker / contract id");
  const before = await identifiers.count();
  await page.getByRole("button", { name: "Add Leg" }).click();
  await expect(identifiers).toHaveCount(before + 1);

  await page.getByTestId("toggle-mount").click();
  await page.getByTestId("toggle-mount").click();

  await expect(page.getByPlaceholder("Ticker / contract id")).toHaveCount(before + 1);
});
