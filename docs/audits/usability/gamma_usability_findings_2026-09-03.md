# Gamma Usability Findings — 2026-09-03

Date: 2026-09-03, Europe/Madrid (CEST)
Audience: Gamma product and engineering
Mode: IBKR-integrated
IBKR state: connected live
Runtime: audit-launched frontend and backend; pre-existing TWS session
Commit / branch / dirty state: `6cc410368f94371a35ea698991babbf65882a293` on `main`; four pre-existing dirty paths were preserved
Data context: US after-hours snapshot; Gamma market-data mode `Auto`; live IBKR option-chain data; yfinance daily history; SEC/company fundamentals; one-point local portfolio history
Scope: Read-only GOOGL concentration and downside-hedge thesis across Portfolio, Risk, Fundamentals, Options, and Copilot. No order, trade, rebalance, or account mutation was attempted.

## Outcome

The research thesis was **partially confirmed**. Gamma established that GOOGL was 51.5% of the live account exposure but 71.5% of modeled variance contribution, and it showed medium-horizon realized volatility near 36% against roughly 33% observed 79-day put volatility. That supports investigating downside protection rather than adding exposure. The provider gate passed with `mock_mode=false`, TWS connected, IBKR labeled live/healthy, and Gamma's read-only boundary active. The end-to-end journey nevertheless could not validate the visible 79-day 340/315 put spread as an account-matched expression: one standard contract would exceed the live share exposure, the fitted surface printed a 24.4% ATM value inconsistent with adjacent observed chain cells near 33%, and Copilot omitted the visible debit/payoff/79-day context while citing mixed-tenor and unavailable evidence. No trade should be inferred from this audit.

## Environment And Provider Matrix

| Provider / subsystem | State | Freshness / mode | Used in verdict | Notes |
| --- | --- | --- | --- | --- |
| Gamma runtime | Healthy during journey | `mock_mode=false`; local audit-launched stack | Yes | Frontend and backend were reachable; read-only boundary reported active with prohibited capabilities locked. |
| IBKR / TWS | Connected live during journey | `Auto`; Portfolio quote mode `snapshot`; Options labeled `LIVE / ibkr` | Yes | Settings reported 86/86 successful IBKR calls, but diagnostics retained 50 recent errors and the surface contained 71/104 cells. This contradiction is a finding. |
| Portfolio history | Degraded | Local history contained one point | No | Current positions and quotes were usable; historical account-path analysis was not. |
| yfinance | Healthy | Daily history; 20/20 recorded calls | Yes | Supplied realized-volatility and historical risk inputs. |
| SEC / company history | Healthy at provider-summary level | One recorded SEC call | Yes | Overview populated; Reverse Valuation and Reference/Filings requests later failed in the visible UI. |
| OpenAI Copilot | Degraded | Two attempts: one provider error, one completed Quick-profile card | No | The completed card was not reliable enough to support the decision because current strategy and tenor state were absent or mixed. |
| RSS | Healthy | 1/1 recorded call | No | Outside the final evidence chain. |
| External SEC sanity check | Available | [Alphabet Q2 2026 10-Q](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/goog-20260630.htm), filed 2026-07-23 | No | Kept separate from the in-product verdict. It corroborated strong reported growth while showing heavy infrastructure cash demands; it did not repair Gamma's UI or provenance defects. |

The post-journey provider snapshot was taken at approximately 00:21 CEST. The Options surface itself displayed an update timestamp of `Sep 2, 10:15 PM` without an explicit timezone.

## Declared Baseline Constraints

- The audit occurred after regular US market hours, so snapshot/frozen behavior and absent executable bid/ask quality were not treated as product defects by themselves.
- `Auto` market-data mode was preserved. Entitlement-by-contract was not independently established.
- Local portfolio history had only one point; broker-history backfill, multi-session P&L, and restart persistence were outside the evidence available here.
- The audit was research-only. Gamma's deliberate lack of order routing, trading, wallet, or rebalancing authority was not tested as an execution workflow.
- No IV collection session was started; the audit used the loaded cross-sectional surface while the session state remained `Idle`.
- Private Portfolio and Risk context was deliberately excluded from Copilot generation. Only Options and Fundamentals were selected so account-level data would not be transmitted to the external model.

