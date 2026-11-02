// Visual refresh guardrail (docs/visual_refresh_plan.md, V4): data rows fully
// visible above a 780px fold in a 1280px-wide window, with the navigation
// drawer closed (its default), on Sitrep, Commodities › Curves & Spreads,
// Options › Overview and Risk › Overview.
//
// Run against a mock-mode backend and a dev or preview server:
//   node scripts/measure-fold-rows.mjs <baseUrl> <dark|light> <outDir> [runs=3] [baseline.json]
// Writes <outDir>/rows-<theme>.json and one fold screenshot per view. With a
// baseline report from an earlier run, it also prints each view's ratio and
// fails (exit code 2) when the theme's total falls below 95% of the baseline.
//
// A data row is a table body row (tbody > tr, without .empty-row), a Sitrep
// tape or follow-up row (.tape-row), a news row (.news-row) or a ranked bar
// row (BarRankChart). It counts when its whole box lies above the fold and
// inside every clipping ancestor, and it is not hidden. Each run starts from a
// fresh browser context; the report keeps each view's median across runs,
// because Sitrep data can arrive late.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const [baseUrl = "http://localhost:5174/", theme = "dark", outDir = ".", runsArg = "3", baselineFile] = process.argv.slice(2);
const runs = Number(runsArg);
const WIDTH = 1280;
const FOLD = 780;
const GUARDRAIL = 0.95;
// Risk has no book in the Research view under mock data, so it is measured in
// the Portfolio view after a Compute Core pass on the mock account.
const TARGETS = [
  { view: "Research View", tab: "SITREP", mode: null, key: "sitrep" },
  { view: "Research View", tab: "COMMODITIES", mode: "CURVES & SPREADS", key: "commodities" },
  { view: "Research View", tab: "OPTIONS", mode: "OVERVIEW", key: "options" },
  { view: "Portfolio View", tab: "RISK", mode: "OVERVIEW", key: "risk", compute: "COMPUTE CORE" },
];
const SELECTORS = {
  table: "tbody > tr:not(.empty-row)",
  tape: ".tape-row",
  news: ".news-row",
  rank: ".chart > .row:has(> .track)",
};
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Waits until the main region stops changing for quietMs.
async function settle(page, quietMs = 2500, maxMs = 25000) {
  const start = Date.now();
  let last = "";
  let stableSince = Date.now();
  while (Date.now() - start < maxMs) {
    const signature = await page.evaluate(() => {
      const main = document.querySelector("main") || document.body;
      return `${main.querySelectorAll("*").length}:${main.innerText.length}:${document.documentElement.scrollHeight}`;
    });
    if (signature !== last) {
      last = signature;
      stableSince = Date.now();
    } else if (Date.now() - stableSince >= quietMs) {
      return;
    }
    await wait(300);
  }
}

// Labels are compared upper-cased, so a sentence-case label still matches.
const clickByText = (page, selector, text) =>
  page.evaluate(([sel, wanted]) => {
    const element = [...document.querySelectorAll(sel)].find(
      (candidate) => candidate.textContent.trim().replace(/\s+/g, " ").toUpperCase() === wanted
    );
    if (!element) return false;
    element.click();
    return true;
  }, [selector, text]);

function countRows(page) {
  return page.evaluate(([selectors, fold, width]) => {
    const fullyVisible = (element) => {
      const box = element.getBoundingClientRect();
      if (box.width <= 0 || box.height <= 0) return false;
      if (getComputedStyle(element).visibility === "hidden") return false;
      let top = 0;
      let bottom = Math.min(fold, innerHeight);
      let left = 0;
      let right = width;
      for (let ancestor = element.parentElement; ancestor && ancestor !== document.documentElement; ancestor = ancestor.parentElement) {
        const style = getComputedStyle(ancestor);
        if (style.display === "none" || style.visibility === "hidden") return false;
        const clip = ancestor.getBoundingClientRect();
        if (style.overflowY !== "visible") {
          top = Math.max(top, clip.top);
          bottom = Math.min(bottom, clip.bottom);
        }
        if (style.overflowX !== "visible") {
          left = Math.max(left, clip.left);
          right = Math.min(right, clip.right);
        }
      }
      // Half-pixel tolerance for subpixel layout.
      return box.top >= top - 0.5 && box.bottom <= bottom + 0.5 && box.right > left && box.left < right;
    };
    const result = {};
    const seen = new Set();
    for (const [name, selector] of Object.entries(selectors)) {
      const rows = [...document.querySelectorAll(`main ${selector}`)].filter((element) => !seen.has(element));
      rows.forEach((element) => seen.add(element));
      result[name] = rows.filter(fullyVisible).length;
    }
    result.total = Object.values(result).reduce((sum, value) => sum + value, 0);
    return result;
  }, [SELECTORS, FOLD, WIDTH]);
}

