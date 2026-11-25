# Ideas Persona Audits (I6) — 2026-11-24

Date: 2026-11-24
Audience: future AI agents and contributors closing Workstream 12 (Ideas)
Mode: fixed-task persona audits (the I6 acceptance in [`idea_workspace_spec.md`](../idea_workspace_spec.md#checkpoints)), scored like the usability audit
Data: live providers; the quant audit also had TWS (IBKR client id 17, read-only, market-data mode `auto`)
Context: the last Workstream 12 checkpoint. It ran on branch `claude/ideas-closeout` (cut from `main` at 2de1b1c) after the weekday I3d re-check and with its fixes. The I5 live Copilot runs made during the retail audit are recorded in the spec's [I5 live acceptance](../idea_workspace_spec.md#i5-live-acceptance-2026-11-24).

## Verdict

| Audit | Open P0 | Open P1 | Cross-tab workflow | Speed to insight | Acceptance |
| --- | ---: | ---: | ---: | ---: | --- |
| Retail, no TWS | 0 | 0 | 8 | 8 | **Met** after the fixes on this branch (one P0 found and fixed) |
| Quant, live data | 1 | 0 | 8 | 7 | **Not met**: Script runs on the configured runtime never completed (GUA-20261124-10), so the Script signal and walk-forward tasks could not be done |

## Audit Setup

- Worktree `.claude/worktrees/ideas-closeout`, its own `data/` and `cache/` (and `data_8011/`, `cache_8011/` for the retail backend); the main checkout's data and the desktop backend on port 8000 were not touched.
- Retail backend: port 8011, `IB_PORT=1` so it can never reach TWS, root `.env` provider keys and SEC identity passed as process environment. Vite on 5173.
- Quant backend: port 8010, IBKR client id 17, connected read-only to TWS. Vite on 5174.
- Browser: the in-app browser pane at 1440×900 for the walk-through; headless Playwright (Chromium, DPR 1) for timing and theme/width checks.
- Copilot: the configured default model (`gpt-6.1-sol`, OpenAI Responses, profile `auto`). Five of the six allowed live runs were used.
- Script: the configured runtime (`openai_code_interpreter_v1`, same model). The owner approved one new run plus a three-point sweep; two executions were made (see GUA-20261124-10).

## Retail audit (no TWS)

Thesis: "NVDA outperforms QQQ over the next four weeks because the 24 November drop priced governance headlines more than earnings risk."

Signal that sparked it (captured before the thesis): Sitrep at 20:40 UTC showed NVDA −7.6% on the day, Nasdaq Composite −2.0% and the Dow +0.6%, with headlines about political pressure on Nvidia's board.

| # | Task | Tab | Result |
| --- | --- | --- | --- |
| R1 | Capture a thesis and pin evidence from four tabs | Equity Research, Fundamentals, Sitrep, Prediction Markets | Worked. The first pin created the idea from the pin dialog ("New idea…"). Pins: NVDA scope vs QQQ (supports: −7.49% day, −15.90% over 252D, beta 1.59); NVDA price and valuation (challenges: 28.4× EV/EBIT, Gamma's DCF base case $67 against $152.70); Sitrep worldwide indices (context); "DOJ criminally charges NVIDIA by December 31?" (challenges). Macro and Crypto have no pin (GUA-20261124-5). |
| R2 | Plain criteria with an invalidation rule | Ideas | Worked. NVDA close below 140 (invalidate), NVDA close above 165 (confirm), DOJ contract above 50% (invalidate), review date. The form prefilled the ticker and the pinned contract and titled the rule after the contract. "Check now" read the last final close (165.05 on 11-23), not the in-progress bar. Typing the outcome "Yes" left the prediction rule unavailable (GUA-20261124-2, fixed). |
| R3 | Run test and risk; read them in plain language | Ideas | Worked. Backtest 2023-11-20 → 2026-11-24, 756 observations: +51.57% total, −19.67% max drawdown, SPY +63.75%, labelled "In-sample only", "No costs", "Trials 1". Risk: 95% one-day historical VaR −1.66%, ES −2.43%, worst replayed episode Q4 2018 −15.14%, all eight episodes fully covered. The journal restates both in one sentence each. |
| R4 | Activate; read the hypothetical tracking and its costs | Ideas | Worked. Activated 20:47:57 UTC; "Waiting for the first close after 2026-11-24 20:47 UTC". After the close settled (21:20 UTC) the first session entered at NVDA 155.38 / QQQ 638.10, net −0.10% from 5 bp per side on each leg. |
| R5 | Promote a Sitrep follow-up; use the notification center | Sitrep, Ideas | Worked. Starring "ADI −16.6%" made a follow-up; "◇ Promote to idea" opened a draft with the Sitrep origin (no leg carried, GUA-20261124-7). A review-date criterion triggered at once; the top-bar notification center showed "1 triggered · 0 reviews due" with Acknowledge. |
| R6 | Copilot: review, then draft | Ideas (Copilot shelf) | Worked for the user (runs 1 and 2 of the I5 acceptance). The review caught a flaw in my own thesis (a QQQ beta compared with a Nasdaq Composite move), the unavailable governance rule and the 34.1% vs 11.5% contract discrepancy. The draft proposed a relative-return idea with three criteria; "Create draft idea" created it as a draft. |
| R7 | Close with a review; read Review mode | Ideas | Worked. Closed as Abandoned (superseded by the Copilot draft) with a lesson and per-pin verdicts. Review mode: 1 reviewed, median holding under a day, median net −0.10%, "Invalidation before a loss 0 of 1". |

### Retail findings

| ID | Severity | Status | Finding | Steps and evidence |
| --- | --- | --- | --- | --- |
| GUA-20261124-1 | P0 | Fixed on this branch | Polymarket's headline probability was the last trade even when it sat far outside the order book. "DOJ criminally charges NVIDIA by December 31?" showed **34.1%** while the book was 0.09 / 0.139 (midpoint 11.45%) and the outcome ladder said 11.5% ("now at 100.0% of range"). The pin captured 34.1%, and a `prediction_probability` rule without an outcome would have been evaluated against it. | R1 step 4. `GET /prediction-markets/markets/polymarket:6994526`: `current_probability` 0.341, `best_bid` 0.09, `best_ask` 0.139. Polymarket's own rule ([help.polymarket.com, "How are prices calculated?"](https://help.polymarket.com/en/articles/13364488-how-are-prices-calculated), checked 2026-11-24): the midpoint of the spread, or the last trade when the spread is wider than $0.10. Fix: `_polymarket_probability_proxy` applies that rule; regression test `test_polymarket_probability_follows_the_venue_display_rule`. After the fix the same contract reads 0.1145 and the rule shows "11.5%, Holding". The pin taken before the fix keeps its frozen 34.1% by design. |
| GUA-20261124-2 | P2 | Fixed on this branch | The criterion's "Outcome" field accepted only an internal outcome id (`6994526:0`); typing "Yes" made the rule unavailable ("Outcome Yes is not on polymarket:6994526"). | R2. Fix: the reader matches the outcome by id or by label and lists the outcomes when neither matches; regression test `test_a_prediction_outcome_is_found_by_its_label`. |
| GUA-20261124-3 | P2 | Open | Fundamentals on a cold backend says "NVDA has no matching SEC company profile" for about 20 seconds while the overview is still loading, then loads NVIDIA normally. | R1 step 2. The notice condition (`focusedTickerNotice`) does not wait for the overview request. Acceptance: no "no matching profile" text while the search result contains the ticker or the overview is loading. |
| GUA-20261124-4 | P2 | Open | The Fundamentals "Price and valuation" pin is labelled "Unknown · ibkr" on a backend that has never connected to TWS. | R1 step 2. Acceptance: the pin names the provider that actually priced it. |
| GUA-20261124-5 | P2 | Open | Macro and Crypto panels have no "Pin to idea"; a retail user can pin rates only through Sitrep's Rates panel. | R1. `PinToIdea` is imported by Sitrep, Prediction Markets, Options, Fundamentals, Equity Research and Commodities only. |
| GUA-20261124-6 | P2 | Open | Ideas mixes clocks: "Updated", "Captured", "Last pin" and the segment "Activated" are local time without a zone, next to UTC-labelled text in the same panel ("Waiting for the first close after 2026-11-24 20:47 UTC" beside "Activated 2026-11-24 21:47"). | R4. Acceptance: one convention with a visible zone. |
| GUA-20261124-7 | P2 | Open | Promoting a Sitrep follow-up does not carry its instrument: "ADI −16.6%" became a draft with no leg and no pinned evidence. | R5. Acceptance: an equity follow-up becomes a leg (and the row a context pin). |
| GUA-20261124-8 | P2 | Open | A test snapshot taken during the session includes the in-progress daily bar (window "→ 2026-11-24" at 20:47 UTC). The same bar is now excluded from criteria (see the spec's live check), not yet from Run test. | R3. Acceptance: snapshots end at the latest final close, as tracking does. |
| GUA-20261124-9 | P2 | Open | Copilot polish: the Research Operator resolves "Review this idea" as an SEC entity search (it offered IACO, IACOU, IDTL "Idea" issuers); the energy draft's leg is shown with the model's free-text label ("Proposed oil ETF proxy; verify tracking…") instead of its ticker. | R6 and the I5 runs 4 and 5. The Operator limitation was already listed under I5 "Left for later". |
| — | Nits | Open | "Added a invalidate criterion" in the journal; "at Today (gamma_clock)" in a review trigger entry; the notification kind tag truncates to "Re…"; the close form said "No priced sessions yet" while the record already had its first session; the follow-up row's actions are icon-only (✎ ◇ ✓ ✕). | R2, R5, R7. |

## Quant audit (live data, TWS)

| # | Task | Result |
| --- | --- | --- |
| Q1 | Attach a Script signal from existing runs and sweeps | **Blocked.** The worktree had no runs; the owner approved one new run plus a three-point sweep. Script "AAPL/MSFT relative momentum (quant audit)", user-authored, inputs exported from Equity history (AAPL and MSFT, 1,031 daily closes each, preview then export). Both executions (`dfbc695d…` single run, `7d3934ee…` sweep point 0) ended **incomplete** with `executed_code: false`: "The provider did not return one verbatim execution wrapper; exact-source association was not established." The remaining two sweep points were not run. The Ideas signal picker listed both runs as "incomplete"; `POST /ideas/{id}/signal` refused them ("ended incomplete; attach a completed run"). Gamma also refused the first source revision for an absolute path (`/mnt/data`), as designed. |
| Q2 | Walk-forward validation; trial count everywhere | Walk-forward **blocked** by Q1. Trial counts were consistent where they can be: the idea header, the test snapshot and the tracking panel read "Trials 2" after a CSV signal and a Strategy Lab backtest; the signal card reads the count at attach time ("Trials 1"); the journal says "2 trials". |
| Q3 | Import CSV weights and positions; attach from Strategy Lab and from Risk | Worked. CSV weights on the AAPL/MSFT pair (AAPL 30%, MSFT −70%, "Cash at 0% +140%"), CSV positions on the six-name basket (shares valued at the 11-23 final closes, weight of gross per leg, 5 bp per side). Strategy Lab composer → "Attach to idea" stored a backtest snapshot (source Strategy Lab); the same book carried into Risk → "Attach to idea" stored a risk snapshot (95% VaR −0.84%, worst episode 2022 rate shock −10.77%). |
| Q4 | Python client from a separate process | Worked. `gamma_client` read 85 AAPL and MSFT closes ending at the last final close (11-23) with provenance, computed 20-day relative-momentum weights in pandas and attached them as a weights signal (`trial_count` 1, "No out-of-sample validation"); the idea's legs followed the book. A call outside the allowlist (`POST /system/connection`) raised `RouteNotAllowedError` before anything was sent. |
| Q5 | Rebalancing and per-leg costs on the tracking record | Per-leg costs visible (5 bp per side per leg; exit cost marked to liquidation). The rebalancing cost could not be read live: the signal changes were attached after the 16:00 New York close, so the old book exits and the new one enters at the 11-25 close. The journal already states "paying the per-side cost on each instrument's turnover"; the figure is covered by the I4a tests. |

### Quant findings

| ID | Severity | Status | Finding | Steps and evidence |
| --- | --- | --- | --- | --- |
| GUA-20261124-10 | P0 | Open (follow-up) | Script runs on the configured runtime (`openai_code_interpreter_v1` with `gpt-6.1-sol`) never complete: the model does not execute Gamma's wrapper verbatim, so Gamma withholds the outputs. This blocks Script signals and walk-forward end to end. Gamma's gate behaves correctly; the runtime/model pairing does not. | Q1. Two of two executions incomplete, 40 s and 29 s, `executed_code: false`, output `output-source-association-error`. Acceptance: a completed run of an accepted revision whose analytics validate, then a sweep, walk-forward and an Ideas attach. Needs a runtime investigation and further runs, which spend credit, so it waits for the owner. **2026-11-25: diagnosed on `claude/script-runtime-completion` and still open.** One owner-approved live rerun also ended `incomplete` (`multiple_code_calls`). The only call that ran was `os.listdir('/mnt/data')`. The model's second call was a verbatim copy of the wrapper, but `max_tool_calls=1` kept it from running. So the copy is exact; the problem is an inspection call made before it. The gate stays strict. The branch adds a per-call diagnosis and transport prompt `exact_copy_v3` (wrapper first and only). A second approved rerun with v3 also ended `incomplete`: its single call was again `os.listdir('/mnt/data')`, so a prompt cannot fix this. Recommended next step, waiting for the owner: pin `gpt-5.6-luna` for Script runs. Details: the Script plan, "Script runtime completion (GUA-20261124-10)". |
| GUA-20261124-11 | P2 | Open | The Script run picker in the signal form offers incomplete runs; attaching one fails only when submitted. | Q1. Acceptance: incomplete runs are shown disabled with their reason. |
| GUA-20261124-12 | P2 | Open | A Strategy Lab snapshot of a different book reads "Stale" the moment it is attached; the signal card's "Trials 1" is the count at attach while the idea reads "Trials 2". Both are right by design but read as errors. | Q2, Q3. Acceptance: "Different book" and "Trials 1 at attach". |
| GUA-20261124-13 | P2 | Open | Intraday strip after the close: the "Prior close" column showed the same day's provisional close between 16:00 and 16:20 New York time; after a mid-session segment change the leading gap disappeared; the cadence note on a frozen mark says "Gamma marks only the legs of tracked ideas" although the leg is tracked and the mark is frozen. | Weekday I3d check, pair idea. |

## Defects found by the weekday I3d check (fixed on this branch)

Recorded in the spec's [Live check, 2026-11-24](../idea_workspace_spec.md#live-check-2026-11-24-weekday); listed here because the quant audit relies on the intraday layer.

- IBKR marks repeated the previous pass's prices (ib_insync's cached `Ticker`), so every mark after the first lagged one pass (P0, fixed).
- Equity close rules triggered from Yahoo's in-progress daily bar instead of a close or a mark (P0, fixed).
- A short TWS disconnection (one missed pass) left no gap and the chart line joined across it (P1, fixed).
- The strip stopped refreshing after a disconnection and never showed the reconnection (P2, fixed).

## What Could Not Be Proven This Run

- The Script path (Q1, Q2): blocked by GUA-20261124-10.
- The rebalancing cost figure: due at the 11-25 close.
- Five trading days of wall-clock tracking with no TWS (the I3 acceptance): needs an idea activated now and read after the fifth close; the worktree data is deleted after this run.
- Visual quality beyond structure: the fixes' only UI change is the strip's polling; it was captured in light and dark at 1440, 1000 and 390 px with no page overflow and no console errors.

## Scoring

| Category | Retail | Quant | Rationale (one sentence) |
| --- | ---: | ---: | --- |
| Data breadth | 8 | 8 | Equities, SEC fundamentals, prediction markets, commodities and IBKR marks all fed the ideas; FX needs TWS. |
| Data depth / drill-down | 7 | 8 | Pins reopen their source; the contract page exposed the book that contradicted its own headline. |
| Analytical tooling | 8 | 6 | Test, risk, stress replay and costs work from any tab; Script signals and walk-forward were blocked. |
| Copilot usefulness | 8 | n/a | The review found a real flaw in the thesis and the draft was valid; the Operator cannot review ideas yet. |
| Cross-tab workflow / state continuity | 8 | 8 | Pin-to-idea from four tabs, criteria prefilled from pins, attach from Strategy Lab, Risk, CSV and the client; Macro and Crypto cannot pin. |
| Visual density & design consistency | 8 | 8 | B′ panels throughout; mixed local/UTC clocks are the main inconsistency. |
| Speed to insight | 8 | 7 | Signal to active, tested idea in under ten minutes; the quant could not reach a validated signal. |
| Overall | 8 | 7 | Retail closes the loop; the quant loop waits on the Script runtime. |

## Prioritized Follow-Up

- **P0** GUA-20261124-10: make the Script runtime complete on the configured model (or pin a model that executes the wrapper verbatim), then rerun the quant Script tasks. Open.
- **P2** GUA-20261124-3 to -9, -11 to -13 and the nits above. Open.
