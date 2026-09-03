# Gamma Usability Findings — 2026-09-01

Date: 2026-09-01, Europe/Madrid (CEST, UTC+2)

Audience: Gamma product and engineering

Mode: degraded provider-backed

Runtime: audit-launched localhost frontend (`http://127.0.0.1:5173`) and backend (`http://127.0.0.1:8000`)

Commit / branch / dirty state: `6cc410368f94371a35ea698991babbf65882a293` / `main` / dirty before the audit. The pre-existing changes were `docs/copilot_v2_tab_plan.md` modified and `.agents/` untracked; both were preserved.

Data context: `MOCK_DATA=false`; Gamma reported `Live`; TWS was disconnected; portfolio history and all audit persistence were isolated under a temporary audit directory.

Scope: one AAPL research journey through SITREP, Equity Research, Fundamentals, Risk, and Copilot, including a focused restart/reproduction pass.

## Outcome

The provider-backed completion gate passed in degraded mode. Gamma supplied decisive yfinance history and SEC filing data, and the provisional thesis was **rejected**: AAPL's roughly `+2.5%` latest-day outperformance was real in the loaded public history, but the app's peer valuation, growth, DCF, reverse-valuation, and risk evidence did not corroborate durable company-specific strength over the next one to three months. The journey reached four analytical surfaces and two handoffs, but it did not complete a Copilot artifact. The highest-priority product results are a direct Equity Research → Risk handoff that drops the loaded SPY benchmark, visible run parameters that do not reconstruct the result being shown, contradictory Fundamentals fallback provenance/health, and a Copilot synthesis that failed twice without a usable partial answer.

## Environment And Provider Matrix

| Provider / subsystem | State | Freshness / mode | Used in verdict | Notes |
| --- | --- | --- | --- | --- |
| Gamma runtime | Worked with degradation | Live mode, audit-launched | Yes | Backend and frontend were reachable. TWS remained disconnected. |
| yfinance | Worked with degradation | Historical/live-ish; SITREP labeled equity and index data about 2 hours old | Yes | Supplied AAPL, SPY, index, and peer price context. Gamma correctly warned that it is an unofficial public source. |
| SEC / EdgarTools | Worked with degradation | Historical filings through 2026-07-31 | Yes | Loaded Apple profile, eight filings, normalized statements, and peers after a long transient false-unsupported state. Development identity fallback was disclosed. |
| Fundamentals price context | Worked with degradation | Latest price as of 2026-09-01 | Yes, cautiously | The visible source badge said `UNKNOWN / ibkr`, while the origin line said `yfinance.download`; TWS was disconnected. |
| IBKR / TWS | Blocked by provider or entitlement | Disconnected; market-data mode Auto | No | Settings nevertheless labeled the provider `Healthy` and counted unavailable price-context calls as successful. |
| FRED / Treasury / EIA fallback | Worked with degradation | Historical and release-lagged | Discovery only | SITREP loaded rates and commodity context. The Commodities provider was configured for IBKR but fell back while TWS was disconnected. |
| Polymarket / Kalshi | Worked | Open markets, `<1m` old in SITREP | No | Available for discovery but not relevant to the selected AAPL thesis. |
| RSS news | Worked with degradation | Delayed; about 2 hours old | No | Twenty headlines loaded; one ECB feed failed TLS certificate verification. |
| OpenAI Copilot | Blocked | `gpt-5.6-luna`, Auto/Standard route | No | First run ended `incomplete` at `max_output_tokens`; Retry ended in a provider error. Settings showed 2 calls, 0 successes, and `DEGRADED`. |
| Sample/news fallback | Unsupported by design | Disabled in live mode | No | Gamma did not silently load sample news while `MOCK_DATA=false`. |

## Research Question And Provisional Thesis

- Question: Does AAPL's latest-day outperformance reflect company-specific strength that is independently supported by peer-relative performance and fundamentals?
- Provisional thesis: AAPL's `+2.6%` SITREP move against a falling S&P 500 (`-0.7%`) and Nasdaq (`-1.0%`) is a durable company-specific signal over a one-to-three-month horizon.
- Horizon: 1–3 months.
- Initial signal: provider-backed SITREP equity/index history dated 2026-09-01, with AAPL the clear positive megacap outlier.
- Expected confirmation: AAPL should show persistent relative strength, a defensible peer valuation/growth profile, and risk-adjusted behavior that survives a benchmark-aware handoff.
- Falsifier / kill condition: absence of independent peer/fundamental support, reverse-valuation assumptions outside plausible bounds, or loss of benchmark context that prevents relative-risk confirmation.
- Hypothetical expression, if any: none. This was research-only and no trade was proposed.

