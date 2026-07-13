# Copilot V2 Handoff Prompt

Use this prompt to continue or meaningfully advance Copilot V2.

```text
You are continuing work in C:\Users\User\Desktop\Gamma.

Read first:
- AGENTS.md instructions in the repo root.
- roadmap.md, especially Workstream 7.
- docs/copilot_v2_tab_plan.md, especially "July 2026 Copilot Completion Plan".
- docs/design_principles.md if touching frontend UI.

Current product decision:
- Copilot has two roles inside one workspace:
  1. Research Agent: grounded thesis, synthesis, challenge, and artifact drafting.
  2. Research Operator: app-native tests, simulations, traces, and confirmed local research-state workflows.
- The quick shelf remains for contextual cards. The dedicated tab owns persistent sessions, plans/runs, sources, traces, confirmations, memos, and reports.
- Agent/Operator are role controls, not top-level tab modes.
- The user approved the OpenAI Agents SDK for the Research Operator path behind Gamma's action registry.
- Gamma backend services remain authoritative for permissions, execution, confirmation tokens, persistence, and local research-state mutation rules.

Critical boundary:
- Gamma is a read-only research environment for market/account/wallet activity.
- Never add trade execution, order placement, account modification, wallet signing, wallet transactions, rebalancing, or arbitrary in-app strategy code execution.
- Read-only analytics may run automatically when bounded. Durable local research-state changes require the active confirmation policy.

Current implementation:
- Dedicated Copilot chat workspace plus contextual shelf.
- Local sessions, turns, context snapshots, archive/search, and new-chat.
- Structured research cards and explicit provider-error states.
- Research plans, bounded execution, ResearchActionRegistry, Operator plans/events, confirmation checkpoints, reports, and Markdown export routes.
- Direct Responses API Research Agent provider.
- Agents SDK Research Operator behind GAMMA_COPILOT_OPERATOR_ORCHESTRATOR=agents_sdk.
- Typed read-only tools across most major Gamma domains and a confirmed Fundamentals DCF mutation flow.
- Operator eval harness with passing custom-loop and offline Agents SDK cases; current live baseline is GPT-5.5.

Authoritative next delivery order:
1. Provider-native streaming and explicit provider/run state.
2. Typed transcript blocks and full evidence/source/tool/warning parity between the shelf and dedicated tab.
3. Complete in-tab memo/report editing, export, and session lifecycle.
4. Live Operator events, cancellation, and inline confirmations.
5. Missing Sealanes/news and high-value IV/Commodities/Equity Research drilldowns plus source navigation.
6. Eval-backed GPT-5.6 model policy and routing.
7. Agents SDK default-orchestrator decision.
8. Diagnostics, first-run guidance, accessibility, and release validation.
9. Optional explicit external deep research; voice remains later.

OpenAI model direction as of 2026-07-13:
- Do not make a model-string-only migration.
- Compare GPT-5.6 Terra low/medium with the passing GPT-5.5 baseline for standard Agent and Operator work.
- Reserve GPT-5.6 Sol for deep synthesis/report work only where evals show a material gain.
- Use GPT-5.6 Luna only for low-risk auxiliary work after grounding/citation evals pass.
- Keep the Responses Multi-agent beta out of the default path while Gamma needs stricter tool-call budgets and permission control.
- Keep Agents SDK as the controlled Operator orchestration candidate behind the Gamma action registry.

First implementation slice:
1. Replace the synchronous OpenAI provider call and wrapper stream with provider-native Responses semantic events.
2. Define one Gamma run-event contract for Agent and Operator: created, text delta, tool call/result, warning, confirmation-needed, refusal, incomplete, cancelled, failed, usage, and completed.
3. Add run ids, monotonic sequence ids, cancellation, timeout, idempotent finalization, and persistence/replay tests.
4. Build the frontend event reducer, real incremental rendering, Stop/Retry controls, and typed final/non-success blocks.
5. Remove the client-side fake typewriter after real deltas are verified.

Relevant files:
- src/services/openai_copilot_provider.py
- src/application/copilot_service.py
- src/application/copilot_agents_operator.py
- src/application/research_action_registry.py
- src/application/runtime.py
- src/models/copilot.py
- src/api/routes/copilot.py
- src/api/schemas/copilot.py
- src/services/copilot_store.py
- evals/copilot_operator_eval.py
- tests/test_copilot.py
- tests/test_copilot_agents_sdk_smoke.py
- frontend/src/lib/api/types.ts
- frontend/src/lib/stores/app.ts
- frontend/src/views/CopilotView.svelte
- frontend/src/components/CopilotResearchCard.svelte
- docs/copilot_v2_tab_plan.md

Validation:
- python -m pytest tests/test_copilot.py tests/test_copilot_agents_sdk_smoke.py tests/test_copilot_operator_eval.py
- cd frontend; npm run typecheck
- cd frontend; npm run build
- cd frontend; npm test -- CopilotView CopilotResearchCard copilot-result
- Run the live Agent/Operator smoke suite only when OPENAI_API_KEY is intentionally configured for that run.

Watch out:
- Preserve unrelated dirty worktree changes.
- Use rg for searching and apply_patch for manual edits.
- Provider/model errors must be visible and typed; never downgrade them to neutral empty cards.
- Validate every source-backed claim against known context/tool source ids.
- Do not broaden durable mutation families before streaming, cancellation, inline confirmation, and read-only Operator reliability are complete.
```
