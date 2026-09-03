# Gamma Usability Findings — 2026-09-03 (Fix Verification)

Date: 2026-09-03, Europe/Madrid (CEST)
Audience: Gamma product and engineering
Mode: IBKR-integrated live fix verification
IBKR state: connected live during the journey; Gamma disconnected during cleanup
Runtime: audit-launched frontend and backend; pre-existing TWS session
Commit / branch / dirty state: `7a897be76470f64115bedcf45f6a7f01e0a6c3e1` on `main`; clean at start
Fix commit under test: `702d1cf97196af791f9b1e544cb70fb127a2d5c3`
Data context: regular US session; Gamma market-data mode `Auto`; live IBKR account, quote, risk, and option-chain data; yfinance daily history; isolated local portfolio-history directory
Scope: Audit-only verification of the five 2026-09-03 findings, replay of the GOOGL concentration/downside-protection thesis, a public AAPL Copilot probe, and a Strategy Lab coverage mission. No order, trade, rebalance, save, account mutation, or implementation change was attempted.

## Outcome

Four of the five prior acceptance criteria passed with live evidence. The fitted selected-expiry IV, account-aware strategy sizing, Risk analysis identity, and degraded-provider health semantics all behaved as intended. The Copilot fix did not pass: the locally visible selected-expiry and realized-versus-implied state was correct, but navigating from Options to Copilot destroyed the Options view and cleared the shared workbench store before the later Copilot submission. The persisted run therefore exposed surface/session evidence but no `Options strategy workbench` source, and both bounded public-context provider attempts terminated after a tool call with a typed error.

The GOOGL research thesis remains **partially confirmed**. Live Risk still showed a materially concentrated risk contribution, and the corrected 78-day IV/RV comparison supports investigating protection. Gamma now honestly reports that one standard option contract would over-cover an exposure smaller than 100 shares, so the displayed spread is useful research but not an account-matched expression. A separate public Strategy Lab mission found historical support for a market-neutral long-QQQ/short-SPY relative-value thesis, with low realized volatility and controlled drawdown over the available sample. Neither result is a trading instruction.

## Remediation Status

| Prior finding | Verification result | Live evidence | Status |
| --- | --- | --- | --- |
| GUA-20260903-1 — fitted ATM IV contradicted adjacent observations | The GOOGL 2026-11-20 / 78D ATM cell displayed 33.1%, explicitly labeled strike-interpolated on that expiry, and reconciled with neighboring same-expiry observations around 33%. Per-cell lineage and interpolation counts were visible. | IBKR Max Surface, 66/104 cells; 26 strike-interpolated, 12 wing-extended, no term fallback | **Accepted live** |
| GUA-20260903-2 — Copilot dropped strategy/current-tenor state | The local Options workspace correctly retained the 78D selected expiry and tenor-matched RV/IV. The Copilot run did not receive the built strategy: only surface, session, and a fresh RV/IV analysis appeared as evidence. Code inspection confirms `IvView` clears `ivWorkbenchState` in `onDestroy`, while the handoff changes the active tab before the user submits. Both allowed public-context attempts then failed after the provider tool continuation. | Public AAPL 325/315 put-spread probe; 3 sources, 1 tool, 0 strategy-workbench source; two typed terminal failures | **Not accepted** |
| GUA-20260903-3 — no live-exposure sizing | Position Sizing showed one contract × 100 shares, total debit/profit/loss, shares represented, coverage, a `0 contracts fit` result, and an explicit over-hedge warning while remaining research-only. | Live GOOGL exposure smaller than one standard contract; coverage displayed about 167% | **Accepted live** |
| GUA-20260903-4 — 252D Risk showed 281 aligned observations | Risk displayed requested 252, analyzed 252, exact 2025-09-03 to 2026-09-02 dates, 281 raw rows, and 29 rows outside the newest window. Benchmark overlap also reconciled to 252. | Fresh live Core compute with 100% modeled coverage | **Accepted live** |
| GUA-20260903-5 — provider stayed Healthy despite partial/failing requests | Settings separated session connectivity from request/completeness health and labeled IBKR `Degraded`, with the reason tied to partial surface data and failed requests. The final snapshot remained degraded at 26 successes / 3 errors from 29 IBKR calls. | Partial GOOGL and AAPL surfaces plus provider-usage panel | **Accepted live** |

