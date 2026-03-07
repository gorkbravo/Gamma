# Risk Tab Logic (MyQuantWork) - Current Implementation Audit

This document reflects the current `Risk` tab implementation after the risk-math, Jensen alpha, and UX decluttering updates.

It covers:

- UI layout and interaction behavior
- async compute/data flow
- risk metric and VaR implementation details
- benchmark beta/correlation/Jensen alpha logic
- exclusions, coverage, warnings, and diagnostics
- chart rendering behavior
- known limitations / follow-on ideas

Primary implementation file:

- `src/ui/tabs/risk_tab.py`

Supporting analytics/data/services/models:

- `src/analytics/returns.py`
- `src/analytics/risk_metrics.py`
- `src/analytics/var.py`
- `src/models/portfolio.py`
- `src/services/market_data.py`
- `src/services/risk_free_rate.py`

## 1. Purpose

`RiskTab` computes portfolio risk metrics from the latest `PortfolioSnapshot` received from the Overview tab.

Current outputs include:

- Historical VaR / CVaR (covered portfolio)
- Parametric VaR (covered portfolio, sqrt-time scaling for horizon > 1)
- Coverage-scaled estimated total VaR / CVaR / Parametric VaR
- Daily / annual realized volatility
- Max drawdown
- Benchmark beta / correlation
- Jensen alpha (USD only, when FRED risk-free data is available)
- Concentration metrics (HHI, top-5 weight, effective bets)
- Symbol-level risk contribution table (contribution %, MCTR, component VaR)
- Excluded assets details (in collapsible Details section)
- Returns histogram with VaR overlays
- Drawdown (underwater) chart
- Warnings / diagnostics (in collapsible Details section + compact warning summary)

## 2. Dependencies and Inputs

`RiskTab` is initialized with:

- `IBKRClient` (`client`)
- `MarketDataService` (`market_data`)
- `MockDataService` (`mock_service`)
- `RiskFreeRateService` (`risk_free_service`)
- `base_currency`
- `default_lookback`

State kept on the tab:

- `self.snapshot: PortfolioSnapshot | None`
- `self.thread_pool: QThreadPool`
- `self._latest_request_id` (used to ignore stale worker results)

Snapshot flow:

- `OverviewTab` emits `snapshot_updated`
- connected to `risk_tab.set_snapshot(snapshot)`

## 3. UI Layout and UX Behavior

### 3.1 Main Layout (Top to Bottom)

1. Controls row
- Confidence (`90%`, `95%`, `99%`)
- Lookback (`126`, `252`, `504`)
- Horizon (`1`, `10`)
- Benchmark ticker input (default `SPY`)
- Beta window (`63`, `126`, `252`)
- `Compute Risk` button
- Status label

2. Compact diagnostics row
- Warning summary label (hidden when no warnings)
- `Details` toggle button (hidden when no details exist)

3. Risk Metrics group
- Covered VaR/CVaR/Parametric VaR
- Estimated total VaR/CVaR/Parametric VaR
- Daily/Annual Vol
- Max Drawdown
- Beta/Correlation/Jensen Alpha
- Risk coverage %, observation count, benchmark overlap

4. Risk Concentration group
- HHI
- Top-5 Weight
- Effective Bets

5. Symbol risk contribution table
- Intentionally compact height (roughly ~3 visible rows before scrolling)
- Prioritizes top contributors without letting the table dominate the tab

6. Charts group (side-by-side)
- Returns histogram (with VaR overlays)
- Drawdown curve (underwater chart)
- Chart heights are capped to avoid consuming excess vertical space

7. Collapsible Details panel (hidden by default)
- Excluded Assets group (only visible if there are exclusions)
- Messages group (only visible if warnings/errors exist)

### 3.2 Details Toggle Behavior

The Details UI is adaptive:

- Hidden entirely if there are no messages and no excluded assets.
- Toggle label shows counts when present:
  - e.g. `Details (W:2, X:1)`
