# Gamma Usability Findings — 2026-10-21

Date: 2026-10-21, 12:27–13:00 Europe/Madrid (CEST, UTC+2)<br>
Audience: future AI agents and contributors improving Gamma<br>
Mode: full<br>
Data: live IBKR (TWS on 7496, account identifier not retained), market data `Auto`; European session open, US cash and options pre-market (06:30–07:00 ET)<br>
Context: Brent–WTI / Strait of Hormuz trade-idea audit that retests the open items of the 2026-09-04 report and the 2026-09-01/09-03 series, with first substantive coverage of Prediction Markets and Sealanes.

## Audit Setup

- Commit `e388e74` on `main`, clean at start. No product code, tests, configuration or roadmap were edited.
- Backend was down at start (gate exit 3). The audit launched `uvicorn src.api.main:app` on `127.0.0.1:8000` and Vite on `127.0.0.1:5173`, both with the repo `.env` loaded into the process (`MOCK_DATA=false`, matching `GAMMA_SESSION_TOKEN` / `VITE_GAMMA_SESSION_TOKEN`).
- The backend did **not** auto-connect to TWS: the gate then returned exit 2 (`mock_mode=False connected=False`). The connection was made from the first-run Setup dialog (`Broker > Test connection`, backend log `IBKR connect ok` at 12:29:22). Gate exit 0 at 12:29:46 CEST.
- First-run Setup appeared because no `setup.json` existed. It was finished with no changes; the SEC identity step was left empty on purpose (no personal data entered), so Fundamentals was only checked for its gate.
- Tabs exercised: SITREP, Commodities (Overview, Curves & Spreads), Sealanes, Prediction Markets (Screener, Contract), Strategy Lab (Composer, Validate, Compose), Risk (Overview, Scenarios), Macro (US, EU), Copilot (Research Agent, Research Operator), Options (Overview, Strategies), Fundamentals (gate only), Settings. Not exercised: Equity Research, Crypto, Portfolio.
- Outside tools, and why:
  - Hand-computed same-month Brent–WTI spreads from the two curve tables: Gamma has no inter-crude spread.
  - Direct reads of `/sitrep/workspace`, `/commodities/spreads`, `/commodities/price-history`, `/maritime/workspace`: the UI hides the as-of dates needed to judge freshness.
  - Source reading to locate root causes of three defects (timestamps, Add Leg, EU FX series). No external market data or news site was used.

## Regression Delta (vs `gamma_usability_findings_2026-09-04.md`, plus open items from 2026-09-03-x, 09-01, 07-08 and 06-27)

| ID | Finding | Prior status | This run | Evidence |
| --- | --- | --- | --- | --- |
| GUA-20260904-1 | Research Operator sends OpenAI-invalid tool names | Open P1 | **Confirmed fixed** | Operator run at 10:47:45Z called `get_commodities_workspace_summary` and the curve inspection tool; "synthesized … from 3 validated tool observation(s)". |
| GUA-20260904-2 | Operator recovery loses the prompt | Open P2 | **Partially fixed** | No Operator failure occurred. The Research Agent `incomplete` card kept the prompt in the transcript and Follow-up worked, but there is still no Retry control (see GUA-20261021-6). |
| GUA-20260904-3 | Safe preview cannot answer the Script thesis | Open P2 | Not retested | Setup now says "Script runs isolated Python through OpenAI"; Script mode not exercised. |
| GUA-20260904-4 | Script input provenance stops at Gamma's adapter | Open P2 | Not retested | — |
| GUA-20260903-6 | Options strategy survives a symbol change | Open P1 | **Confirmed fixed** | USO call spread, then BNO reload: "Cleared the USO structure. Legs, marks, payoff and sizing do not carry across symbols; rebuild on BNO." |
| GUA-20260903-2 | Options workbench cleared before Copilot | Open | Not retested | — |
| GUA-20260903-7 | Strategy Lab → Risk mixes research book and live account | Open P1 | **Confirmed fixed** | Risk header "Strategy Lab book: AUDIT 2026-10-21 Brent minus WTI · USD"; Largest Movers and Concentration 0 rows; provenance lines name the book. |
| GUA-20260903-8 | Commodities → Strategy Lab drops loaded history | Open P1 | **Confirmed fixed, with a data caveat** | Brent 248 and WTI 245 dated points arrived as inline legs. They are FRED spot proxies ending 2026-10-14, not the IBKR futures on screen (GUA-20261021-9). |
| GUA-20260903-9 | Returning from Risk discards the composer draft | Open P2 | **Confirmed fixed** | After Open In Risk → Ctrl+3, legs, weights, name and composed result were intact. |
| GUA-20260903-10 | Provider diagnostics hide most calls | Open P2 | **Still broken** | Settings: "500 calls" but visible rows sum to 132 (yfinance 28, ibkr 98, rss 3, unavailable 3). FRED, Treasury, Polymarket, EIA and AISstream have no row, and the FRED `HTTPError`s are not counted anywhere. |
| GUA-20260903-11 | Regime Stress omits years and windows | Open P3 | Not retested | — |
| GUA-20260901-2 | Visible lookback does not identify the analysis | Open P1 | **Partially fixed** | Risk now prints "requested 756, analysed 241 spanning 2025-10-22 to 2026-10-14". The Strategy Lab composer with LOOKBACK `252` still produced 319 observations (GUA-20261021-11). |
| GUA-20260901-4 | Multi-context Copilot synthesis has no usable result | Open P1 | **Still broken on the first attempt** | A five-context prompt ended `incomplete — max_output_tokens` after 49 s. A shorter follow-up worked (GUA-20261021-6). |
| GUA-20260901-7 | SITREP aggregate load ~56 s | Open P2 | **Still broken (~77 s cold)** | Research View clicked at 10:30:52Z, indices populated at 10:32:09Z, one `/sitrep/workspace` request. A warm API re-call took 5.7 s. |
| GUA-20260901-8 | News entity tags on unrelated headlines | Open P2 | Partially fixed | Tags were plausible (TSLA, GS, GOOGL); MarketWatch personal-finance stories still fill Market News. |
| GUA-20260901-1/3/5/6 | Equity Research / Fundamentals items | Open | Not retested (out of scope) | SEC identity deliberately not set. |
| GUA-20260708-1 | App-wide freeze on Strategy Lab → Risk | Open P0 | Not reproduced on that path | Strategy Lab → Risk was clean. A **new** app-wide wedge comes from Add Leg (GUA-20261021-1). |
| GUA-20260708-3 | Copilot returns no card | Open P1 | **Confirmed fixed** | Every request returned a card, including an explicit `incomplete` status. |
| GUA-20260708-5 | Fresh commodity changes lost on drill | Open P1 | **Appears fixed** | Headline CHG +2.28% (WTI) and +2.04% (Brent) survived the Sitrep → Commodities drill and the Curves & Spreads switch. |
| GUA-20260708-7 | Unlabeled periods/units, UTC header, unit-blind basis | Open P2 | **Still broken** | UTC clock times are shown without a zone in Commodities, Options and Strategy Lab. Copper basis is still unit-blind: "6.49 vs FRED 13542.82 by 208636.4%". Escalated as GUA-20261021-3/-4. |
| GUA-20260708-8 | Strategy Lab state-loss traps | Open P2 | Partially fixed | A reload now returns to Strategy Lab but silently resets an unsaved draft to the default QQQ/SPY/PM book. |
| GUA-20260708-9 | Sealanes static chokepoint layer coupled to live sample | Open P2 | **Still broken, escalated** | An empty AIS sample gave "Chokepoints 0 boxes"; the Prediction Markets "Open in Sealanes" handoff dead-ends (GUA-20261021-7). |
| GUA-20260627-2 | Daily reference freshness | Open P1 | **Still broken** | FRED spot references end 2026-10-14 (7 days old) and now feed spreads and basis checks (GUA-20261021-2/-4). |
| GUA-20260627-6 | Synthetic-input dead zones | Open P2 | Partially fixed | Tab search and Prediction Markets search are drivable. The Copilot drawer reports its refs as offscreen while visible; the navigation sidebar goes offscreen after a toggle. |
| GUA-0615-pmintent | Prediction-market intent search | Substantially improved | **Confirmed working** | "Hormuz" returned 16+ on-intent contracts (traffic normalisation, weekly and daily transit buckets). |

