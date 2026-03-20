# P1 Refactor Handoff (Archived)

This archived handoff captures the Phase 1 pre-roadmap refactor state as of March 2026. It is preserved for auditability, not as the current execution brief.

## Purpose

This document is the current handoff for finishing Phase 1 foundation work before Gamma starts roadmap expansion.

It is no longer just an identity-rekey note. It now serves as the pre-roadmap readiness brief for the next agent:

- what foundation work is already complete,
- what the March 12, 2026 audit verified,
- what still blocks roadmap work,
- what to avoid spending time on right now.

Read this together with:

- `C:\Users\User\Desktop\Gamma\roadmap.md`
- `C:\Users\User\Desktop\Gamma\docs\archive\migration.md`
- `C:\Users\User\Desktop\Gamma\README.md`

## Repo State

- Baseline checkpoint on `main`: `b72bd9f` (`Checkpoint current UI and desktop changes`)
- Active branch: `codex/p1-foundation-refactor`
- Earlier refactor commit on branch: `452da6b` (`Refactor research validation and identity scaffolding`)
- Previous handoff doc commit: `d57018a` (`Add P1 refactor handoff notes`)
- Current `HEAD`: `6b782c2` (`Fix IBKR FX pair resolution`)
- Current working tree is dirty beyond `HEAD`; inspect `git status` before editing

## Current Goal

The immediate goal is to restore a truly roadmap-ready baseline after the March 14, 2026 follow-up audit found remaining correctness and reproducibility gaps.

That means:

1. keep Gamma read-only and research-focused,
2. preserve the runtime/provider separation work,
3. make cross-domain data adapters possible,
4. keep high-signal live regressions contained,
5. avoid spending time on low-priority UI expansion.

## Follow-Up Status (March 12, 2026)

The pre-roadmap hardening pass moved materially forward after the original audit snapshot:

- backend runtime now omits desktop-only `AppDataContext` state unless the explicit desktop runtime is requested
- research instrument defaults are configurable and benchmark defaults are now separated from research-instrument defaults
- risk coverage semantics were corrected to use modeled risk basis rather than raw net liquidation, with test coverage for margined/live-style books
- provenance expectations for new roadmap entities are now defined in `C:\Users\User\Desktop\Gamma\docs\provenance_expectations.md`
- `cd frontend && npm run tauri:build` now completes and produces an NSIS installer artifact

March 13, 2026 audit follow-up:

- installed-workflow smoke validation of the generated NSIS bundle now passed through a silent temp install
- launched installed `gamma-shell.exe` successfully and verified bundled backend health on `http://127.0.0.1:8000/health`
- direct live runtime probing against the configured TWS path succeeded for:
  - portfolio snapshot
  - portfolio performance
  - research analysis
  - risk computation
- risk-basis coverage semantics were tightened further so fully covered cash-heavy books no longer look artificially under-covered

March 14, 2026 audit follow-up:

