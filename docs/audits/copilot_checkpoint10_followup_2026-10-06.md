# Copilot Checkpoint 10 follow-up — 2026-10-06

**Decision: partial acceptance; not certified.** The market-open direct Options Operator gate now passes. Native screen-reader acceptance and exact reconciliation of the two historical charge gaps remain external evidence requirements. Keep Copilot at approximately 94% until the complete gate passes. This report supplements [October 5 acceptance](copilot_checkpoint10_acceptance_2026-10-05.md), preserving its successful LMT, portfolio, shock, adaptive, approval/recovery and isolated Script evidence.

## Architecture and scope

Reviewed official OpenAI [function calling](https://developers.openai.com/api/docs/guides/function-calling), [agent runtime comparison](https://developers.openai.com/api/docs/guides/agents) and [pricing](https://developers.openai.com/api/docs/pricing) on October 6. Keep the user-selected `gpt-6.1-sol`, custom Responses loop and optional SDK comparison. Gamma remains the authority for schemas, permissions, tools, recovery, persistence and approvals. No new execution or trading authority, framework migration or durable mutation family was introduced.

The existing TWS session on port 7496 was available during regular US market hours. Reused the prior isolated `output/checkpoint10-live/` stores and guarded $5 task ledger with an additional reservation for previously recorded Script/summary allowances. Raw provider payloads remain local and excluded from Git. Unrelated `.env.example`, website, PRODUCT.md and .impeccable changes were preserved.

## Completed work

| Item | Result and evidence |
|---|---|
| Direct Options acquisition and computation | **Passed live.** SPY underlying historical volatility 0.10107934138843605 is now obtained from the stock subscription's generic tick 104. The surface/API/tool retain this field separately from contract fields. [IBKR documents tick 104 as underlying-stock 30-day historical volatility](https://interactivebrokers.github.io/tws-api/tick_types.html); Gamma does not invent its estimator or dates. Every comparison labels the backward 30-day basis and its mismatch with each forward expiry. |
| Actual Operator continuation | **Passed live**, run `checkpoint10-options-open-final-20261006-run`, 61.36s end-to-end. Unloaded SPY inspection followed by the authorized comparison with exact `symbol=SPY`, `max_expiries=4`, `depth_preset=compact`, `market_data_mode=live`. Final synthesis cites returned sources and computes observed premiums/ratios; missing rows remain unavailable. |
| Analytical result | October 6 ATM IV 13.4919%, historical volatility 10.1079%, premium +3.3839 percentage points, ratio 1.3348. October 13 IV 9.5480%, premium −0.5599 points, ratio 0.9446. October 20 and November 6 comparison IVs were missing. Earlier inspection values were a different snapshot and were explicitly not substituted. The comparison had 12 observed/12 interpolated cells and discloses 50% interpolation and missing quote-age/spread assessment. This is a provider-backed research comparison, not a horizon-matched forecast or executable-price certification. |
| Temporary owning-tab result | **Passed materialization and restart.** `work_40ba4bee5ed967eb69471a16` materializes into Options / Realized vs IV, retains exact inputs/output/warnings after backend restart, expires October 13, and has `materialization.durable=false`. No option strategy, DCF or account mutation was created. |
| Bounded acquisition latency | Unloaded Options had a 2.5s acquisition wait and inherited a 12s plan guard, causing an actual live failure before computation. Operator surface acquisition now allows 20s; plans containing IV with a live loop allow 90s. Tool/provider-count, cancellation and authority bounds remain. The successful case took 61.36s including synthesis; this is one observation, not an SLA or distribution. The earlier 33.31s unsuccessful attempt is retained and not counted as a pass. |
| Entity identity | Plain UI/ATM acronyms no longer become competing stock candidates. Explicit `$UI` and `ticker ATM` retain their meaning. The initial ambiguity stop is retained as failed acceptance evidence. |
| Oil delivery labels | **Passed regression and live TWS retest.** Prefer IBKR ContractDetails.contractMonth over the last trading date; expiration remains separate. November delivery expires October 20; December delivery expires November 20; January delivery expires December 21. Nodes retain IBKR provenance. Persist contractMonth in the contract cache and version its key to avoid old lossy records. Historical raw evidence is not rewritten; delayed-node/roll-proxy limitations remain. |
| EIA inventory changes | **Passed regression and live EIA retest.** Sort observations chronologically before computing changes. All 11 live series contain 260 points with zero mismatches between point change and preceding chronological level. Latest crude/gasoline/distillate changes are +0.922/−1.684/−2.251 million barrels. This validates normalization, not external forecasts or inventory-surprise methodology. |
| Future API usage accounting | `GAMMA_OPENAI_USAGE_AUDIT_DIR` enables atomic per-attempt records for Copilot streaming/nonstreaming/entity proposals, Fundamentals filing summaries, Script Responses and Script container creation. Records precede transport, preserve response identity, raw provider usage and service tier, and record uncertain cancellation/transport loss as unknown charge. They omit prompts, output, credentials and error messages. SDK automatic retries are disabled; Gamma-owned bounded retries remain visible. Fundamentals summary usage also survives store/API replay; Script retains the complete SDK usage object and container identity/size. |

## Release verification

Repository-wide backend: **784 passed / 1 opt-in live Script test skipped**, three existing EdgarTools deprecation warnings, 376.52s. Final affected regression suite: **105 passed**, covering checkpoint discoveries, commodity providers and isolated Script runtime, including final accounting and nonfinite-data refinements. The preceding full run passed 777/1; the current full run supersedes it, with final focused refinements verified separately.

Frontend: **461 tests / 61 files passed**; TypeScript typecheck, production build and desktop check passed. **18 affected browser journeys passed** across Copilot recovery, Options continuity and DCF editing. No frontend visual behavior changed in this follow-up; October 5 desktop/narrow/reduced-motion evidence remains applicable. Existing Surface3D/IV SVG and bundle-size warnings remain disclosed.

Deterministic Operator eval: **31 outcomes passed**, average **0.9092741935483871**. No framework/model promotion. The opt-in paid Script runtime test was not repeated; October 5 live runtime evidence remains valid, with affected runtime regression checks rerun here.

## Cost and local evidence

October 6 added **6 completed Responses attempts**, **$0.0330871** using current standard Sol token rates. The attempts include the unsuccessful timing run and the final successful run. All six have provider-reported usage and matching audit records. No new filing-summary or Script request occurred. Total completed model/runtime measurement across both days is **$0.8998712**; including the original uncertain cancellation reservation and unmeasured summary allowance, conservative task accounting is **$1.1178862**, below the existing $5 cap. This is not an invoiced billing reconciliation.

Local evidence: `options-open-final-20261006-request.json`, `*-events.ndjson`, `*-session.json`, `options-direct-open-long-20261006.json`, `options-open-materialized-20261006.json`, `usage.json`, and `usage-audit-20261006/*.json` under `output/checkpoint10-live/`; verification logs under `output/checkpoint10-followup-*`. No API key is included.

Additional live evidence: `options-open-restart-20261006.json`, `curve-open-20261006.json` and `inventories-open-20261006.json`. The task-only backend was restarted for replay verification and stopped at completion, matching the initial state in which no backend listened on port 8000. Final checkpoint regressions also cover delivery-month cache roundtrip and preserve the summary record's positional compatibility.

## Exact remaining certification evidence

1. **Native assistive technology:** no active NVDA/Narrator process and no enabled native accessibility/audio control surface were available. Browser semantics and fixture tests remain useful, but actual announcements and focus comprehension are unverified. Use the checklist below with a human operating a supported native reader; record reader/browser/version, actions, spoken output and findings before signing off.
2. **Historical billing:** the October 5 cancelled request lacks terminal usage; the old filing summary did not persist usage. Provider response storage was disabled and no authorized account billing connector/admin credential is available here. New instrumentation cannot recover those historical charges. Match them against account billing evidence; keep the unknown reservation/allowance distinct from measured cost until then.

Provider measurements, the historical-volatility estimator/date limitation, partial IV coverage and the absence of an approved numerical latency SLA remain explicit limitations. No delivery-specific oil conclusion is certified solely by fixing labels. Fixtures are not counted as live provider success.

### Native reader acceptance checklist

- Open a new chat; confirm named composer, context selector and Agent/Operator controls, logical keyboard order, and explicit authority announcement.
- Submit Agent and Operator requests; confirm streaming status without disruptive repeated transcript announcements, then navigate final claims and source controls and return to the transcript.
- Move shelf → dedicated tab → source tab; verify focus location and retained chat/evidence identity are comprehensible.
- Stop, reconnect and Retry; verify terminal status, retry behavior and original retained evidence are announced distinctly.
- Pause a DCF proposal, restart, then separately approve and reject isolated test proposals; confirm the exact diff, original run continuation and result are understandable, with no duplicate effect.
- Repeat at narrow width with reduced motion, and first-run/unconfigured/degraded states. Record pass/fail for every journey and repair findings before certification.
