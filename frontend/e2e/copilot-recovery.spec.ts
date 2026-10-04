import { test, expect, type Page } from "@playwright/test";

async function fixture(page: Page, outcome: "ready" | "interrupted" | "cancelled" = "ready") {
  const decisions: any[] = [];
  let release: (() => void) | undefined;
  let cancelled = false;
  let detail: any;
  await page.route("http://127.0.0.1:8000/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/cancel")) {
      cancelled = true; release?.();
      await route.fulfill({ json: { run_id: "run9", found: true, cancelled: true } }); return;
    }
    if (url.pathname.endsWith("/decision/stream")) {
      decisions.push(route.request().postDataJSON());
      if (!cancelled) await new Promise<void>(resolve => { release = resolve; });
      const prior = detail.turns[0].result;
      const mutation = { ...prior.operator_events[0].payload.mutation, status: decisions.at(-1).decision === "reject" ? "rejected" : "applied" };
      const status = cancelled ? "cancelled" : decisions.length > 1 ? "ready" : outcome;
      const result = { ...prior, status, message: status === "interrupted" ? "Continuation interrupted. Recover this same run." : `Same run ${status}.`,
        operator_events: [{ ...prior.operator_events[0], payload: { mutation } }] };
      detail.turns[0].result = result;
      await route.fulfill({ contentType: "application/x-ndjson", body: [
        { run_id: "run9", sequence: 20 + decisions.length * 10, event: "run.resumed", data: { decision: decisions.at(-1).decision } },
        { run_id: "run9", sequence: 21 + decisions.length * 10, event: status === "interrupted" ? "failed" : cancelled ? "cancelled" : "completed", data: {}, result }
      ].map(event => JSON.stringify({ timestamp: "2026-10-04T12:00:01Z", ...event })).join("\n") + "\n" });
    } else if (url.pathname.endsWith("/sessions/session9")) await route.fulfill({ json: detail });
    else if (url.pathname.endsWith("/sessions")) await route.fulfill({ json: [detail.session] });
    else await route.fulfill({ json: {} });
  });
  return {
    decisions,
    release: async () => {
      await expect.poll(() => release != null).toBe(true);
      const resolve = release!; release = undefined; resolve();
    },
    capture: async () => {
      // Read the fixture's initial persisted turn through its production store.
      detail = await page.evaluate(async () => {
        const { get } = await import("/node_modules/svelte/src/store/index-client.js");
        const { activeCopilotSession } = await import("/src/lib/stores/app.ts");
        return get(activeCopilotSession);
      });
    }
  };
}

for (const width of [1440, 1024, 640]) {
  for (const shelf of [false, true]) {
    test(`approval authority, keyboard, Stop and layout ${shelf ? "shelf" : "tab"} ${width}px`, async ({ page }, info) => {
      const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
      await page.setViewportSize({ width, height: 960 });
      const server = await fixture(page, "cancelled");
      await page.goto(`/e2e/copilot-recovery-harness.html${shelf ? "?shelf" : ""}`);
      await server.capture();
      if (!shelf) await page.getByRole("button", { name: "Agent", exact: true }).click();
      await expect(page.getByRole("button", { name: "Approve and continue", exact: true })).toBeDisabled();
      const operator = shelf ? page.getByRole("tab", { name: "Research Operator", exact: true }) : page.getByRole("button", { name: "Operator", exact: true });
      await operator.focus(); await page.keyboard.press("Enter");
      await expect(page.getByText("Operator selected.", { exact: false })).toBeVisible();
      const comparison = page.getByRole("region", { name: "DCF before-and-after comparison" });
      await comparison.focus(); await expect(comparison).toBeFocused();
      await page.keyboard.press("ArrowRight");
      await expect(page.getByRole("cell", { name: "8%", exact: true })).toBeVisible();
      await expect(page.getByRole("cell", { name: "9%", exact: true })).toBeVisible();
      await page.screenshot({ path: info.outputPath("approval.png"), fullPage: true });
      const approve = page.getByRole("button", { name: "Approve and continue", exact: true });
      await approve.focus(); await page.keyboard.press("Enter");
      await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible();
      const stop = page.getByRole("button", { name: "Stop", exact: true });
      await stop.focus(); await page.keyboard.press("Enter");
      await expect(page.getByText("Same run cancelled.", { exact: true })).toBeVisible();
      expect(server.decisions).toHaveLength(1);
      expect(server.decisions[0]).toMatchObject({ role: "research_operator", mutation_id: "mutation9", context_fingerprint: "original-context" });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
  }
}

test("interrupted approval recovers the same persisted turn without a new Retry request", async ({ page }) => {
  const server = await fixture(page, "interrupted");
  await page.goto("/e2e/copilot-recovery-harness.html"); await server.capture();
  await page.getByRole("button", { name: "Operator", exact: true }).click();
  await page.getByRole("button", { name: "Approve and continue", exact: true }).click();
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible(); await server.release();
  const recover = page.getByRole("button", { name: "Continue interrupted run", exact: true });
  await expect(recover).toBeEnabled();
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
  await recover.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible(); await server.release();
  await expect(page.getByText("Same run ready.", { exact: true })).toBeVisible();
  expect(server.decisions.map(item => item.decision)).toEqual(["approve", "recover"]);
});

test("shelf rejection continues and promotes its original evidence to the dedicated tab", async ({ page }) => {
  const server = await fixture(page);
  await page.goto("/e2e/copilot-recovery-harness.html?shelf"); await server.capture();
  await page.getByRole("tab", { name: "Research Operator", exact: true }).click();
  await page.getByRole("button", { name: "Reject and continue", exact: true }).click();
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible(); await server.release();
  await expect(page.getByText("Same run ready.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Open in Copilot", exact: false }).click();
  await expect(page.getByText("Same run ready.", { exact: true })).toBeVisible();
  expect(server.decisions.map(item => item.decision)).toEqual(["reject"]);
});
