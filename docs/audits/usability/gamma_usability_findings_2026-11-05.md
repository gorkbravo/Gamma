# Gamma Usability Findings — 2026-11-05

Date: 2026-11-05, 03:07–03:17 and 14:03–14:40 Europe/Madrid (CET, UTC+1)<br>
Audience: future AI agents and contributors improving Gamma<br>
Mode: full (V6 hardening gate, with a visual pass in both themes)<br>
Data: live IBKR (TWS on 7496, account identifier masked and not retained), market data `Auto`. US cash and options markets were closed during both blocks (they open at 15:30 Madrid); CME futures were trading.<br>
Context: the live audit for checkpoint V6 of [`docs/visual_refresh_plan.md`](../../visual_refresh_plan.md) on branch `claude/v6-hardening`. It builds on [`gamma_usability_findings_2026-10-27.md`](./gamma_usability_findings_2026-10-27.md); the V6 acceptance is no new P0/P1 visual finding.

## Audit Setup

- Branch `claude/v6-hardening` (main 4b60e16 plus V6a–V6d, the gate and the fixes below). Suites at the end: vitest 82 files / 654 tests, `tsc --noEmit` clean, `vite build` with the four known warnings.
- Backend `uvicorn src.api.main:app` on 127.0.0.1:8010 with the repo `.env`, `IB_CLIENT_ID=17` and `IB_AUTO_CONNECT=false`, connected with `POST /system/connection`; Vite on 127.0.0.1:5174. Gate (`check-live-ibkr.ps1 -ApiBase http://127.0.0.1:8010`) exit 0 at 03:07 and again at 14:03:25.
- Interruptions, not product faults: the session paused at 03:48 and TWS was closed by 06:52, so the audit resumed at 14:03 after the user reopened TWS. The worktree has no SEC identity, so Fundamentals was not exercised live.
- The Browser pane was hidden (it does not paint), so Gamma was driven with headless Playwright at 1440×900, DPR 1: main-region text dumps with Madrid timestamps and screenshots. Keybindings were not exercised.
- Tabs exercised: Sitrep, Macro (Snapshot, Rates & Policy, Events / Regimes), Prediction Markets (Screener, Contract), Strategy Lab (Composer, Validate, Regime Stress), Risk (research book: Overview, Scenarios), Options (Overview, off-hours), Commodities (Overview, Curves & Spreads), Copilot (Research Agent); visual pass of the twelve Research tabs in both themes. Portfolio and the account's Risk were not opened, so that no account data was captured.
- Outside tools: direct API reads (`/macro/snapshot`, `/system/setup`, `/system/provider-usage`, `/maritime/workspace`) for exact values and payload fields; backend logs for the two tracebacks.
- Copilot: three Research Agent runs; the first never reached the model (GUA-20261105-1).

## Regression Delta (vs `gamma_usability_findings_2026-10-27.md`)

