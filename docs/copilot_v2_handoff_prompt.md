# Copilot V2 ~87% To 100% Execution Prompt

Copy the text inside the block below into the coding agent that will continue Copilot V2.

```text
You are the implementation owner for completing Copilot V2 in:

C:\Users\User\Desktop\Gamma

Your objective is to take Copilot from its approximately 87% clarified baseline through the remaining Checkpoint 8 work, Checkpoint 9, and the desired 100% acceptance gate defined in `roadmap.md` and `docs/copilot_v2_tab_plan.md`.

The former 97% figure measured a narrower chat, persistence, evidence, and bounded-workflow foundation. Historical checkpoints 1 through 6, the Checkpoint 7 closed-loop Operator, Checkpoints 8A-8D, and the isolated Research Script Workspace are verified and should be preserved. The central remaining product work is to generalize temporary tab-owned analysis state beyond the completed Fundamentals, hypothetical Portfolio/Risk, Options realized-versus-implied, and Script slices; then complete same-run approval/recovery and the release gate.

This is an implementation task, not a planning-only exercise. Work in coherent vertical slices, verify each exit criterion, update the active documentation, and continue until the desired end state is proven or a genuine external dependency blocks the remaining gate. Never claim a percentage merely because code was written.

## Read first

Read these files completely before editing:

1. `AGENTS.md`
2. `roadmap.md`, especially `Workstream 7 - Copilot V2`, `Path from 82% to 100%`, sequencing rules, non-goals, and deliverable
3. `docs/copilot_v2_tab_plan.md`, especially:
   - `Two Copilot Roles`
   - `Authority And Interaction Contract`
   - the unloaded-LMT reference workflow
   - `OpenAI References`
   - the current reality and completion boundary
   - open workstreams I through L
   - definition of done, current Operator inventory, and open decisions
4. `docs/provenance_expectations.md`
5. `docs/design_principles.md` before changing Svelte/CSS
6. `README.md` for runtime, provider, and validation commands

Before material Copilot architecture, orchestration, tool, approval, run-state, model-routing, or documentation work, refresh the current official OpenAI developer documentation. Prefer the OpenAI Developer Docs connector when available; otherwise use only official `developers.openai.com` sources. At minimum review current guidance for:

- Responses API versus Agents SDK;
- running agents and the model-tool-model loop;
- sessions/results and resumable state;
- tools and strict schemas;
- guardrails and human approvals;
- orchestration;
- tracing and trace grading;
- current model/tool/streaming behavior.

Record the review date, official URLs, and resulting architectural decision in `docs/copilot_v2_tab_plan.md`. Existing repo notes are a dated snapshot, not a substitute for the refresh. Do not change frameworks or models merely because a newer one exists; use Gamma's evals, permission invariants, reliability, latency, and cost.

## Establish the real baseline

Before editing:

- run `git status --short --branch` and preserve unrelated user work;
- inspect the current Copilot code, tests, and recent changes rather than inferring behavior from documentation alone;
- run focused Copilot backend tests, frontend Copilot tests, typecheck, and build;
- inspect the running desktop and narrow-width Copilot UI when practical;
- compare code reality with the roadmap and detailed plan;
- retain the verified run/transcript/session/artifact, context/evidence, action-registry, DCF proposal, shelf continuity, model/storage-policy, observability, and diagnostics contracts unless the new exit criteria require a compatible change.

Use `rg` for discovery and `apply_patch` for manual edits. Do not reset, discard, overwrite, or reformat unrelated work. Do not commit, push, or open a pull request unless the user separately requests it.

## Desired interaction contract

Copilot has two visible authority levels inside one workspace.

### Research Agent

Research Agent interprets the current surface and context explicitly attached to the turn. It may produce grounded opinions, explanations, theses, memos, or reports, but it must not:

- load a missing entity;
- run DCF, risk, portfolio, options, strategy, or other analytical workflows;
- create or modify app working state;
- silently promote itself to Operator.

If the answer requires app operation, Agent should disclose the missing context and offer a visible Operator workflow.

### Research Operator

Research Operator may operate Gamma's app-native research capabilities. Within the selected scopes, registry, budgets, and product boundary it should be able to:

- resolve a supported entity even when it is not loaded;
- acquire required provider-backed context through Gamma services;
- create explicit session-scoped temporary portfolios, DCFs, scenarios, option sets, assumptions, and intermediate outputs;
- translate the user's exact entities, weights, shocks, dates, horizons, assumptions, and comparison targets into strict tool inputs;
- call authorized typed backend tools;
- inspect each observation and adapt its plan or parameters;
- stop for approval, insufficient evidence, cancellation, budget, or typed failure;
- synthesize the user's requested conclusion from the actual tool results;
- materialize useful results in the owning Gamma tab or working object without silently saving them as durable state.

The representative contract is: in Operator mode, “What is the fair value of LMT?” must work even when LMT is not loaded. Operator resolves LMT, creates an ephemeral Fundamentals/DCF analysis, examines data quality, runs the necessary DCF/reverse-valuation/sensitivity work, adapts if needed, and returns a sourced fair-value estimate or range with assumptions and warnings. Persisting edits to an existing saved DCF remains confirmation-gated.

The same behavior applies to a user-specified hypothetical portfolio, risk scenario, options comparison, Strategy Lab workflow, and other supported tab-owned research capabilities. Analytical depth remains limited by the owning Gamma service, but manual UI pre-staging must not be a harness requirement.

## Non-negotiable product boundary

Gamma is a research environment, not a real-world execution platform.

Never add:

- trade execution, order placement/modification/cancellation, or routing;
- account mutation or portfolio rebalancing;
- wallet connection, signing, transactions, or message signing;
- arbitrary Copilot code or sandbox execution;
- unrestricted browsing as a silent substitute for Gamma provider adapters;
- hidden UI clicking as the authority for analytical execution;
- automatic changes to existing durable research state.

Ephemeral research state may run automatically and must be labeled. A future durable research-state mutation must use Gamma's server-owned registry, show the exact diff and rollback/snapshot policy, pause with resumable run state, and resume the same unfinished run only after the applicable approve/reject decision.

Gamma's backend remains authoritative for tool exposure, schema validation, permissions, budgets, execution, idempotency, persistence, approvals, recovery, trace state, and finalization. The model proposes actions; Gamma authorizes and executes them.

## Harness contract

The end-state Operator loop is:

1. Resolve role, intent, entities, authority, context, and budgets.
2. Create a Gamma-owned run plus session-scoped working-analysis state.
3. Ask the model for a strict plan or next typed tool call.
4. Validate the tool, arguments, permissions, context fingerprint, retry policy, and budget on the server.
5. Execute the app-native backend tool.
6. Return its typed observation, sources, assumptions, and warnings to the model.
7. Let the model choose the next authorized step, revise parameters, pause, or finish.
8. Produce the final answer from the observed outputs and persist the bounded trace.

A deterministic prewritten sequence may remain a fallback, workflow primitive, or test fixture, but it does not satisfy the desired Operator by itself. A generic “N steps executed” card is not a successful answer to an analytical request.

Start with one manager Operator that owns the final answer. Add tab/domain specialists only if separate instructions, tool sets, or handoff contracts improve trace evals. Whether the manager uses a custom Responses loop or Agents SDK is an eval-backed implementation decision; neither option may bypass Gamma's registry or state authority.

## Current verified foundation

Preserve and build on:

- shelf and dedicated workspace;
- Research Agent and Research Operator controls;
- provider-native streaming through the Gamma run-event contract;
- run ids, monotonic events, Stop/Retry, bounded replay, cancellation, timeout, and one terminal result;
- canonical typed transcript/evidence rendering and source navigation;
- local session, context, run, trace, confirmation, and artifact persistence/replay;
- in-workspace memo/report lifecycle and provenance-preserving export;
- `copilot.context.v2` typed scopes, fingerprints, budgets, compaction, omissions, freshness, warnings, and source refs;
- one validated action registry with prohibited execution families structurally absent;
- automatic bounded read-only tools and the narrow confirmed DCF proposal/apply flow;
- exact shelf-to-workspace promotion;
- versioned model/storage policy, local continuation, usage/routing observability, and safe diagnostics;
- adaptive Gamma-owned custom Responses Operator as the capable-provider default, deterministic mock/disabled fallbacks, and a feature-flagged Agents SDK comparison path;
- the existing deterministic benchmark as legacy foundation evidence.
- the completed Checkpoint 7 closed-loop model-tool-model contract and Checkpoints 8A-8D temporary Fundamentals, company-resolution, hypothetical Portfolio/Risk, and Options realized-versus-implied working analyses;
- the completed Strategy Lab `Script` mode, with immutable source/input hashes, isolated no-network execution, retained typed outputs, and no general code authority.

The current benchmark is insufficient for the clarified end state. It must be extended beyond predetermined tool-presence checks.

## Completed Checkpoint 7 — closed-loop Operator core (82%; preserve)

Verified delivery:

- bounded model-tool-model continuation;
- model-produced strict arguments with deterministic server validation;
- fidelity to user-specified entities, legs, weights, shocks, dates, horizons, assumptions, and targets;
- observation-driven next-step selection and replanning;
- explicit final, insufficient-evidence, approval, cancellation, tool/budget exhaustion, and failure stops;
- final model synthesis from actual tool outputs.

Exit criteria:

- traces show the Operator observing results and making an appropriate next decision;
- an intentionally degraded tool result can cause a useful replan or honest stop;
- unrelated fixed defaults fail the gate;
- generic execution summaries fail analytical acceptance;
- custom Responses and Agents SDK variants, where maintained, use the same authoritative registry.

## Checkpoint 8 — finish entity acquisition and working-analysis state (target 89%)

Remaining delivery:

- preserve the completed entity-addressable Fundamentals, natural-company resolution, hypothetical Portfolio/Risk, Options realized-versus-implied, and Research Script contracts;
- extend Gamma-owned `ephemeral`, `draft`, and `durable` state semantics to option-set drafts, Strategy Lab inputs, temporary assumptions, and the remaining representative tab-owned analyses;
- typed owning-tab materialization/handoffs;
- deterministic expiry, discard, promotion, persistence, provenance, and restart behavior.

Exit criteria:

- the already verified unloaded-LMT, natural-company, hypothetical multi-asset portfolio/risk-shock, Options comparison, and Script cases remain green;
- option-set drafts, Strategy Lab inputs, and temporary assumptions preserve the user's exact requested values without manual tab setup;
- temporary work is visible and never confused with saved state;
- no save, rebalance, trade, or other prohibited effect occurs.

## Checkpoint 9 — interruptions, recovery, and authority transition (target 94%)

Required delivery:

- generalized pause/approve-or-reject/resume-the-same-run;
- persisted unfinished-run snapshot, observations, working-state ids, budgets, plan cursor, context fingerprint, pending tool call, and approval decision;
- bounded tool retry, replan, restart recovery, and stale-context behavior;
- idempotency that never repeats committed effects;
- visible and intentional Agent-to-Operator transition.

Exit criteria:

- approve/reject resumes the exact unfinished run;
- restart, rejection, cancellation, stale context, and retry exhaustion are typed and tested;
- Agent cannot execute Operator work before authority changes;
- no new durable mutation family lands without reusable diffs, rollback policy, persistence/replay, and permission evals.

## Checkpoint 10 — end-state acceptance and release gate (target 100%)

Required delivery:

- trace-level deterministic evals for entity acquisition, argument fidelity, plan quality, tool choice, adaptation, stopping behavior, grounded synthesis, citations/warnings, approval/resume, permission compliance, latency, and cost;
- intentionally authorized live smoke for representative Agent and Operator workflows;
- first-run, disabled/unconfigured/rate-limit/quota/degraded guidance;
- keyboard, focus, screen-reader, reduced-motion, desktop, and narrow-layout completion;
- restart/replay, migration, corrupted-state, cancellation, timeout, refusal, incomplete, and provider-error regression coverage;
- reconciled roadmap, detailed plan, this handoff prompt, README setup, and validation commands.

Required acceptance cases:

1. unloaded `LMT` fair-value workflow;
2. a user-specified hypothetical portfolio;
3. a specified portfolio risk shock;
4. an options realized/implied comparison;
5. a cross-domain workflow that must react to a degraded result;
6. a durable-state proposal that pauses and resumes the same run.

Claim 100% only when final answers are grounded in actual tool observations; all happy and non-success states are visible; recovery and approvals work; and no trading/order/account/wallet/rebalance/arbitrary-code capability or hidden sample fallback crosses the boundary.

If provider access, quota, spend authorization, or another external dependency is unavailable, complete every offline/mockable requirement, keep the percentage below 100%, and report the exact missing evidence. Never fabricate a live pass or expose secrets.

## Execution method

For each checkpoint:

1. Inspect the relevant implementation and tests before designing changes.
2. Implement the smallest coherent vertical slice that satisfies the whole outcome; avoid UI facades over missing backend state.
3. Update typed backend models, services, registry/tool schemas, run state, persistence, API contracts, frontend state/rendering, and docs together where required.
4. Add happy, degraded, failure, permission, retry, cancellation, and restart tests.
5. Grade complete traces and the final requested conclusion, not only tool presence.
6. Run focused tests, then affected regression suites.
7. Inspect desktop and narrow UI states for visual changes.
8. Update `docs/copilot_v2_tab_plan.md` and `roadmap.md` only after the checkpoint exit criteria pass.
9. Continue to the next checkpoint.

Do not broaden the tool catalog before the closed loop works. Add tools only where they enable a representative end-to-end Operator goal. Do not broaden durable mutation families before generalized interruptions and same-run recovery are proven.

## Important files

Backend/provider:

- `src/models/copilot.py`
- `src/models/copilot_context.py`
- `src/application/copilot_context_contracts.py`
- `src/services/copilot_provider.py`
- `src/services/openai_copilot_provider.py`
- `src/services/copilot_store.py`
- `src/application/copilot_service.py`
- `src/application/copilot_agents_operator.py`
- `src/application/research_action_registry.py`
- tab-owned application services
- `src/application/copilot_report_service.py`
- `src/application/runtime.py`
- `src/api/routes/copilot.py`
- `src/api/schemas/copilot.py`

Frontend:

- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/api/client.ts`
- `frontend/src/lib/copilot-run.ts`
- `frontend/src/lib/copilot-transcript.ts`
- `frontend/src/lib/copilot-result.ts`
- `frontend/src/lib/stores/app.ts`
- `frontend/src/views/CopilotView.svelte`
- Copilot transcript/card components
- owning-tab stores/views used for materialization

