# Copilot V2 Handoff Prompt

Use this prompt to continue or meaningfully advance Copilot V2.

```text
You are continuing work in C:\Users\User\Desktop\Gamma.

Read first:
- AGENTS.md instructions in the repo root.
- roadmap.md.
- docs/copilot_v2_tab_plan.md, especially "Two Copilot Roles", Phase 7, and Open Decisions.
- docs/design_principles.md if touching frontend UI.

Current product decision:
- Copilot has two roles:
  1. Research Agent: thesis/synthesis from Gamma context.
  2. Research Operator: runs app-native read-only tests/simulations and drafts confirmed local research-state changes, producing traceable reports.
- The user has approved adopting the OpenAI Agents SDK for the Research Operator path.
- Do not rewrite the Research Agent path unless there is a concrete reason. Keep the current planner/executor/report foundation working while the Operator migrates behind the same Gamma action registry.

Critical boundary:
- Gamma remains a read-only research environment for market/account/wallet activity.
- Never add trade execution, order placement, account modification, wallet signing, wallet transactions, rebalancing, or arbitrary in-app strategy code execution.
- Agents SDK may plan, coordinate, trace, stream, and hand off, but Gamma backend services remain authoritative for permissions, execution, confirmation tokens, persistence, and local research-state mutation rules.

Recent completed work:
- Added ResearchActionRegistry in src/application/research_action_registry.py.
- Extended CopilotResearchActionDefinition with permission/provenance/retry metadata.
- Added operator plan models:
  - CopilotOperatorPlan
  - CopilotOperatorPlanStep
  - CopilotOperatorConfirmationCheckpoint
- Added backend routes:
  - GET /copilot/actions
  - POST /copilot/operator-plan
  - POST /copilot/operator-plan/execute
- Added first read-only operator tools:
  - run_risk_scenario_analysis
  - run_fundamentals_reverse_valuation
- DCF mutation planning stops before apply and exposes a confirmation checkpoint.
- Frontend now has TypeScript contracts, store calls, and Copilot workspace UI controls for Research Agent / Research Operator, Operator Plan, Run Operator, ordered steps, permission policies, expected artifacts, checkpoints, warnings, and execution summary.

Relevant files:
- src/application/copilot_service.py
- src/application/research_action_registry.py
- src/application/runtime.py
- src/models/copilot.py
- src/api/routes/copilot.py
- src/api/schemas/copilot.py
- tests/test_copilot.py
- frontend/src/lib/api/types.ts
- frontend/src/lib/stores/app.ts
- frontend/src/views/CopilotView.svelte
- docs/copilot_v2_tab_plan.md

Best next implementation slice:
1. Add operator progress events.
   - Backend event contract should support: plan, step-start, tool-result, warning, confirmation-needed, artifact-created, final-report.
   - Keep backend authoritative; UI should render events but not drive execution state as the source of truth.
   - Persist the event trace into Copilot sessions or an operator-run trace record.

2. Add an Agents SDK-backed Research Operator prototype behind the existing action registry.
   - Start narrow: same supported tasks as the custom operator loop.
   - The SDK layer should translate plans/tool calls into Gamma action-registry executions, not call domain services directly.
   - Preserve confirmation-required behavior for mutation/apply tools.
   - Add a config/feature flag or clearly isolated service so the current custom loop remains available during comparison.

3. Add an eval/benchmark harness before making Agents SDK the default.
   Compare custom loop vs Agents SDK-backed operator on:
   - DCF edit proposal/apply
   - reverse valuation plus report
   - risk shock analysis
   - hypothetical portfolio comparison
   - Strategy Lab backtest
   - cross-domain single-name event report
   Eval dimensions:
   - correct tool selection
   - permission compliance
   - stops for confirmation
   - source/warning preservation
   - useful final report
   - trace completeness

4. Broaden read-only operator tools after the event/prototype path is stable.
   Priorities:
   - Strategy Lab backtest/composition analysis
   - Research scope analysis
   - Options event/volatility comparison
   - Portfolio hypothetical comparison
   - Risk shock scenario with actual shock parameters rather than only current baseline risk

5. Generalize confirmed mutation flow only after read-only operator reliability improves.
   Candidate local research-state mutations:
   - saved research scopes
   - Strategy Lab compositions
   - memo edits
   - watchlists
   - scenario/model snapshots
   - hypothetical portfolio definitions
   Every mutation must return diff, rationale, warnings, source ids, rollback/snapshot context, and require confirmation when durable/non-trivial.

Validation commands:
- python -m pytest tests/test_copilot.py
- python -m pytest tests/test_api.py -k "risk_compute_endpoint or copilot or fundamentals"
- cd frontend; npm run typecheck
- cd frontend; npm run build
- cd frontend; npm test -- app.test

Watch out:
- There may be unrelated dirty files in the worktree. Do not revert or modify them unless required.
- Keep changes scoped.
- Use rg for searching.
- Use apply_patch for manual edits.
- Use python -m pytest, not bare pytest.
```
