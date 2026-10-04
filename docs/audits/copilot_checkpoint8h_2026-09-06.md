# Checkpoint 8H — exact Research scope working analyses

## Contract

`run_research_basket_analysis` accepts 1–100 distinct listed-market symbols, positive fractional weights summing to one, an explicit benchmark, and a bounded integer lookback. It rejects incomplete or malformed input instead of using the active scope, clipping, truncating or silently reweighting. The existing `run_research_scope_analysis` remains compatible with its active-scope callers.

The shared preflight recognizes explicit Research basket requests and bypasses single-company resolution. The mock fallback accepts exact bracketed weights, for example: `Analyze a Research scope basket [AAPL:60%, MSFT:40%] against SPY over 252 days`. Capable models translate ordinary language into the strict tool arguments.

Gamma's existing ResearchService supplies metrics, constituent diagnostics, benchmark coverage and provenance. This action opts into an observation limit so providers returning excess history cannot extend the requested analytical window; constituent statistics, basket returns and benchmark alignment use that same bound. Missing or unexpected constituents prevent materialization and suppress partial-basket metrics. Missing benchmark evidence is explicitly degraded. Cumulative-return charts retain at most 400 points per series; statistics use all observations within the bound. Both model runners receive statistics and the working reference without chart geometry.

Successful output uses the existing seven-day session-ephemeral working record and `copilot.research-scope-working-analysis.v1` target. Equity Research / Scope displays the retained inputs, diagnostics, chart, source, warnings and expiry. Opening does not recompute, save, update the shared equity selection or overwrite the live scope draft. Return to live scope restores the ordinary surface; expired or discarded records cannot masquerade as live analytics.

## Validation

- Three backend acceptance tests cover unloaded deterministic execution, exact inputs, persisted charts, restart replay, idempotent materialization, saved-research invariance, discard/reopen rejection, strict invalid inputs, simulated Responses continuation, SDK observation compatibility, unrelated selected-symbol isolation, and missing-constituent withholding.
- All 437 frontend tests passed, including retained rendering, expiry, typed target validation, zero load/save callbacks and unchanged live draft.
- TypeScript typecheck and production build passed. The build retains the existing IV SVG interaction and Surface3D unused-prop warnings.
- The broader Copilot, SDK smoke and Operator eval run passed 161 tests. After adding the opt-in observation bound, four focused basket and legacy scope tests passed.
- Browser acceptance opened the retained session through Copilot's run inspector into Equity Research / Scope at measured widths of 1800, 1024 and 640 CSS pixels with no horizontal overflow or console errors. A final narrow check verified the styled return control and readable dates; Return to live restored the ordinary empty analysis and original single-ticker builder rather than loading the temporary basket.

This is deterministic and simulated-model acceptance. No live OpenAI or live market-provider acceptance is claimed. Remaining representative analyses, generalized same-run approvals/recovery, and release validation remain open.
