# Gamma Usability Findings — 2026-09-03

Date: 2026-09-03, Europe/Madrid (CEST)
Audience: Gamma product and engineering
Mode: IBKR-integrated
IBKR state: connected live during the journey; Gamma disconnected during cleanup
Runtime: audit-launched frontend and backend; pre-existing TWS session
Commit / branch / dirty state: `9ef7251e9be88ff61a71535b5c44736cc13ff3d4` on `main`; clean at start
Data context: regular US session; Gamma market-data mode `Auto`; live IBKR futures and FX context; Treasury/FRED macro context; yfinance ETF histories; isolated portfolio-history directory
Scope: Audit-only research journey from SITREP through Macro, Commodities, Strategy Lab Backtest / Regime Stress / Saved Runs / Script boundary, and Risk. No order, trade, rebalance, account mutation, provider configuration, roadmap change, or product-code change was attempted.

## Outcome

The provider-backed completion gate passed and the journey reached a research verdict, but the provisional long-gold / short-long-duration thesis was **rejected as a ready research expression**. Gamma found a compelling live divergence and a strong historical backtest, yet Strategy Lab's Regime Stress mode exposed a `-14.31%` drawdown and Risk showed that `93.5%` of modeled variance came from the long-gold leg. The new Strategy modes materially improved the decision by preventing a high headline return and `1.3` Sharpe from being mistaken for robust diversification.

Three trust defects obstructed the workflow. Commodities sent a selected Gold object with 120 visible history observations into Strategy Lab, but the resolver called it unsupported because no history was attached. Strategy Lab then discarded the edited composer draft when the user left for Risk, although the computed result survived. Most seriously, the initial Strategy Lab-to-Risk handoff rendered strategy-book core metrics under a source selector still set to `Live Account Portfolio` while the side panels showed live-account movers and concentration. Manually selecting the strategy book cleared the account rows and restored coherent provenance.

## Environment And Provider Matrix

| Provider / subsystem | State | Freshness / mode | Used in verdict | Notes |
| --- | --- | --- | --- | --- |
| Gamma runtime | Healthy | `mock_mode=false`; isolated audit-launched local stack | Yes | Read-only boundary active. |
| IBKR / TWS | Connected | `Auto`; live/cached futures and FX context | Yes | Eight recorded IBKR calls, eight successful. TWS was pre-existing and remained open. |
| Treasury / FRED / Macro adapters | Available with degradation | 3M US window; Treasury curve; FRED-derived series | Yes | Macro loaded after a slow request. Gold FRED reference failed, but live IBKR Gold remained usable. |
| yfinance | Available | Daily GLD, TLT, and SPY histories through 2026-09-03 | Yes | Seven recorded calls, seven successful; unofficial public source. |
| Commodities | Mixed provider-backed | Live IBKR `GCU6`; some cached IBKR roots and public proxies | Yes | Selected Gold refreshed at 17:17 local time; 120 history observations through 2026-09-02. |
| Strategy Lab | Derived | 938 aligned daily returns, 2022-12-06 through 2026-09-03 | Yes | Read-only composition; normalized result saved as an audit artifact. |
| Research Script runtime | Mock safe preview | Code execution disabled | No | Honest boundary; no substantive script run attempted. |
| News | RSS with one provider failure | Delayed | No | One RSS call succeeded overall; one ECB feed certificate error was disclosed. |

The final Settings snapshot reported 172 provider calls: yfinance `7/7`, IBKR `8/8`, RSS `1/1`, and 155 successful calls attributed to `unknown`. Browser diagnostics recorded no console errors and six slow-request warnings, including SITREP at about 16.5 seconds and Macro at about 14.5 seconds.

## Declared Baseline Constraints

- `Auto` market-data mode was preserved; contract-by-contract live versus delayed entitlement was not independently established.
- GLD and TLT were public ETF proxies. The composition is not a futures-roll strategy and does not model financing, borrow, transaction costs, or executable P&L.
- The commodity handoff was allowed to resolve once and was not force-retried after Gamma classified it as unsupported.
- Script mode was configured as `MOCK / SAFE PREVIEW` with execution disabled. It was inspected for boundary honesty but not counted as provider-backed coverage.
- No private portfolio values, quantities, P&L, account identifiers, or credentials are retained in this report.

## Research Question And Provisional Thesis