- Warning summary row stays visible even when Details is collapsed.
- Message text and excluded-assets table live inside Details.

This is designed to keep primary risk information visible while preserving diagnostic transparency.

## 4. Async Compute Lifecycle (Thread-Safe)

### 4.1 `compute()`

When the user clicks `Compute Risk`:

- If no snapshot is available:
  - message `"No snapshot yet"`
  - return
- Build a thread-safe `RiskComputeRequest` on the UI thread:
  - deep copy of the snapshot
  - current UI parameters (confidence, lookback, horizon, beta window, benchmark)
- Increment and store `request_id`
- Disable controls
- Set status to `"Status: Computing..."`
- Start `Worker(self._compute_worker, request)` in `QThreadPool`

Worker signals:

- `finished -> _on_results`
- `error -> _on_error`
- `progress -> _on_progress`

### 4.2 Stale Result Protection

`_on_results(payload)` receives `request_id` and ignores results if they are not the latest request.  
This prevents race conditions where an older compute finishes after a newer one.

## 5. Compute Request Payload

`RiskComputeRequest` contains:

- `request_id`
- `snapshot` (deep-copied `PortfolioSnapshot`)
- `alpha`
- `lookback_days`
- `horizon_days`
- `beta_window`
- `benchmark_symbol`
- `base_currency`
- `recommended_min_obs` (currently `60`, diagnostic only)

This prevents background-thread reads of Qt widgets and mutable tab state.

## 6. Compute Pipeline (`_compute_worker`)

High-level flow:

1. Resolve portfolio value and horizon warnings
2. Load prices (mock/live)
3. Align prices / compute returns
4. Add cash return columns (`0.0`) where applicable
5. Build weights from `base_market_value`
6. Build a risk-eligible subset (`risk_returns_df`, `weights_aligned`)
7. Compute portfolio returns
8. Compute historical VaR/CVaR and parametric VaR
9. Compute vol + max drawdown
10. Compute benchmark beta/correlation/Jensen alpha
11. Compute concentration metrics
12. Compute symbol-level risk contribution outputs
13. Build `RiskResults` + payload back to UI thread

## 7. Portfolio Value and Coverage Logic

The tab tracks two portfolio values:

- `portfolio_value` (total portfolio value from snapshot)
- `covered_portfolio_value` (sum of included assets used in risk math)

Total portfolio value selection priority:

1. `snapshot.net_liquidation`
2. `snapshot.total_market_value + snapshot.total_cash`
3. fallback `0.0` with warning

Coverage ratio:

- `risk_coverage_ratio = covered_portfolio_value / portfolio_value` (when total > 0)

Why this matters:

- Risk-return math is computed on the covered subset.
- Covered VaR values are converted using `covered_portfolio_value`.
- Separate estimated total VaR values are shown by scaling covered VaR by `total / covered`.

Warnings are emitted when:

- coverage < 100% (covered vs estimated distinction)
- coverage < 95% (interpretability warning)

## 8. Price Loading (Mock vs Live)

### 8.1 `_load_prices(snapshot, lookback_days, progress_cb)`

Mock mode:

- Iterates snapshot positions
- Skips cash symbols (`CASH...`)
- Loads history via `mock_service.load_history(symbol)`

Live mode:

- Uses `client.get_contracts()`
- Calls `market_data.fetch_histories(contracts, lookback_days, progress_cb)`

### 8.2 Missing Histories / Errors

- Missing histories are tracked in both warnings and `excluded_assets`
- `market_data.drain_errors()` is appended to warnings

## 9. Price Alignment and Returns

Using `src/analytics/returns.py`:

### 9.1 `align_prices(prices)`

- Concatenates symbol price series into a DataFrame
- Uses `join="inner"` (strict overlapping timestamps only)
- Sorts index

Implication:

- One short/partial history can shrink the usable common sample materially.

### 9.2 `compute_returns(price_df)`

