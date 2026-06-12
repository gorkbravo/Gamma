# Gamma Documentation

This directory is split into active documentation, audits, and archived project history.

## Active Documents

- [`../README.md`](../README.md): setup, run commands, validation commands, current product status, Roadmap V2 direction, and provider stance
- [`../roadmap.md`](../roadmap.md): source of truth for current roadmap-era product direction, completed/paused phase scope, and constraints
- [`../roadmap_v2.md`](../roadmap_v2.md): detailed Roadmap V2 workstreams for existing-tab hardening, new research surfaces, platform foundation, provider strategy, and beta readiness
- [`design_principles.md`](./design_principles.md): UI and interaction principles for roadmap-era product work
- [`provenance_expectations.md`](./provenance_expectations.md): active provenance contract for new roadmap-era entities
- [`copilot_v2_tab_plan.md`](./copilot_v2_tab_plan.md): dedicated Copilot workspace and agentic research harness plan, including OpenAI references, action taxonomy, safety boundary, and editable progression checklist
- [`copilot_v2_handoff_prompt.md`](./copilot_v2_handoff_prompt.md): reusable handoff prompt for continuing Copilot V2, including the approved Agents SDK Research Operator direction
- [`strategy_lab_cross_tab_handoffs.md`](./strategy_lab_cross_tab_handoffs.md): active spec and progress board for sending selected research objects from source tabs into the Strategy Lab composer
- [`macro_policy_path_depth.md`](./macro_policy_path_depth.md): implementation spec for the first pass of deeper `Rates & Policy` meeting-path depth inside Macro
- [`fundamentals_phase6_spec.md`](./fundamentals_phase6_spec.md): product and architecture spec for the first-pass `Fundamentals` workspace

Current Commodities tab setup, EIA and IBKR provider switches, sample fallback behavior, futures-curve caveats, and read-only constraints are documented in [`../README.md`](../README.md).

Current Options / IV behavior, including selectable surface models, implied-probability slices, strategy payoff flow, Gamma-owned Greeks, and live-provider caveats, is documented in [`../README.md`](../README.md) and tracked in Roadmap V2 Workstream 4.

## Audit Documents

Dated usability, codebase, and frontend audits live under [`audits/`](./audits/README.md).

- [`audits/usability/`](./audits/usability/README.md): live workflow audits and research-thread evaluations
- [`audits/codebase/`](./audits/codebase/README.md): repository, architecture, provider, dependency, and data-feed audits
- [`audits/frontend/`](./audits/frontend/README.md): frontend-specific visual, accessibility, and interaction audits

## Archived Documents

Historical migration logs, completed transition records, old prompts, and handoff notes live under [`archive/`](./archive/README.md).

These files are kept for traceability, not as current operating guidance.

## Documentation Rules

- Keep `README.md` operational, current, and concise about near-future planning context.
- Keep `roadmap.md` focused on future direction, not audit history.
- Keep `roadmap_v2.md` as the detailed V2 planning document and keep the README as the short summary.
- Put dated audit logs in `docs/audits/`.
- Put handoff notes, migration logs, old prompts, and completed transition records in `docs/archive/`.
- Prefer updating an existing live document over creating a new one for one-off status notes.
