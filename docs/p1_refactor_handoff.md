# P1 Refactor Handoff

## Repo State

- Baseline checkpoint on `main`: `b72bd9f` (`Checkpoint current UI and desktop changes`)
- Active branch: `codex/p1-foundation-refactor`
- Refactor commit on branch: `452da6b` (`Refactor research validation and identity scaffolding`)
- Current `HEAD`: `d57018a` (`Add P1 refactor handoff notes`)
- Current working tree also contains additional uncommitted P1 identity-rekey changes described below

## What Was Done

### Phase 1: Research request validation

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
- Validation now allows duplicate display symbols only when the synthetic positions resolve to distinct `instrument_id` values

### Phase 2: Instrument identity rekey

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
- Threaded identity fields through:
  - `src/api/schemas/portfolio.py`
  - `src/api/schemas/research.py`
  - `src/api/schemas/risk.py`
  - `src/services/data_providers.py`
  - `src/services/ibkr_client.py`
  - `src/services/market_data.py`
  - `src/services/mock_data.py`
  - `frontend/src/lib/api/types.ts`
  - `frontend/src/views/PortfolioView.svelte`
  - `frontend/src/views/ResearchView.svelte`
  - `frontend/src/views/RiskView.svelte`

Completed in the current working tree:

- Rekeyed research analytics internals from `symbol` to `instrument_id`
- Rekeyed portfolio performance internals from `symbol` to `instrument_id`
- Rekeyed risk analytics internals from `symbol` to `instrument_id`
- Rekeyed price-loading and missing/exclusion tracking so duplicate display symbols no longer collapse
- Preserved `symbol` and `display_symbol` as compatibility/display fields in API responses and frontend rendering
- Added tests covering two instruments with the same display symbol but distinct identity

### Phase 3: Backend state isolation

Partially implemented, backend cache split advanced.

- Removed backend-global research scope/snapshot mutation from:
  - `src/api/routes/research.py`
- Diagnostics no longer reflect hidden per-request research scope from:
  - `src/api/routes/system.py`
- Split shared research time-series caching out of `AppDataContext` into:
  - `src/services/research_cache.py`
- `AppDataContext` now only owns Qt/workspace state and signals:
  - app mode
  - research scope inputs
  - research snapshot forwarding
- FastAPI diagnostics and status endpoints now read cached research symbols from runtime-owned cache state instead of Qt context

Important limitation:

- `AppDataContext` still exists inside the runtime because the desktop runtime graph is still shared
- research snapshot/session state is still a Qt concern inside the shared runtime assembly
- the API path is safer and more stateless now, but runtime resource separation is not complete
- This remains the highest-priority unfinished refactor slice

## Tests Run

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result: `59 passed`
Current follow-up after the runtime cache split: `60 passed`

Frontend:

```powershell
cd frontend
npm run test
```

Result: `14 passed`

Frontend build:

```powershell
cd frontend
npm run build
```

Result: passed

Focused backend follow-up after the runtime cache split:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app_mode_logic.py tests/test_api.py tests/test_research_service.py tests/test_risk_tab_logic.py
```

Result: `34 passed`

## Key Files Touched

Earlier refactor foundation:

- `src/application/research_validation.py`
- `src/api/routes/research.py`
- `src/api/routes/system.py`
- `src/api/schemas/portfolio.py`
- `src/api/schemas/research.py`
- `src/application/research_service.py`
- `src/models/app_mode.py`
- `src/models/instruments.py`
- `src/models/portfolio.py`
- `src/services/app_context.py`
- `src/services/data_providers.py`
- `src/services/ibkr_client.py`
- `src/services/mock_data.py`
- `tests/test_api.py`
- `tests/test_research_service.py`
- `frontend/src/lib/api/types.ts`

Current working-tree slice:

- `src/application/instrument_identity.py`
- `src/application/research_service.py`
- `src/application/portfolio_service.py`
- `src/application/risk_service.py`
- `src/application/research_validation.py`
- `src/application/__init__.py`
- `src/services/data_providers.py`
- `src/services/research_cache.py`
- `src/services/market_data.py`
- `src/services/app_context.py`
- `src/api/schemas/research.py`
- `src/api/schemas/risk.py`
- `src/api/routes/system.py`
- `tests/test_api.py`
- `tests/test_research_service.py`
- `tests/test_app_mode_logic.py`
- `tests/test_risk_tab_logic.py`
- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/workspace.test.ts`
- `frontend/src/views/PortfolioView.svelte`
- `frontend/src/views/ResearchView.svelte`
- `frontend/src/views/RiskView.svelte`