- Question: Does gold's strength alongside sharply higher U.S. real and nominal yields support a robust long-gold / short-long-duration relative-value basket?
- Provisional thesis: Persistent real-asset demand may allow a 50% long `GLD` / 50% short `TLT` research basket to outperform with limited equity beta while duration remains pressured.
- Horizon: one to three months for monitoring; three years of daily history for the initial test.
- Initial signal: SITREP showed 2Y, 5Y, and 10Y Treasury yields about 32–36 bps higher over three months while Gold was up 3.3% and broad equities were positive.
- Expected confirmation: live Gold provenance, a Macro regime consistent with duration pressure, positive and reasonably stable relative returns, controlled drawdown, and low benchmark beta.
- Falsifier / kill condition: stale or proxy-conflicted Gold data; Regime Stress drawdown worse than roughly 10%; strong positive equity beta; or risk dominated by one leg.
- Hypothetical expression: research only, `+0.5 GLD / -0.5 TLT`, normalized by gross exposure. No execution intent.

## Journey

| # | Surface and action | Evidence / visible provenance | Result | Classification |
| ---: | --- | --- | --- | --- |
| 1 | Run preflight, launch isolated `MOCK_DATA=false` Gamma, and connect to the existing TWS through Settings | Clean `main`; read-only boundary; `Auto`; visible connected state | IBKR-integrated gate passed | Worked |
| 2 | Scan SITREP and follow the policy-divergence card into Macro | yfinance equities/indices; Treasury/FRED macro context; IBKR FX/futures; explicit ages and warnings | Rates rose sharply while the broad dollar lagged | Worked with degradation |
| 3 | Inspect Macro Cross-Asset / Policy | US 2Y `4.39%` (`+0.41 pp`), 10Y `4.79%` (`+0.34 pp`), 10Y real yield `2.44%` (`+0.37 pp`), DXY proxy `-0.4` | Tighter policy signal was coherent; inflation signal was fractured | Worked |
| 4 | Open Commodities, select Gold, and enter Metals | Live IBKR `GCU6` at `4,510`, `+3.29%`; 120 observations; 30D correlation `-0.92` to broad USD and `-0.61` to 10Y real yield | Gold move was provider-backed and genuinely anomalous to the real-yield tape | Worked with degradation |
| 5 | Use Commodities `Add & Open` to Strategy Lab | Handoff preserved Gold identity but resolver reported no attached price history despite 120 visible observations in Metals | Exact commodity-object workflow blocked | Blocked by product defect |
| 6 | Build and validate `+0.5 GLD / -0.5 TLT` in Strategy Lab Composer | yfinance on both legs; 938 aligned observations; gross `1x`, net `0x`; explicit research-only warnings | Public-proxy fallback was valid | Worked |
| 7 | Compose and inspect Backtest | 2022-12-06 to 2026-09-03; `68.01%` total return; `14.96%` annual return; `11.25%` vol; `1.3` Sharpe; `1.8` Sortino | Strong headline historical result | Worked |
| 8 | Inspect Regime Stress | Worst drawdown `-14.31%`; recent rolling return `3.53%`; rolling vol `13.52%`; beta `0.37`; correlation `0.38` | Drawdown kill condition triggered | Worked with degradation |
| 9 | Open the Strategy Lab book in Risk | Header/core metrics showed the research book, but source selector and side panels initially retained live-account state | Cross-tab identity was mixed until manual correction | Blocked by product defect |
| 10 | Manually select the Strategy Lab source and run bounded 2k-path, 10D Gaussian Monte Carlo | 100% modeled coverage; newest 252 of 938 rows; strategy-only provenance; Gold proxy `93.5%` of variance contribution; MC ES `-11.4%` | Risk concentration rejected the diversification framing | Worked with degradation |
| 11 | Return to Strategy Lab | Computed result survived; edited GLD/TLT composer draft reset to the default QQQ/SPY/prediction template | Re-edit required for any continuation | Blocked by product defect |
| 12 | Save and reload the normalized result, then inspect Script | Saved-run load restored 938 return points and metrics; Script honestly showed mock preview and execution disabled | Terminal artifact succeeded; Script provider-backed run unavailable | Worked with degradation |
| 13 | Capture provider usage and clean up | 172 calls; browser warnings only; Gamma disconnected; audit ports closed; TWS stayed open | Cleanup complete | Worked |

## Coverage Mission

