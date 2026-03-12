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

As of March 12, 2026:

- the migration is largely complete,
- IV live usability is not a blocker by itself if proper options-market-data subscriptions are not available yet,
- the real pre-roadmap blockers are provider/runtime generalization, trustworthy reusable risk semantics, and release-path validation.

This means Gamma can move toward roadmap work only if the remaining hard blockers below are either:

1. resolved, or
2. explicitly accepted as deferred by the operator.

## Hard Blockers

- [ ] Provider/runtime assumptions are no longer hardwired to `STK / SMART / USD`
  Evidence to collect:
  - `src/application/runtime.py` and `src/services/data_providers.py` can describe or load instruments without assuming IBKR equities defaults for every new domain
  - new data domains can plug into a provider adapter boundary without parallel app graphs

- [ ] Risk coverage semantics are trustworthy and test-backed
  Evidence to collect:
  - `risk_coverage_ratio` is either a real completeness ratio or renamed to match what it actually means
  - live-style books with cash, leverage, or margin cannot produce misleading headline coverage numbers without an explicit warning/model explanation
  - tests cover the chosen semantics

- [ ] Full packaged desktop build completes and produces a verifiable installer artifact
  Evidence to collect:
  - `npm run tauri:build` completes end-to-end
  - final installer output exists under the expected bundle path
  - installed workflow is smoke-checked, not just backend startup

- [ ] Provenance expectations are defined for new roadmap entities
  Evidence to collect:
  - source/provider
  - retrieval timestamp
  - endpoint/module origin
  - transformation note for derived metrics

## Accepted Non-Blockers

- [x] IV tab live usability can remain partial if missing subscriptions make proper validation impossible today
- [x] PySide fallback can remain during burn-in
- [x] Advanced desktop ergonomics and saved-workspace polish can lag roadmap start
- [x] IV can stay on maintenance-only status unless roadmap work directly touches shared market-data/session behavior

## Baseline Validation

- [x] `.\.venv\Scripts\python.exe -m pytest`
  March 12, 2026 result: `67 passed`

- [x] `cd frontend && npm run test`
  March 12, 2026 result: `15 passed`

- [x] `cd frontend && npm run build`

- [x] `cargo check --manifest-path frontend\src-tauri\Cargo.toml`

- [x] `cd frontend && npm run backend:smoke`

- [x] `cd frontend && npm run desktop:smoke`

- [ ] `cd frontend && npm run tauri:build`
  March 12, 2026 result: timed out after roughly 5 minutes while NSIS was active; no final bundle artifact was present before timeout.

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

1. Finish provider/runtime separation for pre-roadmap work.
2. Fix or clarify risk coverage semantics with tests.
3. Revalidate the packaged desktop build to completion.
4. Only then start roadmap implementation work from a clean, explicit baseline.

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
