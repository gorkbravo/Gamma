# Gamma Live-Provider Regression Pass — 2026-07-24

Date: 2026-07-24

Mode: targeted live-provider regression

Data: live TWS on port 7496, `MOCK_DATA=false`, market-data mode `auto`

Scope: Portfolio, Options, Commodities, Strategy Lab → Risk, Copilot, and provider diagnostics

## Outcome

The live provider layer is broadly functional. TWS accepted a dedicated Gamma audit connection, live futures and options data built successfully, signed Strategy Lab books reached Risk without account-position leakage at the API contract, and Copilot completed two OpenAI-backed requests.

The initial pass confirmed five findings. The same-day remediation pass implemented all five, added deterministic regression coverage, passed the complete backend/frontend gates, and repeated the permitted live/browser checks with a dedicated TWS client.

| Surface | Result | Evidence |
| --- | --- | --- |
| TWS connection | Pass | `/system/status` reported `Connected` on a dedicated audit client id. |
| Portfolio snapshot | Fixed and live-verified | The maximum accepted 10-second quote budget returned six positions and account totals in 11.01s. The partial snapshot retained its bounded quote warning, and an immediate account-subscribe request completed without a false unresponsive-thread result. |
| Options / XLE | Pass at API and UI boundaries | The live session reached `Running (XLE, Live)` and the Options workspace rendered the provider-backed XLE surface with 21 points. |
| Commodities / WTI | Fixed and live/browser-verified | A fresh IBKR WTI quote with a dated prior settlement retained price, change, change percent, and both source timestamps after row drill and immediate non-force reload. The reload identified the source honestly as `ibkr_cached`. |
| Strategy Lab | Pass | XOM and AMD each resolved to 938 yfinance daily return points; the signed 0.6 / -0.4 book validated with 938 aligned observations. |
| Strategy Lab → Risk | Fixed and browser-verified | Risk remained explicitly scoped to `research_book`, retained aggregate-book metrics, rendered separate signed XOM and AMD contribution rows, and showed zero account movers or concentration rows. |
| Copilot streaming | Pass at API and UI boundaries | The follow-up streamed OpenAI run reached one terminal result and rendered a visible sourced research card in the Copilot transcript. |
| Provider diagnostics | Fixed and live-verified | `/system/provider-usage` recorded the follow-up as one successful `openai_copilot` call at `copilot.stream_research_card`; OpenAI Copilot health became `Healthy`. |

## Findings

### P1 — Fresh WTI change disappears on drill/cached reload

This reproduces GUA-20260708-5 against a live TWS session.

- Fresh request: WTI 92.10, change 5.27, change percent 0.060693, provider `ibkr`, prior timestamp 2026-07-22.
- Immediate non-force request: WTI 92.10, change `null`, change percent `null`, provider `ibkr_cached`, prior timestamp `null`.
- The cached response explains that the headline change is intentionally `N/A`, but this still removes the live number the analyst just selected.

Acceptance: drill interactions should reuse the most recent workspace payload, or the fresh quote plus dated prior-close reference should be cached together.

### P1 — Successful OpenAI calls are attributed to `unknown`

Two live Copilot requests completed successfully and persisted ready cards, but `/system/provider-usage` showed:

- `unknown`: 2 calls, 2 successes;
- `openai_copilot`: 0 calls, `Not requested`.

This makes the beta-facing provider diagnostics materially misleading.

Acceptance: the OpenAI streaming provider must register and record calls with provider id `openai_copilot`, including operation, duration, model/run metadata where safe, and terminal status.

### P2 — Portfolio quote timeout can exceed the fixed worker budget

`/portfolio/snapshot?quote_timeout_seconds=10` returned after about 20 seconds with `IB task timed out`, no positions, and no account totals. The queued IB task continued after the API returned; an immediate account-subscribe request then reported the IB thread as unresponsive.

The same live account returned normally with `quote_timeout_seconds=2` in 12.63 seconds.

Acceptance: either cap the public quote timeout to fit the full snapshot worker budget, derive the worker timeout from the requested quote timeout plus bounded account/position overhead, or cancel/expire timed-out queued tasks so later diagnostics do not report a false thread failure.