Verification score: **4/5 accepted live**. Copilot grounding remains open.

The focused regression suite for IV interpolation, Copilot IV grounding, provider usage, and Risk logic also passed: **58 tests passed in 4.88 seconds**. The live browser results above remain authoritative for acceptance because the two residual defects depend on cross-view lifecycle and provider integration.

## Environment And Provider Matrix

| Provider / subsystem | State | Freshness / mode | Used in verdict | Notes |
| --- | --- | --- | --- | --- |
| Gamma runtime | Healthy during the journey | `mock_mode=false`; isolated audit-launched local stack | Yes | Read-only boundary was active. Frontend and backend were stopped after the audit. |
| IBKR / TWS | Connected live during evidence capture | `Auto`; live account/risk data; Options labeled `LIVE / ibkr` | Yes | TWS restarted while the task was paused, which dropped Gamma's connection. The UI reconnected successfully and subsequent AAPL option evidence was live. Final provider state was honestly `Degraded`, not disconnected. |
| Portfolio history | Limited | Isolated local directory; one current point | No | Sufficient for current exposure identity, not for account-path attribution. |
| yfinance | Available | Daily history; 8/8 final recorded calls | Yes | Supplied Risk/realized-volatility history and both public Strategy Lab legs. Gamma labels it an unofficial public source. |
| OpenAI Copilot | Degraded | Quick profile; `gpt-5.6-luna`; two bounded attempts | No | Each attempt received an initial provider response, invoked one tool, then ended on a provider 400 continuation. Gamma rendered a typed error and safe diagnostic. |
| Gamma Strategy Lab | Derived | 939 aligned daily observations, 2022-12-06 through 2026-09-03 | Yes, coverage thesis only | Read-only composition; not saved; no broker portfolio modification. |

The final provider snapshot contained 81 calls overall. IBKR reported 29 calls, 26 successes, 3 errors, and partial data; OpenAI Copilot reported `Degraded`; yfinance reported 8/8 successful calls. The UI remained connected to TWS until the deliberate Gamma-only disconnect.

## Declared Baseline Constraints

- `Auto` market-data mode was preserved. Entitlement-by-contract and executable bid/ask quality were not independently established.
- Partial IBKR option coverage is expected to occur; the verification criterion was honest provenance, interpolation, and health reporting rather than a fabricated complete surface.
- Portfolio details were minimized. This report retains aggregate concentration and risk contribution but no account identifier, account value, position quantity, P&L, or margin figures.
- The public AAPL Options context was used for Copilot so no live holding or account data was sent to the external model.
- No IV stream was started. The audit used bounded cross-sectional Max Surface requests.
- TWS itself was not launched or stopped by the audit. Only the Gamma client connection and audit-launched app processes were cleaned up.

## Research Question And Provisional Thesis

- Primary question: Does the live GOOGL risk concentration still justify investigating medium-horizon downside protection after the fixes, and can Gamma now evaluate the visible spread honestly?
- Provisional thesis: Protection remains worth researching if GOOGL contributes materially more modeled risk than capital weight and selected-expiry implied volatility is not prohibitively rich versus medium-horizon realized volatility.
- Horizon: 78 days for the option structure; one to three months for the risk decision.
- Expected confirmation: Elevated variance contribution, trustworthy same-expiry IV, selected-tenor RV/IV comparison, and a sizing result that explicitly accepts or rejects whole-contract coverage.
- Falsifier / kill condition: Benign risk contribution; selected-expiry IV materially rich to realized volatility; inconsistent surface lineage; or no whole-contract fit to the exposure.
- Hypothetical expression: Research only, per 100 shares, a GOOGL 2026-11-20 335/315 put spread. Gamma correctly rejected it as an exact account-matched hedge because the live exposure was smaller than one contract.

## Journey

