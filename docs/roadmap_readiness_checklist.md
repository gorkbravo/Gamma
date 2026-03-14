# Roadmap Readiness Checklist

## Purpose

This is the execution checklist for the next agent before, and while, Gamma starts roadmap-aligned expansion work.

Use this document when the question is not "what should Gamma build next?" but "what must be true before roadmap work is safe to start?"

Read it together with:

- `C:\Users\User\Desktop\Gamma\roadmap.md`
- `C:\Users\User\Desktop\Gamma\README.md`
- `C:\Users\User\Desktop\Gamma\migration.md`
- `C:\Users\User\Desktop\Gamma\docs\p1_refactor_handoff.md`

## Current Decision

As of March 14, 2026:

- the migration is largely complete,
- IV live usability is not a blocker by itself if proper options-market-data subscriptions are not available yet,
- provider/runtime generalization and risk coverage semantics have improved materially,
- packaged desktop build and installed-workflow validation have both been completed,
- desktop compile validation is now reproducible from this workspace through a clean-target command and an isolated plain-Cargo target directory,
- Gamma is ready to begin roadmap expansion from this working tree, with only the accepted non-blockers below still open.

## Hard Blockers

- [x] Provider/runtime assumptions are no longer hardwired to `STK / SMART / USD`
  Evidence to collect:
  - `src/application/runtime.py` and `src/services/data_providers.py` can describe or load instruments without assuming IBKR equities defaults for every new domain
  - new data domains can plug into a provider adapter boundary without parallel app graphs

- [x] Historical analytics are base-currency-correct for mixed-currency books
  Evidence to collect:
  - portfolio performance converts non-base-currency position histories before combining them with `base_market_value` weights
  - research analytics convert non-base-currency constituent histories before combining them with normalized weights
  - risk analytics include FX effects for non-base-currency instruments instead of applying base-currency exposures to local-currency return series
  - benchmark conversion uses the resolved benchmark quote currency rather than assuming USD
  - spot-FX fallback emits warnings when historical FX is unavailable
  - tests cover at least one mixed-currency portfolio/research/risk path end-to-end

- [x] Risk coverage semantics are trustworthy and test-backed
  Evidence to collect:
  - `risk_coverage_ratio` is either a real completeness ratio or renamed to match what it actually means
  - live-style books with cash, leverage, or margin cannot produce misleading headline coverage numbers without an explicit warning/model explanation
  - tests cover the chosen semantics

- [x] Full packaged desktop build completes and produces a verifiable installer artifact
  Evidence to collect:
  - `npm run tauri:build` completes end-to-end
  - final installer output exists under the expected bundle path
  - installed workflow is smoke-checked, not just backend startup

