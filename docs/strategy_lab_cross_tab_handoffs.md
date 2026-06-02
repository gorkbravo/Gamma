# Strategy Lab Cross-Tab Handoffs

## Status

This document is the active implementation spec for letting Gamma tabs send selected research objects into Strategy Lab without manual copy/paste of time series.

Progress markers:

- `Not started`: no committed implementation exists.
- `Planned`: design is clear, implementation has not started.
- `In progress`: partial implementation exists and needs follow-through.
- `Implemented`: code exists and has local validation.
- `Verified`: code exists, tests pass, and the relevant browser flow has been checked.

Current snapshot:

| Area | Status | Notes |
| --- | --- | --- |
| Strategy Lab mixed portfolio composer | Implemented | Strategy Lab can compose signed long/short legs from listed-market providers, existing Gamma objects, and inline history. |
| Shared cross-tab handoff protocol | Planned | Existing `CrossTabHandoffEnvelope` covers Copilot-style handoffs, but Strategy Lab needs a typed resolver-capability extension. |
| Strategy Lab inbound queue | Not started | No shared frontend queue currently collects objects from other tabs. |
| Prediction Markets `+ Strategy` action | Not started | Highest-priority first source-tab implementation. |
| Backend handoff resolver endpoint | Not started | Needed so tabs pass object identity and intent, not raw tab-specific time series transformations. |
| Composer draft ingestion from handoff | Not started | Strategy Lab should convert resolved handoffs into editable composer rows. |
| Tab-by-tab capability matrix | Planned | Capability taxonomy is defined here; each tab still needs concrete wiring. |
| Progress tracking and validation checklist | Implemented | This document defines the implementation board and inspection workflow. |

## Product Boundary

Gamma remains a read-only research environment. Cross-tab Strategy Lab handoffs are for analysis, hypothesis testing, portfolio simulation, benchmark comparison, and context assembly. They must not create broker orders, executable portfolios, or live trading instructions.

The user-facing language should prefer:

- `Add to Strategy Lab`
- `Add to experiment`
- `Use as benchmark`
- `Use as lens`
- `Attach context`

Avoid language that implies execution:

- `Trade`
- `Buy`
- `Sell`
- `Submit order`
- `Rebalance live portfolio`

## Concept

Strategy Lab should become Gamma's experiment engine. Specialist tabs remain the authoritative place to research their own domains, while Strategy Lab receives selected objects from those tabs and composes them into reproducible analyses.

The core flow is:

```text
Source tab selection
  -> Add to Strategy Lab action
  -> shared handoff envelope
  -> backend resolver
  -> Strategy Lab inbound queue
  -> editable composer draft row
  -> portfolio/run analysis
```

The user should not need to export or paste probability histories, price histories, baskets, or selected scopes. If Gamma has enough history or resolver metadata, the handoff should load the object into Strategy Lab automatically.

## Design Principles

1. Tabs publish objects, Strategy Lab composes them.
2. The backend resolves histories, transformations, provenance, and warnings.
3. The frontend stores user intent, pending objects, and editable composer drafts.
4. Every handoff declares how Strategy Lab may use it.
5. Unsupported objects can still be attached as context, but they must not masquerade as return legs.
6. Prediction-market contracts need explicit semantics because probability history is not always the same as clean investment return history.

## Capability Taxonomy

Each handoff object must declare one resolver capability:

| Capability | Meaning | Example |
| --- | --- | --- |
| `return_leg` | Can resolve into a return stream and participate as a weighted Strategy Lab leg. | ETF, equity ticker, crypto token, commodity proxy, prediction-market contract with price/probability history. |
| `benchmark` | Can resolve into a comparison series but is not part of the weighted composition by default. | SPY, BTC, DXY proxy, front-month oil proxy. |
| `lens` | Filters or slices the analysis window. | Macro regime, inflation shock window, FOMC meeting path period. |
| `overlay` | Provides explanatory assumptions or context. | DCF case, IV regime, market narrative, related contract cluster. |
| `reference_only` | Can be attached to a run but cannot currently be computed against. | Unsupported data source, qualitative note, stale object. |

## Handoff Envelope

Use the existing `CrossTabHandoffEnvelope` shape where possible, but add Strategy Lab-specific metadata rather than inventing a completely separate routing model.

Recommended Strategy Lab handoff payload:

```ts
interface StrategyLabHandoffEnvelope {
  source_tab: string;
  source_mode: string | null;
  intended_target_tab: "strategy_lab";
  intended_target_mode: "composer" | "benchmark" | "lens" | null;
  selected_entity: {
    entity_type: string;
    label: string;
    normalized_id: string;
    provider_id: string | null;
    native_id: string | null;
    metadata: Record<string, unknown>;
  };
  resolver_capability: "return_leg" | "benchmark" | "lens" | "overlay" | "reference_only";
  asset_class:
    | "equity"
    | "etf"
    | "commodity"
    | "crypto"
    | "prediction_market"
    | "macro"
    | "fundamental"
    | "rates"
    | "fx"
    | "other";
  value_kind: "return" | "level" | "probability" | "price" | "spread" | "context";
  default_side: "long" | "short" | "long_yes" | "long_no" | "none";
  default_weight: number | null;
  selected_timeframe: {
    label: string;
    start: string | null;
    end: string | null;
  } | null;
  provider: string | null;
  source: Record<string, unknown> | null;
  warnings: string[];
  normalized_ids: Record<string, string>;
  timestamp: string;
}
```

## Backend Resolver

Add a resolver endpoint that accepts a handoff envelope and returns composer-ready data.

Suggested endpoint:

```text
POST /research/strategy-lab/resolve-handoff
```

Resolver output should include:

- resolved capability;
- composer draft leg when applicable;
- benchmark draft when applicable;
- lens or overlay payload when applicable;
- transformed history if needed;
- date coverage;
- provider/provenance summary;
- warnings;
- unsupported reason when no computation is possible.

The resolver should be responsible for:

- loading object history from provider adapters or cached Gamma objects;
- converting levels, prices, probabilities, or spreads into the Strategy Lab compute format;
- aligning source semantics with the declared capability;
- rejecting or downgrading objects that do not have enough data;
- producing warnings for missing history, stale data, sparse coverage, proxy assumptions, and non-investable interpretation.

## Frontend Inbound Queue

Add a small Strategy Lab handoff queue in the frontend store.

Suggested operations:

- `enqueueStrategyLabHandoff(handoff)`
- `enqueueAndOpenStrategyLab(handoff)`
- `resolvePendingStrategyLabHandoffs()`
- `acceptResolvedStrategyLabHandoff(resolved)`
- `dismissStrategyLabHandoff(id)`
- `clearStrategyLabHandoffs()`

The queue should persist across route changes and ideally across reloads with local storage. It should not silently run expensive resolver calls until Strategy Lab is opened or the user explicitly chooses `Add & Open`.

## UX Flow

### Source Tab

Place actions close to the selected object, usually in detail panel headers or compact action bars.

Preferred controls:

- `+ Strategy`: queue the object and show a toast.
- `Add & Open`: queue the object and navigate to Strategy Lab.
- `Use as Benchmark`: for benchmark-capable objects.
- `Use as Lens`: for regime/window objects.

Avoid putting heavyweight action buttons on every dense table row unless the row already has an action menu. In tables, prefer selected-row batch actions or row overflow menus.

### Strategy Lab

When pending handoffs exist, show an inbound strip above or inside the composer:

```text
3 pending objects from Prediction Markets, Commodities, and Equity Research
[Accept all] [Review] [Clear]
```

Resolved return legs should become editable composer rows with:

- label;
- source tab/provider;
- asset class;
- side;
- weight;
- value kind;
- coverage range;
- warning indicator;
- remove action.

Unsupported objects should land in an `Attached Context` or `Overlays` area, not in the weighted portfolio table.

## Prediction Markets First Pass

Prediction Markets should be the first source tab because it tests the hardest semantics.

### User Flow

1. User opens Prediction Markets.
2. User selects a contract.
3. Detail panel shows `+ Strategy` and `Add & Open`.
4. User clicks `Add & Open`.
5. Gamma creates a handoff envelope with the selected market id, venue, native id, provider, probability history capability, and warnings.
6. Strategy Lab opens in composer mode.
7. Resolver loads probability history.
8. Composer receives an editable prediction-market leg.

### Required Semantics

Prediction-market handoffs should support at least one initial interpretation:

- `long_yes_probability_return`: treat YES probability/price history as a mark-to-market return stream.

Future interpretations:

- `long_no_probability_return`;
- `probability_level_overlay`;
- payout-aware contract PnL;
- cross-contract spread or relative-value leg.

Warnings should be explicit when:

- history is sparse;
- probabilities start near zero and returns become unstable;
- the contract has resolved or is close to resolution;
- the venue history is stale;
- the transformation is a research proxy rather than executable PnL.

## Tab Participation Matrix

