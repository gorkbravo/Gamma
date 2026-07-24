# Gamma Live-Provider Regression Pass — 2026-07-24

Date: 2026-07-24

Mode: targeted live-provider regression

Data: live TWS on port 7496, `MOCK_DATA=false`, market-data mode `auto`

Scope: Portfolio, Options, Commodities, Strategy Lab → Risk, Copilot, and provider diagnostics

## Outcome

The live provider layer is broadly functional. TWS accepted a dedicated Gamma audit connection, live futures and options data built successfully, signed Strategy Lab books reached Risk without account-position leakage at the API contract, and Copilot completed two OpenAI-backed requests.

The pass also confirmed one existing cross-tab data-retention bug and found two diagnostics/timeout-contract gaps.

| Surface | Result | Evidence |
| --- | --- | --- |
| TWS connection | Pass | `/system/status` reported `Connected` on a dedicated audit client id. |
| Portfolio snapshot | Pass with timeout-contract caveat | Default-style 2-second quote timeout returned six positions plus cash, NLV, and market value in 12.63s. A 10-second quote timeout exceeded the fixed 20-second worker budget and returned an empty timeout snapshot while the worker continued. |
| Options / XLE | Pass at API boundary | The visible XLE symbol was accepted; the live session reached `Running (XLE, Live)` with spot 59.50, 21 option points, six expiries, and four strikes. |
| Commodities / WTI | Fail: fresh state not retained | Force refresh returned WTI 92.10, +5.27 / +6.07%, prior reference 2026-07-22. The immediately following cached/drill request kept 92.10 but cleared the change and prior timestamp to `N/A`. |
| Strategy Lab | Pass | XOM and AMD each resolved to 938 yfinance daily return points; the signed 0.6 / -0.4 book validated with 938 aligned observations. |
| Strategy Lab → Risk | Pass for source isolation; partial for decomposition | Risk returned `source_scope=research_book`, the correct source label, 100% coverage, and no account holdings. Contributions still collapse to one `STRATEGY_BOOK` row instead of XOM and AMD legs. |
| Copilot streaming | Pass | Explicit run `live-audit-run-20260724` emitted 421 monotonic events (sequence 0–420): `run.created`, 418 `text.delta`, `usage`, and one `completed`. Terminal result was `ready`, had a card, two sources, and model `gpt-5.5-2026-04-23`. |
| Provider diagnostics | Fail for Copilot attribution | Both Copilot calls succeeded, but provider usage recorded them under `unknown`; `openai_copilot` remained `Not requested`. |

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

## Confirmed Regressions Closed or Narrowed

- Options no longer ignores the requested XLE symbol at the API boundary.
- Options can build a live XLE surface during the current TWS session.
- Copilot no longer completes silently without a card: both tested live requests persisted `ready` cards, and the explicit streaming run reached one `completed` terminal.
- Risk’s backend response no longer mixes live-account holdings into a Strategy Lab research-book result.
- Strategy Lab composition and Risk computation completed without an API retry storm.

## UI Verification Boundary

The embedded browser rejected localhost navigation under its security policy, so this pass could not visually verify:

- active-view-only Options polling after navigating away;
- the Strategy Lab → Risk app-wide freeze fingerprint;
- visible Risk panel separation and contribution rendering;
- visible Copilot transcript rendering;
- the exact Commodities row-click interaction.

Those items still need a desktop/webview or permitted localhost browser run. The provider, persistence, and API contracts above were exercised live rather than mocked.

## Cleanup

The dedicated audit IV session was stopped, the dedicated TWS client was disconnected, and no portfolio, order, account, or trading state was changed.
