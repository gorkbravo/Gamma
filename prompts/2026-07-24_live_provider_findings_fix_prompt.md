# Agent Prompt: Fix the July 24 Live-Provider Findings

You are working in the Gamma repository. Implement and verify the findings recorded by the targeted live-provider regression pass on 2026-07-24.

Do not stop at analysis or a written proposal. Make the code changes, add regression coverage, run the relevant validation suites, and update the active audit/roadmap documentation with evidence for anything you close.

## Read First

Before changing code, read these files in order:

1. `AGENTS.md`
2. `roadmap.md`
3. `README.md`
4. `docs/README.md`
5. `docs/audits/usability/gamma_usability_findings_2026-07-24.md`
6. `docs/provenance_expectations.md`

If you touch frontend UI, browser-visible state, controls, panels, navigation, or CSS, also read:

7. `docs/design_principles.md`

Preserve Gamma’s core boundary: this is a read-only research environment. Do not add order placement, trading, rebalancing, wallet mutation, arbitrary code execution, or any execution-capable provider tool.

## Objective

Fix the five confirmed findings below, in priority order:

1. Fresh Commodities changes disappear on drill/cached reload.
2. Successful OpenAI Copilot calls are attributed to provider `unknown`.
3. Portfolio quote timeout can exceed the IB worker budget and leave misleading queued-work symptoms.
4. Strategy Lab research-book Risk contribution is aggregate-only.
5. Repeated raw IBKR contract errors are noisy and lack useful attribution.

Work through all five unless a concrete dependency makes one unsafe or impossible. If blocked on one item, record the evidence and continue to the next independent item.

Do not broaden this task into new tabs, provider expansion, or unrelated UI redesign.

## Finding 1 — Preserve Fresh Commodity Change Context

Live evidence:

- Fresh WTI request: price 92.10, change 5.27, change percent 0.060693, provider `ibkr`, prior timestamp 2026-07-22.
- Immediate non-force/drill request: price remained 92.10, but change, change percent, and prior timestamp became `null`; provider became `ibkr_cached`.

The fix must preserve the just-fetched, provider-backed dated prior-close context across a normal drill interaction.

Important correctness constraint:

- Do not reintroduce the old bug that calculated headline change by differencing two arbitrary cached curve snapshots.
- A cached headline change is valid only when the cached record contains the exact provider-backed current quote and its dated prior-close/settlement reference from the successful fresh request.
- If that pair is not available or cannot be proven coherent, continue to show `N/A`.

Likely areas to inspect:

- `src/services/commodities_adapters.py`
- `src/application/commodities_service.py`
- the local curve/quote snapshot cache
- `frontend/src/lib/stores/app.ts`
- `frontend/src/views/CommoditiesView.svelte`

Acceptance criteria:

- A force refresh that produces a dated WTI change is followed by a non-force request or row drill without losing price, change, change percent, or prior timestamp.
- Provenance changes honestly from fresh to cached where appropriate.
- Cached records explicitly retain the original current/prior source timestamps.
- An unrelated stale curve snapshot is never treated as a prior close.
- Tests cover fresh → cached/drill retention, missing prior reference, mismatched timestamps, and restart/cache restoration if the cache is durable.

## Finding 2 — Attribute Copilot Usage to OpenAI

Live evidence:

- Two OpenAI-backed Copilot runs completed successfully.
- `/system/provider-usage` recorded two successful calls under `unknown`.
- `openai_copilot` remained at zero calls with health `Not requested`.

Inspect the tracing boundary rather than patching presentation labels after aggregation.

Likely areas:

- `src/application/runtime.py`
- `src/services/provider_usage.py`
- `src/services/openai_copilot_provider.py`
- the Copilot provider interface and tracing proxy

Acceptance criteria:

- OpenAI Copilot card and streaming calls are recorded with provider id `openai_copilot`.
- Provider usage health becomes `Healthy` after a successful configured call.
- Operation/endpoint names are meaningful rather than blank.
- Failures, refusals, incomplete results, cancellation, and timeouts retain typed terminal status without being counted as successful.
- Safe metadata may include run id, resolved model, duration, and operation, but never API keys, prompts, portfolio payloads, or private source contents.
- Mock, disabled, and unavailable Copilot providers retain honest distinct identities and activation-aware health.
- Tests cover synchronous and streamed success plus at least one typed non-success path.

## Finding 3 — Align Portfolio Quote and Worker Timeouts

Live evidence:

- `quote_timeout_seconds=10` returned after roughly 20 seconds with `IB task timed out`, no positions, and no account totals.
- The queued IB task continued after the API response.
- An immediate account-subscribe request then reported the IB thread as unresponsive.
- `quote_timeout_seconds=2` returned six positions and account totals in 12.63 seconds.

Current seams include:

- public API range in `src/api/routes/portfolio.py`
- fixed worker timeout in `src/services/ibkr_client.py`
- market-data quote behavior in `src/services/market_data.py`
- `IBThreadRunner` queue semantics in `src/services/ib_thread.py`

