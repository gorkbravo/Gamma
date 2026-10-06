import { expect, test } from "@playwright/test";

for (const width of [1440, 1000, 390]) {
  test(`Options captures persist and compare at ${width}px`, async ({ page }, testInfo) => {
    const captures: any[] = [];
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 960 });
    await page.route("**/iv/snapshots**", async (route) => {
      const request = route.request(), url = new URL(request.url());
      if (request.method() === "POST") {
        const capture = { snapshot_id: `${captures.length + 1}`.padStart(32, "0"), captured_at: `2026-10-06T${captures.length ? "15" : "14"}:02:00Z`, surface: request.postDataJSON() };
        captures.unshift(capture); await route.fulfill({ json: capture });
      } else if (url.pathname === "/iv/snapshots") {
        await route.fulfill({ json: { snapshots: captures.map((capture) => ({ ...capture, ...capture.surface })), warnings: [] } });
      } else {
        await route.fulfill({ json: captures.find((capture) => capture.snapshot_id === url.pathname.split("/").at(-1)) });
      }
    });
    await page.goto("/e2e/iv-snapshots-harness.html");
    const panel = page.getByRole("article", { name: "Options snapshot comparison" });
    await expect(panel).toContainText("History starts with your first capture");
    await page.getByRole("button", { name: "Capture displayed surface" }).click();
    await expect(panel).toContainText("Saved locally across restarts");
    await page.getByRole("button", { name: "Advance surface" }).click();
    await page.getByRole("button", { name: "Capture displayed surface" }).click();
    await expect(panel.getByRole("cell", { name: "+2.00 pp", exact: true })).toBeVisible();
    await page.reload();
    await expect(panel.getByRole("cell", { name: "+2.00 pp", exact: true })).toBeVisible();
    await panel.getByText("Capture evidence and pricing assumptions", { exact: true }).click();
    await expect(panel).toContainText("Frozen assumptions");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`comparison-${width}.png`), fullPage: true });
    expect(errors).toEqual([]);
  });
}

test("a failed save keeps retained captures and exposes a retryable error", async ({ page }) => {
  await page.route("**/iv/snapshots**", (route) => route.fulfill(route.request().method() === "POST"
    ? { status: 503, json: { detail: "Storage unavailable" } }
    : { json: { snapshots: [], warnings: ["Unreadable capture; original file retained."] } }));
  await page.goto("/e2e/iv-snapshots-harness.html");
  await page.getByRole("button", { name: "Capture displayed surface" }).click();
  await expect(page.getByRole("alert")).toContainText("Storage unavailable");
  await expect(page.getByRole("button", { name: "Capture displayed surface" })).toBeEnabled();
  await expect(page.getByText("Unreadable capture; original file retained.", { exact: true })).toBeVisible();
});
