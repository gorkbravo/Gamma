# Macro V1 Implementation Prompt

Use this prompt when handing Gamma's Macro Phase 2 V1 implementation to another AI coding agent.

## Prompt

You are implementing **Gamma Phase 2 V1: Macro Tab** in the repository at `C:\Users\User\Desktop\Gamma`.

Start by reading:
- `AGENTS.md`
- `roadmap.md`
- `docs/provenance_expectations.md`
- the existing prediction-market implementation for the architecture pattern

### Product goal

Build the first usable **Macro** tab as a **single top-level tab inside the research workspace**. It must be a **mode-driven workspace**, not a long one-page dashboard and not a geography-driven page tree.

The initial internal modes are:
- `Snapshot`
- `Cross-Asset`
- `Rates & Policy`

Do not build `Commodities` or `Credit / Stress` as first-class modes in V1.
Do not build a dedicated `Events / Regimes` mode yet unless the implementation naturally scaffolds it lightly.

### UX / information architecture requirements

Macro navigation should work like this:
- one top-level `Macro` tab in the existing research workspace
- one visible internal mode bar with `Snapshot`, `Cross-Asset`, and `Rates & Policy`
- one persistent context bar for:
  - `Region`
  - `Timeframe`
  - `Theme`
  - optional comparison state if practical

The user should:
- land on `Snapshot`
- preserve context when moving between modes
- be able to click a card on `Snapshot` and drill into a deeper mode with relevant context applied

Do not organize V1 as separate top-level pages such as:
- `US Rates`
- `EU Rates`
- `US Macro`
- `EU Macro`

Region is a lens, not the primary navigation model.

### Regional scope

V1 regional scope:
- `US` should be the deepest and most usable region
- `EU` can be present only if it can be added cleanly without weakening the US implementation
- `Global` should only appear where cross-market comparison is naturally useful

### Data-source scope

Prefer free or public data sources with durable identifiers and clear provenance.

V1 priorities:
1. `FRED / ALFRED`
2. `Treasury public curve / Fiscal Data`
3. `BLS`
4. `BEA`

Optional if time allows:
- `Fed H.10 / H.15`
- `EIA`

Do not make V1 depend on proprietary or fragile sources.
Do not center V1 on swap-curve data unless a clean, well-supported public source is already available in the repo or can be added safely.

### Architecture requirements

Follow Gamma's existing roadmap-era pattern, especially the prediction-market stack:
- adapters isolate external providers
- application service owns normalization and reusable analytics
- API routes stay thin
- API schemas mirror normalized domain models
- frontend store loads data through explicit async functions

Do not force Macro through `ResearchDataProvider` or portfolio abstractions.
Treat Macro as a new first-class domain.

Implement at minimum:
- `src/models/macro.py`
- `src/services/macro_adapters.py`
- `src/application/macro_service.py`
- API routes and schemas for macro endpoints
- frontend types, stores, and a `MacroView.svelte`

### Provenance requirements

Every new normalized macro entity should carry the roadmap provenance contract:
- `source_provider`
- `retrieved_at`
- `origin`
- `transformation_note`

For derived values, `transformation_note` must be non-null.
Cached payloads must preserve source retrieval time, not just cache write time.

### Backend V1 endpoints

Prefer this endpoint shape:
- `POST /macro/snapshot`
- `GET /macro/series/{series_id}/history`
- `POST /macro/divergences`
- `GET /macro/events`

If implementation pressure requires simplification, preserve the separation between:
- overview/snapshot assembly
- series history retrieval
- divergence analytics
- event calendar retrieval

Do not collapse all macro functionality into one monolithic endpoint.

### V1 feature scope

#### Snapshot

Build a compact landing mode that answers: `What matters right now?`

Include a limited but coherent set of cards such as:
- growth context
- inflation context
- policy context
- curve shape
- real yields / breakevens where available
- dollar / FX proxy
- credit / stress proxy if available from public sources
- top divergences
- upcoming macro events

#### Rates & Policy

This should likely be the most mature V1 mode.

Include:
- front-end rate context
- curve summary
- current vs prior curve comparison
- real-yield / breakeven context where public data is clean
- event / meeting context if available

#### Cross-Asset

Build a theme-driven view that answers: `Do these markets agree?`

Initial themes can include:
- inflation
- growth
- policy
- recession risk

This mode should compare expressions across a small curated set of series and proxies, then rank or label divergences.

### Caching and freshness

The existing `CacheService` can be reused, but Macro will likely need source-aware or frequency-aware freshness behavior.
At minimum, structure the code so that:
- daily macro series are not treated the same as event-calendar data
- future per-source TTL improvements are easy to add

### Testing requirements

Add tests in the same spirit as prediction markets:
- adapter normalization tests
- service analytics tests
- API route tests
- frontend/store tests where appropriate

Use focused tests for:
- provenance preservation
- context-preserving mode behavior where practical
- divergence ranking logic
- snapshot assembly

### Implementation priorities

Do the work in this order:
1. Read the existing prediction-market architecture and mirror its boundaries
2. Add macro domain models
3. Extract reusable FRED fetching if appropriate from the current risk-free-rate path
4. Implement the first macro adapters and a minimal `MacroService`
5. Add the backend routes and schemas
6. Add frontend types, stores, and a first `MacroView.svelte`
7. Add tests

### Constraints

- Gamma is a read-only research environment, not an execution system
- do not introduce unnecessary top-level workspace abstractions
- do not build a bloated dashboard before the normalized data layer is coherent
- do not hide the main macro mode switch in a dropdown
- do not over-expand region coverage in V1

### Deliverable

The result should be a coherent first-pass Macro tab that:
- has a visible mode bar
- preserves shared context across modes
- provides a useful `Snapshot`
- provides a usable `Rates & Policy` view
- provides an initial `Cross-Asset` divergence view
- uses public-data adapters with provenance-rich normalized models
- fits naturally into Gamma's existing runtime, API, and frontend patterns
