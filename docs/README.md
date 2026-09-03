# Gamma Documentation

This directory is split into active documentation, audits, and archived project history.

## Active Documents

- [`../README.md`](../README.md): setup, run commands, validation commands, current product status, current roadmap direction, and provider stance
- [`../roadmap.md`](../roadmap.md): single active source of truth for product direction, historical phase checkpoints, workstreams, provider strategy, beta readiness, and constraints
- [`design_principles.md`](./design_principles.md): canonical frontend doctrine, token roles, component contracts, interaction/accessibility rules, review tests, and the §14 common-mistakes / §15 quick-reference lookup used as the post-edit check
- [`provenance_expectations.md`](./provenance_expectations.md): active provenance contract for new roadmap-era entities
- [`copilot_v2_tab_plan.md`](./copilot_v2_tab_plan.md): dedicated Copilot workspace and agentic research harness plan, including OpenAI references, action taxonomy, safety boundary, and editable progression checklist
- [`research_script_workspace_plan.md`](./research_script_workspace_plan.md): completed Strategy Lab `Script` mode architecture, isolated-runtime and authority boundary, domain/API/runtime contracts, delivery evidence, tests, and maintenance rules
- [`copilot_v2_handoff_prompt.md`](./copilot_v2_handoff_prompt.md): reusable ~87%-to-100% handoff prompt for completing temporary tab-owned analyses, same-run approval/recovery, and the release gate while keeping framework choice eval-backed
- [`strategy_lab_cross_tab_handoffs.md`](./strategy_lab_cross_tab_handoffs.md): active spec and progress board for sending selected research objects from source tabs into the Strategy Lab composer
- [`macro_policy_path_depth.md`](./macro_policy_path_depth.md): implementation spec for the first pass of deeper `Rates & Policy` meeting-path depth inside Macro
- [`fundamentals_phase6_spec.md`](./fundamentals_phase6_spec.md): product and architecture spec for the first-pass `Fundamentals` workspace

Current Commodities tab setup, EIA and IBKR provider switches, sample fallback behavior, futures-curve caveats, and read-only constraints are documented in [`../README.md`](../README.md).

Current Options / IV behavior, including selectable surface models, implied-probability slices, strategy payoff flow, Gamma-owned Greeks, and live-provider caveats, is documented in [`../README.md`](../README.md) and tracked in `roadmap.md` Workstream 4.

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
- Keep `roadmap.md` as the single active roadmap, focused on future direction and only the historical checkpoints needed to understand current scope.
- Keep the README as the short operational and product-status summary.
- Put dated audit logs in `docs/audits/`.
- Put handoff notes, migration logs, old prompts, and completed transition records in `docs/archive/`.
- Prefer updating an existing live document over creating a new one for one-off status notes.
