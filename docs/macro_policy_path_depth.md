# Macro Policy Path Depth Spec

## Goal

Deepen Phase 2 Macro `Rates & Policy` so it moves beyond a single front-end path proxy into a more explicit policy-expectation layer, while staying within Gamma's current read-only and public-data architecture.

This implementation is intentionally a transparent **meeting ladder proxy**, not a futures-implied policy curve. The roadmap already states that the current Macro layer is proxy-based and that `Rates & Policy` should gain richer policy-expectation depth before new modes are added.

## Scope

This change extends the existing `MacroRatesPolicySummary` payload and `Rates & Policy` UI with:

1. A structured meeting-ladder section derived from:
   - current policy rate / proxy,
   - current front-end rate proxy,
   - current schedule of upcoming policy meetings.
2. Ladder-level metrics:
   - meetings in window,
   - implied cumulative change,
   - average change per meeting,
   - projected terminal policy rate.
3. Per-meeting rows showing:
   - meeting title and date,
   - projected implied policy rate by that meeting,
   - incremental move assigned to that meeting,
   - cumulative move through that meeting.
4. UI copy that states the methodology and limitation clearly.

## Shipped State

The current implementation now includes, in addition to the original meeting-ladder proxy:

1. A policy-expectation overlay derived from linked public prediction-market contracts.
2. Compact expectation metrics covering:
   - linked contract count,
   - qualitative easier/tighter bias,
   - average contract probability,
   - average recent repricing.
3. UI framing that places the linked-contract set beside the front-end path proxy rather than treating it as a substitute for a derivatives curve.
4. Explicit caveat copy that the linked-contract layer is text-mapped and qualitative.

This means `Rates & Policy` now answers two separate but related questions:

- what the current front-end rates proxy implies about the path,
- whether linked public policy contracts are leaning the same way, the other way, or are mixed.

## Non-Goals

- No claim that the ladder is a market-implied OIS or fed-funds-futures curve.
- No new paid market-data dependency.
- No new Macro mode.
- No notebook hooks or AI Copilot work.

## Current Limitations

- The meeting ladder is still a deterministic proxy built from the current front-end gap, not an implied OIS/futures curve.
- Linked policy contracts are categorized heuristically from public titles and topics; they are a qualitative overlay, not meeting-specific pricing.
- EU coverage remains lighter than US coverage and currently depends on available public policy-calendar coverage.
- This layer should be interpreted together with the broader Macro coherence and event-study outputs, not as a standalone policy model.

## Method

### Inputs

- Policy-rate series already used by `Rates & Policy`
- Front-end rate series already used by `Rates & Policy`
- Upcoming policy meetings already exposed by the macro events adapter

### Derivation

1. Compute the existing `front rate minus policy rate` gap in basis points.
2. Select the next N policy meetings in the active region.
   - First pass target: up to 4 meetings.
3. Spread the current total gap evenly across those meetings.
4. For each meeting:
   - incremental move = total gap / meeting count
   - cumulative move = incremental move * meeting index
   - implied policy rate = current policy rate + cumulative move

### Why this method

- It uses existing normalized inputs.
- It is deterministic and easy to explain.
- It creates explicit policy-path depth without pretending to have a true derivatives curve.
- It preserves Gamma's current roadmap bias toward reusable analytics and provenance-aware transformations.

## Data Model Changes

Add:

- `MacroPolicyMeetingPathRow`
- `MacroPolicyMeetingPathSummary`

Extend `MacroRatesPolicySummary` with:

- `meeting_path: MacroPolicyMeetingPathSummary | None`

## UI Changes

Inside `Rates & Policy`, add a new `Meeting Ladder` panel below the existing `Path Proxy` block.

Panel contents:

1. Headline and summary
2. Compact metrics row
3. Table of upcoming meetings
4. Research-focus note

Copy should explicitly say the ladder:

- spreads the current front-end gap across upcoming meetings,
- is a research aid,
- should be interpreted alongside linked policy contracts and the curve.

## Region Behavior

- `US`: use Fed Funds, 2Y Treasury, and upcoming FOMC meetings.
- `EU`: use ECB policy proxy, 3M rate proxy, and policy-category events if available.
- `Global`: continue to reuse US-first coverage rules already present in Macro V1.

## Provenance

Each meeting-ladder row should carry:

- `source_provider`
- `retrieved_at`
- `origin`
- `transformation_note`

The transformation note should state that the row is a meeting-ladder proxy derived from the current front-end gap and scheduled policy meetings.

## Testing

Backend:

- snapshot contains `meeting_path`
- ladder metrics are populated
- meeting rows are ordered and cumulative values step correctly
- API serializes the new structure

Frontend:

- `Rates & Policy` renders the meeting-ladder section
- metrics and per-meeting rows appear
- research-focus copy is visible

## Follow-On Work

After this lands, the next Macro follow-on should be:

1. denser event windows,
2. better coherence / lead-lag interpretation,
3. later replacement of the proxy ladder with a richer meeting-path source if one is selected.
