# Copilot V2 72% To 100% Execution Prompt

Copy the text inside the block below into the agent that will complete Copilot V2.

```text
You are the implementation owner for completing Copilot V2 in:

C:\Users\User\Desktop\Gamma

Your objective is to take Copilot V2 from its verified ~72% baseline to 100% according to the checkpoint gates in `roadmap.md`. This is an implementation task, not a planning-only exercise. Work checkpoint-by-checkpoint until every 100% exit criterion is proven, unless a genuine external dependency such as missing intentionally authorized live-provider credentials prevents the final gate.

Do not stop after one convenient slice and do not ask the user to choose the next checkpoint. Follow the roadmap order, make reasonable in-scope decisions, implement coherent vertical slices, verify them, update the active documentation, and continue. Never claim a percentage merely because code was written; a percentage is earned only when that checkpoint's exit criteria pass.

## Read first

Read these files completely before editing:

1. `AGENTS.md`
2. `roadmap.md`, especially `Workstream 7 - Copilot V2`, `Path from ~72% to 100%`, sequencing rules, non-goals, and deliverable
3. `docs/copilot_v2_tab_plan.md`, especially the July 2026 completion plan, remaining engineering workstreams, delivery order, and definition of done
4. `docs/provenance_expectations.md`
5. `docs/design_principles.md` before changing Svelte/CSS
6. `README.md` for runtime, provider, and validation commands

When changing the OpenAI SDK, Responses API behavior, Agents SDK integration, model capabilities, or model policy, verify the current official OpenAI documentation first. Do not rely on remembered API shapes or change model strings based only on the model names currently written in the repo.

## Establish the real baseline

Before editing:

- run `git status --short --branch` and inspect recent Copilot commits;
- inspect all existing uncommitted changes and preserve unrelated user work;
- treat the current transcript-block, roadmap, and documentation changes as part of the intended ~72% baseline even if they are still uncommitted;
- run the focused Copilot backend tests, frontend Copilot tests, typecheck, and build to confirm the baseline;
- inspect the running Copilot UI at desktop and narrow widths when practical;
- compare code reality with the roadmap and detailed spec, correcting stale documentation without erasing useful implementation history.

Use `rg` for discovery and `apply_patch` for manual edits. Do not reset, discard, overwrite, or reformat unrelated work. Do not create commits, push, or open a pull request unless the user separately requests it.

## Non-negotiable product boundary

Gamma is a read-only research environment for market, account, and wallet activity.

Never add:

- trade execution, order placement/modification/cancellation, or routing;
- account modification or portfolio rebalancing;
- wallet connection, signing, transactions, or message signing;
- arbitrary in-app strategy/code execution;
- unrestricted browsing as a silent substitute for Gamma provider adapters;
- automatic durable local research-state mutations.

Bounded read-only analysis may run automatically. Every durable or non-trivial local research-state mutation must use Gamma's server-owned action registry and confirmation policy, show a before/after diff plus rollback/snapshot context, and stop until the exact active confirmation token is supplied.

Gamma backend services remain authoritative for tools, permissions, execution, confirmation tokens, persistence, cancellation, finalization, and mutation rules. The UI may navigate for convenience but must not become the authority for analytical execution.

## Current ~72% baseline

The baseline should include:

- quick Copilot shelf plus dedicated no-mode-bar workspace;
- Research Agent and Research Operator roles inside one workspace;
- local sessions, turns, context snapshots, search/archive/new-chat;
- planner, bounded executor, action registry, Operator plans/events, traces, reports, and confirmation foundations;
- typed read-only tools across most Gamma domains and the confirmed Fundamentals DCF mutation flow;
- direct Responses API Research Agent provider and Agents SDK Operator behind a feature flag;
- provider-native Agent Responses streaming behind the Gamma NDJSON run-event contract;
- run ids, monotonic sequences, cancellation, timeout, usage events, idempotent terminal persistence, provisional deltas, Stop/Retry, and typed refusal/incomplete/error/cancelled states;
- finalized Agent transcript blocks with full current ResearchCard fields, source-backed/inferred claims, sources, tool traces, warnings, and cardless evidence parity.

Important current gaps include the supported typed OpenAI client, reconnect/resume, shelf and Operator live-run parity, complete transcript blocks, claim/source resolution, in-tab artifacts, full session lifecycle, inline Operator confirmations, context/tool gaps, versioned model policy, retention/diagnostics, accessibility, restart replay, and full live release evidence.

## Execution method for every checkpoint

For each checkpoint below:

1. Inspect the relevant implementation and tests before designing changes.
2. Resolve the smallest coherent architecture that satisfies the whole checkpoint contract; avoid UI-only facades over missing backend state.
3. Add or update typed backend models, provider/action boundaries, persistence, API schemas/routes, frontend types/state/reducers/components, and documentation as required.
4. Add focused happy-path and failure-path tests before declaring the checkpoint complete.
5. Run the checkpoint's targeted tests, then the relevant broader regression suites.
6. Verify desktop and narrow UI behavior for visual changes, including loading, empty, selected, error, cancelled, and restored states.
7. Record the evidence in the existing Copilot plan and update `roadmap.md` to the checkpoint percentage only after every exit criterion passes.
8. Continue immediately to the next checkpoint.

Do not broaden durable mutation families before sessions/artifacts, inline confirmation, replay, cancellation, and permission invariants are reliable.

## Checkpoint 1 — finish transport and run lifecycle (76%)

Required delivery:

- replace raw `urllib` transport with the supported OpenAI SDK or an equivalent typed streaming client;
- preserve the provider boundary so mock/disabled/other providers remain swappable;
- emit Gamma events for run creation, text deltas, completed function-call arguments, tool start/result, warnings, confirmation-needed, refusal, incomplete, provider error, usage, cancellation, failure, and completion;
- put shelf Agent runs and Operator runs on the shared run-event/reducer contract;
- add reconnect/resume from a last-seen sequence or another bounded replay design;
- preserve run ids, monotonic sequences, cancellation, timeout, idempotent finalization, and finalized persistence;
- persist finalized state and bounded trace, not UI deltas as the durable truth.

Exit evidence:

- Agent and Operator each produce one run id and exactly one persisted terminal result;
- cancellation works before the first event and between safe Operator steps;
- reconnect/replay, duplicate, stale, post-terminal, disconnect, timeout, refusal, incomplete, provider-error, and cancellation tests pass;
- the shelf and workspace no longer depend on separate incompatible run paths.

## Checkpoint 2 — complete transcript and evidence contract (80%)

Required delivery:

- extend discriminated transcript blocks to plans, Operator steps/results, reports, confirmations, mutation diffs, artifacts, and every typed non-success state;
- keep source-backed claims, inference, assumptions, missing data, and warnings visibly distinct;
- validate every source-backed claim against the turn's context/tool source registry before persistence;
- reclassify or reject unresolved claims rather than persisting fake citations;
- add claim-level evidence resolution and source/context navigation using `CrossTabHandoffEnvelope` or the shared navigation contract;
- preserve selected entity, mode, timeframe, and lens where a target mapping exists;
- keep provider/model metadata secondary to the research answer.

Exit evidence:

- all persisted source-backed claim refs resolve to known source ids;
- shelf and dedicated workspace show equivalent evidence for the same result;
- supported source links open the correct Gamma destination without losing context;
- card, plan, Operator, report, confirmation, and error block tests pass.

## Checkpoint 3 — finish sessions and in-tab artifacts (86%)

Required delivery:

- add session rename, restore, delete, schema versioning, forward migrations, and corrupted-record recovery;
- persist role, depth, selected scopes, context fingerprints, resolved model/provider, run status, usage, plans, events, confirmations, artifacts, and trace state;
- build memo/report creation inside the dedicated workspace;
- support source-turn selection, template choice, title/body editing, autosave state, preview, duplicate, delete, and explicit overwrite confirmation;
- support Markdown export first; add PDF/DOCX only if an actual requirement justifies them;
- link every artifact to exact source turns, claims, sources, warnings, context snapshots, provider/model metadata, and tool-trace summary;
- show selected-session artifacts in the rail or support inspector.

Exit evidence:

- restarting Gamma faithfully restores transcript, context, plans, run state, traces, confirmations, memos, and reports;
- migrations and corrupted-record recovery have tests;
- export snapshots preserve claim categories and evidence refs;
- editing/autosave/overwrite/duplicate/delete flows have frontend and persistence coverage.

## Checkpoint 4 — productionize Research Operator (91%)

Required delivery:

- stream Operator plan/step/tool/warning/artifact/final events live through the shared run contract;
- allow cancellation only at safe boundaries and record the outcome;
- render inline confirmation checkpoints with exact proposed mutation, rationale, warnings, source ids, before/after diff, and rollback/snapshot context;
- keep one authoritative action registry, permission policy, confirmation-token service, and persistence path for custom and Agents SDK orchestrators;
- expand read-only workflow reliability before adding mutation families;
- add evals for stale/missing context, provider failure, partial tool failure, cancellation, repeated/expired confirmation, resume after restart, tool-budget enforcement, and forbidden actions;
- decide whether Agents SDK becomes the default only from measured permission, quality, trace, resumability, latency, and maintainability evidence.

Exit evidence:

- bounded read-only Operator workflows run automatically and visibly;
- every durable/non-trivial local mutation stops without the exact active token;
- expired/replayed/wrong-session tokens cannot apply;
- no execution/account/wallet/arbitrary-code tool exists in the registry;
- custom-loop versus Agents SDK comparison is recorded and the default decision is documented.

## Checkpoint 5 — close context and tool-coverage gaps (94%)

Required delivery:

- finish Sealanes context and read-only drilldowns without inventing risk labels;
- make news a first-class item-level external-context tool with URL/source/publication/freshness refs;
- add the highest-value missing Options/IV, Commodities, and Equity Research drilldowns identified in their roadmap sections;
- add context-size budgets, deterministic compaction/summaries, and stale-context invalidation;
- add source navigation mappings and stable context fingerprints for every selectable scope;
- make domain selection and omission reasoning visible.

Exit evidence:

- representative NVDA, CPI/Fed, oil-disruption, and portfolio-rate-shock prompts choose appropriate domains, explain skipped domains, preserve provenance/freshness, and degrade explicitly when data/providers are unavailable;
- provider absence never becomes fabricated evidence or a neutral blank result;
- tool contracts and representative planner/eval cases pass.

## Checkpoint 6 — finish continuity, model policy, retention, and diagnostics (97%)

Required delivery:

- add `Open in Copilot` from the shelf while preserving exact session/thread, selected contexts, entity, lens, sources, and warnings;
- create a versioned, capability-aware server model policy for product profiles such as Auto/Quick/Standard/Deep rather than scattering raw model strings;
- evaluate current candidate models/efforts against the retained passing baseline before changing defaults;
- persist and display resolved model, routing reason, reasoning effort/mode, provider, orchestrator, latency, input/output/reasoning tokens, cache reads/writes, provider calls, tool calls, and cancellation outcome;
- explain Gamma-local storage versus provider-stored responses;
- support and test `store: false` without silently breaking local continuation;
- show OpenAI/provider configuration, capability state, last safe provider error, and copyable diagnostic id in Settings and the run inspector;
- never expose credentials, raw sensitive prompts, or unsafe provider payloads in diagnostics.

Exit evidence:

- shelf promotion loses no thread or context state;
- routing and any Agents SDK default are backed by recorded evals;
- retention modes survive restart and continuation tests;
- disabled, unconfigured, unavailable, rate-limited, quota-exhausted, and provider-error states provide actionable guidance.

## Checkpoint 7 — pass the Copilot V2 release gate (100%)

Required delivery:

- finish keyboard navigation, focus management, screen-reader labels, reduced-motion behavior, desktop and narrow responsive layout, and stable loading/empty/error geometry;
- add first-run guidance for mock, disabled, unconfigured, and live-provider states;
- cover offline/mock, migrations, corrupted persistence, restart replay, cancellation, timeout, refusals, incomplete output, provider failures, and permission boundaries;
- reconcile `roadmap.md`, `docs/copilot_v2_tab_plan.md`, this handoff prompt, README provider/setup notes, and validation commands with actual behavior;
- run the complete backend, frontend, build, desktop, eval, replay, and permission suites;
- when live providers are intentionally configured, run representative live Agent and Operator smoke for NVDA, CPI/Fed, oil disruption, and portfolio rate shock;
- inspect desktop and narrow live UI states and confirm no console errors in the tested flows.

Exit evidence required before writing 100%:

- all automated suites are green;
- representative live Agent and Operator smoke is green when credentials/provider access are intentionally available;
- session restart reproduces final transcript, context, plan, events, trace, confirmations, artifacts, provider/model/usage metadata, and terminal status;
- happy, degraded, unavailable, refused, incomplete, cancelled, timeout, and provider-error states are visible and tested;
- source-backed claims resolve, warnings survive, and hidden sample fallback does not masquerade as live/provider-backed data;
- no execution-capable tool or bypass of confirmation/persistence authority exists;
- the roadmap and detailed plan truthfully state 100% and list only optional post-V2 extensions.

If live credentials or another external dependency is unavailable, complete every offline and mockable requirement, leave the release gate and percentage below 100%, and report the exact missing evidence. Do not fabricate a live pass and do not expose secret values while checking configuration.

## Cross-cutting implementation requirements

- Prefer typed backend models and service/provider adapters over unstructured dictionaries or UI-only state.
- Preserve `source_provider`, provider-native identifiers, retrieval/source timestamps, origin, transformation notes, freshness, and warnings.
- Keep provider failures typed: `unavailable`, `degraded`, `refused`, `incomplete`, `cancelled`, `timeout`, or `error` as appropriate.
- Make retries idempotent and mutation retry safety explicit.
- Keep run/event/session/artifact schemas versioned and migratable.
- Keep UI dense, flat, tokenized, and consistent with Gamma's plane model; no structural gradients, shadows, glass layers, large radii, decorative loaders, or one-off colors.
- Keep the quick shelf concise. Long plans, runs, confirmations, traces, diagnostics, and artifacts belong in the dedicated workspace.
- Add targeted tests for every failure mode introduced, not only happy paths.
- Do not add voice, unrestricted browsing, default external deep research, trading, wallet operations, arbitrary code execution, or every conceivable domain tool merely to claim 100%.

## Important files

Backend and provider:

- `src/models/copilot.py`
- `src/models/copilot_context.py`
- `src/services/copilot_provider.py`
- `src/services/openai_copilot_provider.py`
- `src/services/mock_copilot_provider.py`
- `src/services/copilot_store.py`
- `src/application/copilot_service.py`
- `src/application/copilot_agents_operator.py`
- `src/application/research_action_registry.py`
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
- `frontend/src/components/CopilotResearchCard.svelte`
- `frontend/src/components/CopilotTranscriptResult.svelte`
- `frontend/src/App.svelte`

Tests/evals/docs:

- `tests/test_copilot.py`
- `tests/test_copilot_agents_sdk_smoke.py`
- `tests/test_copilot_operator_eval.py`
- `evals/copilot_operator_eval.py`
- Copilot frontend `*.test.ts` files
- `roadmap.md`
- `docs/copilot_v2_tab_plan.md`
- `docs/copilot_v2_handoff_prompt.md`

## Validation commands

Run focused tests during development, then run at least these Copilot gates:

Backend Copilot and Operator:

`.\.venv\Scripts\python.exe -m pytest tests\test_copilot.py tests\test_copilot_agents_sdk_smoke.py tests\test_copilot_operator_eval.py`

Frontend:

`cd frontend`
`npm test`
`npm run typecheck`
`npm run build`
`npm run desktop:check`

At the 100% release gate, also run the complete repository backend suite:

`.\.venv\Scripts\python.exe -m pytest`

Run live Agent/Operator smoke only when provider credentials and spend are intentionally authorized for that run. Never print credentials.

## Required progress reporting

After each checkpoint, report:

- the checkpoint and earned percentage;
- the user-visible and architectural outcome;
- changed files grouped by backend/frontend/tests/docs;
- targeted and regression test evidence;
- any live-provider evidence or explicitly missing live evidence;
- remaining checkpoint blockers.

Keep working after the report unless the environment requires yielding. If blocked, exhaust safe in-scope alternatives first, then state the exact blocker and the highest honestly earned percentage.

## Final response contract

Claim Copilot V2 100% only when all seven roadmap checkpoints and the release evidence above are satisfied. The final response must summarize the completed system, cite the validation/eval/live-smoke evidence, identify any optional post-V2 work separately, and confirm that Gamma's read-only market/account/wallet boundary remains intact.
```