- Uses `pct_change()`
- Drops rows where all returns are `NaN`

If returns are empty:

- warning `"No return history available"`
- loaded symbols are marked excluded (`"Insufficient overlapping history"`)

## 10. Cash Handling

### `_ensure_cash_returns(snapshot, returns_df)`

Cash positions typically have no price history. The tab:

- identifies cash symbols with `base_market_value`
- adds zero-return columns (`0.0`) if missing

Effect:

- cash contributes to weights / concentration
- cash contributes zero return volatility

## 11. Weight Construction and Risk-Eligible Subset

### `_weights_for_symbols(snapshot, symbols)`

Weights are built from `PositionItem.base_market_value` and normalized by `compute_weights(values)`.

Exclusions:

- Any symbol in `returns_df` lacking `base_market_value` is marked:
  - `"Missing base market value"`

### 11.1 Matrix Alignment Fix (Important Correctness Change)

The tab now constructs:

- `risk_symbols` = symbols present in returns **and** weights
- `risk_returns_df` = `returns_df` restricted to `risk_symbols`
- `weights_aligned` = weights reindexed to `risk_returns_df.columns`

This prevents the previous covariance/weight ordering bug and dimension mismatches.

## 12. Portfolio Returns

Using `portfolio_returns(returns_df, weights)` from `src/analytics/risk_metrics.py`:

- aligns returns columns to `weights.index`
- computes row-wise weighted sum

Warnings:

- `"Return series too short for stable risk metrics"` when `< 2` observations
- diagnostic warning if observations are below the recommended threshold (default `60`)

## 13. VaR / CVaR Metrics

## 13.1 Historical VaR / CVaR (`historical_var_cvar`)

Using `src/analytics/var.py`:

- quantile at `1 - alpha`
- `VaR = -quantile`
- `CVaR = -mean(tail returns <= quantile)`

Outputs are return units and then converted to currency:

- covered historical VaR/CVaR use `covered_portfolio_value`
- estimated total VaR/CVaR are coverage-scaled

## 13.2 Parametric VaR (`parametric_var`)

Using `src/analytics/var.py`:

- `sigma = sqrt(w^T Σ w)`
- `VaR = z(alpha) * sigma`

Horizon handling:

- if `horizon_days > 1`, parametric VaR is scaled by `sqrt(horizon_days)`
- historical VaR/CVaR remain 1-day (warning shown)

### 13.3 Covariance Validation / Degenerate Guards

Before parametric calculations, the tab validates covariance:

- finite values only (no `NaN` / inf)
- non-negative diagonal variances (with a small tolerance)

If invalid:

- parametric VaR / contributions are skipped
- warnings explain why

The helper functions in `src/analytics/var.py` and `src/analytics/risk_metrics.py` also guard against:

- shape mismatches
- non-finite inputs
- non-positive variance

## 14. Volatility and Drawdown Metrics

From `src/analytics/risk_metrics.py`:

- `realized_vol(port_ret)`:
  - daily std dev
  - annualized by `sqrt(252)`
- `max_drawdown(port_ret)`:
  - computes underwater series from cumulative returns
  - returns minimum drawdown value

## 15. Benchmark Beta / Correlation / Jensen Alpha

### 15.1 `_beta_corr_alpha(...)`

Flow:

1. Load benchmark returns (`_load_benchmark_returns`)
2. Inner-join portfolio and benchmark returns
3. Record `benchmark_overlap_count`
4. Require at least `beta_window` observations for rolling metrics
5. Compute rolling beta/correlation and take latest valid values
6. For Jensen alpha:
   - currently only enabled for `USD` base currency
   - fetch USD risk-free daily returns from `RiskFreeRateService`
   - align portfolio / benchmark / risk-free
   - compute rolling Jensen alpha on excess returns
   - annualize latest alpha by `*252`

If any stage fails, warnings are returned and affected metrics remain `N/A`.