## Journey

| # | Surface and action | Evidence / visible provenance | Result | Classification |
| ---: | --- | --- | --- | --- |
| 1 | Run the safe preflight and launch an isolated live-mode stack | Commit, branch, dirty state, `MOCK_DATA=false`, isolated history | Runtime reached both documented localhost addresses | Worked |
| 2 | Inspect Settings before research | Live mode; TWS disconnected; Copilot configured; zero initial provider calls | Honest high-level mode and broker boundary | Worked with degradation |
| 3 | Open SITREP and wait for provider-backed discovery | yfinance, FRED/Treasury, EIA/FRED fallback, Polymarket/Kalshi, RSS | Populated after about 56 seconds; the page remained globally blank/loading until the aggregate completed | Worked with degradation |
| 4 | Select AAPL from the SITREP tape | AAPL `+2.6%`, S&P 500 `-0.7%`, Nasdaq `-1.0%`, dated Sep 1 | Handoff preserved AAPL and opened Equity Research / Scope | Worked |
| 5 | Inspect Equity Research AAPL scope and switch chart horizon to 3M / Relative | yfinance, 456 observations in the SITREP-seeded run, SPY benchmark | Entity and chart controls worked; cards remained pinned to the underlying run | Worked with degradation |
| 6 | Open Equity Research / Comparables | Only one comparable object, `Scope: AAPL`; Run Compare disabled | The loaded SPY benchmark and peer basket were not available as comparison objects | Blocked by product defect |
| 7 | Continue AAPL into Fundamentals | SEC, yfinance fallback, Gamma-derived analytics | Valid AAPL data eventually loaded, but for more than 30 seconds the UI said AAPL had no matching SEC profile and disabled search/actions | Worked with degradation |
| 8 | Inspect Fundamentals overview and Reverse Valuation | Eight SEC filings; price `324.81`; peer heatmap; Gamma DCF/reverse solve | Produced strong contrary evidence and explicit bounded-solve warnings | Worked |
| 9 | Continue AAPL into Risk | Research scope, 100% AAPL, 318/456 AAPL observations depending on run | Absolute risk loaded, but SPY overlap became 0 and beta/correlation became N/A | Worked with degradation |
| 10 | Recompute Risk once | Visible SPY benchmark field, same research scope | Benchmark overlap remained 0; the direct Equity Research → Risk restart retest reproduced it | Blocked by product defect |
| 11 | Ask dedicated Copilot to synthesize SITREP + Equity Research + Fundamentals + Risk | 16 sources / 21 warnings, OpenAI `gpt-5.6-luna` | Typed `incomplete`: `max_output_tokens`; no answer or artifact | Blocked by product defect |
| 12 | Retry the persisted Copilot turn once | 17 sources / 1 tool / 22 warnings; diagnostic `cp6.provider_error.e87c9aa009f4` | Typed provider error; no answer or artifact | Blocked by provider or entitlement |
| 13 | Restart the isolated stack and repeat direct Equity Research → Risk | Fresh 252D AAPL run: 318 SPY-overlap observations, beta `0.748` | Risk again showed SPY overlap 0, confirming the handoff defect rather than the indirect route | Worked |

## Thesis Verdict

- Verdict: rejected.
- Thesis confidence: moderate, approximately 0.72 confidence in rejection.
- Data-quality confidence: medium-low, approximately 0.58, because the decisive yfinance/SEC data loaded but run-state, provenance, and handoff defects constrain interpretation.
- Supporting evidence: AAPL rose about `2.5%` on Sep 1 while major U.S. indexes fell; the fresh direct scope showed strong trailing return, `24.3%` annualized volatility, `-13.8%` max drawdown, 104% ROIC, 32% EBIT margin, and 88.2% cash conversion.
- Contrary evidence: AAPL traded at `43.51x` P/E and `11.82x` EV/Sales, above every displayed peer on those measures; revenue growth was `6.4%`, FCF growth `-9.2%`, and FCF yield `2.0%`. The Base DCF was `141.81` per share (`-56.3%` versus market), the Bull DCF was `223.44` (`-31.2%`), and reverse valuation required `32.3%` revenue CAGR or bounded assumptions such as 65% terminal EBIT margin and 35% FCF CAGR.
- Falsifier status: met. Independent fundamentals and reverse valuation did not support the one-day relative-strength interpretation, and the benchmark-aware Risk confirmation was unavailable because the handoff dropped SPY history.
- Research-only expression or decision implication: do not promote the one-day move into a durable thesis from this run. Revisit only after identifying an app-native catalyst, restoring benchmark continuity, and re-running with an inspectable effective window.

