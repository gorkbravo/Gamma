# Gamma Usability Coverage Ledger

This ledger records substantive usability coverage only. Dates link to the audit that produced the evidence; environment and degradation are part of the credit.

| Surface | Last deep use | Last micro-mission | Environment | Provider/data mode | Last result | Open gap / next mission |
| --- | --- | --- | --- | --- | --- | --- |
| Portfolio | [2026-09-03](./gamma_usability_findings_2026-09-03-2.md) | — | IBKR-integrated live | IBKR snapshot quotes; isolated one-point local history | Worked with degradation | Retest multi-session history, restart persistence, and historical attribution. |
| Risk | [2026-09-03](./gamma_usability_findings_2026-09-03-3.md) | — | IBKR-integrated live | Strategy Lab GLD/TLT aggregate stream; yfinance histories | Worked with degradation | Fix atomic source selection and account-panel clearing on Strategy Lab handoff; verify MC result identity/freshness. |
| Options | [2026-09-03](./gamma_usability_findings_2026-09-03-2.md) | N/A — primary journey | IBKR-integrated live | IBKR `Auto`, Max Surface; yfinance realized volatility | Worked with degradation | Fix cross-symbol strategy invalidation; verify executable liquidity separately. |
| SITREP | [2026-09-03](./gamma_usability_findings_2026-09-03-3.md) | — | IBKR-integrated live | yfinance, Treasury/FRED, IBKR FX/futures, prediction venues, RSS | Worked with degradation | Improve first-load latency and provider attribution; retest progressive loading. |
| Equity Research | [2026-09-01](./gamma_usability_findings_2026-09-01.md) | — | Provider-backed; IBKR disconnected | yfinance historical equity/benchmark data | Worked with degradation | Retest benchmark/peer comparison and Equity Research → Risk handoff live. |
| Strategy Lab | [2026-09-03](./gamma_usability_findings_2026-09-03-3.md) | [2026-09-03](./gamma_usability_findings_2026-09-03-2.md) | IBKR-integrated; public histories | yfinance GLD/TLT/SPY; Gamma Backtest, Regime Stress, Saved Runs, Risk handoff | Worked with degradation | Fix composer state loss and Risk handoff identity; verify a provider-backed Script run. |
| Macro | [2026-09-03](./gamma_usability_findings_2026-09-03-3.md) | — | IBKR-integrated live | Treasury/FRED macro series plus IBKR FX context | Worked | Verify event-window/revision depth and a durable Macro lens into Strategy Lab. |
| Prediction Markets | Unverified | — | — | — | Unverified | Verify one liquid contract, probability history, resolution terms, liquidity, venue, and related markets. |
| Crypto | Unverified | — | — | — | Unverified | Verify one venue-specific liquidity or relative-performance dislocation with chain and pricing basis. |
| Fundamentals | [2026-09-03](./gamma_usability_findings_2026-09-03.md) | — | IBKR-integrated mixed-provider | SEC/company history, yfinance fallback, IBKR price context | Worked with degradation | Retest Reverse Valuation and Reference/Filings after fetch failures; verify current-source identity. |
| Commodities | [2026-09-03](./gamma_usability_findings_2026-09-03-3.md) | — | IBKR-integrated live | IBKR Gold futures curve/history plus FRED macro correlations | Worked with degradation | Fix loaded-history loss in Commodities → Strategy Lab; reconcile front-spread versus full-curve labels. |
| Sealanes | Unverified | — | — | — | Unverified | Verify one route/congestion question with vessel scope, time coverage, provider health, and sparse-data honesty. |
| Copilot | Unverified | — | IBKR-integrated; public AAPL context | OpenAI Responses plus Gamma Options tool | Blocked | Preserve Options workbench across handoff, then complete a trustworthy provider-native terminal pass with persistence and export. |

On first creation, only the 2026-09-01 and initial 2026-09-03 audits were backfilled because their full reports explicitly evidenced substantive use. The 2026-09-03 fix-verification run added Strategy Lab and refreshed Portfolio/Risk/Options. Failed Copilot terminal runs are not credited as substantive coverage.
