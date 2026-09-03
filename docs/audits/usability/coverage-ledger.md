# Gamma Usability Coverage Ledger

This ledger records substantive usability coverage only. Dates link to the audit that produced the evidence; environment and degradation are part of the credit.

| Surface | Last deep use | Last micro-mission | Environment | Provider/data mode | Last result | Open gap / next mission |
| --- | --- | --- | --- | --- | --- | --- |
| Portfolio | [2026-09-03](./gamma_usability_findings_2026-09-03.md) | — | IBKR-integrated live | IBKR snapshot quotes; one-point local history | Worked with degradation | Retest multi-session history, restart persistence, and historical attribution. |
| Risk | [2026-09-03](./gamma_usability_findings_2026-09-03.md) | — | IBKR-integrated live | Live account plus yfinance histories | Worked with degradation | Reconcile 252D identity and run a bounded stress/Monte Carlo mission. |
| Options | [2026-09-03](./gamma_usability_findings_2026-09-03.md) | N/A — primary journey | IBKR-integrated live | IBKR `Auto`, Max Surface; yfinance realized volatility | Worked with degradation | Retest fitted ATM IV, tenor-matched RV-IV, live liquidity, and account-sized strategies. |
| SITREP | [2026-09-01](./gamma_usability_findings_2026-09-01.md) | — | Provider-backed; IBKR disconnected | yfinance, FRED/Treasury, EIA/FRED fallback, prediction venues, RSS | Worked with degradation | Retest progressive loading and entity-tag relevance with IBKR connected. |
| Equity Research | [2026-09-01](./gamma_usability_findings_2026-09-01.md) | — | Provider-backed; IBKR disconnected | yfinance historical equity/benchmark data | Worked with degradation | Retest benchmark/peer comparison and Equity Research → Risk handoff live. |
| Strategy Lab | Unverified | — | — | — | Unverified | Highest debt: import a bounded series, apply a meaningful transform, and verify handoff/provenance. |
| Macro | Unverified | — | — | — | Unverified | Verify one current release or rates divergence, revisions, frequency, and corroboration. |
| Prediction Markets | Unverified | — | — | — | Unverified | Verify one liquid contract, probability history, resolution terms, liquidity, venue, and related markets. |
| Crypto | Unverified | — | — | — | Unverified | Verify one venue-specific liquidity or relative-performance dislocation with chain and pricing basis. |
| Fundamentals | [2026-09-03](./gamma_usability_findings_2026-09-03.md) | — | IBKR-integrated mixed-provider | SEC/company history, yfinance fallback, IBKR price context | Worked with degradation | Retest Reverse Valuation and Reference/Filings after fetch failures; verify current-source identity. |
| Commodities | Unverified | — | — | — | Unverified | Verify one live curve/inventory/spread question with units, contract basis, timestamp, and corroboration. |
| Sealanes | Unverified | — | — | — | Unverified | Verify one route/congestion question with vessel scope, time coverage, provider health, and sparse-data honesty. |
| Copilot | Unverified | — | — | — | Unverified | Complete a trustworthy provider-native terminal pass with current multi-surface state, persistence, and export. |

On first creation, only the 2026-09-01 and 2026-09-03 audits were backfilled because their full reports explicitly evidenced substantive use. Failed Copilot terminal runs were not credited as coverage.