## Thesis Log

### Thesis 1: The ~$11 Dec-26 Brent–WTI spread is a seaborne/Hormuz premium concentrated in the prompt months

- Statement: the wide Brent–WTI spread is prompt-month seaborne/chokepoint stress, not WTI-specific weakness. If true, the spread should decay along the curve, Brent should be more backwardated than WTI, and the catalyst should be priced as persistent.
- Signal that sparked it (captured 10:32Z, before the thesis was written at 10:35Z): SITREP Commodities showed `Brent Crude Oil 111.02 +2.0% IBKR BZZ6` and `WTI Crude Oil 100.05 +2.3% IBKR CLZ6`, a gap of about 10.97. Market News had `09:30 OilPrice — Goldman Sachs Warns of New Oil Price Shock as Tanker Rates Soar` and `09:18 Bloomberg — French Bond Risk Hits 15-Year High on $110 Crude`.
- Steps:
  1. **SITREP:** cold load of the aggregate workspace — worked, but ~77 s. Every provider AGE read `2h old` for data seconds old (GUA-20261021-3).
  2. **SITREP → Commodities:** clicked the Brent row — partial. While REFRESHING the header showed WTI `CLZ6` and a WTI basis conflict; after load it switched to `BZZ6`.
  3. **Commodities Overview (WTI):** curve `CLZ6 100.05 (30d) … CLX7 82.37`, M1–M2 1.88, M1–M6 9.39; US crude stocks 415.58 mb at the 12.3rd percentile (draw −8.56), exports 4.57 mb/d at the 76.9th percentile — worked.
  4. **Commodities (Brent):** `BZZ6 111.01 (12d) … BZX7 87.59`, M1–M2 3.70, M1–M6 15.3, roll +40% vs WTI +22.55% — worked. Brent is the more backwardated curve; Brent has no EIA stack.
  5. **Commodities spreads:** looked for a Brent–WTI spread — blocked; none exists. Hand-computed same-delivery-month spreads: Dec 10.96, Jan 9.14, Feb 7.84, Mar 7.23, Apr 5.15, May 5.05, then 4.8–6.1 through Nov-27. The spread is prompt-concentrated.
  6. **Commodities crack matrix:** read Distillate 1-1 101.12 (85.8th percentile) and Gasoline 1-1 23.54 (0.8th percentile) — **misleading**. The API shows the last observation is 2026-10-14 (FRED spot) while `as_of` is stamped 2026-10-21 (GUA-20261021-2).
  7. **Commodities basis reconciliation:** "Brent … 111.05 differs from FRED spot proxy 126.55 by 14.0%" — partial. The FRED value is Dated Brent on 2026-10-14; FRED WTI that day was 101.91, so the physical Brent–WTI was about $24.6, more than twice the futures spread. Gamma frames this as a data conflict without dates (GUA-20261021-4).
  8. **Commodities → Sealanes:** the "Sealanes Energy Chokepoints" cross-domain row is not clickable. Ctrl+9 opened Sealanes — **blocked**: `UNAVAILABLE · AISSTREAM`, "No AIS positions were received during the 6-second sample window" (two samples, including force refresh), Chokepoints 0 boxes. The empty sample is a provider coverage limit; the vanished static layer is the defect. *Left Gamma (why): no freight rates, tanker index or chokepoint transit counts anywhere.*
  9. **Prediction Markets:** default screen was 40 contracts dominated by 2028-election markets. Search "Hormuz" — worked well:
     - "Strait of Hormuz traffic returns to normal by Oct 31?" 0.7%, by Nov 30 5.0%, by Dec 31 11.0%.
     - "0–5 average daily transits on Oct 31" 91.0%.
     - Weekly bucket for Oct 19–25: mode 25–29 ships at 35%.
  10. **Prediction Markets contract** (`polymarket:2176270`, Dec 31): history 90.5% → 11.0% (−68 pp since May), liquidity 684,667, bid depth 304,685 vs ask 22,207, resolution "IMF Portwatch 7-day MA transit calls ≥ 60". RELATED showed "No linked markets" although the Oct 31 and Nov 30 siblings share the series — partial.
  11. **Prediction Markets → Sealanes:** "Open in Sealanes" (Strait of Hormuz / chokepoints) — **blocked**: it opened the default Atlantic view at zoom 3.0 with no pan, focus or message (GUA-20261021-7).
  12. **Commodities → Strategy Lab:** "Add & Open" for Brent and then WTI. Accepted both, removed the default legs, set weights +1/−1 — worked. Validate Book: VALID, 241 aligned observations, both windows ending **2026-10-14** with no staleness warning, plus an irrelevant yfinance caveat.
  13. **Strategy Lab Compose:** total 8.07%, annual 8.46%, vol 22.05%, Sharpe 0.48, max drawdown −11.44%. Best months Mar-26 +7.43%, Jul-26 +6.68%, Sep-26 +5.46% — worked (spot-proxy returns, not futures).
  14. **Strategy Lab → Risk:** Open In Risk — worked. New per-leg decomposition: Brent 70.7% of VaR (leg vol 65.0%), WTI 29.3% (58.5%); beta to SPY 0.09. "WHAT CHANGED" still says "Largest modeled risk contributor is N/A".
  15. **Risk Scenarios:** historical stress replay 0/6 covered — every episode is an S&P equity crash, and the book carries one year of history. Volatility regimes Calm 25.1% / High vol 20.6% — partial.
  16. **Risk → Strategy Lab (Ctrl+3):** draft and result retained — worked.
  17. **Macro US:** 10Y 5.15%, 2Y 4.77%, 10Y real 2.80%, HY OAS 3.29% (+0.56 pp) — worked. SITREP Rates showed 10Y 5.12% / 2Y 4.79% (Treasury source) with no as-of to reconcile the two.
  18. **Copilot Research Agent** (SITREP + Strategy Lab + Prediction Markets + Commodities + Risk, profile Auto): four-part synthesis — **blocked**, `incomplete … max_output_tokens` after 49 s. The attached evidence held the WTI curve only, not Brent.
  19. **Copilot follow-up** (concise): worked. Dec-26 Brent 111.05 / WTI 99.93 → $11.12; Apr-27 WTI 92.19; "Apr-27 Brent: not in context"; Hormuz 11%.
  20. **Copilot Research Operator:** asked for the Brent curve and same-month spreads — worked in ~2 min. Same-month spreads 11.12 / 9.28 / 7.94 / 7.35 / 5.24 / 5.13 (Dec–May); it honestly reported WTI Jun–Nov N/A ("inspection tool's per-run limit was exhausted").
  21. **Options USO → BNO:** USO headline ATM IV 56.3% came from the 0D (today) pre-market chain. At the 163 strike, call IV was 14.0% and put IV 98.6%, labelled `LIVE` (GUA-20261021-10). The Call Spread template defaulted to 0D. BNO: front ATM IV 73.9%, term −23.5%, expiries out to 2027/04/16. The symbol change correctly cleared the legs.
