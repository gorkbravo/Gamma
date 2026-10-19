# Strategy Lab saved experiments and Risk acceptance

Date: 2026-10-06. Scope: manual Composer → Save → restart → Reopen → Risk → revised-weight comparison. This closes a Research V2 workflow milestone; it does not certify the entire Strategy Lab or Risk workstreams.

## Result

- Compose Portfolio runs directly and reports an actionable input/provider error on failure. Validate Book remains an optional diagnostic. A failed composition retains the previous successful result and its matching research book.
- Save Experiment uses the composition name by default and retains the server-accepted signed inputs, per-leg resolved returns, benchmark history, alignment dates, metrics, warnings, and provenance. The versioned payload is `gamma.strategy-lab-experiment.v1`; older normalized saved runs still load through their existing path.
- Writes use atomic replacement and reject non-finite JSON. Versioned experiment creation validates input/resolved-leg counts and gross-normalized signed weights.
- Reopen Experiment restores the builder's original raw weights and frozen leg/benchmark objects. Changing a ticker or asset class clears the previous retained leg. Weight revisions retain the saved histories and original provider identity.
- Risk receives the hypothetical research book and its retained benchmark. An explicitly empty retained benchmark stays unavailable; it does not silently fetch a replacement. Deliberately selecting another benchmark in Risk uses the provider path.
- Saved Runs compares a selected saved baseline against the current composition or another saved experiment. Existing Compare / Scenario analytics align common timestamps, show total return, annual volatility, max drawdown, percentage-point changes, and rebased NAV. Benchmark-history comparison uses dates/values rather than JSON property order.

## Live evidence

The real-browser acceptance harness mounts the production StrategyLabView, RiskView, stores, API callbacks, and Risk request builder. It calls a real uvicorn backend rather than mocking successful network responses. This is browser/HTTP acceptance, not a packaged Tauri shell test.

Capture connected a separate read-only IBKR client (`88`) to the configured TWS session. Research history providers were restricted to IBKR. The user environment file was unchanged. A separate acceptance storage/cache directory kept test experiments out of the user's saved library.

The browser composed `QQQ=+1`, `SPY=-1`, with SPY benchmark, requested lookback 260 and minimum overlap 60, without clicking Validate Book. Both resolved legs reported `ibkr`. The retained aligned dataset had **289 observations, 2025-08-13 through 2026-10-06**.

The original backend process was terminated and a fresh process loaded the same saved record. TWS remained disconnected during replay. The browser reopened the experiment, computed Risk with `source_scope=research_book`, changed QQQ's raw weight to +2, recomposed from retained objects, and compared original/revised results across all 289 common observations. Exact benchmark and per-leg history equality passed. The baseline's signed weights remained +1/-1.

Risk preserves its existing lookback semantics: the 260-observation request analyses the newest 260 of the 289 handed-off rows, with an explicit window warning. Saved experiment/comparison evidence retains the full aligned provider dataset. Historical provider duration rounding therefore does not imply that Risk and composition metrics use identical windows.

The browser also simulated an unavailable ticker after editing a reopened identifier. It verified the old ticker's retained object was absent, the error appeared, and opening Risk afterward still used the last successful revised book.

Desktop (1440), intermediate (1000), and narrow (390) screenshots were inspected. The comparison remains readable, controls remain reachable, and wide saved tables scroll within their container. There was no viewport overflow or application page error.

Live saved record: `661cb5644f7e4f59b1e0a9ccf9b01bf6`. Local ignored evidence: `output/playwright/strategy-experiments-live/{summary.json,baseline.json,replay.json,comparison-*.png}`. Logs stay local because TWS connection diagnostics can contain account information.

## Reproduction and verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe output/verify_strategy_experiments.py
.\.venv\Scripts\python.exe output/verify_strategy_experiments.py --live
.\.venv\Scripts\python.exe -m pytest tests/test_strategy_experiments.py tests/test_research_v2.py tests/test_research_service.py tests/test_api.py -q
```

From `frontend`:

```powershell
npm test -- src/lib/strategy-experiments.test.ts src/lib/risk-handoff.test.ts src/views/StrategyLabView.test.ts src/lib/view-models/research.test.ts
npm run typecheck
npm run build
```

The focused backend set passed 72 tests, frontend set passed 34 tests, and typecheck/production build passed. Build diagnostics remain the existing Options SVG interaction and Surface3D unused-property warnings. Successful capture/replay acceptance is available in both deterministic inline-history and live IBKR modes. No order, routing, account mutation, rebalancing, or Copilot harness capability was added.

## Follow-up — 2026-10-19 (2026-10-15 review)

Risk adopted a Strategy Lab book's benchmark and lookback only when an arriving result changed the selected source. When the book was already selected, the controls kept the previous values, and the next **Compute Core**/**Run MC** sent them. That happened after a second experiment handoff while Risk stayed mounted, or in a session without an account snapshot, where the book is the only source from mount. **Load Strategy Book** also recomputed with the account values. It set the source but did not seed the controls before submitting.

Risk now seeds the controls from the book's identity (`bookId` + `createdAt`, so a recomposed experiment counts as a new book) whenever the book is the selected source, not on a source change (`strategyLabControlsToSeed` in `frontend/src/lib/risk-handoff.ts`). A deliberate benchmark or lookback edit on the same book is kept. Selecting another source clears the seed, so reselecting the book restores its parameters. **Load Strategy Book** seeds before it submits. A book lookback outside 126/252/504 now appears in the Lookback control instead of leaving it blank.

Tests: `risk-handoff.test.ts` covers the seeding rules. The Playwright harness (`e2e/risk-source-identity.spec.ts`, now a wrapper component that can simulate a second handoff and a `?snapshot=none` session) covers the no-account session, a second handoff after a user edit, and the Load Strategy Book parameters. These three browser tests fail against the previous `RiskView.svelte`. All six harness tests pass with the fix.

