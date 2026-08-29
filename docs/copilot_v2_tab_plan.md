# Copilot V2 Agentic Research Harness

_Living planning document. Future agents should update the status checklist and decision log as implementation progresses._

Last updated: 2026-08-29

## Start Here

Gamma's Copilot should become a broad **agentic research assistant** that can use Gamma's research surfaces intelligently, not a DCF-specific assistant and not a trading/execution agent.

Before implementing changes, read:

- [`../roadmap.md`](../roadmap.md) for the core product boundary and current Workstream 1 / Workstream 7 direction.
- [`provenance_expectations.md`](./provenance_expectations.md) for source, freshness, and transformation expectations.
- [`design_principles.md`](./design_principles.md) before changing the Copilot UI.
- [`research_script_workspace_plan.md`](./research_script_workspace_plan.md) before changing Operator script drafting, Script-mode materialization, hosted runtime behavior, source revisions, or script-run permissions.

Relevant current code:

- `src/application/copilot_service.py`: current Copilot context builders, tool registry, tool execution, persistence handoff.
- `src/services/openai_copilot_provider.py`: current Responses API provider wrapper and structured research-card output.
- `src/models/copilot.py`: Copilot request/result/session/memo models.
- `src/models/copilot_context.py`: compact context contract and read-only safety metadata.
- `src/models/platform_boundary.py`: app-wide read-only boundary.
- `src/api/routes/copilot.py`: Copilot card, stream, sessions, and memo routes.
- `src/services/copilot_store.py`: local session, turn, context snapshot, and memo persistence.
- `src/api/routes/fundamentals.py`: example of a domain that already has local state-changing research routes for DCF save/snapshot.
- `src/application/fundamentals_service.py`: DCF materialization, saving, snapshots, reverse valuation, peers, and reference/filing context.

## Product Intent

The target is a **Gamma research agent**:

- It can understand broad research requests such as "Research NVDA", "what is going on in oil?", or "is my portfolio exposed to a rate shock?"
- It can decide which Gamma domains are relevant and how deep to go in each one.
- It can run analyses through typed Gamma tools across Equity Research, Strategy Lab, Risk, Options, Fundamentals, Macro, Commodities, Prediction Markets, Crypto, Portfolio, Sealanes, and item-level news.
- It can fetch limited outside context, such as recent news, analyst expectations, transcripts, filings, and official events, through approved read-only adapters.
- It can save research sessions, source snapshots, DCF/model snapshots where applicable, memos, and final reports.
- It can propose local research-state edits and apply them only after explicit user confirmation.

It should not:

- place, modify, cancel, or route orders;
- rebalance a portfolio;
- submit wallet transactions, sign messages, or connect wallets;
- execute unrestricted or host-integrated user code; the only approved exception is the isolated Research Script Workspace contract, which grants no Gamma, host, credential, broker, wallet, network, or execution authority;
- browse the UI visually as its primary mechanism;
- use unrestricted web browsing as a default substitute for provider adapters;
- hide unsupported data gaps behind confident prose.

## Two Copilot Roles

Copilot should develop into two related roles. They are not separate products and the user should be able to move between them naturally, but they imply different orchestration, permission, and UI expectations.

### 1. Research Agent

The Research Agent is the context-bounded interpretation role. It helps form, structure, and challenge a thesis from the context the user supplied or selected. It identifies supporting evidence, counter-evidence, missing data, and outputs an opinion, explanation, thesis, memo, or report without operating the app on the user's behalf.

Examples:

- "Is the market underpricing oil disruption risk?"
- "Research NVDA into CPI/Fed week."
- "Compare AI crypto tokens against AI equities."
- "Does this prediction market disagree with macro data?"

Expected behavior:

- read and synthesize the current surface, selected scopes, and other context already attached to the turn;
- separate source-backed claims from model-inferred claims;
- make disconfirming evidence and missing data explicit;
- produce concise thesis structures, memos, and reports;
- do not load missing entities, run analytical workflows, or create/modify app working state;
- explain when the question cannot be answered from the supplied context and offer an Operator workflow instead of silently escalating its own authority;
- avoid changing durable local research state unless the user explicitly asks for an artifact to be saved.

This role can remain mostly compatible with the current context, synthesis, session trace, and report path. The selected role is an authority ceiling: an Agent turn must not silently become an Operator turn.

### 2. Research Operator

The Research Operator can run Gamma workflows on the user's behalf. It may still help form a thesis, but its distinguishing behavior is that it chooses and runs appropriate app-native tests, simulations, and local research-state workflows, then produces a traceable report the user can read before making any real-world decision.

Examples:

- adjust DCF assumptions, show the diff, and apply only after confirmation;
- run reverse valuation and compare implied expectations to current model assumptions;
- run portfolio/risk stress tests for a rate shock, oil shock, or drawdown scenario;
- build hypothetical or saved research portfolios and compare them to benchmarks;
- run Strategy Lab backtests over imported return streams or Gamma object compositions;
- draft a transparent Python research script, materialize it into Strategy Lab, and run it only when the user explicitly invokes the isolated Script workflow;
- compare options implied moves, realized volatility, macro event context, and fundamentals for a single-name event;
- save a final memo or report with tool traces, sources, warnings, and generated artifacts.

Expected behavior:

- produce a structured plan before non-trivial operation;
- call typed Gamma tools rather than visually clicking the UI as the primary mechanism;
- resolve and load entities or analytical inputs even when they are not already active in the UI;
- create session-scoped working objects, set temporary assumptions, and run bounded read-only analyses automatically when they fit the request;
- create an isolated Script draft only for an explicit Operator Script request; after materialization, preserve user-controlled canonical source and stage any later Operator revision as a visible diff;
- inspect each tool result, revise parameters or choose another authorized tool, and continue until it can answer or reaches a declared stopping condition;
- draft durable local research-state changes automatically, but apply them only under the active confirmation policy;
- preserve source refs, warnings, tool traces, and before/after diffs;
- synthesize the final user-facing conclusion from the actual tool outputs, rather than returning a generic execution summary;
- materialize relevant results in Gamma's corresponding tab or working state where useful, and navigate the UI only as a convenience after the authoritative backend action has run.

The Research Operator is the stronger justification for Agents SDK or a hybrid orchestration layer because it needs a genuine model-tool-model loop, resumable run state, progress streaming, approval interruptions, trace inspection, and evals for whether it selected appropriate tests. Even if Agents SDK is adopted, Gamma's backend remains the authority for permissions, execution, persistence, and the read-only product boundary.

### Authority And Interaction Contract

The two roles are differentiated by authority, not by how verbose or capable the model sounds:

| Capability | Research Agent | Research Operator |
|---|---|---|
| Interpret attached/current Gamma context | Yes | Yes |
| Produce analysis, opinions, theses, and reports | Yes | Yes |
| Acquire an entity that is not loaded | No; disclose the missing context and offer Operator | Yes, through entity-addressable Gamma tools |
| Run DCF, risk, portfolio, options, or strategy workflows | No | Yes |
| Set temporary/session-scoped analytical inputs | No | Yes, automatically and visibly |
| Adapt the plan after observing tool output | No | Yes, within budgets and the action registry |
| Persist a new artifact explicitly requested by the user | Yes | Yes |
| Change existing durable research state | No | Only through the applicable confirmation policy |
| Trade, rebalance, route orders, mutate accounts/wallets, or execute unrestricted/host code | Never | Never; Operator may use only the isolated Script Workspace contract |

An explicit Operator request authorizes app-native research work within the selected scopes and the registry's limits; it does not authorize real-world execution. If the user is in Agent mode and asks for work that requires operating Gamma, Copilot should explain the required workflow and offer a visible transition to Operator. It must not hide the authority change.

### Reference Operator Workflow: “What Is The Fair Value Of LMT?”

When this request is made in Operator mode, `LMT` does not need to be preloaded. The intended workflow is:

1. Resolve `LMT` to a supported instrument and acquire the required provider-backed company, filing, market, and valuation context through Gamma services.
2. Create or reuse a session-scoped Fundamentals/DCF working object without silently saving it as durable user state.
3. Inspect data availability and quality, select an appropriate valuation workflow, and expose any defaults or temporary assumptions it introduces.
4. Run the DCF, reverse valuation, sensitivity, or related authorized tests needed to answer the question.
5. Inspect the results and adapt: for example, change a temporary assumption, request an additional sensitivity, or stop with a typed degraded state when evidence is insufficient.
6. Produce a fair-value estimate or range grounded in the tool results, with assumptions, provenance, warnings, and the distinction between reported inputs and model judgment.
7. Optionally open/materialize the resulting DCF in Fundamentals. Persisting edits to an existing saved DCF remains confirmation-gated.

The same contract applies to portfolio composition, risk scenarios, options analyses, Strategy Lab runs, and other tab-owned research capabilities. A tool's analytical depth is limited by its owning tab/service, but the Operator must be able to acquire inputs, invoke it, react to its results, and complete the workflow without requiring the user to pre-stage every screen.

### Reference Operator Workflow: “Draft And Run A Moving-Average Strategy”

When this request explicitly invokes the Script workflow in Operator mode, the intended flow is:

1. Resolve the supported instrument and acquire provider-backed historical data through Gamma services.
2. Create a copied, read-only input snapshot plus provenance manifest.
3. Create a session-ephemeral Python draft with an immutable source revision and SHA-256 hash.
4. Materialize the draft into `Strategy Lab / Script`; do not silently save a durable strategy.
5. If the user requested execution, run that exact revision in the approved isolated runtime and return the outputs as observations.
6. Persist logs, tables, images, files, warnings, usage, source refs, and provider diagnostics in Gamma-owned storage before the provider container expires.
7. Synthesize the result from the actual run outputs. Any later Operator code change is a staged revision, while the visible canonical source remains user-controlled.

This workflow grants no local shell, Gamma API, environment, credential, TWS/IBKR, account, wallet, order, host-filesystem, or outbound-network authority. The detailed contract and delivery status live in [`research_script_workspace_plan.md`](./research_script_workspace_plan.md).

## Core Design Principle

The agent should "use the app" by calling app-native tools, not by clicking the UI.

Preferred model:

```text
User request
  -> resolve role, intent, entities, and authority
  -> create a bounded Gamma-owned run and working-analysis state
  -> model proposes a typed plan or next tool call
  -> Gamma validates permission, schema, context, and budget
  -> app-native backend tool executes
  -> result returns to the model
  -> model adapts, calls another authorized tool, stops for approval, or finishes
  -> final synthesis from actual tool results with citations/warnings
  -> saved session/memo/report
  -> optional app materialization or confirmed durable local state change
```

The loop is complete only when tool results are returned to the model as observations and the model can choose the next authorized step. A deterministic prewritten sequence can remain a fallback or a workflow primitive, but it is not by itself the desired Research Operator.

Avoid:

```text
User request
  -> model directly controls UI
  -> hidden clicks / fragile DOM state
  -> untyped side effects
  -> weak audit trail
```

UI navigation can still exist as a convenience action, such as opening the Fundamentals DCF view after a DCF analysis. It should not be the authority for analysis execution.

## OpenAI References

### Standing Review Rule

Before any material Copilot architecture, orchestration, tool, approval, run-state, model-routing, or related documentation change, the implementing agent must refresh the current official OpenAI guidance. Prefer the OpenAI Developer Docs connector when available; otherwise use only official `developers.openai.com` pages. Record the review date, URLs, and resulting decision in this section or the decision log below. These notes are a dated snapshot, not permanent API truth.

Do not switch frameworks or models solely because a newer option exists. Compare the current Responses API and Agents SDK guidance against Gamma's required loop, permission invariants, persistence model, eval results, latency, reliability, and cost.

### Official Guidance Re-Reviewed 2026-08-29