| ID | Finding | Prior status | This run | Evidence |
| --- | --- | --- | --- | --- |
| GUA-20261027-1 | FOMC/ECB decision dates | Fixed | **Confirmed fixed** | Macro calendar at 03:09: "FOMC Meeting (December 8-9, SEP) · Dec 9, 2026" and "FOMC Meeting (January 26-27) · Jan 27, 2027". |
| GUA-20261027-2 | Duplicate Operator render | Fixed | Not retested | No Operator run. |
| GUA-20261027-3 | Operator curve inspection | Fixed, tool-level check | Not retested | No Operator run. |
| GUA-20261027-4 | Crack history by cache state | Fixed | Not retested across selections | The 2-1-1 crack stays dated: "51.518 USD/bbl · Live 58.739 · Nov 5, 2026, 02:27 PM · Obs 2026-11-03". |
| GUA-20261027-5 | Options symbol edits | Fixed | **Confirmed fixed** | "ZZQXW" → "Options surface failed: RuntimeError: Unable to qualify underlying contract for ZZQXW". Entering the field selects "TLT" (0–3); typing gives "SPY". |
| GUA-20261027-6 | Risk share of result on a near-neutral book | Fixed, unit-tested | Partially retested | GFC replay of a SHY/BIL book: "Share of result" 144.1% / −44.1% (legs offset, net not near zero, so the gross basis did not apply). The near-neutral case was not reproduced. |
| GUA-20261021-2 | Cracks stamped current | Confirmed fixed | Still fixed | As above: Obs date and a same-snapshot Live value. |
| GUA-20261021-5 | EU EUR/USD inverted | Fixed | **Confirmed fixed** | EU snapshot: "EUR/USD Exchange Rate (monthly avg) 1.174 · fred". |
| GUA-20261021-10 | Options off-hours labels | Confirmed fixed | Still fixed | TLT at 14:24: "Stale · closed · last session" and "US options are outside regular hours … last-session or indicative values, not live." |
| GUA-20261021-12 | Sitrep cold load | Confirmed fixed | Holds | Cold at 03:09 with TWS: news and predictions at +14 s while the other sections showed "Loading"; every section loaded by +58 s. Macro › Rates & Policy was still "Rates context loading" 33 s after a cold open and loaded within 15 s warm. |
| GUA-20261021-16 | Accessible names | Mostly fixed | Mostly fixed | "Options underlying symbol", "Expiry", "Payoff option type"; one Options select (value "auto") is still unnamed. |
| RSS `ecb_press` | Certificate chain | Fixed | Calls recorded | Provider Usage lists "www.ecb.europa.eu via news.latest" and "via macro.load_events"; their outcome was not inspected. |
| GUA-20261021-7, -14, Risk copy | — | — | Not retested | Out of the thesis path. |

## Thesis Log

### Thesis 1: the front end prices December, not a two-meeting +73 bp path

- Signal that sparked it (captured before the thesis):
  - Macro › Rates & Policy, 03:09: "2Y Treasury sits 73 bps above Fed Funds; the path proxy leans toward further tightening". The Meeting Ladder reads "FOMC Meeting (December 8-9, SEP) · Dec 9, 2026 · 4.25% · +37 bps" and "FOMC Meeting (January 26-27) · Jan 27, 2027 · 4.61% · +37 bps · +73 bps".
  - Macro reads "Market bias Easier · Avg probability 67%".
  - Sitrep › Rates, 03:12: 3M 4.21% (+38.0 bp over 3M), 2Y 4.61%, Fed Funds 3.88% (+0.25 pp).
  - Prediction Markets, 03:13: "Will the Fed increase interest rates by 25 bps after the December 2026 meeting?" 78.0%; no change 22.0%; +50 bp 0.8%.