- Target surface: Macro.
- Why it had the highest coverage debt: Macro had no credited substantive use in the existing ledger and was safely exercisable with official/provider-backed data.
- Purpose-specific question: Did the current macro regime genuinely support duration pressure, and was Gold's strength a broad inflation signal or a divergence?
- Provider-backed input: Treasury curve and FRED-derived U.S. series, plus IBKR FX context.
- Meaningful action and result: Followed the SITREP policy handoff, preserved `US / 3M / Policy`, and inspected Cross-Asset signals. The 2Y, 10Y, and 10Y real yield moved higher while the dollar proxy lagged; breakevens fell as CPI rose, leaving inflation `fractured` rather than confirming a broad inflation regime.
- Classification: `Worked`.
- Coverage credit: Deep use within the primary journey. Rates, policy, provenance, timeframe, cross-tab entry, supporting evidence, and contradictory inflation evidence were all interpreted.

## Thesis Verdict

- Verdict: rejected.
- Thesis confidence: Medium-high, approximately 0.76, that the visible setup is interesting but the tested basket is not a robust diversifier.
- Data-quality confidence: Medium-high, approximately 0.80. The decisive Strategy/Risk inputs were provider-backed and aligned, but the futures-to-ETF proxy change, commodity handoff failure, and Risk state mix reduce confidence.
- Supporting evidence: live Gold gained `3.29%`; the GLD/TLT basket returned `68.01%` over 938 daily observations with `14.96%` annualized return and `1.3` Sharpe; the latest rolling return was positive.
- Contrary evidence: `-14.31%` max drawdown breached the kill condition; beta and correlation to SPY were positive; `93.5%` of modeled variance contribution came from the long-gold proxy; Macro showed falling breakevens and higher real yields rather than a clean inflation regime.
- Falsifier status: Met. The drawdown and risk-concentration conditions both failed.
- Research-only implication: Keep Gold-versus-duration as a divergence monitor, not as a deployable hedge. A later study could test volatility-scaled or drawdown-controlled weights, but that is a new thesis rather than a repair to this run.

## What Worked

- SITREP produced a useful, current cross-domain anomaly and preserved `US / 3M / Policy` into Macro.
- Macro separated coherent tighter-policy evidence from fractured inflation evidence instead of forcing one regime label.
- Commodities refreshed the exact Gold future with contract, timestamp, prior date, curve, history, and macro-correlation context.
- Composer validation exposed aligned windows and normalized signed weights before computation.
- Backtest and Regime Stress shared one active stream and made headline performance, drawdown, and recent rolling behavior easy to compare.
- Risk accepted the signed aggregate return stream, analyzed the newest 252 rows, and explicitly separated the research book from the broker account after the source was corrected.
- Saved Runs restored normalized metrics with an explicit note that raw CSV rows were not persisted.
- Script mode clearly disclosed its no-network, no-host, no-provider, no-account, no-wallet, no-trade authority and disabled code execution in the configured preview runtime.

## Findings

### P1 — GUA-20260903-7: Strategy Lab-to-Risk handoff mixes research-book and live-account state

- Journey impact: The user can believe Risk is showing one coherent Strategy Lab book while the source selector and side panels still display the live account. This can contaminate a research conclusion with private, unrelated holdings and makes source identity untrustworthy.
- Expected: A handoff should atomically select the Strategy Lab source, compute from that source, clear incompatible account-derived panels and Monte Carlo state, and render one consistent provenance label.
- Observed: Immediately after `Open In Risk`, the header and core/contribution metrics named `AUDIT 2026-09-03 Gold vs Duration`, but the source selector remained `Live Account Portfolio`; Largest Movers and Concentration Flags showed live-account rows. Selecting the Strategy Lab option manually cleared those rows and changed price-source provenance to `Strategy Lab validated aggregate return stream`.
- Evidence: Direct live UI comparison before and after changing the source selector. No API substitution was used.
- Reproduction: Compose a signed Strategy Lab book; click `Open In Risk`; inspect the header, source selector, contribution table, Largest Movers, Concentration Flags, and provenance before touching the source control.
- Classification: product defect.
- Acceptance criteria: The handoff commits one atomic source identity before rendering; every core, contribution, mover, concentration, scenario, optimization, and Monte Carlo panel either refreshes from the research book or clears; the selector matches the active computation; no live-account row can appear under a Strategy Lab header; add a browser regression with distinctive book and account symbols.

### P1 — GUA-20260903-8: Commodities-to-Strategy Lab handoff drops loaded Gold history