| # | Surface and action | Evidence / visible provenance | Result | Classification |
| ---: | --- | --- | --- | --- |
| 1 | Launch isolated Gamma, confirm TWS on 7496, and connect through the UI | `mock_mode=false`; read-only boundary active; IBKR connected live | Provider gate passed | Worked |
| 2 | Replay live Portfolio/Risk concentration and compute 252D Core | 100% modeled coverage; requested/analyzed 252; exact dates; 281 raw rows with 29 excluded | GOOGL was about 52% of exposure and 71.9% of modeled variance contribution; analysis identity reconciled | Worked |
| 3 | Load GOOGL Max Surface and select 2026-11-20 / 78D | `LIVE / ibkr`; 66/104 cells; cell lineage; interpolation summary | Selected ATM IV was 33.1% and consistent with neighboring observations | Worked with honest degradation |
| 4 | Open Realized vs IV | Explicit Front and Selected columns | 20D realized 24.3% vs selected 33.1%; 60D 36.7% vs 33.1%; 120D 36.3% vs 33.1% | Worked |
| 5 | Build the 335/315 put-spread template and inspect Position Sizing | One contract × 100 shares; total debit/payoff; `0 contracts fit`; over-hedge warning | Exact account-matched expression was honestly rejected without execution controls | Worked |
| 6 | Compare Settings with partial surface/request evidence | IBKR `Degraded`; reason linked partial surface and failures | Health semantics matched visible degradation | Worked |
| 7 | Change Options from GOOGL to AAPL after building the spread | AAPL surface/chain loaded, but GOOGL legs and marks remained until a template was clicked again | New cross-symbol state-contamination defect | Blocked by product defect |
| 8 | Rebuild a public AAPL 2026-11-20 325/315 spread and inspect selected-tenor RV/IV | Correct AAPL legs, 3.85 debit and 6.15 maximum profit per share; 60D realized 32.7% vs selected 27.1% | Local state was coherent | Worked |
| 9 | Send the public AAPL Options context to Copilot and retry once | Evidence listed surface, session, and RV/IV analysis; no strategy-workbench source; 2 provider calls and 1 tool call per terminal run | Both runs ended in a typed provider error; current strategy state was absent | Blocked by product defect and provider continuation failure |
| 10 | Run the Strategy Lab coverage mission | Two public provider-resolved ETF legs; yfinance provenance; 939 aligned observations | Market-neutral QQQ-minus-SPY history produced 13.61% cumulative return, 3.95% annual vol, 0.89 Sharpe, and -4.26% max drawdown | Worked |
| 11 | Capture final provider state and clean up | Gamma disconnected; ports 5173/8000 closed; TWS still listening on 7496 | Audit state cleaned without touching TWS or account state | Worked |

## Coverage Mission

- Target surface: Strategy Lab.
- Why it had the highest coverage debt: It was the highest-debt research surface in the coverage ledger and had not received substantive provider-backed use in the two most recent audits.
- Purpose-specific question: Has AI/growth beta, represented by QQQ, delivered persistent excess return versus broad US beta, represented by SPY, with a tolerable market-neutral drawdown?
- Provider-backed input: Public QQQ and SPY daily histories from yfinance, both aligned from 2022-12-06 through 2026-09-03.
- Meaningful action: Removed the unrelated inline prediction proxy from the transient default book, set QQQ to +1 and SPY to -1, validated the book, and composed the unsaved read-only portfolio.
- Result: 939 aligned return observations, 13.61% total return, 3.48% annual return, 3.95% annual volatility, 0.89 Sharpe, 1.28 Sortino, and -4.26% maximum drawdown. Annual returns were positive in 2023, 2024, 2025, and year-to-date 2026, but July 2026 was -3.29% and early September was negative.
- Verdict: Historically supported, with moderate confidence. The spread is a relative-value monitoring thesis, not a prediction that QQQ will continue to outperform.
- Kill condition: A sustained negative trailing-12-month spread, drawdown materially beyond roughly 5%, or a regime change in which QQQ downside beta rises without compensating excess return.
- Coverage credit: Deep enough for Composer validation, provider alignment, metrics, provenance, and a meaningful control; Regime Stress, Script, Backtest, save/reload, and Risk handoff remain unverified.

## Thesis Verdict

- Primary GOOGL verdict: partially confirmed.
- Thesis confidence: Medium, approximately 0.72.
- Data-quality confidence: Medium-high for Risk and selected-expiry Options, approximately 0.82; low for the failed Copilot terminal path.
- Supporting evidence: GOOGL contributed 71.9% of modeled variance at about 52% capital weight; selected 78D ATM IV was a lineage-tagged 33.1%; 60D and 120D realized volatility were 36.7% and 36.3%; the 252D Risk sample reconciled exactly.
- Contrary evidence: 20D realized volatility was only 24.3%, partial chain coverage remained, executable liquidity was unverified, and a whole contract would over-cover the live exposure.
- Falsifier status: Partially met. The concentration signal survived and the data-quality defects were repaired, but the exact spread failed the whole-contract sizing gate by design.
- Decision implication: Continue researching downside protection, but do not treat the 335/315 spread as account-matched. A smaller-notional instrument or a portfolio-level risk reduction would require a separate research path and is outside Gamma's execution boundary.