### P2 — Research-book contribution remains aggregate-only

The Risk contract correctly isolated the Strategy Lab book from the live account, but contribution output contained only:

- `STRATEGY_BOOK`
- weight 1.0
- variance contribution 1.0

Acceptance: preserve the validated Strategy Lab leg identities and aligned leg return streams through the handoff so Risk can show XOM and AMD contribution rows while retaining the aggregate book metrics.

### P2 — Repeated raw IBKR contract errors remain noisy

The successful Portfolio snapshot included five repeated `IBKR error (200): No security definition has been found for the request` warnings, plus missing snapshot quotes for LMT and FOUR.

Acceptance: deduplicate identical provider errors, associate them with the affected symbol/contract when known, and keep the human-facing summary concise.

## Remediation Status

### Closed — Fresh WTI change disappears on drill/cached reload

The curve cache now stores an explicit headline context containing the exact current provider quote, current source timestamp, dated prior close/settlement, prior source timestamp, front contract, and source provider. Restoration requires that pair to match the cached front node and contract coherently. Missing or mismatched references still produce `N/A`; unrelated historical curve snapshots are never promoted to prior close.

Regression coverage includes fresh-to-cached retention, durable cache restoration after service restart, missing prior reference, and mismatched current timestamps. The live/browser follow-up retained the WTI price, change, change percent, and dated prior reference through row selection and an immediate non-force request while changing provenance from `ibkr` to `ibkr_cached`.

### Closed — Successful OpenAI calls are attributed to `unknown`

Tracing now takes the provider identity from the concrete Copilot provider boundary. OpenAI card and stream calls use `openai_copilot` with meaningful operation names; mock, disabled, and unavailable providers retain distinct identities. Terminal tracing preserves ready/success, refusal, incomplete, cancellation, timeout, and unavailable outcomes without treating non-success states as success. Recorded metadata is restricted to safe run/model/operation/duration fields.

The live streamed run produced a visible sourced transcript card. `/system/provider-usage` then reported one `openai_copilot` call, one success, endpoint `copilot.stream_research_card`, and `Healthy` activation-aware health. Existing `unknown` calls from unrelated legacy provider boundaries were not relabeled.

### Closed — Portfolio quote timeout can exceed the fixed worker budget

The public quote timeout is explicitly bounded to 10 seconds. The outer worker budget is derived from market-data mode, account/position overhead, and the accepted quote timeout, with a hard 45-second cap. IB worker tasks now distinguish queued, active, cancelled, and `still_finishing` states so a timed-out active operation cannot masquerade as a dead thread. Partial snapshots retain account data and explain quote-budget degradation.

The live maximum-timeout request returned six positions and account totals in 11.01 seconds with a concise partial-quote warning. An immediate account-subscribe request completed normally. Regression coverage exercises the maximum public value, derivation/capping, queued follow-up behavior, and partial-snapshot warnings.

### Closed — Research-book contribution remains aggregate-only

Validated research books now carry stable per-leg identity, signed gross-normalized weight, and aligned return observations alongside the aggregate return stream. Aggregate VaR, CVaR, volatility, drawdown, beta, and Monte Carlo calculations remain based on the validated aggregate stream; covariance decomposition uses the aligned legs. Duplicate labels receive stable disambiguated ids. Missing/thin legs and older persisted books fall back to the aggregate row with an explicit compatibility warning.

The browser follow-up validated and composed the signed 0.6 XOM / -0.4 AMD book with 938 aligned observations, opened it in Risk without a freeze/retry storm, and rendered separate XOM and AMD contribution rows. Account movers and concentration rows remained empty, confirming research-book/account isolation.

### Closed — Repeated raw IBKR contract errors remain noisy

IBKR error records now retain request id, provider code, mapped contract symbol when available, and the raw provider message for diagnostics. Portfolio-facing summaries deduplicate identical errors within the operation and identify the affected symbol when it is known; distinct symbols and materially distinct failures remain separate. The live follow-up Portfolio result contained only the concise quote warning and did not reproduce code 200, so the original provider error itself was not available for another live comparison.

