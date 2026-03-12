# Gamma Agent Guide

## Start Here

For any task involving product direction, feature expansion, architecture planning, or "what to build next", read [`roadmap.md`](./roadmap.md) first.

Treat [`roadmap.md`](./roadmap.md) as the primary planning document for future Gamma expansion. It defines:
- the product scope,
- the intended development order,
- the constraints that keep Gamma read-only and research-focused,
- the cross-phase technical priorities that new work should align with.

## How To Use It

- If a task adds or changes a major feature, verify it fits the roadmap before implementing.
- Prefer roadmap-aligned work over ad hoc expansion.
- Preserve the core product boundary: Gamma is a research environment, not an execution platform.
- Favor data models, provider adapters, reusable analytics, caching, and provenance over UI-only additions.

## Existing Project Orientation

For repo setup and runtime details, see [`README.md`](./README.md).
For migration history and audit context, see [`migration.md`](./migration.md).
For pre-roadmap readiness and handoff execution, see [`docs/roadmap_readiness_checklist.md`](./docs/roadmap_readiness_checklist.md) and [`docs/p1_refactor_handoff.md`](./docs/p1_refactor_handoff.md).