### 15.2 Risk-Free Data (`RiskFreeRateService`)

Current implementation:

- Source: FRED observations API
- Series: `SOFRINDEX`
- Converts SOFR Index to daily risk-free returns via `pct_change()`
- Reads `FRED_API_KEY` from environment (optional but recommended)
- Uses `CacheService` to avoid repeated downloads

If unavailable:

- Jensen alpha is omitted
- explicit warnings are shown (no silent `rf=0` fallback)

### 15.3 Benchmark Currency Conversion

`_convert_benchmark_to_base(...)`:

- if quote currency == base currency: no conversion
- else tries FX history via `market_data.fetch_fx_history(...)`
  - forward-fill only (`ffill`)
  - no backward-fill (avoids look-ahead)
- else tries spot FX via `market_data.fetch_fx_rate(...)`
  - emits warning that spot fallback was used

## 16. Concentration Metrics

`_concentration_metrics(weights)` uses normalized absolute weights:

- `HHI = Σ w_i^2`
- `Top-5 Weight = sum(largest 5 weights)`
- `Effective Bets = 1 / HHI` (if `HHI > 0`)

Returns `None` values on empty/degenerate inputs.

## 17. Symbol-Level Risk Contribution Outputs

Computed only when:

- covariance is valid
- `weights_aligned` is non-empty
- portfolio variance is positive

### 17.1 % of Portfolio Variance

Using `risk_contributions(weights, cov)`:

- contribution fraction = `w_i * (Σw)_i / (w^TΣw)`

These should sum to ~1.0 (subject to numerical precision).

### 17.2 MCTR

- `MCTR = (Σw) / sigma`

### 17.3 Component VaR

- component VaR (return units) = `weights * MCTR * z(alpha)`
- horizon-scaled by `sqrt(horizon_days)` when applicable
- converted to currency using `covered_portfolio_value`

## 18. Table Rendering

### 18.1 Risk Contribution Table (`_update_table`)

- Clears rows
- Uses `returns_df.columns` for display rows
- Sorts by contribution descending when contribution data exists
- Displays:
  - symbol
  - weight
  - symbol daily vol
  - contribution %
  - MCTR
  - component VaR
  - contribution bar

### 18.2 Compact Height Behavior (`_fit_contrib_table_height`)

The table is intentionally sized to a small fixed-height view (~3 rows + header) to keep more of the tab visible without excessive vertical scrolling.

### 18.3 Contribution Bar (`_make_contrib_bar`)

- Progress-bar style visualization
- Color encodes sign (positive vs negative contribution)
- Tooltip shows signed contribution %

## 19. Charts

### 19.1 Returns Histogram (`_plot_histogram`)

- Histogram of portfolio returns (`30` bins)
- Overlays historical and parametric VaR lines when available
- VaR lines are shown in return units (currency VaR divided by covered value)
- Legend is placed on the right (`upper right`) to avoid the left-tail VaR area

### 19.2 Drawdown Curve (`_plot_drawdown`)

- Replaces the old cumulative-return chart
- Computes drawdown series from cumulative returns:
  - `cum = (1 + returns).cumprod()`
  - `peak = cum.cummax()`
  - `drawdown = (cum / peak) - 1`
- Renders line + shaded underwater area
- Includes zero baseline

### 19.3 Empty Chart State (`_show_plot_message`)

If no data is available:

- axes are cleared and styled
- centered message is shown
- ticks are hidden

## 20. Warnings, Messages, and Status UX

### 20.1 Warning Collection

Warnings may include:

- missing histories
- market data service errors
- no returns / no weights
- short return history
- low observation-count diagnostic (`< 60` recommended)
- invalid covariance / non-positive variance
- coverage warnings (<100% / <95%)
- benchmark overlap insufficiency
- benchmark history / FX conversion failures
- Jensen alpha unavailable (risk-free fetch, unsupported base currency, etc.)
- horizon interpretation warning