Deterministic coverage verifies repeated code 200 errors, distinct symbols, unknown request ids, operation-level deduplication, and the raw-diagnostics versus user-summary split.

## Verification After Remediation

Complete gates:

- backend: `422 passed` in 183.86 seconds;
- frontend typecheck: passed;
- frontend tests: `42` files and `263` tests passed;
- production build: passed;
- desktop check: passed in 26.94 seconds.

Focused regression counts used while iterating:

- Commodities: 16 tests;
- provider usage: 9 tests, plus 7 selected Copilot lifecycle tests;
- Portfolio timeout/market/snapshot: 19 tests;
- research/Risk/API: 81 tests;
- frontend research/Risk handoff and workspace: 34 tests;
- IBKR error and timeout contracts: 8 tests.

The production build retained pre-existing non-fatal warnings for one unused Portfolio selector, IV SVG accessibility annotations, and unused Surface3D exports.

## Post-Remediation Branch Reconciliation

After PR #2 was opened, every local worktree, local branch, Gamma remote branch, stash, and recent unreachable commit was compared with the PR head. No other worktree contained a newer complete app state. Four old divergent branches contained isolated experiments; they were evaluated commit-by-commit rather than merged wholesale.

| Historical commit | Decision | Evidence |
| --- | --- | --- |
| `aef7f70` — expand Macro snapshot/cross-asset coherence | Do not port | The current Macro domain has a newer, richer coherence/lead-lag model, linked prediction-market records, policy-expectation overlays, event studies, trade partners, and country comparison. Porting the old model would duplicate and regress current contracts. |
| `6aaed0a` — survive individual Macro series failures | Port and generalize | The current per-series loop could still abort the full snapshot. The port now isolates FRED, comparison, and IBKR FX failures, preserves remaining series, logs only safe identifiers/error type, and returns actionable warnings without exception text or credentials. |
| `77a69d1` — replace removed London gold spot with `NASDAQQGLDI` | Do not port | FRED confirms the London spot series was removed, but `NASDAQQGLDI` is a Nasdaq gold index in index points with copyright constraints, not a USD/oz spot reference. Using it in the current Commodities contract would be a unit/basis error. |
| `c007481` — move Tauri target output | Do not port | The current desktop scripts already isolate `check` and runtime/build targets under ignored Tauri directories, and the documented desktop check passes. The historical path rewrite provides no current correctness gain. |

The reconciliation also corrected the shared test-safety setting from obsolete `COPILOT_PROVIDER=mock` to the runtime-owned `GAMMA_COPILOT_PROVIDER=mock`. Before the correction, a developer `.env` could make a nominal mock test call live OpenAI; the failure was reproduced as a live 429 and the corrected test passed without provider access.

Reconciliation verification:

- focused Macro: `28 passed`;
- Macro/SITREP/API integration: `57 passed`;
- complete backend: `425 passed` in 160.08 seconds;
- frontend typecheck: passed;
- frontend: `42` files and `263` tests passed;
- production build: passed;
- desktop check: passed.

## Confirmed Regressions Closed or Narrowed

- Options no longer ignores the requested XLE symbol at the API boundary.
- Options can build a live XLE surface during the current TWS session.
- Copilot no longer completes silently without a card: both tested live requests persisted `ready` cards, and the explicit streaming run reached one `completed` terminal.
- Risk’s backend response no longer mixes live-account holdings into a Strategy Lab research-book result.
- Strategy Lab composition and Risk computation completed without an API retry storm.

## UI Verification Boundary

The remediation pass used a permitted in-app localhost browser and visually verified:

- Commodities refresh → WTI select/drill → change and dated prior reference retained;
- live/provider-backed XLE Options surface rendering;
- signed Strategy Lab book → Open in Risk without a freeze/retry storm;
- separate per-leg Risk contributions with no account movers or concentration rows;
- OpenAI Copilot completion into a visible sourced transcript card.

The Options adaptive-poller behavior remains covered by frontend regression tests; the browser pass did not instrument network traffic after navigation, so it does not claim a direct observation of request cessation/backoff.

## Cleanup

The dedicated audit IV session was stopped, the dedicated TWS client was disconnected, and no portfolio, order, account, or trading state was changed.