- Outcome: **confirmed in part.**
  - Supported: prompt concentration (~$11 → ~$5 by Apr-27), Brent more backwardated, and the catalyst priced as persistent (89% "not normal by Dec 31").
  - Not testable in Gamma: the freight/chokepoint mechanism (no freight data; Sealanes empty).

### Thesis 2: France's fiscal plus energy-import shock shows up as French equity underperformance during the oil spikes

- Statement: France's fiscal and energy-import stress should make French equities lag German equities in the months when the oil spread spiked.
- Signal that sparked it (captured 10:32Z): `10:27 CNBC — French 10-year bond yield hits 5% for first time since 2002 amid unrest`; `09:18 Bloomberg — French Bond Risk Hits 15-Year High on $110 Crude, Budget Concern`. SITREP indices showed CAC +0.4% vs DAX +0.5% (EWQ/EWG Oct 21).
- Steps:
  1. **Macro EU:** looked for OAT, Bund and their spread — **blocked**. EU shows only "Euro Area 10Y Government Yield 3.22%" (monthly `IRLTLT01EZM156N`) on the day French 10Y printed 5%; there is no country sovereign, no spread, and "No upcoming events for this region". The header KPI "EUR/USD EXCHANGE RATE 0.852" contradicts the FX widget's 1.1224 (GUA-20261021-5).
  2. **Strategy Lab:** tried to add EWQ/EWG legs to the existing book — **blocked**. Add Leg raised a Svelte duplicate-key error and wedged the app; a reload was required (GUA-20261021-1).
  3. **Strategy Lab (after reload):** edited the default legs to EWQ +1 / EWG −1 with LOOKBACK 252 — worked, but the window was 2025-07-16 → 2026-10-20 (319 observations). Total 0.00%, vol 4.36%, max drawdown −4.62%. Oil-spike months: Mar +0.60%, Jul −0.56%, Sep −0.28%. France lagged only in Aug–Oct (−2.31%, −0.28%, −0.96%).
- Outcome: **rejected** as an oil-linked thesis. The France-specific weakness of about −3.5% since August cannot be attributed in Gamma without OAT–Bund data.

## Trade Verdict

This is research only, not investment advice. Gamma is read-only, and the figures below must be checked against official and primary sources before any use.

- **Does it make sense?** Not as "fade the $11 prompt spread": the futures curve already prices compression to about $5 by Apr-27. The more interesting reading is the tension between two signals seen in-app:
  - Prediction markets give Hormuz an 89% chance of *not* normalising by Dec 31; normalisation odds fell from 90.5% to 11% since May.
  - The deferred Brent–WTI (Mar–Apr-27 at $7.2–$5.2) sits only modestly above the curve's later months.
  - If disruption runs into 2027, the deferred spread looks cheap. The research expression is **long Brent / short WTI in a calendar-matched Mar-27 or Apr-27 pair**, not the prompt.
