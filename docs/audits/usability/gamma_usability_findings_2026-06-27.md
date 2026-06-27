# Gamma Usability Findings — 2026-06-27

Date: 2026-06-27
Audience: future AI agents and contributors improving Gamma
Mode: full
Data: live IBKR, account U15779203, market data `auto` (delayed snapshot; weekend session — last trading day Fri 2026-06-26)
Context: Live trade-idea audit run on a Saturday evening. Two evidenced theses attempted (a Nikkei single-day dislocation; a precious-metals selloff). Both dead-ended on data-trust problems — and the second uncovered a P0 in how the Commodities tab computes its headline "% CHG". Builds on `gamma_usability_findings_2026-06-15.md`.

## Audit Setup
- Backend: FastAPI `127.0.0.1:8000`; Frontend: Vite `127.0.0.1:5173`; session header `X-Gamma-Session`.
- IBKR: account `U15779203`, connected via TWS on port 7496 (`market_data_mode=auto`), `MOCK_DATA=false`. Live-IBKR precondition check passed (exit 0).
- Operator note: the stack was not running at session start and `.env` had no `GAMMA_SESSION_TOKEN`. Pinned a dev token in `.env` (matching the existing `frontend/.env.local` token), started backend + frontend, and toggled the IBKR connection via `POST /system/connection/toggle` before auditing.
- Tabs exercised: Sitrep, Equity Research, Commodities, Fundamentals, Copilot (inline dock). Touched via provenance/API cross-checks: Macro (FX), Prediction Markets (auto-loaded). **Out of scope this run:** Strategy Lab, Risk, Options, Crypto, Sealanes, Macro UI, Portfolio.
- Outside tools used: none. All cross-checks were done inside Gamma or against Gamma's own backend payloads. (Weekend timing means several live feeds were stale-by-design; flagged as coverage, not defects, where relevant.)

## Regression Delta (vs 2026-06-15)

| ID | Finding | Prior status | This run | Evidence |
| --- | --- | --- | --- | --- |
| GUA-0615-rank | Fundamentals exact-ticker ranking (exact MSFT below noisy matches) | Fixed 2026-06-27 | **Confirmed fixed** | `GET /fundamentals/search?query=MSFT` → row 1 = `MSFT / MICROSOFT CORP`; `AAPL` → row 1 = `Apple Inc.` |
| GUA-0615-search | Fundamentals search-state ("No SEC matches" flash during refresh) | Fixed 2026-06-27 | **Not retested** (dropdown not drivable via synthetic input) | search dropdown never opened under programmatic value-set; backend ranking confirmed |
| GUA-0615-dcf | DCF editable-cell clarity / dirty-on-input / labels | Implemented 06-23, Playwright 06-27 | **Not retested this run** (automation friction loading active company) | `/fundamentals/MSFT/dcf` payload intact (3 scenarios, 2026–2030); existing Playwright/SSR coverage stands |
| GUA-0615-copilot | Copilot stalls indefinitely on `GENERATING…`, planner-only | Needs browser retest | **Improved / likely fixed** | UI Generate → `POST /copilot/research-card → 200`; direct API returns explicit `status:"error"` card. No indefinite GENERATING observed |
| GUA-0615-copilot-dup | Duplicate `COPILOT` accessible name collision | Open (P2 a11y) | **Appears fixed** | only one `COPILOT` button found in DOM this run |
| GUA-0615-basis | Commodity price-basis reconciliation (`e032af9`) | Implemented in part | **Partially / regressed-adjacent** | basis fields present per row, but the *change* computation is broken — see GUA-20260627-1 (new P0) |
| GUA-0615-slrisk | Strategy Lab → Risk research-book handoff (`67972ee`) | Complete | **Not retested** (out of scope) | — |
| GUA-0615-pmintent | Prediction-market intent search (`fcb7a5c` related-links) | Partially improved | **Not retested** | Sitrep auto-loaded `polymarket:540844` (an oil market); intent search not exercised |

New positive observation: the **focal-ticker chip carried EWJ from Equity Research into Fundamentals** and auto-loaded `/fundamentals/EWJ/*` — cross-tab single-name context works.

## Thesis Log

