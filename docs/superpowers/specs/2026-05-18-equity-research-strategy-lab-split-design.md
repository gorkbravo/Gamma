# Equity Research And Strategy Lab Split Design

## Context

Gamma's current `Research` tab mixes two distinct workflows:

- equity-oriented market and scope research, including the market treemap, single-name analysis, basket/scope construction, and handoffs to Fundamentals, Risk, and Options;
- lab-oriented strategy experimentation, including imported return streams, comparison, saved runs, and future backtesting.

Roadmap V2 cautions against tab sprawl, but it also defines when a top-level tab is justified: a durable research domain with a distinct data model, a distinct workflow, enough internal modes, and valuable cross-tab relationships. The current `Research` tab now contains two such domains. Splitting them clarifies the product without changing Gamma's read-only research boundary.

The generic `Research` label is also weak because it sits inside the Research workspace. Replacing it with `Equity Research` and `Strategy Lab` makes navigation reflect user intent.

## Goals

- Retire the generic top-level `Research` destination.
- Create an `Equity Research` tab for listed-market and equity-oriented research.
- Create a `Strategy Lab` tab for reproducible strategy, portfolio, and scenario experiments.
- Let Strategy Lab compose live Gamma research objects when the user chooses to do so.
- Preserve the read-only boundary: Strategy Lab studies research compositions, not broker portfolios or executable orders.
- Define a shared Gamma Research Object contract so Strategy Lab can consume objects from other tabs without coupling to each tab's internal payloads.
- Leave arbitrary code execution out of the initial split while preserving a future sandbox path.

## Non-Goals

- Do not add order placement, rebalancing, broker account mutation, wallet signing, or automated execution.
- Do not duplicate full Fundamentals, Risk, Options, Macro, Crypto, or Commodities workspaces inside the new tabs.
- Do not add arbitrary in-app code execution in the first implementation.
- Do not convert Strategy Lab into a general notebook surface.
- Do not make every Gamma object tradable or position-like. Some objects are analytical lenses or overlays.

## Information Architecture

The current top-level `Research` tab should become two top-level tabs in the Research workspace:

1. `Equity Research`
2. `Strategy Lab`

This is a net gain of one tab, but it removes the mixed-world problem inside the current `Research` tab.

### Equity Research

`Equity Research` is the user's entry point for equity market pulse, listed-market discovery, single-name inspection, basket/scope construction, and equity-oriented handoffs.

Initial modes:

- `Overview`: market treemap, sector/industry pulse, leaders/laggards, broad ETF/index context, provider freshness, and coverage warnings.
- `Scope Analysis`: the current single-ticker and synthetic basket workflow, including return/risk diagnostics and constituent structure.
- `Comparables`: peer, sector, and company comparison with handoffs into Fundamentals instead of duplicating full filing/DCF analysis.
- `Scenario / Context`: compact equity scenario comparison and links into Risk, Macro, and Options where relevant.
- `Saved Equity Research`: saved scopes, screens, selected equity objects, and reusable equity research artifacts.

Equity Research produces and inspects equity research objects. It should not become the place for multi-asset strategy composition or backtesting.

### Strategy Lab

`Strategy Lab` is the user's experiment layer. It composes Gamma research objects into reproducible, read-only strategy and portfolio experiments.

Initial modes:

- `Composer`: weighted composition of live Gamma objects and saved objects.
- `Backtest / Analyze`: normalized return-stream resolution, aligned performance metrics, benchmark comparison, drawdown, volatility, correlation, and contribution analysis.
- `Regime / Stress`: Macro and Risk windows, stress periods, factor shocks, volatility regimes, and event slices applied as lenses.
- `Imports`: the current CSV/imported strategy return workflow.
- `Saved Runs`: saved experiments, assumptions, warnings, normalized outputs, and reusable return streams.

Strategy Lab consumes objects from across Gamma. It should not swallow the specialist tabs. Fundamentals, Risk, Options, Macro, Crypto, Commodities, and Prediction Markets remain the authoritative places for their own domain-specific research.

