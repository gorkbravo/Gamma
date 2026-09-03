# Adaptive Thesis Routes

Choose a route from the app's current data and provider availability. Do not begin with a favorite ticker, commodity, or historical audit scenario unless the user supplied it.

## Select The Primary Question

1. Review the usability index and recent report coverage. Note over-tested entities, journeys, and open live-verification gaps.
2. Scan one information-rich starting surface such as SITREP, Portfolio, Equity Research overview, Macro snapshot, Prediction Markets screener, Crypto screener, or provider diagnostics.
3. Generate a small set of candidate questions from visible anomalies, events, divergences, concentrations, valuation gaps, repricing, liquidity conditions, or coverage failures.
4. Prefer the candidate with the best combination of:
   - provider-backed and sufficiently fresh evidence;
   - a real decision or research consequence;
   - two or more independent Gamma evidence lanes;
   - a meaningful cross-tab handoff or saved-workflow path;
   - an explicit way to disconfirm the idea;
   - incremental coverage versus recent audits.
5. Record the chosen provisional thesis before deeper investigation. Do not rewrite the initial thesis after seeing the outcome; add revisions chronologically.

Choose one primary journey. Start a second only when the first is blocked before meaningful research begins, and preserve the first blocker in the report.

## Minimum Thesis Contract

Record:

- research question;
- provisional claim;
- asset, portfolio, relationship, or regime in scope;
- time horizon;
- initial evidence and its provenance/freshness;
- expected supporting evidence;
- likely contradictory evidence;
- falsifier or kill condition;
- hypothetical expression, if useful, with explicit non-execution framing.

At conclusion, state thesis confidence and data-quality confidence separately.

## Route Families

The sequences below are examples. Reorder or skip surfaces when the app's data suggests a better coherent route.

### Portfolio Or Rebalance Research

Possible flow: Portfolio → Risk → Strategy Lab → Risk comparison → Copilot memo.

Test concentration, currency, factor, drawdown, contribution, and history coverage before proposing a hypothetical rebalance. Preserve the distinction between the live account and a research book. Never apply a rebalance or mutate the account.

### Single Equity Or Sector

Possible flow: SITREP or Equity Research → Fundamentals → peers/DCF/reverse valuation → Options or Risk → Copilot artifact.

Test identity continuity, instrument support, price/filing basis alignment, scenario assumptions, peer provenance, and handoffs. An ETF or non-US issuer may deliberately exercise an unsupported state.

### Macro Or Cross-Asset Regime

Possible flow: SITREP → Macro → Commodities or Prediction Markets → Equity Research/Strategy Lab → synthesis.

Test time-base labels, release dates, proxy basis, country/region coverage, lead-lag interpretation, and whether event or market evidence genuinely corroborates the macro claim.

### Commodity Or Event Thesis

Possible flow: SITREP → Commodities overview/curve/inventories → Macro → Prediction Markets/Sealanes → listed expression or memo.

Test contract identity, current/prior timestamp pairing, spot/proxy/futures distinctions, units, curve persistence, inventory freshness, and the honesty of maritime or event-market gaps.

### Prediction Market Or Crypto Thesis

Possible flow: screener → contract/token detail → history/liquidity/related comparison → Macro or other domain context → Copilot synthesis.

Test venue/chain identity, search ranking, stale or broken labels, probability/price basis, liquidity depth, related-market heuristics, calibration coverage, and whether missing wallet/flow detail is labeled rather than inferred.

### Options Or Volatility Thesis

Possible flow: equity/portfolio signal → Options session → chain/surface/realized-versus-implied/probabilities → strategy payoff → Risk or Copilot.

Test visible symbol and expiry continuity, entitlement/session states, observed versus fitted values, pricing and Greek assumptions, polling behavior, and explicit non-execution language. Stop any collection session started by the audit.

### Unsupported Or Imported-Series Thesis

Possible flow: Gamma search → explicit unsupported state → Strategy Lab import or bounded Research Script Workspace → analysis → comparison/synthesis.

Use this route for emerging markets, unusual instruments, custom indices, private series, or other coverage outside a native provider. First test the native Gamma path. Then, if useful, obtain a narrowly scoped authoritative public dataset specifically to test ingestion. Record source URL, retrieval time, units, frequency, transformations, missing values, and whether Gamma expects prices, levels, or returns.

Do not complete the research in an external notebook and describe that as Gamma success. If Gamma cannot ingest the data shape, preserve the import attempt and classify the boundary as unsupported or broken.

## Cross-Examination

Before concluding, ask:

- Which visible fact would be most damaging to the thesis?
- Is the apparent signal a time-window, currency, unit, contract-roll, stale-cache, or proxy artifact?
- Does a second Gamma domain independently corroborate it?
- Did a handoff preserve the exact entity, sign, weight, horizon, expiry, scenario, and warnings?
- Is the proposed expression actually supported by Gamma, or merely imaginable outside the app?
- Would the conclusion change if only the freshest provider-backed evidence were retained?

If the answers cannot be established inside Gamma, reduce confidence or return `indeterminate`.
