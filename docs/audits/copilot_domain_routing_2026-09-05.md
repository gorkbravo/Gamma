# Copilot domain routing acceptance — 2026-09-05

This follow-up repairs the eight pre-existing failures recorded in [Checkpoint 8G acceptance](copilot_checkpoint8g_2026-09-05.md). It is a reliability prerequisite for the remaining Workstream 7 working analyses and release gate.

## Behavior

- Hypothetical portfolios and exact Strategy Lab portfolio inputs reach their existing multi-leg validators without a single-company ambiguity stop.
- Imported Strategy Lab analysis stays on the active strategy workflow instead of acquiring a company from the words “Strategy Lab”.
- Plain CPI/Fed and news-only oil requests avoid speculative SEC lookup and retain the intended domain plan.
- Named-company research, including mixed macro/company requests and lowercase names, retains entity resolution. Existing ambiguous-share-class stops and explicit-ticker behavior remain covered.
- Both model-assisted execution and deterministic preview use the shared preflight. No new authority, persistence, provider credentials, model, or orchestrator is introduced.

## Validation

- The broader `tests/test_copilot.py` and `tests/test_copilot_agents_sdk_smoke.py` run passed all 150 collected tests with three warnings (359.62 seconds). Final name-guard refinements and newly added regressions were verified by the focused routing run below.
- 13 focused existing portfolio, Strategy Lab, temporary Portfolio/Risk, company-name, ambiguous-company, and explicit-ticker tests passed.
- 11 focused routing, representative-domain-plan, and news-provider tests passed. The new regression checks that non-company workflows spend zero company-proposal calls and perform zero SEC searches, including during plan preview.
- 18 Operator eval, IV grounding, and provider diagnostics tests passed.
- 12 exact Prediction Markets, Responses-loop, and registry regressions passed.
- `git diff --check` passed.

No live OpenAI calls or frontend changes were needed. Remaining representative working analyses, generalized same-run approvals/recovery, and live release acceptance remain open.
