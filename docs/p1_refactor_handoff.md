# P1 Refactor Handoff

## Repo State

- Baseline checkpoint on `main`: `b72bd9f` (`Checkpoint current UI and desktop changes`)
- Active branch: `codex/p1-foundation-refactor`
- Refactor commit on branch: `452da6b` (`Refactor research validation and identity scaffolding`)

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

### Phase 2: Instrument identity scaffolding

Partially implemented, additive only.

- Added identity helper module: `src/models/instruments.py`
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
  - `src/services/data_providers.py`
  - `src/services/ibkr_client.py`
  - `src/services/mock_data.py`
  - `frontend/src/lib/api/types.ts`

Important limitation:

- Analytics internals are still mostly keyed by raw `symbol`
- The identity work so far is an API/domain scaffold, not a full analytics rekey

### Phase 3: Backend state isolation

Partially implemented, core API fix done.

- Removed backend-global research scope/snapshot mutation from:
  - `src/api/routes/research.py`
- Diagnostics no longer reflect hidden per-request research scope from:
  - `src/api/routes/system.py`

Important limitation:

- `AppDataContext` still exists inside the runtime for Qt signaling and shared cached timeseries
- The API path is safer and more stateless now, but runtime resource/cache separation is not complete

## Tests Run

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result: `57 passed`

Frontend:

```powershell
cd frontend
npm run test
```

Result: `14 passed`

## Key Files Touched In The Refactor Commit

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

## Current Working Tree

- Clean relative to tracked files after commit `452da6b`
- There is still an untracked root `.playwright-cli/` directory with artifact files; it was intentionally not committed

## Recommended Next Slice

The next agent should focus on finishing the identity/runtime migration rather than adding more validation polish.

### Priority 1

Rekey analytics internals from `symbol` to `instrument_id` across:

- `src/application/research_service.py`
- `src/application/portfolio_service.py`
- `src/application/risk_service.py`
- `src/services/data_providers.py`
- `src/services/market_data.py`

The goal is to stop collapsing weights, prices, and returns on raw ticker symbol.

### Priority 2

Split backend cache/state concerns out of `AppDataContext`.

Target outcome:

- Qt keeps its own workspace/UI context
- FastAPI runtime only holds long-lived resources and explicit caches
- request-scoped research state is never stored globally

### Priority 3

After rekeying analytics, expand tests for:

- two instruments with the same display symbol but different identity
- risk and portfolio paths using identity-aware snapshots
- diagnostics remaining stateless under repeated research requests

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

What is already done:
- shared research request validation exists in `src/application/research_validation.py`
- `/research/analyze` now returns 422 for invalid synthetic payloads
- additive identity fields (`instrument_id`, `display_symbol`, provider/exchange metadata) exist in the domain/API layer
- backend-global research scope mutation was removed from the FastAPI path
- backend tests and frontend tests were passing at handoff time

What is not finished:
- research/portfolio/risk analytics are still mostly keyed by raw `symbol`
- `AppDataContext` still mixes Qt/workspace concerns with backend cache concerns
- the runtime is safer, but not fully decomposed into global resources vs explicit request/session state

Your task:
1. Rekey analytics internals from `symbol` to `instrument_id` wherever prices, weights, returns, exclusions, or contributions are indexed.
2. Preserve current frontend and desktop behavior with compatibility shims.
3. Keep the product read-only and aligned with the roadmap.
4. Add or update tests as you go.
5. Run relevant tests before finishing.

Suggested starting files:
- C:\Users\User\Desktop\StrataLab\src\application\research_service.py
- C:\Users\User\Desktop\StrataLab\src\application\portfolio_service.py
- C:\Users\User\Desktop\StrataLab\src\application\risk_service.py
- C:\Users\User\Desktop\StrataLab\src\services\data_providers.py
- C:\Users\User\Desktop\StrataLab\src\services\market_data.py
- C:\Users\User\Desktop\StrataLab\src\services\app_context.py

Be incremental. Do not do a big-bang rewrite. Prefer additive model changes and compatibility shims.
```