### Thesis 1: Nikkei's −4.15% single-day drop is a tradable Japan-specific dislocation
- One-line thesis: Japanese equities fell far harder than the rest of the world on 2026-06-26, suggesting either a fade (mean-reversion bounce) or the start of a Japan/yen-driven derisking.
- Signal that sparked it: **Sitrep → Worldwide Indices**, Nikkei 225 `−4.2%` while the US tape was flat. Captured first via backend before writing the thesis: `GET /research/overview?universe_id=global_indices&surface=sitrep` → `^N225 total_return −0.04153 (−4.15%)`, `relative_return vs SPY −3.43%`, `latest_price 69,360.88`, `observation_count 1`, `source_provider yfinance`, `retrieved_at 2026-06-27T20:20:15`, freshness "historical". US: S&P −0.0%, DJIA −0.1%, Nasdaq −0.2%; Europe −0.5% to −1.3%.
- Steps taken:
  1. **Sitrep:** read the worldwide-indices board — Nikkei the clear outlier (−4.2% vs flat US). worked.
  2. **Macro (API):** pulled the yen to test carry-unwind — `GET /macro/series/fx-usdjpy/history` (source `ibkr`): 6/25 `161.79` → 6/26 `161.73` (−0.04%). The yen **did not** rally. A real −4% Nikkei risk-off day almost always comes with a sharp yen bid. partial (had to leave the Sitrep UI: its FX strip showed N/A — see GUA-20260627-4).
  3. **Sitrep → News:** scanned `GET /news/latest` — zero Japan-specific headlines; feed dominated by US personal-finance filler. No catalyst. worked (but unhelpful).
  4. **Equity Research → Scope:** built a Single-Ticker scope on `EWJ` (US-listed Japan proxy) to cross-check the cash-index print. Ran analysis: TR 36.80% / β 0.885 / vol 22.06% / maxDD −14.45% over 317 obs vs SPY. worked — but it returned **lookback aggregates only, not the latest daily move**, so it could not corroborate a one-day dislocation. partial.
- Outcome: **abandoned.** The signal could not be corroborated anywhere inside Gamma — flat yen (IBKR), no Japan news, flat US / mild-Europe tape, and no fast daily-move proxy. Combined with the yfinance "unofficial source" warning, the −4.15% is as likely a data artifact as a real event. A thesis you can't corroborate in-app isn't a trade.

### Thesis 2: A broad precious-metals selloff is underway — fade or follow?
- One-line thesis: gold/silver are selling off (news-confirmed); if the move is real and broad, it implies a risk/liquidity event worth expressing.
- Signal that sparked it: **Sitrep → News** headline *"Why a selloff in gold and silver is dragging bitcoin down"* (captured before thesis), then **Commodities → Overview matrix** (captured before thesis): Silver `−16.70%`, Brent `−10.30%`, WTI `−9.86%`, Platinum `−8.99%`, Copper `−6.78%`, Gold `−6.07%`, Aluminum `−5.79%` — all IBKR front futures. Screenshot captured 2026-06-27.
- Steps taken:
  1. **Commodities → Overview:** read the matrix. Noticed every **IBKR front-future** row was down 6–17% while every **FRED spot-proxy** row was *up* (Iron +2.07%, Lead +2.90%, Nickel +5.68%, Tin +8.95%, Zinc +3.08%). A real metals crash would not split cleanly along data-source lines. worked — and immediately suspicious.
  2. **Commodities → Term Structure chart:** the "Current curve" (blue) sat ~8% below the "Previous curve" (gold dashed) across the strip — the visual source of the negative % CHG. worked.
  3. **Backend cross-check:** `POST /commodities/workspace` with `force_refresh:false` → `latest_change`/`latest_change_pct` **null** for SI/CL/GC at every level (`market_summaries`, `overview.matrix_rows`, and curve `nodes[].previous_price`). With `force_refresh:true` → the changes appear and **exactly match the UI** (SI −0.167, CL −0.0986, GC −0.0607, BZ −0.103). All nodes are `ibkr_cached` ("restored from Gamma's local curve snapshot cache; no fresh market-data line was used"). blocked — the signal is an artifact.
  4. **Sanity reference:** no daily spot/history series exists for IBKR-futures metals (`price_histories` only covers EIA energy + FRED base metals), so Gamma offers no in-app way to verify the curve-derived move. blocked (see GUA-20260627-2).
- Outcome: **abandoned (signal invalid).** The "precious-metals crash" is a computation artifact: the headline % CHG differences the freshly-fetched curve against a stale cached prior-run curve and labels multi-day/cross-session drift as a current move. A −16.7% one-day silver print with no news and no FX/base-metal corroboration is not real. This is logged as the run's P0 (GUA-20260627-1).

