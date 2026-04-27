# Copilot V2 Dedicated Tab Plan

## Roadmap Fit

Roadmap V2 Workstream 7 calls for keeping the shell shelf while adding a dedicated Copilot workspace for streaming, sessions, synthesis, planning, memos, and later voice. The dedicated tab is valid because Copilot is no longer just a drawer action: it is the cross-domain research layer that coordinates loaded Gamma context.

The product boundary stays unchanged:

- read-only internal tools only,
- no order placement, wallet signing, account modification, arbitrary code execution, or execution automation,
- source-backed claims separated from inference,
- every answer grounded in explicit Gamma context bundles and source traces.

## Information Architecture

The first dedicated tab should behave more like `SITREP` than `Macro`.

- Top-level research workspace tab: `COPILOT`.
- No mode bar in the first pass.
- Primary task: cross-context synthesis across already loaded Gamma domains.
- Secondary task: continue from the last non-Copilot active tab context.
- Context selection is a scope control, not a mode system.

This avoids a premature mode bar with artificial modes such as Chat, Memos, Sessions, and Tools before those backends exist.

## First-Pass Surface

The prepared shell should contain:

- a compact header with active grounding state, loaded context count, selected scope count, and thread turn count,
- a primary composer with `Synthesis` and `Active Tab` focus toggles,
- a thread transcript area using the existing research-card result shape,
- a support column for loaded context chips, fingerprints, freshness labels, and warnings,
- a build-order panel that makes the V2 path explicit.

The first pass reuses the existing `/copilot/research-card` endpoint and in-memory frontend thread stores. It does not introduce a new session database yet.

Implementation update:
- `COPILOT` is now a no-mode-bar research workspace tab.
- Copilot turns are persisted locally as sessions, context snapshots, and turn records.
- The dedicated tab can create saved memos from persisted session turns.
- `/copilot/research-card/stream` exposes NDJSON status, metadata, result, and done events around the provider result.

## Backend Build Order

1. Keep using `CopilotResearchCardRequest` and existing read-only tool execution for the first dedicated tab.
2. Add a streaming endpoint behind the provider boundary, probably as a sibling to `/copilot/research-card`.
3. Add persisted `CopilotSession`, `CopilotTurn`, `CopilotMemo`, and `CopilotContextSnapshot` records. `Complete first pass.`
4. Store context fingerprints and source references with each turn so a memo can be audited later. `Complete first pass.`
5. Add memo generation as a structured read-only output, not a generic document editor. `Complete first pass.`

## Frontend Build Order

1. Ship a no-mode-bar `CopilotView.svelte` in the research workspace.
2. Reuse the current cross-context synthesis scope options and thread store.
3. Keep the shelf as a quick overlay from any tab.
4. Later split the dedicated tab internally only if durable workflows emerge:
   - session history,
   - memo draft review,
   - research plan tracker,
   - source/tool trace inspector.

Those should become modules first. Add a mode bar only after at least two of them have real backend state and separate research tasks.

## Context Contract Adoption

The dedicated tab should eventually consume tab-owned `CopilotContextContract` payloads rather than loosely assembled frontend state. Adoption order:

1. Macro and Commodities, because they already have workspace-level context.
2. Research and Fundamentals, because they carry richer selected-entity state.
3. IV and Risk, because their payloads need careful warning and coverage framing.
4. SITREP as a synthesis-friendly operating-picture bundle.

## Open Implementation Risks

- Streaming must not bypass the provider boundary or tool audit trail.
- Session persistence must capture context snapshots, not just chat text.
- Synthesis can become noisy if every loaded context is selected by default forever; the UI should keep selected scope explicit.
- The dedicated tab should not duplicate every domain UI. It should summarize, cite, and hand off back to domain tabs.