Choose a coherent timeout contract based on the real bounded work:

- account subscription/readiness;
- account summary and positions;
- contract qualification;
- quote collection;
- totals and FX work.

Acceptance criteria:

- Every accepted public quote timeout fits within or correctly expands the outer task budget.
- A timed-out caller does not leave an indistinguishable live task that causes the next request to report a false “IB thread unresponsive” condition.
- If cancellation of an in-flight ib_insync operation is not safe, expose an explicit `still_finishing`/busy state or reject timeout values that cannot fit the bounded worker contract.
- Default behavior remains responsive.
- The API never silently accepts a timeout value it cannot honor.
- Tests cover the maximum accepted timeout, outer timeout derivation/capping, queued follow-up behavior, and partial-snapshot warnings.

## Finding 4 — Preserve Per-Leg Research-Book Risk Contributions

Live evidence:

- XOM and AMD each resolved to 938 return points.
- The signed 0.6 / -0.4 book validated with 938 aligned observations.
- Risk correctly used `source_scope=research_book` and did not mix live-account holdings.
- Contribution output contained only one `STRATEGY_BOOK` row.

Preserve the existing aggregate book metrics while carrying enough validated leg identity and aligned return information for decomposition.

Likely areas:

- `src/models/research_lab.py`
- `src/api/schemas/research.py`
- `src/api/schemas/risk.py`
- `src/api/routes/risk.py`
- `src/application/risk_service.py`
- `frontend/src/lib/view-models/research.ts`
- `frontend/src/lib/stores/app.ts`
- `frontend/src/lib/risk-handoff.ts`
- `frontend/src/views/RiskView.svelte`

Acceptance criteria:

- Aggregate research-book VaR, CVaR, volatility, drawdown, beta, and Monte Carlo metrics remain based on the validated aggregate stream.
- Contribution output exposes stable XOM and AMD leg identities, signed weights, and per-leg contribution values.
- Short-leg sign and gross-normalized exposure semantics remain correct.
- The Risk screen remains explicitly scoped to the research book and cannot leak account movers or concentration rows.
- Older persisted books without the new leg payload degrade to the existing aggregate row with an explicit compatibility warning.
- Tests cover two signed legs, duplicate labels, missing/thin leg history, old persisted payloads, and account/book isolation.

## Finding 5 — Deduplicate and Humanize IBKR Errors

Live evidence:

- A successful Portfolio snapshot contained five identical `IBKR error (200): No security definition has been found for the request` warnings.
- LMT and FOUR also had missing quote warnings.

Acceptance criteria:

- Identical IBKR errors within one operation are deduplicated.
- When the request/contract can be mapped to a symbol, the user-facing warning identifies it.
- Raw request ids and provider codes remain available in diagnostics, but the primary Portfolio warning list is concise and human-readable.
- Distinct symbols or materially distinct failures are not incorrectly collapsed.
- Existing provenance and read-only warnings remain intact.
- Tests cover duplicate code 200 errors, distinct affected symbols, unknown request ids, and the diagnostics-versus-user-summary split.

## Verification

Run focused tests while iterating, then the complete documented gates.

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Frontend:

```powershell
cd frontend
npm run typecheck
npm run test
npm run build
npm run desktop:check
```

For any frontend-visible change, also verify the relevant flows in a permitted browser or desktop webview:

- Commodities refresh → select/drill → change retained;
- Strategy Lab signed book → Open in Risk → no freeze/retry storm;
- Risk shows per-leg book contributions and no account holdings;
- Copilot completes into a visible sourced transcript card;
- Options polling stops or backs off after navigating away.

Do not claim UI verification if only the API was exercised.

## Live TWS Retest

If TWS is running and the user’s existing configuration is available:

- use `MOCK_DATA=false`;
- use a dedicated non-conflicting `IB_CLIENT_ID`;
- keep market-data mode explicit;
- do not change account, order, or trading state;
- stop IV sessions and disconnect only the dedicated audit client when done;
- do not stop the user’s TWS process.

Minimum live evidence after the fixes:

1. Portfolio snapshot succeeds with the maximum supported quote-timeout contract or rejects an unsupported value clearly.
2. Fresh WTI change survives the immediate cached/drill request with matching source timestamps.
3. XLE IV still reaches a live/provider-backed snapshot.
4. Signed XOM/AMD book reaches Risk with separate contribution rows.
5. OpenAI Copilot streaming reaches one terminal event and `/system/provider-usage` reports `openai_copilot`, not `unknown`.

If live verification is unavailable, keep deterministic mock/integration coverage comprehensive and state exactly what remains to be retested.

## Documentation and Handoff

When a finding is fixed:

- update `docs/audits/usability/gamma_usability_findings_2026-07-24.md` with implementation and verification status;
- update `roadmap.md` only where the current completion statement materially changed;
- keep README commands and provider setup accurate;
- report exact test counts and any live-provider limitations.

Do not mark a finding closed based only on code inspection or unit tests when its acceptance criteria explicitly require live or UI evidence.