- backend tests still passed (`69 passed`)
- frontend tests still passed (`15 passed`)
- `npm run build`, `npm run backend:smoke`, and `npm run desktop:smoke` still passed
- stale ignored rename-era output under `frontend\src-tauri\target\` and `frontend\src-tauri\target-check\` was identified as the reason direct `cargo check --manifest-path frontend\src-tauri\Cargo.toml` had failed
- desktop compile validation is now standardized on `cd frontend && npm run desktop:check`, which isolates `CARGO_TARGET_DIR` to `%TEMP%\gamma-tauri-check`
- direct plain `cargo check --manifest-path frontend\src-tauri\Cargo.toml` also passes again in this workspace because `.cargo\config.toml` routes plain Cargo output to the repo-root `target\` tree
- mixed-currency portfolio, research, and risk analytics now normalize non-base-currency histories into the snapshot base currency before return computation
- portfolio and risk benchmark conversion now use the resolved benchmark quote currency instead of assuming USD
- spot-FX fallback now emits explicit warnings when historical FX series are unavailable
- post-fix validation passed with `75` backend tests, `15` frontend tests, and a successful frontend production build

March 14, 2026 full audit follow-up:

- backend tests passed again (`75 passed`)
- frontend tests passed again (`16 passed`)
- `npm run desktop:check`, direct `cargo check`, `npm run backend:smoke`, `npm run desktop:smoke`, and `npm run tauri:build` all passed from this workspace
- browser-level mock smoke validated portfolio rendering and risk computation through the web UI
- current-session live runtime revalidation did not complete because `build_runtime(mock_mode=False)` reported `IBKR not connected`

## Roadmap Start Decision

Gamma can start roadmap expansion from this working tree.

IV readiness by itself is not the thing that should block roadmap progress.

If live options-market-data subscriptions are not available yet, treat IV live usability as a deferred validation problem rather than a roadmap gate.

Remaining follow-up work now separates into blockers and non-blockers.

Blockers:

1. none

Accepted non-blockers:

1. IV one-shot live behavior should stay documented maintenance work
2. broader live-IBKR and longer-session live QA are still useful but can run in parallel

## What Was Already Done

### Research request validation

Implemented and verified.

- Added shared validation module: `src/application/research_validation.py`
- Enforced validation in:
  - `src/application/research_service.py`
  - `src/api/routes/research.py`
- Reused validation in the Qt-side helper:
  - `src/services/app_context.py`
- Invalid synthetic research payloads now fail fast with `422` on the API path
- Covered cases:
  - duplicate synthetic symbols
  - non-positive synthetic weights
  - inconsistent scope payloads
- Validation allows duplicate display symbols only when they resolve to distinct `instrument_id` values

### Instrument identity rekey

Substantially implemented, additive compatibility preserved.

- Added identity helper module: `src/models/instruments.py`
- Added shared snapshot identity mapping helper: `src/application/instrument_identity.py`
- Extended domain models:
  - `src/models/app_mode.py`
  - `src/models/portfolio.py`
- Added additive fields such as:
  - `instrument_id`
  - `display_symbol`
  - `exchange`
  - `primary_exchange`
  - `provider`
  - `provider_id`
- Threaded identity fields through the domain, API, service, and frontend layers
- Rekeyed research, portfolio-performance, and risk internals from `symbol` to `instrument_id`
- Preserved `symbol` and `display_symbol` in API responses for compatibility

### Backend state isolation

Implemented to the level required for roadmap-readiness work.

- Removed backend-global research scope/snapshot mutation from the FastAPI path
- Diagnostics no longer reflect hidden per-request research scope
- Split shared research time-series caching out of `AppDataContext` into:
  - `src/services/research_cache.py`
- `AppDataContext` is now much closer to a desktop-only workspace object

Current limitation:

- the broader app is still IBKR-first overall,
- but the backend/runtime boundary no longer depends on desktop-only state,
- and research/benchmark instrument defaults are now configurable rather than hardwired in the research path.

## March 12, 2026 Audit Snapshot

### Documentation reviewed

- `roadmap.md`
- `README.md`
- `docs/archive/migration.md`

### Automated checks run

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result: `67 passed`

Frontend tests:

```powershell
cd frontend
npm run test
```

Result: `15 passed`

Frontend production build:

```powershell
cd frontend
npm run build
```

Result: passed

Rust/Tauri compile check:

```powershell
cargo check --manifest-path frontend\src-tauri\Cargo.toml
```

Result: passed

Packaged backend smoke:

```powershell
cd frontend
npm run backend:smoke
```

Result: passed

Desktop launcher smoke:

```powershell
cd frontend
npm run desktop:smoke
```

Result: passed

### Live IBKR verification

A direct non-mock runtime probe was run on March 12, 2026 against the configured TWS path.

Verified:

- runtime connected successfully to `127.0.0.1:7496`
- configured account resolved successfully
- managed account discovery worked
- account values populated
- live positions populated
- diagnostics returned live cache/account evidence

This means IBKR readiness is real, not just nominal.

### Visual inspection summary

Live browser inspection covered:

- landing/connect flow
- portfolio workspace
- research workspace
- risk workspace
- IV workspace

Observed:

- portfolio flow is usable,
- research flow is usable,
- risk flow is usable,
- IV backend can return data,
- IV one-shot live loading is still unreliable.

## Current Findings That Matter For Pre-Roadmap Work

### Finding 1: provider/runtime generalization was the main architectural gap

The roadmap requires provider adapters and normalized entities that can support prediction markets, crypto, fundamentals, and AI context.

The follow-up refactor addressed the highest-signal blocker in the current research/provider path:

- `src/services/data_providers.py`
- `src/application/runtime.py`

What is now true:

- backend runtime no longer builds desktop-only `AppDataContext` state by default
- desktop runtime attaches workspace state explicitly
- research defaults are configurable through runtime/env settings
- benchmark defaults are now separate from research-instrument defaults
- same-symbol instruments can keep distinct identities and cache keys

Remaining implication:

- provider adapters for new roadmap domains still need to be built,
- but the pre-roadmap blocker is no longer the old `STK / SMART / USD` hardwiring in the research/runtime path.

### Finding 2: risk coverage semantics were misleading on live books, and are now corrected

Live audit reproduced a concrete issue in the current risk service:

- `portfolio_value = 58709.18`
- `covered_portfolio_value = 67722.18`
- `risk_coverage_ratio = 1.1535`

That was a real output from the earlier code path.

The current implementation compares:

- `snapshot.net_liquidation`

against:

- summed included `base_market_value`

The follow-up refactor changed the model to compare covered risky exposure against an explicit risk basis rather than raw net liquidation, and added test coverage for margined/live-style books.

Files:

- `src/application/risk_service.py`

Current implication:

- the risk outputs are materially safer than before for single-currency and covered-book semantics,
- but that does not by itself make the historical analytics pipeline safe for mixed-currency books.

### Finding 3: mixed-currency historical analytics are now base-currency-correct

This blocker was closed in the March 14, 2026 follow-up fix.

What changed:

- added a shared historical-series normalization helper at the provider boundary in `src/services/data_providers.py`
- portfolio, research, and risk now convert non-base-currency position histories into the snapshot base currency before computing returns
- portfolio and risk benchmark conversion now use the benchmark instrument's resolved quote currency rather than assuming USD
- spot-FX fallback now emits explicit warnings when historical FX is unavailable

Coverage added:

- mixed-currency portfolio performance
- mixed-currency research analysis
- mixed-currency risk computation
- non-USD benchmark conversion using resolved benchmark currency

### Finding 4: repo rename fallout affected desktop validation and is now normalized

The folder rename from `StrataLab` to `Gamma` left stale local build state behind.

Observed in the March 14, 2026 audit:

- direct `cargo check --manifest-path frontend\src-tauri\Cargo.toml` failed because the local `frontend\src-tauri\target\...` build output still referenced generated permissions under `C:\Users\User\Desktop\StrataLab\...`
- wrapped scripts such as `npm run desktop:smoke` still passed because `frontend/scripts/run-tauri.mjs` overrides `CARGO_TARGET_DIR` into `%TEMP%`
- docs and handoff notes still contained `StrataLab` absolute paths before this update

Fix now in place:

- `frontend\package.json` now exposes `cd frontend && npm run desktop:check` as the supported compile-validation path
- `frontend\scripts\check-tauri.mjs` isolates `CARGO_TARGET_DIR` to `%TEMP%\gamma-tauri-check` unless overridden
- `.cargo\config.toml` routes plain Cargo output to the repo-root `target\` tree instead of the stale checked-out Tauri target directories
- direct plain `cargo check --manifest-path frontend\src-tauri\Cargo.toml` now passes again from the current `Gamma` checkout

Implication:

- another agent should use `cd frontend && npm run desktop:check` for reproducible desktop validation after any future workspace move
- if plain cargo output ever drifts after a rename or path move, treat `frontend\src-tauri\target\` and `target-check\` as disposable ignored build output and rely on `cd frontend && npm run desktop:check` before treating it as a product regression
- this is primarily a reproducibility and operator-trust issue, not a product-logic issue

### Finding 5: IV web flow has a live regression

IV is not a current roadmap priority, but the regression should be documented clearly so another agent does not waste time rediscovering it.

Observed live:

- one-shot `/iv/surface` returned no payload with the default `2.5s` wait,
- the IV session path eventually produced a usable delayed surface,
- the web IV flow therefore remains unreliable for one-shot live use.

Current high-signal causes:

- `src/application/iv_service.py` stops the temporary IV engine after a short fixed wait before a first live snapshot is reliably available,
- the IV engine treats `auto` like delayed mode instead of matching the rest of the app's live-then-fallback behavior,
- live option subscriptions still emit contract-definition errors during startup.

Files:

- `src/application/iv_service.py`
- `src/services/iv_surface_engine.py`

Implication:

- do not expand IV right now,
- if someone touches this path incidentally, do the smallest fix necessary so one-shot loads and mode semantics are predictable.

## Non-Goals Right Now

### IV is on the backburner

Do not delete it.
Do not deactivate it.
Do not spend roadmap-prep time expanding it.

IV live usability is an accepted non-blocker for roadmap start unless the current work directly depends on shared IV/session or market-data behavior.

Only touch IV if:

- a regression blocks basic current use, or
- a refactor incidentally breaks it and a small compatibility fix is needed.

### Do not expand IV beyond maintenance

Prediction markets, crypto, fundamentals, and AI copilot work should wait until the blockers above are addressed.

The remaining constraint is that IV should stay on maintenance-only status unless the work directly touches shared market-data/session behavior.

## Recommended Next Slice

The next agent should start roadmap implementation from the cleaned readiness baseline, not reopen already-closed foundation questions unless a concrete regression appears.

### Priority 1

Keep the clean-target desktop validation path as the supported operator workflow.

Target outcome:

- `cd frontend && npm run desktop:check` remains the documented compile-validation command
- stale `StrataLab` path references stay out of operator-facing docs except as explicit historical audit context

### Priority 2

Do the minimum IV compatibility fix if touched.

Target outcome:

- one-shot IV loading and market-data-mode behavior are predictable enough that another agent does not have to rediscover the live failure mode

Concrete direction:

- do the smallest backend fix that improves one-shot IV reliability or makes the failure mode explicit
- align IV `auto` mode semantics with the rest of the market-data stack if that path is touched
- do not redesign the IV feature

### Priority 3

Expand tests around roadmap-readiness constraints.

Add tests for:

- stateless API behavior under repeated research requests
- identity-aware behavior in more edge cases
- risk coverage semantics on nontrivial books
- provider-boundary behavior staying additive and compatible

## Key Files To Read First

- `src/application/runtime.py`
- `src/services/data_providers.py`
- `src/application/risk_service.py`
- `src/services/app_context.py`
- `src/api/routes/system.py`
- `src/api/routes/research.py`
- `src/api/schemas/research.py`
- `src/api/schemas/risk.py`
- `frontend/src/lib/stores/app.ts`
- `frontend/src/App.svelte`
- `tests/test_api.py`
- `tests/test_research_service.py`
- `tests/test_app_mode_logic.py`

## Current Working Tree Notes

- The working tree is dirty; do not assume the doc matches committed state only
- Root `.playwright-cli/` artifacts are generated local inspection output and should remain ignored
- `frontend\src-tauri\target\` and `frontend\src-tauri\target-check\` are disposable ignored local build directories; if a future workspace move poisons plain `cargo check`, use `cd frontend && npm run desktop:check` or clear those directories before treating it as a product regression

## Handoff Prompt

Use this prompt for the next agent:

```text
You are continuing Gamma pre-roadmap foundation work on branch `codex/p1-foundation-refactor`.

