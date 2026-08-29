# Gamma Usability Findings — 2026-07-08

Date: 2026-07-08
Audience: future AI agents and contributors improving Gamma
Mode: full
Data: live IBKR, account U1234567, market data `auto` (weekday evening session; US cash close Jul 7 fresh, CME Globex overnight)
Context: First weekday live run since the 2026-06-27 weekend audit. A real geopolitical tape (US strikes on Iran, oil surging) let two evidenced theses run end-to-end. The Commodities `% CHG` P0 fix and the single-day corroboration work were verified live; the run's sharpest new findings are an intermittent app-wide UI freeze on the Strategy Lab → Risk handoff, an unbounded Options polling loop, and a Copilot that completes but never delivers a card. Builds on `gamma_usability_findings_2026-06-27.md`. Note: this run audited the `visual-language-pass` working tree (uncommitted GUA-20260627-3 Sitrep/Research changes included).

## Audit Setup
- Backend: FastAPI `127.0.0.1:8000` (started this session from the working tree); Frontend: Vite `127.0.0.1:5174`; session header `X-Gamma-Session`.
- IBKR: TWS on 7496, `MOCK_DATA=false`, live-IBKR precondition check passed (exit 0). Operator note: the stack was down at session start; audit toggled `POST /system/connection/toggle` and accidentally raced the frontend's own auto-connect (first toggle disconnected a just-connected session — the toggle endpoint has no "desired state" parameter).
- Tabs exercised: Sitrep, Commodities, Sealanes, Prediction Markets, Equity Research (Overview + Scope), Strategy Lab, Macro, Fundamentals (partial — see GUA-20260627-6), Options (blocked), Copilot, Risk. Out of scope: Crypto, Portfolio workspace.
- Outside tools: none for market data. Backend API probes (`/maritime/workspace`, `/fundamentals/search`, `/fundamentals/XOM/dcf`, `/iv/session`) were used where the UI was not drivable by synthetic events — each probe is flagged where it stands in for a UI step.

## Regression Delta (vs 2026-06-27)

