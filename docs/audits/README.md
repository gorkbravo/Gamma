# Gamma Audits

This directory contains dated audit records that are still useful for product, codebase, and frontend follow-up work.

Use this area for findings that should remain discoverable after the immediate branch or implementation pass is complete. Use `docs/archive/` for migration records, old handoffs, superseded prompts, and transition history that should be preserved but is not an active audit category.

## Categories

- [`usability/`](./usability/): live workflow audits, trade-idea experiments, research-thread evaluations, and product friction reports.
- [`codebase/`](./codebase/): repository, architecture, dependency, provider, security-boundary, and data-feed audits.
- [`frontend/`](./frontend/): visual, interaction, design-system, accessibility, and frontend-specific implementation audits.

## Filing Rules

- Prefer dated filenames: `topic_YYYY-MM-DD.md`.
- Keep each audit self-contained: setup, scope, findings, severity or priority, and validation notes.
- Link follow-up specs or implementation docs instead of duplicating them.
- When an audit becomes obsolete, keep it here if it still explains why a change was made; move it to `docs/archive/` only if it is purely historical.
