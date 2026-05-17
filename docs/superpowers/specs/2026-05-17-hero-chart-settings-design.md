# Hero Chart Settings Design

## Context

Gamma has several price-chart surfaces, but not all charts should expose chart-level customization. The requested settings belong only on hero price charts where the user is studying a selected asset, especially equity price charts in Fundamentals and Research. Routine macro, commodity, ranking, and supporting line charts should stay simple.

This fits the Gamma roadmap because it is read-only, data-first, and keeps derived logic such as moving averages in reusable chart/view-model helpers rather than burying analytics inside the UI.

## Goals

- Add a compact settings button in the hero chart header using the approved header-icon placement.
- Let eligible hero charts choose price style: line by default, candlesticks when OHLC data exists.
- Let eligible hero charts toggle volume overlay when volume data exists.
- Let eligible hero charts toggle moving averages computed by Gamma from price/close history.
- Keep these controls scoped to explicit hero price chart instances, not every `TimeSeriesChart`.
- Preserve provenance and data availability: disabled options should say when the required OHLCV data is not available.

## Non-Goals

- Do not add global chart customization across the app.
- Do not fake candlesticks from close-only data.
- Do not turn this into a trading or execution surface.
- Do not add new chart libraries; the existing `lightweight-charts` dependency supports the needed series types.

## Current Architecture

`frontend/src/components/TimeSeriesChart.svelte` is the reusable chart renderer. It currently accepts line and area series and renders them with `lightweight-charts`.

The known hero price chart surfaces are:

- `frontend/src/views/FundamentalsView.svelte`: company overview market-context price chart, backed by `overview.price_history`.
- `frontend/src/views/ResearchView.svelte`: single-ticker price mode in the scope-analysis hero chart, backed by `result.primary_price_points`.
- `frontend/src/views/CryptoView.svelte`: token deep-dive hero chart, backed by `history.points`.

Current data support:

- Fundamentals equity history is close-only through `FundamentalsPricePoint`.
- Research single-ticker history is close-only through generic `TimeSeriesPoint`.
- Crypto token history has price, market cap, and total volume through `CryptoPricePoint`, so volume overlay is viable there now.
- Candlesticks require OHLC data and should stay disabled until OHLC is present.

## Data Model

Add a frontend chart data shape for hero price charts:

```ts
interface HeroPricePoint {
  time: UTCTimestamp;
  close: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
}
```

This shape is view-model level. It allows each tab to adapt its existing API payload without forcing every domain to expose OHLCV immediately.

For equity candlesticks and volume, extend backend history models later or in the implementation if IBKR bars are available:

- `FundamentalsPricePoint`: add optional `open`, `high`, `low`, `close`, `volume`, with `price` kept as a compatibility alias for close.
- Research `primary_price_points`: either remains close-only for V1 or receives a richer equity history payload behind a separate field if broad schema churn is too high.

## Derived Analytics

Moving averages are Gamma-owned logic:

- Implement simple moving averages over the close series.
- Supported windows: 20, 50, 200.
- A point appears only once the full window is available.
- Null, non-finite, and duplicate timestamps are filtered through existing chart normalization rules.

The helper should live outside Svelte components, likely in `frontend/src/lib/chart-data.ts` or a small hero-chart view-model helper, with unit tests.

## UI Design

Create a small hero-only wrapper component, tentatively `HeroPriceChart.svelte`.

Responsibilities:

- Render a `TimeSeriesChart` with the selected style and overlays.
- Render a compact gear/settings button in the panel header area supplied by the caller.
- Open a sharp-corner dropdown aligned to the button.
- Persist settings by chart key, for example:
  - `fundamentals:equity`
  - `research:single-ticker`
  - `crypto:token`

Default settings:

- Price style: `line`
- Volume overlay: off
- Moving averages: none

Dropdown controls:

- Price: `Line` / `Candles`
- Volume: `Off` / `On`
- Moving averages: `20`, `50`, `200` as independent checkboxes

Unavailable states:

- Disable `Candles` when any displayed point lacks `open`, `high`, `low`, or `close`.
- Disable `Volume` when no displayed point has finite volume.
- Keep moving-average controls available whenever close history exists.

## Chart Rendering

Extend `TimeSeriesChart.svelte` narrowly:

- Add candlestick series support using `CandlestickSeries`.
- Add histogram support using `HistogramSeries`, assigned to a volume price scale when used.
- Keep existing line/area behavior unchanged for all current callers.

Do not require existing chart callers to pass new fields. The new series types are additive.

## Initial Rollout

Implement in this order:

1. Shared chart data helpers and tests.
2. Additive `TimeSeriesChart` support for candlestick and histogram series.
3. Hero settings component and persistence.
4. Fundamentals overview price chart.
5. Research single-ticker price chart.
6. Crypto token hero chart for volume overlay and moving averages. Candles remain disabled unless OHLC is added.

If IBKR daily bars can be exposed with low churn, include optional OHLCV in Fundamentals during the same implementation. If it requires deeper provider refactoring, ship the UI with candlesticks disabled for close-only equity data and leave the backend OHLCV extension as the next step.

## Error Handling

- If a selected chart setting becomes unavailable after data changes, fall back to line style for rendering while preserving the user's setting in storage.
- The dropdown should show availability labels rather than warnings in the primary chart surface.
- Empty charts keep the existing stable `CHART UNAVAILABLE` or domain-specific empty messages.

## Testing

- Unit-test moving-average calculation.
- Unit-test chart-data normalization with duplicate and invalid points.
- Add component or view-model tests for settings availability:
  - close-only data disables candles and volume.
  - volume data enables volume overlay.
  - full OHLC data enables candlesticks.
- Run frontend tests and build validation after implementation.

## Acceptance Criteria

- Hero chart settings appear only on approved hero price charts.
- The settings button uses the header placement, not an in-chart overlay.
- Existing non-hero charts do not change behavior or show new controls.
- Moving averages render from Gamma-owned calculations.
- Candlestick and volume controls are data-aware and never fake unavailable data.
- The UI remains compact, flat, and token-aligned with Gamma design principles.