- Journey impact: The highest-value handoff for this thesis failed, forcing the user to substitute an ETF proxy and weakening contract/basis fidelity.
- Expected: `Add & Open` from Gold Metals should carry or re-resolve the 120 loaded price observations, provider, contract, unit, and non-roll-adjusted caveat into a read-only Strategy Lab return stream.
- Observed: Commodities showed Gold `GCU6`, 120 price-history observations, and live IBKR provenance. Strategy Lab preserved the `Gold` identity but classified the handoff `unsupported` and stated that the selected commodity had no loaded price history.
- Evidence: Direct visible source and target states; no backend probe replaced the UI step.
- Reproduction: Connect TWS; open Commodities; select Gold; confirm the 120-observation price-history label; click `Add & Open`; wait for handoff resolution.
- Classification: product defect.
- Acceptance criteria: The handoff carries or deterministically reloads the exact visible history and its contract/basis metadata; the target reports the same observation window; failures distinguish missing history from unsupported transformation; a live Gold regression reaches an accepted Strategy Lab input without substituting GLD.

### P2 — GUA-20260903-9: Returning from Risk discards the edited Strategy composer draft

- Journey impact: The computed result survives, but the exact GLD/TLT builder inputs reset to the default QQQ/SPY/prediction template. The user must reconstruct the book to revise a weight, label, or lookback.
- Expected: The current composer draft should survive tab switches, especially after it produced the active result, or Gamma should offer an explicit `Restore inputs from result` action.
- Observed: The result `AUDIT 2026-09-03 Gold vs Duration` remained active after returning from Risk, but the builder showed the default three-leg template and `Strategy Lab Portfolio` title.
- Evidence: Direct UI comparison before and after Strategy Lab → Risk → Strategy Lab.
- Reproduction: Edit the default composer, validate and compose, open in Risk, then return to Strategy Lab Composer.
- Classification: usability friction.
- Acceptance criteria: Preserve unsaved builder state across tab switches or restore exact inputs from the active/saved result; clearly distinguish draft, active result, and saved state; add a round-trip browser test.

### P2 — GUA-20260903-10: Provider diagnostics misattribute a FRED failure to IBKR and hide most calls under `unknown`

- Journey impact: The user cannot reliably identify which provider failed or judge whether a healthy IBKR session explains a missing Gold reference.
- Expected: FRED failures should appear under FRED, IBKR health should summarize only IBKR calls/data quality, and every recorded macro/prediction call should retain an actionable provider identity.
- Observed: Settings labeled IBKR `Healthy` while its detail text reported `FRED series GOLDAMGBD228NLBM failed`; 155 of 172 successful calls were grouped under `unknown` despite visible Treasury, FRED, Kalshi, and Polymarket use.
- Evidence: Final visible Settings provider-usage panel.
- Reproduction: Load SITREP, Macro, and IBKR Commodities Gold; open Settings; inspect provider call groups and provider health detail.
- Classification: product defect.
- Acceptance criteria: Attribute each provider call and failure to the correct provider; do not attach another provider's warning to IBKR; reduce `unknown` to genuinely internal/derived work with an explicit label; retain activation-aware health semantics.

### P3 — GUA-20260903-11: Regime Stress omits year and rolling-window definitions from key tables

- Journey impact: Worst-drawdown dates such as `Jun 24` are ambiguous across a multi-year sample, and the user cannot tell what horizon `ROLL RET`, rolling beta, correlation, and volatility use without inference.
- Expected: Multi-year dates include the year, and every rolling metric exposes its window and frequency in the header or tooltip.
- Observed: The sample covered 2022-12-06 through 2026-09-03, but Worst Drawdowns displayed month/day only; `ROLL RET`, `VOL`, `BETA`, and `CORR` had no visible rolling-window label.
- Evidence: Direct Strategy Lab Regime Stress UI observation.
- Reproduction: Compose any multi-year strategy and open Regime Stress.
- Classification: usability friction.
- Acceptance criteria: Show full dates for multi-year windows; label rolling return/volatility/beta/correlation horizons and observation frequency; carry the definitions into saved/exported artifacts.

## Cross-Tab And State Continuity

SITREP-to-Macro continuity worked: the handoff landed on `US / 3M / Policy` and then Cross-Asset. Commodities-to-Strategy Lab preserved entity identity but lost the loaded history, so it failed. Strategy Lab-to-Risk preserved the book title and aggregate series but initially mixed source selection and live-account side panels; a manual source change repaired the visible state. Returning to Strategy Lab preserved the computed result but discarded the edited builder draft. Saved Runs successfully restored the normalized result and metrics.