## Research Question And Provisional Thesis

- Question: Does the live GOOGL concentration justify investigating near-term downside protection, and does the visible 79-day options structure offer a credible research-only expression?
- Provisional thesis: Over the next one to three months, downside insurance may be attractive if GOOGL contributes materially more account risk than its portfolio weight and relevant implied volatility is not prohibitively rich versus realized volatility.
- Horizon: 79 days for the candidate option structure; one to three months for the decision.
- Initial signal: GOOGL represented 51.5% of the live exposure on the Risk surface.
- Expected confirmation: Elevated component risk, weak recent portfolio path, liquid/observed option data near the chosen expiry, and 79-day implied volatility near or below medium-horizon realized volatility.
- Falsifier / kill condition: Benign risk contribution; expensive or untrustworthy option data; inability to size the expression to the actual exposure; or materially adverse liquidity/payoff terms.
- Hypothetical expression, if any: Research only, per 100 shares—not an account instruction—the visible 2026-11-20 340/315 put spread, conditional on data-quality and sizing gates.

## Journey

| # | Surface and action | Evidence / visible provenance | Result | Classification |
| ---: | --- | --- | --- | --- |
| 1 | Launch an isolated live-mode Gamma stack and inspect Settings | `mock_mode=false`; TWS process already listening on 7496; read-only boundary active | Runtime came up disconnected, then connected successfully to the existing TWS session | Worked |
| 2 | Open Risk and compute Core for the live account | 100% modeled coverage; 281 aligned observations displayed for a 252D selection; yfinance/IBKR/Gamma context | Portfolio vol was 19.8%, max drawdown -14.7%, 1M return -9.9%, and beta 0.94 to SPY | Worked with degradation |
| 3 | Inspect risk contribution | Live account aggregation; GOOGL weight 51.5%, own vol 31.6% | GOOGL contributed 71.5% of modeled variance, confirming risk concentration beyond capital weight | Worked |
| 4 | Open Portfolio and switch the history control from Growth to Drawdown | TWS connected; quote coverage 3/3; readiness usable; snapshot quotes; one local history point | Live holdings/quotes loaded and identity matched Risk, but the history control had no decision-grade series to analyze | Worked with degradation |
| 5 | Search GOOGL in Fundamentals and inspect Overview | SEC/company history, yfinance fallback, IBKR price context, Gamma-derived ratios | Revenue, profitability, growth, leverage, valuation, and DCF scenarios loaded after roughly 60 seconds | Worked with degradation |
| 6 | Open Reverse Valuation and Reference/Filings | Same active GOOGL identity | Both paths returned `Failed to fetch`; exact reverse inputs were unavailable in the current UI session | Blocked by product defect |
| 7 | Use the Fundamentals → Options handoff | GOOGL persisted across tabs | Options opened with the correct symbol and live IBKR source | Worked |
| 8 | Inspect Surface and change expiry to 2026-11-20 / 79D | Spot 337.76; front ATM IV 30.5%; 8 expiries, 13 strikes, 71/104 cells, line interpolation | The surface loaded, but the fitted 337.5 ATM value of 24.4% contradicted adjacent observed chain IV near 33% | Blocked by product defect |
| 9 | Open Realized vs IV | yfinance realized history and live IBKR front ATM IV | 20D realized 20.8% versus front IV 30.5%; 60D and 120D realized 36.6% and 36.2% versus the same front IV | Worked with degradation |
| 10 | Inspect the 79D Chain and build the Put Spread template | Neighboring 335/340 strike put IV 33.1%/32.7%; some ATM cells N/A; template marks | The 340/315 spread showed a 10.67 debit, 14.33 maximum profit, 10.67 maximum loss, and 329.33 break-even per share | Worked with degradation |
| 11 | Compare the strategy with live exposure | Standard US equity-option multiplier; Portfolio/Risk exposure already observed | No quantity or coverage control could express the hedge without exceeding the live share exposure | Blocked by product defect |
| 12 | Inspect the 79D Implied Probabilities view | Local lognormal RND proxy; line interpolation; 34.90% mass in the visible 325.8–349.8 range | The view rendered, but a visibly spiky fitted distribution inherited the partial/interpolated surface caveat | Worked with degradation |
| 13 | Ask Copilot for a five-bullet research-only verdict using Options + Fundamentals | First Auto attempt returned a typed provider error; one bounded Quick-profile retry completed with 8 sources and 16 warnings | The card omitted visible debit/payoff/79D RV-IV state, mixed a 2D strike-IV observation into the 79D answer, and cited unavailable reverse-valuation inputs | Blocked by product defect |
| 14 | Reinspect Settings and disconnect | IBKR Healthy 86/86, yfinance 20/20, SEC 1/1, OpenAI 1 success/1 error; diagnostics had 50 recent errors | Provider summary captured; Gamma client disconnected cleanly while TWS remained running | Worked |

