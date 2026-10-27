# Usability Audits

Live product workflow audits and research-thread evaluations.

## Audits

- [`gamma_usability_findings_2026-10-27.md`](./gamma_usability_findings_2026-10-27.md) (current): verify-only live IBKR retest of the 2026-10-21 fixes plus the Event Book ladder and `us_macro_events`; every retested P0/P1 holds after nine follow-up fixes found live (Commodities SITREP 50 s → ~11 s, FOMC dropped on its first day, partial calls counted as failures, Operator SEC warning and transcript noise, Retry on cancelled turns).

- [`gamma_usability_findings_2026-10-21.md`](./gamma_usability_findings_2026-10-21.md): historical - live IBKR Brent–WTI / Strait of Hormuz trade-idea audit; Prediction Markets and the Commodities → Strategy Lab → Risk loop carried the thesis, the Operator tool-name, Options symbol-change and Strategy Lab → Risk defects are confirmed fixed, and two new P0s were found (Add Leg duplicate-key app wedge, crack spreads computed from week-old history but stamped current).

- [`options_snapshot_live_acceptance_2026-10-06.md`](./options_snapshot_live_acceptance_2026-10-06.md) (current): two real SPY/TWS surfaces captured with exact payload preservation, retained across runtime reconstruction, and compared with the production observed-strike helper; partial coverage produces honest N/A values.

- [`gamma_usability_findings_2026-09-04.md`](./gamma_usability_findings_2026-09-04.md): historical - IBKR-integrated QQQ-minus-SPY thesis audit focused on Research Operator and Strategy Lab Script; the live provider gate passed and Script safe preview retained immutable provenance, while a P1 invalid-tool-name defect blocked the Operator-to-Script loop.

- [`gamma_usability_findings_2026-09-03-3.md`](./gamma_usability_findings_2026-09-03-3.md) (current): IBKR-integrated Gold-versus-duration audit; Strategy Lab Backtest/Regime Stress rejected the hedge thesis, while commodity-history loss and mixed Risk/account state exposed two P1 cross-tab trust defects.

- [`gamma_usability_findings_2026-09-03-2.md`](./gamma_usability_findings_2026-09-03-2.md) (current): live IBKR verification of the 2026-09-03 fixes; four of five acceptance criteria passed, Strategy Lab supported a public QQQ-minus-SPY thesis, while Copilot workbench loss and cross-symbol stale strategy state remain P1 defects.

- [`gamma_usability_findings_2026-09-03.md`](./gamma_usability_findings_2026-09-03.md) (current): IBKR-integrated GOOGL concentration/hedge thesis partially confirmed; live Portfolio/Risk/Fundamentals/Options worked, while P1 ATM-IV interpolation, account-sizing, and Copilot-grounding defects blocked a clean account-matched expression.

- [`gamma_usability_findings_2026-09-01.md`](./gamma_usability_findings_2026-09-01.md) (current): degraded provider-backed AAPL thesis journey; yfinance/SEC evidence rejected the thesis, while P1 benchmark loss into Risk, run-state/provenance contradictions, and Copilot terminal failure blocked a clean end-to-end result.

- [`gamma_portfolio_verification_2026-07-27.md`](./gamma_portfolio_verification_2026-07-27.md) (current): deterministic Portfolio completion-contract pass; mock runtime, persistence/restart, degraded-state, browser, production, packaged-backend, and desktop gates passed. Current live TWS verification was unavailable, so the roadmap completion marker remains withheld.

- [`gamma_usability_findings_2026-07-24.md`](./gamma_usability_findings_2026-07-24.md) (current): targeted live TWS regression pass; live XLE IV, signed Strategy Lab → isolated Risk, and provider-native Copilot streaming passed. Confirmed fresh Commodities changes still disappear on drill/cached reload; found Copilot provider-usage misattribution and a Portfolio quote-timeout/worker-budget mismatch.

- [`gamma_usability_findings_2026-07-08.md`](./gamma_usability_findings_2026-07-08.md) (current): live IBKR weekday audit during the Iran-strike oil spike; confirmed the Commodities `% CHG` P0 fix and the single-day corroboration path live, first end-to-end trade verdict across three audits. New: intermittent app-wide freeze on Strategy Lab → Risk (P0), Options polling loop, Copilot returns no card, Risk book/account blend.
- [`gamma_usability_findings_2026-06-27.md`](./gamma_usability_findings_2026-06-27.md): historical - live IBKR weekend trade-idea audit; found a P0 in the Commodities headline "% CHG" and a P1 daily-reference gap, both since fixed and verified live on 2026-07-08.
- [`gamma_usability_findings_2026-06-15.md`](./gamma_usability_findings_2026-06-15.md): historical - current-state update of the live IBKR-connected trade-idea audit, incorporating recent handoff/provenance commits and a targeted Fundamentals retest.
- [`gamma_usability_findings_2026-06-07.md`](./gamma_usability_findings_2026-06-07.md): historical - prior live usability audit and prioritized improvement guidance that drove Strategy Lab, Options, Copilot, handoff, related-market, and provenance fixes.