- [x] Desktop validation commands are reproducible after the repo rename from `StrataLab` to `Gamma`
  Evidence to collect:
  - supported compile validation uses `cd frontend && npm run desktop:check`, which isolates `CARGO_TARGET_DIR` into `%TEMP%\gamma-tauri-check`
  - direct `cargo check --manifest-path frontend\src-tauri\Cargo.toml` also works in the current workspace because `.cargo\config.toml` routes plain Cargo output to the repo-root `target\` tree
  - operator-facing docs no longer reference `C:\Users\User\Desktop\StrataLab\...` outside explicit historical audit context
  - stale rename fallout in generated local directories is isolated as disposable ignored build output rather than part of the supported validation contract

- [x] Provenance expectations are defined for new roadmap entities
  Evidence to collect:
  - source/provider
  - retrieval timestamp
  - endpoint/module origin
  - transformation note for derived metrics
  - baseline documented in `docs/provenance_expectations.md`

## Accepted Non-Blockers

- [x] IV tab live usability can remain partial if missing subscriptions make proper validation impossible today
- [x] PySide fallback can remain during burn-in
- [x] Advanced desktop ergonomics and saved-workspace polish can lag roadmap start
- [x] IV can stay on maintenance-only status unless roadmap work directly touches shared market-data/session behavior

## Baseline Validation

- [x] `.\.venv\Scripts\python.exe -m pytest`
  March 12, 2026 follow-up result: `68 passed`
  March 13, 2026 current result: `69 passed`
  March 14, 2026 mixed-currency follow-up result: `75 passed`

- [x] `cd frontend && npm run test`
  March 12, 2026 result: `15 passed`
  March 14, 2026 full-audit result: `16 passed`

- [x] `cd frontend && npm run build`
  March 14, 2026 full-audit result: passed

- [x] `cd frontend && npm run desktop:check`
  March 14, 2026 result: passed and isolated desktop compile validation to `%TEMP%\gamma-tauri-check`

- [x] `cargo check --manifest-path frontend\src-tauri\Cargo.toml`
  March 14, 2026 historical audit result: failed in the local checked-out `frontend\src-tauri\target\` tree because stale generated permissions still referenced `C:\Users\User\Desktop\StrataLab\...`
  March 14, 2026 post-fix result: passed after `.cargo\config.toml` redirected plain Cargo output to the repo-root `target\` tree

- [x] `cd frontend && npm run backend:smoke`
  March 14, 2026 result: passed and rebuilt the packaged backend under `frontend\src-tauri\resources\backend\gamma-backend\`

- [x] `cd frontend && npm run desktop:smoke`
  March 14, 2026 result: passed through the wrapped Tauri dev launcher

- [x] `cd frontend && npm run tauri:build`
  March 12, 2026 follow-up result: passed and produced `C:\Users\User\AppData\Local\Temp\gamma-tauri-build\release\bundle\nsis\Gamma_0.1.0_x64-setup.exe`
  March 14, 2026 full-audit result: passed and rebuilt `C:\Users\User\AppData\Local\Temp\gamma-tauri-build\release\bundle\nsis\Gamma_0.1.0_x64-setup.exe`

- [x] Installed NSIS workflow launches successfully
  March 13, 2026 result:
  - silent install succeeded into `C:\Users\User\AppData\Local\Temp\gamma-install-test`
  - installed `gamma-shell.exe` launched successfully
  - bundled backend answered `GET /health` with `200 OK`

## Live Runtime Sanity

- [x] IBKR connection toggle works against the configured TWS path
- [x] Diagnostics show managed account discovery, account values, and live positions
- [x] Portfolio workspace loads a real live book
- [x] Research workspace runs on live-delayed data
- [x] Research handoff into Risk works
- [x] IV session mode can eventually produce a live-delayed surface
- [ ] March 14, 2026 full-audit live IBKR revalidation
  Current audit note:
  - `build_runtime(mock_mode=False)` reported `IBKR not connected`
  - live portfolio snapshot returned zero positions with `Net liquidation unavailable` and `Cash balance unavailable`
  - this audit therefore revalidated mock/web/desktop behavior only, and relies on the earlier March 13 live evidence for roadmap readiness

- [ ] One-shot `/iv/surface` loads are reliable enough for live use
  Current audit note:
  - the one-shot path returned no surface with the default 2.5s wait
  - the long-running IV session produced a usable surface only after a much longer warm-up

- [ ] IV `auto` mode semantics match the rest of the app

## Recommended Agent Order

1. Use `cd frontend && npm run desktop:check` as the reproducible desktop compile-validation path, and treat `frontend\src-tauri\target\` plus `target-check\` as disposable local build output.
2. Keep IV on maintenance-only status unless shared market-data behavior is being touched.
3. Preserve the provider-adapter, normalized-schema, cache, and provenance boundaries defined in `roadmap.md`.
4. Keep mixed-currency analytics on the shared normalization path rather than reintroducing ad hoc local-currency return handling.

## Evidence Log Template

Use this section format when another agent updates the checklist:

```text
Date:
Branch:
Commit:
Commands run:
- ...

Verified:
- ...

Open blockers:
- ...

