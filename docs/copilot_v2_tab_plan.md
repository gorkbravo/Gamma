# Copilot V2 Agentic Research Harness

_Living planning document. Future agents should update the status checklist and decision log as implementation progresses._

Last updated: 2026-05-27

## Start Here

Gamma's Copilot should become a broad **agentic research assistant** that can use Gamma's research surfaces intelligently, not a DCF-specific assistant and not a trading/execution agent.

Before implementing changes, read:

- [`../roadmap.md`](../roadmap.md) for the core product boundary: Gamma is a read-only research environment, not an execution platform.
- [`../roadmap_v2.md`](../roadmap_v2.md), especially Workstream 1 and Workstream 7.
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

Implementation interpretation for Gamma:

- The current direct Responses API wrapper is acceptable for early phases and small tool catalogs.
- As the workflow becomes long-running, multi-step, and multi-specialist, prefer the Agents SDK for orchestration, tracing, guardrails, handoffs, resumable state, and evaluation loops.
- Use custom function tools for Gamma-owned services and local research-state operations.
- Use hosted tools only where they fit the product boundary. Web search may be useful for context, but approved provider adapters are preferred for durable research workflows.
- Keep tool descriptions specific: what the tool does, when to use it, inputs, side effects, retry safety, and common failure modes.
- Use structured outputs for plans, tool decisions, reports, and proposed mutations. Do not rely on prose parsing for critical actions.

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
- [ ] Reconcile this document with `roadmap_v2.md` if the roadmap changes.
- [ ] Add any new OpenAI docs references used during implementation.

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

- [ ] Add draft mutation schema and diff renderer.
- [ ] Add confirmation token flow.
- [ ] Add `fundamentals.propose_dcf_update`.
- [ ] Add `fundamentals.apply_dcf_update` after confirmation.
- [ ] Save DCF snapshot before or after confirmed edits according to UX decision.
- [ ] Add similar confirmed flows only where there is clear product value.

### Phase 7 - Agents SDK Migration Or Hybrid Orchestration

- [ ] Evaluate whether current custom loop is limiting tracing, handoffs, state, or evals.
- [ ] Prototype Agents SDK orchestration behind the existing Gamma action registry.
- [ ] Preserve existing Gamma permission checks and local persistence.
- [ ] Add traces/evals for tool selection quality.

## Open Decisions

Future agents should update this section.

| Decision | Current stance | Notes |
|---|---|---|
| Direct Responses API vs Agents SDK | Start with current Responses API wrapper; migrate when orchestration complexity justifies it. | Gamma already has `OpenAIResponsesCopilotProvider`; avoid premature rewrite. |
| UI control vs backend tools | Backend tools are authoritative; UI navigation is convenience only. | This preserves auditability and avoids fragile DOM automation. |
| Outside info | Provider adapters first; general web search only as fallback or explicit mode. | News and estimates are context, not execution. |
| Local state changes | Allowed only for research state and only with confirmation when non-trivial. | Never market/account/wallet execution. |
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
