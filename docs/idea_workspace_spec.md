# Idea Workspace Spec

> **Status: approved (2026-11-14); I1 and I2 merged into main on 2026-11-21 after a code review (see [Review before merge](#review-before-merge-2026-11-21)); I3a-I3d merged into main on 2026-11-22 (merge commit 8aafa1f).** Roadmap [Workstream 12 - Ideas](../roadmap.md#workstream-12---ideas); listed in [`docs/README.md`](./README.md). The product owner settled the seven open decisions on 2026-11-14 (see [Decisions](#decisions)) and split I3 into I3a-I3d on 2026-11-21. I3a (forward tracking), I3b (close and review), I3c (test and risk snapshots) and I3d (the TWS intraday layer) were built on stacked branches `claude/laughing-gauss-4b5d02`, `claude/ideas-i3b-close-review`, `claude/ideas-i3c-test-risk` and `claude/ideas-i3d-intraday-579806` and merged into main together on 2026-11-22 (see the [I3a](#i3a-implementation-notes), [I3b](#i3b-implementation-notes), [I3c](#i3c-implementation-notes) and [I3d](#i3d-implementation-notes) notes, and the [live check](#live-check-2026-11-21)). I4 was split on 2026-11-23 (see [I4 design decisions](#i4-design-decisions)); I4a was built on branch `claude/ideas-i4-quant` and merged into main on 2026-11-23 (merge commit 57553e4; see [I4a implementation notes](#i4a-implementation-notes)). I4b (the Python client) and I4c (attach from results) were built on branch `claude/ideas-i4bc` and merged into main on 2026-11-23 (merge commit ddafbeb; see [I4b and I4c design decisions](#i4b-and-i4c-design-decisions)). I5 (Copilot) was built on branch `claude/ideas-i5` and merged into main on 2026-11-23 (merge commit f1c6ddd; see [I5 design decisions](#i5-design-decisions)). I6 is not started.

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

**Default cost model (decision 5):** costs are per side, set by asset class, and shown wherever a return appears. The defaults were checked on **2026-11-21** against the official broker, venue and tax pages listed below. They remain **assumptions**: a fee schedule gives the commission and the fees, but the half spread is an estimate, and every user's broker differs. Two starting values were raised after the check: other equities from 10 to 15 bp, and spot crypto from 25 to 50 bp.

| Asset class | Default per side | Basis (checked 2026-11-21) |
| --- | --- | --- |
| Liquid US equities and ETFs (index members) | 5 bp | Commission $0 online at Schwab [2] and Fidelity [3] and at IBKR Lite; IBKR Pro Fixed $0.005 per share, $1 minimum, 1% maximum (about 1-2 bp on a typical order) [1]. SEC Section 31 fee $20.60 per million of sales since 2026-04-04 (0.21 bp, sales only) [4]. FINRA TAF $0 from 2026-10-01 to 2026-12-31 [5], otherwise $0.000195 per share sold, at most $9.79 per trade [6]. **Assumption:** half spread of 1-3 bp for index members; 5 bp is a conservative sum |
| Other equities and ETFs (small caps, non-US, UCITS) | 15 bp | IBKR Europe 0.05% per order (5 bp) with a EUR 3 minimum (Fixed) [1]. **Assumption:** half spread of about 10 bp for small caps, non-US listings and UCITS ETFs. **Not included:** buy-side taxes, which a user can add by raising the class cost: UK stamp duty or SDRT 0.5% [7], French TTF 0.4% since 2025-04-01 [8], Spanish ITF 0.2% on companies above EUR 1,000 M [9], Italian FTT 0.4% (0.2% on regulated markets and MTFs) [10] |
| Futures | 3 bp of notional | IBKR $0.85 per E-mini contract; its ES example totals $2.24 with exchange and regulatory fees, Micro E-mini $0.25 plus fees [11]. ES is $50 × the index with a 0.25-point tick worth $12.50 [12]. **Assumption:** at an index level near 6,000 that is about 0.3 bp per side for ES; 3 bp is kept to cover less liquid contracts. Not priced in I3a |
| Options | Half the quoted bid-ask at the mark | Taken from the chain; marked unavailable without a quote. Commission at IBKR Pro $0.65 per contract (premium of $0.10 or more), $1 minimum per order [13]; $0.65 at Schwab and Fidelity [2][3]. Not priced in I3a |
| Spot crypto | 50 bp | Entry-tier taker fees: Coinbase Advanced 0.50% in the EU and UK and 0.90% in the US [14]; Kraken Pro 0.80% [15]; Binance 0.10%, not available to US residents [16]. **Assumption:** market orders at an EU/UK entry tier; a US or Kraken user pays more and a Binance user less |
| Prediction market contracts | Half the quoted spread, plus the venue fee where the venue charges one | Taken from the book. Polymarket charges takers C × rate × p × (1 − p) with a rate of 0.05 or 0.01 by category, makers nothing, geopolitics exempt [17]. **Kalshi not verified:** its fee schedule page refused connections; its help page confirms maker fees on some markets but not the formula [18]. Not priced in I3a |
| Macro series and other non-tradable observables | None | They are criteria, not legs |

Sources, all read on 2026-11-21:

1. IBKR stock commissions: <https://www.interactivebrokers.com/en/pricing/commissions-stocks.php>
2. Charles Schwab pricing: <https://www.schwab.com/pricing>
3. Fidelity commissions: <https://www.fidelity.com/trading/commissions-margin-rates>
4. SEC Fee Rate Advisory 2026-2 (issued 2026-02-27): <https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2>
5. FINRA billing FAQ (TAF suspension): <https://www.finra.org/rules-guidance/guidance/faqs/finra-billingcollections>
6. FINRA fee adjustment schedule (SR-FINRA-2024-019): <https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule>. FINRA's rulebook page still shows the older $0.000166 and $8.30.
7. GOV.UK, tax when you buy shares: <https://www.gov.uk/tax-buy-shares>
8. BOFiP, French TTF at 0.4% (ACTU-2025-00034): <https://bofip.impots.gouv.fr/bofip/14605-PGP.html/ACTU-2025-00034>
9. BOE, Ley 5/2020 (Impuesto sobre las Transacciones Financieras), art. 7: <https://www.boe.es/buscar/act.php?id=BOE-A-2020-12356>
10. Agenzia delle Entrate, imposta sulle transazioni finanziarie: <https://www.agenziaentrate.gov.it/portale/schede/pagamenti/imposta-sulle-transazioni-finanziarie/infogen-imposta-transazioni-finanziarie>
11. IBKR futures commissions: <https://www.interactivebrokers.com/en/pricing/commissions-futures.php>
12. CME Group, E-mini S&P 500 contract specs: <https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.contractSpecs.html>
13. IBKR options commissions: <https://www.interactivebrokers.com/en/pricing/commissions-options.php>
14. Coinbase Advanced fee tiers: <https://www.coinbase.com/advanced-vip> and the 2026-09-16 announcement <https://www.coinbase.com/blog/were-lowering-fees-for-many-active-traders-on-coinbase-advanced> (the signed-in fee page was not read)
15. Kraken Pro fees: <https://www.kraken.com/pro/fees>
16. Binance fee schedule: <https://www.binance.com/en/fee/schedule>
17. Polymarket trading fees: <https://docs.polymarket.com/trading/fees>
18. Kalshi help, fees: <https://help.kalshi.com/trading/fees> (the fee schedule at kalshi.com could not be read)

Fee schedules change; check these pages again before relying on a default. The figures are for research costs on a hypothetical book, not advice.

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
| I1: core object | `Idea`, `IdeaEvidence`, `IdeaJournalEntry`, store, routes, Ideas tab (Board and Idea), Pin to idea on the panels that have a provenance badge, Sitrep promote, Markdown and JSON export | Create, pin from five different tabs, reopen each pin in its source tab on the same entity; store survives a restart and a corrupt file. **Status: I1 done, merged 2026-11-21** (see [I1 implementation notes](#i1-implementation-notes)) |
| I2: criteria and notifications | `IdeaCriterion`, observable registry v1, evaluation on start, open and daily close, notification center, Sitrep "Your ideas", "What is this?" registry | Every observable evaluates live, or is `unavailable` with its reason when TWS or a key is missing; a trigger reaches the notification center and Sitrep. **Status: I2 done, merged 2026-11-21** (see [I2 implementation notes](#i2-implementation-notes)) |
| I3: test, risk, tracking | `IdeaTest`, `IdeaRisk`, `IdeaTracking` with segments, the canonical daily series and the TWS intraday layer, the per-asset-class cost model, close and review, Review mode | A legs idea tracks for five trading days with no backfill and no TWS; with TWS, the intraday layer records and shows its gaps without changing the daily series; an edit opens a new segment; close requires a review. Split on 2026-11-21 into the four slices below. **Status: done, merged 2026-11-22** |
| I3a: forward tracking | `IdeaTracking` with segments, the canonical daily series, the per-asset-class cost model, `GET`/`PATCH /ideas/{id}/tracking`, the tracking chart in the Idea view, the Board column | A legs idea tracks for five trading days with no backfill and no TWS; an edit opens a new segment; gaps stay gaps; costs are applied and shown. **Status: done, merged 2026-11-22** (see [I3a implementation notes](#i3a-implementation-notes)) |
| I3b: close and review | Close with `IdeaReview`, reopen as a new segment, Review mode | Close requires a review; tracking stops at the close date. **Status: done, merged 2026-11-22** (see [I3b implementation notes](#i3b-implementation-notes)) |
| I3c: test and risk snapshots | `IdeaTest`, `IdeaRisk` | Snapshots keep their source ids, window and provenance and show their date when stale. **Status: done, merged 2026-11-22** (see [I3c implementation notes](#i3c-implementation-notes)) |
| I3d: TWS intraday layer | IBKR marks for the legs while TWS is connected | With TWS, the intraday layer records and shows its gaps without changing the daily series. **Status: done, merged 2026-11-22; checked live against TWS over a weekend and re-checked on a weekday session on 2026-11-24, with four defects fixed on `claude/ideas-closeout`** (see [I3d implementation notes](#i3d-implementation-notes), [Live check, 2026-11-21](#live-check-2026-11-21) and [Live check, 2026-11-24](#live-check-2026-11-24-weekday)) |
| I4: quant layer | `IdeaSignal` from Script runs and CSV import, validation snapshots, trial count, signal-driven tracking | A Script signal attaches with its out-of-sample result and trial count; tracking follows the signal's positions; costs are visible. Split on 2026-11-23 into I4a and I4c (see [I4 design decisions](#i4-design-decisions)) |
| I4a: signals | `IdeaSignal` (Script runs and CSV imports), E5 walk-forward validation snapshots, the trial ledger and `trial_count` beside every performance figure, per-leg costs, schema v6, `POST`/`DELETE /ideas/{id}/signal`, signal-driven tracking with rebalancing costs | The I4 acceptance above. **Status: done, merged 2026-11-23** (see [I4a implementation notes](#i4a-implementation-notes)) |
| I4c: attach from results | "Attach to idea" on Strategy Lab composition, backtest and Script results and on Risk replays, through the shared picker | A result attaches from its own tab with the same validation and trial count as from the Idea view. **Status: done, merged 2026-11-23** (see [I4c implementation notes](#i4c-implementation-notes)) |
| I4b: Python client | Read-only client in `clients/python/`: histories with provenance, ideas, observables, and signal import into an idea | From a notebook: read a history, attach a signal to an idea, and see it validated in Gamma exactly as a CSV import; no route the client uses can place, stage or route anything. **Status: done, merged 2026-11-23** (see [I4b implementation notes](#i4b-implementation-notes)) |
| I5: Copilot | Ideas context builder, draft, review and explain tools | Copilot plan updated with a dated OpenAI guidance review; draft-from-card needs user acceptance; no execution authority. **Status: done, merged 2026-11-23; live model acceptance run on 2026-11-24: drafting, validation, the proposal card and drafting from another context met; the review path answered from context without calling the read-only tools, an open decision** (see [I5 implementation notes](#i5-implementation-notes) and [I5 live acceptance](#i5-live-acceptance-2026-11-24)) |
| I6: persona audits | Retail audit without TWS and quant audit, each with fixed tasks | No P0/P1 finding in either; each scores at least 8 on cross-tab workflow and speed to insight. **Status: run on 2026-11-24 on `claude/ideas-closeout`: retail accepted (one P0 fixed; 8 and 8); quant not accepted (Script runs on the configured runtime never complete, one open P0; 8 and 7). 2026-11-25: P0 diagnosed (the model makes an inspection call before the verbatim wrapper); fix on `claude/script-runtime-completion`, live verification pending** (see [I6 persona audits](#i6-persona-audits-2026-11-24)) |

### I1 implementation notes

Recorded 2026-11-14 for review; merged into main on 2026-11-21.

- **Model:** `src/models/ideas.py`. `title` is required; `thesis` may be empty while the idea is a draft, and activation requires it. Evidence `stance` is required. `captured_values` are deep-frozen, JSON-strict and bounded (24 KiB, nesting depth 5, 500 items per list or object, 2,000 characters per string); a `series` longer than 260 points is downsampled at a uniform stride that keeps both ends, and the method is stored beside it. The journal is append-only and the store refuses any write that edits or drops an entry.
- **Lifecycle in I1:** `draft` -> `active` -> `archived`, plus restore (back to the status the idea had when archived) and delete (the file moves to `data/ideas/trash/`). `closed` and `closed_at` are valid stored values reserved for I3; no I1 route reaches them.
- **Store:** `data/ideas/items/<id>.json` plus `index.json`. The index is reused at start only when it matches every item file's size and mtime; otherwise it is rebuilt from the files. Corrupt, invalid and unsupported files move to `quarantine/` and appear as storage warnings on the Board; a file from a newer schema is left untouched.
- **Routes:** the I1 subset of the table above, plus `POST /ideas/{id}/journal` (user notes and decisions), `POST /ideas/{id}/archive` and `POST /ideas/{id}/restore`. Every edit, pin, unpin and status change writes a system journal entry.
- **Pin to idea** (`frontend/src/components/PinToIdea.svelte`, one shared component) is wired on Sitrep (the four market tables), Equity Research (Scope Analysis), Fundamentals (Price and Valuation), Options (the surface header), Prediction Markets (the contract panel) and Commodities (the selected market). Each pin freezes the shared provenance badge the panel shows; Fundamentals, Prediction Markets, Commodities and the Equity Research scope panel gained the shared badge (dot variant) in their title rows so the pin and the panel show the same provenance. Reopen goes through the existing cross-tab handoff path in `App.svelte` (`openHandoffEnvelope`), shared with Copilot source links. A synthetic Equity Research basket reopens the Scope mode without its weights.
- **Sitrep promote** creates an idea with the follow-up's title, note and handoff (`origin.kind = sitrep_follow_up`); the follow-up stays, and its row then offers "open" instead of a second promote.
- **Fundamentals** needs an SEC identity even in mock mode (its adapter is live). With the developer identity configured, its pin and reopen were verified in the browser on 2026-11-14. The Price and Valuation panel mixes SEC figures with the price-context source; the pin carries the panel's badge provenance (the price context), not per-figure sources.

### I2 implementation notes

Recorded 2026-11-15 for review and updated on 2026-11-16 after the live FRED check. Branch `claude/ideas-i2-c55f00`, stacked on the I1 branch; neither is merged.

- **Model (schema v2):** `IdeaCriterion` in `src/models/ideas.py` with `kind`, a plain-language `label` (generated from the rule when left blank, editable), an `ObservableRef`, `condition`, `threshold`, `window` (`1d`, `5d`, `1m`, `3m`, `6m`, `1y`), `cadence`, `armed_at`, a baseline (`baseline_as_of`, `baseline_for`), `last_evaluation`, and, once triggered, `triggered_at` plus `trigger_evaluation` (the observation that met the rule, the date it was first met and its provenance). A trigger latches until the rule is edited. Editing the rule re-arms it from now and starts again; a label-only edit keeps the state. An idea holds at most 12 criteria. Version 1 idea files migrate on load (`migrate_idea_v1_to_v2`), so an older build skips a v2 file instead of dropping its criteria.
- **Evaluation** (`src/application/idea_evaluation.py`, pure rules in `idea_criteria.py`):
  - Only `active` ideas are evaluated. Each pass reads each observable once.
  - A daemon scheduler, started in the API lifespan only when the app owns its runtime, runs every cadence at start. It runs a daily-close pass after 16:20 New York time on weekdays. With Trader Workstation connected it runs an intraday pass every five minutes for intraday criteria whose observable has an IBKR intraday source.
  - Opening an active idea evaluates its `on_open` criteria and any never evaluated. Activation and saving a rule on an active idea evaluate at once. `GAMMA_IDEAS_EVALUATION=off` disables the scheduler, which never runs under pytest.
  - Only what was not yet known when a rule was armed (and the idea activated) can trigger it, so a start-up pass finds "while you were away" triggers with their first-met date and nothing older. That means observations dated on or after the arming day, plus any newer than the criterion's baseline. The baseline is the newest observation already known at the first evaluation after arming, taken again after a re-activation.
  - The baseline exists because lagging series arrive dated before the day they become known. FRED publishes a daily yield a day or two late, and a monthly print carries the first day of its reference month. Without it, the October CPI print, released in November, could never trigger a rule armed in October. If the first usable reading comes long after arming, anything published in between that is dated before the arming day counts as already known. A rule that is already met when it is armed holds until a new observation meets it.
  - A missing dependency or provider failure is `unavailable` with the reason. A value older than the observable tolerates is `stale` unless it already met the rule.
- **Observable registry v1** (`src/application/idea_observables.py`), ordered for the reference retail user. Differences from the table above are noted:
  - `equity_close`: research market data (Yahoo Finance, then IBKR). In demo mode only the AAPL, MSFT, SAP and SPY sample histories exist.
  - `macro_series`: FRED series through a new `MacroService.get_series_history_result`, which reports why a series did not load. FRED series need `FRED_API_KEY`. FX series come from IBKR, need TWS but no FRED key, and are unavailable in demo mode, which has no FX history. A series that loads empty is unavailable with the provider and its series code.
  - `prediction_probability`: Prediction Markets detail and daily history in percent. `event_occurs` reads the venue's resolution (Yes, or the chosen outcome).
  - `crypto_price`: CoinGecko daily history.
  - `commodity_price`: the Commodities service price history. `commodity_spread` offers level rules only, because calendar-spread history is a proxy until historical futures curves exist. Curve points are not in v1.
  - `macro_event`: the macro calendar drops past events and carries no released values, so it supports `date_reached` only, using the scheduled time stored with the rule once the event leaves the calendar. Use a macro series for the print.
  - `calendar_date`: Gamma's clock.
  - `script_signal`: the latest completed run of the accepted revision, read only from an eligible `gamma_analytics.json` (a metric, or the last point of a signals series). Mock-runtime runs are unavailable with that reason.
  - `option_atm_iv` and `option_skew`: the Options IV snapshot; both need TWS. Skew ports the Options tab's wing rule (put wing minus call wing, front expiry at least seven days out). A live Options stream on another symbol is never interrupted; the criterion is unavailable and says why.
  - Intraday criteria on any other observable fall back to the daily close and say so.
- **Notifications:** `GET /ideas/notifications` lists unacknowledged triggers and reviews due (an active idea whose review date is today or earlier, in UTC). The top-bar notification center and Sitrep's "Your ideas" section show the same items, open the idea and acknowledge triggers. The frontend polls every minute and refreshes after every criterion change. Both surfaces state that evaluation runs only while Gamma runs. A review stays listed until its date changes or the idea leaves `active`.
- **"What is this?":** one registry (`src/services/idea_explanations.py`, served at `GET /ideas/explanations`) covers every observable, condition, state, the cadence, the criterion kinds and the idea statistics. A single shared popover (`WhatIsThis.svelte`) shows it with the reading's provenance.
- **Routes:** the I2 subset of the table above, plus `POST /ideas/observables/preview` (the form's "Check now"), `GET /ideas/explanations` and `POST /ideas/{id}/criteria/{cid}/acknowledge`. Every criterion change, trigger and acknowledgement writes a journal entry. Markdown and JSON exports carry the criteria (JSON export format v2).
- **Mock acceptance, 2026-11-15:**
  - One criterion per observable was added through the form, and activation evaluated them.
  - Bitcoin, the 2026-11-01 date and the demo SPY ATM IV triggered. AAPL was stale on the old sample history.
  - XOM, the FRED series without a key and the Script run were unavailable, each with its reason. The rest held.
  - Triggers reached the notification center and Sitrep. Acknowledging from Sitrep cleared both lists.
  - A backend restart ran the start-up pass over two ideas (13 criteria, 12 readings, no duplicate triggers).
- **Live FRED check, 2026-11-16** (demo runtime with a real `FRED_API_KEY`, through the API and the UI):
  - Of the 39 macro series, 16 are FX. Each of the 23 FRED series loads with its value, date and `fred` provenance, except one. Euro Area Unemployment (`LRHUTTTTEZM156S`) came back empty and is unavailable with that reason.
  - Several euro-area series that FRED takes from the OECD are months old and show as stale. The policy-rate proxy, the 3-month rate, the 10-year yield, EUR/USD monthly and the 3m10y slope end on 2026-01-01; industrial production ends on 2023-10-01. Euro-area HICP and the broad dollar index are a few days past their tolerance. That is the source, not the evaluation.
  - A rule on the 10-year yield, the core CPI change, or a crossing on the 2s10s slope holds with the real reading, and its baseline is stored.
  - An idea back-dated on disk to 2026-10-20 triggered on real data, and both triggers reached the journal and notifications:
    - "Headline CPI YoY above 4.00%" triggered on the October print, first met 2026-10-01, at 4.08 %.
    - "US 10Y Treasury Yield above 5.00%" triggered at 5.15 %, first met 2026-10-19.
- **Left for later checkpoints:** native desktop notifications (Tauri), commodity curve points, IBKR intraday marks for equities, and a history for ATM IV and skew (so crossings and changes on them), which needs stored snapshots.

### Review before merge, 2026-11-21

A backend and a frontend code review of I1+I2 found these defects. They were fixed on the branch with regression tests, and the label and notification-center fixes were checked in a mock browser run before the merge:

- An IV criterion no longer calls `get_surface` while Options is still loading the same symbol's live stream (that call stops the stream); the reading is `unavailable` until the next pass.
- The store rejects ids that are not already safe instead of stripping characters, and a case-only mismatch (NTFS) is "not found" instead of quarantining the real file. `delete` checks the file before moving it.
- Any malformed item payload is quarantined instead of failing store start-up, and a bad file no longer aborts a whole evaluation pass.
- Notifications are sorted without `datetime.timestamp()`, which raises on Windows for dates before 1970.
- An idea archived during a slow read gets no trigger or journal entry.
- Editing a criterion regenerates its labels when a parameter changes, and an edited `macro_event` rule loads its events.
- A promoted Sitrep macro follow-up reopens with its region and theme. A double click on "Promote to idea" creates one idea, and a failed pin retries against the idea it already created.
- Deleting or editing an idea refreshes the notifications. Opening another idea clears the previous one while it loads. The notification popover takes focus and closes when focus leaves it.

**Follow-ups closed on 2026-11-21** (the review's open design questions):

- **No look-back by instant for timestamped data.** Readers whose points carry the moment they were observed (crypto price, contract probability, ATM IV and skew, commodity spreads) set `instant_points`, and only points after the arming instant count. Daily closes, commodity daily prices, Script signals and FRED series keep the day rule and the baseline, because they publish after the date they carry. A level already met when a rule is armed holds until a new observation meets it.
- **`event_occurs` on an already-resolved contract.** The venues give no resolution time, so a resolution counts only after a successful reading since arming has seen the contract open. If the first reading after arming already shows it resolved Yes, the rule holds with that reason (`known_at_arming` on the evaluation) and never triggers; a re-activation re-arms it the same way.
- **Equity Research pins** store the lookback and benchmark of the run that produced the figures (`researchResultBasis`), in the title, the captured metrics and the reopen ids, and reopening runs exactly that analysis. Older pins reopen as before. The scope form now follows external draft changes, so after any handoff it shows the ticker, benchmark and lookback of the analysis on screen.
- Still open, small: a "What is this?" button sits inside a `<label>` in the criteria form, and the legs editor table is not inside a `.table-scroll` wrapper at 390 px.

### I3a implementation notes

Recorded 2026-11-21 for review. Branch `claude/laughing-gauss-4b5d02`, cut from local `main` at b5b7ccd; merged into main with the rest of I3 on 2026-11-22.

- **Model (schema v3):** `IdeaTracking` in `src/models/ideas.py` holds the benchmark (SPY by default), the `IdeaCostModel`, the segments and the last computed `IdeaTrackingSnapshot`. A segment freezes its legs as `IdeaTrackedLeg` records: the stated weight, the signed share of gross exposure (absolute shares add up to 1), where the weight came from, the detected asset class and the market. Segments only grow, and only the last one can be open.
- **Weights:** with no stated weights, a `long` or `short` idea is an equal-weight book with that sign. A relative, event or neutral idea needs a signed weight on every leg, and a mix of stated and missing weights is refused rather than guessed. Such a segment, or one with a leg type this slice cannot price (commodity, prediction contract, FX, rates, macro), still opens with its `untracked_reason`. The period stays visible as a state.
- **Segments:**
  - Activation opens segment 1; restoring an archived idea opens a new one (reason `restored`).
  - A leg edit that changes the book closes the open segment and opens the next one. That covers a new instrument, a different share of gross, or a stance change that alters a default weight. Renaming a leg or scaling all weights (1/−1 to 2/−2) keeps the segment.
  - Archiving or removing every leg closes the segment.
  - Every change writes a `tracking_segment` journal entry that starts with "Hypothetical, not executed".
- **Entry and exit:**
  - A segment's book enters at the first session where every leg has a close *after* the freeze instant, and exits at the first such close after its end. Consecutive segments chain at the same close.
  - Each listing's close is placed at its exchange's closing time (`TRACKING_EXCHANGES`, at or before the official close). An unknown exchange suffix is taken to close at the start of its UTC day, so a close known before the freeze is never used.
  - A segment edited again before its first close is `never_entered` and holds nothing.
  - Nothing before a freeze is ever added.
- **Canonical daily series** (`src/application/idea_tracking.py`):
  - It is rebuilt on every read from provider closes. Equities and ETFs come from research market data, the read path of Strategy Lab and the `equity_close` observable (Yahoo Finance, then IBKR when configured; demo sample history in mock mode). Crypto comes from CoinGecko daily closes stamped at 00:00 UTC; the current-price point is not a close and is dropped.
  - A session counts only once its close is final (20 minutes after the close; crypto at the next UTC midnight).
  - The book buys fixed quantities at the entry close. Gross return is Σ share × (price / entry price − 1), in each instrument's own currency (no FX conversion in this slice).
  - Net return subtracts the per-side cost of entering and of closing at the latest close (mark to liquidation).
  - Benchmark, excess return and maximum drawdown (on the net path) are computed on the same sessions. Segments chain into one record "since activation".
- **Gaps stay gaps:**
  - Each market's calendar is the set of sessions on which any leg of that market, or a benchmark on the same market, has a close. Crypto trades every day.
  - A session in a leg's calendar without that leg's close is a gap: no value, a warning naming the leg and the date, and a break in the chart line. Later sessions are valued from the entry prices, so nothing is interpolated.
  - A market that was closed while another leg's market traded (an equity on a weekend in a crypto book) keeps its last close; that is not a gap.
  - **Limitation:** without an exchange holiday calendar, a day that every source misses cannot be told from a holiday and is not shown as a gap.
- **Costs:**
  - Per side, by asset class (table above), never zero by default. The four stated-cost classes are editable from 0 to 500 bp, and a tracked leg can be moved to another stated-cost class. Options and prediction contracts take their cost from a live quote, which daily tracking does not read.
  - The gross record never depends on the costs. A change is journaled (`tracking_settings`), recomputes the net figures and drops the stored Board headline, so a figure computed with other assumptions is never shown.
- **Board headline:** rebuilding the series stores the snapshot on the idea without touching `updated_at`. The scheduler does it at start-up and after each daily close, together with the criteria passes; `GAMMA_IDEAS_EVALUATION=off` turns off both. The index (schema v3) serves it, and the Board's "Since activation (hyp.)" column shows the net return with its as-of session, gaps and "stopped" or "partial". It reads "Not tracked" or "Not computed" when there is no figure.
- **Migration v2 → v3:** an active idea with legs gets one open segment, frozen at the later of its last activation or restore and its last leg edit (both read from the journal), with start reason `migrated`. Its legs have not changed since that instant, so nothing earlier is added. Earlier active periods are not reconstructed, because version 2 journals describe old legs only as text. Drafts and archived ideas get none.
- **API and exports:**
  - `GET /ideas/{id}/tracking` returns the rebuilt series: status, summary, segments with their legs and costs, points with gaps, cost classes with their basis, warnings and per-source provenance. `PATCH /ideas/{id}/tracking` changes the costs, leg classes or benchmark and returns the recomputed record.
  - The idea and the Board rows carry the tracking record and headline.
  - JSON export (format v3) adds `tracking_label` and the rebuilt `tracking_series`. Markdown adds "Tracking — Hypothetical, not executed" with the summary, the segments, the cost assumptions and the method.
- **UI:**
  - `IdeaTrackingPanel.svelte` sits after the criteria in the Idea view. Its title row has the label tag "Hypothetical, not executed", the session count and as-of date, and the shared provenance badge, whose tooltip holds the method.
  - The panel shows net, gross, costs (with the per-side range), the benchmark, excess and maximum drawdown. Below them: a 220 px chart of the net record against the benchmark with S1, S2 … markers at segment entries, the segments table with the reason each one opened, an inline cost editor and the warnings.
  - `TimeSeriesChart` gained opt-in `breakOnGaps`, `valueFormat: "percent"` and `markers`. lightweight-charts draws across whitespace points, so with `breakOnGaps` each continuous run is its own series and the gap keeps its slot on the axis.
  - Two "What is this?" entries were added: `stat.forward_return` and `stat.tracking_costs`.
- **Tests:**
  - `tests/test_idea_tracking.py` (19, injected clock and prices, no network, no TWS) covers five trading days with no backfill, activation after the close, waiting for the first close, a leg edit opening segment 2 and chaining, renames and scaled weights, never-entered segments, archive and restore, gaps that stay gaps, closed markets that are not gaps, crypto with equities over a weekend, costs and their edits, asset classes, untrackable legs and weights, provider failures, close instants and DST, CoinGecko closes, the v2 → v3 migration, and the routes against the demo runtime.
  - Frontend: `idea-tracking.test.ts`, `IdeaTrackingPanel.test.ts`, the Board column in `IdeasView.test.ts`, and the gap helpers in `chart-data.test.ts`.
  - Full suites on 2026-11-21: backend 1275 passed, 5 skipped (`GAMMA_IDEAS_EVALUATION=off`); frontend 712 passed; `tsc` clean; production build OK.
- **Browser check, 2026-11-21:**
  - Mock backend with its `data/`, `cache/` and a copy of the sample data in the worktree. One MSFT close (2026-01-21) was removed to show a real gap. Ideas were seeded with an injected clock in January 2026, the range the demo sample covers.
  - Headless Playwright in the light and dark themes at 1440, 1000 and 390 px: no console errors and no horizontal page overflow. The table scrolls inside its box at 390 px.
  - What was seen: the pair idea's two segments with their markers, the gap as a break in both lines, the SPY idea entering the session after an after-close activation, the migrated v2 idea, and the commodity idea as "Not tracked" with its reason.
  - A cost edit from the UI moved the net from −1.58% to −1.78%, left the gross at −1.38%, and wrote the journal entry.
- **Left for later slices:** close, review and Review mode (I3b); test and risk snapshots (I3c); the TWS intraday layer (I3d). Also deferred: pricing commodity, futures, option and prediction legs; FX conversion of non-USD legs; exchange holiday calendars, so a day every source misses becomes a gap; borrow costs for shorts.

### I3b implementation notes

Recorded 2026-11-21 for review. Branch `claude/ideas-i3b-close-review`, cut from the I3a branch at 1e1118e; merged into main with the rest of I3 on 2026-11-22.

- **Model (schema v4):** `Idea.reviews` holds `IdeaReview` records. Each review keeps:
  - the `outcome` (`confirmed`, `invalidated`, `abandoned`, `expired`), the `lesson` (required), `expected` (the thesis when left blank) and an optional `realized_note`;
  - when its episode opened (the activation, or the reopen after an earlier close) and when it closed;
  - a verdict per pin (`held`, `failed`, `unclear`) with the pin's title and stance frozen;
  - every criterion's state at close, with its trigger time;
  - `realized`, the hypothetical tracking headline as it stood when the idea was closed.

  The model refuses a closed idea without the review of its close. The store refuses any write that edits or drops an earlier review, as it does for the journal. Version 3 files migrate on load with no reviews; no version 3 idea can be closed.
- **Lifecycle:**
  - `POST /ideas/{id}/close` closes an active idea and requires the review. It journals the outcome and the lesson, and closes the tracking segment with end reason `closed`. Tracking stops at the close date: the book exits at the first close after the close instant, and nothing later is added.
  - `POST /ideas/{id}/reopen` returns a closed idea to active. It keeps the review and opens a new tracking segment (start reason `reopened`).
  - A closed idea can be archived, and restoring it returns it closed.
- **Realized:** the route rebuilds the series just before closing and freezes that headline into the review; its exit close may still be pending. The tracking snapshot gained `final`, set once no segment is open or waiting for its exit close. The scheduler keeps rebuilding closed and archived ideas until their record is final, so the Review mode shows the final figure once the exit close is priced, and "exit pending" with its as-of date before that.
- **Review mode** (`GET /ideas/review`, the Ideas tab's third mode):
  - It lists the review of each idea's current close: closed ideas, and archived ones that were closed. An idea that was reopened drops out until it is closed again; its earlier review stays on the idea.
  - It shows the outcome mix, holding time (median, range, by outcome), the median net hypothetical return and the median excess return over the benchmark (each with its sample size), and the closed ideas with their expectation, realized return, invalidation and lesson.
  - "Invalidation before a loss" counts the losing ideas whose invalidation criterion fired before the close, against all losses and against the losses that had an invalidation rule.
  - It describes the user's own record only, with no score.
- **UI:**
  - The Idea view has Close (active) and Reopen (closed); a closed idea can also be archived.
  - `IdeaCloseForm.svelte` asks for the outcome, the expectation (prefilled with the thesis), the hypothetical record so far, what happened, a verdict per pin and the lesson. The submit button stays disabled until there is an outcome and a lesson.
  - `IdeaReviewSection.svelte` shows the current review, the record at close beside the record now (final or exit pending), the pin verdicts, the triggered criteria and the earlier closes.
  - `IdeaReviewMode.svelte` is the Review mode. The Board gained a "Closed" filter.
  - Three "What is this?" entries: `review.outcome`, `stat.holding_time`, `stat.invalidation_before_loss`. Exports carry the reviews: in the JSON idea, and a "Reviews" section in Markdown.
- **Tests:**
  - `tests/test_idea_review.py` (10, injected clock and prices) covers: close requires a review and an active idea; the frozen review and realized record; tracking stops at the exit close; reopen keeps the review and opens a segment; reviews cannot be rewritten; archive and restore of a closed idea; the statistics; refreshing until final; the v3 → v4 migration; the routes against the demo runtime.
  - Frontend: `idea-review.test.ts`, `IdeaReviewSection.test.ts` (section, close form, Review mode), the Idea and Review modes in `IdeasView.test.ts`, and the mode registry in `navigation.test.ts`.
  - Full suites on 2026-11-21: backend 1285 passed, 5 skipped; frontend 722 passed; `tsc` clean.
- **Browser check, 2026-11-21:**
  - Same worktree-only mock fixture as I3a, plus closed ideas: a confirmed one with pin verdicts, an invalidated one whose invalidation fired before the loss, one archived after an abandoned close, and one reopened after an expired close.
  - Light and dark at 1440, 1000 and 390 px: no console errors and no horizontal page overflow.
  - From the UI: the Close button stayed disabled until the outcome and lesson were filled in. The idea closed and its tracking showed "Stopped". Review listed it. Reopen returned it to active with the earlier review shown.
- **Left for later:** Copilot's `review_idea` (I5); counting every close of a reopened idea, not just the current one, in the statistics; per-episode returns for a reopened idea (the record since activation chains every segment).

### I3c implementation notes

Recorded 2026-11-21 for review. Branch `claude/ideas-i3c-test-risk`, cut from the I3b branch at 6da1839; merged into main with the rest of I3 on 2026-11-22.

- **Model (schema v5):** `Idea.tests` holds `IdeaTestSnapshot` records and `Idea.risks` holds `IdeaRiskSnapshot` records; they are the spec's `IdeaTest` and `IdeaRisk`.
  - Each snapshot keeps the legs and signed shares of gross exposure it ran on (the same frozen legs as tracking), the benchmark, the lookback, the window and observation count, the source ids (the composition and its origin), the provenance and the data warnings. Strategy Lab's generic disclaimers are left out of the warnings.
  - Version 4 files migrate on load with none. An idea keeps the last 20 of each, and the journal keeps every run (`test_refreshed`, `risk_refreshed`).
- **Recomputed only when asked:**
  - `POST /ideas/{id}/test` composes the idea's legs in Strategy Lab (`ResearchService.compose_strategy_lab_portfolio`, 756-session lookback, the idea's benchmark). It keeps total and annual return, volatility, Sharpe, Sortino, maximum drawdown, the benchmark's return and the excess, beta and correlation, per-leg contributions, and the equity and benchmark curves, each at most 260 points.
  - A backtest is labelled in-sample with no costs (`sample = in_sample`, `costs_included = false`) wherever its figures appear. Out-of-sample splits and trial counts arrive with I4.
  - `POST /ideas/{id}/risk` runs the Risk service on that research book (`source_scope = research_book`, 252 sessions, 95%, one day, no Monte Carlo). It keeps historical and parametric VaR and expected shortfall as shares of the book (shown as losses), volatility, beta, correlation and drawdown. It also replays the same signed weights through the documented stress episodes, keeping each episode's status, and names the worst priced one.
  - Equity and ETF legs resolve through research market data. Crypto legs reach Strategy Lab as inline CoinGecko daily closes. Legs this slice cannot price, missing weights, an unknown symbol, or an idea that is not a draft or active answer 422 with the reason.
- **Stale snapshots:** a snapshot is stale when the idea's legs or shares of gross changed after the run (scaling every weight keeps it fresh) or when it is 7 days old or more. The API serves `stale_reason`, and the UI tags it "Stale" beside the run date.
- **UI:** `IdeaAnalysisPanel.svelte` ("Test and risk") sits between the criteria and the tracking panel, as the spec orders the Idea view.
  - It has "Run test" and "Run risk" buttons for draft and active ideas with legs, and the latest backtest with its "No costs" and "In-sample only" tags, run date, window, legs, metrics and a 160 px curve against the benchmark.
  - Below that: the latest risk run, with VaR, ES, volatility, beta, the worst replayed episode and the priced episodes table.
  - Each part carries the shared provenance badge.
  - Exports carry the snapshots: in the JSON idea, and a "Test and risk snapshots" section in Markdown.
- **Tests:**
  - `tests/test_idea_analysis.py` (8) covers: the backtest and risk snapshots on the demo runtime (window, metrics, curves, provenance, no boilerplate, journal, VaR written as a loss, episodes and the worst one, exports); staleness after a leg edit; refusals for legless, unpriceable and unknown legs; crypto legs as inline closes (with a fake Strategy Lab); the 20-snapshot cap with the journal kept; staleness by age and by rescaled weights; archived ideas refused; record validation and round trip; the v4 → v5 migration.
  - Frontend: `IdeaAnalysisPanel.test.ts` (helpers, labels, losses, worst episode, stale and empty states).
  - Full suites on 2026-11-21: backend 1293 passed, 5 skipped; frontend 726 passed; `tsc` clean.
- **Browser check, 2026-11-21:** same worktree-only mock fixture (its v4 idea files migrated to v5 on start).
  - From the UI at 1440 px in the light theme, the panel started empty. "Run test" and "Run risk" filled it, and the journal recorded both runs.
  - Light and dark at 1440, 1000 and 390 px: labels shown, no horizontal page overflow, and no console errors once the backend was up.
  - On the demo sample, the backtest covers 2024-12-24 to 2026-01-27. Only the 2025 tariff episode falls inside the sample; the older ones are unavailable and stay out of the table.
- **Left for later:** "Attach to idea" from Strategy Lab and Risk results (the snapshots here run from the idea itself); out-of-sample validation and trial counts (I4); costs inside the backtest; Monte Carlo for signed books.

### Stack review, 2026-11-21

A code review of the I3a-I3c stack found nine defects. They were fixed in one commit on top of `claude/ideas-i3c-test-risk`, so merging the whole stack includes them; merging I3a or I3b alone does not. Each fix has a regression test in `tests/test_idea_tracking.py` or `tests/test_idea_analysis.py`, or a frontend unit test, and the frontend ones were checked in the mock browser.

- **(I3a)** A version 2 file whose migration fails, for example an active idea with an out-of-range leg weight, now goes to quarantine. Before, it stopped the store, and so the backend, from starting.
- **(I3a)** A headline computed while the record changed is dropped. The tracking signature (segments and their ends, benchmark, costs) is checked before the snapshot is written, so a slow rebuild no longer overwrites the Board figure of a book edited meanwhile.
- **(I3a)** Consecutive segments never hold two books at once. A segment enters no earlier than the close where the previous one exits, and waits, with that reason, while the previous one cannot exit yet. Before, a removed leg with a missing close could make both segments count the same sessions.
- **(I3a)** A provider that stops answering is named. When a leg of an open, waiting or exiting segment has no close for more than three of its market's sessions, the record gains `stale_since` with a warning and the reason. The Board shows "provider stopped", and the panel shows "no close since …". The record still stops there and is never filled in.
- **(I3a, pre-existing pattern)** A store update whose mutation changes nothing no longer rewrites the item file and the index, so reading a tracking record no longer writes to disk when nothing changed.
- **(I3a)** Editing anything other than the legs of an active idea never opens a tracking segment. Before, a migrated idea without a segment got one labelled "Legs added" on a title edit.
- **(I3b)** Review mode requests its statistics once when it opens; it requested them twice.
- **(I3b)** The close form says "Loading…", "Tracking unavailable" or "Not computed yet" according to the tracking state, and falls back to the last stored headline with its date. Before, it could show "Loading…" forever.
- **(I3c)** A failing source during "Run test" or "Run risk" (Strategy Lab, Risk, CoinGecko) answers 502 with the reason instead of a bare 500.

### I3d implementation notes

Recorded 2026-11-21 for review. Branch `claude/ideas-i3d-intraday-579806`, cut from the I3c branch at f5f2c44 (with the stack review fixes); merged into main with the rest of I3 on 2026-11-22.

- **What the layer is for:** today's hypothetical P&L, the intraday drawdown and intraday criterion triggers, while Trader Workstation is connected and Gamma runs. It never replaces or rewrites the canonical daily series. `compute_tracking` reads provider closes only. The daily series (points, segments, figures and Board headline) is identical with and without marks, and a test checks it.
- **Recording** (`src/application/idea_intraday.py`, `IdeaIntradayService`):
  - The evaluation scheduler records marks before its intraday criteria pass, and once at start-up. `GAMMA_IDEAS_EVALUATION=off` turns it off with the rest.
  - The legs marked are those of every active idea's open, trackable segment. The cadence is every 5 minutes while any leg's market is in its regular session (crypto always; US 09:30-16:00 New York time on weekdays).
  - A leg whose market is closed is asked once an hour, and its frozen mark is reused in between. An idea whose markets are all closed gains one row an hour.
  - Connecting or disconnecting TWS, or a change of tracked books, makes a pass due at once.
  - Demo mode records nothing. Before TWS has connected once in a run, nothing is written either: there is no layer to interrupt yet.
- **IBKR reads** (`src/services/ibkr_marks.py`, `IbkrMarkReader`): market-data snapshots only, through the runtime's IBKR client: no orders and no account or position requests from the layer. The TWS connection itself is Gamma's existing one, opened read-only.
  - Each distinct instrument is asked once per pass, even when several ideas share it, and at most 24 instruments per pass.
  - Batches hold 8 contracts, or 4 while the Options surface streams, which stays inside the 10 lines its engine keeps in reserve. The stream is never started, stopped or reconfigured.
  - Each batch is one task on the shared IB thread. It sets the market-data type, requests, waits, falls back and restores the session default (live for `auto` or `live`, delayed for `delayed`), so a type cannot leak into another service's request. An open market asks live, then delayed; a closed one asks frozen, then delayed-frozen.
  - US listings map to SMART stock contracts. CoinGecko `bitcoin`, `ethereum`, `litecoin` and `bitcoin-cash` map to IBKR crypto on PAXOS, which has no snapshots: it is streamed for up to 2.5 times the snapshot wait (5 s) and cancelled. Other listings and leg types are named as unmarked.
  - When TWS refuses a contract for lack of data (errors 200, 354, 10089, 10168, 10186 on every type tried), the leg carries TWS's message, and the contract is not asked again for an hour.
  - Each pass is recorded in the provider usage ledger (`ideas.intraday_marks`).
- **Labels:** each mark keeps the data type TWS served and the field it came from (last trade, or the bid-ask mid). It is `live` only when TWS served live data and the market was in session.
  - Delayed data or a delayed field is `delayed`.
  - Frozen data or a closed market is `frozen`.
  - Both together are `delayed_frozen`.
  - The quality of a point is the oldest of its legs.
  - TWS's `close` tick is never a mark. Over a weekend it is the close of the session before the latest one, which was checked live: on Sunday the delayed `close` was Thursday's. A ticker with nothing else gives no mark, with that reason. A leg whose market is closed then carries its canonical last close.
- **Storage** (`src/services/idea_intraday_store.py`): `data/ideas/intraday/<idea_id>/<UTC day>.json`. Each file holds `mark` rows (price, field, data type and quality per leg, the legs without a mark and why, the segment, the run id and the promised cadence) and `status` rows.
  - A status row is a stretch where Gamma ran but could not mark, because TWS was disconnected or IBKR did not answer. Each stretch is one row, extended while it lasts.
  - Bounds: at most 400 rows per file (a 5-minute cadence writes about 290 a day) and the 10 newest days per idea. Writes are atomic; an unreadable file is moved aside.
- **Valuation** (`compute_intraday`, pure):
  - A mark values its segment's book against the entry prices of the canonical series, with the same per-side costs and mark to liquidation, chained to the earlier segments as the daily record is.
  - Today's return is measured from the latest daily close before the mark's UTC day.
  - The intraday drawdown is the deepest fall from the session's running peak, which starts at that close.
  - The canonical closes are dividend-adjusted and the marks are not. Valuing against the entry price keeps a total return, consistent with the daily series.
- **Absence:**
  - A leg with no mark while its market is open makes the point a gap, with no value. A leg whose market is closed carries its last close, labelled.
  - A mark before the segment's first close has no P&L: the book enters at that close.
  - The gaps list is explicit. A stretch between two marks longer than 2.5 times the promised cadence is a gap. So are the stretch from the regular open (or the segment's start) to the first mark, and from the last mark to now or to the close.
  - A gap is split at the status stretches inside it: "TWS disconnected" or "IBKR did not answer" for the time Gamma saw, and "Gamma not running" (the run id changed) or "not recorded" for the rest.
  - Nothing is interpolated: the chart line breaks at every gap.
- **Criteria:**
  - `equity_close` and `crypto_price` are now intraday-capable. With `intraday` cadence and TWS connected, the reading appends the latest recorded mark of a tracked leg (live or delayed only, at most 12.5 minutes old) as one more observation at its instant, with IBKR provenance.
  - That observation counts only if it was taken after the rule was armed (the instant rule; `ObservableReading.intraday_from`).
  - Frozen marks never trigger. Without a fresh mark the rule is evaluated at the daily close and says why.
  - Criteria never ask IBKR for a quote of their own.
- **API:**
  - `GET /ideas/{id}/tracking` (and `PATCH`) keeps the daily series and adds `intraday`: the latest session's view.
  - `GET /ideas/{id}/tracking/intraday?session=YYYY-MM-DD` serves one stored session without persisting anything.
  - The view holds the status (`recording`, `idle`, `no_marks`, `demo`, `not_tracked`), the reference close, the summary (today, since activation live, intraday drawdown, quality, marks, gaps), the points, the gaps, the latest marks per leg, the warnings and the provenance, all labelled "Hypothetical, not executed".
- **UI** (`IdeaIntradayStrip.svelte` in `IdeaTrackingPanel.svelte`, below the daily chart):
  - The head holds "Intraday", the "Hypothetical, not executed" tag, the quality tag (Live in the accent; Delayed or Frozen as a warning), "Recording" or "TWS disconnected", "as of HH:MM UTC · marks · gaps", a session picker when several days are stored, and the shared provenance badge.
  - Below: the Today, Since activation live and Intraday drawdown stats; a 120 px chart of today's return with the line broken at gaps; the gaps table (UTC period, length, why); and the latest IBKR mark per leg (mark, source, prior close, move).
  - The strip rereads its session every minute while it records today and the window is visible; otherwise its figures do not move.
  - Empty states keep the same place and say what is missing.
- **Tests:**
  - `tests/test_idea_intraday.py` (24, fake IBKR client and injected clock, no network or TWS) covers: marks recorded while connected and valued against the daily series; the daily series unchanged; the intraday drawdown; delayed and frozen labels; the prior-session close never used as a mark; a disconnection and a restart as explicit gaps, and a gap split at the stretches Gamma saw; nothing written before the first connection; connection changes making a pass due; a missing mark as a gap and a closed market carried; hourly closed-market requests while crypto keeps five minutes; deduplication and the instrument budget; demo mode; a segment waiting for its first close; storage bounds and a corrupt file; the reader's live-to-delayed fallback, frozen requests and type restore, batches while Options streams, and TWS's no-subscription error with its one-hour wait; intraday criteria from fresh marks only and the service's fallback note; the scheduler order; and the routes.
  - Frontend: `idea-intraday.test.ts`, `IdeaIntradayStrip.test.ts`, the intraday case in `IdeaTrackingPanel.test.ts`, and `percentAxisFormat` in `chart-data.test.ts`.
  - Full suites on 2026-11-22: backend 1325 passed, 5 skipped (`GAMMA_IDEAS_EVALUATION=off`); frontend 740 passed; `tsc` clean; production build OK.
- **Left for later:**
  - IBKR contracts for non-US listings.
  - An exchange holiday calendar: on a US holiday the marks may read live.
  - Marking legs that are not in a tracked segment (criteria on other symbols fall back to the daily close).
  - Keeping the old book's P&L for the rest of the day after a mid-session leg edit (the new segment's marks have no P&L until its entry close).
  - Live P&L on the Board.

### Live check, 2026-11-21

Run on Saturday 2026-11-21 and Sunday 2026-11-22 against real providers and TWS, on branch `claude/ideas-i3d-intraday-579806`. US equity markets were closed on both days. A live-mode backend ran from the worktree on port 8010 with its own `data/` and `cache/` (never the main checkout's), the provider keys of the root `.env`, and IBKR client id 17 (the desktop backend was not running and was not touched). Ideas were seeded through `IdeaService` with an injected clock, so real closes from the previous two weeks were used. The worktree data was deleted afterwards.

**I3a-I3c on real data (no TWS needed):**

- **Equity pair** (AAPL +1 / MSFT −1, relative). Activated Friday 2026-11-06 at 22:30 UTC, after the New York close. On Thursday 2026-11-12 at 15:00 UTC, NVDA +0.5 was added.
  - S1 entered at the Monday 11-09 close, the first close after activation; nothing earlier was used. It exited at the Thursday 11-12 close, with AAPL +50% and MSFT −50%: 4 sessions, gross +2.67%, net +2.57%, costs 0.10%, SPY +0.59%.
  - S2 entered at that same Thursday close, with AAPL +40%, MSFT −40% and NVDA +20%. Through 11-20 it had 7 sessions: gross −3.41%, net −3.51%, SPY −8.89%.
  - Since activation: 10 sessions (11-09 to 11-20), no gaps, net −1.03%, gross −0.83%, cost drag 0.19% (5 bp per side on four sides), SPY −8.35%, excess +7.33%, maximum drawdown −3.73%.
- **Crypto and equity** (CoinGecko `bitcoin` and COIN, equal-weight long). Activated Wednesday 11-11 at 15:00 UTC, it entered at the 11-11 close.
  - It has 10 sessions, including Saturday 11-14 and Sunday 11-15, with crypto closes while COIN and SPY kept their Friday closes. There were no gaps.
  - Net −23.32%, gross −22.83%, costs 0.49% (50 bp per side on Bitcoin, 5 bp on COIN), SPY −9.21%. Bitcoin went from 73,974 to 58,818 and COIN from 136.27 to 101.97.
  - The record is as of 11-20, because Saturday's crypto close is final only at 00:00 UTC on Sunday.
- **Closed idea** (XOM long). Activated Monday 11-09 at 15:00 UTC; closed Wednesday 11-18 at 16:00 UTC as `invalidated`, with a lesson.
  - The review froze the record as it stood at the close, as of 11-17: 7 sessions, net +2.05%, SPY −2.69%.
  - The final record exited at the 11-18 close: 8 sessions, net −2.00%, SPY −2.99%, excess +0.98%, `final`.
  - Review mode showed one invalidated idea, holding time 9.04 days, median net −2.00% and median excess +0.98% (n = 1), and one loss with no invalidation rule.
- **Closes cross-checked against IBKR daily bars** (TRADES, unadjusted, read through TWS). The Yahoo closes matched to the cent wherever no dividend fell inside the window: COIN, NVDA, SPY, and AAPL from 11-12. Earlier AAPL, MSFT and XOM closes were lower by exactly one quarterly dividend: AAPL 350.42 against 350.69 on 11-09, XOM 163.70 against 164.73.
  - Research market data reads Yahoo with `auto_adjust=True`. The canonical series is therefore a total return, and an entry price shown in the segments table is restated after an ex-dividend date.
  - This was not documented; the methodology text now says it. A provider switch to IBKR's unadjusted bars in the middle of a record would show a jump the size of a dividend. That stays a known limitation.
- **Run test on the pair** (three years). Window 2023-11-16 to 2026-11-20, 756 observations: total +42.57%, annual +12.55%, volatility 14.72%, Sharpe 0.88, maximum drawdown −17.09%, SPY +58.87%, excess −16.30%. Labelled in-sample with no costs.
- **Run risk on the pair.** Over 252 observations: historical VaR 1.54%, expected shortfall 2.40% and parametric VaR 1.69%, as one-day losses at 95%.
  - All eight stress episodes were priced with full coverage, including the ones the demo sample could not price: the 2007-2009 financial crisis −16.41% (SPY −55.19%), Q4 2018 −16.96%, COVID 2020 −7.79% (SPY −33.72%), the 2020 oil collapse −4.00%, the 2022 rate shock −8.98% (SPY −24.50%), the 2022 energy shock −0.80%, August 2024 −3.62% and the 2025 tariffs −12.26%.
  - The worst was Q4 2018.
- **Run test and risk on the crypto idea.** CoinGecko serves 365 days, so 250 observations were analysed, with the warning shown. The four episodes before 2021 were unavailable; the 2022-2025 ones were partial, with Bitcoin missing.
  - **Defect found and fixed:** the "Worst replayed episode" figure named the 2022 rate shock at −36.07%. That is a partial replay in which Bitcoin, half the gross exposure, has no history and is treated as flat, but the figure did not say so.
  - Now each episode stores its coverage, the share of gross with history. The worst episode is the worst fully covered one, and a partial one only when no episode is fully covered.
  - The figure and the coverage column say "Partial · 50% of gross". Regression tests: `test_the_worst_episode_is_a_full_replay_and_a_partial_one_says_its_coverage` (backend) and the coverage case in `IdeaAnalysisPanel.test.ts`.
- **Five trading days in wall-clock time** cannot be checked from back-dated ideas. An idea has to be activated now and read later.
  - The worktree data is deleted after this check, so it cannot hold that idea.
  - To run it, activate a legs idea in the desktop app with no TWS, for example SPY long or a pair, and note the instant. Then open its tracking panel after the fifth US close that follows. The first session must be the first close after the activation instant, there must be five sessions, nothing earlier, and the Board column must show the same figure.

**I3d against TWS** (port 8010, IBKR client id 17, read-only connection; Saturday 21 and Sunday 22 November, US markets closed):

- **Connection and first marks.** Connecting from the API made a pass due at once, and the first marks were written within a minute. On Saturday at 21:38 UTC (market-data mode `auto`), TWS served frozen data (type 2) for AAPL 344.87, MSFT 489.54 (bid-ask mid) and NVDA 130.01 (last). These are Friday's after-hours last trades, above the closes of 342.56, 484.52 and 125.53, and every mark was labelled frozen.
  - The pair's strip read: Today +0.43% against the 11-20 close, Since activation live −0.60% (the daily record is −1.03%), intraday drawdown 0.00%.
  - On the weekend the pair was marked once an hour. The crypto idea kept the five-minute cadence, and COIN's frozen mark was reused between hourly requests (`marked_at`).
- **Delayed labelling.** With `IB_MARKET_DATA_MODE=delayed` on Sunday, TWS answered the closed US listings with delayed-frozen data (type 4), but only the `close` tick. That tick was Thursday's close, not Friday's: AAPL 349.21, MSFT 498.30, NVDA 145.98, COIN 108.87.
  - **Defect found and fixed:** the first build used that tick as a frozen mark, which would have shown a false move (AAPL +1.9% against Friday). Now the `close` tick is never a mark. The leg says "IBKR served only the prior session's close", and a leg whose market is closed carries its canonical close. Regression tests: `test_best_price_never_uses_the_prior_session_close` and `test_a_ticker_with_only_the_prior_close_has_no_mark_and_says_why`.
  - The rows that build wrote, two marks at 18:22 UTC in the test data, were discarded.
  - A delayed BTC mark arrived once (60,648.5, labelled delayed) and not on later passes, even with a 5 s wait.
- **IBKR crypto.** On Saturday TWS refused BTC on PAXOS with error 354 ("Requested market data is not subscribed"). The leg showed that message, the contract was not asked again for an hour, and the crypto idea's points were gaps, because Bitcoin's market was open and it had no mark.
  - After TWS's nightly restart, on Sunday, BTC came back live (type 1): 60,616.5, then 60,664.75. The crypto strip read Today +0.63% against the 11-21 close and Since activation live −21.96% (the daily record is −22.45%).
- **Gaps:**
  - Stopping the backend for 13 minutes on Saturday (last mark 21:38:47, next 21:52:39 from a new run) showed "Gamma not running".
  - Disconnecting TWS from the API on Sunday from 18:32:57 to 18:47 wrote one `disconnected` status row, extended every five minutes. Its stretch, 18:32:42-18:48:00, showed "TWS disconnected" on the crypto idea. The pair's hourly cadence on a closed market correctly showed no gap for it.
  - Sunday's leading stretch was split into "not recorded" (00:00-18:23:51) and "IBKR did not answer" (18:23:51-18:32:42, the delayed-mode passes). **Defect found and fixed:** before the split, the whole 18-hour stretch read "IBKR did not answer". Regression test: `test_a_gap_is_split_at_the_stretches_gamma_saw`.
  - The laptop went into standby on Saturday at about 21:57 UTC, so the Saturday file ends there with a trailing "not recorded" stretch. TWS dropped its API at its nightly restart (04:59 local, error 1100), and the backend stopped with it.
- **The daily series did not change.** After two days of marks, disconnections and restarts, every daily point and segment of both ideas was identical to its copy saved before the first connection. The crypto idea only gained the 11-21 session from CoinGecko's final close.
- **Browser** (headless Playwright against this backend and Vite on 5174): light and dark at 1440, 1000 and 390 px for both ideas, with no console errors and no horizontal page overflow. The tables scroll inside their box at 390 px.
  - **Defect found and fixed (pre-existing since I3a):** `TimeSeriesChart`'s `valueFormat: "percent"` used lightweight-charts' `percent` price format. That format belongs to its percentage scale mode and does not print the value: it showed 2.468 as "2.1%" and 0.6 as "0.1%". Only whole ticks came out right, which is why the daily chart looked correct.
  - This affected the tracking chart, the backtest curve and the intraday strip. Percent series now use a custom formatter (`percentAxisFormat`, two decimals), tested in `chart-data.test.ts`.
  - Also from this check: isolated marks are drawn as points, and the gaps table no longer repeats the label in its reason line.
- **Not verifiable on a weekend; re-check on a weekday session with TWS connected:**
  - live (type 1) and delayed (type 3) marks during regular hours, and the five-minute cadence while the US market is open;
  - the leading gap from the 09:30 New York open to the first mark;
  - today's P&L and the intraday drawdown moving through a session, and the strip refreshing every minute;
  - an intraday criterion on `equity_close` triggering from a live or delayed mark (frozen marks never trigger);
  - the hand-over at the US close, from five-minute to hourly frozen marks;
  - no conflict with a streaming Options surface, where batches are limited to 4 contracts.

  To re-check, run the app with TWS connected and an active legs idea, for example the AAPL/MSFT pair, from before the open into the session. Open the idea's tracking panel and confirm the quality tag reads Live (or Delayed without a live subscription) and the marks arrive every five minutes. Then disconnect TWS for 15 minutes and reconnect: a "TWS disconnected" row should appear. The daily figures above the strip must not move.

### Live check, 2026-11-24 (weekday)

Run on Tuesday 2026-11-24 from 20:00 to 21:25 UTC (15:00 to 16:25 New York time), across the US close, on branch `claude/ideas-closeout` (cut from `main` at 2de1b1c). This is the weekday re-check that the [2026-11-21 check](#live-check-2026-11-21) could not do. A live backend ran from the worktree on port 8010 with its own `data/` and `cache/`, IBKR client id 17 (read-only connection, market-data mode `auto`) and the root `.env` provider keys passed as process environment; the desktop backend on port 8000 was not running and was not touched. A minute-by-minute recorder read the tracking views and the stored rows; the worktree data was deleted afterwards.

**Seed.** With an injected clock, an AAPL +1 / MSFT −1 pair and a Bitcoin + COIN idea were activated on Monday 2026-11-23 at 13:00 UTC, before that day's open, so both entered at the 11-23 close and today's P&L could move. (Activating "after Monday's close" would have entered at Tuesday's close, leaving no P&L to watch.) A six-name long basket (NVDA, AMZN, GOOGL, META, JPM, XOM) was activated through the API at 20:05 UTC to give the reader ten instruments; it enters at today's close, so its marks have no P&L.

**What was confirmed:**

- **Live marks during regular hours.** Connecting at 20:03:01 made a pass due at once: AAPL 351.75 and MSFT 492.755, both `last`, market-data type 1, labelled Live. Every mark until the close was type 1 and labelled live; Bitcoin on PAXOS was again refused with error 354 (no crypto subscription on this account), so the crypto idea's points were gaps, as specified.
- **Five-minute cadence.** Pair marks at 20:03:08, 20:06:11 (the basket's activation made a pass due), then 20:11:18, 20:16:18, 20:21:18, 20:32:19, 20:37:19, 20:42:19, 20:47:19, 20:52:19 and 20:57:20, each row promising 300 s.
- **Leading gap.** "Not recorded before the first mark", 14:30 UTC (the 09:30 New York open) to 20:03:08, because the backend started at 20:02.
- **Today's P&L and the intraday drawdown moved.** Today +0.36% → +0.30% → +0.34% → +0.23% → +0.44% at the last frozen mark; intraday drawdown 0.00% → −0.05% → −0.12%. The daily record above the strip stayed at net −0.10% as of 11-23.
- **The strip refreshes every minute.** Headless Chromium logged `GET /ideas/{id}/tracking/intraday?session=2026-11-24` at 20:18:38, 20:19:38, 20:20:38 and 20:21:38, and the head followed ("as of 20:16 UTC · 4 marks" → "as of 20:21 UTC · 5 marks"). In the in-app browser pane, which runs as a background page when hidden, the timer stalled; that is the host browser's throttling, not the strip.
- **An intraday criterion triggered from a live mark.** "AAPL close above 352.00" (intraday, armed 20:04:41) triggered at 20:19:18 from the live mark of 20:16:18 (352.10): `first_met_at` is the mark's instant and the provenance reads "IBKR/TWS (live)". After the close, the same rules fell back to the daily close ("No fresh IBKR mark for AAPL … Evaluated at the daily close"), so frozen marks never triggered.
- **The daily series did not change.** The pair's daily points and segments hashed to the same value at every minute from 20:05:00 to 21:13:05, across twelve marks, a ten-minute TWS disconnection, a backend restart and a second disconnection. It changed only when a signal was attached (21:14) and when the 11-24 close became final (21:20).
- **Options streaming.** A SPY surface streamed from 20:05:41 to 20:21:23 ("Running (SPY, Live)", 30 contracts, 31 of 60 market-data lines with 10 reserved) through four mark passes, with no messages and no interruption. After the restart, with the stream running, the backend logged "Intraday marks: 10 instrument(s) in 3 batch(es) of at most 4 (Options stream running)".
- **TWS disconnected.** TWS was disconnected from the API from 20:21:29 to 20:31:30. One `disconnected` status row was written (20:22:19, extended to 20:27:19) and, after the fix below, the strip shows "20:21–20:32 · 11 min · TWS disconnected" with the chart line broken.
- **Hand-over at the close.** The last live pass was 20:57:20 (cadence 300 s); the next, 21:02:20, asked frozen data (type 2) and promised 3600 s for the pair and the basket. The crypto idea kept five minutes because Bitcoin's market is open; COIN's frozen mark was then reused between hourly requests (102.03 at 21:07:34, 21:12:34 and 21:20:35).

**Defects found and fixed (each with a regression test):**

1. **Marks repeated the previous pass (P0).** The pass at 20:06:11 returned exactly the 20:03:08 prices for AAPL, MSFT and COIN while Yahoo's one-minute bars had AAPL near 351.93 and MSFT near 493.61; the basket's six legs repeated their 20:06:11 prices at 20:11:18 to the cent. ib_insync keys tickers by `id(contract)` and keeps their last, bid and ask; the reader caches qualified contracts, so a new snapshot read the old ticker before TWS answered and every mark lagged one pass. A separate read-only probe (client id 18) confirmed it: on the second round `main`'s reader answered in 0.00 s with the first round's prices, the fixed reader waited 0.64 s for new ones. `IbkrMarkReader` now forgets the cached ticker before each request and after it. Test: `test_a_new_pass_never_reads_the_previous_pass_price_from_the_cached_ticker`.
2. **A close rule triggered from Yahoo's in-progress bar (P0).** "AAPL close above 350.50", armed at 20:03:48, triggered at once with `met_value` 351.74 and `first_met_at` 2026-11-24 00:00: Yahoo's daily history carries today's bar with the latest price during the session. The mark it should have used (20:03:08) was taken before the rule was armed. `equity_close` now keeps only sessions whose close is final at the reading time, with the tracking rule (`market_horizon`: a US close counts from 16:20 New York time), and says which bar it ignored. Test: `test_todays_provisional_bar_never_triggers_a_close_rule_and_the_mark_does`. The latched trigger from before the fix stays latched until the rule is edited, as designed.
3. **A short disconnection left no gap (P1).** Ten minutes without TWS cost one pass; the stretch between marks (20:21:18 → 20:32:19, 11 minutes) was under the 2.5 × cadence threshold, so the view showed no gap and the line joined across it, although a `disconnected` row was stored. A status row inside a stretch now makes it a gap whatever its length; an ongoing disconnection shows as an open gap. Test: `test_a_short_disconnection_is_a_gap_even_below_the_threshold`. The rows stored before the fix render correctly after it.
4. **The strip stopped after a disconnection (P2).** It polled only while `recording`, so after a disconnection it showed "TWS disconnected" until the idea was reopened. It now keeps reading today's session while TWS is disconnected; checked in a browser: Recording → TWS disconnected (still polling) → Recording at 21:07:57 without reopening. Test: the `shouldPollIntraday` cases in `idea-intraday.test.ts`.

The reader also logs one line per pass with the instrument count, the batches and whether the Options stream runs.

**Browser** (headless Chromium, DPR 1, against this backend and Vite on 5174): the pair's strip in light and dark at 1440, 1000 and 390 px, with no page overflow and no console errors; the tables scroll inside their box at 390 px.

**Left as follow-ups (P2):** between 16:00 and 16:20 New York time the strip's "Prior close" column shows the same day's provisional close; after a mid-session segment change the strip drops the leading gap; the fallback note on a frozen mark says "Gamma marks only the legs of tracked ideas" instead of naming the frozen mark. The rebalancing cost of a signal change made after the close appears at the next close and was not read live.

### I4 design decisions

Settled on 2026-11-23, before implementation, from the I4 row above, the `IdeaSignal` table, the quant bridge, the rigor guardrails and the "Left for later" items of I3b and I3c. They extend the spec; where a decision narrows a table above, the decision wins.

1. **Where the positions come from after activation: the latest positions or weights are frozen at attach, and every later change is a new attach that opens a new segment.**
   - A Script run is fixed and costs API credit, so Gamma never runs a Script on its own, and a CSV is a file the user supplied once. A signal therefore describes one book: the last row of the schedule dated on or before the attach day. That book is frozen in a tracking segment exactly like the legs of I3a, and held at fixed quantities until the next change.
   - New positions arrive only through the user: a new Script run they started in Strategy Lab, or a new import. Each one is a new attach, which closes the open segment and opens the next one at the next close, with rebalancing costs (decision 3 below). That is the "new imports as new segments" option, and it covers re-runs of a Script too.
   - **Rejected: a dated schedule that already covers the future.** A run's dates end at its data; a schedule that reaches past the attach day would hold weights the script wrote for days it had not seen, and following it would need rebalancing inside a segment, which the segment model does not have. An attach whose rows reach past the attach day is refused with that reason rather than silently trimmed. This can be revisited with I4c if users ask for pre-committed calendars.
   - **Weights and positions.** A `weights` signal is signed exposure as a share of NAV (the Script contract's `signed_nav_exposure`): it is not normalized, the residual is cash at 0%, and gross exposure up to 5× is accepted. A `positions` signal is signed units per instrument; Gamma values them at each instrument's latest provider close on or before the attach day and holds them as shares of a fully invested gross book (absolute shares add up to 1). The conversion prices are stored with the signal.
   - **The legs follow the signal.** Attaching a book sets the idea's legs to the signal's instruments, with the signal weight as the stated weight, and journals it. While a book signal is attached, the legs cannot be edited by hand; detaching the signal returns the legs to the user and opens a new segment under the I3a rules. Test, risk and the intraday layer keep reading the legs, so they all see the signal's book.
2. **A `returns` signal is validation only, labelled as a supplied series.** Gamma cannot rebuild a return stream from provider closes, so it never drives tracking and never appears on the tracking chart or in the canonical series, the Board headline or the review's realized figure. It is stored as a supplied series ("Supplied by you, not rebuilt by Gamma", or "Supplied by Script run …") with its window, its Strategy Lab statistics from the same import path and its warnings, in the signal section only. An idea whose only signal is a return stream keeps tracking its legs; with no legs it is "Not tracked" with that reason.
3. **What counts as a trial, and why the count never resets.**
   - The idea keeps an append-only **trial ledger**, separate from the signals. Each entry is one distinct thing that was tried: a Script run (`run:<run id>`), a sweep point (`sweep:<sweep id>:<point>`, whether or not it ran; a run of a sweep point counts as that point), an import (`import:<content hash>`), and a backtest of the legs with a new set of weights (`legs:<positions hash>`, from "Run test").
   - Attaching a Script signal records every completed run of that script that exists at that moment, every revision and parameter set, not only the attached one: picking the best of several runs is a trial whether or not the others were attached. Attaching a walk-forward validation records every point of its sweep.
   - `trial_count` is the size of the ledger when the current signal was attached, **including the signal itself** (1 means a single try). A test snapshot stores the ledger size when it ran. The store refuses any write that removes or rewrites a ledger entry, as for the journal, so detaching, changing or re-attaching a signal can only add to it.
   - Version 5 files migrate with a ledger seeded from their retained test snapshots (one entry per distinct set of weights). When the journal shows more test runs than snapshots survive (an idea keeps the last 20), the ledger is flagged as a lower bound, and the UI says "at least N".
4. **Rebalancing costs.** A segment opened by a signal change rebalances from the previous book at the close where that book exits: the cost is the per-side cost of each instrument's turnover between the drifted old exposure and the new one, not a full exit plus a full entry. Segments opened by a manual leg edit keep the I3a rule (full exit, then full entry), so I3a records do not change.
5. **Costs per leg.** The tracking cost model keeps the per-asset-class defaults (never zero by default) and gains an optional per-leg override in basis points per side. The signal section and the tracking panel show each leg's cost, its class and whether it was edited. An explicit 0 is allowed and labelled as edited.
6. **"Attach to idea" from Strategy Lab and Risk results is not in this cut.** I4 attaches from the Idea view: a Script run picked from the idea's signal form, or a CSV pasted there. Wiring an "Attach to idea" action into the Strategy Lab and Risk result panels is a cross-tab change of its own (two more tabs, the shared PinToIdea picker, handoffs), so it moves to **I4c**.

**Split.** I4 is split like I3: **I4a** (this cut) delivers `IdeaSignal` from Script runs and CSV imports, E5 validation snapshots, the trial ledger and `trial_count` beside every performance figure (including the I3c test snapshots), per-leg costs, schema v6 with its migration, `POST /ideas/{id}/signal` and `DELETE /ideas/{id}/signal`, and signal-driven tracking. **I4c** adds "Attach to idea" from Strategy Lab and Risk results. I4b, the Python client, follows I4a as planned.

### I4a implementation notes

Recorded 2026-11-23 for review. Branch `claude/ideas-i4-quant`, cut from `main` at b182851; merged into main on 2026-11-23 (merge commit 57553e4). The design decisions above apply.

- **Model (schema v6):** `src/models/ideas.py`.
  - `IdeaSignal` keeps the source, the output kind, a label, `source_ref` (bounded, frozen), `as_of` (the decision date of the frozen book), the book as `IdeaSignalLeg` records, a `supplied` series for a returns signal, a `validation` snapshot, `trial_count` with its lower-bound flag, `detached_at`, warnings and provenance.
  - A Script signal's `source_ref` holds the script id and title, the revision id, number and status, the source hash, the parameter hash and values, the run id, the sweep point when there is one, the output id, the artifact hash, the result ids, the input snapshot and manifest hash, the runtime kind and the completion time. An import's holds the content hash, the row count, the date column and the columns read.
  - `Idea.signals` only grow; the current signal is the last one while it is not detached, and the store allows only that change (`detached_at`, set once) to an earlier record. `Idea.trials` is the append-only ledger (`IdeaTrial`: key, kind, time, label, signal), and `trials_lower_bound` marks a migrated ledger.
  - `IdeaValidationSnapshot` freezes an E5 walk-forward: the sweep id and definition hash, the report hash, the target (`weight_book` or `returns_result`), the execution lag and the turnover cost, the sweep's trial count, the train and test lengths, the window and the selection metric, the common window, every fold (training and test windows, selected point, test return), the out-of-sample metrics and window, the chained out-of-sample curve (at most 260 points), the best in-sample value with its "biased upward" label, the number of distinct selections, whether causality was verified, warnings and provenance. `costs_included` is true when Gamma charged turnover costs in the weight book and null for a returns target, whose costs are whatever the script wrote.
  - `IdeaTestSnapshot` gained `trial_count` and `trial_count_lower_bound` (null on snapshots from before I4). Tracked legs accept the weight source `signal`, with exposure up to 5× NAV. Segments gained `signal_id` and `rebalance`; start reasons `signal_attached`, `signal_changed`, `signal_detached` and end reason `signal_changed` were added. `IdeaCostModel` gained `leg_bp`, a per-leg cost override, and `bp_for_leg`.
  - Version 5 files migrate with no signals and a ledger seeded from their retained backtests (`migrate_idea_v5_to_v6`).
- **Signals** (`src/application/idea_signals.py`, `IdeaSignalService`):
  - **Script:** the run must be completed, of an accepted revision, and have exactly one valid, eligible `gamma_analytics.json`: the same checks as the Strategy Lab analytical handoff (`inspect_analytics`), so a safe preview is refused. A weights signal reads the run's `weights` schedules from the retained bytes; a returns signal reads one `returns` result through the handoff mapping and Strategy Lab analytics. Instruments in the `ticker`, `symbol`, `yahoo`, `yfinance`, `equity` and `etf` namespaces read as tickers and `coingecko` or `crypto` as CoinGecko ids; any other namespace needs an explicit mapping, and the attach says so. Gamma never starts a run.
  - **Validation:** with a sweep of the same script, `walk_forward_sweep` computes the report from the retained per-point results, with the train and test lengths, window and selection metric the user gave. A weight-book target is charged the highest per-side cost of the book's legs per unit of turnover unless the user sets another, so a validation is never costless by default. A run outside the validated sweep is accepted with a warning that the figures describe the sweep's selection rule.
  - **Import:** each column is read with `ResearchService.imported_column_values`, the function Strategy Lab's return import now shares (the same date, number, percent, thousands-separator, missing-cell and duplicate-date rules), and a returns import goes through `analyze_strategy_lab` itself. A book import needs a value for every instrument on its last row (0 when out of the book). Weights above 5× NAV are refused with a hint about percentages. Positions are valued at each instrument's latest final provider close and held as shares of gross; the price and its session are stored.
  - Rows dated after the attach day are refused, for imports and Script schedules alike.
- **Tracking** (`src/application/idea_tracking.py`): a book signal's segment holds the signal weights exactly (NAV, cash at 0%). When a segment opened by a signal change enters at the close where the previous book exits, its entry cost is the per-side cost of each instrument's turnover between the previous book's drifted exposure and the new weights, and the previous book's exit cost is dropped (`rebalanced`, `turnover`, `exit_rebalanced` in the response). Per-leg costs apply everywhere a leg's cost does. The methodology text says both. I3a records are unchanged: segments opened by leg edits still pay a full exit and entry.
- **Service** (`IdeaService`): `attach_signal` and `detach_signal` write `signal_attached` / `signal_detached` journal entries and, on an active idea, a `tracking_segment` entry with "Hypothetical, not executed". A book signal sets the legs; editing the legs while it is attached is refused. Activation, restore and reopen freeze the attached book. "Run test" records a `legs:` trial for a new set of weights and stamps the snapshot with the ledger size; the journal line names it. `PATCH /ideas/{id}/tracking` takes `leg_bp` (null drops an override), journaled.
- **API:** `POST /ideas/{id}/signal` (Script or import; 422 with the reason, 502 when a source is down) and `DELETE /ideas/{id}/signal`. The idea carries `signals` (with `current` and `drives_tracking`), `current_signal_id`, `trials`, `trial_count` and `trials_lower_bound`. The Markdown export gained "Signal and validation"; the JSON export carries the records in the idea.
- **UI:**
  - `IdeaSignalPanel.svelte` ("Signal and validation") sits between "Test and risk" and the tracking panel, collapsed by default. The title row keeps the signal's label, kind and out-of-sample return and the trial count visible while collapsed, plus Attach or Change signal and Detach (with a confirm step).
  - Expanded, it shows the signal with its tags (source and kind, "Drives tracking" and "Hypothetical, not executed", or "Validation only"), the trial count, the source ids, the frozen book with each leg's weight (of NAV or of gross), units and valuation for positions, its cost per side and whether it was edited, and the residual cash; a supplied series with its statistics, "In-sample" and a curve; and the out-of-sample validation with its cost tag, sweep trials, split, statistics, the best in-sample figure labelled as biased, a 140 px curve and the folds table.
  - The attach form takes pasted CSV (parsed with Strategy Lab's CSV parser, date column guessed, one ticker and type per column) or a Script run id with an instrument map and an optional sweep id with train and test lengths.
  - The backtest in "Test and risk" gained a "Trials N" tag beside "No costs" and "In-sample only" (or "Trials N/A" before I4). The tracking panel gained "Follows signal" and "Trials N" tags, a per-leg cost column in the cost editor, readable segment reasons (including rebalanced turnover) and a "Legs (weight)" header, since a signal book is not a share of gross.
- **Tests:**
  - `tests/test_idea_signals.py` (15, injected clock and prices, the deterministic E5 fixture runtime for Script runs, no network, no TWS, no API credit): rebalancing by turnover with exact figures; changing and detaching each opening a segment, and the leg-edit guard; a returns signal leaving the canonical series identical; rows after the attach day refused; the Strategy Lab import rules and a ragged last row; positions valued at the latest final close; crypto columns; the ledger never going back down and the store refusing a removal; backtests as trials; the v5 → v6 migration through the store; per-leg costs; a Script weights signal with walk-forward validation and every trial; a run outside the validated sweep; preview runs and unmapped instruments refused; the routes against the demo runtime.
  - Frontend: `IdeaSignalPanel.test.ts` (helpers, collapsed and expanded panel, returns and empty states, per-leg cost drafts).
  - Full suites on 2026-11-23: backend 1340 passed, 5 skipped (`GAMMA_IDEAS_EVALUATION=off`); frontend 748 passed; `tsc` clean.
- **Browser check, 2026-11-23:** a mock backend on port 8010 with the worktree's own `data/` and `cache/`, and Vite on 5174. Three ideas were seeded with an injected clock: a weights import replacing the legs and then changed (January 2026, demo closes), a returns import (validation only), and a Script weights signal from the deterministic E5 fixture with a four-fold walk-forward. Headless Playwright at device scale 1, light and dark, at 1440, 1000 and 390 px: no console errors and no horizontal page overflow; tables scroll inside their box at 390 px. From the UI, a CSV with a row in 2099 was refused with its reason, and a valid one opened segment 4, raised the trial count to 4 and wrote the journal. Two layout defects found in this check were fixed: a missing space in template-joined meta lines (now built as strings) and the panel title wrapping into three lines at 390 px.
- **Left for later:** I4c ("Attach to idea" from Strategy Lab and Risk results, and a run and sweep picker instead of pasted ids, which needs a runs listing route); I4b (the Python client); pre-committed future schedules; turnover rebalancing for manual leg edits; the intraday layer ignores the turnover entry cost of a rebalanced segment (it values marks with the I3a per-side entry); the Board shows no signal column.

### I4b and I4c design decisions

Settled on 2026-11-23, before implementation, from the I4b and I4c rows above, the quant bridge and the I4a notes.

1. **What "Attach to idea" attaches.** One shared component, `AttachToIdea.svelte`, the counterpart of "Pin to idea": a pin freezes what a panel shows as evidence, while an attach asks the backend to recompute the result into the idea, so it carries provenance and counts as a trial. Nothing the browser computed is stored as truth.
   - **Strategy Lab composer result:** a backtest snapshot (`IdeaTestSnapshot`, `source = strategy_lab`), recomputed from the composer's legs, weights, benchmark and lookback by the same composition path as "Run test". The idea's legs do not change.
   - **Strategy Lab result from a Script run:** the run becomes the idea's signal (I4a's Script path: weights for a weight-book result, returns otherwise). Gamma reads the retained run again and never reruns it.
   - **Strategy Lab result from an imported CSV:** the imported returns become a returns signal (validation only), through the same import path.
   - **Risk with a Strategy Lab research book:** a risk snapshot (`IdeaRiskSnapshot`, `source = risk_tab`) of that book, recomputed as "Run risk" does. Risk on the account portfolio is not attachable: an idea is a research book, not an account.
   - Ideas still prices equity, ETF and crypto legs only; a book with any other leg is refused with the reason, before anything is sent.
2. **Staleness of an attached snapshot.** It is compared with the idea's legs like any snapshot, and says so: "Attached from Strategy Lab: a different book from the idea's legs." The panel tags it "From Strategy Lab" or "From Risk".
3. **Run picker.** The signal form lists scripts, their runs and their sweeps from the existing read-only routes (`GET /research/strategy-lab/scripts`, `…/{id}/runs`, `…/{id}/sweeps`). Runs that did not complete or are safe previews are listed but cannot be chosen. Pasted ids remain as a fallback when no script is listed.
4. **The Python client's API shape** (the decision left open in [Decisions](#decisions)): a `Gamma()` object reading `GAMMA_API_BASE` and `GAMMA_SESSION_TOKEN` from the environment, with `history(symbol, kind=…)`, `macro(series_id)`, `observables()` and `ideas.list / get / tracking / attach_signal`. Reads return pandas DataFrames with provenance columns (lists of dicts without pandas). `httpx` is the only required dependency.
   - **Its histories** come from a new read-only route, `GET /ideas/history`, that serves the closes the canonical tracking series uses (research market data for equities and ETFs, CoinGecko for crypto), final closes only, with provenance; an unavailable source is a state with its reason. Macro series use the existing `GET /macro/series/{id}/history`.
   - **Its one write** is `attach_signal`, which turns a DataFrame or rows into an import request for `POST /ideas/{id}/signal`; Gamma validates it exactly like a Strategy Lab CSV import.
   - **Its safety** is structural: every request is checked against an allowlist of six read routes and the signal import before it is sent, and a test checks that each allowed route exists and that none can place, stage or route anything or touch an account.

### I4c implementation notes

Recorded 2026-11-23 for review. Branch `claude/ideas-i4bc`, cut from `main` at 623e65d; merged into main on 2026-11-23 (merge commit ddafbeb).

- **Backend:** `IdeaAnalysisService.run_test` and `run_risk` take an optional `AttachedBook` (source, label, legs with type, symbol and weight, benchmark, lookback). The legs are frozen as signed shares of gross with the I3a rules and composed through the same Strategy Lab and Risk paths; the snapshot keeps `source` (`strategy_lab` or `risk_tab`) and `attached_from` / `attached_label` in its source ids. `POST /ideas/{id}/test` and `/risk` accept that book as their body; an empty body runs the idea's legs as before. The journal says "Attached a Strategy Lab backtest of …". A backtest of a new set of weights is a `legs:` trial wherever it comes from.
- **Frontend:**
  - `AttachToIdea.svelte` (shared picker: choose an idea or create one; it states what will be attached and opens the idea afterwards) and `lib/idea-attach.ts` (pure builders: `compositionBook`, `scriptSignalPayload`, `importedReturnsPayload`, `strategyLabAttachTarget`, `riskAttachTarget`), with `attachToIdea` in the Ideas store.
  - Strategy Lab's result panel offers "Attach to idea" for a composer result, a Script-derived result and an imported CSV result; Risk's header offers it while a Strategy Lab research book is the source. A disabled button says why in its tooltip.
  - The signal form's Script mode lists scripts, runs (time in UTC, sweep point, parameter hash; incomplete runs and safe previews disabled) and sweeps (`lib/idea-script-picker.ts`).
  - "Test and risk" tags an attached snapshot "From Strategy Lab" or "From Risk".
- **Tests:** `tests/test_idea_attach.py` (5: a Strategy Lab book as a recomputed snapshot with its stale reason, trial and journal; a Risk book; a matching book stays fresh and an empty body still runs the legs; refusals for unpriceable, flat and unknown-source books; the runs route). Frontend: `AttachToIdea.test.ts` (builders, picker labels, the shared button) and the source tag in `IdeaAnalysisPanel.test.ts`.
- **Browser check, 2026-11-23:** a mock backend on 8010 with the worktree's own `data/` and `cache/`, Vite on 5174, and a script with a six-point sweep from the deterministic E5 fixture runtime seeded into the worktree's script store (no Python executed, no API credit). With headless Playwright: in Strategy Lab, a composer book (AAPL +1, MSFT −1) was composed and attached; "Open in Risk" carried it to Risk, whose header attached it as a risk snapshot; "Open idea" showed both, tagged "From Strategy Lab" and "From Risk", with the trial count. In the Idea view the picker listed the script, its seven runs and the sweep, and attaching with a 60/30 walk-forward produced the validation snapshot and eight trials. Light and dark at 1440, 1000 and 390 px: no console errors and no horizontal overflow. The check found one defect, fixed: at 390 px the signal form's selects took the width of their longest option and widened the page by 23 px.
- **Left for later:** an "Attach to idea" on Risk's stress-replay table alone (the header action attaches the whole book); attaching a saved Strategy Lab run from "Saved Runs".

### I4b implementation notes

Recorded 2026-11-23 for review, on the same branch.

- **Client** (`clients/python/`, package `gamma_client`, `pyproject.toml` as `gamma-research-client` 0.1.0, README): `Gamma`, `IdeasAPI`, `GammaClientError` (with the HTTP status and Gamma's reason), `RouteNotAllowedError`, `ALLOWED_ROUTES`, `route_allowed` and `signal_rows` (a DataFrame with dates in the index or a column, a Series, or a list of dicts, as text cells the import reads).
- **Route:** `GET /ideas/history?symbol=&kind=equity|etf|crypto&days=` returns the symbol, market, `available`, the reason when unavailable, the final closes (session, close instant, price), the warnings and the provenance.
- **Tests:** `tests/test_python_client.py` (7, against the routes of a demo runtime, with FastAPI's test client as the transport): a history with provenance and the demo warning; ideas, tracking and observables; a DataFrame signal validated like a CSV import (percent strings, a future row refused with 422); a returns Series as validation only; the allowlist (each route exists, only GETs plus the signal import, nothing order- or account-shaped, other routes refused before sending); row conversion and the token requirement; a macro series' provenance (mocked transport, since FRED is offline in tests).
- **End-to-end, 2026-11-23:** from a separate Python process against the mock backend on 8010, `Gamma()` read MSFT's closes with their provenance, attached a weights DataFrame to an idea (a `-30%` cell read as −0.30, one trial, a new tracking segment), and refused a `DELETE` before sending it. The signal then showed in the Idea view.
- **Full suites on 2026-11-23** (I4b and I4c together): backend 1352 passed, 5 skipped (`GAMMA_IDEAS_EVALUATION=off`); frontend 755 passed; `tsc` clean.
- **Left for later:** publishing the package; an async client; reading observables' readings (the client lists the registry only).

### I5 design decisions

Settled on 2026-11-23, after reading the Copilot end state and completion contract in [`copilot_v2_tab_plan.md`](./copilot_v2_tab_plan.md) and re-checking the current official OpenAI guidance (recorded there, "Official guidance reviewed 2026-11-23 — Ideas in Copilot").

1. **Gamma computes, the model writes.** The Ideas context and both read-only tools return facts Gamma computed from the local record and the rebuilt hypothetical series (`src/application/idea_copilot.py`); the model never supplies a figure, a state or a verdict.
2. **Ideas is a context, not an automatic route.** The `ideas` domain is the idea open in the Ideas tab (`idea_id` on the request context), chosen in the Copilot context picker or used from the Ideas tab's shelf; it can join a synthesis like any loaded context. The Research Operator's planner does not route to Ideas on its own in this checkpoint, so existing plans and evals are unchanged; its attached context does carry the open idea for the three tools.
3. **Read-only tools.** `review_idea` (expected against realized, evidence verdicts, criteria that fired, the realized figure at close and now) and `explain_criterion_state` (the decisive evaluation, its provenance, the arming rule and the shared "What is this?" texts) are `read_context` tools in the Ideas domain.
4. **The draft is a draft change under the existing confirmation flow.** `draft_idea_from_context` is offered from every context, only for an explicit request to draft or save an idea. Gamma validates the proposal against the observable registry (two to four criteria, a warning when none invalidates, the observables of the read paths, equity, ETF and crypto legs) and binds it as a pending `CopilotDraftMutation` through `CopilotConfirmationService`; nothing is written to the idea store. `ideas.apply_idea_draft` is an `apply_change` with `confirmation_required`: the user accepts it from the card, with the mutation's token, session and proposal hash, and Gamma creates a **draft** idea (origin `copilot`, journaled) in one write. Copilot never activates, closes or edits an idea or its criteria.
5. **Where the proposal appears.** The card result carries the pending proposals (`proposals`, and `proposal_ids`, which the saved turn keeps), and the transcript shows them with "Create draft idea" and "Reject". The proposal is not hidden inside an Operator run: the Agents SDK route excludes draft changes and the Responses Operator path keeps its own DCF approval flow, unchanged.

### I5 implementation notes

Recorded 2026-11-23 for review. Branch `claude/ideas-i5`, cut from `main` at c83e699; merged into main on 2026-11-23 (merge commit f1c6ddd).

- **Facts** (`src/application/idea_copilot.py`): `idea_context_summary` (thesis, stance, legs, evidence with stance, frozen values and provenance, criteria with their evaluations, the last two test and risk snapshots with sample, costs and trial count, the tracking summary labelled "Hypothetical, not executed", the signal and trial count, the journal tail, reviews, the review statistics when the prompt asks about the record, and a boundary line); `review_idea_facts`; `explain_criterion_facts`; `build_idea_draft` with its strict function schema (`draft_tool_schema`); `draft_from_dict` for the stored proposal. `IdeaService.create_idea_from_draft` creates the idea and its criteria in one write, so a rule the registry refuses at acceptance leaves nothing behind.
- **Copilot wiring** (`src/application/copilot_ideas.py`, registered in `copilot_service.py`): the `ideas` context builder (sources `ideas.idea`, `ideas.tracking` and up to twelve pins, each navigating to the idea), the three tools, the `ideas.propose_idea_draft` and `ideas.apply_idea_draft` registry entries, `apply_copilot_mutation` (dispatch by apply action, used by `POST /copilot/mutations/{id}/apply`), and `proposals_for_result`, which ties each bound proposal to the turn's session before the turn is saved. Also: the context budget (28 KB) and the `idea_id` selector, the provider's default prompt, the default plan tool and an omission reason, the Operator attached context (`ideas_selection`), the runtime wiring, and a deterministic `ideas` branch in the mock provider (review, explain, and a draft when the prompt asks for one).
- **Frontend:** `ideas` joins `CopilotBaseDomain`, the domain labels, threads and cards, the context fingerprint (idea id and last change), the request context (`idea_id`), the synthesis validation, the context picker ("Ideas", once an idea is open) and the Ideas tab's shelf surface. `CopilotIdeaProposals.svelte` (with `lib/copilot-idea-proposals.ts`) shows each proposal: title, thesis, stance, legs, criteria with their rationale, the grounding and warnings, the status, "Create draft idea" and "Reject", then "Open idea"; after a session reload it reads the proposals by id. A Copilot source pointing at an idea opens it.
- **Tests:** `tests/test_idea_copilot.py` (14: drafts validated and refused with reasons, warnings, acceptance in one write, the strict schema, context, explain and review facts) and `tests/test_copilot_ideas.py` (6, through the Copilot API of a demo runtime with the mock provider: the context and read-only tools, a draft that waits and becomes a draft idea only with the right token and session and only once, a rejected draft, a missing idea, the registry permissions, a refused draft). `tests/test_copilot_operator_attached_context.py` covers the new attached context. Frontend: `CopilotIdeaProposals.test.ts`.
- **Full suites on 2026-11-23:** backend 1373 passed, 5 skipped (`GAMMA_IDEAS_EVALUATION=off`); frontend 758 passed; `tsc` clean. No live model call was made: every Copilot test and the browser check used Gamma's deterministic mock provider.
- **Browser check, 2026-11-23:** a mock backend on 8010 with `GAMMA_COPILOT_PROVIDER=mock` and the worktree's own `data/` and `cache/`, Vite on 5174, and an active idea seeded with an injected clock. From the Ideas tab's Copilot shelf, "Review this idea and draft a follow-up idea" produced a card from the review and explain tools and a drafted idea; "Create draft idea" created it as a draft and "Open idea" opened it. The Copilot tab listed "Ideas" in its context picker, and a source link opened the idea from the Board. Light and dark at 1440, 1000 and 390 px: no console errors and no horizontal overflow.
- **Live acceptance pending:** a run against the configured OpenAI model (it spends API credit, so it waits for the owner's go-ahead) to confirm the model calls `draft_idea_from_context` only on request and fills the strict schema.
- **Left for later:** Operator planning that routes to Ideas; drafting from a Research Operator run; editing a proposal before accepting it.

### I5 live acceptance, 2026-11-24

Five live runs against the configured default model (`gpt-6.1-sol` through OpenAI Responses, profile `auto` resolving to `standard`, reasoning `medium`, Gamma's custom Responses loop), out of six the owner allowed. They ran on the retail backend (port 8011, no TWS) during the I6 retail audit, from the Ideas tab's Copilot shelf and from Commodities. Official guidance was re-checked the same day (recorded in the Copilot plan, "I5 live acceptance, 2026-11-24").

| Run | Context and prompt | Tool calls | Tokens in / out / reasoning | Latency | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | Ideas, Research Agent: "Review this idea" | none | 7,410 / 1,055 / 84 | 21.1 s, 1 provider call | A correct, grounded review (it caught a mixed QQQ-beta/Nasdaq comparison in the thesis, the unavailable governance rule and the 34.1% vs 11.5% contract discrepancy), written from the Ideas context. `draft_idea_from_context` was not called. |
| 2 | Same thread: "Draft a follow-up idea" | `draft_idea_from_context` ×1 | 17,835 / 977 / 47 | 19.1 s, 2 calls | A valid strict-schema proposal that passed registry validation: relative stance, NVDA +1 / QQQ −1 (equity and ETF), three criteria including an invalidation rule. "Create draft idea" created it as a draft. |
| 3 | Commodities: "What is driving Brent and WTI this week, and what would change that read?" | `inspect_commodity_curve_fundamentals` ×1 | 23,609 / 998 / 72 | 23.9 s, 2 calls | No draft. |
| 4 | Commodities: "Draft an idea from this commodities context so I can track it: an energy idea with an invalidation rule." | `draft_idea_from_context` ×1 | 22,361 / 982 / 81 | 21.1 s, 2 calls | A valid proposal (WTI short via an oil ETF proxy, three criteria). "Reject" marked the mutation rejected and created nothing (still two drafts and one active idea). |
| 5 | Ideas, Research Operator: "Review this idea" | none | 1,153 / 333 / 0 | 12.2 s, 2 calls | The Operator planner does not route to Ideas: it treated "idea" as an issuer name and asked which of IACO, IACOU or IDTL was meant. |

No run was refused and none errored.

**Against the acceptance:**

- Draft only on request: **met** (runs 1 and 3 did not draft; runs 2 and 4 drafted exactly once).
- Strict schema and registry validation: **met** (both proposals validated; the pending mutation carried its token, session and proposal hash).
- Proposal card: **met** (accept created one draft idea with origin Copilot; reject created nothing).
- A prompt outside Ideas drafts only when asked: **met** (runs 3 and 4).
- "Review this idea" calls `review_idea` and `explain_criterion_state`: **not met.** With `tool_choice: auto` the model answered from the Ideas context, which already carries the criteria evaluations and the tracking summary those tools return. The review was grounded in Gamma's facts (decision 1 holds either way), but the tools were not exercised live. The Operator path (run 5) does not reach them either.

**Open decision for the owner.** Either accept context-grounded reviews (the tools stay available for questions the context does not answer), or make the review path deterministic, for example by letting the Ideas shelf's review request restrict the first turn to the two read-only tools (`tool_choice` with `allowed_tools`, required) or by having Gamma run `review_idea` itself before the model call, as a default plan tool. Either change needs one more live run to confirm; the sixth allowed run was kept for that.

**Found on the way** (see the [I6 audit](./audits/ideas_persona_audits_2026-11-24.md)): the energy draft's leg is shown with the model's free-text label instead of its ticker (P2), and the Polymarket headline probability defect (P0, fixed) that the review itself pointed out.

### I6 persona audits, 2026-11-24

Both audits are in [`audits/ideas_persona_audits_2026-11-24.md`](./audits/ideas_persona_audits_2026-11-24.md), each finding with its severity, steps and evidence.

- **Retail, without TWS** (port 8011, public and keyed providers only): every fixed task worked. One P0 was found and fixed on the branch: Polymarket's headline probability was the last trade even far outside the book (34.1% against a 0.09/0.139 book); it now follows Polymarket's own display rule (the midpoint, or the last trade when the spread is wider than $0.10). The outcome of a prediction rule can now be typed by its label. Cross-tab workflow 8, speed to insight 8: **accepted.**
- **Quant, live data** (port 8010, TWS): CSV weights and positions, attach from Strategy Lab and from Risk, the Python client from a separate process and per-leg costs all worked. The Script tasks were blocked: both approved executions on the configured runtime (`openai_code_interpreter_v1`, `gpt-6.1-sol`) ended incomplete because the model did not run Gamma's wrapper verbatim, so Gamma withheld the outputs; walk-forward could not run. Cross-tab workflow 8, speed to insight 7, one open P0: **not accepted.**

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
| 5 | Default costs | **Per asset class**, shown and editable; values are starting assumptions to check against fee schedules before I3 (checked 2026-11-21: other equities 15 bp, spot crypto 50 bp) | `IdeaSignal`, I3 |
| 6 | Python client | **In this repo (`clients/python/`), after I4** | Quant bridge, I4b |
| 7 | Reference retail user | **Any broker, no TWS**: the default path needs no IBKR; IBKR observables are enhancements | Personas, observable registry, I6 |

The client's API shape (I4b) was settled on 2026-11-23 (see [I4b and I4c design decisions](#i4b-and-i4c-design-decisions)). The per-side cost values (decision 5) were checked against official fee schedules on 2026-11-21 (see the default cost model); they stay assumptions the user can edit.