- **Sizing intuition:** Risk on the spot-proxy book showed 22% annual vol for a dollar-neutral pair, single-leg vols of 58–65%, and a −11.4% max drawdown over the last year. That argues for a small notional and a stop defined in $/bbl of spread rather than percent. These numbers come from FRED spot proxies, not roll-adjusted futures, so they are indicative only.
- **What would kill it:**
  - "Hormuz normal by Dec 31" repricing above ~30%.
  - The Apr-27 same-month spread trading below ~$4.
  - A collapse of the physical Dated Brent premium: the last visible observation was 126.55 vs futures 111.05, but it was 7 days old.
  - Evidence that US export capacity (already at the 76.9th percentile) can expand enough to arbitrage the spread.
- **Not established in Gamma:** freight rates, actual transit counts, and a current Dated Brent print.

## Usability Report

### What worked well

- **Prediction Markets intent search and contract depth.** "Hormuz" turned a vague geopolitical premise into a quantified, dated catalyst: probability history, resolution source (IMF Portwatch), book depth and bucket distributions. It was the single most decision-relevant surface this run.
- **Commodities curve tables with contract codes and DTE.** Twelve priced nodes per root made the same-month spread computable by hand. The Brent 12d vs WTI 30d DTE caught the expiry mismatch immediately.
- **Commodities → Strategy Lab → Risk → Strategy Lab.** The loaded series carried through, the research book stayed isolated from the account, the draft survived the round trip, and Risk now decomposes VaR and ES per research leg. Three prior P1/P2 items are closed.
- **Research Operator runs authorized tools.** It produced the same spread table computed by hand and stated exactly which months it could not see.
- **Copilot honesty.** The follow-up answered "not in context" instead of inventing Apr-27 Brent.
- **Options symbol-change invalidation** with an explicit explanatory message.
- **Setup data-sources table** ("Live data: source by tab") is a good map of which provider feeds each tab.

### Friction points (ranked)

1. **P0 — GUA-20261021-1: Strategy Lab "Add Leg" crashes on a duplicate key and wedges the whole app** (Thesis 2 step 2).
   - Cause: `addPortfolioDraftLeg` (`frontend/src/views/StrategyLabView.svelte:209`) builds the id from `defaultStrategyPortfolioDraftLeg(length + 1)` (`frontend/src/lib/view-models/research.ts:173`, `draft-leg-${index}`). After handoff accepts or Remove leg, that id already exists. Console: `Uncaught Svelte error: each_key_duplicate — duplicate key 'draft-leg-4' at indexes 0 and 3` (18 errors).
   - Effect: Add Leg and Remove leg stopped responding. After one more tab switch, Ctrl+1, Ctrl+3 and the navigation toggle were dead and the topbar stuck on "Refreshing…". Only a reload recovered, and the unsaved draft was lost.
   - Repro: open Strategy Lab with the default 3-leg book, accept any commodity handoff (it becomes `draft-leg-4`), remove two legs, press Add Leg.
   - Acceptance: leg ids are unique (monotonic counter or UUID); Add Leg after any remove/accept sequence works; a keyed-each failure can never take down shell navigation; a regression test covers handoff accept → remove → add.
   - Status (same day, after the audit): **fixed in the working tree, except shell-level error isolation.**
     - `appendStrategyPortfolioDraftLeg` / `nextStrategyPortfolioDraftLegId` (`frontend/src/lib/view-models/research.ts`) now issue unused ids for Add Leg, composer objects and handoff accepts.
     - Reset keeps the leg's own id, and the draft restored from the store is de-duplicated with `ensureUniqueStrategyPortfolioDraftLegIds`.
     - Regression tests in `research.test.ts` replay the audit sequence.
     - Browser check: remove → add cycles and a Strategy Lab → Macro → Strategy Lab round trip raised 0 errors.
     - Still open: isolating a view's render error so it cannot wedge shell navigation.
2. **P0 — GUA-20261021-2: Crack and inter-commodity spreads are shown as current but come from week-old history** (Thesis 1 step 6).
   - Evidence: `/commodities/spreads` puts the last observation of the gasoline, distillate, 2-1-1 and 3-2-1 cracks at `2026-10-14T00:00:00` (FRED `DCOILWTICO` 101.91), stamped `retrieved_at 2026-10-21T10:31`. Copper–Aluminum ends on `2026-07-01`. The matrix sits beside a live WTI of 100.05 with no date.
   - Size of the error: recomputed on today's fronts, the gasoline crack is ~33.5, not 23.54, and its "0.8%" percentile is an artefact.
   - Acceptance: every spread row shows the date of its latest aligned observation; spreads whose legs are older than the headline quotes are flagged stale or computed from the same-vintage quotes; `retrieved_at` never stands in for observation time.
3. **P1 — GUA-20261021-3: Naive UTC timestamps give wrong freshness and unlabeled clocks across tabs** (Thesis 1 step 1).
   - Cause: `now_utc()` in `src/utils/time.py:7` returns a naive `datetime.utcnow()`. Payloads carry `"2026-10-21T10:30:52.391105"` with no offset, and `formatSitrepSectionAge` (`frontend/src/lib/view-models/sitrep.ts:287`) parses it as local time. Tests in `sitrep.test.ts:245` only use `Z` strings.
   - Effect: SITREP showed "OLDEST EQUITIES 2H OLD" and "2h old" for every section loaded seconds earlier. Commodities "TIME 10:33 AM", Options "Updated 10:50 AM" and the Strategy Lab source stamp `10:42` are UTC presented as local, while Prediction Markets shows a correct local "12:38:17 PM".
   - Inferred from code, not observed: west of UTC the error flips and stale data reads "<1m old".
   - Acceptance: the backend emits timezone-aware ISO 8601 with an offset; the frontend shows zone-labeled or local times consistently; a test covers naive-input handling.
