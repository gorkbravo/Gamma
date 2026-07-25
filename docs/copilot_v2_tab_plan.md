# Copilot V2 Agentic Research Harness

_Living planning document. Future agents should update the status checklist and decision log as implementation progresses._

Last updated: 2026-07-24

## Start Here

Gamma's Copilot should become a broad **agentic research assistant** that can use Gamma's research surfaces intelligently, not a DCF-specific assistant and not a trading/execution agent.

Before implementing changes, read:

- [`../roadmap.md`](../roadmap.md) for the core product boundary and current Workstream 1 / Workstream 7 direction.
- [`provenance_expectations.md`](./provenance_expectations.md) for source, freshness, and transformation expectations.
- [`design_principles.md`](./design_principles.md) before changing the Copilot UI.

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
- It can run analyses through typed Gamma tools across Equity Research, Strategy Lab, Risk, Options, Fundamentals, Macro, Commodities, Prediction Markets, Crypto, Portfolio, and later Sealanes/news.
- It can fetch limited outside context, such as recent news, analyst expectations, transcripts, filings, and official events, through approved read-only adapters.
- It can save research sessions, source snapshots, DCF/model snapshots where applicable, memos, and final reports.
- It can propose local research-state edits and apply them only after explicit user confirmation.

It should not:

- place, modify, cancel, or route orders;
- rebalance a portfolio;
- submit wallet transactions, sign messages, or connect wallets;
- execute arbitrary user strategy code inside Gamma;
- browse the UI visually as its primary mechanism;
- use unrestricted web browsing as a default substitute for provider adapters;
- hide unsupported data gaps behind confident prose.

## Two Copilot Roles

Copilot should develop into two related roles. They are not separate products and the user should be able to move between them naturally, but they imply different orchestration, permission, and UI expectations.

### 1. Research Agent

The Research Agent helps form, structure, and challenge a thesis. This is the evolution of the old Synthesis idea: the user brings a possible idea, Copilot gathers relevant Gamma context across tabs, identifies supporting evidence, counter-evidence, missing data, and outputs a structured thesis, memo, or report.

Examples:

- "Is the market underpricing oil disruption risk?"
- "Research NVDA into CPI/Fed week."
- "Compare AI crypto tokens against AI equities."
- "Does this prediction market disagree with macro data?"

Expected behavior:

- select relevant domains without running every available tab;
- read and synthesize app state and approved external context;
- separate source-backed claims from model-inferred claims;
- make disconfirming evidence and missing data explicit;
- produce concise thesis structures, memos, and reports;
- avoid changing local research state unless the user explicitly asks for an artifact to be saved.

This role can remain mostly compatible with the current planner, bounded executor, session trace, and report path.

### 2. Research Operator

The Research Operator can run Gamma workflows on the user's behalf. It may still help form a thesis, but its distinguishing behavior is that it chooses and runs appropriate app-native tests, simulations, and local research-state workflows, then produces a traceable report the user can read before making any real-world decision.

Examples:

- adjust DCF assumptions, show the diff, and apply only after confirmation;
- run reverse valuation and compare implied expectations to current model assumptions;
- run portfolio/risk stress tests for a rate shock, oil shock, or drawdown scenario;
- build hypothetical or saved research portfolios and compare them to benchmarks;
- run Strategy Lab backtests over imported return streams or Gamma object compositions;
- compare options implied moves, realized volatility, macro event context, and fundamentals for a single-name event;
- save a final memo or report with tool traces, sources, warnings, and generated artifacts.

Expected behavior:

- produce a structured plan before non-trivial operation;
- call typed Gamma tools rather than visually clicking the UI as the primary mechanism;
- run bounded read-only analyses automatically when they fit the request;
- draft local research-state changes automatically, but apply them only under the active confirmation policy;
- preserve source refs, warnings, tool traces, and before/after diffs;
- navigate the UI only as a convenience after the authoritative backend action has run.

The Research Operator is the stronger justification for Agents SDK or a hybrid orchestration layer because it needs multi-step plans, tool handoffs, resumable state, progress streaming, trace inspection, and evals for whether it selected appropriate tests. Even if Agents SDK is adopted, Gamma's backend remains the authority for permissions, execution, persistence, and the read-only product boundary.

## Core Design Principle

The agent should "use the app" by calling app-native tools, not by clicking the UI.

Preferred model:

```text
User request
  -> intent and depth planner
  -> domain relevance scores
  -> bounded research plan
  -> typed Gamma tool calls
  -> synthesis with citations/warnings
  -> saved session/memo/report
  -> optional confirmed local state changes
```

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

Use current OpenAI docs when implementing provider or orchestration changes:

- [Responses API overview](https://developers.openai.com/api/reference/responses/overview): the API surface Gamma currently targets through `OpenAIResponsesCopilotProvider`.
- [Using tools](https://developers.openai.com/api/docs/guides/tools): custom function tools, hosted tools, and tool design.
- [Agents SDK](https://developers.openai.com/api/docs/guides/agents): code-first agent app guidance, orchestration, handoffs, guardrails, results/state, and observability.
- [SDKs and CLI - Use the Agents SDK](https://developers.openai.com/api/docs/libraries#use-the-agents-sdk): use Agents SDK when the app needs orchestration for agents, tools, handoffs, guardrails, tracing, or sandbox execution.
- [Latest model guidance](https://developers.openai.com/api/docs/guides/latest-model): current model, reasoning, structured output, prompt caching, tool-calling, and state-management guidance.
- [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), and [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna): the current capability, balanced, and efficient model tiers.
- [Streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses): provider-native semantic SSE events for text, tools, refusals, completion, and errors.
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs): strict schema output, explicit refusals, and streaming structured responses.
- [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching): GPT-5.6 explicit/implicit cache controls and usage accounting.
- [Responses API Multi-agent beta](https://developers.openai.com/api/docs/guides/responses-multi-agent): hosted parallel subagent orchestration for independently divisible work.
- [Deep research](https://developers.openai.com/api/docs/guides/deep-research): long-running, source-heavy web/file/MCP research through explicit background jobs.

Implementation interpretation for Gamma:

- The current direct Responses API wrapper is acceptable for early phases and small tool catalogs.
- As the workflow becomes long-running, multi-step, and multi-specialist, prefer the Agents SDK for orchestration, tracing, guardrails, handoffs, resumable state, and evaluation loops.
- Use custom function tools for Gamma-owned services and local research-state operations.
- Use hosted tools only where they fit the product boundary. Web search may be useful for context, but approved provider adapters are preferred for durable research workflows.
- Keep tool descriptions specific: what the tool does, when to use it, inputs, side effects, retry safety, and common failure modes.
- Use structured outputs for plans, tool decisions, reports, and proposed mutations. Do not rely on prose parsing for critical actions.

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

The largest gaps are integration and reliability gaps, not missing concepts. Checkpoints 1 through 3 are verified at 86%: the supported OpenAI SDK feeds typed events into server-owned Agent and Operator runs; bounded replay survives subscriber disconnects; shelf and workspace share one typed transcript/evidence renderer; claim refs are normalized against known turn sources before persistence; supported evidence links preserve mapped Gamma context; sessions have a typed lifecycle and schema-v3 migration/recovery contract; restart replay retains the complete turn contract; and the dedicated workspace owns memo/report creation, editing, preview, duplication, deletion, and Markdown export. Remaining gaps are:

- a focused post-checkpoint pass must fix New Chat reconciliation, clear accepted prompts from the composer, and move the storage-recovery warning out of the action area;
- the custom Operator streams live and cancels at safe step boundaries, but Agents SDK progress parity and inline confirmation/diff/rollback UX remain incomplete;
- the Agents SDK operator remains feature-flagged and the current model defaults are GPT-5.5;
- Sealanes, news, and some deeper IV/Commodities drilldowns do not yet have tool parity;
- privacy, retention, cost, usage, and model-routing diagnostics are not yet understandable from the Copilot workspace.

### Completion Boundary

Copilot is complete for the current Gamma pass when a user can do all of the following without leaving the app or reading backend logs:

1. Start, search, rename, archive, restore, and delete a research conversation.
2. See exactly which Gamma contexts, entities, timeframes, freshness states, and warnings ground the turn.
3. Ask a normal research question and receive a genuinely streamed answer with visible provider/model/run state.
4. Distinguish source-backed claims, inference, assumptions, missing data, and warnings, with clickable source/context destinations.
5. Preview a research plan, run bounded read-only tools, watch live progress, stop the run, and inspect per-step results.
6. Reach an inline confirmation checkpoint for any durable local research-state mutation and see the before/after diff and rollback context before applying it.
7. Create, edit, autosave, duplicate, and export a memo or report inside the Copilot workspace.
8. Reopen a session and recover the transcript, context snapshots, plans, events, artifacts, confirmations, and provider metadata faithfully.
9. Get explicit `unavailable`, `degraded`, `refused`, `incomplete`, `cancelled`, and `error` states instead of a neutral empty card.
10. Use the shelf for quick contextual work and promote that exact thread/context into the full workspace without losing state.

Voice, unrestricted web browsing, arbitrary code execution, trading/account/wallet actions, and automatic durable mutations are not current-pass completion requirements. Explicit long-running external deep research is a later opt-in extension, not the default answer path.

### Final In-App Layout

Copilot remains one research workspace, not a collection of top-level modes. `Research Agent` and `Research Operator` are role/focus controls, not tab modes.

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
- **Agents SDK:** retain as the chosen Research Operator orchestration layer behind Gamma's action registry. It remains the better controlled path for typed tools, traces, approvals, server-owned state, and evals.
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

#### C. Context and tool coverage — blocker

- Finish Sealanes context and read-only drilldowns without inventing risk labels.
- Make news a first-class external-context drilldown with item-level source/freshness refs.
- Add the highest-value missing IV, Commodities, Equity Research, and cross-tab drilldowns identified in their roadmap sections.
- Add context-size budgets, deterministic compaction/summaries, and stale-context invalidation.
- Add source navigation mappings and context fingerprints for every selectable scope.

#### D. Research Operator productionization — blocker

- Stream operator events live and support cancellation between safe steps.
- Expand the eval set before switching the feature flag: provider failure, stale/missing context, partial tool failure, cancellation, repeated confirmation, and resume-after-restart.
- Run GPT-5.6 Terra/Sol comparisons against the existing GPT-5.5 baseline.
- Promote Agents SDK only if it passes all permission gates and improves a measured dimension such as tool selection, trace quality, resumability, latency, or maintainability.
- Keep one server-side action registry, permission policy, confirmation-token service, and persistence path for both custom and Agents SDK orchestrators.
- Do not broaden durable mutations until the read-only operator and inline confirmation UI are reliable.

#### E. Artifacts, memos, and reports — checkpoint 3 complete (86%)

- [x] Bring memo/report creation into the dedicated workspace instead of relying on backend-only endpoints or a separate floating surface.
- [x] Add template choice, source-turn selection, title/body editing, autosave state, explicit overwrite confirmation, duplicate, and delete.
- [x] Add canonical preview and Markdown export; PDF/DOCX remain excluded without a real requirement.
- [x] Preserve claim labels, inline citations, source metadata, warnings, model/provider metadata, context snapshots, and tool-trace summary in exports.
- [x] Link artifacts back to the exact source turns and show artifacts in the selected-session inspector.

#### F. Sessions, retention, and model policy — session lifecycle/replay complete; retention/model policy still required

- [x] Add session rename, archive/restore, delete, schema versioning, migrations, and non-destructive corrupted-record recovery.
- [x] Persist role, depth, requested/resolved provider/model metadata, selected scopes, context fingerprints/snapshots, run status, cancellation, usage, plans, events, confirmations, warnings, sources, traces, and artifacts.
- Add a visible retention control explaining Gamma-local storage versus OpenAI stored responses.
- Support a `store: false` path without breaking local continuation, including encrypted reasoning replay only if it is intentionally adopted and tested.
- Put model aliases, allowed efforts/modes, routing rules, and fallbacks in a versioned policy object with capability validation.

#### G. Shelf/full-workspace continuity — required

- Add `Open in Copilot` from the shelf, preserving thread id, active context, sources, warnings, and selected entity/lens.
- Keep quick shelf responses concise and card-oriented; send plans, long runs, confirmations, and artifacts to the full tab.
- Ensure handoffs from source tabs and the shelf converge on the same session/context contract.

#### H. Diagnostics and first-run experience — required

- Show OpenAI configuration, selected/resolved model, orchestrator, storage mode, last provider error, and provider capability state in Settings and the run inspector.
- Surface structured provider errors with retry guidance and a copyable diagnostic id; never leak credentials or raw sensitive payloads.
- Record latency, input/output/reasoning tokens, cache reads/writes, provider calls, tool calls, and cancellation outcome.
- Add first-run guidance for disabled, unconfigured, unavailable, rate-limited, and quota-exhausted states.

#### I. Validation and release gate — blocker

- Backend: provider event parsing, structured output/refusal/incomplete handling, cancellation, persistence replay, migrations, permission/confirmation invariants, and model-policy tests.
- Frontend: streamed reducer, transcript blocks, source navigation, artifact editing, error states, Stop/Retry, responsive inspector, keyboard navigation, and accessibility tests.
- Evals: grounded claims, citation validity, tool selection, domain omission, warning preservation, confirmation stops, final report usefulness, and cost/latency capture.
- Live smoke: Agent and Operator paths for the representative NVDA, CPI/Fed, oil, and portfolio-rate-shock prompts against configured providers.
- Regression: shelf and dedicated-tab parity, session reopen after restart, offline/mock behavior, disabled-provider behavior, and no execution-capable tools.

### Delivery Order

1. ~~Provider-native streaming, shared run lifecycle, bounded replay, and explicit provider state.~~ Completed 2026-07-17 at checkpoint 1 (76%).
2. ~~Typed transcript blocks, validated claim/source resolution, and dedicated-tab evidence parity.~~ Completed 2026-07-24 at checkpoint 2 (80%).
3. ~~In-tab artifacts/memos and session lifecycle completion.~~ Completed 2026-07-25 at checkpoint 3 (86%).
4. Fix the focused New Chat, composer-clear, and storage-warning presentation regressions recorded in `docs/copilot_v2_checkpoint3_prompt.md`.
5. Live operator events, cancellation, and inline confirmations.
6. Missing context/tool coverage and source navigation.
7. GPT-5.6 eval-backed model policy and routing rollout.
8. Agents SDK default decision.
9. Diagnostics, first-run guidance, accessibility, and full release gate.
10. Optional external deep research; later voice.

Do not start with model-string replacement alone. The GPT-5.6 migration should land with provider streaming, capability-aware configuration, usage instrumentation, and eval evidence so the model change improves the product rather than merely changing metadata.

### Definition Of Done

- Provider-native deltas reach the UI before completion; the fake typewriter path is removed.
- Every completed live turn ends in one schema-valid final block or a typed non-success state.
- All source-backed claims resolve to known source ids; unsupported claims are inference or missing data.
- All operator tools pass the server action registry; forbidden execution/account/wallet actions do not exist in the registry.
- Confirmation-required actions cannot apply without the exact active token and visible diff.
- Session replay after app restart reproduces the final transcript, trace, artifacts, and context metadata.
- The dedicated tab supports full memo/report editing and export.
- The shelf can promote a thread into the tab without context loss.
- GPT-5.6 routing is backed by recorded eval results against the GPT-5.5 baseline.
- Live smoke and frontend/backend test suites cover happy, degraded, unavailable, refused, incomplete, cancelled, and provider-error paths.

## Smart Depth Policy

The agent must not run every domain for every request. It should adapt the plan to the request.

Example depth behavior:

| Request | Expected depth |
|---|---|
| "Research NVDA" | Deep Fundamentals and Equity Research, medium Options/news/estimates, light Macro unless relevant. |
| "Research NVDA into CPI/Fed week" | Medium Fundamentals, deep Macro/Rates and Options event risk, recent news/context. |
| "What is going on in oil?" | Deep Commodities, Macro, relevant Prediction Markets/news; no DCF. |
| "Is my portfolio exposed to rate shock?" | Deep Portfolio/Risk/Macro, optional Options; no company memo unless a position dominates. |
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
- never allowed for market execution, account modification, wallet signing, wallet transactions, rebalancing, or arbitrary in-app strategy code execution.

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
- First-pass operator progress events now ride on `/copilot/operator-plan/execute` results as `operator_events` and are persisted with Copilot turns. The backend remains authoritative for execution state; the Copilot workspace renders the trace for inspection only. Events currently cover deterministic custom-loop execution and are shaped so the Agents SDK prototype can emit the same contract behind the existing action registry.
- Operator trace events now include compact `output_summary` payloads on completed/failed tool results and `output_summaries` plus `failed_steps` in final reports. Full `outputs` remain available for compatibility, while the compact summaries make per-step results easier to scan and distinguish skipped steps from actual tool failures.
- Research report generation now consumes persisted operator events in addition to tool traces, so confirmation-needed, skipped, completed, and failed step statuses retain source ids, compact output summaries, and event-level warning provenance in exported report summaries.
- Generated research reports now expose a structured `warning_provenance` section alongside the existing flat `warnings` list. Precise operator event warnings are preferred, final-report aggregate warnings are used only as fallback provenance, and Markdown exports include a compact warning-provenance section.
- Custom-loop and Agents SDK operator final events now include `output_retention` metadata. The `outputs` key remains present for compatibility, but very large full outputs are replaced with per-step compact summaries once they exceed the payload budget.
- Agents SDK orchestration now exists behind `GAMMA_COPILOT_OPERATOR_ORCHESTRATOR=agents_sdk`. The default remains the deterministic custom loop. The SDK path exposes only a single Gamma action-registry execution tool to the agent, validates each requested action against the existing `ResearchActionRegistry`, runs only automatic read-only actions through Gamma's existing context builders and tool executors, emits the same `operator_events` contract, and persists the result as a normal Copilot session turn. It currently targets the same first-pass operator surface as the custom loop: typed risk scenario analysis, Strategy Lab backtest summaries from active normalized results, fundamentals reverse valuation, and DCF confirmation checkpoints without applying local DCF changes.
- A local benchmark harness now lives in `evals/copilot_operator_eval.py`. It compares the deterministic custom loop with an offline stubbed Agents SDK path on the approved operator benchmark set and can optionally include a live Agents SDK run when `OPENAI_API_KEY` is configured and the caller passes the live flag. A no-secret SDK contract smoke test verifies the installed SDK import shape, `function_tool` schema generation, `Runner.run(..., max_turns=...)`, and `ModelSettings(parallel_tool_calls=False)` without making an API call.
- Live smoke note: using the existing `.env` `OPENAI_API_KEY`, the real Agents SDK path successfully ran the bounded portfolio rate-shock operator case on 2026-05-31. The run used `GAMMA_COPILOT_MODEL=gpt-5.4`, executed registry tools through `openai_agents_sdk_operator`, emitted the normal operator event contract, and returned `ready`. The current OpenAI docs list `gpt-5.5` and medium reasoning as the newer baseline, so model/reasoning migration should be handled as a separate eval-backed tuning pass rather than folded into the operator default switch.
- GPT-5.5 migration note: a narrow live benchmark on 2026-06-03 compared the custom loop, `gpt-5.4` low, `gpt-5.5` medium, and `gpt-5.5` low on the existing Research Operator eval set. The custom loop passed all cases and remains the default orchestrator. The `gpt-5.4` low Agents SDK path missed the required reverse-valuation tool on the cross-domain event-report case and hit the max-turn guard. Both `gpt-5.5` variants passed all cases; `gpt-5.5` low matched medium on tool selection, confirmation stops, and trace/report quality while using fewer measured SDK tokens and lower SDK latency, so the feature-flagged Agents SDK operator config now defaults to `gpt-5.5` with `low` reasoning. This does not change Gamma's action registry, permission boundaries, or default custom-loop orchestrator.

Current Research Operator state:

- `run_risk_contribution_analysis` is automatic read-only and runs Gamma's existing risk engine from the active portfolio or research snapshot. It returns contribution rank, coverage/concentration metrics, VaR/beta/correlation context, bounded Monte Carlo diagnostics when requested, warnings, and provenance without relying on a precomputed UI risk result or changing any state.
- `run_risk_scenario_analysis` is automatic read-only and now accepts typed, bounded shock inputs (`scenario_type`, `rate_shift_bps`, `equity_shock_pct`, `duration_proxy_years`, and explicit `symbol_shocks`). Gamma still computes VaR/contribution/frontier metrics through the existing risk engine; the new `shock_proxy` block is a transparent position-level estimate, not full curve or factor repricing.
- `run_research_scope_analysis` is automatic read-only and runs Gamma's existing ResearchService scope analysis from an active single-name or synthetic research result, or explicit typed scope arguments. It returns scope metrics, structure, coverage, constituent diagnostics, warnings, and provider provenance without saving scopes, loading durable research objects, rebalancing, or modifying state.
- `run_strategy_lab_backtest` is automatic read-only and summarizes the active normalized Strategy Lab imported result, composition, or comparison. It does not execute strategy code, restore raw uploaded CSV rows, save research objects, rebalance, or modify portfolios.
- `run_hypothetical_portfolio_comparison` is automatic read-only and builds a temporary long-only synthetic research scope from typed legs/weights, compares its normalized return stream to a benchmark through the existing Compare/Scenario service path, and can optionally hand the temporary fixed-notional snapshot to Risk for bounded contribution analytics. It returns coverage, relative metrics, optional risk handoff output, warnings, and provenance without saving, rebalancing, or trading anything.
- `run_options_realized_implied_comparison` is automatic read-only and uses Gamma's existing IVService surface path or active Options state to compare ATM implied volatility against available provider historical-volatility fields by expiry. It returns implied moves, vol premium/ratio rows where data is sufficient, missing-history or missing-IV statuses where it is not, surface quality/collection metadata, warnings, and provenance without direct Copilot provider calls or state changes.
- `run_fundamentals_reverse_valuation` remains automatic read-only. DCF update proposals stop at draft/confirmation checkpoints; `fundamentals.apply_dcf_update` remains confirmation-required and is not run by automatic operator execution.
- `evals/copilot_operator_eval.py` currently passes for both the custom loop and offline stubbed Agents SDK path on DCF confirmation stop, reverse valuation, risk rate shock, hypothetical portfolio comparison, Strategy Lab backtest, Options realized-versus-implied comparison, research scope analysis, and cross-domain single-name event report. There are no expected-gap cases left in the current benchmark set.

What remains for the next agents:

1. Add narrower read-only drilldowns where they materially improve operator quality:
   - Options event/volatility comparison can build on the new realized-versus-implied operator action once event/calendar context is strong enough.
2. Expand hypothetical portfolio comparison carefully only where it stays read-only:
   - Consider saved research object inputs and Strategy Lab result inputs.
   - Optional handoff to Risk for deeper risk analytics now exists for typed temporary legs; keep it ephemeral and read-only.
   - Keep durable hypothetical portfolio definitions as a later confirmed-mutation family, not automatic operator behavior.
3. Improve reports and trace usability:
   - Surface compact per-step outputs without flooding the final event payload.
   - Preserve source ids and warning provenance in report generation.
   - Make skipped steps easier to distinguish from tool failures.
4. Keep Agents SDK behind the feature flag until the eval harness shows a practical reason to switch defaults, such as better trace quality, resumability, handoffs, or maintainability as tools grow.
5. Do not broaden mutations yet.
   - Candidate future mutation families remain saved research scopes, Strategy Lab compositions, memos, watchlists, scenario/model snapshots, and hypothetical portfolio definitions.
   - Every durable or non-trivial mutation must return a diff, rationale, warnings, source ids, rollback/snapshot context where applicable, and require confirmation.

6. Evaluate Agents SDK against the operator path.
   - Prototype a narrow hybrid orchestrator after the action registry and read-only operator tools are stable.
   - Run the same benchmark tasks through the custom loop and the Agents SDK-backed loop.
   - Use evals to measure whether the orchestrator picked appropriate tools, respected permissions, stopped for confirmations, cited sources correctly, and produced useful reports.
   - If the prototype passes the permission/eval gates, make Agents SDK the Research Operator orchestration layer while leaving Research Agent synthesis on the current path until there is a concrete reason to migrate it.

## Open Decisions

Future agents should update this section.

| Decision | Current stance | Notes |
|---|---|---|
| Direct Responses API vs Agents SDK | Adopt Agents SDK for the Research Operator path behind Gamma's action registry. | User approved the direction on 2026-05-27. Keep the Research Agent path on the current Responses/provider wrapper until a separate migration is justified. |
| UI control vs backend tools | Backend tools are authoritative; UI navigation is convenience only. | This preserves auditability and avoids fragile DOM automation. |
| Outside info | Provider adapters first; general web search only as fallback or explicit mode. | News and estimates are context, not execution. |
| Copilot roles | Research Agent plus Research Operator. | Research Agent structures theses from context; Research Operator runs app-native tests and confirmed local research-state workflows. |
| Local state changes | Allowed only for research state and initially confirmation-required when durable or non-trivial. | Trust-based loosening can be reconsidered after usage, but never for market/account/wallet execution. |
| DCF | Important first confirmed-mutation use case, but not the agent's whole identity. | The agent should be domain-broad. |

## Agent Handoff Notes

When continuing this work:

1. Update the checklist above before or after implementation.
2. Keep changes aligned with Gamma's read-only boundary.
3. Prefer typed backend tools over UI-driving behavior.
4. Add tests for planner decisions and permission behavior, not only happy-path synthesis.
5. Preserve provenance and source refs in every new payload.
6. Make missing data explicit. Do not let Copilot imply a provider was available when it was not.
7. Keep the user-facing Copilot experience concise: plan, progress, findings, warnings, saved artifacts.