## Trade Verdict
No trade taken. Both candidate trades were killed not by market logic but by **data trust**:
- Thesis 1 (Japan): if the −4.15% were real and yen-stable, a small mean-reversion long via `EWJ` (US-listed, dollar-clean) sized to event risk would be the cleanest expression — but it requires corroboration Gamma could not provide on a weekend. Verdict: pass; revisit on a weekday when EWJ's US-session print and a daily-move view are available.
- Thesis 2 (metals): the trade evaporates once the −16.7% is shown to be an artifact. What would have made it real: a genuine prior-settlement reference showing the move, plus base-metals and bitcoin confirming. None present. Verdict: no trade; the finding is the bug.

## Usability Report

### What worked well
- **Cross-asset Sitrep board** surfaced a genuine outlier (Nikkei) in one glance, and **provenance is everywhere** — `source_provider`, `retrieved_at`, `freshness_label`, and explicit "yfinance is unofficial" warnings let me *distrust* a number intelligently. The provenance discipline is what made both dead-ends productive instead of misleading.
- **Equity Research Scope (Single Ticker)** ran an `EWJ`-vs-SPY analysis cleanly with dense, labeled metrics (TR/β/vol/maxDD/correlation, aligned-observation counts).
- **Focal-ticker chip cross-tab carry** (EWJ → Fundamentals auto-load) worked without manual re-entry.
- **Commodities provenance** was good enough to *debug the Commodities bug* — basis labels, `ibkr_cached` notes, and contract symbols (SIN6/CLQ6/GCN6) made the artifact diagnosable. The transparency is a strength even where the math is wrong.
- **Copilot no longer hangs:** the research-card request reached a terminal state (200 card in the UI, explicit error cards via API). The prior indefinite-`GENERATING…` P0 was not reproduced.

### Friction points (ranked)

1. **GUA-20260627-1 (P0) — Commodities "% CHG" is computed against a stale cached curve and presents cross-session drift as a daily move.** Blocked Thesis 2 step 1–3. The Overview matrix showed Silver −16.70%, Brent −10.30%, WTI −9.86%, Gold −6.07%, Platinum −8.99%, Copper −6.78% — none reproducible from the backend without `force_refresh:true`, at which point they match exactly. The "previous curve" is a prior-run cached snapshot of unknown vintage, not a prior settlement; on a weekend both curves are `ibkr_cached`. Acceptance criteria: (a) % CHG must reference a real prior settlement/close with a visible timestamp, or render `N/A`; (b) never difference two cached snapshots of unknown/mismatched vintage; (c) when the IBKR-futures rows move uniformly opposite to FRED-proxy rows, suppress or warn rather than display; (d) the term-structure "Previous curve" overlay must label its as-of date.
2. **GUA-20260627-3 (P1) — No fast in-app corroboration path for a single-day index dislocation.** Blocked Thesis 1 step 4. To sanity-check Nikkei −4.15% I needed (a) the yen on the same screen (Sitrep FX strip was N/A), (b) a US-listed proxy's *latest daily* move (Equity Research Scope shows only lookback aggregates), and (c) a relevant headline (none). Acceptance criteria: surface a latest-day return alongside lookback metrics in Scope; let a Sitrep tile pivot to a quick proxy/daily view; keep the FX strip populated from the same live source Macro uses.
3. **GUA-20260627-2 (P1) — IBKR-futures commodities have no daily spot/history series to validate curve-derived numbers.** Contributed to Thesis 2 step 4. `price_histories` covers EIA energy + FRED base metals but not gold/silver/platinum/copper. Acceptance criteria: attach a spot or front-continuous daily history (or a clear "no daily reference available") to each IBKR-futures row so the headline change can be cross-checked.
4. **GUA-20260627-4 (P2, needs confirmation) — Sitrep FX strip shows N/A while Macro FX (IBKR) returns live values.** Sitrep `FX PAIRS` (labeled "Macro / IBKR") rendered `N/A` for all pairs, yet `GET /macro/series/fx-usdjpy/history` (source `ibkr`) returned 161.7-handle values. Likely the Sitrep FX strip pulls from the weekend-empty yfinance provider (`SITREP_MARKET_DATA_PROVIDERS=yfinance`) while Macro uses IBKR — a provider-wiring inconsistency rather than missing data. Confirm on a weekday before treating as a hard defect. Acceptance: Sitrep FX should fall back to the IBKR series Macro already has, or label the source/staleness.
5. **GUA-20260627-5 (P2) — Sitrep stays in a perpetual "REFRESHING" / "US EQUITY TAPE UNAVAILABLE" state after data has loaded.** The indices/news populated but the header spinner never cleared; `preview_screenshot` timed out only on Sitrep (worked on every other tab), consistent with a never-idle animation/retry loop on the unavailable US equity tape. Acceptance: clear the loading indicator once data is present; bound retries; show "tape unavailable (market closed)" as a terminal state, not a permanent spinner.
6. **GUA-20260627-6 (P2, accessibility/automation) — several controls aren't drivable by synthetic events.** The `COPILOT` nav tab didn't switch views under dispatched pointer/click events; the Fundamentals search dropdown didn't open under programmatic value-set; tab keybindings exist for `Ctrl+1..9` but tab 10 (Copilot) has no `Ctrl+0`. A human with a mouse/keyboard sidesteps all of these, so this is an agent/a11y bucket, not a human blocker. (Net positive: the prior duplicate-`COPILOT`-name collision now resolves to a single button.)

