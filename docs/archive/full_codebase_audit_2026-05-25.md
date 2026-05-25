# Gamma Full Codebase Audit - 2026-05-25

## Scope

This audit reviewed the working tree at `C:\Users\User\Desktop\Gamma` on branch `main` for backend, frontend, desktop shell, dependency posture, security boundaries, tests, and UI/design drift.

The working tree already had user-owned changes before this audit:

- modified `Stuff.md`
- untracked `tmp_news.py`
- untracked `tmp_pms.py`
- untracked `tmp_probe.py`

Those files were not changed or reverted.

Gamma's active product boundary remains: read-only market research environment, not an execution platform. Findings below are ordered by importance and written as implementation handoff packets for future agents.

## Validation Snapshot

| Check | Result | Notes |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe -m pytest` | Passed | `279 passed` in about 72 seconds. |
| `npm run test` from `frontend/` | Failed | 1 test file failed, 2 assertions failed in `CommoditiesView.test.ts`. |
| `npm run build` from `frontend/` | Passed with warnings | Unused CSS selector warnings and main chunk size warning. |
| `npm run desktop:check` from `frontend/` | Passed | Tauri dev-profile check completed. |
| `npx tsc --noEmit` from `frontend/` | Failed | Multiple production and test typing errors. |
| `npm audit --audit-level=moderate` from `frontend/` | Failed | 3 advisories: `devalue`, `postcss`, `svelte`. |

## Remediation Update - 2026-05-25

Completed after the audit:

- Fixed `P1. Cache Keys Can Escape The Cache Directory On Windows` by hashing logical cache keys into bounded filenames, adding resolved-path containment checks, updating cache-backed risk discovery for hashed filenames, and adding hostile-key regression tests in `tests/test_cache_service.py`.
- Fixed `P3. News Force Refresh Is Accepted But Ignored` by wiring `force_refresh` through `/news/latest`, adding a short service-level latest-feed cache, and proving `force_refresh=true` bypasses and replaces that cache.
- Validation after these fixes: `.\.venv\Scripts\python.exe -m pytest` passed with `287 passed` in about 68 seconds.

## P1. Cache Keys Can Escape The Cache Directory On Windows - Fixed 2026-05-25

Status: fixed after the audit. `src/services/cache.py` now resolves all cache filenames under the configured cache directory using a sanitized debug prefix plus SHA-256 digest, and tests cover hostile Windows-style separators, parent traversal, long inputs, and empty key parts. `src/application/risk_service.py` was updated so file-backed equity-cache discovery still works with hashed cache filenames.

### Impact

User-controlled cache key material can produce paths outside the configured cache directory on Windows. This is a local arbitrary JSON write primitive constrained by the fixed suffixes used by the cache layer, but it still breaks cache isolation and can overwrite adjacent JSON state. Long or malformed keys can also create avoidable filesystem errors and denial-of-service behavior.

### Evidence

`src/services/cache.py` builds paths directly from caller-provided keys:

- `src/services/cache.py:17` - `_meta_path(self, key)` returns `self.base_dir / f"{key}.json"`
- `src/services/cache.py:20` - `_data_path(self, key)` returns `self.base_dir / f"{key}.bin"`
- `src/services/cache.py:23` - `_value_path(self, key)` returns `self.base_dir / f"{key}.value.json"`
- `src/services/cache.py:26` - `_json_path(self, key)` returns `self.base_dir / f"{key}.payload.json"`
- `src/services/cache.py:92` - `set_json` writes the derived path without containment checks
- `src/services/cache.py:98` - `make_key` only removes spaces and replaces `/`

Request-controlled data can reach cache keys:

- `src/api/schemas/crypto.py:27` - `CryptoWorkspaceRequestModel`
- `src/api/schemas/crypto.py:28` - `query: str = ""` has no length or character bounds
- `src/services/crypto_adapters.py:116` - query value is included in `cache.make_key("crypto", "coingecko", "search", normalized_query.lower())`
- `src/services/crypto_adapters.py:141` - joined token ids flow into another cache key
- `src/services/crypto_adapters.py:165` - token id flows into detail cache key
- `src/services/crypto_adapters.py:195` - token id flows into history cache key

On Windows, `make_key("crypto", "coingecko", "search", "x\\..\\..\\data\\foo")` preserves backslashes and `..`, creating a path that can resolve outside the cache base.

### Reproduction / Verification

Use a unit test rather than a live provider call:

1. Instantiate `CacheStore` with a temporary base directory.
2. Call `set_json` with a key containing Windows separators and parent traversal, for example `safe\\..\\outside\\probe`.
3. Assert that the resolved output path does not remain under the temporary cache directory with the current implementation.

Also add direct tests for `make_key` or its replacement with cases containing:

- backslash
- slash
- `..`
- colon
- reserved Windows names
- very long input
- empty parts

### Recommended Fix

Prefer eliminating path-derived keys entirely:

1. Add a helper such as `_safe_filename_for_key(key: str) -> str`.
2. Hash the full logical key with SHA-256 and use the digest as the filename stem.
3. Optionally keep a short sanitized prefix for debugging, but make the digest authoritative.
4. Add `_resolve_under_base(path: Path) -> Path` and assert the resolved path is under `base_dir.resolve()`.
5. Apply the helper to every `_meta_path`, `_data_path`, `_value_path`, and `_json_path` path builder.
6. Add Pydantic length bounds to request fields that contribute to cache keys.

### Acceptance Criteria

- All cache path builders produce paths under `CacheStore.base_dir` for hostile keys.
- Unit tests cover Windows-style separators even when running on non-Windows hosts.
- Long query strings do not create overlong filesystem names.
- Backend test suite still passes.

## P1. Local API Control Plane Has No Session Boundary

### Impact

The FastAPI backend exposes system and provider-control routes on localhost without authentication or a per-session token. Broad localhost CORS makes browser-origin access easier during development, and side-effecting GET endpoints can be triggered by arbitrary pages even when CORS prevents reading responses.

This is most relevant when Gamma is running locally and a user visits a malicious or compromised web page. The app is read-only with respect to trading, but it can still connect or disconnect providers, clear local state, trigger broker/provider calls, and consume rate limits.

### Evidence

CORS is permissive for localhost development origins:

- `src/api/main.py:45` - `allowed_origins` includes dev ports
- `src/api/main.py:51` - `allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$"`
- `src/api/main.py:57` - `allow_methods=["*"]`

