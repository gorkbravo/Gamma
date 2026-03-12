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

Do not start roadmap feature work yet.

The immediate goal is to finish pre-roadmap readiness so Gamma can support new research domains cleanly without re-entangling the codebase.

That means:

1. keep Gamma read-only and research-focused,
2. finish the runtime/provider separation work,
3. make cross-domain data adapters possible,
4. fix the highest-signal live regressions,
5. avoid spending time on low-priority UI expansion.

## Roadmap Start Decision

The default recommendation is still to finish pre-roadmap hardening first.

However, IV readiness by itself is not the thing that should block roadmap progress.

If live options-market-data subscriptions are not available yet, treat IV live usability as a deferred validation problem rather than a roadmap gate.

The real pre-roadmap blockers are:

1. provider/runtime abstractions still being too IBKR/equities-specific,
2. risk coverage semantics still needing a trustworthy reusable basis,
3. packaged desktop validation still not having a completed end-to-end installer proof.

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

Partially implemented.

- Removed backend-global research scope/snapshot mutation from the FastAPI path
- Diagnostics no longer reflect hidden per-request research scope
- Split shared research time-series caching out of `AppDataContext` into:
  - `src/services/research_cache.py`
- `AppDataContext` is now much closer to a desktop-only workspace object

Important limitation:

- runtime construction is still centered around the current IBKR/equities Gamma shape,
- the backend is safer than before, but not yet provider-agnostic,
- this is still the main unfinished foundation slice.

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

### Finding 1: provider layer is not roadmap-ready

This is the most important architectural gap.

The roadmap requires provider adapters and normalized entities that can support prediction markets, crypto, fundamentals, and AI context.

The current research/provider path is still hardwired to IBKR-style US equities:

- `src/services/data_providers.py`
- `src/application/runtime.py`

Examples:

- research history requests default to `STK / SMART / USD`
- single-name research snapshots synthesize the same assumptions
- runtime assembly is still fundamentally an IBKR/equities app graph

Implication:

- prediction markets and crypto cannot plug into the current abstractions cleanly,
- starting roadmap Phase 1 or Phase 2 now would create parallel stacks or force another rewrite.

### Finding 2: risk coverage math is misleading on live books

Live audit reproduced a concrete issue in the current risk service:

- `portfolio_value = 58709.18`
- `covered_portfolio_value = 67722.18`
- `risk_coverage_ratio = 1.1535`

That is a real output from the current code path.

The current implementation compares:

- `snapshot.net_liquidation`

against:

- summed included `base_market_value`

This can produce coverage above 100% on margined/live books and makes the "coverage" semantics wrong.

Files:

- `src/application/risk_service.py`

Implication:

- the current risk outputs are not a trustworthy base for future reusable analytics without fixing the exposure basis.

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

### Do not start roadmap tabs yet

Do not begin prediction markets, crypto, fundamentals, or AI copilot implementation from this branch until the provider/runtime groundwork and risk semantics are in place.

## Recommended Next Slice

The next agent should work on pre-roadmap readiness, not feature expansion.

### Priority 1

Finish provider/runtime separation.

Target outcome:

- keep `AppDataContext` desktop-only,
- keep FastAPI runtime focused on long-lived services and explicit caches,
- introduce or prepare a provider adapter boundary that is not tied to `STK / SMART / USD`,
- make research and analytics consume normalized entities instead of broker-specific assumptions.

Concrete direction:

- audit `src/application/runtime.py`
- audit `src/services/data_providers.py`
- identify the minimum normalized contracts/entities needed to support non-IBKR research sources later
- keep changes additive and compatible

### Priority 2

Fix risk exposure/coverage semantics.

Target outcome:

- `risk_coverage_ratio` cannot exceed 100% under normal semantics, or
- the metric is renamed and the model is made explicit if it is not a completeness ratio

Concrete direction:

- review denominator/basis in `src/application/risk_service.py`
- verify live and mock behavior
- add tests for margined/live-style books where net liq and gross included exposure differ

### Priority 3

Do the minimum IV compatibility fix if touched.

Target outcome:

- one-shot IV loading and market-data-mode behavior are predictable enough that another agent does not have to rediscover the live failure mode

Concrete direction:

- do the smallest backend fix that improves one-shot IV reliability or makes the failure mode explicit
- align IV `auto` mode semantics with the rest of the market-data stack if that path is touched
- do not redesign the IV feature

### Priority 4

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

What still blocks roadmap work:
- provider/runtime abstractions are still too IBKR/equities-specific
- research data loading still assumes `STK / SMART / USD`
- risk coverage semantics are wrong or at least misleading on live books
- IV has known live issues, but IV is not a current priority and is not a blocker by itself

Important constraint:
- Do not start roadmap feature implementation yet
- Do not delete or disable IV
- Do not spend major time expanding IV
- Keep Gamma read-only and aligned with the roadmap

Your task:
1. Finish the provider/runtime separation needed for pre-roadmap readiness.
2. Make the data/provider layer more adapter-friendly without doing a big-bang rewrite.
3. Fix or clarify risk coverage semantics with tests.
4. If your changes touch IV behavior, only do the minimum fix needed so one-shot loads and market-data-mode behavior are predictable.
5. Run relevant tests before finishing.

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
