# Gamma Usability Findings — 2026-09-04

Date: 2026-09-04 01:54 CEST<br>
Audience: Gamma product, research UX, and Copilot owners<br>
Mode: IBKR-integrated<br>
IBKR state: connected live<br>
Runtime: audit-launched frontend and backend, visible browser UI<br>
Commit / branch / dirty state: `37264f59d4541fa4c6bfc349f6fe28df4d0da9c4` / `main` / clean before audit<br>
Data context: live provider-backed Gamma session; yfinance public history, IBKR/TWS context, Treasury/FRED macro context, prediction venues, and RSS discovery<br>
Scope: SITREP discovery, Research Operator from the Copilot drawer, and Strategy Lab Script mode. No orders, trades, rebalancing, account writes, or product-code changes were made.

## Outcome

The provisional QQQ-minus-SPY relative-strength thesis is indeterminate, not investable: SITREP supplied a plausible discovery signal, but the Research Operator was blocked by a Gamma-generated invalid OpenAI tool name before it could acquire or materialize the requested Script workflow, and Script safe preview explicitly did not execute Python (`executed=false`). The provider gate passed for the live read-only session, and the direct Script workflow completed with an immutable Rev 1, a 756-day daily QQQ snapshot, typed outputs, and retained provenance. The highest-priority result is a P1 Research Operator defect that prevents the requested closed loop; the Script boundary itself was honest and safe.

## Environment And Provider Matrix

| Provider / subsystem | State | Freshness / mode | Used in verdict | Notes |
| --- | --- | --- | --- | --- |
| IBKR / TWS | Healthy, connected | Live read-only session | Discovery context and provider gate | 14 calls, 14 successes in the audit backend; no account identifier retained in this report. |
| yfinance | Healthy | Public historical data; SITREP labeled historical/live-ish and approximately 2 hours old | Initial QQQ/SPY signal and Script input | 5 calls, 5 successes. Gamma labels it as an unofficial public source rather than institutional quote truth. |
| Gamma research market-data export | Completed | QQQ daily, 756-day lookback; retrieved 2026-09-03 23:52:36 CEST | Script input snapshot | One 28,027-byte CSV; manifest SHA-256 prefix `a490db0039f6`. The UI exposed Gamma's provider boundary, while the manifest did not identify the upstream yfinance source directly. |
| OpenAI Copilot / Research Operator | Degraded | One failed request and one successful empty-context retry | Operator evaluation | 2 calls, 1 success, 1 error. The failed request returned HTTP 400 because a tool name violated OpenAI's allowed name pattern. |
| Treasury/FRED macro | Healthy | Historical macro context; mixed with IBKR macro/FX context | Contrary-context check | Rates moved higher over the displayed 3M window, increasing the risk that QQQ strength is duration/rate exposure rather than persistent spread alpha. |
| Script runtime | Available, safe preview | `mock_safe_preview`; no network; code execution disabled | Script execution boundary | Run completed in 0.00 s, with six typed outputs and one warning; it did not calculate strategy returns. |

## Declared Baseline Constraints

This audit stayed inside Gamma's read-only research boundary. The Script runtime was configured as `mock_safe_preview`, and Gamma clearly declared that Python was persisted and hash-bound but not executed, with no network, host, provider, account, wallet, or trade-tool access. Therefore actual source execution, dynamic multi-asset computation, and live trading behavior were outside this run. The expression below is hypothetical research only.

## Research Question And Provisional Thesis

