# P1 Refactor Handoff

## Purpose

This document is the current handoff for finishing Phase 1 foundation work before Gamma starts roadmap expansion.

It is no longer just an identity-rekey note. It now serves as the pre-roadmap readiness brief for the next agent:

- what foundation work is already complete,
- what the March 12, 2026 audit verified,
- what still blocks roadmap work,
- what to avoid spending time on right now.

Read this together with:

- `C:\Users\User\Desktop\StrataLab\roadmap.md`
- `C:\Users\User\Desktop\StrataLab\migration.md`
- `C:\Users\User\Desktop\StrataLab\README.md`

## Repo State

- Baseline checkpoint on `main`: `b72bd9f` (`Checkpoint current UI and desktop changes`)
- Active branch: `codex/p1-foundation-refactor`
- Earlier refactor commit on branch: `452da6b` (`Refactor research validation and identity scaffolding`)
- Previous handoff doc commit: `d57018a` (`Add P1 refactor handoff notes`)
- Current `HEAD`: `6b782c2` (`Fix IBKR FX pair resolution`)
- Current working tree is dirty beyond `HEAD`; inspect `git status` before editing

## Current Goal

The immediate goal is to start roadmap work from a now-verified pre-roadmap baseline, while preserving the architectural boundaries that made that transition safe.

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
- provenance expectations for new roadmap entities are now defined in `C:\Users\User\Desktop\StrataLab\docs\provenance_expectations.md`
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

What still remains open before the checklist is fully clean:

1. IV one-shot live behavior remains documented maintenance work, not a roadmap blocker

## Roadmap Start Decision

Gamma is now ready to start roadmap work from this branch.

IV readiness by itself is not the thing that should block roadmap progress.

If live options-market-data subscriptions are not available yet, treat IV live usability as a deferred validation problem rather than a roadmap gate.

Remaining follow-up work is burn-in quality assurance, not a roadmap-start blocker:

1. IV one-shot live behavior should stay documented maintenance work
2. broader longer-session live QA is still useful but can run in parallel with roadmap work

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
- `migration.md`

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

- the risk outputs are now a materially safer base for future reusable analytics,
- and UI copy now reflects risk-basis coverage rather than implying completeness against raw portfolio value.

### Finding 3: IV web flow has a live regression

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

Prediction markets, crypto, fundamentals, and AI copilot work can now start from this branch.

The remaining constraint is that IV should stay on maintenance-only status unless the work directly touches shared market-data/session behavior.

## Recommended Next Slice

The next agent should start roadmap implementation from the cleaned readiness baseline, not reopen already-closed foundation questions unless a concrete regression appears.

### Priority 1

Start roadmap work from the now-verified baseline.

Target outcome:

- preserve the read-only research boundary,
- keep new domains behind provider adapters and normalized schemas,
- avoid re-entangling desktop session state with backend services.

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
- There is still an untracked root `.playwright-cli/` directory with inspection artifacts; do not commit it accidentally
- There are active in-flight changes around runtime/context separation; inspect diffs before editing

## Handoff Prompt

Use this prompt for the next agent:

```text
You are continuing Gamma pre-roadmap foundation work on branch `codex/p1-foundation-refactor`.

Start by reading:
- C:\Users\User\Desktop\StrataLab\roadmap.md
- C:\Users\User\Desktop\StrataLab\migration.md
- C:\Users\User\Desktop\StrataLab\README.md
- C:\Users\User\Desktop\StrataLab\docs\p1_refactor_handoff.md

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

What no longer blocks roadmap work:
- installed-workflow validation of the generated NSIS bundle is complete
- IV still has known live issues, but IV is not a current priority and is not a blocker by itself

Important constraint:
- Do not delete or disable IV
- Do not spend major time expanding IV
- Keep Gamma read-only and aligned with the roadmap

Your task:
1. Start roadmap-aligned implementation from the current provider/runtime/risk baseline.
2. If your changes touch IV behavior, only do the minimum fix needed so one-shot loads and market-data-mode behavior are predictable.
3. Run relevant tests before finishing.

Suggested starting files:
- C:\Users\User\Desktop\StrataLab\src\application\runtime.py
- C:\Users\User\Desktop\StrataLab\src\services\data_providers.py
- C:\Users\User\Desktop\StrataLab\src\application\risk_service.py
- C:\Users\User\Desktop\StrataLab\src\services\app_context.py
- C:\Users\User\Desktop\StrataLab\src\api\routes\system.py
- C:\Users\User\Desktop\StrataLab\frontend\src\lib\stores\app.ts
- C:\Users\User\Desktop\StrataLab\tests\test_api.py

Be incremental. Prefer additive model changes, compatibility shims, and test-backed refactors.
```