## What Worked

- Live mode did not silently replace unavailable news or broker data with sample data.
- SITREP eventually combined provider-backed equity, rates, commodity, prediction-market, and RSS context with visible freshness and warning labels.
- SITREP → Equity Research preserved the AAPL entity and landed in Scope.
- Fundamentals loaded a rich Apple workspace with filings, statements, peers, DCF scenarios, reverse valuation, explicit model warnings, and read-only continuation actions.
- Risk preserved the AAPL symbol, 100% research weight, return history, volatility, drawdown, concentration flags, and read-only provenance notes.
- Copilot persisted both non-success turns, their source/warning counts, routing, usage, and safe diagnostic across restart.
- No trading, order, account, wallet, or rebalance action was exposed or taken.

## Findings

### P1 — GUA-20260901-1: Equity Research → Risk drops a loaded benchmark

- Journey impact: Gamma could not test whether AAPL's outperformance survived benchmark-aware risk analysis.
- Expected: `Open In Risk` should preserve or reproducibly reload the active SPY benchmark, effective window, source, and warnings.
- Observed: the fresh direct Equity Research run showed 318 SPY-overlap observations, beta `0.748`, and correlation `0.375`. Risk preserved AAPL and 318 observations but reported SPY overlap `0`, beta/correlation N/A, and `Benchmark history unavailable for SPY`. Recompute did not recover it.
- Evidence: direct reproduction after restart on the same audit stack; the earlier 456-observation route failed identically.
- Reproduction: Equity Research → Scope → AAPL / SPY / 252D → Run Analysis → verify positive benchmark overlap → Open In Risk → inspect Provenance / Coverage → Compute Core once.
- Classification: product defect.
- Acceptance criteria: handoff carries the exact benchmark series or enough immutable provider/window identity for Risk to reload it; Risk overlap and beta/correlation match the source run within documented methodology differences; direct and restart tests cover the contract.

### P1 — GUA-20260901-2: Visible `252D` state does not identify the analysis being shown

- Journey impact: the user cannot reproduce or compare the AAPL result and therefore cannot know which return/risk evidence underlies the thesis.
- Expected: cards, builder state, handoff metadata, and the result payload should agree on requested and effective lookback, start/end dates, observation count, and data vintage.
- Observed: the SITREP-seeded run visibly showed `252D` but reported 456 observations, 47.53% return, 29.49% volatility, `-33.36%` drawdown, and beta `1.076`. A fresh direct `252D` run after restart reported 318 observations, 63.00% return, 24.32% volatility, `-13.80%` drawdown, and beta `0.748`. Gamma exposed no effective-window identity that explained the difference.
- Evidence: two visible AAPL scope runs on the same date and isolated audit data directory.
- Reproduction: select AAPL from SITREP and record the Scope cards/builder; restart; open Equity Research / Scope, leave AAPL, SPY, and 252D selected, run analysis, and compare.
- Classification: product defect.
- Acceptance criteria: persist and render immutable requested/effective window metadata with every result; hydrate controls from the actual run; disclose provider revision/cache changes; make an identical rerun stable or visibly explain why it changed.

### P1 — GUA-20260901-3: Fundamentals fallback provenance and provider health contradict each other

- Journey impact: valuation multiples and reverse-valuation inputs are decisive, but the user cannot tell which price provider actually supplied them or whether the broker path succeeded.
- Expected: when TWS is disconnected and yfinance supplies fallback price history, the source badge, origin, transformation note, provider-usage status, and provider health should consistently say so.
- Observed: Fundamentals showed `UNKNOWN / ibkr` for Price Context while its origin line said `yfinance.download`; Derived Analytics said it used the current IBKR price context. Settings labeled IBKR / TWS `Healthy`, counted visible IBKR calls as successful, and simultaneously said `Market data unavailable: not connected`.
- Evidence: Fundamentals Overview provenance panel and Settings provider usage/health during the same run.
- Reproduction: start live mode without TWS, load AAPL Fundamentals, inspect Price Context and Derived Analytics provenance, then open Settings.
- Classification: product defect.
- Acceptance criteria: fallback provider identity is authoritative end to end; unavailable broker attempts are not counted as successful provider data; health becomes unavailable/degraded rather than Healthy; derived analytics enumerate the actual price source.