- Question: Does a 1.0x long QQQ / 1.0x short SPY relative-strength expression produce persistent positive excess return with controlled drawdown over roughly three years of daily history?
- Provisional thesis: AI/growth beta may retain relative strength against broad beta, allowing a market-neutral QQQ-minus-SPY spread to outperform when leadership persists.
- Horizon: Initial 3-year daily test; monitor over 1–3 months.
- Initial signal: SITREP's latest displayed day showed Nasdaq/QQQ up approximately 1.4% versus S&P/SPY up approximately 1.1% on 2026-09-03. This is a discovery signal, not confirmation.
- Expected confirmation: positive cumulative and annualized spread return, positive Sharpe, controlled volatility and drawdown, positive trailing 12-month behavior, and low residual SPY beta/correlation.
- Falsifier / kill condition: trailing 12-month spread return remains negative, drawdown exceeds 10% hard (5% preferred tolerance), beta/correlation is not meaningfully neutral, or the workflow cannot prove that the exact immutable source and input snapshot were used.
- Hypothetical expression, if any: long QQQ 1.0x / short SPY 1.0x; no trade or account action implied.

## Journey

| # | Surface and action | Evidence / visible provenance | Result | Classification |
| ---: | --- | --- | --- | --- |
| 1 | Connect Gamma to the isolated audit backend and IBKR/TWS | Settings showed Connected; read-only boundary remained active; provider gate reported IBKR healthy | Live discovery session established without account writes | Worked |
| 2 | Load SITREP and frame the hypothesis | Visible source/freshness labels; QQQ/Nasdaq approximately +1.4% versus SPY/S&P approximately +1.1% on the latest displayed day; rates mixed and higher | Useful cross-asset discovery, but delayed/mixed-source context | Worked with degradation |
| 3 | Open Copilot and select Research Operator | Operator context opened from SITREP with an explicit prompt requesting a Script draft, bounded run, metrics, contrary evidence, and falsifier | Drawer and prompt entry worked | Worked |
| 4 | Run Research Operator | Operator trace showed the closed-loop plan, then OpenAI HTTP 400: invalid `tools[0].name` pattern; no Gamma tool call, script draft, or materialization occurred | Intended closed loop stopped before research actions | Blocked by product defect |
| 5 | Retry the failed Operator action | The first accepted run had cleared the composer and no visible persisted Retry control was available; the second click submitted no prompt | Model returned a ready report from 0 observations and no hypothesis, with repeated progress events and no tool calls | Blocked by product defect |
| 6 | Create a new audit-labeled Script from the editor | Title `AUDIT 2026-09-04 QQQ minus SPY`; immutable Rev 1; source SHA-256 prefix `e9f715604411` | Script creation and revision binding worked | Worked |
| 7 | Prepare the Gamma input snapshot | Strategy Lab Script showed Equity history / QQQ / Daily / 756; one immutable `qqq-prices.csv`, 28,027 bytes; manifest SHA-256 prefix `a490db0039f6` | Provider-backed input acquisition and manifest creation worked; upstream attribution was indirect | Worked with degradation |
| 8 | Run Script safe preview | Status COMPLETED; log, metric, table, image, file, and warning outputs; table reported the exact source hash, input hash, one input file, and `executed=false` | Typed-output and safety contract completed honestly; no performance metrics were computed | Worked with degradation |
| 9 | Switch Script → Composer → Script | Rev 1, editor text, selected snapshot, completed run, output list, and recovery counts remained visible after returning | Cross-mode state retained | Worked |
| 10 | Inspect retained Script run and runtime boundary | Stored run remained selectable; runtime showed `mock_safe_preview`, network Disabled, code execution Disabled, cancellation Not supported; local run artifact retained | Audit trail and safety disclosure were available | Worked |

## Coverage Mission

- Target surface: Strategy Lab Script mode, with Research Operator as the requested orchestration path.
- Why it had the highest coverage debt: the prior audit explicitly left a provider-backed Script run unverified, and the Operator-to-Script closed loop had not been exercised live.
- Purpose-specific question: Can Gamma take a public, provider-backed relative-strength question, let Research Operator acquire and materialize a bounded Script, and retain a reproducible source/input/output trace without execution authority?
- Provider-backed input: live Gamma QQQ daily history export, 756-day lookback, plus SITREP public QQQ/SPY discovery context.
- Meaningful action and result: direct Script creation, immutable input binding, safe preview execution, output inspection, export request, and mode-switch recovery all completed; Operator orchestration failed before any tool action.
- Classification: Script workflow `Worked with degradation`; Research Operator `Blocked by product defect`.
- Does this count as deep coverage, micro-mission coverage, or no substantive coverage? Deep coverage for Strategy Lab Script; substantive blocked coverage for Research Operator.