## Unsupported And Unverified Boundaries

- Options, Fundamentals, Prediction Markets detail, Crypto, Sealanes, Portfolio history, durable Copilot, and execution-quality questions were not exercised.
- Research Script execution was unavailable in the configured `MOCK / SAFE PREVIEW` runtime; code, snapshot preparation, typed outputs, cancellation, and retained-output recovery remain unverified here.
- Financing, borrow, fees, slippage, taxes, futures roll, volatility scaling, and live execution were not modeled.
- The apparent MC terminal values updated visually after `RUN MC`, but the UI did not expose a run timestamp or result identity; freshness of the terminal plot remains `Unverified` beyond the visible strategy source and parameters.
- The root cause of the Gold handoff loss was not established through storage or API inspection; the visible UI failure is sufficient for the product classification.

## Coverage Ledger Update

- Surfaces credited this run: SITREP, Macro, Commodities, Strategy Lab, and Risk.
- Coverage depth: Macro received deep coverage within the primary journey; Strategy Lab received Backtest, Regime Stress, save/reload, and Risk-handoff coverage; Commodities received provider-backed Gold/Metals use but its outbound handoff failed.
- Surfaces still carrying the highest debt: Prediction Markets, Crypto, Sealanes, a provider-backed Script run, and a successful trustworthy Copilot terminal pass.
- Environment/provider qualification: IBKR-integrated live, with yfinance public histories and Treasury/FRED macro context; degraded where explicitly stated.

## Scorecard

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | 8/10 | Live futures/FX, official macro context, public ETF histories, and derived Risk supported a coherent cross-domain test. |
| Data depth and drill-down | 8/10 | Macro decomposition, Gold curve/history/correlation, Backtest, Regime Stress, saved runs, and Risk contribution were substantive. |
| Data trust and provenance | 6/10 | Individual surfaces were well labeled, but two handoffs mixed or dropped data and Settings misattributed a provider failure. |
| Analytical tooling | 9/10 | The new Strategy modes decisively overturned a superficially attractive backtest. |
| Cross-tab continuity | 4/10 | SITREP-to-Macro worked, but Commodities-to-Strategy and Strategy-to-Risk had material identity failures. |
| Recovery and state resilience | 6/10 | Manual Risk source selection and Saved Runs recovered the analysis; the composer draft did not survive navigation. |
| Agent drivability | 8/10 | Major controls were accessible and deterministic; blocked handoff and state repair required vigilance. |
| Speed to insight | 6/10 | The decision was reachable, but SITREP/Macro latency and handoff repair slowed the path. |
| Overall | 6.9/10 | Strong analytical depth and honest boundaries, weakened by cross-tab state/provenance defects. |

## Cleanup And Residual State

- Gamma was disconnected from IBKR after evidence capture.
- The pre-existing TWS process remained open and listening; it was not launched, restarted, or stopped by the audit.
- The audit-launched frontend and backend were stopped; ports 5173 and 8000 were closed.
- No IV collection, streaming session, order, trade, rebalance, account write, wallet action, provider configuration, credential, roadmap, or product-code state changed.
- The clearly labeled `AUDIT 2026-09-03 Gold vs Duration` saved Strategy Lab result remains in the isolated audit data directory as a terminal research artifact.
- One additional generic `Strategy Lab Run` saved result remains beside it because the first Composer-level save used the default Saved Runs title; it was created by this audit but not deleted through the UI without explicit destructive-action confirmation.
- One unsupported Gold inbound handoff remains visible in Strategy Lab. It was created by this audit and left as direct reproduction evidence.
- The isolated audit data directory was retained to preserve those research artifacts. Its temporary session-token file, backend logs, and portfolio-history CSV were removed after process shutdown.

## Audit-Only Follow-Up

1. **Fix GUA-20260903-7 first:** make Strategy Lab-to-Risk source selection and every dependent panel atomic. This is the highest trust risk because private live-account state can appear under a research-book header.
2. **Fix GUA-20260903-8:** preserve the exact loaded commodity series and basis through the handoff so the user does not have to substitute an ETF.
3. **Fix GUA-20260903-9:** retain or explicitly restore the composer inputs that produced the active result.
4. **Fix GUA-20260903-10:** correct provider attribution and eliminate misleading cross-provider health messages.
5. **Polish GUA-20260903-11:** make Regime Stress horizons and dates self-identifying.

This audit made no product implementation changes and does not mark any finding fixed.