### P1 — GUA-20260901-4: Four-context Copilot synthesis produces no usable terminal result

- Journey impact: the required terminal synthesis/memo step could not complete despite loaded provider-backed evidence.
- Expected: Copilot should compact a four-context request into a bounded card, or at minimum render a useful partial answer with a clear continuation path.
- Observed: the first run ended `incomplete` at `max_output_tokens` with 16 sources and 21 warnings but no answer. Retry used one tool and ended in a provider error with 17 sources and 22 warnings. No artifact was created.
- Evidence: persisted Copilot transcript, run inspector, diagnostic `cp6.provider_error.e87c9aa009f4`, and Settings showing 2 calls / 0 success / DEGRADED.
- Reproduction: select SITREP, Equity Research, Fundamentals, and Risk; ask Agent for a concise thesis verdict that preserves warnings; Send; Retry once.
- Classification: product defect, with a provider failure on the bounded retry.
- Acceptance criteria: context compaction and output budget permit a terminal card for this representative request; an output-limit terminal preserves usable partial content; Retry is idempotent and can complete from the persisted turn; failure never leaves only metadata and no research answer.

### P2 — GUA-20260901-5: Fundamentals transiently labels a supported AAPL handoff as unsupported

- Journey impact: a user can abandon a valid U.S.-filer workflow before the provider request completes.
- Expected: loading should remain a loading/degraded state until company resolution has actually failed.
- Observed: for more than 30 seconds, the AAPL handoff showed `AAPL has no matching SEC company profile`, `No CIK`, zero filings, disabled search/actions, and `Refreshing`. It later resolved Apple successfully without user intervention.
- Evidence: sequential visible-state checks at approximately 10 and 30 seconds, followed by a successful Apple profile.
- Reproduction: start a cold live-mode backend, carry AAPL into Fundamentals, and observe the status before the workspace request completes.
- Classification: usability friction and product defect.
- Acceptance criteria: pending, unsupported, provider-failed, and successful states are mutually exclusive; valid stale content is retained where available; controls expose cancel/retry after a bounded wait.

### P2 — GUA-20260901-6: Comparables cannot compare the active equity to its loaded benchmark or peers

- Journey impact: the intended peer-relative confirmation branch ended before analysis.
- Expected: `Peer And Benchmark Comparison` should expose the active SPY benchmark and/or the loaded peer basket as comparison objects.
- Observed: only `Scope: AAPL` was available for both sides; Run Compare was disabled even though the Scope view had a loaded SPY benchmark and Fundamentals later exposed five peers.
- Evidence: Equity Research / Comparables immediately after the successful AAPL scope.
- Reproduction: load AAPL with benchmark SPY, open Comparables, inspect Left/Right options.
- Classification: usability friction.
- Acceptance criteria: active benchmark and eligible peer/basket streams are first-class comparison choices, or the mode clearly explains the exact save/compose step required and offers it inline.

### P2 — GUA-20260901-7: SITREP blocks progressive insight behind a roughly 56-second aggregate load

- Journey impact: discovery began with empty tables and no usable partial data despite individual provider calls succeeding.
- Expected: independently completed sections should render with per-section loading/degraded states while slower sections continue.
- Observed: SITREP remained globally `LOADING`, `OFFLINE`, and `NOT LOADED` for about 56 seconds, then populated all sections at once. Settings already showed successful yfinance, macro, prediction-market, and RSS calls during the blank interval.
- Evidence: visible snapshots after approximately 6, 26, and 56 seconds plus Settings provider usage.
- Reproduction: cold-start live mode without TWS and open SITREP.
- Classification: usability friction.
- Acceptance criteria: stream or progressively commit independent section results; identify the slow section; keep Refresh/cancel/retry behavior section-scoped; time-to-first-usable public-provider panel stays within the beta target.

### P2 — GUA-20260901-8: News entity tags attach AAPL to unrelated headlines

- Journey impact: false entity links can create spurious company catalysts and contaminate handoffs or Copilot grounding.
- Expected: ticker chips should require high-confidence headline/snippet evidence for the company.
- Observed: AAPL chips appeared on an unrelated U.S. measles-deaths headline and a generic global bond-rout video.
- Evidence: SITREP Market News visible rows at 17:48 and 16:53.
- Reproduction: load the 2026-09-01 SITREP news feed and inspect entity chips on those rows.
- Classification: data correctness / usability friction.
- Acceptance criteria: false-positive fixtures are added; ambiguous common-token matching is rejected; item-level context exposes why a tag was assigned; low-confidence tags are withheld or visibly qualified.