## What Worked

- Four prior live acceptance criteria passed without mock data.
- Selected-expiry IV now remained near same-expiry observations and exposed cell-level lineage rather than silently repeating a bad ATM value.
- Realized-versus-implied panels separated front and selected expiries, eliminating the earlier mixed-tenor ambiguity.
- Risk reconciled requested, analyzed, raw, excluded, benchmark-overlap, and date-window identity.
- Position Sizing made the standard multiplier and over-hedge result explicit while preserving Gamma's no-routing boundary.
- Settings correctly reported a connected but degraded IBKR provider rather than equating connectivity with complete request success.
- Strategy Lab produced a useful public relative-value result with explicit source, alignment, normalization, and research-only warnings.

## Findings

### P1 — GUA-20260903-6: Options strategy state survives a symbol change with incompatible legs and marks

- Journey impact: The workspace can present an AAPL header and chain while retaining a GOOGL spread, prices, payoff, and sizing. Any downstream analysis or Copilot context can therefore mix instruments unless the user notices and manually rebuilds.
- Expected: Loading a new symbol should clear incompatible strategy legs, payoff, template notice, and sizing, or explicitly rebind/reprice a compatible structure to the new symbol with a visible confirmation.
- Observed: After building the GOOGL 335/315 put spread, changing the symbol to AAPL loaded the AAPL surface and chain but left the 335/315 GOOGL legs and 8.09 debit visible. Clicking the AAPL Put Spread template rebuilt correct AAPL legs and marks.
- Evidence: Direct live UI comparison before and after the symbol load; source inspection shows the symbol-change path resets `selectedExpiry` but does not clear `strategyLegs`.
- Reproduction: Connect live IBKR; load GOOGL Options; build the 2026-11-20 spread; change the symbol to AAPL and load; open Strategies without clicking a new template.
- Classification: product defect.
- Acceptance criteria: A symbol change atomically clears or safely rebinds every symbol-dependent strategy value; stale legs cannot be rendered under a different active symbol; workbench/Copilot payload validation rejects mismatched surface and leg symbols; add a browser-level GOOGL-to-AAPL regression test.

### Open — GUA-20260903-2: Options workbench state is cleared before Copilot submission

- Journey impact: The Copilot cannot evaluate the strategy the user explicitly handed off, even when the local Options calculations are correct.
- Expected: The selected symbol, submode, expiry, legs, marks, payoff, sizing, Greeks, and selected-tenor RV/IV state should be captured atomically at handoff and persist through the later terminal submission.
- Observed: The public AAPL run exposed surface/session/RV-IV evidence but no `iv.strategy` / `Options strategy workbench` source. `IvView` publishes the state, then clears `ivWorkbenchState` in `onDestroy`; `handleSendToCopilot` changes the active tab and destroys the view before the user submits.
- Provider behavior: The initial Responses call returned successfully, the automatic RV/IV tool completed, and the continuation returned 400 on both the first attempt and the one allowed retry. Gamma rendered an honest typed terminal error.
- Classification: product defect; prior acceptance criterion remains open.
- Acceptance criteria: Snapshot workbench state into the handoff or persisted Copilot session before leaving Options; validate symbol consistency; show `Options strategy workbench` in evidence; complete a public-context live prompt that reproduces expiry, both legs, debit, maximum profit, RV/IV, and a falsifier.

## Cross-Tab And State Continuity

Portfolio, Risk, and Options agreed on the GOOGL identity and concentration signal. Selected expiry stayed coherent across Surface, Chain, RV/IV, and the rebuilt strategy. Two continuity breaks remain: strategy legs are not invalidated on a symbol change, and the entire Options workbench is cleared when the view is destroyed on the Copilot handoff. These are related state-lifecycle defects with different triggers and should be tested independently.

## Copilot Evaluation