async function measureRun(browser, run) {
  const context = await browser.newContext({ viewport: { width: WIDTH, height: FOLD }, deviceScaleFactor: 1, reducedMotion: "reduce" });
  await context.addInitScript((value) => {
    try {
      localStorage.setItem("gamma.theme", value);
    } catch {
      // Storage may be unavailable; the app then uses its default theme.
    }
  }, theme);
  const page = await context.newPage();
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  // The first-run setup dialog opens without a setup.json; close it unsaved.
  const close = page.getByRole("button", { name: "Close setup" });
  const closeSetup = async () => {
    await wait(2000);
    if (await close.isVisible().catch(() => false)) await close.click();
  };
  await closeSetup();
  let currentView = null;
  const counts = {};
  for (const target of TARGETS) {
    if (currentView !== target.view) {
      if (currentView) await page.getByRole("button", { name: "Change View" }).click({ timeout: 30000 });
      await page.getByRole("button", { name: target.view }).click({ timeout: 30000 });
      await closeSetup();
      currentView = target.view;
    }
    if (!(await clickByText(page, "button.tab-button", target.tab))) throw new Error(`tab not found: ${target.tab}`);
    await settle(page);
    if (target.mode && !(await clickByText(page, "main .mode-bar .mode-btn", target.mode))) throw new Error(`mode not found: ${target.mode}`);
    if (target.compute) {
      await settle(page);
      if (!(await clickByText(page, "main button", target.compute))) throw new Error(`action not found: ${target.compute}`);
      await settle(page, 3000, 40000);
    }
    await page.mouse.move(WIDTH - 1, FOLD - 1);
    await settle(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    counts[target.key] = await countRows(page);
    if (run === 0) {
      await page.screenshot({ path: path.join(outDir, `fold-${theme}-${target.key}.png`), animations: "disabled", caret: "hide" });
    }
    console.log(theme, run, target.key, JSON.stringify(counts[target.key]));
  }
  await context.close();
  return counts;
}

const median = (values) => [...values].sort((a, b) => a - b)[Math.floor((values.length - 1) / 2)];

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
const report = { baseUrl, theme, viewport: `${WIDTH}x${FOLD}`, runs: [], views: {}, ranges: {} };
try {
  for (let run = 0; run < runs; run++) report.runs.push(await measureRun(browser, run));
} finally {
  await browser.close();
}
for (const target of TARGETS) {
  const values = report.runs.map((counts) => counts[target.key].total);
  report.views[target.key] = median(values);
  report.ranges[target.key] = [Math.min(...values), Math.max(...values)];
}
report.total = Object.values(report.views).reduce((sum, value) => sum + value, 0);
writeFileSync(path.join(outDir, `rows-${theme}.json`), JSON.stringify(report, null, 2));
console.log("rows", theme, JSON.stringify(report.views), "total", report.total);

if (baselineFile) {
  const baseline = JSON.parse(readFileSync(baselineFile, "utf8"));
  for (const target of TARGETS) {
    const before = baseline.views[target.key];
    const after = report.views[target.key];
    console.log(`${target.key}: ${after} / ${before} (${before ? ((after / before) * 100).toFixed(1) : "n/a"}%)`);
  }
  const ratio = report.total / baseline.total;
  const pass = ratio >= GUARDRAIL;
  console.log(`total: ${report.total} / ${baseline.total} (${(ratio * 100).toFixed(1)}%) ${pass ? "PASS" : "FAIL"} at ${GUARDRAIL * 100}%`);
  if (!pass) process.exitCode = 2;
}
