import { expect, test } from "@playwright/test";

test("the app shell keeps an explicit Options handoff over an older conversation scope", async ({ page }) => {
  test.setTimeout(60_000);
  await page.addInitScript(() => {
    localStorage.setItem("gamma.workspace.state.v1", JSON.stringify({ workspaceMode: "research", activeTab: "iv", modes: { iv: "strategies" } }));
    localStorage.setItem("gamma.copilot.session", "older-macro");
  });
  const surface = { symbol: "GOOGL", timestamp: "2026-10-04T12:00:00Z", retrieved_at: "2026-10-04T12:00:00Z",
    snapshot_available: true, spot: 337.76, expiries: ["20261120"], strikes: [330, 340], iv_grid: [[0.33, 0.33]],
    points: 2, delayed: true, pairs: [], source_provider: "mock", origin: "playwright.options", freshness_label: "mocked",
    warnings: [], messages: [], collection: null, quality: null };
  const summary = { session_id: "older-macro", title: "Older macro research", active_domain: "macro", turn_count: 1,
    created_at: "2026-09-03T12:00:00Z", updated_at: "2026-09-03T12:00:00Z", warnings: [] };
  let sessionLoaded = false;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.port === "5173") { await route.continue(); return; }
    if (url.pathname === "/system/status") {
      await route.fulfill({ json: { healthy: true, mock_mode: true, app_name: "Gamma", backend: "fixture",
        base_currency: "USD", market_data_mode: "delayed", cached_symbols: [],
        connection: { connected: false, status_text: "Mock", action_text: "Connect", action_enabled: false, active_account: null } } });
    } else if (url.pathname === "/iv/session") {
      await route.fulfill({ json: { running: false, status_text: "Idle", active_symbol: "GOOGL", market_data_mode: "delayed", surface, messages: [] } });
    } else if (url.pathname === "/copilot/sessions/older-macro") {
      sessionLoaded = true;
      await route.fulfill({ json: { session: summary, turns: [{ turn_id: "macro-turn", turn_index: 1, role: "research_agent",
        prompt: "Review CPI", selected_scope_domains: ["macro"], result: { status: "ready", domain: "macro", sources: [],
          tool_traces: [], operator_events: [], warnings: [], card: null } }], memos: [], artifacts: [], context_snapshots: [], storage_warnings: [] } });
    } else if (url.pathname === "/copilot/sessions") await route.fulfill({ json: [summary] });
    else await route.fulfill({ status: 503, json: { detail: "Unavailable fixture provider" } });
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "GOOGL", exact: true })).toBeVisible({ timeout: 30_000 });
  await page.locator("section.view").getByRole("button", { name: "Copilot", exact: true }).click();
  await expect.poll(() => sessionLoaded).toBe(true);
  await expect(page.locator(".context-trigger")).toContainText("Options");
});

for (const width of [1440, 1200, 800]) {
  test(`Options handoff remains usable at ${width}px`, async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 960 });
    await page.goto("/e2e/options-copilot-harness.html");
    await page.getByRole("button", { name: "Put Spread", exact: true }).click();
    await expect(page.locator(".leg-row")).toHaveCount(2);
    await page.screenshot({ path: testInfo.outputPath("options.png") });
    await page.getByRole("button", { name: "Copilot", exact: true }).click();
    await expect(page.locator("textarea")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("copilot.png") });
    expect(errors).toEqual([]);
  });
}

test("a selected expiry and sized spread survive Options → Copilot → Options", async ({ page }) => {
  await page.goto("/e2e/options-copilot-harness.html");
  await page.locator(".builder-controls select").nth(2).selectOption("20270115");
  await page.getByRole("button", { name: "Put Spread", exact: true }).click();
  await page.getByLabel("Contracts per structure").fill("3");
  await page.getByLabel("Contracts per structure").blur();
  const legs = await page.locator(".leg-row strong").allTextContents();
  await page.getByRole("button", { name: "Copilot", exact: true }).click();
  await page.getByRole("button", { name: "Return to Options" }).click();
  await expect(page.getByLabel("Contracts per structure")).toHaveValue("3");
  await expect(page.locator(".builder-controls select").nth(2)).toHaveValue("20270115");
  await expect(page.locator(".leg-row strong")).toHaveText(legs);
});

