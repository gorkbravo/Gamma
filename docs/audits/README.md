# Gamma Audits

This directory contains dated audit records that are still useful for product, codebase, and frontend follow-up work.

Use this area for findings that should remain discoverable after the immediate branch or implementation pass is complete. Use `docs/archive/` for migration records, old handoffs, superseded prompts, and transition history that should be preserved but is not an active audit category.

## Categories

- [Strategy Lab saved experiments and Risk acceptance, 2026-10-06](./usability/strategy_lab_experiments_2026-10-06.md): exact saved inputs/histories, restart replay, retained benchmark Risk handoff, revised-weight comparison, and live TWS browser evidence.
- [Copilot Checkpoint 10 follow-up, 2026-10-06](./copilot_checkpoint10_followup_2026-10-06.md): market-open direct Options acceptance, provider/accounting fixes and exact remaining native-reader/billing gates.
- [Copilot Checkpoint 10 acceptance, 2026-10-05](./copilot_checkpoint10_acceptance_2026-10-05.md): representative live outcomes, release checks and historical cost accounting limitations.

- [`usability/`](./usability/): live workflow audits, trade-idea experiments, research-thread evaluations, and product friction reports.
- [`codebase/`](./codebase/): repository, architecture, dependency, provider, security-boundary, and data-feed audits.
- [`frontend/`](./frontend/): visual, interaction, design-system, accessibility, and frontend-specific implementation audits.

## Filing Rules

- Prefer dated filenames: `topic_YYYY-MM-DD.md`.
- Keep each audit self-contained: setup, scope, findings, severity or priority, and validation notes.
- Link follow-up specs or implementation docs instead of duplicating them.
- When an audit becomes obsolete, keep it here if it still explains why a change was made; move it to `docs/archive/` only if it is purely historical.
