# Idea Workspace Spec

> **Status: approved (2026-11-14); I1 and I2 merged into main on 2026-11-21 after a code review (see [Review before merge](#review-before-merge-2026-11-21)).** Roadmap [Workstream 12 - Ideas](../roadmap.md#workstream-12---ideas); listed in [`docs/README.md`](./README.md). The product owner settled the seven open decisions on 2026-11-14 (see [Decisions](#decisions)) and split I3 into I3a-I3d on 2026-11-21. I3a (forward tracking), I3b (close and review) and I3c (test and risk snapshots) are done on stacked branches `claude/laughing-gauss-4b5d02`, `claude/ideas-i3b-close-review` and `claude/ideas-i3c-test-risk`. None is merged; all await review (see the [I3a](#i3a-implementation-notes), [I3b](#i3b-implementation-notes) and [I3c](#i3c-implementation-notes) notes). I3d and I4-I6 are not started.

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
| I3: test, risk, tracking | `IdeaTest`, `IdeaRisk`, `IdeaTracking` with segments, the canonical daily series and the TWS intraday layer, the per-asset-class cost model, close and review, Review mode | A legs idea tracks for five trading days with no backfill and no TWS; with TWS, the intraday layer records and shows its gaps without changing the daily series; an edit opens a new segment; close requires a review. Split on 2026-11-21 into the four slices below |
| I3a: forward tracking | `IdeaTracking` with segments, the canonical daily series, the per-asset-class cost model, `GET`/`PATCH /ideas/{id}/tracking`, the tracking chart in the Idea view, the Board column | A legs idea tracks for five trading days with no backfill and no TWS; an edit opens a new segment; gaps stay gaps; costs are applied and shown. **Status: done on branch `claude/laughing-gauss-4b5d02`, not merged** (see [I3a implementation notes](#i3a-implementation-notes)) |
| I3b: close and review | Close with `IdeaReview`, reopen as a new segment, Review mode | Close requires a review; tracking stops at the close date. **Status: done on branch `claude/ideas-i3b-close-review` (stacked on I3a), not merged** (see [I3b implementation notes](#i3b-implementation-notes)) |
| I3c: test and risk snapshots | `IdeaTest`, `IdeaRisk` | Snapshots keep their source ids, window and provenance and show their date when stale. **Status: done on branch `claude/ideas-i3c-test-risk` (stacked on I3b), not merged** (see [I3c implementation notes](#i3c-implementation-notes)) |
| I3d: TWS intraday layer | IBKR marks for the legs while TWS is connected | With TWS, the intraday layer records and shows its gaps without changing the daily series |
| I4: quant layer | `IdeaSignal` from Script runs and CSV import, validation snapshots, trial count, signal-driven tracking | A Script signal attaches with its out-of-sample result and trial count; tracking follows the signal's positions; costs are visible |
| I4b: Python client | Read-only client in `clients/python/`: histories with provenance, ideas, observables, and signal import into an idea | From a notebook: read a history, attach a signal to an idea, and see it validated in Gamma exactly as a CSV import; no route the client uses can place, stage or route anything |
| I5: Copilot | Ideas context builder, draft, review and explain tools | Copilot plan updated with a dated OpenAI guidance review; draft-from-card needs user acceptance; no execution authority |
| I6: persona audits | Retail audit without TWS and quant audit, each with fixed tasks | No P0/P1 finding in either; each scores at least 8 on cross-tab workflow and speed to insight |

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

Recorded 2026-11-21 for review. Branch `claude/laughing-gauss-4b5d02`, cut from local `main` at b5b7ccd; not merged and not pushed.

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

Recorded 2026-11-21 for review. Branch `claude/ideas-i3b-close-review`, cut from the I3a branch at 1e1118e; not merged and not pushed.

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

Recorded 2026-11-21 for review. Branch `claude/ideas-i3c-test-risk`, cut from the I3b branch at 6da1839; not merged and not pushed.

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

Still to settle during implementation: the client's API shape (I4b). The per-side cost values (decision 5) were checked against official fee schedules on 2026-11-21 (see the default cost model); they stay assumptions the user can edit.
