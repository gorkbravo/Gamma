# Idea Workspace Spec

> **Status: approved (2026-11-14), not started.** Roadmap [Workstream 12 - Ideas](../roadmap.md#workstream-12---ideas); listed in [`docs/README.md`](./README.md). The product owner settled the seven open decisions on 2026-11-14 (see [Decisions](#decisions)). Nothing here is implemented yet.

## Goal

Give Gamma one object that turns thirteen surfaces into one research workflow: the **Idea**. An Idea is a written thesis that collects evidence from any tab, states in advance what would prove it wrong, can be tested and risk-checked, and is then tracked forward and reviewed — without Gamma ever executing anything.

The same object serves two audiences at different depths:

- **Retail investors:** write a thesis, pin evidence, set plain criteria ("tell me if Brent closes below 85"), read the risk in plain language, keep a journal and learn from closed ideas.
- **Sophisticated retail and quants:** attach a signal (a Script or an imported series), validate it out of sample, check the book in Risk, and get an honest forward track record that cannot be overfit after the fact.

Every audience works with the same numbers and the same provenance. Explanations are added on demand for the first group, and the full parameters stay visible for the second. Nothing is simplified away.

## Why now

- The 2026-11-05 live audit scored data breadth 7 and analytical tooling 7, while cross-tab continuity, speed to insight and Copilot scored 6. Gamma's gap is the workflow that connects its parts, not more domains.
- Pieces already exist but do not connect: Sitrep follow-ups (`SitrepFollowUp`), the `/research/saved` store, Prediction Markets watchlists and comparison sets, Copilot memos and working analyses, Strategy Lab compositions and Script runs, Risk stress replays. Each keeps its own fragment of a thesis.
- Roadmap principles this serves: "Research, not just monitoring" (what changed, what would disconfirm it), "Cross-tab handoffs should become first-class", "Copilot must remain grounded", and Saved Research ("not a full notebook initially… a structured saved-research layer").

## Product boundary

Unchanged and restated, because an Idea comes closest to "strategy" of anything in Gamma:

- **No execution:** no orders, staging, broker alerts, rebalancing or automated deployment. Forward tracking is hypothetical and labelled as such everywhere it appears.
- **Read-only evaluation:** criteria evaluate only through existing read-only services and adapters. An idea never acquires broker, account, wallet or order authority.
- **Local only:** ideas live on the user's machine. Nothing is sent anywhere, except to Copilot's model when the user explicitly selects the Ideas context.
- **Not advice:** Gamma does not rate ideas as buy or sell, and has no "Gamma conviction score". Statistics describe the user's own record.

## Personas and jobs

| Job | Retail | Sophisticated retail / quant |
| --- | --- | --- |
| Capture | "I think X because Y", the instruments, a horizon | The same, with signed legs and weights |
| Gather evidence | Pin a panel from any tab | Pin series, Script outputs and backtests |
| Say what would prove it wrong | Plain thresholds and dates | Machine-checkable rules on any observable, or a signal |
| Test | Composer backtest with defaults | Walk-forward, sweeps, out-of-sample, costs |
| Check risk | VaR, the worst replayed episode, plain-language summary | Per-leg contribution, episodes, correlations |
| Watch | Notification when a criterion triggers | The same, plus signal state and forward P&L |
| Learn | Journal; what happened versus what I expected | Expected versus realized, signal decay, trial count |

Acceptance for the workstream (see Checkpoints) is a persona audit per column, run like the usability audit but with fixed tasks.

**Reference retail user (decision 7):** an investor with **any broker** and no TWS session. Everything an Idea needs for that user must work from public or keyed providers: equities and ETFs through the research market data path, macro, prediction markets and crypto. IBKR-backed observables (options IV, futures curves, the live account) are enhancements when TWS is connected, never the default path or a requirement of a checkpoint's retail acceptance.

## Domain model

All records are frozen dataclasses in `src/models/ideas.py`, carry `schema_version`, and reuse `HandoffEntity`, `CrossTabHandoffEnvelope` and `ProvenanceRecord` from `src/models/handoff.py` and `src/models/provenance.py`.

### `Idea`

| Field | Notes |
| --- | --- |
| `idea_id`, `schema_version` | Stable id; version for migration |
| `title`, `thesis` | One-line thesis, required |
| `notes` | Markdown body, optional |
| `stance` | `long`, `short`, `relative`, `event`, `neutral` |
| `legs` | `HandoffEntity` plus an optional signed weight; empty for a pure event idea |
| `horizon` | Review date or holding window; drives the review prompt |
| `status` | See Lifecycle |
| `origin` | `manual`, `sitrep_follow_up`, `copilot`, `handoff`, `import`, with a source reference |
| `tags`, `created_at`, `updated_at`, `closed_at` | |

### `IdeaEvidence` (a pin)

A frozen snapshot of something the user saw, with its provenance at capture time. It does not live-update. The UI may show a "now" value beside it when the source can be resolved again ("then 78% · now 64%").

| Field | Notes |
| --- | --- |
| `evidence_id`, `idea_id` | |
| `kind` | `metric`, `series`, `table`, `filing`, `news`, `prediction_contract`, `research_card`, `script_output`, `backtest`, `risk_result`, `note` |
| `stance` | `supports`, `challenges`, `context` — the user's tag, required, so disconfirming evidence is first-class |
| `captured_values` | The exact values shown (bounded size; series downsampled with the method recorded) |
| `provenance`, `freshness` | `ProvenanceRecord` and `FreshnessRecord` as they were at capture |
| `reopen` | `CrossTabHandoffEnvelope` to reopen the source tab and mode on the same entity and lens |
| `captured_at`, `note` | |

### `IdeaCriterion`

A rule stated before the outcome is known. Kinds: `invalidate` (the thesis is wrong if this happens), `confirm` (the thesis is playing out), `review` (look again; for example a date or an event).

| Field | Notes |
| --- | --- |
| `criterion_id`, `kind`, `label` | The label is plain language and generated from the rule, editable |
| `observable` | A reference into the observable registry (below) |
| `condition` | `above`, `below`, `crosses_above`, `crosses_below`, `change_over_window`, `date_reached`, `event_occurs` |
| `threshold`, `window` | |
| `cadence` | `on_open` (evaluate when Gamma starts and when the idea is opened), `daily_close`, `intraday` (IBKR marks while TWS is connected and Gamma runs; falls back to `daily_close` otherwise, and says so) |
| `state` | `pending`, `holding`, `triggered`, `unavailable`, `stale` |
| `last_evaluation` | Value, evaluated_at, provenance; `unavailable` is never shown as `holding` |
| `triggered_at`, `acknowledged_at` | |

**Observable registry (v1)**, built only on existing read paths:

| Observable | Source in Gamma | Needs TWS |
| --- | --- | --- |
| Equity / ETF close and change | Research market data (yfinance, then IBKR) | No |
| Macro series value and change | `/macro/series/{id}/history` (FRED, Treasury) | No (IBKR FX pairs do) |
| Prediction contract probability | Prediction Markets detail and history | No |
| Commodity front or curve point, spread | Commodities service | Yes for IBKR futures; EIA/FRED otherwise |
| ATM IV, skew | Options IV snapshot | Yes |
| Crypto price and change | CoinGecko | No |
| Script signal state | Latest accepted Script run output | No |
| Date / scheduled event | Macro calendar | No |

An observable declares its dependencies. When one is missing (TWS closed, no key, provider failure), the criterion is `unavailable` with the reason, never silently `holding`.

The registry orders observables for the reference retail user: the ones that need no TWS come first in pickers and in Copilot's proposals. A TWS-only observable is offered with its dependency visible ("needs Trader Workstation").

### `IdeaSignal` (optional, the quant layer)

| Field | Notes |
| --- | --- |
| `signal_source` | `script` (script id, accepted revision, parameter hash, run id) or `import` (CSV of positions, weights or returns, validated like Strategy Lab imports) |
| `output_kind` | `positions`, `weights`, `returns` |
| `validation` | Snapshots of the walk-forward and out-of-sample results from E5 sweeps, with their windows |
| `trial_count` | Number of Script runs and sweep points attached to this idea before the current signal. It is shown next to every performance statistic |
| `cost_model` | Explicit cost and slippage assumptions per leg, from the per-asset-class defaults below; always shown, editable, never zero by default |

**Default cost model (decision 5):** costs are per side, set by asset class, and shown wherever a return appears. The values below are **starting assumptions**, not measured figures. They should be checked against current broker and venue fee schedules before I3 ships.

| Asset class | Default per side | Basis |
| --- | --- | --- |
| Liquid US equities and ETFs (index members) | 5 bp | Commission plus half a typical spread |
| Other equities and ETFs (small caps, non-US, UCITS) | 10 bp | Wider spreads, FX and venue fees |
| Futures | 3 bp of notional | Half a tick plus commission on liquid contracts |
| Options | Half the quoted bid-ask at the mark | Taken from the chain; marked unavailable without a quote |
| Spot crypto | 25 bp | Taker fee plus spread |
| Prediction market contracts | Half the quoted spread, plus the venue fee where the venue charges one | Taken from the book |
| Macro series and other non-tradable observables | None | They are criteria, not legs |

### `IdeaTest` and `IdeaRisk`

Frozen snapshots of a Strategy Lab composition or backtest result and of a Risk result (VaR/ES, stress replay, contributions). Each keeps its source ids, window and provenance. They are recomputed only when the user asks; a stale snapshot shows its date.

### `IdeaTracking` (forward tracking)

The honest track record. Activation freezes the legs and weights (or the signal) and starts a **hypothetical** book from the next available close.

Two resolutions (decision 4): IBKR marks while TWS is connected, daily closes otherwise.

- **Canonical daily series:** one end-of-day mark per session, from the same providers as Strategy Lab. It is rebuilt from provider closes, so it has no holes when Gamma or TWS was closed. Return, drawdown, the benchmark and the costs from the cost model are computed on this series, and only on this series, so every idea is comparable.
- **Intraday layer while TWS is connected:** Gamma records IBKR marks for the legs at the tracking cadence while TWS is connected and Gamma runs. The layer feeds today's live P&L, the intraday drawdown and intraday criterion triggers. Delayed IBKR quotes are labelled delayed. Where Gamma or TWS was closed, the layer shows an explicit gap. It never replaces or rewrites the canonical daily mark.
- **No backfill:** nothing before activation is ever added. Editing the legs or the signal closes the current segment and opens a new one; every segment stays visible, with the reason for the change.
- **Gaps stay gaps:** a missing price leaves a gap with a warning, never an interpolation.
- **Labelling:** the series is always labelled "Hypothetical, not executed" in the UI and in exports.

### `IdeaJournalEntry`

Append-only, timestamped entries. The system writes entries for activation, criterion triggers, test or risk refreshes, segment changes and closing; the user writes notes and decisions. Corrections are new entries, not edits.

### `IdeaReview`

Written at close: an `outcome` (`confirmed`, `invalidated`, `abandoned`, `expired`), what was expected versus what was realized (from tracking), which evidence held up, and a free-text lesson. Closed ideas feed the review statistics.

## Lifecycle

`draft` → `active` → `closed` → (`archived`)

- **draft:** thesis and evidence only; no tracking.
- **active:** criteria are evaluated, and forward tracking runs when the idea has legs or a signal.
- **closed:** needs an outcome and a review; tracking stops at the close date.
- **archived:** hidden from the board, kept for review statistics.

Reopening a closed idea creates a new active segment and a journal entry, so the record of the original close stays.

## Surfaces

Per "Modes over tab sprawl", an Idea justifies a Research tab: it has a distinct data model, a distinct workflow and relationships with every other tab.

**Ideas tab** (Research workspace, after Sitrep), three modes:

1. **Board:** every active idea in one dense table. Columns: thesis, stance, legs, criterion states (`triggered` first), forward return since activation, days to review, last evidence. Filters by status and tag.
2. **Idea:** the detail view, in sections:
   - thesis and stance;
   - evidence, split into supports, challenges and context;
   - criteria with their live state;
   - test and risk snapshots;
   - signal and validation (collapsed by default);
   - tracking chart (hypothetical, with segments);
   - journal.
3. **Review:** closed ideas. Shows the outcome mix, expected versus realized, how often invalidation criteria fired before the loss, and holding-time statistics. It describes the user's own record only; there is no score.

**Entry points elsewhere** (one shared component, not a per-view copy):

- **Pin to idea:** a panel-title action on every panel that has a Copilot context contract or a provenance badge. It opens a small picker to choose an idea or create one, and the stance.
- **Sitrep:** a follow-up gets "Promote to idea"; a "Your ideas" section lists triggered criteria and reviews due. This replaces the need for a separate alert list.
- **Copilot:** "Draft an idea from this card" (see Copilot).
- **Strategy Lab and Risk:** "Attach to idea" on composition, backtest and replay results.

**Notifications (decision 3):** in-app only for this workstream. A notification center in the top bar lists criterion triggers and reviews due, each linking to the idea, and Sitrep shows the same items under "Your ideas". Native desktop notifications through the Tauri shell are a later follow-up. Off-machine channels (email, phone push) are out of scope, because they would send data off the user's machine.

**Limitation stated in the UI:** evaluation runs only while Gamma runs. On start, Gamma evaluates every `on_open` and `daily_close` criterion and shows "while you were away" triggers with the time each condition was first met, when the history allows it.

## Explanations on demand

Every observable and every statistic shown in an idea has a "What is this?" popover with three parts:

- **What it measures:** one sentence.
- **Why it matters for this kind of idea:** one sentence per stance.
- **How Gamma computes it:** a link to the transformation note and the provenance.

This sits behind an icon, not in static text, so it does not break the doctrine against interpretive notes (`design_principles.md`). The texts live in one registry so the Ideas tab, panels and Copilot share them.

## Copilot

An Ideas context builder follows the Copilot context contract. It covers the selected idea's thesis, evidence (with stance and provenance), criteria and their states, test and risk snapshots, tracking summary and journal tail, and the review statistics when asked.

Proposed tools; scope them with the Copilot plan before implementation:

- `draft_idea_from_context`: proposes a thesis, legs and two to four criteria from the current card or tab. The proposal is a draft the user must accept, a local state change under the existing confirmation flow.
- `review_idea`: compares the expected path with the realized one and lists the evidence that held or failed. Read-only.
- `explain_criterion_state`: why a criterion is holding, triggered or unavailable. Read-only.

Before implementation, AGENTS.md applies: read `docs/copilot_v2_tab_plan.md` and re-check the current official OpenAI guidance, then record the decision there. Copilot never activates, closes or edits criteria without the user's confirmation, and never gains execution authority.

## Quant bridge (read-only client)

Sophisticated users want their own Python, libraries and notebooks. Gamma should not run arbitrary local code; the Research Script runtime stays isolated and has no network. The bridge is the other direction:

- **A small read-only Python client** over the existing local API, authenticated with the session token. It lists ideas and observables and reads normalized histories with their provenance.
- **One write path:** importing a signal or a return stream into an idea, validated exactly like Strategy Lab CSV imports. That path is data import, not execution.
- **Local only:** the client runs on the user's machine, under their control. Gamma never invokes it.

**Decision 6:** the client lives in this repository under `clients/python/`, versioned with the API it reads, and is built after I4, once ideas carry signals.

The problem it solves: a user who programs wants to test strategies in their own Python (pandas, their libraries, Jupyter). Today they have two paths. Script runs in an isolated OpenAI container with no network, few libraries and per-run cost. The other is exporting and importing CSV by hand. The local API already serves the data, but using it directly means handling the session token, the endpoints and raw JSON.

Intended shape, to be settled in its own checkpoint:

```python
g = Gamma()                          # local API, session token from the environment
df = g.history("SPY")                # DataFrame with provenance columns
g.ideas.attach_signal(idea_id, df)   # validated like a Strategy Lab import
```

## Rigor guardrails

These apply to every audience; they are what make the forward record trustworthy:

- **Evidence is frozen at capture**, and criteria evaluate only on data available at evaluation time; there is no look-ahead.
- **Forward tracking never backfills**, and every edit is a visible new segment.
- **Next to every performance figure:** the out-of-sample split, the trial count and the cost model. A backtest without costs is labelled as such.
- **Data caveats are inherited, not hidden:** yfinance is unofficial, there are no point-in-time fundamentals, and survivorship applies to the index proxies.
- **Absence is a state:** unavailable observables, stale snapshots and partial tracking are labelled, never filled in.

## Persistence and API

- **Store:** `IdeaStore` in `src/services/idea_store.py`. It keeps local JSON under `data/ideas/`, one file per idea plus an index, and follows the existing stores: atomic replace, schema validation, quarantine of corrupt files, migration by `schema_version`. Evidence values are bounded in size.
- **Export:** an idea exports to Markdown with provenance, like Copilot memo export. A JSON export makes ideas portable between machines.

Routes (prefix `/ideas`):

| Method and path | Purpose |
| --- | --- |
| `GET /ideas`, `POST /ideas` | List with filters; create |
| `GET/PATCH/DELETE /ideas/{id}` | Read, edit (journaled), delete (confirmed in the UI) |
| `POST /ideas/{id}/evidence`, `DELETE …/evidence/{eid}` | Pin and unpin |
| `POST/PATCH/DELETE /ideas/{id}/criteria[/{cid}]` | Manage criteria |
| `POST /ideas/{id}/evaluate`, `POST /ideas/evaluate` | Evaluate one or all now |
| `POST /ideas/{id}/activate`, `/close`, `/reopen` | Lifecycle (close requires a review) |
| `GET /ideas/{id}/tracking` | Hypothetical forward series and segments |
| `POST /ideas/{id}/signal` | Attach a Script run or an imported series |
| `GET /ideas/observables` | Registry with dependencies and availability |
| `GET /ideas/notifications` | Pending triggers and reviews |
| `GET /ideas/{id}/export?format=md\|json` | Export |

## Relationship with what exists

| Existing piece | What happens |
| --- | --- |
| Sitrep follow-ups | Stay as quick stars. "Promote to idea" carries the handoff and note across. No forced migration |
| `/research/saved` items | Can be attached as evidence. The store stays for Scope Analysis and Strategy Lab reuse |
| Prediction Markets watchlists and comparison sets | Stay; they are lists, not theses. A contract can be pinned as evidence or used as an observable |
| Copilot memos and research cards | Can be attached as evidence; a card can seed a draft idea |
| Copilot working analyses | Stay session-ephemeral; materializing one into an idea requires the user's confirmation |
| Strategy Lab compositions, Script runs, sweeps | Attached by id with frozen result snapshots; they remain owned by Strategy Lab |
| Risk research books and replays | Attached as `IdeaRisk` snapshots; "Open in Risk" from the idea uses the existing handoff |

## Checkpoints

Each checkpoint lands on its own branch with tests, a browser review in both themes at 1440, 1000 and 390, and the B′ doctrine (`design_principles.md`, the gamma-ui skill).

| Checkpoint | Scope | Acceptance |
| --- | --- | --- |
| I1: core object | `Idea`, `IdeaEvidence`, `IdeaJournalEntry`, store, routes, Ideas tab (Board and Idea), Pin to idea on the panels that have a provenance badge, Sitrep promote, Markdown and JSON export | Create, pin from five different tabs, reopen each pin in its source tab on the same entity; store survives a restart and a corrupt file |
| I2: criteria and notifications | `IdeaCriterion`, observable registry v1, evaluation on start, open and daily close, notification center, Sitrep "Your ideas", "What is this?" registry | Every observable evaluates live, or is `unavailable` with its reason when TWS or a key is missing; a trigger reaches the notification center and Sitrep |
| I3: test, risk, tracking | `IdeaTest`, `IdeaRisk`, `IdeaTracking` with segments, the canonical daily series and the TWS intraday layer, the per-asset-class cost model, close and review, Review mode | A legs idea tracks for five trading days with no backfill and no TWS; with TWS, the intraday layer records and shows its gaps without changing the daily series; an edit opens a new segment; close requires a review |
| I4: quant layer | `IdeaSignal` from Script runs and CSV import, validation snapshots, trial count, signal-driven tracking | A Script signal attaches with its out-of-sample result and trial count; tracking follows the signal's positions; costs are visible |
| I4b: Python client | Read-only client in `clients/python/`: histories with provenance, ideas, observables, and signal import into an idea | From a notebook: read a history, attach a signal to an idea, and see it validated in Gamma exactly as a CSV import; no route the client uses can place, stage or route anything |
| I5: Copilot | Ideas context builder, draft, review and explain tools | Copilot plan updated with a dated OpenAI guidance review; draft-from-card needs user acceptance; no execution authority |
| I6: persona audits | Retail audit without TWS and quant audit, each with fixed tasks | No P0/P1 finding in either; each scores at least 8 on cross-tab workflow and speed to insight |

## Non-goals

- Orders, execution, broker-side alerts, paper trading through the broker, automatic deployment.
- Cloud sync, sharing, social features, leaderboards.
- Tick-level alerting, intraday alerting without TWS, and alerts while Gamma is closed.
- A Gamma conviction or quality score for ideas.
- Unrestricted local code execution inside Gamma.

## Decisions

Settled by the product owner on 2026-11-14:

| # | Question | Decision | Where it lands in this spec |
| --- | --- | --- | --- |
| 1 | Name | **Ideas** | Throughout |
| 2 | Place | A **Research tab** after Sitrep (Board, Idea, Review); "Pin to idea" works from every panel | Surfaces |
| 3 | Notifications | **In-app only**: notification center and Sitrep "Your ideas"; Tauri desktop notifications later; no off-machine channels | Surfaces |
| 4 | Tracking resolution | **IBKR marks while TWS is connected, daily closes otherwise**: a canonical daily series for all statistics, plus an intraday layer recorded only while TWS is connected | `IdeaTracking`, I3 |
| 5 | Default costs | **Per asset class**, shown and editable; values are starting assumptions to check against fee schedules before I3 | `IdeaSignal`, I3 |
| 6 | Python client | **In this repo (`clients/python/`), after I4** | Quant bridge, I4b |
| 7 | Reference retail user | **Any broker, no TWS**: the default path needs no IBKR; IBKR observables are enhancements | Personas, observable registry, I6 |

Still to settle during implementation: the exact cost values (decision 5) and the client's API shape (I4b).