## Current Working Tree

- Dirty relative to tracked files at current `HEAD` (`d57018a`) because the latest identity-rekey slice is not yet committed
- There is still an untracked root `.playwright-cli/` directory with artifact files; it was intentionally not committed

## Recommended Next Slice

The next agent should focus on finishing runtime/state separation rather than more identity polish.

### Priority 1

Split backend cache/state concerns out of `AppDataContext`.

Target outcome:

- Qt keeps its own workspace/UI context
- FastAPI runtime only holds long-lived resources and explicit caches
- request-scoped research state is never stored globally
- cached timeseries responsibilities are explicit rather than being mixed with UI state
- Current status:
  - shared research history cache is now runtime-owned
  - API diagnostics/system no longer depend on Qt context for cache visibility
  - remaining work is to finish separating desktop session state from shared runtime construction

### Priority 2

Tighten compatibility cleanup after the identity rekey.

Target outcome:

- replace remaining symbol-based fallback lookups where safe
- reduce duplicate snapshot metadata lookups in response mappers
- keep frontend payloads stable while moving more internals to identity-only indexing

### Priority 3

Expand tests around runtime isolation and identity-aware behavior:

- diagnostics remaining stateless under repeated research requests
- risk and portfolio paths using identity-aware snapshots in more edge cases

## Handoff Prompt

Use this prompt for the next agent:

```text
You are continuing Gamma backend refactor work on branch `codex/p1-foundation-refactor`.

Start by reading:
- C:\Users\User\Desktop\StrataLab\roadmap.md
- C:\Users\User\Desktop\StrataLab\migration.md
- C:\Users\User\Desktop\StrataLab\docs\p1_refactor_handoff.md

Current git state:
- `main` baseline checkpoint: b72bd9f (`Checkpoint current UI and desktop changes`)
- current branch commit: 452da6b (`Refactor research validation and identity scaffolding`)
- current handoff doc commit: d57018a (`Add P1 refactor handoff notes`)
- there is additional uncommitted working-tree progress after `d57018a`; inspect `git status` before proceeding

What is already done:
- shared research request validation exists in `src/application/research_validation.py`
- `/research/analyze` now returns 422 for invalid synthetic payloads
- additive identity fields (`instrument_id`, `display_symbol`, provider/exchange metadata) exist in the domain/API layer
- research, portfolio, and risk analytics have been rekeyed to `instrument_id` in the current working tree
- compatibility response fields still expose `symbol` and `display_symbol` for the frontend
- backend-global research scope mutation was removed from the FastAPI path
- backend tests and frontend tests were passing at handoff time

What is not finished:
- `AppDataContext` still mixes Qt/workspace concerns with backend cache concerns
- the runtime is safer, but not fully decomposed into global resources vs explicit request/session state

Your task:
1. Separate backend runtime/cache concerns from `AppDataContext`.
2. Preserve current frontend and desktop behavior with compatibility shims.
3. Keep the product read-only and aligned with the roadmap.
4. Add or update tests as you go.
5. Run relevant tests before finishing.

Suggested starting files:
- C:\Users\User\Desktop\StrataLab\src\services\app_context.py
- C:\Users\User\Desktop\StrataLab\src\application\runtime.py
- C:\Users\User\Desktop\StrataLab\src\application\system_service.py
- C:\Users\User\Desktop\StrataLab\src\api\routes\system.py
- C:\Users\User\Desktop\StrataLab\src\api\routes\research.py
- C:\Users\User\Desktop\StrataLab\frontend\src\lib\workspace.ts
- C:\Users\User\Desktop\StrataLab\tests\test_api.py

Be incremental. Do not do a big-bang rewrite. Prefer additive model changes and compatibility shims.
```