4. **P1 — GUA-20261021-4: Basis reconciliation is date-blind and still unit-blind** (Thesis 1 step 7).
   - Evidence: "WTI … 100.05 differs from FRED spot proxy 101.91 by 1.9%" and "Brent … 111.05 differs from FRED spot proxy 126.55 by 14.0%" compare today's futures with FRED spot from 2026-10-14. "Copper … 6.49 vs 13542.82 by 208636.4%" mixes USD/lb with USD/t.
   - Effect: the reconciliation labels a large, real physical-vs-futures premium a data "conflict" and hides its date.
   - Acceptance: each reference shows its observation date and unit; conversions run before comparison; references older than N days are labeled stale rather than "conflict"; a futures–spot basis is shown as a value with dates.
5. **P1 — GUA-20261021-5: Macro EU header "EUR/USD 0.852" is an inverted, monthly USD/EUR series** (Thesis 2 step 1).
   - Cause: `src/application/macro_service.py:232` maps `eu-eurusd` to FRED `CCUSMA02EZM618N` (monthly average, euros per dollar) and titles it "EUR/USD Exchange Rate". The same page's FX widget shows EUR/USD 1.1224.
   - Acceptance: title and value agree (invert, or label it USD/EUR, monthly average, with an as-of); the header uses the daily IBKR pair where available.
6. **P1 — GUA-20261021-6: Copilot multi-context synthesis truncates at its output cap with no answer and no retry** (Thesis 1 step 18).
   - Evidence: the turn record shows `output_tokens 1422`, `reasoning_tokens 114` against `max_output_tokens=1400` (`src/services/openai_copilot_provider.py:254`, `:427`), about 99k input tokens, and "context exceeded its scope budget … 2199 repeated item(s)" compacted. The card shows only "incomplete", with no partial text and no Retry or Continue.
   - Evidence scope: the attached Commodities evidence carried only the selected instrument (`commodities.curve.wti`), so Brent could not be analysed even after viewing it and adding it to the Strategy Lab book.
   - Acceptance: the output budget scales with the requested sections or is continued automatically; partial output is shown; an explicit Continue/Retry keeps the prompt; Commodities context includes every curve viewed or referenced by an included tab.
7. **P1 — GUA-20261021-7: The Sealanes handoff dead-ends and the static chokepoint layer disappears with an empty AIS sample** (carries GUA-20260708-9; Thesis 1 steps 8 and 11).
   - Effect: "Open in Sealanes" for Strait of Hormuz opened the default Atlantic view (zoom 3.0) with no pan, highlight or message, and `chokepoints: []` because the 6-second sample was empty. The Commodities cross-domain "Sealanes Energy Chokepoints" row is inert.
   - Acceptance: chokepoint geometry and metadata render independently of live AIS; an entity handoff pans and zooms to the target and states live coverage (for example "0 AIS positions in last sample"); cross-domain rows are actionable.
8. **P1 — GUA-20261021-8: Metals "front" contracts are delivery months with no trade, and the FRED fallbacks are dead** (SITREP evidence).
   - Evidence: SITREP Gold `GCV6` 0.00 / 0.0%, Silver `SIV6`, Platinum `PLV6` and Aluminum `ALIV6` all 0.00. Copper's front is "Oct 2026". FRED `GOLDAMGBD228NLBM`, `SLVPRUSD` and `PPLTUSDM` fail with `HTTPError` (likely discontinued series; not verified). Zinc's LME contract lookup fails on every refresh (IBKR Error 200, 6 times in 3 minutes, no negative cache).
   - Acceptance: front selection skips delivery or thin months (by volume/open interest or exchange roll calendars); fallback series are valid; failed contract discovery is cached for the session.
9. **P1 — GUA-20261021-9: Commodity research books silently use spot proxies ending a week ago** (Thesis 1 steps 12–15).
   - Evidence: the Brent/WTI handoffs resolve to FRED spot to 2026-10-14 while the tab headline is IBKR futures; Validate Book does not warn that both legs end 7 days before today. Risk stress replay covers 0/6 because history is truncated to one year and all episodes are equity crashes.
   - Acceptance: the handoff states which series (futures front, continuous, spot proxy) and end date it carries; validation warns when the window end lags today by more than N trading days; commodity books can replay commodity episodes (2020, 2022) using full available history.
10. **P2 — GUA-20261021-10: Options headline uses a 0DTE pre-market chain labeled LIVE; the template defaults to the nearest expiry** (Thesis 1 step 21; carries the known default-expiry sore spot).
    - Evidence: USO front ATM IV 56.3% from 2026/10/21 with call/put IV 14.0% / 98.6% at the same strike; the Call Spread template filled 0D legs; Net Theta +0.453 on a 0.68 debit (unverified, see below).
    - Acceptance: the headline skips same-day expiries outside regular hours; quotes outside the session are labeled `closed/stale`; templates take a horizon or default to ≥ 30 DTE.
11. **P2 — GUA-20261021-11: Strategy Lab LOOKBACK does not determine the window** (Thesis 2 step 3).
    - Evidence: LOOKBACK `252` gave 319 observations, 2025-07-16 → 2026-10-20, with no unit on the field.
    - Acceptance: the analysed window follows the field (trading days, labeled), or the composer says why it differs.
12. **P2 — GUA-20261021-12: SITREP cold load is still one ~77 s aggregate request** (carries GUA-20260901-7).
    - Acceptance: sections render progressively as each provider returns.
13. **P2 — GUA-20261021-13: Copilot and Operator rendering noise.**
    - Evidence: the Operator RATIONALE table rendered as raw `| Delivery | Brent |` pipes; step details dump raw JSON; one "Operator warning" step per FRED failure; an irrelevant SEC-identity warning on a commodities task; an empty "PROPOSED TEST" heading on the Agent card; context snapshots of 4.6–5.0 MB per turn under `data/copilot/snapshots/`.
    - Acceptance: markdown tables render; trace JSON is collapsed by default; repeated warnings are coalesced; warnings are scoped to the task; empty sections are omitted.
