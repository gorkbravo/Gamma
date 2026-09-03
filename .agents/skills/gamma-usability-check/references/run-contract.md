# Gamma Usability Audit Run Contract

Use this contract for every audit. It protects live data honesty, user state, and the distinction between product evidence and diagnostic substitution.

## 1. Establish The Baseline

Record before interacting with the app:

- local date, time zone, commit, branch, and dirty/clean state;
- whether the app was already running or was launched for the audit;
- frontend/desktop and backend addresses;
- `MOCK_DATA` as reported by `/system/status`, not merely the launcher shell;
- market-data mode and read-only boundary;
- TWS connection state without recording an account identifier;
- provider capability and provider-usage health relevant to the candidate journey;
- market session context when it materially affects the workflow.

Run the safe preflight from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\skills\gamma-usability-check\scripts\audit-preflight.ps1
```

If the running backend requires a session token, make it available to the process as `GAMMA_SESSION_TOKEN` or pass `-SessionToken` without logging the value. The script reports booleans and sanitized status only.

Never read or print `.env` contents to discover credentials. Check presence through the preflight, app diagnostics, or provider capability metadata.

## 2. Attach Or Launch Safely

Prefer an existing healthy Gamma runtime so the audit reflects the product the user is running. Do not restart it merely for a cleaner setup.

If Gamma is not running:

1. Use the commands currently documented in `README.md`.
2. Use `MOCK_DATA=false` for the provider-backed audit.
3. Reuse configured providers without copying keys into commands, reports, screenshots, or logs.
4. Use a fresh session token shared only between the backend and frontend processes.
5. Use an isolated `PORTFOLIO_HISTORY_DIR` when launching a dedicated audit stack unless the selected journey explicitly needs the user's existing local history. Record the isolation either way.
6. Do not take over an active IBKR client id. Prefer an existing connected Gamma runtime or a separately configured audit client id known to be unused.
7. Keep a list of processes and sessions started by the audit so only those are stopped later.

Use the localhost frontend in an in-app browser for inspectable UI work when available. Use the desktop shell when the shell itself is in scope. Fall back to Playwright only when interactive browser control is unavailable or repeatable instrumentation is needed.

## 3. IBKR And Provider-Backed Completion Gate

The default requested mode is IBKR-integrated. Classify the run before choosing the thesis:

### IBKR-integrated

Gamma reports `mock_mode=false`, a connected IBKR session, and the relevant Gamma surfaces expose provider-backed inputs. Record market-data mode and entitlement gaps separately; connection does not imply that every instrument has live quotes.

This is the only mode that may be described as a full Gamma usability audit.

### Provider-only focused

Use this mode only when the user explicitly requests it. At least one decisive input must be provider-backed, but the scope excludes broker-dependent Portfolio, Options, Risk, live-market, and account-continuity claims that cannot be established without IBKR. Public-provider workflows may still be audited, but the report must not generalize its score or verdict to the full app.

### Diagnostic-only blocked

No meaningful provider-backed route is available, the UI cannot be reached, authentication cannot be established, mock mode is active, or the product boundary prevents safe continuation. Do not substitute mock data and call the run complete.

If a normal full audit is requested and IBKR is disconnected, stop before thesis selection and return a concise preflight blocker. Do not create a standard usability report or update the coverage ledger unless the user explicitly asked to retain failed preflight attempts. Ask for IBKR to be connected, then rerun.

### Known-Constraint Suppression

In a provider-only focused run, treat the missing IBKR connection as a declared environmental constraint:

- do not file “IBKR disconnected,” absent holdings, unavailable broker quotes, or downstream broker-dependent emptiness as separate findings;
- do not lower scores for capabilities excluded by the declared mode; mark them `N/A — requires IBKR-integrated audit`;
- do not repeat the same connection warning across surface findings;
- file a product finding only when Gamma misreports the connection, presents fallback data dishonestly, lets the expected absence break an independent provider workflow, floods or freezes the UI, or fails a safe reconnection/status-recovery experience that was actually exercised;
- distinguish `connected but not entitled`, `connected with delayed/frozen data`, and `disconnected`.

Public provider data reached through Gamma—such as SEC, FRED, Treasury, DB.nomics, Census, yfinance, CoinGecko, GeckoTerminal, Polymarket, Kalshi, EIA, RSS, or configured AIS—may satisfy a provider-only focused gate when its provenance and freshness fit the claim. It does not upgrade that run into a full Gamma usability audit without IBKR.

## 4. Capture Evidence Without Turning The Audit Into An API Test

Drive the primary workflow through visible controls. For each important step record:

- user intent and exact surface/mode;
- selected entity, scope, horizon, and assumptions;
- visible source, freshness, warning, and timestamp;
- result classification;
- whether context survived navigation, handoff, refresh, and return;
- elapsed wait when latency is material;
- screenshot or trace reference for blockers, misleading values, and successful terminal artifacts.

Use API probes or logs to isolate a failure only after observing the UI behavior. A successful endpoint does not make an undrivable UI step pass. A failed endpoint behind an honest unavailable state is not automatically a UI defect.

Capture `/system/provider-usage` before and after provider-dependent actions when authenticated access is available. Compare calls, statuses, cache behavior, and health labels without copying sensitive messages.

Store only selected durable evidence under:

```text
docs/audits/usability/evidence/<report-stem>/
```

Do not commit broad network dumps, account identifiers, raw portfolio payloads, session tokens, API keys, or provider responses that may contain private data. Prefer redacted screenshots and concise measurements in the report.

## 5. Exercise A Complete Research Job

Unless blocked, a complete journey should include:

- discovery from a live Gamma surface;
- a provisional thesis recorded before deep drilling;
- meaningful analysis in at least three relevant product surfaces;
- one context-preserving handoff when Gamma offers one;
- supporting and disconfirming evidence;
- a final synthesis, memo, saved research object, or clearly stated reason no artifact can be produced;
- a conclusion of `confirmed`, `partially confirmed`, `rejected`, `indeterminate`, or `unsupported`;
- separate thesis-confidence and data-quality-confidence judgments.

The numbers are a floor for an ordinary successful journey, not a reason to visit irrelevant tabs. Depth and coherence matter more than tab count.

Also complete one coverage-debt mission under [coverage-policy.md](coverage-policy.md), unless the primary journey already used the selected target substantively. Keep that mission bounded and separate when it is not naturally related to the thesis.

When the selected route creates durable local state, test one relevant continuity boundary—tab switch, refresh, restart, or reopen—if doing so is safe. Do not delete pre-existing user state to make the test deterministic.

## 6. Retry And Stop Conditions

- Retry a failed user action once after checking visible state and diagnostics. Use a second materially different recovery only when evidence suggests it is safe and useful. Do not create request storms.
- Stop the affected branch immediately if an action could place an order, alter an account or wallet, expose a credential, overwrite user research, or escape Gamma's bounded research runtime.
- Stop the full journey and write a diagnostic-only report when provider-backed evidence is unavailable across reasonable alternative routes.
- If a UI step is blocked, an API probe may establish whether the backend exists, but it must not be reported as end-to-end success.
- Do not fix code, change feature flags, edit provider configuration, or rerun against a modified working tree.

## 7. Cleanup

At the end:

1. Stop IV collection, streams, browser recordings, or other bounded sessions started by the audit.
2. Disconnect only a dedicated TWS client connection started by the audit. Do not disconnect a pre-existing user session.
3. Stop only backend/frontend/desktop processes launched by the audit.
4. Archive or remove only clearly labeled audit artifacts created during the run when the app provides a safe, unambiguous path. Otherwise leave them and list them.
5. Confirm that no order, account, portfolio, wallet, provider configuration, credential, or product-code state changed.
6. Record cleanup and residual artifacts in the report.

Report cleanup failures as findings when they expose a product usability problem; otherwise list them as audit residue.
