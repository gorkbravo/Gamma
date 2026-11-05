import { expect, test } from "@playwright/test";

/* Visual baselines (V6, docs/visual_refresh_plan.md): fixture-driven e2e
   harness pages in both themes, full page at 1440×900 and DPR 1, so a token
   or primitive change that moves pixels fails a comparison instead of
   drifting silently.

   - Only the dev server is reachable: every other request is aborted, so the
     fixtures are the whole state and no backend or provider is needed.
   - The harness pages do not run the app's theme bootstrap, so the theme is
     set on <html> after load, as appearance.ts would.
   - The PNGs are platform-specific (…-chromium-win32.png). After a deliberate
     visual change, regenerate them with
       npx playwright test e2e/visual.spec.ts --update-snapshots
     and review the image diff before committing it. */

const PAGES = [
  ["fundamentals-dcf", "/e2e/fundamentals-dcf-harness.html"],
  ["iv-snapshots", "/e2e/iv-snapshots-harness.html"],
  ["strategy-experiments", "/e2e/strategy-experiments-harness.html?fixture=1"],
  ["script-analytics", "/e2e/script-analytics-harness.html"],
  ["copilot-recovery", "/e2e/copilot-recovery-harness.html"],
  ["options-copilot", "/e2e/options-copilot-harness.html"],
] as const;

for (const theme of ["dark", "light"] as const) {
  for (const [name, path] of PAGES) {
    test(`${name} renders unchanged (${theme})`, async ({ page, baseURL }) => {
      const devHost = new URL(baseURL ?? "http://127.0.0.1:5173").host;
      await page.route((url) => url.host !== devHost, (route) => route.abort());
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(path);
      await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), theme);
      await page.evaluate(() => document.fonts.ready);
      // Let aborted requests settle into their stable error or empty states.
      await page.waitForLoadState("networkidle");
      await page.mouse.move(1439, 899);
      await expect(page).toHaveScreenshot(`${name}-${theme}.png`, {
        fullPage: true,
        animations: "disabled",
        caret: "hide",
        maxDiffPixelRatio: 0.002,
      });
    });
  }
}