test("a symbol change clears old legs, marks and sizing", async ({ page }) => {
  await page.goto("/e2e/options-copilot-harness.html");
  await page.getByRole("button", { name: "Put Spread", exact: true }).click();
  await expect(page.locator(".legs-panel")).toContainText("340");
  await page.getByLabel("Contracts per structure").fill("3");
  await page.getByLabel("Contracts per structure").blur();
  await page.getByRole("button", { name: "Load AAPL" }).click();
  await expect(page.locator(".legs-panel")).not.toContainText("340");
  await expect(page.getByLabel("Contracts per structure")).toHaveValue("1");
  await expect(page.getByText("Cleared the GOOGL structure.", { exact: false })).toBeVisible();
});

test("edits to a temporary Copilot option set survive returning to Options", async ({ page }) => {
  await page.goto("/e2e/options-copilot-harness.html?temporary=1");
  await expect(page.locator(".leg-row")).toHaveCount(1);
  await page.getByRole("button", { name: "Put Spread", exact: true }).click();
  await expect(page.locator(".leg-row")).toHaveCount(2);
  await page.getByLabel("Contracts per structure").fill("3");
  await page.getByLabel("Contracts per structure").blur();
  await page.getByRole("button", { name: "Copilot", exact: true }).click();
  await page.getByRole("button", { name: "Return to Options" }).click();
  await expect(page.locator(".leg-row")).toHaveCount(2);
  await expect(page.getByLabel("Contracts per structure")).toHaveValue("3");
});

test("submission and Operator retry retain the exact Options snapshot after background updates", async ({ page }) => {
  const requests: any[] = [];
  let detail: any = { session: { session_id: "options-continuity", title: "Options", active_domain: "iv", turn_count: 0 },
    turns: [], context_snapshots: [], memos: [], artifacts: [], storage_warnings: [] };
  await page.route("**/copilot/**", async (route) => {
    const request = route.request();
    if (request.url().endsWith("/stream")) {
      const payload = request.postDataJSON(); requests.push(payload);
      const result = { domain: "iv", current_tab: "iv", status: requests.length === 1 ? "error" : "ready",
        provider: "mock", model: null, response_id: `response-${requests.length}`, message: "Fixture provider result",
        card: null, sources: [], tool_traces: [], operator_events: [], warnings: [] };
      detail = { ...detail, turns: [{ turn_id: "failed-options", turn_index: 1, session_id: "options-continuity",
        domain: "iv", prompt: payload.prompt, role: payload.role, selected_scope_domains: payload.selected_scope_domains,
        context_snapshot_id: "options-snapshot", context_fingerprint: payload.context_fingerprint, result }],
        context_snapshots: [{ snapshot_id: "options-snapshot", context_fingerprint: payload.context_fingerprint,
          request_context: { context: payload.context, synthesis: null } }] };
      await route.fulfill({ contentType: "application/x-ndjson", body: [
        { run_id: payload.run_id, sequence: 0, event: "run.created", timestamp: "2026-10-04T12:00:00Z", data: { domain: "iv" } },
        { run_id: payload.run_id, sequence: 1, event: result.status === "ready" ? "completed" : "failed",
          timestamp: "2026-10-04T12:00:01Z", data: { status: result.status }, result },
      ].map((event) => JSON.stringify(event)).join("\n") + "\n" });
    } else await route.fulfill({ json: request.url().endsWith("/sessions") ? [detail.session] : detail });
  });
  await page.goto("/e2e/options-copilot-harness.html");
  await page.getByRole("button", { name: "Put Spread", exact: true }).click();
  await page.getByRole("button", { name: "Copilot", exact: true }).click();
  await page.getByRole("button", { name: "Background surface update" }).click();
  await page.getByRole("button", { name: "Operator", exact: true }).click();
  await page.locator("textarea").last().fill("Evaluate this exact GOOGL spread");
  await page.getByRole("button", { name: "Run Operator", exact: true }).click();
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[0].context.iv_state.surface.symbol).toBe("GOOGL");
  expect(requests[0].context.iv_state.workbench.legs).toHaveLength(2);
  expect(requests[0].context.iv_state.workbench.strategy_symbol).toBe("GOOGL");
  expect(requests[1].context).toEqual(requests[0].context);
  expect(requests[1].context_fingerprint).toBe(requests[0].context_fingerprint);
  expect(requests[1].role).toBe("research_operator");
  expect(requests[1].prompt).toBe(requests[0].prompt);
  expect(requests[1].run_id).not.toBe(requests[0].run_id);
});