## Coverage Mission

- Target surface: Options.
- Why it had the highest coverage debt: It is broker-dependent, the roadmap still carries live Options acceptance work, and the user explicitly required a connected TWS session.
- Purpose-specific question: Is medium-horizon GOOGL downside insurance reasonably priced relative to realized volatility, and can Gamma express it coherently without execution authority?
- Provider-backed input: Live IBKR GOOGL chain/surface data, yfinance realized volatility, and IBKR spot context.
- Meaningful action and result: Changed the expiry to 79D, checked observed Chain cells against the fitted Surface, reviewed realized versus implied volatility, built a defined-risk put spread, inspected its payoff and Greeks, and opened the implied-probability slice.
- Classification: Worked with degradation.
- Does this count as deep coverage, micro-mission coverage, or no substantive coverage? Deep coverage; Options was central to the primary thesis and received provider, control, provenance, state, and contradiction checks.

## Thesis Verdict

- Verdict: partially confirmed.
- Thesis confidence: Medium, approximately 0.67.
- Data-quality confidence: Medium-low, approximately 0.55.
- Supporting evidence: GOOGL contributed 71.5% of modeled variance at 51.5% weight; the portfolio's visible 1M return was -9.9%; observed 79-day put IV around the relevant strikes was approximately 32.7%–33.3%, below 60D/120D realized volatility of 36.6%/36.2%; the company overview showed strong growth and margins but a demanding market valuation and downside-heavy Gamma DCF scenarios.
- Contrary evidence: Front 2D ATM IV was 9.6 points above 20D realized volatility; the RV-IV panel did not provide tenor-matched 79D IV; the fitted surface contained a material ATM anomaly; and no live bid/ask-spread or execution-quality evidence was established.
- Falsifier status: Partially met. The need to investigate concentration protection survived, but the exact spread failed the account-sizing and data-trust gates.
- Research-only expression or decision implication: Do not add risk on the basis of this run. A 2026-11-20 340/315 put spread is a useful per-100-share scenario for further research, not a valid account-specific recommendation. Kill it if exact coverage cannot be matched, the 10.67 debit materially worsens at the same width, tenor-matched 79D IV proves materially rich to realized volatility, or the fitted/observed IV discrepancy remains unresolved.

## What Worked

- Gamma preserved GOOGL through the Fundamentals → Options handoff and kept the research boundary read-only.
- Live Portfolio and Risk views made the concentration signal legible without requiring account mutation.
- Options exposed expiry, depth, source, interpolation method, cell/line coverage, realized-versus-implied windows, strategy payoff, Greeks, and distribution assumptions in one coherent workspace.
- Partial option coverage was visible rather than silently presented as a complete chain.
- Copilot's first failure was typed and a single bounded retry recovered provider delivery.
- The external SEC sanity check did not overturn Gamma's central tension: strong operating growth coexists with elevated capital demands, so valuation-sensitive downside remains a legitimate research question.

