# Roadmap Readiness Checklist

## Purpose

This is the execution checklist for the next agent before, and while, Gamma starts roadmap-aligned expansion work.

Use this document when the question is not "what should Gamma build next?" but "what must be true before roadmap work is safe to start?"

Read it together with:

- `C:\Users\User\Desktop\StrataLab\roadmap.md`
- `C:\Users\User\Desktop\StrataLab\README.md`
- `C:\Users\User\Desktop\StrataLab\migration.md`
- `C:\Users\User\Desktop\StrataLab\docs\p1_refactor_handoff.md`

## Current Decision

As of March 13, 2026:

- the migration is largely complete,
- IV live usability is not a blocker by itself if proper options-market-data subscriptions are not available yet,
- provider/runtime generalization and risk semantics have now been hardened to roadmap-readiness level,
- packaged desktop build and installed-workflow validation have both been completed,
- Gamma is ready to begin roadmap work from this branch, with only accepted deferrals remaining.

## Hard Blockers

- [x] Provider/runtime assumptions are no longer hardwired to `STK / SMART / USD`
  Evidence to collect:
  - `src/application/runtime.py` and `src/services/data_providers.py` can describe or load instruments without assuming IBKR equities defaults for every new domain
  - new data domains can plug into a provider adapter boundary without parallel app graphs

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

- [x] `cd frontend && npm run test`
  March 12, 2026 result: `15 passed`

- [x] `cd frontend && npm run build`

- [x] `cargo check --manifest-path frontend\src-tauri\Cargo.toml`

- [x] `cd frontend && npm run backend:smoke`

- [x] `cd frontend && npm run desktop:smoke`

- [x] `cd frontend && npm run tauri:build`
  March 12, 2026 follow-up result: passed and produced `C:\Users\User\AppData\Local\Temp\gamma-tauri-build\release\bundle\nsis\Gamma_0.1.0_x64-setup.exe`

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

- [ ] One-shot `/iv/surface` loads are reliable enough for live use
  Current audit note:
  - the one-shot path returned no surface with the default 2.5s wait
  - the long-running IV session produced a usable surface only after a much longer warm-up

- [ ] IV `auto` mode semantics match the rest of the app

## Recommended Agent Order

1. Start roadmap implementation from this explicit baseline.
2. Keep IV on maintenance-only status unless shared market-data behavior is being touched.
3. Preserve the provider-adapter, normalized-schema, cache, and provenance boundaries defined in `roadmap.md`.
4. Treat longer-session live QA as burn-in follow-up, not as a roadmap-start gate.

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