Accepted deferrals:
- ...
```

## Evidence Log

Date:
March 12, 2026

Branch:
`codex/p1-foundation-refactor`

Commands run:
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\python.exe -m pytest tests\test_app_mode_logic.py tests\test_risk_tab_logic.py tests\test_api.py`
- `cd frontend && npm run test`
- `cd frontend && npm run build`
- `cargo check --manifest-path frontend\src-tauri\Cargo.toml`
- `cd frontend && npm run backend:smoke`
- `cd frontend && npm run desktop:smoke`
- `cd frontend && npm run tauri:build`

Verified:
- backend runtime no longer constructs desktop-only `AppDataContext` state by default
- desktop runtime still attaches `AppDataContext` explicitly for Qt flows
- research-provider defaults are configurable and benchmark defaults are now separate from research-instrument defaults
- risk coverage is modeled against explicit risk basis rather than raw net liquidation, with test coverage for missing-value and margined-book cases
- provenance baseline is documented in `docs/provenance_expectations.md`
- NSIS bundle build completed and installer artifact exists at `C:\Users\User\AppData\Local\Temp\gamma-tauri-build\release\bundle\nsis\Gamma_0.1.0_x64-setup.exe`

Open blockers:
- none

Accepted deferrals:
- IV one-shot live reliability remains maintenance-only and is not a roadmap-start blocker
- longer-session live QA is still advisable, but it is not a blocker for roadmap start

Date:
March 13, 2026

Branch:
`codex/p1-foundation-refactor`

Commands run:
- `.\.venv\Scripts\python.exe -m pytest`
- `cd frontend && npm run backend:smoke`
- `cd frontend && npm run test`
- `cd frontend && npm run build`
- `cargo check --manifest-path frontend\src-tauri\Cargo.toml`
- `cd frontend && npm run desktop:smoke`
- `cd frontend && npm run tauri:build`
- `C:\Users\User\AppData\Local\Temp\gamma-tauri-build\release\bundle\nsis\Gamma_0.1.0_x64-setup.exe /S /D=C:\Users\User\AppData\Local\Temp\gamma-install-test`
- `cmd /c start "" "C:\Users\User\AppData\Local\Temp\gamma-install-test\gamma-shell.exe"`
- `Invoke-WebRequest http://127.0.0.1:8000/health`
- live runtime probe against configured TWS using `build_runtime(mock_mode=False)`

Verified:
- installed NSIS bundle can be silently installed and launched
- installed shell starts the bundled backend successfully
- live IBKR portfolio snapshot, portfolio performance, research analysis, and risk computation all executed against the configured TWS path
- cash-heavy live books now treat fully covered risky exposure as fully covered, avoiding misleading risk-basis scaling

Open blockers:
- none

Accepted deferrals:
- IV one-shot live reliability remains maintenance-only and is not a roadmap-start blocker
- longer-session live QA remains advisable but is not a roadmap-start blocker

Date:
March 14, 2026

Branch:
`codex/p1-foundation-refactor`

Commands run:
- `.\.venv\Scripts\python.exe -m pytest`
- `cd frontend && npm run test`
- `cd frontend && npm run build`
- `cd frontend && npm run desktop:check`
- `cargo check --manifest-path frontend\src-tauri\Cargo.toml`
- `cd frontend && npm run backend:smoke`
- `cd frontend && npm run desktop:smoke`
- `cd frontend && npm run tauri:build`
- Playwright browser smoke against the mock web stack (`portfolio` render + `risk` compute)
- live runtime probe via `build_runtime(mock_mode=False)`

Verified:
- backend tests passed (`75 passed`)
- frontend tests passed (`16 passed`)
- frontend production build, packaged backend smoke, wrapped desktop smoke, direct Cargo compile check, clean-target desktop compile check, and full Tauri packaging all passed
- mock web workflow smoke loaded portfolio data and computed risk successfully through the browser UI
- warning surfaces remained explicit in the UI for FX spot fallback and missing benchmark history

Open blockers:
- none

Accepted deferrals:
- this audit did not revalidate live IBKR because the runtime reported `IBKR not connected`; roadmap readiness still relies on the earlier March 13 live evidence plus the current automated and mock-workflow audit
- IV one-shot live reliability remains maintenance-only and is not a roadmap-start blocker