- Scope/privacy: Only public AAPL Options context was used; no account data was sent.
- Local grounding: Selected expiry and RV/IV were correct before navigation.
- Persisted grounding: Failed. Surface and session persisted; the strategy workbench did not.
- Tool behavior: `run_options_realized_implied_comparison` completed and produced eight expiry rows.
- Provider delivery: Failed twice after the tool continuation. The UI showed a typed provider error, one-retry guidance, routing/usage telemetry, and a safe diagnostic instead of fabricating a card.
- Evidence rendering: Three sources and one tool were inspectable, but the missing strategy source is the decisive defect.
- Persistence: The public audit conversation remains in the isolated local Copilot history because deletion was not necessary for verification and was not implicitly authorized.
- Memo/export: Not exercised because no trustworthy terminal card completed.

## Unsupported And Unverified Boundaries

- No trade, order, rebalance, save, wallet action, account write, or execution-quality test was attempted.
- Bid/ask spread, fill probability, slippage, and executable liquidity remain unverified.
- Strategy Lab Regime Stress, Script, Backtest, save/reload, and Risk handoff were not exercised.
- Copilot with private Portfolio/Risk context was intentionally not exercised.
- The OpenAI 400 continuation's detailed upstream body was not exposed by Gamma; this audit establishes the failure point but not a unique upstream root cause.
- TWS restart resilience was observed only once and opportunistically, not as a controlled fault-injection test.

## Coverage Ledger Update

- Surfaces credited this run: Portfolio, Risk, Options, and Strategy Lab.
- Coverage depth: Portfolio/Risk/Options were substantive fix-verification replays; Strategy Lab received its first provider-backed coverage mission.
- Copilot remains uncredited because no trustworthy terminal result completed and the active strategy source was absent.
- Highest remaining debt: Macro, Prediction Markets, Crypto, Commodities, Sealanes, and a successful state-preserving Copilot terminal pass.

## Scorecard

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | 8/10 | Live account/risk/options plus public relative-value history covered the targeted decisions. |
| Data depth and drill-down | 9/10 | Risk reconciliation, cell lineage, RV/IV, payoff, sizing, provider health, and Strategy Lab metrics were inspectable. |
| Data trust and provenance | 8/10 | Four prior trust defects were repaired; partial IBKR coverage was labeled honestly. Copilot state loss remains material. |
| Analytical tooling | 9/10 | Risk, Options, and Strategy Lab supported real bounded research without execution authority. |
| Cross-tab continuity | 6/10 | Identity generally held, but symbol changes and Options-to-Copilot lifecycle boundaries can retain or discard the wrong state. |
| Recovery and state resilience | 7/10 | Gamma reconnected after a TWS restart and preserved typed provider failure, but the Copilot retry failed identically. |
| Agent drivability | 8/10 | Primary controls were accessible and deterministic; strategy cleanup still depends on user vigilance. |
| Speed to insight | 8/10 | Live Risk/Options and public Strategy Lab reached useful evidence with bounded waits. |
| Overall | 7.9/10 | The core live research surfaces improved materially and four fixes passed, but two P1 state-lifecycle defects still block trustworthy Copilot use. |

## Cleanup And Residual State

- Gamma's audit-started client was disconnected from IBKR after evidence capture.
- The pre-existing TWS process remained open and listening on port 7496.
- The audit-launched frontend and backend were stopped; ports 5173 and 8000 were closed.
- The in-app audit browser tab was closed.
- The transient Strategy Lab composition was not saved.
- No product code, tests, configuration, roadmap, portfolio, order, or account state was modified.
- The isolated temporary portfolio-history directory was left in place rather than destructively deleting an automatically generated path.
- One public-context AAPL Copilot conversation remains in the isolated local audit history; it contains no private account context.

## Audit-Only Follow-Up

1. **Close GUA-20260903-2:** persist an atomic Options workbench snapshot before navigation, keep it in the Copilot session fingerprint, and fix or expose the provider continuation failure. Accept only with a live public-context card that cites the exact visible strategy and selected tenor.
2. **Fix GUA-20260903-6:** invalidate or rebind every symbol-dependent strategy field on symbol changes, add mismatch guards to the UI and Copilot payload, and cover GOOGL-to-AAPL switching in a browser regression test.
3. **Retain the four accepted fixes:** add live-contract fixtures or deterministic replay coverage for IV lineage, 252D row reconciliation, sub-contract sizing, and degraded provider semantics.

This audit made no implementation changes and does not mark the two remaining state defects fixed.