- [Code Interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter): the hosted tool writes and runs Python in a sandboxed container, accepts uploaded files, and can generate files/images. Containers are ephemeral, so Gamma must persist source, manifests, run metadata, and retained outputs independently.
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling): Script draft/run actions remain strict application-defined tools with `additionalProperties: false` and every property required, using nullable types for optional values.
- [Responses create](https://developers.openai.com/api/reference/resources/responses/methods/create): the Responses request owns model/tool selection and returns typed output items. Gamma continues to own tool exposure, sequential observations, permissions, validation, persistence, and terminal truth.

Installed SDK review: `openai==2.38.0`. The inspected package supports `responses.create`, `responses.cancel`, `containers.create`, `containers.files.create`, `containers.files.list`, and `containers.files.content.retrieve`, along with Code Interpreter output items and container-file annotations. OpenAI SDK and Responses types remain confined to the provider adapter. Synchronous v1 Research Script execution does not claim provider cancellation support; Gamma records the honest capability and reconciles late results after a local terminal cancellation.

Research Script Workspace architectural decision from the 2026-08-29 review:

- Approve the narrow Workstream 2A exception documented in [`research_script_workspace_plan.md`](./research_script_workspace_plan.md): Operator may draft and explicitly run Python only through the Strategy Lab `Script` workflow.
- Use a provider-neutral runtime contract. `MockResearchScriptRuntime` lands first; OpenAI Code Interpreter is the preferred first real adapter only if the exact-source/hash spike passes.
- Keep source revisions, input snapshots, runs, outputs, limits, permissions, and audit state Gamma-owned. Provider container/response state is transport metadata, not the authoritative record.
- Treat containers as ephemeral and download retained files into Gamma-owned storage immediately. Expired containers are recovered by replaying the same immutable revision and input snapshot in a new container.
- Keep outbound network disabled and acquire external data through Gamma's provider adapters. Do not expose provider credentials, Gamma APIs, localhost, TWS/IBKR, accounts, wallets, host files, or environment variables to the runtime.
- Keep the current custom Responses Operator as the default control plane and the Agents SDK as the feature-flagged comparison. No framework or default-model switch is justified by the Script Workspace.
- Preserve user edit authority after materialization: Operator-created follow-up changes are staged revisions or diffs, never silent canonical-source overwrites.
- Keep Gamma's configured `gpt-5.4` default. Its published capability supports Code Interpreter; the adapter capability-checks the configured provider/model and keeps the mock runtime when unsupported instead of silently selecting another model.
- Approve `strategy_lab.draft_research_script` and `strategy_lab.run_research_script` as the only new Script action ids. `run_strategy_lab_backtest` remains unchanged. Draft requires an explicit Script workflow; run requires an explicit current-turn execution request plus exact script, revision, snapshot, source-hash, and manifest-hash arguments.
- Extend `copilot.working-analysis.v1` with `copilot.strategy-lab-script-working-analysis.v1`, materialized non-durably to Strategy Lab / Script. The visible canonical editor, staged accept/reject controls, and stale-parent conflicts remain Gamma-owned.
- App-native input acquisition may copy only supported bounded data (v1: configured symbol history) into the immutable snapshot. Unsupported acquisition produces explicit warnings and never grants runtime network, shell, package, broker, account, wallet, order, credential, localhost, or host-filesystem authority.
- Verification on 2026-08-29: 12 Script Operator tests passed inside the combined `55 passed, 1 skipped` Script/API suite and again in a focused `12 passed in 2.37s` rerun; 14 selected existing action/permission/store/custom-loop regressions passed; the Script-specific eval passed all 12 checks; the retained Operator eval passed all 31 deterministic outcomes with average score `0.9092741935483871`; 384 frontend tests, typecheck, and production build passed. The retained eval harness now forces mock/sample providers unless a live flag is explicit. A broader `tests/test_copilot.py` run retained seven unrelated current-worktree failures in legacy entity/intent, elapsed-budget, and external-context cases (`132 passed, 7 failed`); none exercises the Research Script action/runtime/permission/materialization family, and this scoped implementation did not modify those expectations.

### Official Guidance Re-Reviewed 2026-08-25

- [Latest model guidance](https://developers.openai.com/api/docs/guides/latest-model): GPT-5.6 is the current documented production baseline family, but model migration still requires Gamma's representative quality, latency, reliability, and cost evals rather than an alias-only change.
- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state): Responses supports provider-managed continuation through Conversations or `previous_response_id`; response storage has provider retention consequences, so Gamma-local session, working-analysis, approval, and recovery records remain authoritative and must work with provider storage disabled.
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling): strict schemas remain recommended; object schemas require `additionalProperties: false` and every property marked required, with nullable types for optional values. Disabling parallel tool calls remains appropriate when each observation can change the next authorized decision.

Checkpoint 8 architectural decision from the 2026-08-25 review:

- Keep the Gamma-owned custom Responses loop as the default and the Agents SDK as a feature-flagged comparison. This checkpoint adds no framework or default-model migration because the working-analysis problem is application authority and state ownership, not provider orchestration novelty.
- Keep `parallel_tool_calls=false` semantics for the adaptive Operator path. Entity acquisition, analytical output, warnings, and temporary materialization can change the next bounded decision and therefore remain sequential observations.
- Treat provider conversation/response state as optional transport continuation, never as Gamma's only working-state copy. `copilot.working-analysis.v1` is persisted locally with entity identity, inputs, outputs, sources, context fingerprint, lifecycle timestamps, and typed owning-tab materialization.
- Opening a working analysis may set temporary visible UI state, but it does not save or mutate a durable DCF. Existing durable Fundamentals changes remain behind the server-owned confirmation contract.

Natural-language entity-resolution addendum from the same 2026-08-25 review:

- [Function calling](https://developers.openai.com/api/docs/guides/function-calling) confirms the application-defined boundary used here: the model may select a strict function and supply schema-valid arguments, while the application executes the lookup and returns the observation. Gamma therefore uses one forced, strict `propose_equity_entity` function call only as a semantic proposal for natural company names.
- The proposal is not canonical identity. Gamma validates the proposed ticker and legal issuer name against the existing SEC Fundamentals reference adapter, records the proposal and authoritative candidates separately, and injects a ticker into Operator context only after one unique match is established.
- Explicit user tickers and the active server-owned Fundamentals ticker bypass the model proposal. Deterministic plan previews use SEC name search without spending a model call. Ambiguous issuer/share-class matches produce a typed `entity_disambiguation` plan with zero analytical tool budget and require an explicit ticker before the run can continue.
- The preflight follows the selected provider-storage policy, uses `parallel_tool_calls=false`, records its provider usage in the terminal run, and grants no new tool, mutation, trading, order, account, wallet, portfolio, or arbitrary-code authority. No framework or default-model change was justified by this addition.

Checkpoint 8C working-state addendum from the same 2026-08-25 review:

- [Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create) continues to define function tools as application-supplied custom code with typed inputs and outputs. Gamma therefore keeps portfolio construction, Risk execution, validation, persistence, and materialization in app-native services; the model only chooses among authorized strict tools and supplies arguments.
- Provider response continuation remains optional transport state. The exact temporary legs, normalized weights, shocks, observations, sources, and lifecycle timestamps are merged into one Gamma-owned `copilot.working-analysis.v1` record and replay without `previous_response_id` or provider storage.
- No framework or default-model switch was justified. The custom Responses loop remains the default and the Agents SDK remains the feature-flagged comparison; both call the same registry handlers and working-analysis decorator. Risk materialization is a typed temporary view in the existing Risk tab, never a saved portfolio, rebalance, order, or trading action.

### Official Guidance Re-Reviewed 2026-07-30

- [Build agents and compare the Responses API with the Agents SDK](https://developers.openai.com/api/docs/guides/agents#compare-the-responses-api-and-agents-sdk): Responses is appropriate when the application owns a custom loop; the Agents SDK provides a built-in lifecycle for bounded workflows, sessions, guardrails, approvals, traces, and orchestration.
- [Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents): a real agent run is a model-tool-model loop that continues until final output or a declared stopping condition; sessions are the preferred default for durable history and resumable approvals.
- [Orchestration](https://developers.openai.com/api/docs/guides/agents/orchestration): start with one agent and add specialists only when their contracts differ; use manager-style agents-as-tools when one orchestrator must retain ownership of the final answer.
- [Guardrails and approvals](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals): validate inputs, outputs, and tool calls near the relevant boundary; approval is an interruption carrying resumable run state, followed by approve/reject and continuation of the same run.
- [Agent results and state](https://developers.openai.com/api/docs/guides/agents/results): results expose final output, interruptions, and continuation state; Gamma should persist the application-owned snapshot required to inspect and resume safely.
- [Tools](https://developers.openai.com/api/docs/guides/tools): expose narrow, typed function tools with strict schemas and clear behavior rather than granting general UI or compute access.
- [Tracing](https://developers.openai.com/api/docs/guides/agents/integrations-observability#tracing) and [trace grading](https://developers.openai.com/api/docs/guides/trace-grading): capture model calls, tool calls/results, guardrails, approvals, and orchestration spans; grade end-to-end traces to catch workflow regressions, not only final-answer errors.
- [Agent evals](https://developers.openai.com/api/docs/guides/agent-evals): keep repeatable workflow-level evals around tool selection, argument fidelity, observation use, stopping, final-answer quality, and regressions rather than judging the harness only by a final string.
- [Latest model guidance](https://developers.openai.com/api/docs/guides/latest-model), [Streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), and [prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching): keep model routing and provider behavior versioned, observable, and eval-backed.

Architectural interpretation for Gamma:

- The harness is Gamma's control plane: it owns the loop, action registry, permissions, state, budgets, approvals, recovery, tracing, and final persistence. The model proposes actions; Gamma authorizes and executes them.
- The direct Responses API remains valid for the context-bounded Research Agent and for a deliberately custom Operator loop. Agents SDK is preferred when it materially simplifies the required sessions, interruptions, guardrails, tracing, or orchestration without weakening Gamma's authority.
- Use one manager Operator first. Add tab/domain specialists only when separate instructions, tool sets, or handoff contracts demonstrably improve eval outcomes; the manager retains final-answer ownership.
- Use strict, entity-addressable Gamma function tools. Each tool contract states what it does, when to use it, required inputs, whether it creates ephemeral or durable state, retry/idempotency behavior, outputs, failure states, and provenance.
- Persist a Gamma-owned run/session snapshot even when provider-managed continuation is enabled. Provider state must never be Gamma's only transcript, approval, or recovery record.
- Treat approvals as paused runs, not fresh chat turns. An approval token must resume the same unfinished run with the same plan, context fingerprint, observations, budgets, and audit trail.
- Trace and evaluate the full workflow: entity resolution, plan quality, parameter choice, tool selection, adaptation, stopping behavior, synthesis, citations, approval behavior, and permission-boundary compliance.
- Do not add general sandbox or arbitrary-code execution to Copilot. OpenAI sandbox guidance is not a reason to cross Gamma's research-only boundary; analytical compute remains inside typed, bounded Gamma services.
- Hosted web/file/deep-research tools may be considered only as explicit, bounded research features with retention, cost, source, and permission controls. Approved provider adapters remain preferred for durable Gamma workflows.

Checkpoint 7 decision from the 2026-07-30 review:

- Keep the Gamma-owned custom Responses loop as the default orchestration path when the configured provider supports it; keep the Agents SDK as the maintained feature-flagged comparison path. The current guidance supports both responsibility splits, so the choice remains governed by Gamma's permission invariants and evals rather than framework novelty.
- In both paths, expose one strict function schema per authorized read-only Gamma action. The model supplies the complete arguments; Gamma re-authorizes the action, validates the JSON-schema subset at the server boundary without hidden defaults/coercion, executes it, and returns the bounded observation to the same run.
- Treat `final_output`/the final structured Responses message as the user-facing synthesis only after at least one required validated observation exists. Tool-count summaries, malformed argument fallback, and a final card detached from tool outputs do not satisfy the contract.
- Keep approval resumption and generalized working-state persistence for Checkpoints 8-9. Checkpoint 7 does not delegate those responsibilities to provider state or add any trading, order, account, wallet, rebalancing, or arbitrary-code authority.

## July 2026 Copilot Completion Plan

This section is the authoritative remaining-work layout for completing the in-app Copilot. It reconciles the current roadmap, the shipped code, the June/July UI rebuild, and the current OpenAI model/API guidance. Older phase notes below remain useful implementation history, but this section owns priority and completion scope.

### Current Reality

Gamma already has more than a chat shell:

- a dedicated chat workspace and a contextual shelf;
- local sessions, turns, context snapshots, archive/search, and new-chat flows;
- structured research cards with source-backed and inferred claim fields;
- planner, bounded executor, action registry, operator plans, confirmation checkpoints, persisted traces, reports, and Markdown export routes;
- a direct Responses API provider and an Agents SDK Research Operator behind a feature flag;
- typed read-only tools across most major Gamma domains;
- a narrow confirmed DCF mutation flow with rollback context;
- offline and optional live operator eval paths.

The earlier 97% claim measured a narrower completion boundary: a grounded chat workspace plus a bounded, registry-owned workflow executor. Against the clarified end state in this document, Copilot is **approximately 85% complete** through Checkpoint 8C. This is a scope correction plus verified capability advances, not a regression or loss of delivered work. Checkpoints 1 through 6 remain verified foundation, Checkpoint 7 adds the bounded closed-loop Operator core, and Checkpoints 8A-8C prove unloaded-company Fundamentals plus user-specified hypothetical portfolio/Risk working-analysis and materialization contracts without yet generalizing them to every analytical family.

The material remaining gaps are product behavior, not only release hardening:

- public-company names now have a model-assisted, SEC-validated ticker preflight, but entity and intent acquisition remain shallow for other asset classes and multi-entity workflows;
- entity acquisition remains inconsistent across non-Fundamentals tools; several workflows still depend on already-active tab context or precomputed results;
- the versioned session-scoped working-analysis contract now covers unloaded Fundamentals reverse valuation and user-specified hypothetical portfolio/Risk workflows, but option sets, strategy inputs, temporary assumptions, and remaining cross-tool outputs are not yet covered;
- Fundamentals reverse-valuation and Risk scenario results can now materialize temporarily in their owning tabs, but other tool results do not yet consistently materialize in the corresponding Gamma tab or working object;
- the durable approval model is narrow and DCF-specific rather than a general pause/approve-or-reject/resume-the-same-run contract;
- replayable events preserve history, but do not yet provide generalized workflow recovery, replanning, retries, or approval resumption;
- role escalation from Agent to Operator is not yet a complete, visible authority transition;
- accessibility, first-run, responsive, and representative live-provider release evidence also remains open after the Operator outcome work.

### Completion Boundary

Copilot is complete for the clarified Gamma pass when a user can do all of the following without leaving the app or reading backend logs:

1. Start, search, rename, archive, restore, and delete a research conversation.
2. See exactly which Gamma contexts, entities, timeframes, freshness states, and warnings ground the turn.
3. Use Research Agent to interpret only the attached/current context without silently loading entities, running workflows, or changing app state.
4. Ask Research Operator a goal such as “What is the fair value of LMT?” when the entity is not loaded and have it resolve the entity, create an ephemeral working analysis, run the required app-native workflows, adapt to results, and answer.
5. Ask Research Operator to compose a hypothetical portfolio, run a specified risk scenario, run a DCF/reverse valuation, or invoke another supported tab-owned research workflow without manually pre-staging every tab.
6. Inspect the plan, temporary assumptions, parameters, tool calls, progress, results, warnings, and stopping reason; stop the run safely when desired.
7. Receive a final answer synthesized from the actual tool outputs, clearly separating source-backed facts, analytical outputs, assumptions, inference, missing data, and warnings.
8. See relevant Operator work materialized in the appropriate Gamma tab or session-scoped working object without confusing temporary state with saved state.
9. Reach an inline confirmation checkpoint for any durable local research-state mutation, inspect the before/after diff and rollback context, then approve or reject and resume the same run.
10. Reopen or recover a run and retain its transcript, context snapshots, working state, observations, plans, events, budgets, artifacts, approvals, and provider metadata faithfully.
11. Create, edit, autosave, duplicate, and export a memo or report inside the Copilot workspace.
12. Get explicit `unavailable`, `degraded`, `refused`, `incomplete`, `cancelled`, and `error` states instead of a neutral empty card.
13. Use the shelf for quick contextual work and promote that exact thread/context into the full workspace without losing state.

Voice, unrestricted web browsing, unrestricted code execution, trading/account/wallet actions, and automatic durable mutations are not current-pass completion requirements. The separately approved Research Script Workspace is tracked in Roadmap Workstream 2A and is not a blocker for Copilot V2's current completion gate. Explicit long-running external deep research is a later opt-in extension, not the default answer path.

### Final In-App Layout

Copilot remains one research workspace, not a collection of top-level modes. `Research Agent` and `Research Operator` are visible authority controls, not tab modes.

```text
Copilot workspace
  Left rail (14-16rem)
    New conversation
    Search / active / archived filters
    Conversation list
    Saved artifacts for selected conversation

  Primary transcript
    Compact run header
      Context scope + freshness/warning count
      Agent / Operator
      Depth: Quick / Standard / Deep
      Model profile: Auto (resolved model shown, advanced override optional)
    Transcript
      User turns
      Streamed answer blocks
      Plans and approval checkpoints
      Live operator steps
      Cards, diffs, memos, and reports
    Pinned composer
      Prompt / stop / retry
      Plan or run action
      Explicit save/export action

  Collapsible support inspector (18-22rem)
    Context
    Run / trace
    Sources and warnings
    Artifacts
    Provider / model / token / latency diagnostics
```

At medium widths, the inspector becomes an in-workspace drawer. At narrow widths, the conversation rail becomes a compact overlay and the transcript remains primary. The quick shelf keeps its smaller card-oriented layout and gains `Open in Copilot` rather than reproducing the full operator/artifact UI.

Required UI behavior:

- render the full research-card contract in the dedicated tab, including required data, confounders, next steps, caveats, source-backed claims, inferred claims, tools, and warnings;
- put citations beside the claims they support and let a source open the originating Gamma tab/mode/entity when a handoff exists;
- show provider/model as secondary metadata, not as the main answer label;
- replace the client-side typewriter simulation with provider deltas and a stable final structured render;
- keep partial text visibly provisional until the schema-valid final result is available;
- show tool-start/tool-result/confirmation/error events as compact status rows and move verbose payloads to the inspector;
- add Stop, Retry, Copy, Save as memo, Export report, and Open source actions;
- preserve selected contexts and role/depth per session, while preventing stale context from silently carrying into a new conversation;
- keep destructive session deletion and durable mutation application confirmation-gated.

### OpenAI Model Fit And Routing

The current OpenAI guidance names GPT-5.6 as the latest family. All three GPT-5.6 tiers support Responses, streaming, structured outputs, function calling, web/file search, prompt caching, text/image input, and a 1,050,000-token context window. Gamma should expose product-level profiles and record the resolved model on every turn rather than force most users to choose raw model slugs.

| Gamma workload | Candidate | Starting effort | Rationale |
|---|---|---:|---|
| Standard Research Agent answer and synthesis | `gpt-5.6-terra` | `medium` | Best default candidate for research quality versus cost. |
| Quick follow-up, title, compact summary, low-risk formatting | `gpt-5.6-luna` | `low` or `none` | High-volume efficiency; only adopt where evals show no grounding/citation regression. |
| Standard Research Operator tool selection | `gpt-5.6-terra` | `low`, compare `medium` | Natural successor candidate to the current passing GPT-5.5-low operator baseline. |
| Deep cross-domain synthesis or difficult final report review | `gpt-5.6-sol` | `medium` or `high` | Reserve frontier capacity for work with measured quality benefit. |
| Quality-first final review | same selected GPT-5.6 tier with `reasoning.mode: pro` | eval-backed | Use only for non-interactive, quality-first work; it is not the normal streaming chat path. |
| Explicit outside-source deep research | `o4-mini-deep-research` or `o3-deep-research` | background job | Optional future workflow requiring source tools, long-run UX, retention disclosure, and separate cost limits. |

Migration policy:

- keep current GPT-5.5 defaults until the existing live operator and research-card eval suites run against GPT-5.6;
- benchmark `gpt-5.6-terra` low/medium against GPT-5.5 low/medium first, then test Sol only on cases where Terra misses quality gates;
- do not route by model marketing tier alone; route by depth profile, task risk, tool complexity, latency budget, and measured eval performance;
- resolve `Auto` server-side and persist model, reasoning effort/mode, provider, usage, latency, cache reads/writes, and routing reason;
- allow an advanced per-run override, but keep provider availability and safety policy authoritative;
- use a versioned model-policy configuration instead of scattering model strings through runtime, tests, and UI.

Feature fit:

- **Provider-native Responses streaming:** adopt now. It directly solves the largest UX/reliability gap.
- **Structured Outputs:** keep, but generate/validate the schema from one typed source where practical; handle refusal and incomplete events separately from parse failure.
- **Persisted reasoning and response continuation:** evaluate per session with explicit retention controls. Do not let OpenAI response state become Gamma's only transcript store.
- **Prompt caching:** instrument current cache behavior first. For GPT-5.6, evaluate explicit breakpoints around stable instructions/tool schemas and track both cache reads and billable cache writes.
- **Programmatic Tool Calling:** do not use it to replace Gamma analytics. Consider it only for bounded, read-only filtering/joining/reduction after direct function-tool execution remains authoritative.
- **Responses Multi-agent beta:** do not make it the default operator. It can parallelize independent domain research, but its beta schema, shared tool visibility, extra token use, and lack of `max_tool_calls` support conflict with Gamma's current deterministic budget controls. Re-evaluate behind a flag after provider streaming and single-agent operator promotion.
- **Agents SDK:** maintain as the feature-flagged Research Operator candidate behind Gamma's action registry. Promote it only when the clarified trace/eval suite shows a material advantage for sessions, interruptions, guardrails, traces, maintainability, quality, reliability, latency, or cost.
- **Deep research models:** add only as an explicit `External deep research` job with provider/data-retention disclosure, background progress, cancellation, citations, and hard spend/tool limits.
- **Realtime/voice:** defer until the text workspace meets the completion gate.

### Remaining Engineering Workstreams

#### A. Provider transport and run lifecycle — checkpoint 1 complete (76%)

- [x] Replace raw `urllib` with the supported OpenAI SDK typed Responses client while preserving the provider protocol.
- [x] Stream Responses semantic events through one Gamma NDJSON event contract without buffering provider deltas behind the final result.
- [x] Stream completed function-call arguments, tool start/result, refusal, incomplete, provider error, usage, cancellation, and final events.
- [x] Add run ids, monotonic sequence ids, bounded cursor replay, cancellation, timeouts, and idempotent finalization.
- [x] Make shelf Agent, workspace Agent, and custom-loop Operator use the same frontend run-event reducer.
- [x] Persist finalized result plus bounded trace; provisional UI deltas are not durable truth.

Implementation note (2026-07-17, checkpoint complete):
- `OpenAIResponsesCopilotProvider` now uses `openai>=2.38,<3` and `client.responses.create(..., stream=True)`. Typed SDK events are normalized at the provider boundary; no raw `urllib` transport remains. Function arguments, refusal, incomplete, failed/error, text, usage, and tool rounds map into Gamma semantics.
- `CopilotService` owns a bounded 512-event, 15-minute in-memory replay record per active/recent run. POST reconnect uses `last_seen_sequence`; `GET /copilot/runs/{run_id}/events?after_sequence=N` resumes without re-execution. Closing a subscriber does not cancel server work. Duplicate run ids may only reattach to the identical request.
- Agent and custom-loop Operator runs each have one Gamma run id, monotonic sequences, post-terminal event rejection, explicit pre-first-event/safe-boundary cancellation, timeout, and exactly one persisted terminal result. Operator plan, step/tool, warning, confirmation, artifact, report, and final states stream over the shared envelope.
- The shelf now calls the same streaming loader as the dedicated workspace. The client retries a disconnected stream from its last accepted sequence; the reducer drops foreign, stale, duplicate, and post-terminal events. One selected context resolves to its native typed domain; two or more resolve to synthesis.
- Checkpoint evidence: `85 passed` across `tests/test_copilot.py`, Agents SDK smoke, and Operator eval; frontend `41 files / 259 tests` passed; typecheck, build, and desktop check passed. Mock Agent and Operator were inspected at 1440x900 and 720x900 with no console errors. Live-provider release smoke remains intentionally unclaimed.

#### B. Answer contract and evidence UX — checkpoint 2 complete (80%)

- [x] Unify `ResearchCard`, operator result, plan, report, confirmation, mutation diff, artifact, and error rendering around typed transcript block models.
- [x] Restore dedicated-tab parity with the shelf's full card/source/tool/warning rendering.
- [x] Add claim-level evidence resolution and deep links through `CrossTabHandoffEnvelope` where possible.
- [x] Validate every cited source id against the context/tool source registry before persisting a source-backed claim.
- [x] Keep inference, assumption, missing-data, and warning categories visibly distinct in cards and reports. Checkpoint 3 preserves those categories in artifact editing, replay, duplication, reopen, and Markdown export.

Implementation note (2026-07-24, checkpoint complete):
- `frontend/src/lib/copilot-transcript.ts` now maps finalized results and transcript extras into discriminated blocks for messages, cards, plans, Operator steps/results, reports, confirmations, mutation diffs, artifacts, typed non-success states, evidence, and provider metadata.
- `CopilotTranscriptResult.svelte` is the canonical shelf/workspace renderer. It presents source-backed claims, inference, assumptions, missing data, and warnings as distinct states and keeps provider/model metadata in secondary provenance details.
- The backend evidence resolver now runs before service return, before persistence, and when legacy records are read. Unknown refs are removed from source-backed claims and reclassified instead of surviving as citations.
- Supported evidence refs build `CrossTabHandoffEnvelope` navigation and retain mapped entity, mode, timeframe, region, lens, instrument, market, or token context. Unsupported refs remain inspectable without pretending to be navigable.
- Checkpoint evidence: `86 passed` in `tests/test_copilot.py`; `3 passed` across Agents SDK smoke and Operator eval; frontend `42 files / 267 tests` passed; typecheck, production build, and desktop check passed. Live UI inspection covered ready/error/cancelled states and a claim-source handoff to Macro Snapshot preserving the 3M timeframe, with zero console errors.

#### C. Context and tool coverage — checkpoint 5 complete (94%)

- [x] Finish Sealanes context and bounded read-only route/chokepoint drilldowns without inventing congestion, cargo, sanctions, ownership, operational-risk, or vessel-risk labels.
- [x] Make news a first-class external-context drilldown with stable item ids, validated URLs, publication/retrieval/freshness metadata, deterministic deduplication, and cross-feed provenance.
- [x] Add complete, registry-owned IV structure, commodity curve/fundamentals, and equity-research drilldowns through Gamma's authoritative domain services.
- [x] Add typed, versioned contracts, per-scope and aggregate context budgets, deterministic compaction/summaries, omission disclosure, and freshness-based invalidation.
- [x] Add source navigation mappings and canonical context fingerprints for every selectable scope.
- [x] Persist concise selected/omitted-domain reasons and context diagnostics through restart replay without exposing private reasoning or provider payloads.
- [x] Validate every claim reference against the active source registry and represent inspectable-but-nonnavigable sources honestly.

Implementation note (2026-07-25, checkpoint complete):
- Every selectable scope emits `copilot.context.v2` metadata. Fingerprints use canonical domain/entity/mode/timeframe/lens/object/source-version/retrieval inputs; equivalent inputs remain stable while materially changed or stale inputs invalidate. Sensitive keys are redacted.
- Per-scope budgets are explicit and the aggregate synthesis ceiling is 96 KB. Compaction is deterministic, preserves protected facts/source refs/warnings/freshness, and reports summarized or omitted material rather than silently truncating it.
- Maritime context reuses `MaritimeService`; sparse AIS and unavailable historical routes return typed degraded/unavailable results. News keeps normalized item-level provenance across deduplicated reporting sources and rejects unsafe navigation URLs.
- `inspect_options_structure`, `inspect_commodity_curve_fundamentals`, and `inspect_equity_research_context`, plus the maritime and news drilldowns, are bounded read-only registry actions with typed unavailable/degraded states and explicit navigation support.
- NVDA, CPI/Fed, oil-disruption, and portfolio-rate-shock planner/eval cases select the expected domains and retain compact omission reasons. The oil case never fabricates maritime cargo or risk facts, and the portfolio case remains confined to Portfolio/Risk/Macro with no mutation capability.
- Evidence: 209 focused backend tests, the full 461-test backend suite, 315 frontend tests, typecheck, production build, desktop check, and 22/22 deterministic eval outcomes passed. The eval used explicit sample maritime/commodities/news providers and a mock Copilot provider. No new live-provider success is claimed; the earlier OpenAI quota limitation remains external.

#### D. Research Operator productionization — checkpoint 4 complete (91%)

- [x] Stream custom and Agents SDK plan/provider/step/tool/warning/artifact/final progress through the shared run contract.
- [x] Cancel the custom loop between tools and the Agents SDK at its `after_turn` safe boundary.
- [x] Keep one validated server-side registry and permission path for automatic reads, automatic drafts, and confirmed mutations.
- [x] Bind durable confirmations to tool, session, context fingerprint, proposal hash, expiry, and single-use persisted state.
- [x] Render exact DCF proposals, rationale/warnings/source ids, before/after diff, pre-change snapshot policy, and apply/reject controls inline.
- [x] Reconcile apply/reject/expiry into persisted confirmations, mutation refs, embedded events, turn terminal status, and restart replay.
- [x] Cover provider failure, stale context, partial tool failure, budget enforcement, cancellation, forbidden actions, repeated/expired confirmation, and restart resume.

Implementation note (2026-07-25):
- Explicit DCF mutation prompts are intentionally routed through Gamma's deterministic authority path even when Agents SDK orchestration is enabled. The SDK can coordinate bounded read-only actions, but it cannot mint, consume, or bypass a local mutation confirmation.
- `CopilotConfirmationService` atomically consumes a single active token and durably marks expiry. Applying DCF saves a pre-change Fundamentals snapshot and replaying the token fails.
- The Agents SDK branch now uses the maintained `Runner.run_streamed` interface, emits bounded provider-progress events, retains the non-streaming fallback for compatible test doubles, and calls `cancel(mode="after_turn")`.
- The custom loop remains default. The retained custom-versus-offline-SDK benchmark passes both permission/trace paths; no new live quality or latency result justifies changing the default.
- Evidence: 104 backend/eval tests and 309 frontend tests passed with typecheck, production build, and desktop check.
- A bounded authorized live smoke reached the real Agents SDK/Responses transport and emitted `provider.progress`, then terminated through Gamma's typed failure path because the configured OpenAI account was quota exhausted before any tool call. It is not counted as a successful live Operator run.

#### E. Artifacts, memos, and reports — checkpoint 3 complete (86%)

- [x] Bring memo/report creation into the dedicated workspace instead of relying on backend-only endpoints or a separate floating surface.
- [x] Add template choice, source-turn selection, title/body editing, autosave state, explicit overwrite confirmation, duplicate, and delete.
- [x] Add canonical preview and Markdown export; PDF/DOCX remain excluded without a real requirement.
- [x] Preserve claim labels, inline citations, source metadata, warnings, model/provider metadata, context snapshots, and tool-trace summary in exports.
- [x] Link artifacts back to the exact source turns and show artifacts in the selected-session inspector.

#### F. Sessions, retention, and model policy — checkpoint 6 complete (97%)

- [x] Add session rename, archive/restore, delete, schema versioning, migrations, and non-destructive corrupted-record recovery.
- [x] Persist role, depth, requested/resolved provider/model metadata, selected scopes, context fingerprints/snapshots, run status, cancellation, usage, plans, events, confirmations, warnings, sources, traces, and artifacts.
- [x] Create each new conversation as one authoritative empty session and keep selected, inactive, running, and archived states distinct.
- [x] Add visible Settings/run-inspector language explaining Gamma-local storage versus provider-side response storage.
- [x] Support a tested `store: false` path without response-id dependence by reconstructing bounded continuation from Gamma's local structured transcript.
- [x] Put Auto/Quick/Standard/Deep aliases, efforts/modes, routing rules, capabilities, storage behavior, and explicit degradation in the server-owned `copilot.model-policy.v1` contract.

Implementation note (2026-07-25, post-checkpoint regression pass; the checkpoint percentage is unchanged):
- `POST /copilot/sessions` creates one authoritative empty session. Passing an explicit `session_id` is idempotent, so a double activation reattaches instead of creating a duplicate. `New chat` now creates the session before selecting it, which removes the not-found reconciliation that made it silently open an existing conversation.
- The client no longer mints a session id just to read state. An unselected workspace is a real state: with no persisted selection Gamma adopts the newest unarchived session, or shows an honest empty workspace when none exists, instead of surfacing a not-found error.
- `selected`, `inactive`, `running`, and `archived` are independent facts in `frontend/src/lib/copilot-workspace.ts`. Selection is not proof of an active run; switching conversations or starting a new chat does not cancel a server-owned run, the source conversation keeps a running indicator, and the settled turn stays with its own session rather than being appended to the transcript now on screen.
- Composer clearing is driven by run acceptance (`CopilotRunState.accepted`, set on the first acknowledged run event), not by the final status. Quota, provider-error, refusal, incomplete, cancellation, timeout, and zero-tool Operator outcomes all clear the composer because the turn is already persisted; a submission rejected before acceptance preserves the draft, and Retry resends the persisted turn prompt.
- The storage-recovery warning is now an in-flow status strip in the chat column with a `RECOVERY` badge, a plain-language explanation that originals were preserved, an inspectable list of safe record details (record type, recovery action, store-relative path, message), a session-scoped dismiss, and a `Storage` header control for rediscovery. It is statically positioned with no `z-index`, so it cannot cover the composer, artifact controls, or confirmation dialogs at desktop or narrow widths.
- Checkpoint 6 adds schema-v4 fields for selected/resolved profile, provider/model, policy version, product-level routing reason, reasoning mode/effort, orchestration path, total/provider latency, available input/output/reasoning/cache tokens, provider/tool call counts, cancellation outcome/boundary, and safe provider error correlation. Legacy placeholders migrate to `null` when the provider never supplied a value; raw provider usage payloads are discarded.
- `copilot.provider-storage.v1` keeps Gamma-local persistence distinct from provider response retention. When effective storage is disabled, OpenAI requests use `store: false`, omit `previous_response_id`, and include a bounded safe local continuation contract. Providers that cannot honor a requested storage mode return typed degradation.
- The server policy resolves Auto, Quick, Standard, and Deep and records user selection separately from the final resolution. Unsupported provider/model/profile combinations return explicit safe states. The GPT-5.5 Agent baseline and Gamma-owned custom orchestration path remain defaults because the retained comparison showed no authorized live quality, latency, reliability, or cost advantage for switching to Agents SDK. After Checkpoint 7, that custom path is adaptive when the configured provider supports `stream_research_operator`, with deterministic execution retained for mock/disabled fallback fixtures.

#### G. Shelf/full-workspace continuity — checkpoint 6 complete (97%)

- [x] Add `Open in Copilot` from the shelf, preserving the exact source session, turn ids, snapshot ids, context fingerprint/version, selected scopes, role/profile, sources, warnings, freshness, domain decisions, and supported entity/lens/account-or-research-book boundary.
- [x] Keep quick shelf responses concise and card-oriented; plans, traces, diagnostics, confirmations, and artifacts remain in the full workspace.
- [x] Make promotion reference the authoritative persisted turns instead of copying transcript content, with deterministic idempotency and typed `incomplete`, `stale`, `unavailable`, and `already_promoted` states that survive restart replay.

#### H. Diagnostics and first-run experience — diagnostics complete; release polish remains

- [x] Show provider configuration, selected/resolved profile/model, routing result, orchestrator, local/provider storage mode, last provider error, and capability state in Settings and the run inspector.
- [x] Surface structured provider errors with category-specific retry/configuration guidance and a copyable `cp6.<category>.<hash>` diagnostic id; never leak credentials, stack traces, authorization values, raw prompts, or provider payloads.
- [x] Record and replay available latency, input/output/reasoning tokens, cache reads/writes, provider calls, tool calls, and cancellation outcome/boundary without inventing missing values.
- Add first-run guidance for disabled, unconfigured, unavailable, rate-limited, and quota-exhausted states.

Implementation note (2026-07-25, checkpoint 6 complete):
- The supported deterministic CLI scored grounding, citation validity, domain selection/omission, warning preservation, tool selection, permission stops, trace completeness, and final usefulness. It passed 31/31 outcomes across 11 retained cases: Auto/custom covered all 11, while Quick/custom, Standard/custom, Deep/custom, and Standard/Agents-SDK-stub each covered the four Checkpoint 5 representative prompts plus the DCF permission stop. Average score was 0.9093.
- The eval records wall/provider latency and returned usage when present, labels all executed variants `deterministic_mock`, and emits an explicit routing decision. No live-provider flag or spend was authorized, so no live pass is claimed and no default changed.
- Verification: 125/125 focused Copilot/Agents/eval tests; 50/50 affected API/provider/capability/usage tests; 468/468 full backend tests; 320/320 frontend tests across 46 files; typecheck, production build, and desktop check.
- Final release evidence still requires full first-run/accessibility/focus/reduced-motion/narrow-layout certification and representative successful live Agent and Operator smoke when provider access, quota, and spend are intentionally authorized. This gate now follows the clarified Operator workstreams.

#### I. Closed-loop Research Operator — checkpoint 7 complete (82%)

- [x] Replace the fixed capable-provider Operator sequence with a bounded model-tool-model loop that observes each result before selecting the next step.
- [x] Make request-to-schema translation model-assisted and validated: preserve the user's entities, portfolio legs, weights, scenario shocks, DCF assumptions, dates, horizons, and comparison targets instead of substituting unrelated fixed defaults.
- [x] Return successful tool observations to the final synthesis step and require the final answer to address the user's goal; a generic count of completed steps is not a successful result.
- [x] Define explicit stopping conditions for final answer, insufficient evidence, user cancellation, elapsed/tool/provider/request-limit budget exhaustion, refusal, incomplete output, and typed provider failure. Approval interruption remains generalized Checkpoint 9 work because Checkpoint 7 adds no new durable mutation family.
- [x] Keep deterministic workflows as tools, fallbacks, and test fixtures; do not confuse a prewritten sequence with the capable-provider Operator harness.

Implementation note (2026-07-30, checkpoint complete):

- `OpenAIResponsesCopilotProvider.stream_research_operator` now owns the repeated Responses model turns while Gamma owns tool exposure, re-authorization, strict server validation, execution, observation construction, budgets, cancellation, events, persistence, and the final typed terminal. The custom path sends the complete bounded tool observation back as `function_call_output` and accepts a schema-valid final `ResearchCard` only after required evidence exists.
- `ResearchActionRegistry.validate_arguments` enforces the bounded JSON-schema subset used by Gamma actions: required fields, exact objects, nested types, arrays, enums, numeric limits, and patterns. It does not fill hidden defaults or coerce strings into numbers. Malformed model JSON is preserved as a deterministic validation failure, including for otherwise-empty action schemas.
- The Agents SDK path now exposes one maintained `FunctionTool` per authorized action using the action's exact strict schema, returns bounded complete observations to the agent, parses typed `final_output` into the shared `ResearchCard`, and enforces tool, per-action request, external-provider, elapsed, and model-turn limits. The old generic `(tool_id, arguments_json)` wrapper remains only for injected legacy test doubles.
- Both variants write `copilot.operator.loop.v1` final events with a typed `stop_reason`, `synthesis_source`, observation-linked output summaries, retained bounded outputs, and budget counters. A ready workflow with planned tools but no validated observation, or without a schema-valid model final card, is downgraded to a typed non-success.
- Retained tests cover exact `+75 bps`, `-12%`, and `7.5 year` scenario arguments; schema rejection and model correction; observation-driven continuation; unapproved-action blocking; tool-budget exhaustion; provider failure; cancellation; and model-final persistence/replay. The eval gate rejects generic tool-count cards for closed-loop traces.
- Verification: 31 focused Operator tests, 8 focused Checkpoint 7 contract tests, 2 Agents SDK smoke tests, the full 542-test backend suite, 368 frontend tests across 50 files, TypeScript typecheck, and the production frontend build passed. The installed `openai 2.38.0` / `agents 0.17.4` contract was exercised without dependency changes.
- Authorized live smoke reached the real Responses transport on 2026-07-30 with provider storage disabled. The provider returned a streamed quota exhaustion before any tool call; Gamma persisted a safe `quota_exhausted`/`provider_error` `copilot.operator.loop.v1` terminal with zero tools and no fallback card. This validates the live error boundary, not a successful live model-tool-model result.

#### J. Entity-addressable tools and working-analysis state — in progress (Checkpoints 8A-8C complete)

- [x] Prove unloaded entity acquisition with `LMT` reverse valuation: the planned ticker hydrates Fundamentals context and remains the authoritative tool argument without requiring the tab to be preloaded.
- [x] Add `copilot.working-analysis.v1` as Gamma-owned session-scoped state for Fundamentals reverse-valuation outputs, including entity, inputs, complete bounded output, provenance, context fingerprint, read-only safety, expiry, restart replay, discard, and recoverable session deletion.
- [x] Distinguish this slice as `session_ephemeral`, expose `TEMPORARY` state in the run inspector and Fundamentals, and record that typed materialization is non-durable with explicit confirmation required for any later saved-DCF change.
- [x] Materialize the active result into Fundamentals / Reverse Valuation through a server-recorded typed target plus normal app navigation; UI clicking remains non-authoritative and no DCF draft is silently written.
- [x] Add the Checkpoint 8B public-company identity preflight: natural names may be proposed by the configured model, but Gamma validates them against SEC reference data, injects only a unique canonical ticker, records resolution provenance/usage, and stops with typed candidates on issuer or share-class ambiguity.
- [x] Generalize the same contract to user-specified hypothetical portfolios and Risk, preserving exact legs, normalized weights, typed shocks, complete bounded outputs, provenance, restart/discard/expiry, and typed non-durable Risk materialization.
- [ ] Continue the contract through Options sets, Strategy Lab inputs, temporary assumptions, and other cross-tool outputs.
- [ ] Integrate the separately tracked Research Script Workspace only after its mock contracts, immutable revision store, and Script-mode materialization payload are stable; do not fold arbitrary source execution into `run_strategy_lab_backtest`.
- [ ] Add explicit promotion/persist workflows where product requirements call for them; expiration and discard are implemented for the first slice, while durable promotion remains confirmation-owned future work.

Implementation note (2026-08-25, Checkpoint 8A):

- The Operator decorates successful `run_fundamentals_reverse_valuation` observations in deterministic, custom Responses, and Agents SDK paths with the same stored working-analysis reference. Analysis ids are run/entity/tool-derived, and records live under the Copilot store without changing the store schema version or saved Fundamentals state.
- The session detail and dedicated lifecycle routes list, inspect, materialize, and discard working analyses. Active records expire after seven days, materialization is idempotent, discarded/expired records cannot be reopened, and session deletion moves them into recoverable local trash with the rest of the session.
- The run inspector uses the existing compact inspector plane to show temporary status, owning surface, expiry, open, and discard actions. Fundamentals reuses the existing Reverse Valuation mode and displays a temporary-state banner; it loads the named ticker through the normal provider-backed service path and never populates or saves the editable DCF draft.
- Retained acceptance coverage starts from an unprepared Copilot session, asks for `LMT`, verifies the strict `ticker=LMT` tool call and complete stored output, reopens the exact record through a restarted store, materializes it, discards it, rejects reopening, and verifies recoverable session cleanup. A separate expiry test and frontend typed-target tests cover invalid lifecycle/target states.
- Verification on 2026-08-25: the two focused Checkpoint 8 backend tests, all 372 frontend tests, TypeScript typecheck, and the production frontend build passed. The broader backend run reached 537 passes with seven unrelated current-clock/data-fixture failures (six expired August commodities-contract cases and one SITREP NaN serialization case). A live `store=false` Responses transport smoke succeeded with the configured `gpt-5.5-2026-04-23` model; this was a provider-boundary check, not a live model-tool-model acceptance run.
- The in-app browser visual pass was unavailable because the local browser-control kernel could not install its assets. Targeted run-inspector and Fundamentals component tests were added and passed, but a later browser screenshot pass should still verify the final rendered density and interaction states.

Implementation note (2026-08-25, Checkpoint 8B):

- Operator execution now runs entity preflight before plan/context construction. The configured Responses provider can return one strict `copilot.entity-resolution.v1` proposal containing the natural-language mention, likely ticker, legal issuer name, exchange, confidence, and reason. Gamma then searches its SEC-backed Fundamentals company reference and creates typed resolved, ambiguous, or not-found state; the model output alone can never authorize a ticker.
- Unique resolution replaces only the request's ephemeral `fundamentals_ticker`, so existing Fundamentals, Equity Research, IV, and reverse-valuation plan/tool contracts continue to receive canonical symbols without requiring tab preload. Explicit tickers bypass the proposal, and the shared acronym filter prevents finance terms such as `DCF`, `WACC`, `SEC`, and `EBITDA` from becoming ticker entities.
- Plan previews remain deterministic and free of model cost. Execution records proposal-provider usage in the ordinary run usage record. Resolved provenance and ambiguous candidates render inline in the existing Copilot plan plane; no tab or secondary surface was added.
- Issuers with multiple listed share classes remain unresolved until the user names a ticker. The server returns an `incomplete` terminal, a `confirmation-needed` event, a zero-tool `entity_disambiguation` plan, and authoritative candidates instead of allowing the model to choose silently.
- Verification on 2026-08-25: all 138 Copilot backend tests and all 373 frontend tests passed, along with TypeScript typecheck and the production frontend build. The repository-wide backend run reached 542 passes with the same seven unrelated date/data failures recorded for this worktree (six August futures-expiry commodity fixtures and one SITREP NaN serialization case). Focused coverage includes strict proposal schema/storage policy, model-proposed `Apple` → SEC-validated `AAPL`, deterministic no-model plan resolution, persisted resolution provenance, `Alphabet` share-class ambiguity, and explicit-ticker/acronym handling. A bounded live `store=false` proposal smoke returned `AAPL` / `Apple Inc.` from the configured `gpt-5.5-2026-04-23` model in one provider call; Gamma's separate SEC validation remained the authority-bearing step.

Implementation note (2026-08-25, Checkpoint 8C):

- `run_risk_contribution_analysis` and `run_risk_scenario_analysis` now accept a strict nullable `temporary_portfolio` input in addition to a loaded portfolio/research snapshot. An unprepared request can therefore preserve its named legs and weights, build the fixed-notional read-only snapshot inside Gamma, and run the existing Risk engine without loading or mutating the Portfolio or Research tabs.
- The representative two-tool portfolio-plus-scenario plan has a dedicated 60-second elapsed guard. This remains bounded, but leaves room for two app-native analytics and the required observation-driven model turns instead of inheriting the generic 12-second single-surface guard.
- Hypothetical comparison and subsequent Risk observations share a run/portfolio-derived analysis id. Gamma merges `portfolio_comparison`, `risk_scenario` or `risk_contribution`, exact normalized inputs, source ids, warnings, and provenance into one session-ephemeral record. Provider retries cannot resurrect discarded/expired state, and the same seven-day restart/discard/expiry policy remains in force.
- The existing Risk tab owns materialization through `copilot.risk-working-analysis.v1` in Overview or Scenarios mode. Its compact `TEMPORARY` module shows the portfolio definition, typed shocks, estimated proxy impact, warnings, and provenance without populating a saved portfolio, changing the live account snapshot, or exposing save/rebalance/order controls.
- The retained unprepared-session acceptance asks for `60% AAPL / 40% TLT`, `+100 bps`, and `-10% equity`; it verifies both exact tool calls, one merged working record, restart replay, typed Risk materialization, discard/reopen rejection, and an unchanged portfolio snapshot. Verification on 2026-08-25: all 139 Copilot backend tests and all 375 frontend tests passed, along with TypeScript typecheck and the production frontend build. The repository-wide backend run reached 544 passes with the same seven unrelated current-clock/data failures recorded before 8C (six expired August futures fixtures and one SITREP NaN serialization case). The build retained pre-existing IV/Surface3D warnings unrelated to this checkpoint.
- A bounded live `store=false` custom-Responses smoke with the configured `gpt-5.5-2026-04-23` model selected both intended tools and preserved `AAPL=0.6`, `TLT=0.4`, `+100 bps`, and `-10%` exactly. The default 12-second guard stopped before the second observation, which led to the intent-specific 60-second guard above. A test-only 90-second rerun executed the Risk scenario and created the correct temporary Risk / Scenarios record, but Yahoo history rate limits degraded the comparison and the final Responses continuation returned HTTP 400. This is useful live argument/state evidence, not a successful end-to-end live acceptance claim.

#### K. Generalized interruptions, recovery, and role transition — open

- Generalize the DCF proposal pattern into pause/approve-or-reject/resume-the-same-run for every future durable local research-state mutation.
- Persist the unfinished run snapshot, plan cursor, observations, budgets, working-state ids, context fingerprint, pending tool call, and approval decision.
- Add bounded tool retry, replan, resume-after-restart, and stale-context behavior without replaying already committed side effects.
- Make Agent-to-Operator escalation visible and intentional. The original Agent run may propose the workflow, but it cannot execute until Operator authority is selected.
- Keep all execution-capable families structurally absent from both roles.

#### L. End-state validation and release gate — blocker

- Backend: provider event parsing, structured output/refusal/incomplete handling, closed-loop continuation, cancellation, working-state persistence/replay, migrations, permission/confirmation invariants, and model-policy tests.
- Frontend: streamed reducer, transcript blocks, source navigation, app materialization, temporary-versus-durable state, artifact editing, error states, Stop/Retry, responsive inspector, keyboard navigation, and accessibility tests.
- Evals: entity acquisition, argument fidelity, plan quality, tool selection, adaptation after observations, stopping behavior, grounded synthesis, citation validity, warning preservation, approval interruptions, resume behavior, final usefulness, and cost/latency capture.
- Representative acceptance cases: unloaded `LMT` fair value; a user-specified hypothetical multi-asset portfolio; a specified portfolio risk shock; an options realized/implied comparison; and one cross-domain workflow requiring replanning after a degraded tool result.
- Live smoke: Agent and Operator paths for representative single-name, CPI/Fed, oil, portfolio-risk, and approval-resume prompts against intentionally configured providers.
- Regression: shelf and dedicated-tab parity, session/run reopen after restart, offline/mock behavior, disabled-provider behavior, and no execution-capable tools.

### Delivery Order

1. ~~Provider-native streaming, shared run lifecycle, bounded replay, and explicit provider state.~~ Completed 2026-07-17 at checkpoint 1 (76%).
2. ~~Typed transcript blocks, validated claim/source resolution, and dedicated-tab evidence parity.~~ Completed 2026-07-24 at checkpoint 2 (80%).
3. ~~In-tab artifacts/memos and session lifecycle completion.~~ Completed 2026-07-25 at checkpoint 3 (86%).
4. ~~Fix the focused New Chat, composer-clear, and storage-warning presentation regressions recorded in `docs/copilot_v2_checkpoint3_prompt.md`.~~ Completed 2026-07-25 (see the note under workstream F).
5. ~~Live operator events, cancellation, and inline confirmations.~~ Completed 2026-07-25 at checkpoint 4 (91%).
6. ~~Missing context/tool coverage and source navigation.~~ Completed 2026-07-25 at checkpoint 5 (94%).
7. ~~Versioned, capability-aware model/storage policy and eval-backed routing decision.~~ Completed 2026-07-25 at checkpoint 6 (97%); retain GPT-5.5/custom Operator defaults because no authorized live evidence justified a switch.
8. ~~Agents SDK checkpoint-4 default decision.~~ Keep the custom loop as default until a later live comparison demonstrates a measured advantage.
9. ~~Safe provider/model/storage diagnostics and replayable observability.~~ Completed 2026-07-25 at checkpoint 6. First-run guidance, accessibility, responsive/live UI certification, and the full release gate remain after the clarified Operator outcome checkpoints.
10. ~~Build the closed-loop Operator and model-assisted, schema-validated argument path.~~ Completed 2026-07-30 at Checkpoint 7 (82%).
11. Add entity-addressable tools plus generalized session-scoped working-analysis state and app materialization. In progress: unloaded-company Fundamentals and hypothetical portfolio/Risk vertical slices are complete through Checkpoint 8C; Options, Strategy Lab, and the remaining owning surfaces are next.
12. Generalize approval interruption, same-run resume, recovery/replanning, and visible Agent-to-Operator transition.
13. Pass trace-level deterministic and live acceptance cases against the clarified completion boundary.
14. Optional external deep research; later voice.

Do not start with model-string replacement alone. Any future candidate-model rollout must use the Checkpoint 6 policy and land with provider streaming, capability validation, usage instrumentation, and recorded eval/live evidence so it improves the product rather than merely changing metadata.

The percentages attached to completed Checkpoints 1 through 7 below are historical gates under earlier completion boundaries. They document verified foundation work but do not override the current **approximately 85%** end-state baseline through Checkpoint 8C.

### Definition Of Done

- Provider-native deltas reach the UI before completion; the fake typewriter path is removed.
- Every completed live turn ends in one schema-valid final block or a typed non-success state.
- All source-backed claims resolve to known source ids; unsupported claims are inference or missing data.
- All operator tools pass the server action registry; forbidden market/account/wallet/host-code actions do not exist in the registry. The separately approved Script actions are limited to their isolated runtime and exact-source/input contracts.
- An Operator request can acquire an unloaded supported entity, create explicit ephemeral working state, run tools, observe results, adapt, and synthesize the requested conclusion.
- User-specified analytical parameters survive intent translation into strict tool schemas or fail visibly; hidden unrelated defaults do not count as success.
- Tool observations feed the same run's next decision and final answer; generic execution summaries do not satisfy analytical requests.
- Temporary work can materialize in the owning Gamma surface without becoming durable user state.
- Confirmation-required actions cannot apply without the exact active token and visible diff; approve/reject resumes the same unfinished run.
- Session replay after app restart reproduces the final transcript, trace, artifacts, context metadata, working-state references, observations, budgets, and pending interruption.
- The dedicated tab supports full memo/report editing and export.
- The shelf can promote a thread into the tab without context loss.
- Model/profile/orchestrator routing is replayable and backed by recorded eval results against the retained GPT-5.5/custom-loop baseline; no default changes without measured evidence.
- Trace evals and live/frontend/backend suites cover entity acquisition, parameter fidelity, adaptation, stopping behavior, synthesis, approval/resume, and happy, degraded, unavailable, refused, incomplete, cancelled, and provider-error paths.
- When Workstream 2A is present, Script evals additionally prove role separation, explicit-run intent, staged Operator revisions, immutable source/input hashes, output retention, and the absence of Gamma/host/credential/broker/wallet/network authority.

## Smart Depth Policy

The agent must not run every domain for every request. It should adapt the plan to the request.

Example depth behavior:

| Request | Expected depth |
|---|---|
| "Research NVDA" | Deep Fundamentals and Equity Research, medium Options/news/estimates, light Macro unless relevant. |
| "Research NVDA into CPI/Fed week" | Medium Fundamentals, deep Macro/Rates and Options event risk, recent news/context. |
| "What is going on in oil?" | Deep Commodities and relevant Sealanes, Macro, Prediction Markets, and news context; explicit degradation when AIS, curves, inventories, routes, or feeds are unavailable; no DCF or invented maritime risk. |
| "Is my portfolio exposed to rate shock?" | Deep Portfolio/Risk/Macro within the selected account or research-book boundary; no rebalance, trade, order, or company memo unless separately requested. |
| "Stress my AI basket if front-end rates rise 100 bps" | Deep Strategy Lab/Research/Risk/Macro; light Fundamentals/Options only for major constituents if requested. |

Depth profiles:

- `quick`: answer from current context plus at most a small number of cheap tools.
- `standard`: run the most relevant domains and save a session trace.
- `deep`: broader cross-domain pass, outside context, explicit missing-data list, and report-ready synthesis.
- `user_directed`: user names domains or analyses; planner respects those unless impossible or unsafe.

The planner should produce a structured plan before execution for non-trivial requests:

```json
{
  "intent": "single_company_research",
  "target_entities": [{"kind": "ticker", "id": "NVDA"}],
  "depth_profile": "standard",
  "domain_plan": [
    {"domain": "fundamentals", "depth": "deep", "reason": "single-company valuation request"},
    {"domain": "options", "depth": "medium", "reason": "earnings/event risk may matter"},
    {"domain": "macro", "depth": "light", "reason": "background context only"}
  ],
  "requires_confirmation": false,
  "expected_artifacts": ["session_trace", "research_memo"]
}
```

## Action Taxonomy

All tools should be classified by action type.

### 1. Read Context

Loads already available Gamma state or fetches a domain workspace payload.

Examples:

- `portfolio.get_snapshot`
- `research.get_scope_context`
- `fundamentals.get_company_context`
- `macro.get_workspace_context`
- `commodities.get_workspace_context`
- `options.get_surface_context`

Default permission: automatic.

### 2. Run Analysis

Runs deterministic Gamma analytics from typed inputs.

Examples:

- `risk.run_var`
- `risk.run_contribution`
- `risk.run_scenario`
- `research.run_scope_analysis`
- `options.compare_realized_implied`
- `fundamentals.run_reverse_valuation`
- `commodities.inspect_curve_spreads`
- `prediction_markets.compare_related_contracts`
- `strategy_lab.run_research_script` only under the separate isolated Script Workspace contract and an explicit current-turn run request

Default permission: automatic if read-only and bounded by request limits.

### 3. Fetch External Context

Uses approved read-only providers for current context.

Examples:

- `news.fetch_recent_company_news`
- `news.fetch_macro_context`
- `estimates.fetch_consensus_snapshot`
- `transcripts.fetch_recent_earnings_transcript`
- `filings.fetch_latest_company_filing`

Default permission: automatic for configured providers if no sensitive credentials are exposed to the model. Must include provenance and freshness. General web search should be a fallback or explicit user-directed mode, not the default durable provider strategy.

### 4. Draft Change

Produces a proposed local research-state mutation without applying it.

Examples:

- `fundamentals.propose_dcf_update`
- `research.propose_saved_scope`
- `strategy_lab.propose_composition`
- `strategy_lab.draft_research_script`
- `copilot.propose_memo_edit`

Default permission: automatic. Must return a diff, rationale, expected impact, warnings, and rollback/snapshot path if applicable.

### 5. Apply Change

Applies a local research-state mutation after user confirmation.

Examples:

- `fundamentals.apply_dcf_update`
- `fundamentals.save_dcf_snapshot`
- `research.save_scope`
- `copilot.create_memo`
- `copilot.update_memo`

Default permission: confirmation required unless the user explicitly requested an unambiguous save-only action.

Confirmation policy can become more permissive later after trust is earned through usage, but the initial Research Operator posture should stay conservative:

- automatic for read-only context loading, bounded analytics, simulations, and draft diffs;
- automatic for passive session traces;
- confirmation-required for durable local research-state changes such as DCF edits, saved strategy objects, saved scopes, memo overwrites, watchlists, or model snapshots unless the current user turn explicitly requested the exact save/export action;
- never allowed for market execution, account modification, wallet signing, wallet transactions, rebalancing, local/host code execution, or code execution outside the approved isolated Research Script Workspace.

### 6. Save Artifact

Persists research output.

Examples:

- `copilot.save_session`
- `copilot.create_memo`
- `copilot.export_report_markdown`
- `fundamentals.save_dcf_snapshot`
- `research.save_research_object`

Default permission: confirmation usually not required for passive session trace; required for overwrites or model changes.

### 7. Navigate UI

Opens a relevant tab/mode/lens for user inspection.

Examples:

- `ui.open_fundamentals_dcf`
- `ui.open_risk_scenarios`
- `ui.open_macro_rates_policy`

Default permission: automatic if non-destructive. This is a convenience layer, not the analytical execution layer.

## Tool Registry Requirements

Every agent tool should have:

- stable `tool_id`;
- domain;
- action type;
- read-only flag;
- mutation flag;
- confirmation policy;
- input schema;
- output schema;
- provenance behavior;
- timeout/retry policy;
- request-limit policy;
- whether it can call external providers;
- expected warnings/failure modes;
- test coverage owner.

Example shape:

```python
@dataclass(frozen=True)
class ResearchActionDefinition:
    tool_id: str
    domain: str
    action_type: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    read_only: bool = True
    mutates_local_state: bool = False
    requires_confirmation: bool = False
    external_provider: str | None = None
    timeout_seconds: float = 30.0
```

## Domain Coverage Target

Initial target domains and likely tools:

### Portfolio

- snapshot summary
- exposure/concentration summary
- performance/local-history context
- handoff into Risk

### Equity Research

- build single-name scope
- build synthetic scope
- run scope analysis
- compare scope vs benchmark
- save/reload research object

### Strategy Lab

- inspect imported return stream
- compose Gamma objects
- run backtest/analyze
- run regime/stress lens
- save run
- draft a session-ephemeral research script through the strict Workstream 2A action
- explicitly run an immutable Script revision in the isolated runtime and return typed outputs
- stage Operator code revisions without overwriting the user-controlled canonical source

### Risk

- run VaR/CVaR
- run contribution analysis
- run beta/correlation
- run scenario stress
- summarize coverage gaps

### Options / IV

- load IV surface
- inspect skew and term structure
- compare realized vs implied
- inspect session status and data-quality warnings
- summarize event/volatility risk

### Fundamentals

- search/select company
- load overview
- load financials
- load peers
- load filings/reference context
- run reverse valuation
- load DCF
- propose DCF change
- apply DCF change after confirmation
- save DCF snapshot

### Macro

- load snapshot
- load cross-asset divergences
- load rates/policy context
- load events/regimes
- load trade/country context
- identify relevant macro context for a non-macro query

### Commodities

- load workspace
- inspect selected curve
- inspect spreads
- inspect inventories/fundamentals
- inspect events/cross-domain notes

### Prediction Markets

- screen markets by topic
- load market detail/history
- inspect flow/wallet context
- inspect related markets
- inspect calibration

### Crypto

- screen token universe
- load token detail
- load price/liquidity/flow summary
- compare token to basket
- inspect narrative/sector context

### External Context

- recent news
- analyst estimates
- earnings transcript snippets
- SEC/company filing deltas
- official macro/event calendars

External context must be strictly read-only and provenance-rich.

## Confirmation Policy

Confirmation is required when:

- a tool mutates local research state beyond passive session logging;
- a tool overwrites an existing saved object;
- a tool changes DCF assumptions, peers, saved strategy objects, memos, or watchlists;
- a tool creates a report intended as a durable artifact and the user did not explicitly ask to save/export;
- the action is ambiguous or the planner cannot identify the target entity confidently.

Confirmation can be skipped when:

- reading data;
- running bounded analytics;
- creating an ephemeral session trace;
- generating a draft;
- saving a memo/report that the user explicitly requested in the current turn and no overwrite is involved.

For DCF/state edits, always return:

- current value;
- proposed value;
- rationale;
- downstream valuation impact if available;
- source ids used;
- warnings;
- snapshot/rollback plan.

## Persistence And Reports

The final harness should persist:

- session id;
- user prompt;
- normalized research plan;
- tool call trace;
- tool outputs or compact summaries;
- source refs and warnings;
- context snapshots;
- generated synthesis;
- saved artifacts;
- user confirmations;
- final report or memo.

Reports should separate:

- source-backed claims;
- model-inferred claims;
- assumptions;
- missing data;
- warnings/caveats;
- tool trace summary;
- saved Gamma artifacts such as DCF snapshots or saved scopes.

## Architecture Recommendation

Short term:

- Extend the current `CopilotService` tool registry and provider wrapper.
- Add a structured planner output before tool execution.
- Keep using the current Responses API provider if the orchestration remains simple.

Medium term:

- Introduce a `ResearchActionRegistry` separate from `CopilotService`.
- Move domain tool definitions closer to their domain services while exposing a shared registry interface.
- Add confirmation tokens and durable action traces.
- Add external context provider adapters.

Long term:

- Migrate orchestration to the OpenAI Agents SDK when the workflow needs specialists, handoffs, guardrails, tracing, resumable state, or richer eval loops.
- Keep Gamma's own tool execution and permission checks server-side.
- Treat the model as planner/orchestrator, not as the authority on whether an action is allowed.

## Suggested Backend Modules

Potential module split:

```text
src/models/research_actions.py
src/application/research_action_registry.py
src/application/copilot_planner.py
src/application/copilot_orchestrator.py
src/application/copilot_confirmation_service.py
src/application/copilot_report_service.py
src/services/news_adapters.py
src/services/estimate_adapters.py
```

Do not introduce all of these at once. Add them when the current `CopilotService` starts becoming too large or when tests need clearer seams.

## Progression Path

Future agents should update this checklist in place.

### Phase 0 - Documentation And Boundary

- [x] Create living agentic harness spec.
- [x] Reconcile this document with `roadmap.md` if the roadmap changes.
- [x] Add current GPT-5.6, streaming, structured output, caching, Multi-agent, and deep-research references.

### Phase 1 - Planner-Only Prototype

- [x] Add structured research-plan schema.
- [x] Add planner route or planner mode that returns intent, entities, depth profile, domain plan, and expected artifacts.
- [x] Add tests for representative prompts:
  - "Research NVDA"
  - "Research NVDA into CPI/Fed week"
  - "What is going on in oil?"
  - "Is my portfolio exposed to rate shock?"
- [x] Show plan preview in Copilot workspace for non-trivial requests.

### Phase 2 - Read-Only Multi-Domain Execution

- [x] Convert current Copilot drilldown tools into action-registry entries or a compatible adapter.
- [x] Add bounded read-only execution against the selected plan.
- [x] Add tool traces to persisted sessions.
- [x] Add source/warning aggregation across domains.
- [x] Add tests for planner-to-tool execution.

Implementation note:
- First-pass execution lives at `/copilot/research-plan/execute`. It reuses the deterministic planner, executes only registered read-only Gamma tools, bounds execution to a small number of domains/tools, skips missing loaded contexts and unavailable external-provider work with explicit warnings, aggregates sources/tool traces, and persists the execution as a Copilot session turn.

### Phase 3 - Smart Depth And Budgeting

- [x] Implement `quick`, `standard`, `deep`, and `user_directed` profiles.
- [x] Add per-domain cost/latency estimates.
- [x] Add max tool-call, max provider-call, and max elapsed-time guards.
- [x] Add "why this domain was/was not used" output.

Implementation note:
- Phase 3 keeps the deterministic planner/executor path and adds profile-level execution budgets, per-domain tool/provider/latency estimates, explicit selected/omitted domain decisions, and bounded executor guards for max domains, tool calls, provider calls, and elapsed time. The Copilot workspace plan preview now surfaces the budget envelope and domain-use rationale. Representative tests cover quick, standard, user-directed, planner-budget metadata, domain decisions, and quick executor bounds.

### Phase 4 - External Context Providers

- [x] Harden news provider boundary for company, macro, commodity, and event context.
- [x] Add analyst estimate provider boundary if a viable provider is selected.
- [x] Add transcript/filing delta context if needed.
- [x] Add provenance and freshness labels for all external context.
- [x] Add fallback behavior when providers are missing or stale.

Implementation note:
- Phase 4 now executes through the same bounded planner/executor path as the read-only Gamma tools. `external_context` is a real Copilot context domain with `get_external_context_summary`, backed by the existing normalized `NewsService` provider boundary. It classifies company, macro, commodity, and event prompts into a compact external-context profile, fetches only approved read-only news/event provider data, filters relevant items, emits source refs for the feed and individual items, and returns freshness labels on the feed and every item. Analyst estimates, transcripts, and filing deltas are represented as explicit unavailable provider boundaries until a viable adapter is selected; company filing chronology should continue to come from the SEC-backed Fundamentals context rather than invented external deltas. Missing, failing, unavailable, and stale providers return warnings and unavailable/stale freshness labels instead of confident claims. Tests cover the tool boundary and planner execution path.

### Phase 5 - Research Reports

- [x] Add report schema and templates.
- [x] Generate reports from session traces and selected artifacts.
- [x] Export memo/report as Markdown.
- [x] Include source-backed claims, inferred claims, assumptions, missing data, warnings, and tool trace summary.
- [x] Add report snapshot tests.

Implementation note:
- Phase 5 now has a deterministic report layer over persisted Copilot session traces. `CopilotResearchReport` and `CopilotReportToolTraceSummary` define the typed report contract, `CopilotReportService` compiles selected turns and memo artifacts into source-backed claims, inferred claims, assumptions, missing-data warnings, source refs, and tool traces, and `/copilot/sessions/{session_id}/report` plus `/copilot/sessions/{session_id}/report/export` expose JSON and Markdown outputs. Memo Markdown export remains supported through the existing memo route. Tests cover report generation and Markdown snapshot sections.

### Phase 6 - Confirmed Local Research-State Mutations

- [x] Add draft mutation schema and diff renderer.
- [x] Add confirmation token flow.
- [x] Add `fundamentals.propose_dcf_update`.
- [x] Add `fundamentals.apply_dcf_update` after confirmation.
- [x] Save DCF snapshot before or after confirmed edits according to UX decision.
- [x] Add similar confirmed flows only where there is clear product value.

Implementation note:
- Phase 6 now has a narrow confirmed-mutation backend path for local Fundamentals DCF research state. `/copilot/mutations/fundamentals/dcf/propose` accepts explicit typed DCF assumption / override updates, returns a persisted draft mutation with structured diff entries, rendered diff text, warnings, and a confirmation token, and does not change the DCF model. `/copilot/mutations/{mutation_id}/apply` requires the matching confirmation token, saves a pre-change DCF snapshot as rollback context, applies the DCF payload through the existing Fundamentals service, and records the mutation as applied. The Copilot action registry now distinguishes `draft_change` from `apply_change`, with only the apply action marked as local-state mutating and confirmation-required. No other confirmed mutation families were added because DCF is the only current high-value, well-bounded research-state edit target in this phase.

### Phase 7 - Agents SDK Operator Orchestration

- [x] Decide whether to adopt Agents SDK for the Research Operator path.
- [x] Prototype Agents SDK orchestration behind the existing Gamma action registry.
- [x] Preserve existing Gamma permission checks and local persistence.
- [x] Add traces/evals for tool selection quality.

Implementation direction:

- The user has approved adopting Agents SDK for the Research Operator path. Treat Phase 7 as a controlled migration, not an open-ended rewrite.
- Keep the Research Agent path working on the current planner/executor/report foundation while the operator path is prototyped.
- Build the Agents SDK operator behind the same Gamma action registry shape used by the current executor. Agents SDK may plan, coordinate, trace, and hand off, but it must not bypass Gamma's server-side permission checks, confirmation tokens, or persistence.
- Compare the hybrid prototype against the current custom loop on concrete operator tasks: DCF edit proposal/apply, reverse valuation plus report, risk shock analysis, hypothetical portfolio comparison, Strategy Lab backtest, and cross-domain single-name event report.
- Promote Agents SDK into the default Research Operator orchestrator after the prototype preserves existing behavior and materially improves progress streaming, trace quality, resumable state, handoffs, eval coverage, or maintainability as tools grow.

Research Operator build path:

1. Define operator-grade action contracts.
   - Move tool metadata toward a standalone `ResearchActionRegistry`.
   - Require every operator tool to declare action type, permission policy, input/output schema, provenance behavior, timeout, retry safety, and mutation behavior.
   - Keep domain services as the execution authority.

2. Add operator plans.
   - Extend the planner so it can output an ordered test plan, not just domain relevance.
   - Include intended artifacts, confirmation checkpoints, expected runtime/cost, and what would cause the plan to stop early.
   - Show the plan to the user before long or state-changing runs.

3. Expand read-only operator tools first.
   - Prioritize `risk.run_scenario`, `risk.run_contribution`, `fundamentals.run_reverse_valuation`, `strategy_lab.run_backtest`, `research.run_scope_analysis`, options event/volatility comparisons, and portfolio/hypothetical comparison tools.
   - These should run automatically when bounded and relevant because they do not mutate durable state.

4. Expand draft-and-confirm mutation tools second.
   - Generalize the DCF mutation pattern to other high-value local research state only after the read-only operator path is reliable.
   - Candidate families: saved research scopes, Strategy Lab compositions, memo edits, watchlists, scenario/model snapshots, and hypothetical portfolio definitions.
   - Every mutation must return a diff, rationale, warnings, source ids, and rollback/snapshot context where applicable.

5. Add progress, trace, and report surfaces.
   - [x] Emit plan, step-start, tool-result, warning, confirmation-needed, artifact-created, and final-report events.
   - [x] Persist the full operator run as a session trace.
   - Generate reports that distinguish source-backed claims, inferred claims, assumptions, missing data, warnings, and exact tool calls.

Implementation note:
- Operator progress events ride on `/copilot/operator-plan/execute` results as `operator_events` and are persisted with Copilot turns. The backend remains authoritative for execution state; the Copilot workspace renders the trace for inspection only. Checkpoint 7 adds observation-linked `copilot.operator.loop.v1` traces for both capable-provider custom Responses execution and the Agents SDK variant, while deterministic fallback traces remain supported for mock/disabled providers.
- Operator trace events now include compact `output_summary` payloads on completed/failed tool results and `output_summaries` plus `failed_steps` in final reports. Full `outputs` remain available for compatibility, while the compact summaries make per-step results easier to scan and distinguish skipped steps from actual tool failures.
- Research report generation now consumes persisted operator events in addition to tool traces, so confirmation-needed, skipped, completed, and failed step statuses retain source ids, compact output summaries, and event-level warning provenance in exported report summaries.
- Generated research reports now expose a structured `warning_provenance` section alongside the existing flat `warnings` list. Precise operator event warnings are preferred, final-report aggregate warnings are used only as fallback provenance, and Markdown exports include a compact warning-provenance section.
- Custom-loop and Agents SDK operator final events now include `output_retention` metadata. The `outputs` key remains present for compatibility, but very large full outputs are replaced with per-step compact summaries once they exceed the payload budget.
- Agents SDK orchestration exists behind `GAMMA_COPILOT_OPERATOR_ORCHESTRATOR=agents_sdk`. Gamma-owned custom orchestration remains the default, now using the adaptive Responses loop when the provider supports it and deterministic fallback otherwise. The SDK path exposes one strict `FunctionTool` per authorized read-only action, independently re-authorizes and validates every model-produced argument object through `ResearchActionRegistry`, returns bounded observations to the agent, emits the shared event contract, and persists the model's typed final card as a normal Copilot turn.
- A local benchmark harness lives in `evals/copilot_operator_eval.py`. It compares the custom path with an offline stubbed Agents SDK path on the approved benchmark set and can optionally include a live Agents SDK run when `OPENAI_API_KEY` is configured and the caller passes the live flag. Its closed-loop gate requires `model_final_output`, observation summaries, a typed stop reason, and a substantive card; a generic executed-tool count fails. A no-secret SDK contract smoke test verifies exact manual `FunctionTool` schemas, `Runner.run`/`run_streamed(..., max_turns=...)`, and `ModelSettings(parallel_tool_calls=False)` without an API call.
- Live smoke note: using the existing `.env` `OPENAI_API_KEY`, the real Agents SDK path successfully ran the bounded portfolio rate-shock operator case on 2026-05-31. The run used `GAMMA_COPILOT_MODEL=gpt-5.4`, executed registry tools through `openai_agents_sdk_operator`, emitted the normal operator event contract, and returned `ready`. The current OpenAI docs list `gpt-5.5` and medium reasoning as the newer baseline, so model/reasoning migration should be handled as a separate eval-backed tuning pass rather than folded into the operator default switch.
- GPT-5.5 migration note: a narrow live benchmark on 2026-06-03 compared the custom loop, `gpt-5.4` low, `gpt-5.5` medium, and `gpt-5.5` low on the existing Research Operator eval set. The custom loop passed all cases and remains the default orchestrator. The `gpt-5.4` low Agents SDK path missed the required reverse-valuation tool on the cross-domain event-report case and hit the max-turn guard. Both `gpt-5.5` variants passed all cases; `gpt-5.5` low matched medium on tool selection, confirmation stops, and trace/report quality while using fewer measured SDK tokens and lower SDK latency, so the feature-flagged Agents SDK operator config now defaults to `gpt-5.5` with `low` reasoning. This does not change Gamma's action registry, permission boundaries, or default custom-loop orchestrator.

Current Research Operator state (foundation inventory, not the desired end state):

- `run_risk_contribution_analysis` is automatic read-only and runs Gamma's existing risk engine from the active portfolio or research snapshot. It returns contribution rank, coverage/concentration metrics, VaR/beta/correlation context, bounded Monte Carlo diagnostics when requested, warnings, and provenance without relying on a precomputed UI risk result or changing any state.
- `run_risk_scenario_analysis` is automatic read-only and now accepts typed, bounded shock inputs (`scenario_type`, `rate_shift_bps`, `equity_shock_pct`, `duration_proxy_years`, and explicit `symbol_shocks`). Gamma still computes VaR/contribution/frontier metrics through the existing risk engine; the new `shock_proxy` block is a transparent position-level estimate, not full curve or factor repricing.
- `run_research_scope_analysis` is automatic read-only and runs Gamma's existing ResearchService scope analysis from an active single-name or synthetic research result, or explicit typed scope arguments. It returns scope metrics, structure, coverage, constituent diagnostics, warnings, and provider provenance without saving scopes, loading durable research objects, rebalancing, or modifying state.
- `run_strategy_lab_backtest` is automatic read-only and summarizes the active normalized Strategy Lab imported result, composition, or comparison. It does not execute strategy code, restore raw uploaded CSV rows, save research objects, rebalance, or modify portfolios.
- `run_hypothetical_portfolio_comparison` is automatic read-only and builds a temporary long-only synthetic research scope from typed legs/weights, compares its normalized return stream to a benchmark through the existing Compare/Scenario service path, and can optionally hand the temporary fixed-notional snapshot to Risk for bounded contribution analytics. It returns coverage, relative metrics, optional risk handoff output, warnings, and provenance without saving, rebalancing, or trading anything.
- `run_options_realized_implied_comparison` is automatic read-only and uses Gamma's existing IVService surface path or active Options state to compare ATM implied volatility against available provider historical-volatility fields by expiry. It returns implied moves, vol premium/ratio rows where data is sufficient, missing-history or missing-IV statuses where it is not, surface quality/collection metadata, warnings, and provenance without direct Copilot provider calls or state changes.
- `run_fundamentals_reverse_valuation` remains automatic read-only. DCF update proposals stop at draft/confirmation checkpoints; `fundamentals.apply_dcf_update` remains confirmation-required and is not run by automatic operator execution.
- `evals/copilot_operator_eval.py` currently passes for both the custom loop and offline stubbed Agents SDK path on DCF confirmation stop, reverse valuation, risk rate shock, hypothetical portfolio comparison, Strategy Lab backtest, Options realized-versus-implied comparison, research scope analysis, and cross-domain single-name event report. Checkpoint 7 adds retained argument-fidelity, validation-correction, observation-continuation, forbidden-action, budget-stop, and model-final tests plus the generic-summary eval rejection. The remaining benchmark gaps are unloaded-entity acquisition, generalized working state/materialization, degraded cross-domain replanning breadth, and same-run approval resumption.

What remains for the next agents:

1. Generalize `copilot.working-analysis.v1` from the completed Fundamentals and hypothetical-portfolio/Risk slices to Options sets, Strategy Lab inputs, and the remaining tab-owned temporary analyses.
2. Generalize interruptions and recovery as described in workstream K. Do not broaden durable mutation families until pause/resume state, idempotency, diffs, rollback policy, and permission evals are reusable.
3. Extend the Checkpoint 7 trace gate with degraded-result cross-domain replanning, unnecessary-tool, stale-context, remaining unloaded-entity families, working-state, and same-run approval-resume cases.
4. Compare the custom Responses loop and Agents SDK as later end-state contracts enter the benchmark. Promote Agents SDK only if sessions, interruptions, traces, maintainability, quality, reliability, latency, or cost show a practical advantage without weakening permissions.
5. Continue adding narrower read-only drilldowns only where they enable a representative end-to-end Operator goal. Tab-specific analytical depth remains owned by the corresponding Gamma service.

## Open Decisions

Future agents should update this section.

| Decision | Current stance | Notes |
|---|---|---|
| Direct Responses API vs Agents SDK | Keep Agents SDK as the maintained, feature-flagged Research Operator comparison path behind Gamma's registry; keep the Gamma-owned custom path as the product default, adaptive for capable providers and deterministic only for fallback/test providers. | Checkpoint 7 implements the same closed-loop authority contract in both variants. The 2026-07-30 live custom-path smoke validated typed quota failure but did not produce successful live quality/latency/cost evidence, so no orchestrator switch is justified. |
| Desired Operator harness | Closed-loop model-tool-model execution with strict server-owned authority, budgets, state, and stopping rules. | Deterministic plans remain useful fallbacks/primitives, but cannot satisfy the clarified adaptive Operator end state alone. |
| UI control vs backend tools | Backend tools are authoritative; UI navigation is convenience only. | This preserves auditability and avoids fragile DOM automation. |
| Outside info | Provider adapters first; general web search only as fallback or explicit mode. | News and estimates are context, not execution. |
| Copilot roles | Research Agent plus Research Operator, differentiated by authority. | Agent interprets attached context without operating Gamma; Operator acquires inputs and runs app-native research workflows. Authority changes are visible, never silent. |
| Working analysis | Operator may create and modify explicit session-scoped ephemeral state automatically. | Hypothetical portfolios, DCFs, scenarios, assumptions, and intermediate outputs must not be confused with durable saved objects. |
| Research Script Workspace | Approved as a narrow Strategy Lab mode behind a provider-neutral isolated runtime; mock first, then Code Interpreter if the exact-source/hash spike passes. | Operator may draft and explicitly run, but has no unrestricted code authority. Canonical post-materialization edits are user-controlled and later Operator changes are staged. See `research_script_workspace_plan.md`. |
| Local state changes | Allowed only for research state and confirmation-required when an existing durable object will be changed. | Approval pauses and resumes the same run. Never permit market/account/wallet execution. |
| DCF | Important first confirmed-mutation use case, but not the agent's whole identity. | The agent should be domain-broad. |
| Official OpenAI guidance | Refresh before material agentic work and record the review. | Current framework/model guidance informs the design but does not override Gamma's evals or product boundary. |

## Agent Handoff Notes

When continuing this work:

1. Refresh the official OpenAI agent/tool/orchestration/state/approval/tracing guidance and record the date, URLs, and architectural effect before material changes.
2. Update the checklist above before or after implementation.
3. Keep changes aligned with Gamma's read-only boundary.
4. Prefer typed backend tools over UI-driving behavior.
5. Add trace-level tests for entity resolution, argument fidelity, planner decisions, tool adaptation, final synthesis, resumption, and permission behavior.
6. Preserve provenance and source refs in every new payload.
7. Make missing data explicit. Do not let Copilot imply a provider was available when it was not.
8. Keep the user-facing Copilot experience concise: plan, temporary assumptions, progress, findings, warnings, approvals, and saved artifacts.
9. Read and update [`research_script_workspace_plan.md`](./research_script_workspace_plan.md) before adding Script actions, materialization, runtime calls, source revisions, or script-run evals. Do not repurpose `run_strategy_lab_backtest` for code execution.