## Thesis Verdict

- Verdict: indeterminate.
- Thesis confidence: low-to-medium as a research question; the initial relative-strength observation is real in the displayed discovery context but is not a backtest result.
- Data-quality confidence: medium for the bounded QQQ snapshot and low-to-medium for the broader discovery context because sources were mixed and delayed.
- Supporting evidence: latest displayed Nasdaq/QQQ performance exceeded S&P/SPY; Gamma successfully captured a provider-backed QQQ daily snapshot and bound it to an immutable manifest.
- Contrary evidence: 2Y, 5Y, and 10Y rates were all higher over the displayed 3M window, so the apparent QQQ lead may be regime- or duration-sensitive; the Script source was not executed and produced no return, Sharpe, volatility, or drawdown statistics.
- Falsifier status: not testable in this run. The required statistics and exact two-asset executable calculation were unavailable in safe-preview mode.
- Research-only expression or decision implication: keep the QQQ-minus-SPY idea as a watchlist hypothesis only. Do not treat this audit as a trade recommendation or account instruction.

## What Worked

- The live read-only provider gate was healthy and the app stayed within the execution boundary.
- The Script UI made the safety boundary unusually clear: source persistence and hashing were visible, while non-execution, no-network, and no-app-state access were explicit.
- Immutable revision/input binding was traceable in the visible table output and retained run artifact.
- Typed outputs included log, metric, table, image, file, and warning forms rather than a single opaque response.
- Script state survived a mode switch and the stored run remained recoverable.
- Gamma did not fabricate thesis metrics when the configured runtime could not execute source.

## Findings

### P1 — GUA-20260904-1: Research Operator sends OpenAI-invalid tool names

- Journey impact: a valid research request could not reach Gamma's authorized Script tools, so the requested Operator-to-Script closed loop never started.
- Expected: Gamma's server-owned registry should map internal action identifiers to provider-compliant tool names while preserving the internal identifier and audit trace.
- Observed: the Operator trace stopped after planning with OpenAI HTTP 400: `Invalid 'tools[0].name' ... expected ... ^[a-zA-Z0-9_-]+$`. The internal Gamma action identifiers visible in source and plan include dotted names such as `strategy_lab.draft_research_script`; no Gamma tool call was recorded.
- Evidence: visible Operator error card and trace artifact; backend recorded one `openai_copilot` error for `copilot.stream_research_operator` at approximately 2026-09-03 23:48:54 CEST; `executed_steps=[]`, `tool trace count=0`, `external provider calls used=0` in the synthesized error report.
- Reproduction: connect live read-only; open Copilot from SITREP; select Research Operator; submit the explicit QQQ/SPY Script request. The run returns the invalid-tool-name error before executing the planned actions.
- Classification: product defect.
- Acceptance criteria: the same request reaches the authorized Script action registry; OpenAI receives only compliant tool names; the trace preserves the Gamma action IDs; the run either materializes and runs a bounded Script or reports a truthful provider/runtime constraint with zero ambiguous partial state.

### P2 — GUA-20260904-2: Operator recovery loses the original prompt

- Journey impact: after a provider failure, the user cannot reliably retry the intended research task from the visible drawer.
- Expected: the original prompt, plan, error, and a clearly labeled Retry action should remain available; a retry should not silently submit an empty context.
- Observed: after the failed accepted run, the composer was cleared and no persisted Retry control was visible. Clicking the available Run Operator control again produced a ready report from 0 validated observations, stated that no hypothesis could be evaluated, and generated repeated progress steps without a tool call.
- Evidence: visible second-run card `Insufficient research specification`; final report `model_final_output`, `source_count=0`, `tool trace count=0`, `external provider calls used=0`, and warning that no prompt was supplied.
- Reproduction: repeat the P1 flow, wait for the provider error, then use the remaining Run Operator control without re-entering the prompt.
- Classification: usability friction with product-state defect.
- Acceptance criteria: preserve the prompt and plan across failure; expose Retry with the original payload; prevent empty-context retries unless the user explicitly chooses them; cap or coalesce repetitive progress events.