## Findings

### P1 — GUA-20260903-1: Fitted 79-day ATM IV contradicts adjacent observed chain cells

- Journey impact: The anomaly undermines the surface, Greeks, probability view, and any downstream Copilot claim that treats 24.4% as the 79-day ATM volatility.
- Expected: When the exact 337.5 ATM cell is unavailable, interpolation should remain near same-expiry neighboring observed values or stay N/A with a clear reason.
- Observed: For 2026-11-20 / 79D, the 337.5 call and put cells were N/A. At 335 the call/put IV was 33.3%/33.1%, and at 340 it was 33.1%/32.7%, yet the fitted surface/Greeks state showed 24.4% at 337.5. The same 24.4% value appeared across later expiries.
- Evidence: Direct visual comparison of Options / Chain and Options / Surface at the same symbol and expiry; Surface disclosed line interpolation and 71/104 cells.
- Reproduction: Connect live IBKR, open GOOGL Options, load Max Surface, select 2026-11-20, then compare the 337.5 fitted value with 335/340 Chain IV.
- Classification: product defect.
- Acceptance criteria: Same-expiry interpolation is bounded by valid neighboring observations unless a documented model deliberately extrapolates; every fitted cell exposes observed inputs and method; missing/low-confidence ATM data cannot silently become a repeated cross-expiry constant; automated checks reject discontinuities of this magnitude.

### P1 — GUA-20260903-2: Copilot drops current strategy state and mixes tenors and unavailable sources

- Journey impact: The terminal synthesis could not judge the strategy the user was looking at and introduced apparently source-backed claims that were not available in the visible session.
- Expected: A Copilot run from Options should fingerprint the active symbol, mode, selected expiry, strategy legs, marks, payoff, RV-IV state, and source availability, and should keep tenors explicit.
- Observed: The successful Quick-profile card said debit, payoff, break-even, and 79-day RV-IV evidence were missing even though the strategy and RV-IV panels had displayed them. It substituted a front-expiry 315-strike IV observation for the 79-day question, repeated the suspect 24.4% later-expiry ATM value, and cited exact reverse-valuation inputs after the current Fundamentals route had failed.
- Evidence: One bounded retry completed with 8 sources and 16 warnings; the prior Auto attempt returned a typed provider error.
- Reproduction: Build the GOOGL 2026-11-20 340/315 put spread, visit RV-IV, select only Options + Fundamentals in Copilot, and request a tenor-specific verdict with payoff and falsifier.
- Classification: product defect.
- Acceptance criteria: The source fingerprint includes active Options submode, expiry, legs, quantity, marks, payoff, Greeks, and RV-IV windows; unavailable source blocks cannot be cited as current evidence; tenor identity is retained in every option statistic; the generated card either uses the visible state or explicitly fails before making a verdict.

### P1 — GUA-20260903-3: Strategy Builder cannot size a hedge to live exposure

- Journey impact: The one-click spread cannot become a credible account-specific research scenario because a single standard contract would cover more shares than the live holding.
- Expected: A read-only strategy tool should allow integer contract quantity, state the 100-share multiplier, show exposure coverage, and warn about over- or under-hedging.
- Observed: The Put Spread template created one fixed unit and displayed per-share payoff/Greeks, but offered no quantity or coverage-ratio control and no account-context sizing warning.
- Evidence: Direct comparison of the live exposure from Portfolio/Risk with the Options / Strategies builder. No raw account quantity is retained in this report.
- Reproduction: Open a live holding smaller than one standard contract, hand off the symbol to Options, build the one-click Put Spread, and attempt to match coverage.
- Classification: usability friction.
- Acceptance criteria: Editable integer contracts; explicit multiplier and total premium/payoff; portfolio-context coverage percentage; over-hedge warning; and no expansion of Gamma's read-only/non-execution boundary.