### Gaps
- A commodity headline change needs a **first-class prior-settlement reference** (contract, settlement date, prior close) instead of an opportunistic curve diff. This is the same class of problem the basis work (`e032af9`) targeted, one level up: the *time reference* of the change, not the *instrument* basis.
- Sitrep tiles need a **"this is stale because the market is closed" state** distinct from "unavailable" and distinct from a live spinner.
- Single-day vs lookback is a recurring blind spot: Equity Research, Sitrep, and Commodities each express change on a different time basis with no unifying "as-of / period" label the analyst can trust at a glance.

### Cross-tab coherence
- Worked: focal-ticker chip (EWJ) → Fundamentals auto-load.
- Dropped / not exercised: Equity Research scope (EWJ) did not pre-seed Fundamentals' active company (a human must still pick the dropdown result); Strategy Lab/Risk/Options paths out of scope this run.
- The bigger coherence issue this run was **temporal**, not navigational: the same asset's "change" means different things (and is computed against different baselines) across Sitrep (yfinance DoD), Equity Research (lookback), and Commodities (cached-curve diff).

### Copilot evaluation
- Prompt tried (UI inline dock, Commodities context selected): *"Using the loaded Commodities context, is the reported Silver −16.70% and WTI −9.86% a real one-day move, or an artifact of comparing the current curve against a stale cached previous curve? State what would confirm or reject it."* → `POST /copilot/research-card → 200` (provider `openai_responses`). No indefinite `GENERATING…`. Card rendered but its text was not scrapable via my DOM queries (drawer collapsed before capture).
- Direct API probe: `POST /copilot/research-card {domain:"macro"|"commodities", prompt}` resolved to `domain:"portfolio"` and returned a clean `status:"error"` card ("Portfolio copilot requires a portfolio snapshot") — i.e. the explicit-failure-card behavior the prior report asked for is present, but the raw endpoint appears to derive the effective domain from request **context** rather than the `domain` field (a minor API-contract observation; the UI supplies that context).
- Net: the P0 stall is resolved; **whether Copilot correctly grounds and flags the stale-curve artifact was not verified this run** (see below).