| ID | Finding | Prior status | This run | Evidence |
| --- | --- | --- | --- | --- |
| GUA-20260627-1 | Commodities `% CHG` diffed stale cached curves (P0) | Addressed in code; live retest recommended | **Confirmed fixed live** | Cached state: all IBKR rows `% CHG N/A`, header `PRIOR N/A`, label "IBKR cached front future". After Refresh: `PRIOR Jul 6, 2026, 12:00 AM`, WTI +5.67%, Brent +5.90%, HO +2.68%, gold −0.24% — oil-specific, matching the Iran-strike news, not a uniform artifact. Labels flip cached↔fresh correctly. |
| GUA-20260627-2 | No daily reference for IBKR-futures commodities (P1) | Addressed in code; retest recommended | **Implemented; staleness limits usefulness** | WTI drill shows "PRICE HISTORY 245 obs · Jun 29, 2026" — the reference series ends 9 days before the audit, so it cannot corroborate the +5.67% headline move. Copilot payload confirms the per-row dated-reference-or-placeholder contract is live. |
| GUA-20260627-3 | No single-day corroboration path (P1) | Addressed in code 2026-07-08; retest recommended | **Confirmed working live** | Sitrep Worldwide Indices show LAST / LATEST DAY / LATEST DAY % / PROXY-AS-OF (e.g. Nasdaq −302.47 / −1.2% / QQQ Jul 7; Nikkei −0.0% EWJ Jul 6). Scope XLE shows `LATEST DAY 2.84% as of Jul 7` beside `LOOKBACK RETURN 21.56%`. Tile→EWJ pivot click not exercised. |
| GUA-20260627-4 | Sitrep FX strip N/A while Macro FX had data (P2) | Needs confirmation | **Fixed on weekday, with a load-order dependency** | FX PAIRS renders "Macro not loaded / FX unavailable N/A" until macro context loads, then fully populates labeled "IBKR" (EUR/USD 1.141, USD/JPY 162.10 +1.5%…). Change columns carry no period label — see GUA-20260708-7. |
| GUA-20260627-5 | Perpetual REFRESHING / stuck tape (P2) | Open | **Not reproduced (weekday)** | Refresh button returns to idle "Refresh"; US equity tape live (NVDA +0.7%, TSLA −4.0%); `preview_screenshot` no longer times out on Sitrep; "DEGRADED / 6 WARN" renders as a terminal status, not a spinner. Weekend behavior remains unverified. |
| GUA-20260627-6 | Agent/a11y-undrivable controls (P2) | Open | **Still open** | Fundamentals search dropdown never renders under programmatic input (backend `/fundamentals/search?query=XOM` ranks XOM #1, so ranking fix holds); topbar "Search tabs" dropdown renders an empty container under synthetic input; Copilot context chips and all nav tabs DO respond to programmatic clicks post-reload (improvement vs prior run's COPILOT-tab failure). |
| GUA-0615-pmintent | Prediction-market intent search matched threshold proxies | Partially improved | **Substantially improved** | Query "Iran" returned 297 PM event markets led by exactly-on-thesis contracts ("Iran successfully targets shipping on July 8?" 18%, Δ24h +15.2pp; "US announces blockade on Iran by July 31?" 21%, +12pp) with live Δ24H repricing. |
| GUA-0615-slrisk | Strategy Lab → Risk research-book handoff | Complete (not retested 06-27) | **Works, but froze the app once** | Attempt 1: UI froze app-wide (see GUA-20260708-1). Attempt 2 (after reload): clean handoff — Risk consumed "Strategy Lab book: Strategy Lab Portfolio", computed VaR/MC on 938 aligned obs. |

## Thesis Log

### Thesis 1: US strikes on Iran keep the front of the crude curve bid — long front-month energy, killed by de-escalation
- Signal that sparked it (captured before thesis, Sitrep news feed, Jul 7 ~23:01 UTC): "Oil Surges as US Strikes Targets in Iran Following Ship Attacks" (Bloomberg 22:01), "Crude prices rise as U.S. launches strikes on Iran shortly after canceling its license to sell oil" (MarketWatch 22:11), "US Crude Oil, Product Inventories Fall Even As Hormuz Traffic Begins to Flow" (OilPrice 20:48). Sitrep commodities tile: Brent 76.24 / WTI 72.46. Screenshot captured before the thesis sentence.
- Steps:
  1. **Commodities → Overview:** cached matrix showed `% CHG N/A` on every IBKR row (honest, but the spike magnitude was invisible during a live event). partial.
  2. **Commodities → Refresh:** fresh quotes arrived with a dated prior close (`PRIOR Jul 6`): WTI +5.67%, Brent +5.90%, HO +2.68%; gold −0.24% and copper −0.11% flat → move is oil-specific, not an artifact. The P0 fix did exactly what it promised. worked.
  3. **Commodities → WTI drill:** clicking the row re-requested the workspace and reverted to the cached view — the +5.67% I clicked on vanished back to N/A (GUA-20260708-5). Energy drill still delivered: 12-contract CL strip in backwardation (M1–M6 4.21, roll +4.14%), crude stocks 408.4M bbl at the **0.4th percentile**, refinery inputs 99.2th pctl, gasoline crack proxy z=2.05 at the 100th percentile. partial — data excellent, change retention broken.
  4. **Sealanes (Hormuz leg):** map rendered with VESSELS 0; Modes panel: Chokepoints 0 boxes, Trade Flows 0, REFRESH UNAVAILABLE. `/maritime/workspace` says `coverage_status: unavailable`, "No AIS positions were received during the 6-second AISstream sample window" — honest coverage, not a bug, but the tab contributed nothing during a chokepoint-driven event (GUA-20260708-9). blocked (coverage).
  5. **Prediction Markets → search "Iran":** event-intent results with live repricing: shipping-attack Jul 8 market 18% (+15.2pp), blockade-by-Jul-31 21% (+12pp), airspace closure 9.3% (+5.2pp); de-escalation repriced down (US-Iran meeting by Jul 17: 21%, −20pp) and the Jul-10 meeting market's history chart shows collapse from ~80% to 1.7%. The thesis kill-switch is quantified in-app: meeting-by-Jul-31 still 59%. worked.
  6. **Macro:** CPI YoY 4.27% (+1.44pp) re-accelerating, 2Y 4.13% pricing further tightening, FOMC July 28–29 as the next catalyst; app itself flags CPI-vs-breakevens disagreement. worked.
  7. **Equity Research → Scope XLE:** LATEST DAY +2.84% as of Jul 7, lookback 21.56%, β 0.531, corr 0.382 vs SPY over 317 obs — the energy leg is a real diversifier against the tech-heavy tape. worked.
  8. **Options → XLE:** blocked. "Load Max Surface" click issued no surface request; view stuck polling `/iv/session` + `/iv/underlying-history?symbol=SPY` every 1–2s with all-N/A KPIs and no explanation (GUA-20260708-2). blocked.
- Outcome: **confirmed** — corroborated across four tabs (curve, inventories, event markets, macro), with the options expression unverifiable this run.

### Thesis 2: The AI-debt selloff is hitting semis far harder than the tape — long energy / short semis as one regime trade
- Signal that sparked it (captured before thesis): Sitrep news "AI-related debt sells off sharply as Amazon looks to borrow another $25 billion" (22:35), "Tech Rout Deepens as Chipmakers Fall" (20:39); worldwide indices Nasdaq −1.2% vs S&P −0.4% (Jul 7). Then Equity Research market map (Day-over-day): laggards INTC −9.7%, KLAC −7.2%, LRCX −6.9%, AMD −6.5%, MU −4.7% vs leaders COP +4.7%, XOM +3.8%, CVX +3.5%.
- Steps:
  1. **Equity Research → Synthetic scope `XOM 0.5 / AMD -0.5`:** the short leg was **silently dropped** — preview showed "1 parsed names, XOM 100.00%", no warning (known long-only limitation, still unannounced). blocked → switched to Strategy Lab.
  2. **Strategy Lab → Composer:** signed book long XOM 0.6 / short AMD −0.4. Validate Book: VALID, 2/2 legs, 938 aligned obs, per-leg provider + window shown. Compose: total return −56.84%, Sharpe −0.72, maxDD −63.3% — the pair was suicidal 2023–mid-2026, but monthly returns flip to **+6.60% in July 2026** after −25.3/−18.6/−9.5% in Apr–Jun: Gamma's own backtest frames it as a fresh regime trade, not a trend. worked (excellent).
  3. **Strategy Lab → Open In Risk (attempt 1):** the entire app froze — no tab clicks, no composer buttons, no console error; backend received six identical `POST /risk/compute` (200) plus an XLE IV-surface call; only a page reload recovered (GUA-20260708-1). blocked.
  4. **Strategy Lab → recompose → Open In Risk (attempt 2):** clean handoff. Risk shows the book: VaR USD 2,730 on a 100k notional, vol 26.3%, MC ES −19.8%, and 1D return **+4.9%** — which independently reconciles with the day's tape (0.6×3.8% + 0.4×6.5% = 4.9%). But the Risk screen mixes the live account into book context (GUA-20260708-4) and contribution detail is one collapsed row (prior known gap). partial.
- Outcome: **partially confirmed** — the pair is validated, priced, and working today; the app can express and risk it, but the Risk view's mixed-portfolio readout and the one-time freeze eroded trust at the last step.

## Trade Verdict
Long energy with a defined de-escalation kill, half-size:
- **Expression:** XLE (or XOM outright) rather than futures — the front future's +5.67% is only refresh-deep in Gamma (changes evaporate on drill), while the ETF leg has a clean latest-day KPI, β 0.53, and corr 0.38 to SPY. The XOM/AMD pair book is the aggressive variant; Gamma's backtest says it only works if the July regime holds (+6.6% MTD after three brutal months).
- **Confirms:** crude stocks at the 0.4th percentile with refinery inputs at 99.2th (physical tightness), crack proxies at the 100th percentile, CL backwardation M1–M6 4.21, shipping-attack market +15.2pp overnight.
- **Kills:** de-escalation — Polymarket prices a US–Iran diplomatic meeting by Jul 31 at **59%** (by Jul 17: 21%). That is a coin-flip against the thesis inside the trade's horizon and is exactly why sizing stays small. FOMC Jul 28–29 stacks rate risk the same week.
- **Sizing intuition:** half-size, front-month/ETF expression, exit trigger = the Jul-17 meeting market repricing back above ~40% or crude stocks printing a build against the 0.4th-pctl base.

## Usability Report

### What worked well
- **The P0 fix held under a real event.** Cached rows say N/A instead of lying; refreshed rows show a dated prior close; the resulting +5.67% WTI matched the news tape and the flat gold/copper rows proved it wasn't an artifact. This is the exact inverse of the 06-27 disaster, verified on the same surface.
- **Prediction-market intent search became a corroboration engine.** "Iran" surfaced the precise event contracts with 24h repricing (shipping attack +15.2pp, blockade +12pp, de-escalation −20pp) and the detail chart's collapse-to-2% was the single most persuasive artifact of the run. The thesis kill-switch came with a market-implied probability.
- **Latest-day everywhere it was promised.** Sitrep index rows (LATEST DAY % + proxy/as-of), Scope KPI (2.84% as of Jul 7), market-map leaders/laggards — the single-day blind spot from the prior two audits is materially closed.
- **Strategy Lab signed books are real.** Negative weights validated with per-leg source/window/obs diagnostics; the composed monthly-return table gave an instant regime read (Apr–Jun bloodbath, July flip) that directly shaped the trade verdict.
- **Provenance kept every diagnosis honest** — cached-vs-fresh labels debugged the drill regression, `live_stream_empty_sample` separated Sealanes coverage from bugs, and the Copilot payload's source list documented what the model was (correctly) given before it failed.

### Friction points (ranked)

1. **GUA-20260708-1 (P0, intermittent) — "Open In Risk" from a composed Strategy Lab book froze the entire app once.** Thesis 2 step 3. All interactivity died (nav tabs, composer buttons, sidebar toggle — native events fired, Svelte state never updated), zero console errors, while the backend received six identical `POST /risk/compute` 200s and an unrequested `GET /iv/surface?symbol=XLE&depth_preset=max`. Only `location.reload()` recovered, which drops to the landing page and loses workspace state. Not reproduced on attempt 2. Acceptance: no state update may hard-freeze the UI; risk auto-compute must be idempotent (one in-flight compute, no retry storm); an unhandled effect error must surface visibly.
2. **GUA-20260708-2 (P1) — Options workspace is an unbounded polling loop wearing an empty state.** Thesis 1 step 8. After one visit, `/iv/session` + `/iv/underlying-history?symbol=SPY` fire every 1–2s indefinitely — continuing after navigating away (still firing from the Copilot dock, hundreds of requests observed). The symbol stays SPY despite an XLE focal chip and XLE typed in the input; "Load Max Surface" produced no surface request; KPIs render all-N/A with `freshness_label: unavailable` and zero warnings or messages explaining why. Acceptance: poll only while the view is active, with backoff; bind the load button to the visible input; an empty surface must say why (closed session / no entitlement / no snapshot).
3. **GUA-20260708-3 (P1) — Copilot completes but delivers nothing, silently.** Copilot section below. Two synthesis attempts → `POST /copilot/research-card` 200 with `status:"error"`, `card:null`, `message:"OpenAI returned no structured research card."` (provider `openai_responses`, model gpt-5.4). The dock renders a neutral empty-state card; the error message is never shown. Acceptance: render the error card the API already returns; retry/fallback when the provider returns unstructured output.
4. **GUA-20260708-4 (P1) — Risk workspace blends the research book with the live account.** Thesis 2 step 4. Source says "Strategy Lab book", VaR/vol/returns are book numbers, but Largest Movers and Concentration panels show the real IBKR account (GOOGL 50.7% "concentration breach", LMT, FOUR) — a reader would attribute account breaches to the XOM/AMD book. Also: "Largest modeled risk contributor is N/A" beside a populated contribution row, six raw repeated "IBKR error (200): No security definition has been found" lines in the provenance panel, and per-leg contribution still collapsed to one row (carried gap from 06-15). Acceptance: one portfolio per risk screen (or explicit split panels); dedupe/humanize provider errors; per-leg decomposition for research books.
5. **GUA-20260708-5 (P1) — Freshly fetched Commodities changes are not retained.** Thesis 1 step 3. After a force refresh renders dated `% CHG`, clicking any matrix row re-fetches the workspace in cached mode and every change reverts to N/A — the analyst loses the number they were investigating. Acceptance: a drill interaction must reuse the just-fetched workspace (or the fresh quotes must enter the cache the drill reads).
6. **GUA-20260627-6 (P2, carried) — synthetic-input dead zones persist.** Fundamentals search dropdown and the topbar tab-search dropdown never render options under programmatic input (both verified again); Fundamentals therefore remains effectively un-drivable for agents even though `/fundamentals/search` ranks correctly. Improvement worth recording: nav tabs and Copilot context chips now respond to programmatic clicks.
7. **GUA-20260708-7 (P2) — unlabeled time bases and units still leak.** Sitrep RATES "MOVE" (+35bp on 2Y) and FX "%CHG" are 3M-window changes with no period label, reading as shock daily moves next to a "Latest daily close" indices board; header timestamp is UTC with no TZ suffix; Commodities "INVENTORY OUTLIERS" renders percentiles as signed changes ("+99.2%"); basis reconciliation compares copper USD/lb against a USD/metric-ton proxy and reports a 218,384.2% conflict. Acceptance: every change/outlier chip carries its period or unit; unit-normalize basis checks.
8. **GUA-20260708-8 (P2) — small state-loss traps in Strategy Lab.** Composer legs reset to the 3-leg default on tab switch; "Compose Portfolio" is a silent no-op until Validate Book has run (no disabled state or hint); a page reload lands on the landing page losing the active workspace/tab (only the research book survives via localStorage).
9. **GUA-20260708-9 (P2, coverage-adjacent) — Sealanes renders zero context when the live sample is empty.** Chokepoint boxes are static reference geography, yet 0 boxes render when AISstream returns an empty 6-second sample, and REFRESH shows UNAVAILABLE — during a Hormuz-driven event the tab offered nothing. Keep the static chokepoint layer (and its stress context) independent of live-sample success.

### Gaps
- **No options leg without a working IV workspace.** A thesis whose natural expression is calls/spreads on XLE could not be structured, priced, or Greeked this run.
- **Commodity daily references must be current to serve their purpose.** A dated-reference contract satisfied by a 9-day-stale series (last obs Jun 29 on Jul 7) still cannot corroborate a headline move; freshness needs a target, not just a label.
- **Focal-chip carry is inconsistent:** XLE carried into the topbar and Strategy Lab reusable objects, but Fundamentals ignored it (no auto-load, no "ETF — no SEC profile" explanation; prior audit saw EWJ auto-load) and Options ignored it (input stayed SPY).

### Cross-tab coherence
- Worked: Sitrep news → Commodities → Prediction Markets → Macro → Equity Research all told one consistent story (this is the first audit where the tabs corroborated each other on a live event); XLE scope became a reusable Gamma object in Strategy Lab; the composed book reached Risk with provenance intact.
- Dropped: Fundamentals (focal ignored), Options (symbol ignored), and the Risk screen's account/book blend — the last hop of the workflow is where coherence still leaks.

### Copilot evaluation
- Setup: dock opens cleanly; context chips (Equity Research + Macro + Prediction Markets + Commodities) toggle and display; SITREP/Strategy Lab chips showed "unavailable" with no explanation of why despite both tabs being loaded.
- Prompt 1 (full thesis with numbers, 4 contexts, medium thinking): GENERATING… → `status:"error"`, `card:null`, "OpenAI returned no structured research card." The assembled scope was excellent — 12 sources with provenance (commodities workspace + coverage, macro snapshot/divergences/FOMC calendar, prediction detail/history/wallet/related/calibration, equity overview) and a `get_synthesis_scope_summary` tool trace — the grounding pipeline works; the card generation does not.
- Prompt 2 (shorter, same contexts): same silent empty-state outcome.
- Net: **regression vs 06-27** ("no indefinite stall" still holds — every request reached a terminal state quickly — but zero usable output this run, and the UI hides the failure). The 06-27 open question "does Copilot ground correctly" remains unanswerable.

## What Could Not Be Proven This Run
- **Whether the freeze (GUA-20260708-1) reproduces for a human with a mouse.** It occurred once under programmatic clicks and not on retry; the 6× risk/compute storm is objective (backend log), the trigger conditions are not isolated.
- **Human-facing behavior of the Fundamentals and tab-search dropdowns** — both are synthetic-input dead zones; a human retest (and ideally Playwright coverage with real key events) is needed.
- **Options/IV correctness** — no surface was ever loaded (session closed hours + the polling/symbol bugs); template expiry defaults and diagnostics remain untested since 06-15.
- **The Nikkei→EWJ tile pivot** (GUA-20260627-3's last acceptance item) — the new columns and Scope KPI were verified, the click-through was not.
- **Whether "PRIOR Jul 6, 12:00 AM" is a true settlement print** — the % CHG now references a dated prior close, but I cannot verify the settlement value itself from inside Gamma (the daily reference series ends Jun 29).

## Scoring

| Category | Score | Δ vs prior | Rationale (one sentence) |
| --- | ---: | :--: | --- |
| Data breadth | 8/10 | = | Everything a two-legged geopolitical thesis needed was present except live vessel coverage (honest gap). |
| Data depth / drill-down | 8/10 | +1 | Dated prior closes, EIA percentiles, crack z-scores, 12-node curves, event-market microstructure — depth carried the verdict; stale daily references cap it. |
| Analytical tooling | 7/10 | = | Signed books with validation and instant regime backtests are excellent; the Risk blend, lost fresh quotes, and a dead Options workspace offset them. |
| Copilot usefulness | 3/10 | −3 | Perfect grounding scaffolding, zero cards delivered, failures hidden from the user. |
| Cross-tab workflow / state continuity | 6/10 | +1 | First run where five tabs corroborated one thesis and a book reached Risk; Fundamentals/Options drops and the account/book blend keep it from 7+. |
| Visual density & terminal feel | 8/10 | = | Dense, provenance-rich; the new latest-day columns fit the terminal idiom. |
| Speed to insight | 7/10 | +2 | Headline → curve → inventories → event-market kill-switch in under an hour; one freeze-reload and the Options dead end were the only stalls. |
| Overall (gestalt) | 7/10 | +1 | Gamma fabricated nothing and carried a real trade end-to-end for the first time across three audits; the remaining failures are stability and delivery, not data trust. |

## Prioritized Follow-Up

### P0 — GUA-20260708-1: App-wide freeze on Strategy Lab → Open In Risk (intermittent)
- Problem: one occurrence of a total UI freeze (no console error) with a 6× `/risk/compute` retry storm and a spurious XLE IV-surface fetch; reload-only recovery loses workspace state.
- Acceptance: idempotent risk auto-compute (single in-flight request); no silent effect-scheduler death — errors must surface; workspace state survives reload.
- Status: **Open.** Reproduce with instrumentation around `openRiskFromResearch` (App.svelte:1522) and the RiskView mount path.

### P1 — GUA-20260708-2: Options polling loop + dead load button
- Problem: 1–2s `/iv/session`+`/iv/underlying-history` polling forever (survives tab switches); load button ignores the typed symbol/focal chip; empty surface carries no explanation.
- Acceptance: active-view-only polling with backoff; symbol binding fixed; explicit empty-surface reason.
- Status: **Implemented in code 2026-07-12; live IBKR retest recommended.** Adaptive polling is active-view and page-visibility scoped with failure backoff; idle status polls no longer request underlying history without a renderable surface; visible symbol requests persist at the app boundary; and scoped IV errors plus disconnected/collecting/entitlement/no-snapshot messages remain visible until a real surface arrives.

### P1 — GUA-20260708-3: Copilot returns no card; UI hides the error
- Problem: `status:"error" / card:null / "OpenAI returned no structured research card"` rendered as a blank neutral card, twice, with healthy grounding.
- Acceptance: show the API's error message; add structured-output retry or fallback model; surface why a context chip is "unavailable".
- Status: **Open.**

### P1 — GUA-20260708-4: Risk screen mixes research book and live account
- Problem: book VaR beside account movers/concentration with no separation; raw duplicated IBKR errors; per-leg contribution still one row.
- Acceptance: single-portfolio screens or labeled split; deduped human-readable warnings; per-leg decomposition.
- Status: **Open** (per-leg gap carried from 06-15).

### P1 — GUA-20260708-5: Fresh commodity changes lost on drill
- Problem: row click re-fetches cached workspace, reverting dated `% CHG` to N/A mid-investigation.
- Acceptance: drill reuses the fresh workspace payload or the fresh quotes seed the cache it reads.
- Status: **Open.**

### P1 — GUA-20260627-2 (carried): daily reference freshness
- Problem: reference series 9 days stale defeats corroboration.
- Acceptance: freshness target for daily references (≤1 trading day when the front contract has traded) or an explicit stale-reference warning on the panel.
- Status: **Reopened as freshness gap.**

### P2 — GUA-20260627-6 (carried): synthetic-input dead zones (Fundamentals search, tab search)
### P2 — GUA-20260708-7: unlabeled periods/units (Sitrep MOVE/%CHG, UTC header, percentile "+", unit-blind basis check)
### P2 — GUA-20260708-8: Strategy Lab state-loss traps (legs reset, silent Compose, reload → landing)
### P2 — GUA-20260708-9: Sealanes static chokepoint layer coupled to live-sample success

## Guidance For Future Agents
- The data-trust war is largely won — this run's failures are **stability (freeze), delivery (Copilot cards, Options), and last-hop coherence (Risk blend)**. Start there.
- Retest GUA-20260708-1 with a human or trusted-event automation before treating it as fixed; the backend log signature (repeated `/risk/compute` with no UI change) is the fingerprint.
- Drive Fundamentals via `/fundamentals/*` APIs until the dropdown accepts synthetic input; the search/ranking backend is fine.
- Run one audit during US cash hours: the Options workspace, live (non-cached) commodity quotes, and the Nikkei→EWJ pivot all need an open session to verify.