### P1 — GUA-20260903-4: Risk's 252D selection reports 281 aligned observations

- Journey impact: Users cannot tell which date range and sample actually drive portfolio volatility, beta, drawdown, and contribution results.
- Expected: Requested horizon, effective start/end dates, market-calendar basis, raw observations, aligned observations, and dropped rows should reconcile.
- Observed: The visible 252D state reported 281 aligned observations, while other provenance text referenced 281 observations “over 252 days.” The current state did not explain the excess or the effective analysis window.
- Evidence: Risk / Core and its visible provenance after a fresh live compute. This is a recurrence of the analysis-identity problem documented as GUA-20260901-2.
- Reproduction: Connect a live portfolio, choose 252D, compute Core, and compare the control label, aligned-observation count, and provenance text.
- Classification: product defect.
- Acceptance criteria: Show requested and effective horizons separately with exact start/end dates and row reconciliation; persist that analysis identity across Risk cards, exports, and Copilot context; never imply that an unexplained 281-row sample is a 252-observation run.

### P2 — GUA-20260903-5: Provider health stays Healthy while live option requests materially degrade

- Journey impact: Settings communicates full IBKR success at the same time the research surface and diagnostics show partial failures, making the provider badge a weak trust signal.
- Expected: Health should distinguish transport/session connectivity from contract-level request success and surface-level completeness.
- Observed: Settings reported IBKR `Healthy` with 86 calls / 86 successes / 0 unavailable / 0 errors, while diagnostics showed 50 recent errors and the Options surface showed only 71/104 cells and 209/240 lines. Backend evidence included contract-level IBKR request failures during the load.
- Evidence: Post-journey Settings/diagnostics snapshot plus visible Options coverage counters. Sensitive raw provider messages are omitted.
- Reproduction: Load GOOGL Max Surface live, note partial cell/line coverage, then open Settings and compare IBKR usage with recent diagnostics.
- Classification: usability friction.
- Acceptance criteria: Report session, request, and surface-completeness health separately; count or summarize contract-level failures; link a degraded provider badge to affected symbols/expiries; never show 100% success when user-visible requests failed.

## Cross-Tab And State Continuity

GOOGL identity survived the Fundamentals → Options handoff, and the selected 79-day expiry stayed coherent across Chain, Strategy, and Implied Probabilities. Portfolio and Risk agreed on the headline GOOGL exposure. The meaningful break occurred at the Copilot boundary: opening the failed run reported that the shelf no longer matched the persisted source session, and the successful retry did not retain the visible Strategy/RV-IV state. The cross-tab navigation layer therefore worked better than the terminal-context layer.

## Copilot Evaluation

- Grounding: Failed the decision standard. The card omitted current strategy terms and mixed 2D and 79D option evidence.
- Tool/context scope: Only public-ish Options and Fundamentals contexts were selected; private Portfolio/Risk context was deliberately excluded. No unauthorized tools or prohibited capabilities appeared.
- Provider delivery: First Auto attempt returned a typed provider error; one bounded Quick-profile retry completed after roughly 60 seconds.
- Transcript rendering: The completed card rendered a concise five-part verdict with 8 sources and 16 warnings, but the warnings did not prevent unsupported source use.
- Persistence: After the first failure, `Open in Copilot` reported a source-session mismatch rather than promoting a stable shelf item.
- Memo/export behavior: N/A — not exercised, because the terminal result was not trustworthy enough to preserve or export.

## Unsupported And Unverified Boundaries

- No order, trade, rebalance, allocation change, wallet action, or account write was attempted.
- Live bid/ask spread, fill quality, slippage, and executable liquidity were unverified; only marks, open interest, and model outputs were inspected.
- A tenor-matched 79-day realized-versus-implied comparison was unavailable; the panel reused front ATM IV against 20D/60D/120D realized windows.
- Monte Carlo, stress modes beyond Core, and portfolio-history persistence/restart were not exercised.
- Strategy Lab, Macro, Prediction Markets, Crypto, Commodities, and Sealanes were not substantively exercised.
- Copilot with private account contexts was intentionally unverified.
- Fundamentals Reverse Valuation and Reference/Filings were blocked in this run; their current-session values remain unverified.