Start by reading:
- C:\Users\User\Desktop\Gamma\roadmap.md
- C:\Users\User\Desktop\Gamma\docs\archive\migration.md
- C:\Users\User\Desktop\Gamma\README.md
- C:\Users\User\Desktop\Gamma\docs\archive\p1_refactor_handoff.md

Current git state:
- `main` baseline checkpoint: b72bd9f (`Checkpoint current UI and desktop changes`)
- earlier refactor commit on this branch: 452da6b (`Refactor research validation and identity scaffolding`)
- previous handoff-doc commit: d57018a (`Add P1 refactor handoff notes`)
- current HEAD when the handoff doc was updated: 6b782c2 (`Fix IBKR FX pair resolution`)
- the working tree is dirty; inspect `git status` before proceeding

What is already true:
- research validation exists and `/research/analyze` returns 422 for invalid synthetic payloads
- additive identity fields exist through the domain/API/frontend stack
- research, portfolio, and risk internals have mostly been rekeyed to `instrument_id`
- API-global research scope mutation was removed
- backend/runtime safety is better than before
- automated checks were green during the March 12, 2026 audit
- live IBKR validation succeeded against the configured TWS path
- desktop compile validation is now standardized on `cd frontend && npm run desktop:check`
- plain `cargo check --manifest-path frontend\src-tauri\Cargo.toml` also works again because `.cargo\config.toml` routes it to the repo-root `target\` tree

What is not blocking roadmap work:
- desktop compile validation no longer depends on stale rename-era target artifacts in this workspace
- installed-workflow validation of the generated NSIS bundle is complete
- mixed-currency portfolio, research, and risk analytics now normalize into the snapshot base currency before return computation

What is no longer blocking roadmap work by itself:
- IV still has known live issues, but IV is not a current priority and is not a blocker by itself

Important constraint:
- Do not delete or disable IV
- Do not spend major time expanding IV
- Keep Gamma read-only and aligned with the roadmap

Validation note:
- use `cd frontend && npm run desktop:check` for reproducible desktop compile validation
- treat `frontend\src-tauri\target\` and `frontend\src-tauri\target-check\` as disposable ignored local build output

Your task:
1. Preserve the shared mixed-currency normalization path across portfolio, research, risk, and benchmarks if you touch historical analytics.
2. If your changes touch IV behavior, only do the minimum fix needed so one-shot loads and market-data-mode behavior are predictable.
3. Run relevant tests before finishing.

Suggested starting files:
- C:\Users\User\Desktop\Gamma\src\application\portfolio_service.py
- C:\Users\User\Desktop\Gamma\src\application\research_service.py
- C:\Users\User\Desktop\Gamma\src\application\risk_service.py
- C:\Users\User\Desktop\Gamma\src\services\data_providers.py
- C:\Users\User\Desktop\Gamma\frontend\scripts\run-tauri.mjs
- C:\Users\User\Desktop\Gamma\tests\test_api.py
- C:\Users\User\Desktop\Gamma\tests\test_risk_tab_logic.py
- C:\Users\User\Desktop\Gamma\tests\test_research_service.py

Be incremental. Prefer additive model changes, compatibility shims, and test-backed refactors.
```
