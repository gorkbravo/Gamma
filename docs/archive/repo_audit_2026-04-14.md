# Gamma Full Repo Audit - 2026-04-14

## Scope

This audit reviewed the working tree at `C:\Users\User\Desktop\Gamma` on branch `main`.

I treated the existing uncommitted changes as user-owned work and did not revert them. The working tree already contained:

- deleted archived prompt files under `docs/archive/`
- matching untracked prompt files under `docs/archive/prompts/`
- Fundamentals DCF range changes across backend models, schemas, service code, frontend API types, and `FundamentalsView.svelte`
- a modified Tauri target-dir script

The audit used `roadmap.md` as the product source of truth. The repo remains aligned with the core roadmap boundary: Gamma is a read-only research environment, not an execution platform.

## Validation Results

| Check | Result | Notes |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe -m pytest` | Failed | 139 passed, 2 failed. Both failures are Copilot route tests making live FRED calls through Macro and receiving upstream HTTP 500. |
| `npm run test` | Passed | 66 frontend tests passed. Svelte reported one unused selector in `CryptoView.svelte`. |
| `npm run build` | Passed with warnings | Build succeeded. Warnings: unused `.basket-card p` selector and `main` chunk larger than 500 kB. |
| `npm run desktop:check` | Passed | Cargo check for Tauri shell succeeded. |
| `npm run desktop:smoke` | Passed with noisy logs | Smoke marker passed, but the run logged an attempted duplicate bind on `127.0.0.1:8000` and an Edgar cache permission warning. I cleaned up the leftover smoke processes. |
| `npm run backend:smoke` | Failed | PyInstaller build completed, but the packaged backend executable exited with code 1 before `/health`. Manual run shows missing `edgar/reference/data/secforms.csv` inside the bundled app. |
| `npm audit --audit-level=moderate` | Failed | 3 advisories: `vite` high, `picomatch` high, `devalue` moderate. |
| `.\.venv\Scripts\python.exe -m pip check` | Passed | No broken Python requirements. |

## High Priority Findings

### 1. Packaged backend is currently broken after adding `edgartools`

Severity: High / release blocker for packaged desktop.

`npm run backend:smoke` builds the backend, then the generated executable exits before the health endpoint becomes reachable. Manual execution of `frontend/src-tauri/resources/backend/gamma-backend/gamma-backend.exe` shows:

```text
FileNotFoundError: ... _internal\edgar\reference\data\secforms.csv
[PYI-4460:ERROR] Failed to execute script 'desktop_entry'
```

Relevant files:

- `frontend/scripts/build-backend.mjs`: only `sample_data` and uvicorn hidden imports are explicitly bundled.
- `src/services/fundamentals_adapters.py`: imports `edgar` at module import time, so missing package data prevents the API from starting even if Fundamentals is not used.

Recommended fix:

- Add the required `edgar.reference.data` package data to the PyInstaller build.
- Consider moving `edgar` imports behind the Fundamentals adapter boundary so portfolio/system startup does not fail if optional Fundamentals packaging is incomplete.
- Keep `npm run backend:smoke` as the release gate because it caught a real packaged-runtime failure that normal tests and Tauri cargo check do not catch.

### 2. Backend test suite is not hermetic and currently fails on live FRED

Severity: High for CI/release confidence.

The failing tests are:

- `tests/test_copilot.py::test_macro_copilot_route_returns_structured_research_card`
- `tests/test_copilot.py::test_synthesis_copilot_route_returns_cross_context_research_card`

Both call the real route through `_build_test_client()` and reach `CopilotService._build_macro_context`, which calls:

- `macro_service.get_snapshot(...)`
- `macro_service.get_divergences(...)`
- `macro_service.get_events(...)`

Those calls then hit FRED. During this audit FRED returned HTTP 500, making the local suite fail.

Recommended fix:

- Inject stubbed Macro adapters into Copilot route tests, or add a deterministic test-runtime builder for route tests.
- Add graceful route/service handling so a single upstream macro provider failure becomes a warning/degraded Copilot card rather than an unhandled API failure.

### 3. SEC identity fallback is hard-coded to a personal identity

Severity: High for privacy/configuration hygiene.

`src/services/fundamentals_adapters.py` still contains a TODO and defaults to:

- `Gorka Bravo`
- `gorka.bravo1@gmail.com`

The adapter writes that value to `EDGAR_IDENTITY` and calls `set_identity(...)`. The value also appears in test and smoke logs.

Recommended fix:

- Require `GAMMA_SEC_USER_NAME` and `GAMMA_SEC_USER_EMAIL` for live SEC access, or surface an explicit settings path.
- In mock/test mode, use a non-personal Gamma test identity.
- Avoid logging personal identity values during routine test runs.

### 4. Frontend dependency audit has current high-severity advisories

Severity: Medium-high.

`npm audit --audit-level=moderate` reports:

- `vite` high: dev server file-read/path traversal advisories
- `picomatch` high: glob matching/ReDoS advisories
- `devalue` moderate: prototype pollution advisories

Recommended fix:

- Run and review `npm audit fix`.
- Re-run `npm run test`, `npm run build`, and `npm run desktop:check` after dependency updates.

## Architecture Findings

### Strengths

- The FastAPI route layer is consistently thin and mostly delegates to application services.
- Provider adapters are explicit for major external domains: FRED, Treasury, Polymarket, Kalshi, CoinGecko, GeckoTerminal, SEC/EdgarTools, IBKR.
- Domain models and API schemas are separated, which makes provenance and UI contracts easier to reason about.
- Roadmap-era entities often carry `source_provider`, `retrieved_at`, `origin`, and `transformation_note`, matching `docs/provenance_expectations.md`.
- The repo has meaningful backend and frontend tests across Prediction Markets, Macro, Crypto, Fundamentals, Risk, navigation, stores, and view models.

### Main maintainability risk: domain files are becoming too large

The architecture is sound, but several files are now large enough that future roadmap work will become slower and riskier:

| File | Approx. lines | Risk |
| --- | ---: | --- |
| `src/application/macro_service.py` | 2695 | Mixed metadata, ingestion orchestration, snapshot construction, divergence scoring, event studies, coherence, policy path, and formatting. |
| `src/application/copilot_service.py` | 1959 | Context building, tool execution, synthesis, provider interaction, result shaping, and fallback behavior in one file. |
| `frontend/src/lib/stores/app.ts` | 1678 | Global state, API orchestration, Copilot threading, validation, Macro/Crypto/Fundamentals loaders, Risk/IV actions. |
| `frontend/src/views/FundamentalsView.svelte` | 1664 | UI rendering, DCF editing, projection logic, peer interactions, formatting helpers, CSS. |
| `frontend/src/views/CryptoView.svelte` | 1527 | Multi-mode UI, screener, token detail, synthetic portfolio, liquidity/flow rendering, CSS. |

Recommended direction:

- Split services by subdomain before adding deeper Roadmap V2 work. For example, Macro can separate catalog/metadata, history loading, divergence/coherence analytics, event studies, and policy path construction.
- Split frontend store orchestration by domain module while preserving the current public store API.
- Move view-local financial/crypto formatting and derived rows into view-model modules where tests already exist.

## Product And Documentation Findings

### README roadmap status is stale

`README.md` currently says:

- Phase 2 Macro is `in progress`
- Phase 4 Copilot is `in progress`
- Phase 5 Crypto is `started`
- Phase 6 Fundamentals is `not started`

`roadmap.md` now says:

- Phase 2 Macro is paused around 84%
- Phase 4 Copilot is paused around 70%
- Phase 5 Crypto is paused around 73%
- Phase 6 Fundamentals is paused around 83%

Recommended fix:

- Update the README current roadmap section to match `roadmap.md`.

### Archive docs have broken links after prompt relocation

The working tree deletes several prompt files from `docs/archive/` and adds replacements under `docs/archive/prompts/`, but `docs/archive/README.md` still links to the old paths for at least:

- `phase5_agent_prompt.md`
- `phase6_fundamentals_agent_prompt.md`

Recommended fix:

- Update archive README links to `./prompts/...`.
- Add `docs/archive/prompts/README.md` if this directory is meant to become a stable archive subsection.

### Docs map omits design principles

`docs/design_principles.md` exists, but `docs/README.md` does not list it under active documents.

Recommended fix:

- Add it to `docs/README.md` so UI/design work starts from the right source.

## UX And Observability Findings

### Frontend API errors discard backend details

`frontend/src/lib/api/client.ts` throws only `"<status> <statusText>"` for failed requests. FastAPI error bodies often include useful `detail` strings, but the frontend drops them.

Impact:

- User-facing failures are harder to diagnose.
- Degraded provider states can look like generic `404 Not Found` or `500 Internal Server Error`.

Recommended fix:

- Parse JSON/text error bodies in `getJson` and `postJson`.
- Prefer FastAPI `detail` when available.

### Desktop smoke logs indicate port/cache cleanup fragility

`npm run desktop:smoke` passed, but logged:

- `Failed to clear stale cache entries ... ~/.edgar/_tcache ... Access denied`
- attempted duplicate bind on `127.0.0.1:8000`

Recommended fix:

- Make the desktop launcher smoke use an isolated API port like packaged backend smoke does.
- Consider isolating Edgar cache/config paths in smoke tests.

## Lower Priority Findings

- `npm run build` reports a 556 kB minified main chunk. This is acceptable for a desktop shell today, but code splitting by workspace would help startup as the research surface grows.
- `frontend/src/views/CryptoView.svelte` has an unused `.basket-card p` selector.
- Python dependencies are broad version ranges in both `pyproject.toml` and `requirements.txt`. This is workable for local development, but reproducible packaged releases would benefit from a lock or constraints file.
- `rg` failed with `Access denied` in this environment, so text scanning used PowerShell `Select-String` as fallback.

## Recommended Next Work Order

1. Fix packaged backend startup by bundling EdgarTools package data and re-run `npm run backend:smoke`.
2. Make Copilot route tests deterministic by injecting stub Macro data, then re-run the backend pytest suite.
3. Replace the hard-coded SEC identity fallback with explicit config/settings behavior.
4. Apply and verify the frontend dependency security updates.
5. Update stale README/archive docs.
6. Start decomposing the largest service/store/view files before Roadmap V2 expansion.