## Shared Gamma Research Object Contract

Tabs that want to participate in Strategy Lab should publish objects through a shared contract.

Required fields:

- stable object id;
- source tab and source mode;
- display name;
- object type;
- symbols, identifiers, or constituents when applicable;
- weights when applicable;
- available date range when applicable;
- provider and provenance summary;
- warnings;
- resolver capability.

Supported initial object types:

- `equity_scope`: single ticker, equity basket, ETF/index proxy, sector, industry, or custom weighted scope.
- `strategy_return_stream`: imported CSV strategy, saved run, or normalized backtest output.
- `crypto_basket`: token basket, narrative basket, or saved crypto composition.
- `macro_regime`: named event/regime window or macro condition.
- `risk_scenario`: stress window, drawdown regime, factor shock, or risk model slice.
- `fundamental_case`: company bear/base/bull case, reverse valuation case, or valuation assumption set.
- `iv_context`: volatility regime, implied distribution, realized-vs-implied context, or surface-derived condition.

Resolver capabilities should explicitly classify how Strategy Lab can use an object:

- `return_leg`: can resolve into a return stream and participate as a weighted leg.
- `benchmark`: can resolve into a comparison series.
- `lens`: filters, labels, or slices the analysis window.
- `overlay`: provides explanatory context or assumptions without becoming a position.
- `reference_only`: can be attached to a run but not directly computed against.

This distinction prevents analytical objects from pretending to be positions. For example, a macro regime is a lens, not a portfolio leg. A fundamental case is usually an overlay or reference object in V1, not a return stream.

## Strategy Lab Composition Model

The user-facing model should be positions and weights because that is how a user naturally describes an experiment.

Example:

```text
Composition
  Leg A: 45% Equity Scope - AI Infrastructure Basket
  Leg B: 25% Strategy Return Stream - Vol Carry CSV
  Leg C: 20% Crypto Basket - Large-cap L1s
  Leg D: 10% Cash or benchmark proxy
  Lens: 2022 inflation shock
  Overlay: High-vol IV regime
```

The internal compute model should resolve return-capable legs into aligned normalized return streams. Strategy Lab then applies weights and assumptions to produce a research run.

Initial outputs:

- cumulative and annualized return;
- annualized volatility;
- Sharpe-style and Sortino-style metrics;
- max drawdown and drawdown duration;
- benchmark-relative return;
- rolling correlation and beta where applicable;
- contribution by leg;
- coverage and alignment diagnostics;
- warnings for missing history, stale providers, partial overlap, proxies, FX assumptions, and unsupported objects;
- regime-specific slices when lenses are applied.

This lets Strategy Lab support position-like composition while staying backed by normalized return-stream analysis.

## Cross-Tab Handoffs

Equity Research should hand off to:

- `Fundamentals` for company filings, statements, DCF, reverse valuation, and peer details.
- `Risk` for scope-level risk, concentration, contribution, drawdown, and stress diagnostics.
- `Options` for underlying IV, skew, term structure, realized-versus-implied, and implied distribution.
- `Strategy Lab` when the user wants to include a scope or selected equity object in an experiment.
- `Copilot` for grounded equity research summaries.

Strategy Lab should hand off to:

- `Risk` for deeper risk decomposition of a saved run or composed return stream.
- `Macro` for regime interpretation and macro window selection.
- `Options` for volatility-context overlays on equity or index legs.
- `Fundamentals` when a composition leg is company-specific and valuation context matters.
- `Copilot` for grounded experiment summaries, assumptions, and memo drafting.

Handoffs should use the existing cross-tab envelope pattern where possible: source tab/mode, selected entity, timeframe, provider/source, warnings, normalized ids, timestamp, and intended target.

## Code Execution Boundary

Arbitrary code execution should not ship as part of the tab split.

The staged path is:

### Stage 1: No Code Execution

Strategy Lab supports live object composition, imported return streams, saved runs, weighted analysis, and regime/stress lenses through declarative app controls.

### Stage 2: Strategy Recipes