14. **P2 — GUA-20261021-14: Setup and first-run friction.**
    - Evidence: the backend never auto-connects to TWS (the gate failed until Setup's Test connection); Review says "No changes" without warning that the empty SEC identity disables Fundamentals; the EIA row says "Also set COMMODITIES_PROVIDER=eia" while the Commodities row promises "IBKR futures with EIA reference data"; the "Setup saved" modal stays open and swallows the next click.
    - Acceptance: optional auto-connect when TWS is reachable; Review lists the capabilities lost by skipped steps; consistent provider guidance; the modal closes on Finish.
15. **P2 — GUA-20261021-15: Prediction Markets RELATED misses same-series siblings, and bucket markets are not grouped.**
    - Evidence: the Dec 31 contract showed "No linked markets" although Oct 31 and Nov 30 share the series "Hormuz Traffic Returns to Normal"; transit buckets list as separate rows with no implied distribution.
    - Acceptance: same-series contracts link automatically; bucketed events can be viewed as one distribution.
16. **P2 — GUA-20261021-16: Accessibility and automation.**
    - Evidence: navigation and table-row buttons have no accessible name; five identical "Remove leg" names with no leg identity; duplicate "Copilot" buttons (topbar and Options header); weight and ticker inputs are named by their value; template buttons are named by description ("bullish / defined risk"), not "Call Spread"; Copilot drawer refs report offscreen while visible; the sidebar item goes offscreen after a toggle.
    - Classification: automation/agent-workflow friction, not human blockers.
17. **P2 — Risk copy contradiction:** "Largest modeled risk contributor is N/A" sits next to "TOP RISK CONTRIBUTORS: Brent 70.7%" (Thesis 1 step 14).
18. **P2 — Transient wrong-market header on drill:** while REFRESHING, the Sitrep → Commodities drill for Brent shows the WTI headline and the WTI basis conflict (Thesis 1 step 2).

### Gaps

- **Freight and transits:** no tanker freight (TD3C/TD25, dirty tanker index) and no chokepoint transit counts. IMF Portwatch, the resolution source of the Hormuz markets, is not ingested; Sealanes is the natural home.
- **Inter-commodity spreads:** no Brent–WTI (or other inter-commodity) spread, no spread curve by delivery month, and no Dated-vs-futures basis series.
- **European sovereigns:** no OAT, Bund or BTP yields and no spreads; no ECB calendar.
- **Futures return streams:** no roll-adjusted futures streams for Strategy Lab and Risk; no commodity stress episodes.
- **Options horizon:** templates cannot target an expiry that matches the thesis horizon (Mar/Apr-27); the USO surface depth stops at Feb-27.
- **Deferred curve changes:** day-over-day change for deferred curve nodes is N/A by design ("Gamma does not diff local cached curve snapshots of unknown market vintage"). It is honest, but it removes the "how did the back of the curve move today" read.

### Cross-tab coherence

- Carried well: Sitrep → Commodities (after a transient WTI header), Commodities → Strategy Lab, Strategy Lab → Risk → Strategy Lab, and Options symbol state.
- Dropped:
  - Prediction Markets → Sealanes: navigation only, no entity focus.
  - Commodities → Sealanes: inert row.
  - Copilot Commodities context: only the selected instrument (WTI), although Brent was viewed and is a Strategy Lab leg.
  - Unsaved Strategy Lab draft on reload.
- Inconsistent: clocks (Prediction Markets local; Commodities, Options and Strategy Lab UTC unlabeled; Sitrep ages offset by 2 h). US 10Y reads 5.15% in Macro (FRED) and 5.12% in SITREP (Treasury) with no as-of on either. The EU EUR/USD header (0.852) contradicts the FX widget (1.1224) on the same page.

### Copilot evaluation

- **Prompt 1 — Research Agent, contexts SITREP + Strategy Lab + Prediction Markets + Commodities + Risk, profile Auto:** a 685-character four-part request (Dec-26/Apr-27 prices and spreads, Hormuz probability, Strategy Lab and Risk stats, stale inputs with dates, cite sources). Result: `incomplete · OPENAI_RESPONSES / GPT-6.1-SOL · max_output_tokens` after 49 s, no body. Evidence: 26 sources, 1 tool (`get_synthesis_domain_context`), 58 warnings.
- **Prompt 2 — follow-up, 200-word cap, "say 'not in context'":** grounded and honest in 23 s.
  - Dec-26 Brent 111.05 (as of 10:39:14) and WTI 99.93 (10:40:54) → $11.12.
  - Apr-27 WTI 92.19; Apr-27 Brent "not in context".
  - Hormuz 11%.
  - Stalest inputs: "Risk frontier alignment ends 2026-03-06" and FRED metals 2026-07-01. It missed that the Strategy Lab book and the cracks end 2026-10-14.
  - It did not summarise the book ("Strategy Lab: no current handoffs").
- **Prompt 3 — Research Operator:** load the Brent curve and report same-month Brent, WTI and spread, Dec-26 to Nov-27, with timestamps. Result in ~2 min, from 3 validated tool observations:
  - Correct six-month table matching the hand computation; it noted the two quotes are 100 s apart, that Brent is cached, and "Time zones were not supplied".
  - It reported WTI Jun–Nov N/A because the per-run inspection limit was exhausted, and did not retry.
- **Hallucination:** none observed; every number traced to a curve or contract object.
- **Grounding scope:** limited by the selected-instrument context (Brent missing in Prompt 1) and the 1,400-token output cap.

## What Could Not Be Proven This Run

- Whether each IBKR futures quote was live or delayed; the UI says "live or delayed" and the entitlement was not checked contract by contract.
- Whether the empty 6-second AISstream samples reflect a provider outage, a regional receiver gap or a key problem. The payload does not distinguish them.
- The west-of-UTC direction of GUA-20261021-3 ("stale reads fresh"), which is inferred from code; the run was in CEST.
- The USO Net Theta of +0.453 on a 0.68-debit long call spread looks wrong in sign and scale, but it may be stale pre-market greeks; it needs a regular-session retest.
- The root cause of LOOKBACK 252 → 319 observations (possible cache reuse) was not traced.
- Copilot behaviour under the Standard/Deep profiles, Script runtime execution, Fundamentals (SEC identity not set), Equity Research, Crypto and Portfolio were not exercised.
- Visual quality beyond structure: most inspection was text and accessibility-tree based; a few screenshots of Sealanes and Copilot were taken.

## Scoring

The 2026-09-04 report used partly different categories; Δ is given where a category maps directly.

| Category | Score | Δ vs prior | Rationale (one sentence) |
| --- | ---: | :--: | --- |
| Data breadth | 7/10 | = | Futures curves, EIA, Treasury/FRED, prediction venues and RSS were all live; there is no freight, transit or EU sovereign data. |
| Data depth / drill-down | 6/10 | +1 | Curve nodes with DTE and full contract detail (resolution, depth, history) are strong, but spreads and basis checks hide week-old observation dates. |
| Analytical tooling (DCF, risk, scenarios, CSV) | 6/10 | +2 | Compose → Risk now decomposes per leg and replays measured regimes, but there is no inter-commodity spread, lookback is not honoured, and Add Leg can crash the app. |
| Copilot usefulness | 6/10 | +3 (vs agent drivability) | The Operator now runs tools and stays honest; the first-shot synthesis still truncates at 1,400 output tokens with selected-instrument-only evidence. |
| Cross-tab workflow / state continuity | 6/10 | +1 | Three handoff defects are closed; the Sealanes handoffs dead-end and clocks disagree across tabs. |
| Visual density & terminal feel | 7/10 | n/a | Dense, legible tables, though Operator traces leak raw JSON and markdown. |
| Speed to insight | 5/10 | +1 | Prediction Markets search was instant and decisive; SITREP's 77 s cold load and the forced reload cost minutes. |
| Overall (gestalt, not an average) | 6/10 | +1 | Gamma carried a real cross-asset thesis further than any prior run, but one P0 wedge and one P0 silent-staleness defect undermine trust. |

## Prioritized Follow-Up

**P0**
1. **GUA-20261021-1** — unique composer leg ids; a keyed-each error must not wedge shell navigation; add the handoff accept → remove → add test. Status: Partially done (unique ids, restore de-duplication and regression tests landed with this report; shell error isolation still open).
2. **GUA-20261021-2** — spreads show the date of their latest aligned observation and flag staleness versus the headline quotes; `retrieved_at` must not stand in for observation time. Status: Open.

**P1**
3. **GUA-20261021-3** — emit timezone-aware timestamps (`src/utils/time.py`); zone-label all clocks; fix the age calculation; add a naive-input test. Status: Open.
4. **GUA-20261021-4** (absorbs the basis part of GUA-20260708-7) — date- and unit-aware basis reconciliation; show physical-vs-futures basis as a dated value. Status: Open.
5. **GUA-20261021-5** — correct the EU EUR/USD series label/orientation and frequency, or use the daily IBKR pair. Status: Open.
6. **GUA-20261021-6** (carries GUA-20260901-4 and GUA-20260904-2) — scale or continue the output budget, show partial output, add Continue/Retry, and include every viewed curve in the Commodities context. Status: Open.
7. **GUA-20261021-7** (carries GUA-20260708-9) — static chokepoint layer independent of AIS; entity-focused Sealanes handoffs; actionable cross-domain rows. Status: Open.
8. **GUA-20261021-8** — liquid front-month selection for metals, valid FRED fallbacks, negative cache for failed contract discovery. Status: Open.
9. **GUA-20261021-9** (carries GUA-20260627-2) — state the series type and end date in commodity handoffs, warn on stale windows, add commodity stress episodes. Status: Open.
10. **GUA-20260903-10** — attribute all provider calls, including FRED, Treasury, prediction venues, EIA and AISstream, and count their failures. Status: Open.

**P2**
11. **GUA-20261021-10** — no 0DTE/off-hours headline IV; session-state labels; horizon-aware template expiry. Status: Open.
12. **GUA-20261021-11** — honour and label LOOKBACK in the composer. Status: Open.
13. **GUA-20261021-12** (carries GUA-20260901-7) — progressive SITREP rendering. Status: Open.
14. **GUA-20261021-13** — Copilot/Operator rendering and trace hygiene; review the snapshot size. Status: Open.
15. **GUA-20261021-14** — Setup auto-connect option, Review warnings, consistent provider hints, modal close. Status: Open.
16. **GUA-20261021-15** — same-series related markets and bucket grouping. Status: Open.
17. **GUA-20261021-16** (carries GUA-20260627-6) — accessible names and offscreen refs. Status: Partially done.
18. Risk "largest contributor N/A" copy and the transient wrong-market drill header — small fixes. Status: Open.
19. Gaps to route through `roadmap.md` before implementation: freight/Portwatch in Sealanes, inter-commodity spread curves, EU sovereigns, roll-adjusted futures streams.

Visual and density observations (raw markdown tables, JSON traces) belong to `gamma-ui`; chart internals were not assessed.

## Fix Status (2026-10-22, uncommitted working tree)

All friction findings above were fixed in one pass on top of `c69ebfc`: seven area agents worked in isolated worktrees and the integrator merged and wired their changes.

**Suites on the integrated tree:**
- Backend `pytest`: 1169 passed, 4 skipped.
- Frontend `vitest`: 607 passed.
- `tsc --noEmit`: clean.

**Browser check:** live backend with TWS closed (IBKR-dependent paths not exercised), so "verified" below means seen in the running app.

| ID | Status | Verified |
| --- | --- | --- |
| GUA-20261021-1 | Fixed: unique leg ids; restored drafts are de-duplicated; a per-view `<svelte:boundary>` in App/Shell keeps navigation alive. | Remove → Add Leg ×3 raised 0 errors. The boundary fallback is covered by SSR tests only. |
| GUA-20261021-2 | Fixed: spreads carry `observed_at`, lag and a `freshness` flag (stale beyond 4 days); an "Obs" column; a same-snapshot "Live" value when every leg has an IBKR front. | Column visible; spread rows need TWS, so not live-checked. |
| GUA-20261021-3 | Fixed in the frontend: `lib/time.ts` reads offset-less API instants as UTC, wired into SITREP ages, provenance badges, Commodities, Options, Strategy Lab, Sealanes, Prediction Markets, Diagnostics and Copilot. Commodities times show their zone; PRIOR shows as a date. A backend wire-format "Z" was tried and reverted: clients echo timestamps back (`expected_updated_at`) and 11 Copilot tests failed. | SITREP ages read "<1m old". |
| GUA-20261021-4 | Fixed: references carry their date and unit; units are converted; old references are reported as `stale_reference` and dated futures-vs-spot gaps as `basis`. Copilot now receives these statuses. | Not live-checked (needs IBKR quotes). |
| GUA-20261021-5 | Fixed: the EU EUR/USD series is inverted and titled "(monthly avg)". | Live: 1.174. |
| GUA-20261021-6 | Fixed: output budget sized per request (ceiling 25k tokens); one automatic continuation on `max_output_tokens`; partial text shown; Retry/Continue keeps prompt and context; Commodities context covers viewed instruments and Strategy Lab legs. Decision recorded in `docs/copilot_v2_tab_plan.md`. | **Not verified live:** no OpenAI calls were made. |
| GUA-20261021-7 | Fixed: a static chokepoint reference is served in live mode; AISstream now subscribes with real bounding boxes, which were empty before; the entity handoff pans, highlights and annotates. Integration bugs fixed: Commodities sent `commodity_links` as objects (group unresolvable), and `applyProjection()` cancelled the focus `fitBounds`. | Live: PM → Sealanes zooms to Hormuz (6.5) with "8 AIS positions in the last 6 s sample"; the Commodities row resolves all 5 chokepoints. |
| GUA-20261021-8 | Fixed: active-month calendar for metals fronts; dead FRED LBMA fallbacks dropped with a warning (env override available); negative cache for failed contract lookups. | Not live-checked (needs TWS). |
| GUA-20261021-9 | Fixed: legs state series type and end date; Validate warns beyond 3 trading days of lag; benchmark caveats are separated; commodity stress episodes added. | Live: an 8/8-episode replay including "2020 oil price war" and "2022 energy shock". The episode windows were set from memory and must be checked against an official source. |
| GUA-20261021-10 | Fixed: headline skips 0D/1D (≥7D); "closed · last session" outside 09:30–16:00 ET (holidays not modelled); put/call IV divergence warning; templates default to ≥30 DTE; the empty state no longer names SPY. Theta aggregation was reviewed and found correct. | Empty state seen; session labels need TWS. |
| GUA-20261021-11 | Fixed: the window is trimmed to N trading days and the field is relabelled. | Live: "Lookback 1700 trading days · analysed 1700". |
| GUA-20261021-12 | Fixed: six concurrent `sections=` requests with isolated failures. | Live: news 5.1 s, FX/rates 7.6 s, indices 14.3 s (was ~77 s for anything). |
| GUA-20261021-13 | Fixed: markdown tables render; JSON collapsed; warnings coalesced; the SEC warning only appears for company lookups; empty sections hidden; snapshots about halved. | Not verified live. |
| GUA-20261021-14 | Fixed: opt-in `IB_AUTO_CONNECT` (one attempt, no retry); Review lists lost capabilities; EIA guidance and activation condition now count `ibkr`; the modal closes on Finish. | Live: auto-connect failed cleanly ("not retrying"); Review table shown. |
| GUA-20261021-15 | Fixed: same-series/same-event siblings in RELATED; a "Group" toggle with distribution and Σ; Copilot gets separate caps (5+5 context, 8+8 flow tool) so siblings reach the model without ~36 rows. | Live: RELATED lists the Oct 31 and Nov 30 Hormuz siblings; grouping shows "Σ 103.0% · +3.0% vs 100%". |
| GUA-20261021-16 | Fixed: per-leg names for Remove/inputs, a distinct Options Copilot button, template names, SITREP row names, `aria-current` on tabs. Part of this finding was a tooling artefact: the accessibility snapshot hid content-derived names. | Live: names present in the accessibility tree. |
| GUA-20260903-10 | Fixed: a central urllib recorder attributes every call by host or adapter and counts failures. | Live: 12 named rows summing to the 520 total, 25 failures counted. |
| Risk copy / transient drill header | Fixed. | Risk copy verified live; drill header covered by tests only. |

**New observations during verification:**
- **App.svelte (pre-existing, fixed):** used `getTabLabel` without importing it since `17fbded`, so every cross-domain handoff threw after navigating.
- **`us_macro_events` (open):** 23 of 31 requests fail. This was invisible before the provider-usage fix.
- **SITREP Commodities section (open):** takes ~94 s when TWS is down; other sections are no longer blocked.
- **Prediction Markets "Event Book" (open):** treats a cumulative date ladder ("Putin out by …?") as a complete book (Σ 11.5 %, overround −88.5 %). This panel predates this pass.
- **Gaps section:** not addressed (freight/Portwatch, inter-commodity spread curves, EU sovereigns, roll-adjusted futures). Route these through `roadmap.md`.

## Coverage Ledger Update

- Prediction Markets: first deep use. One liquid contract with probability history, resolution terms, depth, venue and series siblings. Worked; RELATED and grouping gaps remain.
- Sealanes: first substantive use. Blocked: empty AIS sample, no static chokepoints, dead-end handoff.
- Commodities, Strategy Lab, Risk, Copilot (Agent and Operator): deep use. Options and Macro: micro-missions.
- Not covered: Equity Research, Crypto, Portfolio, Fundamentals (SEC gate only).

## Cleanup And Residual State

- **Files left by the audit:**
  - `data/setup/setup.json` (Setup finished with no changes and no SEC identity).
  - One appended snapshot in `data/portfolio_history_live.csv`.
  - One Copilot session with three turns, three context snapshots and four working analyses under `data/copilot/` (all git-ignored).
- **Strategy Lab:** no strategy or experiment was saved, and the composer draft is back to the original default book after a reload.
- **Processes:** TWS was not reconfigured. The audit-launched backend (IBKR client id 1) and frontend were stopped at the end. They were briefly restarted, without a TWS connection, to verify the GUA-20261021-1 fix, then stopped again.