| Source Tab | Initial Action | Default Capability | Initial Status | Notes |
| --- | --- | --- | --- | --- |
| Prediction Markets | `+ Strategy` on selected contract | `return_leg` or `overlay` | Not started | First implementation target. |
| Equity Research | Add selected ticker/scope/basket | `return_leg` | Planned | Should use existing listed-market history resolution where possible. |
| Commodities | Add selected instrument/proxy | `return_leg` or `benchmark` | Planned | Need clear proxy warnings for futures/spot/spreads. |
| Crypto | Add token or basket | `return_leg` or `benchmark` | Planned | Needs provider coverage and stale-data warnings. |
| Macro | Use regime/window as lens | `lens` | Planned | Macro objects should usually not become positions. |
| Fundamentals | Attach company case | `overlay` or `reference_only` | Planned | Ticker history may become a separate equity leg. |
| Risk | Attach scenario/stress result | `lens` or `overlay` | Planned | Useful after Strategy Lab has saved runs. |
| IV/Options | Attach vol context | `overlay` | Planned | Underlying can become an equity/ETF leg separately. |
| Copilot | Summarize or explain active handoff | `reference_only` | Planned | Copilot can later propose handoffs, but user should confirm. |

## Implementation Board

Update this board as work lands.

| ID | Work Item | Owner | Status | Validation |
| --- | --- | --- | --- | --- |
| SLH-001 | Define frontend Strategy Lab handoff types extending the existing cross-tab envelope. | TBD | Not started | Typecheck. |
| SLH-002 | Add Strategy Lab handoff queue store with add, dismiss, clear, and persistence helpers. | TBD | Not started | Store unit tests. |
| SLH-003 | Add backend request/response models for resolving handoffs. | TBD | Not started | API schema tests. |
| SLH-004 | Add `/research/strategy-lab/resolve-handoff` endpoint. | TBD | Not started | API route tests. |
| SLH-005 | Implement prediction-market resolver from selected market id to Strategy Lab draft leg. | TBD | Not started | Backend unit test with fixture history. |
| SLH-006 | Add `+ Strategy` / `Add & Open` actions to Prediction Markets detail. | TBD | Not started | Frontend view-model/component tests. |
| SLH-007 | Add Strategy Lab inbound strip and accept/review flow. | TBD | Not started | Browser flow verification. |
| SLH-008 | Convert accepted resolved handoffs into editable composer rows. | TBD | Not started | Strategy Lab view-model tests. |
| SLH-009 | Add Equity Research selected ticker/scope handoff. | TBD | Not started | Store and browser tests. |
| SLH-010 | Add Commodities selected instrument handoff. | TBD | Not started | Resolver tests with proxy warning. |
| SLH-011 | Add Macro lens handoff. | TBD | Not started | Lens attachment tests. |
| SLH-012 | Add Copilot context builder coverage for pending and resolved Strategy Lab handoffs. | TBD | Not started | Copilot context tests. |

## Inspection Workflow

Anyone resuming implementation should inspect progress in this order:

1. Read this document and update the status snapshot if code has moved.
2. Check `git status --short` and avoid overwriting unrelated work.
3. Inspect existing Strategy Lab composer code in:
   - `src/application/research_service.py`
   - `src/models/research_lab.py`
   - `src/api/routes/research.py`
   - `src/api/schemas/research.py`
   - `frontend/src/lib/stores/app.ts`
   - `frontend/src/lib/view-models/research.ts`
   - `frontend/src/views/ResearchView.svelte`
   - `frontend/src/views/StrategyLabView.svelte`
4. Inspect cross-tab envelope and navigation code in:
   - `frontend/src/lib/api/types.ts`
   - `frontend/src/App.svelte`
5. Inspect Prediction Markets selection state in:
   - `frontend/src/lib/stores/app.ts`
   - `frontend/src/views/PredictionMarketsView.svelte`
   - `src/api/routes/prediction_markets.py`
   - `src/services/prediction_market_adapters.py`
6. Implement the smallest next board item.
7. Run focused backend and frontend tests.
8. If UI changed, verify the local browser flow.
9. Update this document's status snapshot and implementation board.

## Validation Plan

Backend:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_research_v2.py tests\test_api.py -q
```

Frontend:

```powershell
npm run typecheck
npm run test -- src/lib/view-models/research.test.ts
npm run test -- src/lib/stores/app.test.ts
```

Browser:

- Open the app locally.
- Select a Prediction Markets contract.
- Click `Add & Open`.
- Confirm Strategy Lab opens.
- Confirm the inbound strip appears.
- Accept the handoff.
- Confirm the composer receives a prediction-market row.
- Run composition.
- Confirm warnings/provenance are visible and no layout overflow occurs.

## Open Questions

1. Should `+ Strategy` silently queue or immediately resolve in the source tab?
2. Should Prediction Markets default to `long_yes_probability_return` or ask the user for YES/NO side before adding?
3. Should pending handoffs persist across browser reloads, or only within the current session?
4. Should Strategy Lab save handoff bundles as named experiment drafts?
5. Should Copilot be allowed to propose handoffs automatically, or only explain user-created handoffs first?

## Recommended Next Step

Start with `SLH-001` through `SLH-008` using Prediction Markets as the first source tab. That path proves the full cross-tab workflow without spreading partial affordances across many tabs.