## Coverage Ledger Update

- Surfaces credited this run: Portfolio, Risk, Fundamentals, and Options.
- Coverage depth credited: Deep use for all four; Options was the designated coverage target.
- Surfaces still carrying the highest debt: Strategy Lab, Macro, Prediction Markets, Crypto, Commodities, Sealanes, and a trustworthy provider-native Copilot terminal pass.
- Environment/provider qualification attached to the credit: IBKR-integrated live for Portfolio, Risk, and Options; mixed live IBKR + SEC + yfinance for Fundamentals. Each credit retains its degradation or defect note in the ledger.

## Scorecard

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | 8/10 | Live account, risk, SEC/company fundamentals, historical volatility, option chain/surface, payoff, Greeks, and probability data were available. |
| Data depth and drill-down | 8/10 | The journey reached risk contribution, valuation, expiry/strike detail, RV-IV, strategy payoff, and distribution views. |
| Data trust and provenance | 5/10 | Source labels and coverage counters were strong, but the fitted-IV anomaly, horizon mismatch, failed Fundamentals routes, and provider-health contradiction were material. |
| Analytical tooling | 8/10 | Risk attribution and the Options suite supported a real thesis test without execution authority. |
| Cross-tab continuity | 8/10 | GOOGL handoff and Options submode state worked; Copilot context did not. |
| Recovery and state resilience | 6/10 | A bounded Copilot retry restored delivery, but not trustworthy state or shelf continuity. |
| Agent drivability | 8/10 | Primary controls were reachable and the journey completed without privileged mutation. |
| Speed to insight | 6/10 | Options became useful quickly, while Risk, Fundamentals, and Copilot each required material waits and Fundamentals exposed late failures. |
| Overall | 6.8/10 | Gamma generated a valuable partial verdict, but three P1 defects prevented a defensible account-specific hedge conclusion. |

## Cleanup And Residual State

- Gamma's dedicated audit client was disconnected from IBKR after evidence capture.
- The pre-existing TWS process remained open and listening on port 7496.
- The audit-launched frontend and backend were stopped; ports 5173 and 8000 were closed.
- The in-app audit browser tab was closed.
- No product code, tests, configuration, roadmap, or account state was modified.
- Pre-existing worktree changes were preserved.
- The isolated temporary portfolio-history directory was left in place rather than destructively deleting an automatically generated path. It contains no broker backfill from this run.
- A public-context Copilot conversation may remain in Gamma's default local shelf because the audit did not have an unambiguous safe deletion path; private Portfolio/Risk contexts were not included.

## Audit-Only Follow-Up

1. **GUA-20260903-1 — fitted IV correctness:** bound interpolation to same-expiry observations, expose per-cell lineage, and reject repeated/discontinuous ATM values. Accept only after a live chain/surface retest reconciles the selected ATM with neighboring cells.
2. **GUA-20260903-2 — Copilot terminal grounding:** include active Options strategy/RV-IV state and source availability in the context fingerprint, enforce tenor identity, and prevent unavailable blocks from supporting claims. Accept only when a repeated prompt reproduces the visible debit, payoff, expiry, and correct tenor.
3. **GUA-20260903-3 — account-matched strategy sizing:** add quantity, multiplier, total payoff, coverage ratio, and over-hedge warnings while preserving read-only behavior. Accept with a live sub-100-share holding and no execution controls.
4. **GUA-20260903-4 — Risk analysis identity:** reconcile requested/effective windows and observations everywhere the run is shown or handed off. Accept only when the displayed 252D state has auditable dates and row counts.
5. **GUA-20260903-5 — provider health semantics:** separate connection health from request and surface-completeness health. Accept when contract-level failures produce a visible degraded state that matches diagnostics.

This audit made no implementation changes and does not mark any finding fixed.