Strategy Lab can later support constrained strategy definitions:

- universe;
- ranking or selection rule;
- weighting scheme;
- rebalance frequency;
- volatility target;
- max weight;
- benchmark;
- transaction-cost assumption if modeled.

These recipes are validated, inspectable specs rather than arbitrary code.

### Stage 3: Sandboxed Code Producer

Only after the first two stages are stable, Gamma may consider a separate sandbox where code can produce a normalized research object, such as a `strategy_return_stream` or signal table.

The sandbox must not have direct access to:

- broker APIs;
- order placement;
- account modification;
- secrets;
- arbitrary filesystem paths;
- unrestricted network calls;
- app internals.

The sandbox should receive an explicit data snapshot and return an explicit schema. Runs should have time and memory limits, and saved outputs should include code hash, inputs, outputs, assumptions, provenance, and warnings.

The governing rule is:

> Code, if ever added, is a producer of research objects. It is not an operating surface inside Gamma.

## UI And Navigation Notes

Both tabs should follow Gamma's standard tab architecture:

```text
Tab -> shared context -> mode bar -> mode modules
```

Both tabs should use visible horizontal mode bars, compact context controls, and the existing plane-model styling. Use the mature Gamma surfaces as references by workflow: Macro for shared context and mode switching, Fundamentals for deep entity work, Commodities for provider caveats and cross-domain context, and Risk for compact quantitative diagnostics.

The sidebar should show `Equity Research` and `Strategy Lab` as separate research workspace tabs. Existing keyboard and tab-order persistence should treat them as normal top-level research tabs.

If migration compatibility is needed, old `Research` deep links should route to `Equity Research`, with mode mapping:

- old `overview` -> `Equity Research / Overview`;
- old `scope_analysis` -> `Equity Research / Scope Analysis`;
- old `strategy_lab` -> `Strategy Lab / Imports` or `Strategy Lab / Backtest / Analyze`;
- old `compare_scenario` -> `Strategy Lab / Backtest / Analyze`;
- old `saved_research` -> split by object type when possible, otherwise show in Strategy Lab `Saved Runs` with compatibility warnings.

## Persistence

Existing saved research objects should be migrated or read through compatibility logic.

Recommended split:

- equity scopes, screens, and single-name/basket artifacts belong to `Saved Equity Research`;
- imported strategy results, return streams, comparison runs, and composed experiments belong to `Strategy Lab / Saved Runs`;
- unknown or future schema objects remain loadable best-effort with explicit warnings.

Raw uploaded CSV rows should still not be persisted by default. Persist normalized return streams and metadata unless the user explicitly opts into storing source files later.

## Testing

Implementation should add tests for:

- mode registry and navigation state for the two new tabs;
- legacy `Research` route/mode compatibility mapping;
- shared Gamma Research Object serialization and resolver capability classification;
- Strategy Lab composition validation;
- return-leg alignment and weighted composition calculations;
- lens/overlay behavior for non-return objects;
- saved-object split and compatibility loading;
- cross-tab handoff envelope construction for Equity Research to Strategy Lab and Strategy Lab to Risk/Copilot.

Frontend validation should verify that both tabs preserve the standard Gamma layout, mode-bar behavior, responsive collapse, and no nested-card drift.

## Acceptance Criteria

- The generic top-level `Research` tab is replaced by `Equity Research` and `Strategy Lab`.
- Equity Research contains the market overview/treemap and current scope-analysis workflow.
- Strategy Lab contains imported strategy analysis and the new composition concept.
- Strategy Lab can compose live Gamma objects where resolver capabilities allow it.
- Return-capable objects are resolved into normalized return streams before analysis.
- Macro regimes, risk scenarios, IV contexts, and fundamental cases can act as lenses or overlays without pretending to be positions.
- No broker execution, rebalancing, order placement, wallet signing, or account mutation path is introduced.
- No arbitrary code execution ships in the first split.
- Legacy saved objects and old Research routes degrade gracefully through compatibility handling.
- Copilot and cross-tab handoffs receive grounded context from both new tabs.