Tests/evals/docs:

- `tests/test_copilot.py`
- `tests/test_copilot_agents_sdk_smoke.py`
- `tests/test_copilot_operator_eval.py`
- `evals/copilot_operator_eval.py`
- Copilot frontend `*.test.ts` files
- `AGENTS.md`
- `roadmap.md`
- `docs/copilot_v2_tab_plan.md`
- `docs/copilot_v2_handoff_prompt.md`

## Validation commands

Focused backend:

`.\.venv\Scripts\python.exe -m pytest tests\test_copilot.py tests\test_copilot_agents_sdk_smoke.py tests\test_copilot_operator_eval.py`

Frontend:

`cd frontend`
`npm test`
`npm run typecheck`
`npm run build`
`npm run desktop:check`

At the final gate:

`.\.venv\Scripts\python.exe -m pytest`

Run live Agent/Operator smoke only when credentials, provider access, quota, and spend are intentionally authorized. Never print credentials.

## Progress and final response

After each checkpoint report:

- the earned checkpoint and percentage;
- user-visible and architectural outcomes;
- changed backend/frontend/tests/docs;
- focused and regression evidence;
- trace-eval results;
- any live evidence or explicitly missing live evidence;
- remaining blockers.

Claim Copilot 100% only after the remainder of Checkpoint 8 plus Checkpoints 9 and 10 pass the full acceptance gate. Keep historical checkpoints 1 through 7 and completed Checkpoint 8 slices as foundation history, identify optional post-V2 work separately, and confirm that Gamma's research-only boundary remains intact.
```