### P2 — GUA-20260904-3: Safe preview cannot answer the Script thesis, although the limitation is disclosed

- Journey impact: a user can complete a Script run and see a green COMPLETED state without receiving the requested investment-performance statistics.
- Expected: the UI should make the distinction between a provenance/safety preview and an analytical execution result unmissable at the action point, and provide a supported next step when an execution-capable runtime is unavailable.
- Observed: the run completed with six typed outputs, but its table explicitly reported `executed=false`; the generated chart was labeled a deterministic placeholder; no return, Sharpe, volatility, or drawdown was produced.
- Evidence: visible RUNTIME BOUNDARY `MOCK / SAFE PREVIEW`, `Run safe preview`, warning output, runtime `mock_safe_preview`, and retained run contract `research-script-run.v1` with `executes_source=false`.
- Reproduction: create any Script revision, prepare a Gamma snapshot, and click Run safe preview under the current configured runtime.
- Classification: data/analytical coverage gap; not a safety defect.
- Acceptance criteria: retain the current disclosure; additionally show a prominent `preview only — not an analysis` result state and, when policy/configuration permits, expose a separately named bounded execution runtime or a clear setup path. Never label deterministic placeholder outputs as strategy results.

### P2 — GUA-20260904-4: Script input provenance stops at Gamma's adapter

- Journey impact: a researcher can reproduce the immutable manifest and QQQ snapshot hash, but cannot tell from the Script UI whether the data came from yfinance, IBKR, or another upstream source.
- Expected: each exported input should show the upstream provider, retrieval time, symbol, frequency, lookback, transformation, and any freshness warning.
- Observed: the manifest exposed `provider_id=gamma_research_market_data`, `source_kind=gamma_state`, QQQ, daily, 756 days, and retrieval time; the provider ledger separately recorded the successful upstream request as yfinance. The UI did not join these identities.
- Evidence: manifest `research-script-input.v1`; live provider usage recorded yfinance success for `research_history.load_history` at the same retrieval time.
- Reproduction: in Script mode prepare a Gamma equity-history snapshot and inspect the visible prepared file and run provenance.
- Classification: data trust/provenance gap.
- Acceptance criteria: surface upstream provider identity and source freshness in the input manifest and output provenance, while preserving the adapter and immutable hashes.

## Cross-Tab And State Continuity

The SITREP-to-Copilot context handoff opened the Operator with SITREP context, but the intended Operator-to-Strategy-Lab materialization was blocked before any Gamma action. Direct navigation to Strategy Lab Script worked. Within Strategy Lab, switching Script to Composer and back preserved the audit Script revision, QQQ snapshot, run, outputs, and recovery counts. The existing Composer draft and stale inbound Bitcoin handoffs were observed but not changed, dismissed, or resolved.

## Copilot Evaluation

- Grounding: the initial Operator prompt was specific and hypothetical, with symbols, horizon, expected statistics, contrary evidence, and falsifier. The failed run did not reach a research tool, so no grounded answer was produced.
- Tool/context scope: the planned Gamma actions were visible, but the provider request rejected the tool schema before tool execution. The empty retry correctly executed zero actions but returned a misleadingly ready-shaped generic report.
- Provider delivery: OpenAI Copilot was degraded at the end of the audit: one successful request and one failed request. The failure was a Gamma request-construction defect, not a provider outage.
- Transcript rendering: planning, warning, and report artifacts were rendered, but the retry generated repetitive progress events and did not keep the original prompt visible.
- Persistence: the Script artifact and run persisted; the Operator prompt did not remain available for retry.
- Memo/export behavior: the Script run exposed an Export auditable run bundle action and retained output artifacts. No Operator-derived thesis memo was produced.

