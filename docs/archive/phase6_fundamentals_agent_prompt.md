# Phase 6 Fundamentals Agent Prompt

Use this prompt with another coding agent working inside the Gamma repo.

```text
You are working in the Gamma repository at the roadmap stage where Phase 6 - Fundamentals is the last major first-pass phase still intended to land inside the current roadmap.

Your job is to make as much real, roadmap-aligned progress on Phase 6 as the repo can reasonably support in one pass.

Do not optimize for a tiny safe slice.
Do not stop at scaffolding.
Do not treat architecture-only prep as success unless the codebase truly blocks further implementation.
Push as far as possible, end to end, while keeping the result coherent and shippable.

Read these files first before making decisions:
- roadmap.md
- README.md
- docs/README.md
- docs/provenance_expectations.md
- docs/design_principles.md
- docs/fundamentals_phase6_spec.md

Product boundary:
- Gamma is a read-only research environment, not a trading bot and not an execution platform.
- Preserve the roadmap's data-first architecture bias.
- Favor provider adapters, normalized schemas, reusable analytics, cache/storage hooks, provenance, and research workflows over shallow UI.
- Do not turn Phase 6 into a generic fundamentals dashboard with weak source traceability.
- Do not bypass Gamma's architecture by pushing data munging into the frontend.

Primary goal:
Materially advance Phase 6 - Fundamentals in a way that is:
- roadmap-aligned,
- provenance-aware,
- architecture-consistent,
- usable in the actual Gamma app,
- deeper than a mockup or placeholder shell.

Current intended Phase 6 V1 shape:
- `Overview` mode
- `Financials` mode
- `DCF` mode

These modes are defined in docs/fundamentals_phase6_spec.md and should be treated as the active product spec.

Important implementation bias:
- US-only first pass is acceptable and preferred.
- SEC-filer coverage is the target for the first pass.
- Use SEC-native fundamentals plus existing IBKR integration for price-aware valuation context.
- Gamma must own ratio logic, peer-basket logic, and DCF logic.

Data-source strategy:
- Prefer `edgartools` or a similar SEC-native path for filings, statement history, company facts, filing metadata, and provenance-rich fundamentals ingestion.
- Use existing IBKR integration for current price, price history, and market-aware valuation fields where practical.
- If classification data is not available from one clean source, implement a practical seed-first approach rather than blocking the phase.

Temporary EDGAR identity note:
- Until Gamma has user-configurable SEC identity settings, use this identity for edgartools / SEC automated-access configuration:
  - `Gorka Bravo`
  - `gorka.bravo1@gmail.com`
- Use it explicitly where SEC identity configuration is required for development.
- Do not invent a different identity.
- Also preserve a clear TODO or config seam so this can later become user-configurable rather than hard-coded forever.

Execution mindset:
- Try to land the broadest coherent end-to-end slice possible.
- The ideal outcome is not merely a tab shell. The ideal outcome is a real first-pass Fundamentals workspace with meaningful data flow, ratios, and DCF scaffolding that actually works.
- If the repo can support most of the phase in one pass, pursue that.
- Only fall back to a smaller subset if a broader pass is genuinely blocked.

Best-case delivery target:
- Top-level `Fundamentals` tab in the research workspace
- mode bar with `Overview`, `Financials`, `DCF`
- backend adapters/services for SEC fundamentals and IBKR price context
- company search / selection flow
- overview payload with company profile, headline valuation context, mini chart, and first-pass comps heatmap
- financials payload with annual/quarterly statements and common ratios
- DCF engine with persistent `Bear/Base/Bull` scenarios and scenario selection
- provenance-rich models and responses
- first-pass tests for the new backend logic and any critical frontend/store behavior

If full best-case delivery is not possible, preserve ambition and ship the deepest coherent subset.

Strong fallback order:
1. `Overview + Financials + backend fundamentals ingestion`
2. `Overview + Financials + partial DCF engine`
3. `Overview + backend company/statement foundation`

Do not stop at:
- route stubs,
- placeholder tabs,
- mock-only DCF UI without compute logic,
- frontend-only prototypes disconnected from real data.

Architecture expectations:

Backend:
- Routes stay thin.
- Add schema models under src/api/schemas.
- Add application-layer orchestration in src/application.
- Add provider adapters in src/services.
- Add domain models in src/models where appropriate.
- Reuse existing cache/provenance patterns.

Frontend:
- Follow existing research-tab structure and the design principles.
- Reuse Gamma mode-bar patterns from Macro and Crypto.
- Keep the view dense, flat, and spreadsheet-like where appropriate.
- The DCF grid should feel analytical, not decorative.

Copilot compatibility:
- Preserve the ability to add Copilot grounding later.
- If practical, add first-pass fundamentals context helpers in the existing Copilot patterns.
- Do not let Copilot work block the core Phase 6 slice if time is tight.

Key product decisions already made:

1. Modes
- `Overview`
- `Financials`
- `DCF`

2. Peer model
- Do not rely on sector labels alone as "the comps answer."
- Treat classification as a seed.
- Build a Gamma-owned `peer basket` concept that the user can adjust.
- The peer basket should stay stable across the overview heatmap and other comps surfaces.

3. DCF semantics
- Historical actuals are locked.
- Projected values support formula defaults plus manual overrides.
- `Bear`, `Base`, and `Bull` exist in parallel.
- The currently selected scenario controls the visible working projection line and summary outputs.
- The scenario rows are the source of truth.

4. Provenance
- Filing-derived values, market-derived values, and Gamma-derived values must remain distinguishable.
- Derived values need a non-null transformation note.

Implementation guidance by area:

Company resolution and search:
- Add a practical company search / lookup path for US tickers.
- If broad SEC company search is too heavy for a first pass, support at least ticker-based resolution cleanly and leave room for richer discovery later.
- The user must be able to load a company into the Fundamentals tab without awkward manual backend-only steps.

SEC fundamentals adapter:
- Build a dedicated adapter boundary such as `SecFundamentalsAdapter`.
- Responsibilities may include:
  - resolving SEC company identity / CIK
  - fetching company metadata
  - fetching annual and quarterly statement history
  - returning filing chronology
  - preserving filing metadata such as form type, report period, filing date, accession number, and amendment status where possible
- Preserve or expose source/provider, retrieved time, origin, and transformation note.

Price-aware valuation adapter:
- Build a dedicated path for price-dependent fields using existing IBKR integration where feasible.
- Responsibilities may include:
  - current price snapshot
  - compact price history for the overview chart
  - derived market cap / enterprise value inputs where possible

Application service:
- Add a `FundamentalsService` or equivalent.
- It should orchestrate:
  - company context
  - overview assembly
  - financial statement normalization
  - ratio calculations
  - peer candidate generation
  - peer basket persistence or in-memory state seam
  - DCF model loading, compute, save, and scenario switching

Overview mode:
- Deliver a real overview, not a placeholder.
- Minimum useful content:
  - company identity block
  - about/profile section
  - headline KPIs
  - small price chart
  - peer heatmap if enough data exists
  - compact filing/provenance summary
  - DCF summary card if DCF state exists
- If the heatmap cannot be made fully rich in one pass, land a credible first-pass version with a stable peer set and a smaller metric family.

Financials mode:
- This mode is essential.
- It should include:
  - income statement
  - balance sheet
  - cash flow statement
  - annual / quarterly toggle
  - common ratios and trend views where practical
- Prioritize continuity, clarity, and period labeling over visual flourish.
- If raw-label view and normalized view are both feasible, that is good stretch work.

DCF mode:
- Aim for a genuine working sheet, not just a few sliders.
- Minimum useful version:
  - historical actual block
  - projected years
  - `Bear`, `Base`, `Bull` scenario storage
  - active scenario selector
  - core DCF outputs including enterprise value, equity value, and implied value per share
- Better version:
  - formula defaults for key lines such as revenue growth, EBIT margin, capex, D&A, NWC
  - per-cell override handling
  - compact scenario comparison summary
  - sensitivity matrix

Peer basket:
- Implement a clear internal shape for:
  - focal company
  - candidate peers
  - selected peer basket
  - display ordering
- Let the architecture support user-adjustable peers even if the first pass UI is modest.
- Do not hardcode a meaningless static peer list.

Classification:
- Sector/industry labels are a seed, not the final truth.
- A practical V1 path is acceptable:
  - upstream classification if available
  - fallback heuristics if needed
  - peer basket stability is more important than taxonomy perfection

Ratios and analytics:
- Gamma should own common ratio calculations.
- Good first-pass ratio families:
  - margins
  - growth
  - leverage
  - liquidity
  - returns on capital
  - cash conversion
- Be explicit when a metric mixes filing and market data.

Provenance rules:
- Follow docs/provenance_expectations.md.
- Filing-derived records must expose SEC provider identity and filing/module origin.
- Market-derived records must expose IBKR origin where used.
- Derived analytics, heatmaps, and DCF outputs need non-null transformation notes.
- Do not silently collapse filing and market inputs into opaque blended values.

Caching and persistence:
- Reuse Gamma cache patterns for fetched SEC and market payloads.
- Preserve original retrieval timestamps.
- DCF scenarios and peer baskets should be treated as research objects that can be persisted locally if practical.
- If durable persistence cannot be finished, add a clean seam for it rather than tangling it into UI state.

Testing expectations:
- Add targeted backend tests for:
  - company resolution
  - fundamentals normalization
  - overview payload construction
  - ratio calculations
  - DCF scenario calculation behavior
- Add frontend tests for any non-trivial store normalization or scenario-switch logic you introduce.
- Run the relevant tests you add.
- State clearly what remains unverified.

UI expectations:
- Follow docs/design_principles.md.
- Use the same design language as Macro and Crypto.
- Keep the interface dense and flat.
- Use borders and dividers, not card stacks.
- The DCF grid is allowed to be dense and spreadsheet-like.
- Do not make it look like a consumer finance app.

Important non-goals unless they become unexpectedly cheap:
- non-US fundamentals coverage
- estimate consensus integrations
- full reverse-valuation engine
- governance / proxy / insider ownership deep dive
- overly elaborate peer-modeling infrastructure
- execution/trading features

Decision rule:
- First determine whether most of Phase 6 can be landed in one coherent pass.
- If yes, do it.
- If not, ship the deepest coherent end-to-end slice you can.
- When reducing scope, cut breadth before cutting integrity.
- Never stop at disconnected scaffolding.

Before finishing:
- summarize what part of Phase 6 is now actually implemented,
- call out what remains open,
- state whether the work is enough to consider Phase 6 materially started,
- identify any follow-on seams that were intentionally left for later.
```