Unauthenticated side-effecting routes:

- `src/api/routes/system.py:83` - `/system/connection/toggle`
- `src/api/routes/system.py:94` - `/system/market-data-mode`
- `src/api/routes/system.py:104` - `/system/base-currency`
- `src/api/routes/system.py:151` - account diagnostics / subscribe path
- `src/api/routes/portfolio.py:89` - `/portfolio/history/clear`

GET routes can trigger provider or local-state work:

- `src/api/routes/portfolio.py:41` - `/portfolio/history`
- `src/api/routes/portfolio.py:49` - optional snapshot refresh inside GET
- `src/api/routes/research.py:16` - `/research/overview`
- `src/api/routes/iv.py:14` - `/iv/surface`

### Reproduction / Verification

Manual checks:

1. Start the backend.
2. From a separate local HTML page or curl request, call a mutating route without credentials.
3. Confirm the route accepts the request.

Regression tests to add:

- Requests to mutating routes without a session token return `401` or `403`.
- Requests with the correct runtime token succeed.
- Requests from unknown origins are rejected by CORS where CORS applies.
- Side-effecting refreshes are not exposed via GET.

### Recommended Fix

1. Generate a random backend session token at process start.
2. Pass it to the Tauri frontend through the existing backend launch / API-base wiring.
3. Require a header such as `X-Gamma-Session` for mutating routes and expensive refresh routes.
4. Restrict CORS to the actual frontend origin rather than every localhost port.
5. Move side-effecting refresh actions from GET to POST where practical.
6. Keep unauthenticated `GET /health` available for smoke checks if needed.

### Acceptance Criteria

- Local malicious pages cannot trigger mutating Gamma API calls without the per-session token.
- Tauri frontend and local dev frontend still work after token wiring.
- Smoke checks are updated for the new auth boundary.
- Tests cover both allowed and denied route access.

## P2. Expensive Request Models Are Not Bounded

### Impact

Several request schemas accept unbounded numeric, string, list, or dictionary payloads. This can lead to high memory use, high CPU use, provider-rate-limit waste, or oversized cache keys. Even for a local desktop app, bounded request contracts are important because the backend is an HTTP surface.

### Evidence

Risk Monte Carlo inputs are unbounded:

- `src/api/schemas/risk.py:12` - `RiskComputeRequestModel`
- `src/api/schemas/risk.py:14` - `alpha`
- `src/api/schemas/risk.py:16` - `lookback_days`
- `src/api/schemas/risk.py:17` - `horizon_days`
- `src/api/schemas/risk.py:19` - `mc_horizon_days`
- `src/api/schemas/risk.py:20` - `mc_num_simulations`
- `src/application/risk_service.py:333` - request values flow into risk computation
- `src/analytics/var.py:187` - Monte Carlo allocates arrays sized by simulations and horizon

Strategy Lab accepts unbounded rows:

- `src/api/schemas/research.py:48` - `StrategyLabAnalyzeRequestModel`
- `src/api/schemas/research.py:49` - `rows: list[dict[str, Any]]`
- `src/application/research_service.py:906` - iterates all request rows
- `src/application/research_service.py:926` - builds a DataFrame from parsed rows

Other schemas with loose bounds:

- `src/api/schemas/crypto.py:28` - unbounded query string
- `src/api/schemas/crypto.py:35` - plain integer limit
- `src/api/schemas/prediction_markets.py:17` - unbounded request fields in prediction-market workspace request

### Reproduction / Verification

Add route-level tests that submit oversized payloads and assert validation errors:

- very high `mc_num_simulations`
- very high `horizon_days`
- very large Strategy Lab `rows`
- megabyte-scale strings for search/query fields
- excessive list lengths for market or token ids

### Recommended Fix

1. Add Pydantic `Field` constraints to all public request schemas.
2. Use both schema-level bounds and service-level clamps for expensive calculations.
3. Return clear `422` validation errors for invalid input.
4. Keep limits product-appropriate. Suggested starting caps:
   - Monte Carlo simulations: 20,000 or lower
   - Monte Carlo horizon: 252 trading days or lower
   - VaR lookback: 2,520 trading days or lower
   - Strategy Lab rows: 10,000 or lower
   - Search strings: 128-256 characters
   - ids per request: 50-100

### Acceptance Criteria

- Oversized requests fail fast with `422`.
- Normal UI requests continue to pass.
- Backend tests include both valid boundary values and invalid over-limit values.
- No service can allocate arrays directly from untrusted request integers without a cap.

## P2. Frontend Commodities Tests Are Red

### Impact

The frontend test suite is currently failing. This blocks reliable frontend CI and indicates drift between the intended Commodities deep-research surface and the current component behavior.

### Evidence

`npm run test` fails in:

- `frontend/src/views/CommoditiesView.test.ts:73` - expects `Vessel / Flow Proxy`
- `frontend/src/views/CommoditiesView.test.ts:95` - expects `LME / COMEX Warehouse Stocks`

The expected strings are not present in `frontend/src/views/CommoditiesView.svelte`.

Related component gates:

- `frontend/src/views/CommoditiesView.svelte:1909` - fundamental chart grid only renders when `fundamentalGroups.length`
- `frontend/src/views/CommoditiesView.svelte:1924` - fundamental tape only renders when `fundamentalTapeRows.length`

### Reproduction / Verification

Run:

```powershell
cd frontend
npm run test -- src/views/CommoditiesView.test.ts
```

Expected current result: 2 failed assertions.

### Recommended Fix

First decide product intent:

1. If those modules are still roadmap-aligned, restore stable module frames and empty states for:
   - vessel / flow proxy
   - EIA fundamental stack
   - LME / COMEX warehouse stocks
2. If the product surface intentionally changed, update the tests to assert the new headings and empty states.

Given Gamma's design principles, prefer stable dense module frames with clear empty states rather than disappearing analytical sections.

### Acceptance Criteria

- `npm run test` passes.
- Commodities deep views render predictable structures when backing arrays are empty.
- Tests assert both populated and empty-data states for Energy and Metals.

## P2. TypeScript Contract Check Is Failing And Not Enforced

### Impact

The Vite build succeeds while TypeScript fails, so contract drift can ship. This is especially risky because Gamma has many typed backend-derived payloads and view models.

### Evidence

`npx tsc --noEmit` fails with production and test errors. Production examples:

- `frontend/src/lib/external-links.ts:107` - `handleClick` is typed as `MouseEvent` but used as a DOM `EventListener`
- `frontend/src/lib/external-links.ts:108` - same issue on removal
- `frontend/src/lib/risk-workspace.ts:544` - invalid type predicate for nullable rows / cell shape
- `frontend/src/lib/risk-workspace.ts:547` - downstream row mapping uses the narrowed type
- `frontend/src/lib/view-models/crypto.ts:95` - reducer infers nullable accumulator in `sumNullableNumbers`
- `frontend/src/lib/view-models/iv.ts:185` - `surface.spot` / `sigma` narrowing is not preserved
- `frontend/src/lib/view-models/iv.ts:194` - `logNormalCdf` receives values typed as possibly null
- `frontend/src/lib/view-models/research.ts:449` - unsafe cast from generic record to metrics shape
- `frontend/src/lib/view-models/research.ts:479` - generic copy type mismatch
- `frontend/src/lib/view-models/research.ts:821` - implicit `any` recursion issue

Test fixtures are also stale and miss newer required fields such as `dependency_network`, `correlation_matrix`, `instrument_id`, `display_symbol`, and `source_provider`.

### Reproduction / Verification

Run:

```powershell
cd frontend
npx tsc --noEmit
```

### Recommended Fix

1. Add a `typecheck` script to `frontend/package.json`.
2. Fix production TypeScript errors first.
3. Update stale fixtures to match current API types.
4. Add typecheck to the standard validation sequence and CI.
5. Consider running `svelte-check` as a separate follow-up if not already covered.

### Acceptance Criteria

- `npm run typecheck` exists and passes.
- `npm run build` still passes.
- `npm run test` still passes.
- Production code has no `tsc --noEmit` errors.

## P2. Frontend Dependency Audit Has Known Advisories

### Impact

The frontend dependency tree has moderate and high advisories. Some Svelte advisories may be lower impact in a Tauri client without SSR exposure, but the dependency posture should still be cleaned up because Gamma runs local web technology with privileged desktop integration nearby.

### Evidence

`npm audit --audit-level=moderate` reports:

- `devalue` high severity, installed as `5.7.1`
- `postcss` moderate severity, installed as `8.5.8`
- `svelte` moderate severity, installed as `5.53.7`

Relevant package files:

- `frontend/package.json:20` - `@sveltejs/vite-plugin-svelte`
- `frontend/package.json:22` - `svelte`
- `frontend/package-lock.json:1537` - `devalue`
- `frontend/package-lock.json:1878` - `postcss`
- `frontend/package-lock.json:2038` - `svelte`

### Reproduction / Verification

Run:

```powershell
cd frontend
npm audit --audit-level=moderate
npm ls svelte devalue postcss --depth=2
```

### Recommended Fix

1. Run `npm audit fix` and inspect lockfile changes.
2. If audit fix is insufficient, manually bump Svelte and related tooling to patched versions.
3. Keep Vite 7 compatibility in mind.
4. Re-run frontend tests, typecheck, build, and desktop check.

### Acceptance Criteria

- `npm audit --audit-level=moderate` passes or remaining advisories are documented as non-applicable with rationale.
- `npm run test`, `npm run build`, `npm run desktop:check`, and `npm run typecheck` pass.

## P3. News Force Refresh Is Accepted But Ignored - Fixed 2026-05-25

Status: fixed after the audit. `/news/latest` now passes `force_refresh` into `NewsService.latest`, and the service uses a short latest-feed cache that is bypassed and replaced when `force_refresh=true`. Regression coverage in `tests/test_news_service.py` verifies both service behavior and API wiring.

### Impact

The frontend exposes a refresh path for news/SITREP data, but the backend discards the `force_refresh` parameter. Users and agents may believe they are bypassing stale provider cache when they are not.

### Evidence

- `frontend/src/lib/stores/app.ts:1165` - `loadNewsFeed` builds the news URL
- `frontend/src/lib/stores/app.ts:1172` - sends `force_refresh=true`
- `src/api/routes/news.py:11` - route accepts `force_refresh`
- `src/api/routes/news.py:15` - route deletes `force_refresh`
- `src/application/news_service.py:15` - `latest` has no force-refresh parameter

### Reproduction / Verification

1. Add logging or a test spy around the provider/cache layer.
2. Call `/news/latest?force_refresh=true`.
3. Confirm no refresh behavior differs from the default path.

### Recommended Fix

Choose one:

1. Implement true `force_refresh` support in `NewsService.latest`.
2. Remove the parameter from the route and frontend if refresh is intentionally unsupported.

Given user expectations, implementing the backend path is preferable.

### Acceptance Criteria