Date:
March 14, 2026

Branch:
`codex/p1-foundation-refactor`

Commit:
`75d07d5`

Commands run:
- `cargo check --manifest-path frontend\src-tauri\Cargo.toml`
- `cd frontend && npm run desktop:check`
- `cd frontend && npm run desktop:smoke`
- `cd frontend && npm run build`

Verified:
- stale ignored Tauri build output under `frontend\src-tauri\target\` and `frontend\src-tauri\target-check\` was the root cause of the rename-era `StrataLab` path failure
- `frontend\src-tauri\target\` and `target-check\` are disposable local generated artifacts and are not part of the supported validation contract
- `.cargo\config.toml` now routes plain Cargo output to the repo-root `target\` tree so direct `cargo check` no longer reuses the stale checked-out Tauri target directories
- supported desktop compile validation now uses `cd frontend && npm run desktop:check`, which isolates `CARGO_TARGET_DIR` to `%TEMP%\gamma-tauri-check`
- direct plain `cargo check --manifest-path frontend\src-tauri\Cargo.toml` also passes again in the current workspace through the repo-root Cargo target directory
- operator-facing documentation now points at the supported clean-target command and only mentions `StrataLab` as historical audit context

Open blockers:
- none

Accepted deferrals:
- IV one-shot live reliability remains maintenance-only and is not a roadmap-start blocker
- longer-session live QA remains advisable but is not a roadmap-start blocker

Date:
March 14, 2026

Branch:
`codex/p1-foundation-refactor`

Commands run:
- `.\.venv\Scripts\python.exe -m pytest`
- `cd frontend && npm run test`
- `cd frontend && npm run build`
- `cargo check --manifest-path frontend\src-tauri\Cargo.toml`
- `$env:CARGO_TARGET_DIR=[System.IO.Path]::GetFullPath((Join-Path $env:TEMP 'gamma-tauri-check-audit')); cargo check --manifest-path frontend\src-tauri\Cargo.toml`
- `cd frontend && npm run backend:smoke`
- `cd frontend && npm run desktop:smoke`

Verified:
- backend tests still pass (`69 passed`)
- frontend tests still pass (`15 passed`)
- frontend production build still passes
- packaged backend smoke still passes
- wrapped desktop smoke still passes
- direct `cargo check` is no longer reproducible from the checked-out local target tree after the repo rename
- operator docs and handoff notes still contained stale `StrataLab` absolute paths before this documentation update
- portfolio, research, and risk still compute mixed-currency historical analytics from raw local-currency price histories rather than base-currency-normalized return series
- benchmark conversion in portfolio and risk still assumes a USD-quoted benchmark even when benchmark defaults are configurable

Open blockers:
- direct desktop compile validation still depends on cleaning or isolating stale local Tauri build artifacts after the repo rename

Accepted deferrals:
- IV one-shot live reliability remains maintenance-only and is not a roadmap-start blocker
- longer-session live QA remains advisable but is not a roadmap-start blocker

Date:
March 14, 2026

Commands run:
- `.\.venv\Scripts\python.exe -m pytest`
- `cd frontend && npm run test`
- `cd frontend && npm run build`

Verified:
- mixed-currency portfolio, research, and risk analytics now normalize non-base-currency histories into the snapshot base currency before return computation
- benchmark conversion in portfolio and risk now uses the resolved benchmark quote currency instead of assuming USD
- spot-FX fallback emits explicit warnings when historical FX is unavailable
- backend tests now cover mixed-currency portfolio performance, research analysis, risk computation, and non-USD benchmark conversion
- backend tests passed (`75 passed`)
- frontend tests still passed (`15 passed`)
- frontend production build still passed

Open blockers:
- direct desktop compile validation still depends on cleaning or isolating stale local Tauri build artifacts after the repo rename

Accepted deferrals:
- IV one-shot live reliability remains maintenance-only and is not a roadmap-start blocker
- longer-session live QA remains advisable but is not a roadmap-start blocker