- Thesis: Polymarket and the 3M bill price about one December hike, while Gamma's ladder allocates the whole 2Y premium to December and January; if January is priced as a hold, the 2Y premium is about later meetings, and the near-dated hawkish risk sits in December alone.
- Steps:
  1. **Macro:** read the ladder and the linked contracts — worked. The "Easier" bias comes from three resolved contracts (GUA-20261105-2).
  2. **Sitrep:** compare the Rates table — partial. The Prior column repeated the current value for Fed Funds and 2s10s (GUA-20261105-3, fixed during the run).
  3. **Prediction Markets:** read December, then search "Fed January 2027" at 14:05 — worked. January: +25 bp 24.0%, no change 77.0%, +50 bp 0.6%, −25 bp 1.5%. December unchanged at 78.0%; the Event Book reads "5 legs · complete · Book Sum 101.5%".
  4. **Prediction Markets › Contract:** open the December contract — partial. After a screener Refresh the row was fresh (24H volume 209,440), but the contract page still showed the 03:13 detail ("Retrieved 11/5/2026, 3:13:36 AM", 24H volume 529,567) (GUA-20261105-5). Opening the contract also triggers the wallet summary, which returned 500 (GUA-20261105-4).
  5. **Strategy Lab:** compose "Long 1-3Y Treasuries" SHY +1 and "Short T-bills" BIL −1, then Validate and Compose — worked.
     - Validate: "VALID · 2/2 · 756 aligned obs · 2023-10-31 to 2026-11-04"; weights normalised to 0.5 / −0.5.
     - Total return −0.43%, annual vol 0.81%, Sharpe −0.17, max drawdown −1.52% (Sep 28, 2026).
     - Annual returns: 2023 +0.61%, 2024 −0.61%, 2025 +0.39%, 2026 −0.81%.
  6. **Strategy Lab › Regime Stress:** worked. The 63-day rolling return is −0.17% to −0.34% from Oct 20 to Nov 4 and the beta 0.01–0.02. It cannot condition on a policy regime or an FOMC date.
  7. **Risk (Open In Risk):** worked. "Strategy Lab book: Front-end pause: SHY vs BIL · USD", coverage 100%. Stress replay covered 8/8 episodes: GFC +3.1%, COVID +0.9%, Q4 2018 +0.3%, 2022 rate shock −2.5% (SHY leg −4.4%), August 2024 +0.4%, 2025 tariffs +0.4%.
  8. **Options:** load TLT for an implied-move check — blocked by the clock, not the product. The market was closed, so the surface was "Stale · closed · last session".
  9. **Copilot:** see the Copilot evaluation. Run 1, with Prediction Markets in the context, hung (GUA-20261105-1). Run 3, with Sitrep + Macro, identified the three linked contracts as December 2025 and January 2026 markets and called the "Easier" read unreliable.
- Outcome: **partially confirmed.**
  - The contracts (≈ +19 bp in December plus ≈ +6 bp in January, ≈ +25 bp by end-January, normalised for the book overround) and the 3M bill spread (+33 bp, a period average) roughly agree with each other.
  - Both disagree with Gamma's +73 bp ladder. The disagreement is a Gamma heuristic, not a market mispricing (GUA-20261105-6).
  - Whether the 2Y premium is about later hikes or term premium cannot be settled in Gamma: there is no meeting-dated curve.

### Thesis 2: credit is pricing the tightening that equities ignore

- Signal (captured before the thesis): Macro at 03:09 — "US High Yield OAS 3.40% +0.55 pp" over 3M while "US Unemployment Rate 4.20% −0.10 pp"; Macro's Recession Risk divergence score 2.10. Sitrep at 03:12: S&P 500 +1.6% and DJIA +3.0% on Nov 4.
- Thesis: a 55 bp widening in HY spreads during a hiking cycle, against an equity rally, says equities lag credit; test whether past widening of that size preceded SPY underperformance.
- Steps:
  1. **Macro › Cross-Asset:** read the lead-lag — worked: "2s10s Treasury Slope moved first …; US High Yield OAS only aligned roughly 34d later."
  2. **Strategy Lab:** build a test conditioned on HY OAS — blocked. Leg classes are Equity, ETF, Commodity, Prediction, Crypto and Custom; a FRED series cannot be a leg or a condition.
- Outcome: **abandoned.** Leaving Gamma (a notebook with FRED and SPY) would be needed to condition a backtest on a macro series.

## Trade Verdict

Thesis 1 as a trade:

- **The play:** a pause after December, already 77% priced for January, would favour 1–3-year Treasuries over bills. In Gamma's replay that spread earns in easing and stress windows (GFC +3.1%, COVID +0.9%) and loses in hiking shocks (2022 −2.5%, 2026 so far −0.81%).
- **Sizing:** at 0.81% annual volatility, the 0.5 / −0.5 book needs roughly ten times its notional to carry a meaningful risk budget. Gamma reports this but does not size it.
- **What kills it:** a hawkish December SEP (dots above 4.25% into 2027), or the January +25 bp contract repricing above about 50%.
- **Verdict:** not actionable from Gamma alone. The evidence that would decide it is a meeting-dated forward curve (SOFR or fed funds futures), which Gamma does not expose.