### 20.2 Message Area and Summary

- Full warnings/errors are written to the message area
- Message area is hidden when empty
- A compact warning summary line is shown near the top when warnings exist
  - shows count and first warning snippet

### 20.3 Progress and Status

- live history loading updates status:
  - `"Status: Loading {current}/{total} ({symbol})"`
- compute start:
  - `"Status: Computing..."`
- success:
  - `"Status: Done"`
- failure:
  - `"Status: Error"`

## 21. Result Model (`RiskResults`)

`RiskResults` now includes both core and diagnostic fields, including:

- `historical_var`, `historical_cvar`, `parametric_var` (covered values)
- `historical_var_total_estimate`, `historical_cvar_total_estimate`, `parametric_var_total_estimate`
- `covered_portfolio_value`
- `risk_coverage_ratio`
- `aligned_obs_count`
- `benchmark_overlap_count`
- standard metrics and warnings/exclusions

See `src/models/portfolio.py`.

## 22. Known Limitations / Current Tradeoffs

1. Strict price alignment (`join="inner"`)
- Can materially reduce sample size when one asset has sparse history.
- This is surfaced better now (obs counts/warnings), but the alignment policy is still strict.

2. Jensen alpha currently USD-only
- Uses a USD risk-free series from FRED (`SOFRINDEX`).
- Non-USD base currencies currently return Jensen alpha as unavailable.

3. Historical VaR/CVaR remain 1-day
- Multi-day horizon scaling is only applied to parametric VaR/component VaR.

4. Coverage-scaled total VaR is an estimate
- It is not a full-model estimate for excluded assets.
- It is a proportional scaling of covered-portfolio risk.

5. Table is intentionally compact
- Good for layout clarity, but users must scroll for full contributor list.

## 23. Suggested Follow-On Work

1. Add a chart mode switch for the right chart
- `Drawdown` / `Rolling Vol` / `Rolling VaR`

2. Add risk coverage badges/colors
- Highlight low-coverage states visually in the metrics panel

3. Add stress/scenario analysis panel
- More actionable than another single summary metric

4. Consider alternative alignment policies
- Pairwise covariance or symbol-level screening before strict intersection

5. Add VaR backtesting diagnostics
- Simple exceedance chart / exception count would complement VaR outputs well

## 24. Simplified Call Graph

`compute()`  
-> `_build_request()` (UI thread snapshot of params + deep-copied snapshot)  
-> worker thread: `_compute_worker(request)`  
-> `_load_prices()`  
-> `align_prices()` / `compute_returns()`  
-> `_ensure_cash_returns()` / `_weights_for_symbols()` / `compute_weights()`  
-> build `risk_returns_df` + `weights_aligned`  
-> `portfolio_returns()`  
-> `historical_var_cvar()` / `parametric_var()`  
-> `realized_vol()` / `max_drawdown()`  
-> `_beta_corr_alpha()` -> `_load_benchmark_returns()` -> `_convert_benchmark_to_base()` -> `RiskFreeRateService` (for Jensen alpha)  
-> `_concentration_metrics()`  
-> risk contributions / MCTR / component VaR  
-> UI thread: `_on_results()`  
-> `_update_metrics()` / `_update_table()` / `_update_excluded_assets()` / `_plot_histogram()` / `_plot_drawdown()` / `_show_warnings()`

## 25. Files to Review When Modifying Risk Logic

- `src/ui/tabs/risk_tab.py` (UI + orchestration + UX behavior)
- `src/analytics/returns.py` (alignment and returns)
- `src/analytics/risk_metrics.py` (weights/returns/vol/drawdown/contributions)
- `src/analytics/var.py` (historical/parametric VaR)
- `src/models/portfolio.py` (`PortfolioSnapshot`, `RiskResults`)
- `src/services/market_data.py` (histories / FX data)
- `src/services/risk_free_rate.py` (FRED SOFR Index risk-free returns for Jensen alpha)
