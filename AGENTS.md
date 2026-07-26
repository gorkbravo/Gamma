# Gamma Agent Guide

## Start Here

For any task involving product direction, feature expansion, architecture planning, or "what to build next", read [`roadmap.md`](./roadmap.md) first.

Treat [`roadmap.md`](./roadmap.md) as the single active planning document for future Gamma expansion. It defines:
- the product scope,
- the historical phase checkpoints and current workstreams,
- the constraints that keep Gamma read-only and research-focused,
- the cross-phase technical priorities that new work should align with.

## How To Use It

- If a task adds or changes a major feature, verify it fits the roadmap before implementing.
- Prefer roadmap-aligned work over ad hoc expansion.
- Preserve the core product boundary: Gamma is a research environment, not an execution platform.
- Favor data models, provider adapters, reusable analytics, caching, and provenance over UI-only additions.

## Copilot And Agentic Work

For any Copilot architecture, orchestration, tool, approval, run-state, model-routing, or agentic documentation change:

1. Read the Copilot end-state and completion contract in [`docs/copilot_v2_tab_plan.md`](./docs/copilot_v2_tab_plan.md).
2. Re-check the current official OpenAI developer documentation before deciding how the harness should work. Prefer the OpenAI Developer Docs connector when available; otherwise use only official `developers.openai.com` sources.
3. Record the review date, relevant official URLs, and the resulting architectural decision in the active Copilot plan. Existing notes are a dated snapshot, not a substitute for checking current guidance.
4. Evaluate Responses API and Agents SDK responsibilities deliberately. Do not adopt a framework or model merely because it is newer; use Gamma's evals, permission invariants, and product boundary to decide.

Gamma's server remains the authority for tool exposure, validation, permissions, persistence, approvals, and audit state. The model may choose among authorized app-native research tools, but it must never acquire trading, order-routing, account, wallet, portfolio-rebalancing, or arbitrary-code authority.

## Existing Project Orientation

For repo setup and runtime details, see [`README.md`](./README.md).
For the current documentation map, see [`docs/README.md`](./docs/README.md).
For dated audits, see [`docs/audits/README.md`](./docs/audits/README.md).
For migration history and handoff records, see [`docs/archive/README.md`](./docs/archive/README.md).