## Usability Report

### What worked well

- **Strategy Lab → Risk with a signed two-leg ETF book:** validate, compose and replay eight dated episodes in about a minute, with per-leg windows, observation counts, normalised weights and per-position episode P&L.
- **The Prediction Markets Event Book:** a complete five-leg book with its overround stated ("Book Sum 101.5%"), the resolution text and the Fed resolution source.
- **Options off-hours honesty:** "Stale · closed · last session" and an explicit outside-hours note.
- **Copilot, when it runs:** it refused to invent contract names it could not see, and with Macro in scope it caught the stale linked contracts that Macro and Sitrep present as current.
- **The visual pass:** B′ held in all twelve Research tabs in both themes; no P0/P1 visual finding (details below).

### Friction points (ranked)

1. **P1 — GUA-20261105-1: Copilot hangs when Prediction Markets is in the context** (Thesis 1, step 9).
   - Run 1 (14:12) stayed "running" with "Plan / Stop" for more than 300 s.
   - The backend log shows `_build_prediction_market_context` calling `get_wallet_summary`, which raised `HTTPError 410: Gone` from Polymarket's trades endpoint. `_execute_agent_run` catches only `ValueError` around the context builder, so the thread died without a failed event.
   - Acceptance: any provider error in a context builder fails the run within seconds with a message, and the wallet summary degrades to "unavailable" with a warning.
   - Root cause: Polymarket retired Data API v1 ("Data API v1 has been retired"); v2 answers on `/v2/trades` and `/v2/holders` filtered by `condition`.
   - Status: Fixed in `5f01681` (with the user's go-ahead, the same day). Any context-builder error now ends the run with a failed terminal event, the agent and operator workers run under a guard, and the wallet summary uses Data API v2 and degrades to a warning. Live after the fix: the same Prediction Markets card completed in 15 s with wallet flow.
2. **P1 — GUA-20261105-2: Macro's policy read uses resolved contracts** (Thesis 1, step 1).
   - `rates_policy.linked_markets` held polymarket:705689, 705688 (December 2025 FOMC cut markets, end 2025-12-12) and 1179306 (January 2026, end 2026-01-28), all `status: "resolved"`, although `_linked_prediction_markets_for_theme` asks the screener for `status="open"`.
   - They produce "Market bias Easier · Avg probability 67%", the "Policy expectations · diverging" card in Macro, and the same line in Sitrep's What Changed. Meanwhile the open December 2026 contract priced +25 bp at 78%.
   - Acceptance: only open, unexpired contracts for upcoming meetings, and the contract status carried into the Copilot context.
   - Root cause: the screener never filtered an "open" screen by status, and the US policy query "Fed FOMC rates cut hike policy" matched only settled FOMC markets (18 of 22, none open).
   - Status: Fixed in `e94fe62`. An "open" screen drops resolved and closed rows, Macro links only open contracts before their end time, the US query is "Fed interest rates", and "increase/decrease" count as tighter/easier. Live after the fix: the December 2026 meeting markets (+25 bp 78%, no change 21%, +50 bp 0.8%), "Market bias Tighter", overlay "aligned". Still open: the contract status in the Copilot context.
3. **P1 — GUA-20261105-3: Sitrep's Rates Prior column repeated the current value** on policy rows ("Feds Funds 3.88% · +0.25 pp · Prior 3.88%"; 2s10s "34 bps · −13 bps · Prior 34 bps") (Thesis 1, step 2).
   - Status: Fixed in `0697257` (3.63%, 47 bps; "Fed Funds"), with a test.
4. **P2 — GUA-20261105-4: the Polymarket wallet summary returns 500** when the trades endpoint answers 410 Gone. The browser reports it as a CORS error (Thesis 1, step 4). Same root cause as GUA-20261105-1.
   - Acceptance: a 200 with an "unavailable" summary and a warning.
   - Status: Fixed in `5f01681`: the route returns 200 with Data API v2 data (37 trades, 10 participants for the December 2026 market), and a failed request degrades to a warning.
5. **P2 — GUA-20261105-5: the contract page ignores a screener Refresh** and shows an 11-hour-old detail (24H volume 529,567 against 209,440 in the refreshed row; "Retrieved 3:13:36 AM" at 14:07) (Thesis 1, step 4).
   - Acceptance: the contract refreshes with the screener, or offers its own refresh, and the two agree.
   - Status: Open.
6. **P2 — GUA-20261105-6: the Meeting Ladder spreads the whole 2Y−Fed Funds gap over the next two meetings.** That gives +73 bp by January, against ≈ +25 bp in the contracts and +33 bp in the 3M bill (Thesis 1, steps 1 and 3). The text calls it a proxy, but the table reads as a meeting path.
   - Acceptance: spread the gap over the meetings inside the 2Y horizon, or anchor the near meetings to the 3M bill or futures.
   - Status: Open.
7. **P2 — GUA-20261105-7: Copilot's Sitrep context seems to omit the Rates table** (Thesis 1, step 9). Run 3 reported: "The user's 3M bill quote is not reproduced in the supplied SITREP summary or its available drilldown." The context payload itself was not inspected. Status: Open.
8. **P2 visual — GUA-20261105-8: the Commodities momentum/roll scatter stretched a 360×110 viewBox** (distorted labels, clipped y title; also on main). Status: Fixed in `499642c`.
9. **P2 visual — GUA-20261105-9: three Sitrep empty states were still in capitals.** Status: Fixed in `0697257`.
10. **P2 visual — GUA-20261105-10: Risk › Largest Movers toned flat rows (cash at 0 P&L) as gains.** Status: Fixed in `e70d6e4`. Still open (gamma-ui): Risk's simple tables tone whole rows, identifiers included, and the MC VaR and ES labels overlap in the terminal distribution.
11. **P2 — GUA-20261105-11: the Macro FX charts read "Loading FX data" for good** when the IBKR history comes back empty (checked at 20, 60 and 120 s without TWS). Status: Fixed in `d296f6f` ("FX history unavailable").
12. **P3 — GUA-20261105-12:**
    - One Options select (value "auto") has no accessible name.
    - Copilot threads from demo mode appear in the live session list. They carry the mock caveat, but a live follow-up continues the demo thread.
    - Status: Open.

### Gaps

- No meeting-dated policy curve (SOFR or fed funds futures), although IBKR carries them; this blocked Thesis 1's decisive test.
- Strategy Lab cannot use a FRED series as a leg or as a conditioning signal (Thesis 2).
- No regime split by policy events in Regime Stress, although Macro › Events / Regimes knows the FOMC dates.

### Cross-tab coherence

- **Carried:**
  - Strategy Lab → Risk: the research book arrived with its legs, windows and provenance.
  - Prediction Markets → Macro: the December contract's handoff targets "US macro events · events_regimes".
  - The Macro FX values agree with Sitrep's FX table.
- **Inconsistent:**
  - Macro's and Sitrep's policy read against Prediction Markets (GUA-20261105-2).
  - The screener row against the contract page (GUA-20261105-5).
  - Copilot's Sitrep summary against the Sitrep Rates table (GUA-20261105-7).

### Copilot evaluation

| Run | Contexts / prompt | Result |
| --- | --- | --- |
| 1 | Sitrep + Macro + Prediction Markets; the ladder-versus-contracts question | Hung at "Plan / Stop" for more than 300 s; backend thread died on the Polymarket 410 (GUA-20261105-1). No model call. |
| 2 | Sitrep + Commodities (Macro left out by the test driver) | Answered in 34 s. Correct arithmetic (+37+37 ≈ +73 bp; 4.21 − 3.88 = +33 bp); said plainly that the contract names could not be verified because Macro was not in scope; no hallucination. |
| 3 | Sitrep + Macro, same question | Answered in 44 s. Named the three linked contracts with their markets and dates and concluded "'Easier' is a mapping of this historical cut-contract set, not reliable current December–January easing pricing". It proposed the right missing data (a meeting-dated forward curve) and flagged that contract status is not in its context. |

## What Could Not Be Proven This Run

- **Options in session:** both blocks were outside US regular hours, as the user noted, so no LIVE surface or greeks were checked.
- **Not retested:** Operator runs (GUA-20261027-2 and -3); crack consistency across instrument selections (GUA-20261027-4); the gross-share basis on a near-neutral book in the UI (GUA-20261027-6); the Setup review; the Sealanes handoff.
- **Portfolio and the account's Risk:** not opened, by design, so no account data was captured; Fundamentals needs a SEC identity this worktree does not have.
- **Visual quality** beyond structure, colour and density in screenshots; keyboard navigation; and the packaged desktop app.

## Scoring

| Category | Score | Δ vs prior | Rationale (one sentence) |
| --- | ---: | :--: | --- |
| Data breadth | 7/10 | = | Same providers; the missing meeting-dated futures curve is the gap that mattered this run. |
| Data depth / drill-down | 7/10 | = | Event Book, book depth, per-leg windows and dated cracks are strong; the contract page serves an old detail after a refresh. |
| Analytical tooling (DCF, risk, scenarios, CSV) | 7/10 | = | A signed ETF book replayed over eight episodes in a minute; no conditioning on macro series or policy events. |
| Copilot usefulness | 6/10 | −1 | Grounded and honest when it runs, but it hung with Prediction Markets in scope (fixed afterwards in `5f01681`). |
| Cross-tab workflow / state continuity | 6/10 | −1 | Strategy Lab → Risk carries cleanly; Macro and Sitrep contradicted Prediction Markets on the policy path (fixed afterwards in `e94fe62`). |
| Visual density & design consistency | 8/10 | +1 | B′ holds in every Research tab in both themes; the four visual defects found were P2 and are fixed. |
| Speed to insight | 6/10 | = | Macro Rates & Policy loads within 15 s warm but was still loading after 33 s cold; a cold Sitrep was complete by 58 s. |
| Overall (gestalt, not an average) | 6/10 | −1 | The B′ surfaces read well and the research loop works, but two backend defects misled or stalled exactly the policy question this run asked. Scores are as observed during the run, before the same-day fixes. |

## Prioritized Follow-Up

**P1**
1. **GUA-20261105-1** — fail Copilot runs on any context-builder error and degrade the wallet summary. Status: Fixed (`5f01681`).
2. **GUA-20261105-2** — open, unexpired linked contracts only, with their status in the Copilot context. Status: Fixed (`e94fe62`) except the status in the Copilot context.
3. **GUA-20261105-3** — the Sitrep Prior column. Status: Fixed (`0697257`).

**P2**
4. **GUA-20261105-4** — wallet summary 410 → unavailable with a warning. Status: Fixed (`5f01681`, Data API v2).
5. **GUA-20261105-5** — contract detail refresh. Status: Open.
6. **GUA-20261105-6** — ladder methodology. Status: Open.
7. **GUA-20261105-7** — the Rates table in Copilot's Sitrep context. Status: Open.
8. **GUA-20261105-8 to -11** — visual and state fixes. Status: Fixed (`499642c`, `0697257`, `e70d6e4`, `d296f6f`). Open for gamma-ui: whole-row tones in Risk's simple tables; the overlapping MC VaR and ES labels.

**P3**
9. **GUA-20261105-12** — the unnamed Options select; demo threads in live mode. Status: Open.
