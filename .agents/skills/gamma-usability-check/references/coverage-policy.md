# Surface Coverage Policy

Use this policy to prevent natural thesis selection from repeatedly favoring Equity Research, Fundamentals, Portfolio, and other broadly applicable surfaces while specialist surfaces go untested.

## Two Separate Tracks

Every successful audit has:

1. a **primary thesis journey** selected for coherence and decision value; and
2. one **coverage mission** selected for coverage debt.

Do not distort the primary thesis to include an unrelated tab. If the primary journey already uses the selected coverage target substantively, it satisfies both tracks. Otherwise run one bounded, standalone micro-mission after the primary journey.

The goal is rotation across audits, not shallow traversal of every tab in one audit.

## Maintain The Coverage Ledger

Use `docs/audits/usability/coverage-ledger.md`. If it does not exist, create it from the current live top-level navigation and current roadmap rather than copying a historical tab list from this skill.

On first creation, backfill only the most recent audits whose reports explicitly evidence substantive surface use. Leave uncertain history blank or `unverified`; do not infer coverage from report titles or index summaries.

Use one row per current top-level surface:

```markdown
| Surface | Last deep use | Last micro-mission | Environment | Provider/data mode | Last result | Open gap / next mission |
| --- | --- | --- | --- | --- | --- | --- |
```

Add newly visible surfaces. Mark removed or renamed surfaces without deleting their history. Link the audit report from updated date cells. Do not credit a failed preflight or a landing-page visit as coverage.

Environment qualification is part of the coverage record. Provider-only, mock, disconnected, delayed, or entitlement-limited evidence does not replace an IBKR-integrated pass for a broker-dependent surface.

## Select The Coverage Target

Choose the available surface with the highest practical coverage debt. Prioritize, in order:

1. never substantively exercised;
2. exercised only with mock data, disconnected IBKR, or an unavailable provider;
3. no deep use across the three most recent successful audits;
4. affected by recent product changes or an unresolved regression risk;
5. capable of providing a useful contradiction or independent evidence lane for the current thesis.

Do not select a surface twice as the coverage target while another current, safely exercisable surface has never received provider-backed substantive coverage. If the highest-debt surface is unavailable because of provider, entitlement, market-hours, or safety constraints, record the debt and choose the next available surface. Do not count the unavailable attempt as coverage.

## What Counts As Coverage

A surface receives **deep use** only when it is part of the primary journey and the audit:

- enters with a concrete user question;
- loads provider-backed or legitimate imported data;
- exercises at least one meaningful analytical control or drill-down;
- interprets the result in the thesis or decision;
- checks visible provenance, freshness, warnings, and state continuity where relevant.

A surface receives **micro-mission coverage** when the same conditions are met for a narrower standalone question and the result is recorded independently of the primary thesis.

Opening the tab, confirming that it renders, scrolling a landing page, or observing an expected unavailable state is not substantive coverage.

## Specialist Micro-Mission Patterns

Adapt these patterns to current app capabilities and data. They are purpose prompts, not fixed scripts.

- **Prediction Markets:** Find a current, sufficiently liquid contract connected to a material event; inspect probability history, time to resolution, liquidity, related markets, venue provenance, and whether the contract adds information beyond headlines.
- **Crypto:** Identify a current liquidity, volume, or relative-performance dislocation; verify token, chain, venue, pricing basis, and whether detail/history supports the apparent signal.
- **Commodities:** Investigate one visible curve, inventory, spread, or event divergence; verify contract, units, timestamps, provider, and prior-period basis.
- **Sealanes or maritime:** Test one live route, congestion, or disruption question; verify vessel/route scope, temporal coverage, provider health, and the honesty of sparse data.
- **Options:** Test one event-volatility or realized-versus-implied question; verify symbol, expiry, market-data mode, observed/fitted distinction, assumptions, and non-execution framing.
- **Strategy Lab or imported data:** Import or reuse one bounded series to answer a comparison, regime, or stress question; verify expected shape, units, transforms, provenance, and handoff continuity.
- **Macro:** Test one current release, policy, rates, trade, or cross-asset divergence; verify release dates, revisions, frequency, proxy basis, and independent corroboration.
- **Fundamentals or Equity Research:** When these carry the highest debt, use a less-covered issuer type, region, ETF, peer set, or valuation path rather than repeating the same US mega-cap workflow.

Stop the micro-mission once the purpose question has a supported answer, an evidenced blocker, or an honest unsupported result. It is not a second sprawling thesis.