## Unsupported And Unverified Boundaries

- Actual Python execution and performance calculation: unsupported by the configured `mock_safe_preview` runtime in this audit.
- Two-asset QQQ/SPY Script computation: unverified; only QQQ was bound as an immutable Script input, and no valid Operator materialization occurred.
- A confirmed or rejected investment thesis: unverified; the result is indeterminate by design of the evidence available.
- Trading, order routing, rebalancing, account writes, and wallet actions: outside scope and remained unavailable.
- The existing Strategy Lab Backtest, Regime Stress, Risk handoff, and saved-run flows were not re-run in this targeted Operator/Script mission.

## Coverage Ledger Update

- Surfaces credited this run: Strategy Lab Script (deep coverage); SITREP (supporting discovery); Research Operator (substantive blocked coverage).
- Coverage depth credited: one deep Script mission and one blocked Operator mission.
- Surfaces still carrying the highest debt: Research Operator closed loop, executable Script analytics, and Copilot recovery/persistence.
- Environment/provider qualification attached to the credit: IBKR-integrated live read-only session; public yfinance history; Script `mock_safe_preview`; mixed-source SITREP with disclosed freshness/degradation.

## Scorecard

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | 7/10 | SITREP covered equities, indices, FX, rates, commodities, predictions, and news; several sources were mixed or delayed. |
| Data depth and drill-down | 5/10 | QQQ snapshot depth and manifest worked; the two-asset thesis and Script calculations could not be drilled through. |
| Data trust and provenance | 6/10 | Hashes, retrieval time, source labels, and warnings were strong; upstream Script-provider identity remained indirect. |
| Analytical tooling | 4/10 | Script lifecycle and typed outputs worked, but safe preview produced no strategy analytics. |
| Cross-tab continuity | 5/10 | Script state survived mode switching; Operator materialization and retry context failed. |
| Recovery and state resilience | 5/10 | Script recovery was good; Operator prompt persistence and retry behavior were weak. |
| Agent drivability | 3/10 | Research Operator accepted a well-specified task but failed before authorized actions due to invalid tool schema. |
| Speed to insight | 4/10 | Discovery loaded with delay/degradation; direct Script setup completed, but Operator failure prevented the intended shortcut. |
| Overall | 5/10 | Safe, honest Script boundary and strong immutable artifacts, offset by the blocked Operator loop and absent executable thesis metrics. |

## Cleanup And Residual State

No product code, tests, configuration, roadmap, or user artifacts were edited. The audit used an isolated local backend/frontend and audit-only session token. A new script titled `AUDIT 2026-09-04 QQQ minus SPY`, its Rev 1, one QQQ input snapshot, one completed safe-preview run, and retained safe-preview output artifacts remain in the isolated audit history directory for reproducibility. The pre-existing TWS process was not stopped or reconfigured; the audit's dedicated Gamma client session was isolated from the user's existing app instance. Existing Composer draft fields and stale handoffs were left unchanged.

## Audit-Only Follow-Up

1. P1 / GUA-20260904-1: normalize provider-facing tool names and preserve Gamma action-ID mapping; add a live regression for the exact Operator-to-Script request.
2. P2 / GUA-20260904-2: persist the Operator prompt and expose a real Retry action; prevent empty retries and bound progress-event volume.
3. P2 / GUA-20260904-4: join upstream provider identity and freshness to Script input manifests and output provenance.
4. P2 / GUA-20260904-3: keep safe-preview disclosure, but distinguish preview completion from analytical completion and document/enable the next supported execution path.
5. Re-run the same QQQ-minus-SPY thesis only after the Operator loop is fixed and an execution-capable, policy-bounded Script runtime is explicitly available; require reported returns, volatility, Sharpe, max drawdown, trailing behavior, source/input hashes, and contrary evidence before changing the thesis verdict.