- A backend test proves `force_refresh=true` bypasses or invalidates stale cache.
- Frontend refresh behavior matches the backend contract.
- If unsupported, the UI no longer sends or implies force refresh.

## P3. UI Styling Has Design-Token Drift And Stale CSS

### Impact

Gamma's active design guidance requires tokenized, dense, flat, research-first UI. Static scans and build warnings show accumulated raw colors, shadows, gradients, pill radii, and unused selectors. Some instances are harmless or intentional overlay exceptions, but the drift makes future UI work less consistent.

### Evidence

Build warnings reported unused CSS selectors in:

- `frontend/src/Shell.svelte`
- `frontend/src/views/CryptoView.svelte`
- `frontend/src/views/PredictionMarketsView.svelte`
- `frontend/src/views/FundamentalsView.svelte`
- `frontend/src/views/SitrepView.svelte`
- `frontend/src/views/RiskView.svelte`
- `frontend/src/views/IvView.svelte`

Design-token drift examples:

- `frontend/src/KeyBindingsWindow.svelte:166` - radial gradient
- `frontend/src/KeyBindingsWindow.svelte:167` - linear gradient
- `frontend/src/KeyBindingsWindow.svelte:183` - box shadow
- `frontend/src/components/TabBar.svelte:304` - `border-radius: 99px`
- `frontend/src/components/TabBar.svelte:349` - gradient treatment
- `frontend/src/components/TabBar.svelte:350` - shadow treatment
- `frontend/src/components/AllocationDonut.svelte:271` - box shadow
- `frontend/src/components/SearchDropdown.svelte:171` - box shadow; may be acceptable as an overlay exception

### Reproduction / Verification

Run:

```powershell
cd frontend
npm run build
rg -n "rgba\(|#[0-9a-fA-F]{3,8}|box-shadow|linear-gradient|radial-gradient|border-radius:\s*99" src
```

Review matches against `docs/design_principles.md` and `frontend/src/lib/theme/tokens.css`.

### Recommended Fix

1. Remove unused selectors reported by build.
2. Replace raw color values with theme tokens where token equivalents exist.
3. Remove decorative gradients/shadows from structural UI.
4. Keep documented exceptions only for overlays, focus rings, and data-visualization internals where tokens are insufficient.
5. Re-run a visual browser pass after CSS cleanup.

### Acceptance Criteria

- `npm run build` no longer reports unused selectors.
- Static scan has no unexplained raw color or decorative treatment matches in structural UI.
- UI remains dense and legible after cleanup.

## P3. Frontend Main Bundle Is Large

### Impact

The production frontend build emits a large main JavaScript chunk. In Tauri this is less urgent than on the public web, but it still affects startup time, memory, and future maintainability.

### Evidence

`npm run build` produced a warning for:

- `assets/main-CKykYV9_.js` around 2,054.96 kB minified
- gzip size around 558.02 kB

Likely contributors include large route/view modules and map/chart dependencies.

### Reproduction / Verification

Run:

```powershell
cd frontend
npm run build
```

Inspect the generated chunk warning. For deeper diagnosis, add a bundle visualizer in a separate change.

### Recommended Fix

1. Dynamically import heavy tab views by route/tab.
2. Consider splitting map-heavy code paths such as maritime/map modules.
3. Consider splitting large domain workspaces such as Commodities and Fundamentals.
4. Avoid premature splitting of tiny shared components.

### Acceptance Criteria

- Main chunk warning is removed or materially reduced.
- App startup remains correct in dev, production build, and Tauri shell.
- Tab transitions still load predictably with loading states where needed.

## Suggested Work Order

1. `Done 2026-05-25` Fix cache key path containment and add hostile-key tests.
2. Add local API session-token protection for mutating and expensive refresh routes.
3. Add request bounds for Risk, Strategy Lab, Crypto, and Prediction Markets.
4. Restore green frontend tests by resolving Commodities view/test drift.
5. Add and fix `npm run typecheck`.
6. Update vulnerable frontend dependencies.
7. `Done 2026-05-25` Implement or remove News `force_refresh`.
8. Clean CSS token drift and unused selectors.
9. Split the frontend bundle after correctness and security issues are closed.

## Standard Validation Gate After Fixes

Run these commands before marking any packet complete:

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm run test
npm run build
npm run desktop:check
npm audit --audit-level=moderate
```

After adding the script, also run:

```powershell
cd frontend
npm run typecheck
```