## Cross-Tab And State Continuity

- SITREP → Equity Research: entity continuity worked. AAPL opened directly in Scope and the global equity-focus chip persisted.
- Equity Research → Fundamentals: entity focus persisted, but a pending request was temporarily rendered as unsupported.
- Equity Research → Risk: AAPL, weight, base currency, and return history persisted; SPY benchmark history and relative-risk outputs did not.
- Restart: the isolated Copilot conversation, two non-success turns, source/warning counts, and diagnostic replayed. Loaded tab contexts correctly required reloading after restart.
- No durable peer basket, DCF change, saved research object, order, or account state was created.

## Copilot Evaluation

- Grounding: four selected contexts were visible and the transcript retained 16–17 sources and 21–22 warnings.
- Tool/context scope: the retry recorded one tool call; no unauthorized or trading tool was exposed.
- Provider delivery: failed. The first terminal was `incomplete` because of `max_output_tokens`; the retry was a provider error.
- Transcript rendering: non-success states, model/provider, evidence counts, warnings, routing, usage, and safe diagnostics rendered and replayed correctly.
- Persistence: both turns survived backend restart in the isolated audit store.
- Memo/export: not exercised because no successful assistant result or artifact existed.

## Unsupported And Unverified Boundaries

- Live TWS, Portfolio, Options/IV, and broker-entitled market data were not exercised because TWS was disconnected.
- No DCF scenario was changed or saved; only existing read-only scenarios and reverse valuation were inspected.
- Prediction Markets, Crypto, Commodities drilldowns, Sealanes, Strategy Lab, and Script execution were not part of the selected thesis route.
- The Bloomberg external stream was not evaluated beyond its visible external/live status.
- No direct API result was substituted for a blocked UI step.

## Scorecard

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | 8/10 | Public equities, filings, macro, commodities, news, and prediction markets were available without TWS. |
| Data depth and drill-down | 7/10 | Fundamentals and Risk were deep; Equity Comparables could not use the active benchmark/peers. |
| Data trust and provenance | 4/10 | Useful warnings existed, but price-source, provider-health, run-window, and benchmark-continuity contradictions were material. |
| Analytical tooling | 7/10 | Scope, peer heatmap, DCF, reverse valuation, and absolute Risk were useful and read-only. |
| Cross-tab continuity | 4/10 | Entity continuity was good; benchmark continuity failed on a central handoff. |
| Recovery and state resilience | 5/10 | Copilot replayed across restart, but Fundamentals misclassified pending data and Copilot could not recover. |
| Agent drivability | 6/10 | Most controls were semantically reachable; some visible select labels were not programmatically associated and Comparables had no actionable path. |
| Speed to insight | 4/10 | SITREP took about 56 seconds and cold Fundamentals more than 30 seconds before becoming useful. |
| Overall | 5.6/10 | Gamma can support a real provider-backed research verdict, but trust and continuity defects prevent a clean end-to-end job. |

## Cleanup And Residual State

- The audit-created browser tabs were closed.
- Both audit-launched backend/frontend sessions were stopped; ports 8000 and 5173 had no remaining listeners.
- No IV collection, TWS client, order, account, portfolio, wallet, provider configuration, base currency, or product code was changed.
- The audit-created Copilot session and provider caches were isolated from the normal Gamma data directory.
- Residual audit data remains at `C:\Users\User\AppData\Local\Temp\gamma-usability-a5f2f3018983435d8429dfbd909a1f3c`. It contains only the isolated audit persistence tree, including the `AUDIT 2026-09-01` Copilot session. A validated recursive deletion was refused by the local command safety policy, so the directory was left in place rather than bypassing the guard.
- Repository writes are limited to this report and its one-line usability index entry. Pre-existing working-tree changes were preserved.

## Audit-Only Follow-Up

1. Fix GUA-20260901-1 first: a cross-tab handoff that silently discards the benchmark invalidates relative-risk research.
2. Fix GUA-20260901-2 and GUA-20260901-3 together as a trust pass: immutable effective-window metadata and truthful fallback provenance must make each number reproducible.
3. Fix GUA-20260901-4 before claiming a successful multi-context terminal job: the representative synthesis must yield a bounded answer or useful partial.
4. Harden pending-state semantics and progressive loading (GUA-20260901-5 and -7) for beta usability.
5. Make the advertised peer/benchmark comparison path actionable and tighten news entity tagging (GUA-20260901-6 and -8).

This was an audit-only run. No finding was remediated or marked fixed.