## What Could Not Be Proven This Run
- **Whether the Nikkei −4.15% and the gold/silver moves are real or stale.** yfinance is flagged unofficial; IBKR rows are `ibkr_cached`. On a weekend with no fresh ticks, I can show the Commodities change is an artifact (it only appears on force-refresh, diffing cached snapshots) but cannot independently price Friday's true closes from inside Gamma.
- **Copilot's grounded synthesis content/accuracy.** The UI card returned 200 but I could not capture its text; the raw API couldn't be coerced into the commodities/macro domain without full UI context. So I can confirm "it completes" but not "it reasoned correctly about the artifact."
- **DCF editable-cell behavior and Fundamentals search-state transitions** — not reproduced via this automation harness (dropdown/active-company selection didn't fire under synthetic input). Existing Playwright/SSR coverage is the current evidence, not this run.
- **Weekday behavior** of the Sitrep FX strip, the perpetual-REFRESHING state, and whether live ticks change the Commodities change computation — all should be re-checked when markets are open.

## Scoring

| Category | Score | Δ vs prior | Rationale (one sentence) |
| --- | ---: | :--: | --- |
| Data breadth | 8/10 | = | Same wide cross-asset coverage; nothing missing that a thesis demanded. |
| Data depth / drill-down | 7/10 | = | Deep where it counts, but no daily reference for IBKR-futures commodities and lookback-only Scope hurt single-day work. |
| Analytical tooling | 7/10 | −1 | Scope/DCF remain strong, but the Commodities change computation actively produces wrong analytics. |
| Copilot usefulness | 6/10 | +1 | Terminal states fixed (no more infinite GENERATING); grounded-content quality still unproven. |
| Cross-tab workflow / state continuity | 5/10 | = | Focal-chip carry works; temporal/period inconsistency across tabs is the new coherence gap. |
| Visual density & terminal feel | 8/10 | = | Dense, provenance-rich, readable treemaps and matrices. |
| Speed to insight | 5/10 | −1 | Two theses stalled on corroboration friction (FX N/A, lookback-only, stuck refresh). |
| Overall (gestalt) | 6/10 | −1 | A genuine P0 that fabricates commodity moves outweighs the real Copilot/search fixes this run. |

## Prioritized Follow-Up

### P0 — GUA-20260627-1: Fix Commodities headline "% CHG"
- Problem: % CHG (and the term-structure "Previous curve") is computed by differencing the current curve against a stale cached prior-run curve; it only materializes on `force_refresh`, is null otherwise, and produced impossible uniform moves (Silver −16.70%, Brent −10.30%, …) split exactly along IBKR-vs-FRED source lines.
- Acceptance criteria: change references a real prior settlement/close with a visible as-of timestamp, or renders `N/A`; never diff two cached snapshots of unknown vintage; term-structure overlay labels the previous curve's date; add a guard/warning when all IBKR-futures rows move uniformly opposite the FRED-proxy rows.
- Status: Open (new).

### P1 — GUA-20260627-2: Daily reference for IBKR-futures commodities
- Problem: no spot/daily history for gold/silver/platinum/copper to validate curve-derived numbers.
- Acceptance: attach a spot or front-continuous daily series (or an explicit "no daily reference") to each IBKR-futures row.
- Status: Open (new).

### P1 — GUA-20260627-3: Single-day corroboration path
- Problem: reacting to a one-day index dislocation has no fast in-app cross-check (FX strip N/A, Scope shows lookback only, no event search from a tile).
- Acceptance: latest-day return shown beside lookback metrics in Scope; Sitrep tile → quick proxy/daily view; consistent "as-of / period" labeling across Sitrep/Equity Research/Commodities.
- Status: Open (new).

### P2 — GUA-20260627-4: Sitrep FX strip source
- Problem: Sitrep FX `N/A` while Macro FX (IBKR) has live values.
- Acceptance: Sitrep FX falls back to the IBKR series Macro uses, or labels provider/staleness; confirm on a weekday.
- Status: Open (needs confirmation).

### P2 — GUA-20260627-5: Sitrep perpetual REFRESHING / unavailable-tape state
- Problem: spinner never clears after data loads; US equity tape stuck "UNAVAILABLE" with ongoing retries (also blocks screenshots).
- Acceptance: clear indicator once data present; bound retries; terminal "market closed" state.
- Status: Open (new).

### P2 — GUA-20260627-6: Agent/a11y-unfriendly controls
- Problem: COPILOT tab + Fundamentals search dropdown not drivable by synthetic events; no `Ctrl+0` for tab 10.
- Acceptance: nav/search controls respond to standard events and expose stable roles; add a keybinding for the Copilot tab.
- Status: Open (carryover bucket; duplicate-COPILOT-name sub-issue appears fixed).

## Guidance For Future Agents
- The single highest-value fix is GUA-20260627-1: a research terminal that silently shows a −16.7% silver "day" that never happened is worse than one that shows `N/A`. Provenance saved this run — the change number was wrong but the `ibkr_cached`/null fields let me prove it. Keep that discipline and extend it to the *time basis* of every change.
- Run weekday if possible. A weekend session makes "stale-by-design" and "broken" hard to separate; several findings here are explicitly marked needs-confirmation for that reason.
- To drive Copilot/Fundamentals reliably, prefer real user-event simulation over `dispatchEvent`; the synthetic path doesn't open the search dropdown or switch the Copilot tab.
