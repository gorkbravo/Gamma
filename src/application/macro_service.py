from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.application.prediction_market_service import PredictionMarketScreenerRequest, PredictionMarketService
from src.models.macro import (
    MacroCurveNode,
    MacroDivergenceRecord,
    MacroExpectationRecord,
    MacroEventRecord,
    MacroLinkedMarketRecord,
    MacroMetricRecord,
    MacroRatesPolicySummary,
    MacroSeriesHistory,
    MacroSeriesPoint,
    MacroSnapshotCard,
    MacroSnapshotPayload,
    MacroThemeComparison,
)
from src.models.prediction_markets import PredictionMarketRecord
from src.services.macro_adapters import FredMacroAdapter, TreasuryCurveAdapter, USMacroEventsAdapter
from src.utils.time import now_utc


SERIES_REGISTRY: dict[str, dict[str, Any]] = {
    "us-fed-funds": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "DFF",
        "title": "Fed Funds Rate",
        "unit": "pct",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot", "rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "policy_rate",
    },
    "us-2y-yield": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "DGS2",
        "title": "US 2Y Treasury Yield",
        "unit": "pct",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot", "rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "front_end_rate",
    },
    "us-10y-yield": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "DGS10",
        "title": "US 10Y Treasury Yield",
        "unit": "pct",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot", "rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "long_rate",
    },
    "us-30y-yield": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "DGS30",
        "title": "US 30Y Treasury Yield",
        "unit": "pct",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
    },
    "us-real-10y-yield": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "DFII10",
        "title": "US 10Y Real Yield",
        "unit": "pct",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot", "rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "real_rate",
    },
    "us-5y-breakeven": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "T5YIE",
        "title": "US 5Y Breakeven Inflation",
        "unit": "pct",
        "frequency": "daily",
        "theme": "inflation",
        "mode_tags": ["snapshot", "cross_asset", "rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "breakeven_short",
    },
    "us-10y-breakeven": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "T10YIE",
        "title": "US 10Y Breakeven Inflation",
        "unit": "pct",
        "frequency": "daily",
        "theme": "inflation",
        "mode_tags": ["snapshot", "cross_asset", "rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "breakeven_long",
    },
    "us-unemployment-rate": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "UNRATE",
        "title": "US Unemployment Rate",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "growth",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 900,
        "ttl_hours": 36,
        "comparison_key": "labor_slack",
    },
    "us-dollar-broad": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "DTWEXBGS",
        "title": "Broad Dollar Index",
        "unit": "index",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "fx_proxy",
    },
    "us-hy-oas": {
        "kind": "raw",
        "region": "US",
        "provider_series_id": "BAMLH0A0HYM2",
        "title": "US High Yield OAS",
        "unit": "pct",
        "frequency": "daily",
        "theme": "recession_risk",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "credit_proxy",
    },
    "eu-policy-rate": {
        "kind": "raw",
        "region": "EU",
        "provider_series_id": "IRSTCI01EZM156N",
        "title": "ECB Policy Rate Proxy",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "policy",
        "mode_tags": ["snapshot", "rates_policy"],
        "history_days": 900,
        "ttl_hours": 36,
        "comparison_key": "policy_rate",
    },
    "eu-3m-rate": {
        "kind": "raw",
        "region": "EU",
        "provider_series_id": "IR3TIB01EZM156N",
        "title": "Euro Area 3M Rate",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "policy",
        "mode_tags": ["snapshot", "rates_policy"],
        "history_days": 900,
        "ttl_hours": 36,
        "comparison_key": "front_end_rate",
    },
    "eu-10y-yield": {
        "kind": "raw",
        "region": "EU",
        "provider_series_id": "IRLTLT01EZM156N",
        "title": "Euro Area 10Y Government Yield",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "policy",
        "mode_tags": ["snapshot", "rates_policy"],
        "history_days": 900,
        "ttl_hours": 36,
        "comparison_key": "long_rate",
    },
    "eu-unemployment-rate": {
        "kind": "raw",
        "region": "EU",
        "provider_series_id": "LRHUTTTTEZM156S",
        "title": "Euro Area Unemployment Rate",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "growth",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 1200,
        "ttl_hours": 72,
        "comparison_key": "labor_slack",
    },
    "eu-eurusd": {
        "kind": "raw",
        "region": "EU",
        "provider_series_id": "CCUSMA02EZM618N",
        "title": "EUR/USD Exchange Rate",
        "unit": "fx",
        "frequency": "monthly",
        "theme": "policy",
        "mode_tags": ["snapshot", "cross_asset", "rates_policy"],
        "history_days": 1200,
        "ttl_hours": 36,
        "comparison_key": "fx_proxy",
    },
    "us-cpi-yoy": {
        "kind": "yoy",
        "region": "US",
        "provider_series_id": "CPIAUCSL",
        "title": "Headline CPI YoY",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "inflation",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 1200,
        "ttl_hours": 36,
        "comparison_key": "inflation_yoy",
        "transformation_note": "Year-over-year percent change computed from the CPI index level.",
    },
    "us-core-cpi-yoy": {
        "kind": "yoy",
        "region": "US",
        "provider_series_id": "CPILFESL",
        "title": "Core CPI YoY",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "inflation",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 1200,
        "ttl_hours": 36,
        "comparison_key": "inflation_core_yoy",
        "transformation_note": "Year-over-year percent change computed from the core CPI index level.",
    },
    "us-real-gdp-yoy": {
        "kind": "yoy",
        "region": "US",
        "provider_series_id": "GDPC1",
        "title": "Real GDP YoY",
        "unit": "pct",
        "frequency": "quarterly",
        "theme": "growth",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 1800,
        "ttl_hours": 72,
        "comparison_key": "activity_yoy",
        "transformation_note": "Year-over-year percent change computed from the chained real GDP level.",
    },
    "us-payrolls-yoy": {
        "kind": "yoy",
        "region": "US",
        "provider_series_id": "PAYEMS",
        "title": "Nonfarm Payrolls YoY",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "growth",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 1200,
        "ttl_hours": 36,
        "comparison_key": "employment_growth_yoy",
        "transformation_note": "Year-over-year percent change computed from total nonfarm payroll employment.",
    },
    "eu-hicp-yoy": {
        "kind": "yoy",
        "region": "EU",
        "provider_series_id": "CP0000EZ19M086NEST",
        "title": "Euro Area HICP YoY",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "inflation",
        "mode_tags": ["snapshot", "cross_asset", "rates_policy"],
        "history_days": 1200,
        "ttl_hours": 36,
        "comparison_key": "inflation_yoy",
        "transformation_note": "Year-over-year percent change computed from the Euro Area HICP level.",
    },
    "us-2s10s-slope": {
        "kind": "spread",
        "region": "US",
        "left_provider_series_id": "DGS10",
        "right_provider_series_id": "DGS2",
        "title": "2s10s Treasury Slope",
        "unit": "bps",
        "frequency": "daily",
        "theme": "recession_risk",
        "mode_tags": ["snapshot", "cross_asset", "rates_policy"],
        "history_days": 540,
        "ttl_hours": 24,
        "comparison_key": "curve_slope",
        "transformation_note": "10Y constant-maturity Treasury yield minus 2Y Treasury yield, scaled to basis points.",
    },
    "eu-3m10y-slope": {
        "kind": "spread",
        "region": "EU",
        "left_provider_series_id": "IRLTLT01EZM156N",
        "right_provider_series_id": "IR3TIB01EZM156N",
        "title": "3M-10Y Euro Area Slope",
        "unit": "bps",
        "frequency": "monthly",
        "theme": "recession_risk",
        "mode_tags": ["snapshot", "cross_asset", "rates_policy"],
        "history_days": 1200,
        "ttl_hours": 36,
        "comparison_key": "curve_slope",
        "transformation_note": "Euro Area 10Y government bond yield minus the Euro Area 3M interbank rate, scaled to basis points.",
    },
    "eu-industrial-production-yoy": {
        "kind": "raw",
        "region": "EU",
        "provider_series_id": "EA19PRINTO01GYSAM",
        "title": "Euro Area Industrial Production YoY",
        "unit": "pct",
        "frequency": "monthly",
        "theme": "growth",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 1200,
        "ttl_hours": 36,
        "comparison_key": "activity_yoy",
        "transformation_note": "OECD/FRED provides this Euro Area industrial production series as a year-over-year growth rate.",
    },
}

TIMEFRAME_DAYS = {"1M": 31, "3M": 93, "6M": 186, "1Y": 370}
THEME_ORDER = ["all", "growth", "inflation", "policy", "recession_risk"]
REGION_ORDER = ["US", "EU", "Global"]
PRIMARY_COMPARISON_REGIONS = {"US", "EU"}
PREDICTION_MARKET_THEME_LINKS: dict[str, dict[str, Any]] = {
    "growth": {
        "query": "recession",
        "category": "Economy",
        "market_direction": -1.0,
        "headline": "Growth proxies versus recession pricing",
        "market_note": "Recession contracts are used as an inverse growth proxy in Macro V1.",
    },
    "inflation": {
        "query": "inflation",
        "category": "Economy",
        "market_direction": 1.0,
        "headline": "Inflation proxies versus linked inflation markets",
        "market_note": "Higher probabilities are read as reinforcing the inflation narrative.",
    },
    "policy": {
        "query": "fed cut",
        "category": "Economy",
        "market_direction": -1.0,
        "headline": "Rates proxies versus policy-cut pricing",
        "market_note": "Rate-cut odds are inverted so higher cut probabilities read as easier policy.",
    },
    "recession_risk": {
        "query": "recession",
        "category": "Economy",
        "market_direction": 1.0,
        "headline": "Stress proxies versus recession pricing",
        "market_note": "Higher recession probabilities are read as reinforcing the stress narrative.",
    },
}
PREDICTION_MARKET_MAX_LINKS = 3

REGION_THEME_SERIES = {
    "US": {
        "growth": ["us-real-gdp-yoy", "us-payrolls-yoy", "us-unemployment-rate", "us-2s10s-slope"],
        "inflation": ["us-cpi-yoy", "us-core-cpi-yoy", "us-5y-breakeven", "us-10y-breakeven", "us-dollar-broad"],
        "policy": ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-dollar-broad", "us-real-10y-yield"],
        "recession_risk": ["us-2s10s-slope", "us-hy-oas", "us-unemployment-rate", "us-dollar-broad"],
    },
    "EU": {
        "growth": ["eu-industrial-production-yoy", "eu-unemployment-rate", "eu-3m10y-slope"],
        "inflation": ["eu-hicp-yoy", "eu-eurusd", "eu-10y-yield"],
        "policy": ["eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-eurusd"],
        "recession_risk": ["eu-3m10y-slope", "eu-unemployment-rate", "eu-eurusd"],
    },
}

REGION_THEME_FACTORS = {
    "US": {
        "growth": {"us-real-gdp-yoy": 1.0, "us-payrolls-yoy": 1.0, "us-unemployment-rate": -1.0, "us-2s10s-slope": 0.6},
        "inflation": {"us-cpi-yoy": 1.0, "us-core-cpi-yoy": 1.0, "us-5y-breakeven": 0.9, "us-10y-breakeven": 0.8, "us-dollar-broad": -0.5},
        "policy": {"us-fed-funds": 1.0, "us-2y-yield": 1.0, "us-10y-yield": 0.4, "us-dollar-broad": 0.4, "us-real-10y-yield": 0.6},
        "recession_risk": {"us-2s10s-slope": -0.8, "us-hy-oas": 1.0, "us-unemployment-rate": 0.8, "us-dollar-broad": 0.2},
    },
    "EU": {
        "growth": {"eu-industrial-production-yoy": 1.0, "eu-unemployment-rate": -0.9, "eu-3m10y-slope": 0.5},
        "inflation": {"eu-hicp-yoy": 1.0, "eu-eurusd": -0.4, "eu-10y-yield": 0.3},
        "policy": {"eu-policy-rate": 1.0, "eu-3m-rate": 0.9, "eu-10y-yield": 0.4, "eu-eurusd": -0.2},
        "recession_risk": {"eu-3m10y-slope": -0.8, "eu-unemployment-rate": 0.8, "eu-eurusd": -0.2},
    },
}

SIGNAL_SCALES = {
    "us-real-gdp-yoy": 0.5,
    "us-payrolls-yoy": 1.0,
    "us-unemployment-rate": 0.15,
    "us-cpi-yoy": 0.35,
    "us-core-cpi-yoy": 0.25,
    "us-fed-funds": 0.25,
    "us-2y-yield": 0.2,
    "us-10y-yield": 0.15,
    "us-30y-yield": 0.15,
    "us-real-10y-yield": 0.12,
    "us-5y-breakeven": 0.12,
    "us-10y-breakeven": 0.12,
    "us-dollar-broad": 2.0,
    "us-hy-oas": 0.35,
    "us-2s10s-slope": 20.0,
    "eu-industrial-production-yoy": 1.0,
    "eu-unemployment-rate": 0.12,
    "eu-hicp-yoy": 0.25,
    "eu-policy-rate": 0.2,
    "eu-3m-rate": 0.15,
    "eu-10y-yield": 0.12,
    "eu-eurusd": 0.02,
    "eu-3m10y-slope": 20.0,
}

REGION_SNAPSHOT_SERIES = {
    "US": [
        "us-real-gdp-yoy",
        "us-payrolls-yoy",
        "us-unemployment-rate",
        "us-cpi-yoy",
        "us-core-cpi-yoy",
        "us-fed-funds",
        "us-2y-yield",
        "us-10y-yield",
        "us-30y-yield",
        "us-2s10s-slope",
        "us-real-10y-yield",
        "us-5y-breakeven",
        "us-10y-breakeven",
        "us-dollar-broad",
        "us-hy-oas",
    ],
    "EU": [
        "eu-industrial-production-yoy",
        "eu-unemployment-rate",
        "eu-hicp-yoy",
        "eu-policy-rate",
        "eu-3m-rate",
        "eu-10y-yield",
        "eu-3m10y-slope",
        "eu-eurusd",
    ],
}

SERIES_BY_COMPARISON_KEY: dict[str, dict[str, str]] = {}
for _series_id, _meta in SERIES_REGISTRY.items():
    comparison_key = _meta.get("comparison_key")
    region = _meta.get("region")
    if comparison_key and region in PRIMARY_COMPARISON_REGIONS:
        SERIES_BY_COMPARISON_KEY.setdefault(str(comparison_key), {})[str(region)] = _series_id


@dataclass(frozen=True)
class MacroSnapshotRequest:
    region: str = "US"
    timeframe: str = "3M"
    theme: str = "all"
    comparison_region: str | None = None
    force_refresh: bool = False


class MacroService:
    def __init__(
        self,
        *,
        fred_adapter: FredMacroAdapter,
        treasury_adapter: TreasuryCurveAdapter,
        events_adapter: USMacroEventsAdapter,
        prediction_market_service: PredictionMarketService | None = None,
    ) -> None:
        self.fred_adapter = fred_adapter
        self.treasury_adapter = treasury_adapter
        self.events_adapter = events_adapter
        self.prediction_market_service = prediction_market_service

    def get_snapshot(self, request: MacroSnapshotRequest) -> MacroSnapshotPayload:
        region = self._normalize_region(request.region)
        timeframe = self._normalize_timeframe(request.timeframe)
        theme = self._normalize_theme(request.theme)
        comparison_region = self._normalize_comparison(region, request.comparison_region)
        data_region = self._data_region(region)
        histories = self._load_histories(self._snapshot_series_ids(data_region, theme), timeframe=timeframe, force_refresh=request.force_refresh)
        comparison_histories = self._load_comparison_histories(
            region=data_region,
            comparison_region=comparison_region,
            series_ids=list(histories),
            timeframe=timeframe,
            force_refresh=request.force_refresh,
        )
        events = self.get_events(region=region, force_refresh=request.force_refresh)
        divergences = self.get_divergences(
            MacroSnapshotRequest(
                region=region,
                timeframe=timeframe,
                theme=theme,
                comparison_region=comparison_region,
                force_refresh=request.force_refresh,
            ),
            histories=histories,
            comparison_histories=comparison_histories,
        )
        linked_expectations = self._build_linked_expectations(
            region=region,
            theme=theme,
            histories=histories,
            comparison_histories=comparison_histories,
            comparison_region=comparison_region,
            timeframe=timeframe,
            force_refresh=request.force_refresh,
        )
        warnings = self._snapshot_warnings(
            region=region,
            requested_comparison=request.comparison_region,
            comparison_region=comparison_region,
            linked_prediction_markets=bool(linked_expectations),
        )
        rates_policy = self._build_rates_policy(
            region=region,
            histories=histories,
            comparison_histories=comparison_histories,
            comparison_region=comparison_region,
            events=events,
            timeframe=timeframe,
            force_refresh=request.force_refresh,
        )
        retrieved_at = max(
            [row.retrieved_at for row in histories.values() if row.retrieved_at is not None]
            + [row.retrieved_at for row in comparison_histories.values() if row.retrieved_at is not None]
            + [row.retrieved_at for row in events if row.retrieved_at is not None]
            + [row.retrieved_at for row in divergences if row.retrieved_at is not None]
            + [row.retrieved_at for row in linked_expectations if row.retrieved_at is not None]
            + ([rates_policy.retrieved_at] if rates_policy.retrieved_at is not None else []),
            default=now_utc(),
        )
        return MacroSnapshotPayload(
            region=region,
            timeframe=timeframe,
            theme=theme,
            comparison_region=comparison_region,
            available_regions=list(REGION_ORDER),
            available_timeframes=list(TIMEFRAME_DAYS),
            available_themes=THEME_ORDER,
            snapshot_cards=self._build_snapshot_cards(
                region=region,
                histories=histories,
                comparison_histories=comparison_histories,
                comparison_region=comparison_region,
                divergences=divergences,
                events=events,
                linked_expectations=linked_expectations,
                timeframe=timeframe,
            ),
            rates_policy=rates_policy,
            cross_asset=self._build_cross_asset(
                region=region,
                histories=histories,
                comparison_histories=comparison_histories,
                comparison_region=comparison_region,
                divergences=divergences,
                timeframe=timeframe,
            ),
            linked_expectations=linked_expectations,
            top_divergences=divergences[:3],
            upcoming_events=events[:5],
            warnings=warnings,
            source_provider="macro+prediction_markets" if linked_expectations else "fred",
            retrieved_at=retrieved_at,
            origin="macro_service.snapshot",
            transformation_note="Snapshot combines normalized FRED series histories, Treasury curve snapshots where available, comparison-aware metric overlays, official calendar events, and linked prediction-market expectation packets into a mode-oriented macro workspace.",
        )

    def get_series_history(self, series_id: str, *, region: str = "US", timeframe: str = "1Y", force_refresh: bool = False) -> MacroSeriesHistory | None:
        normalized_region = self._normalize_region(region)
        data_region = self._data_region(normalized_region)
        if data_region == "US" and series_id.startswith("eu-"):
            return None
        if data_region == "EU" and series_id.startswith("us-"):
            return None
        return self._load_histories([series_id], timeframe=self._normalize_timeframe(timeframe), force_refresh=force_refresh).get(series_id)

    def get_divergences(
        self,
        request: MacroSnapshotRequest,
        *,
        histories: dict[str, MacroSeriesHistory] | None = None,
        comparison_histories: dict[str, MacroSeriesHistory] | None = None,
    ) -> list[MacroDivergenceRecord]:
        region = self._normalize_region(request.region)
        data_region = self._data_region(region)
        theme = self._normalize_theme(request.theme)
        timeframe = self._normalize_timeframe(request.timeframe)
        comparison_region = self._normalize_comparison(region, request.comparison_region)
        loaded_histories = histories or self._load_histories(self._divergence_series_ids(data_region, theme), timeframe=timeframe, force_refresh=request.force_refresh)
        loaded_comparison_histories = comparison_histories or self._load_comparison_histories(
            region=data_region,
            comparison_region=comparison_region,
            series_ids=self._divergence_series_ids(data_region, theme),
            timeframe=timeframe,
            force_refresh=request.force_refresh,
        )
        themes = [theme] if theme != "all" else [name for name in THEME_ORDER if name != "all"]
        rows: list[MacroDivergenceRecord] = []
        for theme_name in themes:
            signal_rows = self._collect_signal_rows(data_region, theme_name, loaded_histories, timeframe=timeframe, comparison_region=comparison_region, comparison_histories=loaded_comparison_histories)
            if len(signal_rows) < 2:
                continue
            strongest_positive = max(signal_rows, key=lambda item: item[1])
            strongest_negative = min(signal_rows, key=lambda item: item[1])
            score = round(strongest_positive[1] - strongest_negative[1], 2)
            label = "high" if score >= 2.4 else "moderate" if score >= 1.2 else "low"
            comparison_score = None
            score_gap = None
            score_gap_display = None
            if comparison_region is not None:
                comparison_signal_rows = self._collect_signal_rows(
                    comparison_region,
                    theme_name,
                    loaded_comparison_histories,
                    timeframe=timeframe,
                    comparison_region=None,
                    comparison_histories={},
                )
                if len(comparison_signal_rows) >= 2:
                    comparison_positive = max(comparison_signal_rows, key=lambda item: item[1])
                    comparison_negative = min(comparison_signal_rows, key=lambda item: item[1])
                    comparison_score = round(comparison_positive[1] - comparison_negative[1], 2)
                    score_gap = round(score - comparison_score, 2)
                    score_gap_display = f"{score_gap:+.2f}"
            summary = f"{strongest_positive[0].label} is reinforcing the theme while {strongest_negative[0].label} is leaning the other way."
            if comparison_region is not None and comparison_score is not None:
                summary = f"{summary} Divergence is {score_gap_display} versus {comparison_region} on the same theme."
            rows.append(
                MacroDivergenceRecord(
                    divergence_id=f"{region.lower()}:{theme_name}:divergence",
                    theme=theme_name,
                    region=region,
                    headline=f"{self._title_theme(theme_name)} divergence score {score:.2f}",
                    summary=summary,
                    score=score,
                    label=label,
                    metrics=[row for row, _ in signal_rows],
                    series_ids=[row.series_id for row, _ in signal_rows if row.series_id],
                    source_provider="fred",
                    retrieved_at=max((row.retrieved_at for row, _ in signal_rows if row.retrieved_at is not None), default=now_utc()),
                    origin="macro_service.divergences",
                    transformation_note="Divergence scores compare directional changes across curated theme proxies, scaled by series-specific thresholds, theme orientation, and optional cross-region comparison overlays.",
                    comparison_region=comparison_region,
                    comparison_score=comparison_score,
                    score_gap=score_gap,
                    score_gap_display=score_gap_display,
                )
            )
        rows.sort(key=lambda row: (-row.score, row.theme))
        return rows

    def get_events(self, *, region: str = "US", force_refresh: bool = False) -> list[MacroEventRecord]:
        return self.events_adapter.list_events(region=self._normalize_region(region), as_of=now_utc(), force_refresh=force_refresh)

    def _build_linked_expectations(
        self,
        *,
        region: str,
        theme: str,
        histories: dict[str, MacroSeriesHistory],
        comparison_histories: dict[str, MacroSeriesHistory],
        comparison_region: str | None,
        timeframe: str,
        force_refresh: bool,
    ) -> list[MacroExpectationRecord]:
        if self.prediction_market_service is None:
            return []

        data_region = self._data_region(region)
        themes = [theme] if theme != "all" else [name for name in THEME_ORDER if name != "all"]
        query_cache: dict[tuple[str, str | None, bool], list[PredictionMarketRecord]] = {}
        rows: list[MacroExpectationRecord] = []

        for theme_name in themes:
            link_config = PREDICTION_MARKET_THEME_LINKS.get(theme_name)
            if link_config is None:
                continue
            signal_rows = self._collect_signal_rows(
                data_region,
                theme_name,
                histories,
                timeframe=timeframe,
                comparison_region=comparison_region,
                comparison_histories=comparison_histories,
            )
            if not signal_rows:
                continue

            cache_key = (str(link_config["query"]), link_config.get("category"), force_refresh)
            if cache_key not in query_cache:
                try:
                    result = self.prediction_market_service.screener(
                        PredictionMarketScreenerRequest(
                            query=str(link_config["query"]),
                            category=link_config.get("category"),
                            status="open",
                            force_refresh=force_refresh,
                            limit=6,
                        )
                    )
                    query_cache[cache_key] = [
                        market
                        for market in result.markets
                        if market.current_probability is not None and not (market.freshness and market.freshness.is_broken)
                    ][:PREDICTION_MARKET_MAX_LINKS]
                except Exception:
                    query_cache[cache_key] = []

            linked_markets = query_cache[cache_key]
            if not linked_markets:
                continue

            macro_signal_score = self._average_signal_score(signal_rows)
            market_signal_score, market_probability, repricing_signal = self._prediction_market_signal(
                linked_markets,
                direction=float(link_config["market_direction"]),
            )
            score_gap = round(macro_signal_score - market_signal_score, 2)
            agreement_label = self._expectation_agreement_label(macro_signal_score, market_signal_score)
            lead_label, lead_summary = self._lead_lag_summary(
                macro_signal_score=macro_signal_score,
                market_repricing_signal=repricing_signal,
                timeframe=timeframe,
            )

            market_note = str(link_config["market_note"])
            summary_parts = [
                f"Macro proxies lean {self._theme_signal_text(theme_name, macro_signal_score)} while linked prediction markets lean {self._theme_signal_text(theme_name, market_signal_score)}.",
                market_note,
                lead_summary,
            ]
            if region != "US":
                summary_parts.append("Prediction-market coverage remains US/global-topic first in this regional lens.")

            linked_rows = [
                MacroLinkedMarketRecord(
                    market_id=market.market_id,
                    venue=market.venue,
                    title=market.title,
                    event_title=market.event_title,
                    probability=market.current_probability,
                    probability_display=_format_probability(market.current_probability),
                    recent_price_change=market.recent_price_change,
                    recent_price_change_display=_format_probability_delta(market.recent_price_change),
                    research_score=market.research_score,
                    resolution_date=market.end_time,
                    note=market_note,
                    source_provider=market.source_provider,
                    retrieved_at=market.retrieved_at,
                    origin=market.origin,
                    transformation_note=market.transformation_note or "Linked prediction-market rows preserve the underlying venue payload used in the macro expectations bridge.",
                )
                for market in linked_markets
            ]
            retrieved_at = max(
                [row.retrieved_at for row in linked_rows if row.retrieved_at is not None]
                + [row.retrieved_at for row, _ in signal_rows if row.retrieved_at is not None],
                default=now_utc(),
            )
            rows.append(
                MacroExpectationRecord(
                    expectation_id=f"{region.lower()}:{theme_name}:linked-expectation",
                    theme=theme_name,
                    region=region,
                    headline=str(link_config["headline"]),
                    summary=" ".join(summary_parts),
                    agreement_label=agreement_label,
                    macro_signal_score=macro_signal_score,
                    macro_signal_display=f"{macro_signal_score:+.2f}",
                    market_signal_score=market_signal_score,
                    market_signal_display=f"{market_signal_score:+.2f}",
                    market_probability=market_probability,
                    market_probability_display=_format_probability(market_probability),
                    score_gap=score_gap,
                    score_gap_display=f"{score_gap:+.2f}",
                    lead_label=lead_label,
                    lead_summary=lead_summary,
                    linked_markets=linked_rows,
                    source_provider="macro+prediction_markets",
                    retrieved_at=retrieved_at,
                    origin="macro_service.linked_expectations",
                    transformation_note="Linked expectations combine macro theme signal scoring with prediction-market research-ranked contracts, theme-specific direction mapping, and a lightweight lead/lag proxy based on repricing intensity.",
                )
            )

        rows.sort(key=lambda row: (0 if row.agreement_label == "conflicted" else 1, -abs(row.score_gap or 0.0), row.theme))
        return rows

    def _load_histories(self, series_ids: list[str], *, timeframe: str, force_refresh: bool) -> dict[str, MacroSeriesHistory]:
        rows: dict[str, MacroSeriesHistory] = {}
        for series_id in series_ids:
            history = self._load_history(series_id, timeframe=timeframe, force_refresh=force_refresh)
            if history is not None:
                rows[series_id] = history
        return rows

    def _load_comparison_histories(
        self,
        *,
        region: str,
        comparison_region: str | None,
        series_ids: list[str],
        timeframe: str,
        force_refresh: bool,
    ) -> dict[str, MacroSeriesHistory]:
        if comparison_region is None:
            return {}
        counterpart_ids: list[str] = []
        for series_id in series_ids:
            counterpart = self._counterpart_series_id(series_id, comparison_region)
            if counterpart is not None and counterpart not in counterpart_ids:
                counterpart_ids.append(counterpart)
        if not counterpart_ids:
            return {}
        return self._load_histories(counterpart_ids, timeframe=timeframe, force_refresh=force_refresh)

    def _load_history(self, series_id: str, *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory | None:
        meta = SERIES_REGISTRY.get(series_id)
        if meta is None:
            return None
        kind = meta["kind"]
        if kind == "raw":
            return self._load_raw_history(series_id, meta, timeframe=timeframe, force_refresh=force_refresh)
        if kind == "yoy":
            return self._load_yoy_history(series_id, meta, timeframe=timeframe, force_refresh=force_refresh)
        if kind == "spread":
            return self._load_spread_history(series_id, meta, timeframe=timeframe, force_refresh=force_refresh)
        return None

    def _load_raw_history(self, series_id: str, meta: dict[str, Any], *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory:
        start, end = self._history_window(meta["history_days"], timeframe)
        points, retrieved_at = self.fred_adapter.get_series(meta["provider_series_id"], start=start, end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        return MacroSeriesHistory(
            series_id=series_id,
            title=meta["title"],
            region=meta["region"],
            unit=meta["unit"],
            frequency=meta["frequency"],
            theme=meta["theme"],
            mode_tags=list(meta["mode_tags"]),
            points=[point for point in points if point.timestamp >= start],
            source_provider="fred",
            retrieved_at=retrieved_at,
            origin=f"fred.series.observations:{meta['provider_series_id']}",
            transformation_note=meta.get("transformation_note"),
        )

    def _load_yoy_history(self, series_id: str, meta: dict[str, Any], *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory:
        start, end = self._history_window(meta["history_days"], timeframe)
        raw_points, retrieved_at = self.fred_adapter.get_series(meta["provider_series_id"], start=start - timedelta(days=400), end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        yoy_points = _compute_yoy_points(raw_points, retrieved_at=retrieved_at, note=meta["transformation_note"], periods_per_year=_periods_per_year(meta["frequency"]))
        return MacroSeriesHistory(
            series_id=series_id,
            title=meta["title"],
            region=meta["region"],
            unit=meta["unit"],
            frequency=meta["frequency"],
            theme=meta["theme"],
            mode_tags=list(meta["mode_tags"]),
            points=[point for point in yoy_points if point.timestamp >= start],
            source_provider="fred",
            retrieved_at=retrieved_at,
            origin="macro_service.derived.yoy",
            transformation_note=meta["transformation_note"],
        )

    def _load_spread_history(self, series_id: str, meta: dict[str, Any], *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory:
        start, end = self._history_window(meta["history_days"], timeframe)
        left_points, left_retrieved_at = self.fred_adapter.get_series(meta["left_provider_series_id"], start=start, end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        right_points, right_retrieved_at = self.fred_adapter.get_series(meta["right_provider_series_id"], start=start, end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        left_map = {point.timestamp.date(): point for point in left_points}
        right_map = {point.timestamp.date(): point for point in right_points}
        points: list[MacroSeriesPoint] = []
        for key in sorted(set(left_map) & set(right_map)):
            left = left_map[key]
            right = right_map[key]
            points.append(
                MacroSeriesPoint(
                    timestamp=datetime.combine(key, datetime.min.time()),
                    value=(left.value - right.value) * 100.0,
                    source_provider="fred",
                    retrieved_at=max(filter(None, [left.retrieved_at, right.retrieved_at]), default=now_utc()),
                    origin="macro_service.derived.spread",
                    transformation_note=meta["transformation_note"],
                )
            )
        return MacroSeriesHistory(
            series_id=series_id,
            title=meta["title"],
            region=meta["region"],
            unit=meta["unit"],
            frequency=meta["frequency"],
            theme=meta["theme"],
            mode_tags=list(meta["mode_tags"]),
            points=points,
            source_provider="fred",
            retrieved_at=max(left_retrieved_at, right_retrieved_at),
            origin="macro_service.derived.spread",
            transformation_note=meta["transformation_note"],
        )

    def _build_snapshot_cards(
        self,
        *,
        region: str,
        histories: dict[str, MacroSeriesHistory],
        comparison_histories: dict[str, MacroSeriesHistory],
        comparison_region: str | None,
        divergences: list[MacroDivergenceRecord],
        events: list[MacroEventRecord],
        linked_expectations: list[MacroExpectationRecord],
        timeframe: str,
    ) -> list[MacroSnapshotCard]:
        data_region = self._data_region(region)
        if data_region == "EU":
            cards = [
                self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Activity and labor backdrop", summary="EU growth context blends industrial activity, labor slack, and a lighter curve signal.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("eu-industrial-production-yoy"), histories.get("eu-unemployment-rate"), histories.get("eu-3m10y-slope")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="Realized inflation against FX and rates proxies", summary="EU inflation context emphasizes headline HICP and how FX and long rates are absorbing the same narrative.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("eu-hicp-yoy"), histories.get("eu-eurusd"), histories.get("eu-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="policy", title="Policy Context", subtitle="ECB proxy and front-end rates", summary="Policy context uses ECB and money-market proxies first, then long-end confirmation.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("eu-policy-rate"), histories.get("eu-3m-rate"), histories.get("eu-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="curve-shape", title="Curve Shape", subtitle="3M to 10Y slope", summary="The EU curve card is intentionally lighter in V1 and focuses on the 3M-to-10Y slope rather than a full sovereign curve grid.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("eu-3m10y-slope"), histories.get("eu-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="fx", title="EUR / USD Proxy", subtitle="Currency context", summary="FX often carries the policy and risk read in lighter EU coverage, especially when deeper credit and event tooling is still US-first.", mode_target="cross_asset", target_theme="policy", metric_histories=[histories.get("eu-eurusd")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
            ]
        else:
            cards = [
                self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Labor and activity backdrop", summary="Growth context blends real activity, payrolls, and labor-market slack.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("us-real-gdp-yoy"), histories.get("us-payrolls-yoy"), histories.get("us-unemployment-rate")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="Realized inflation versus market-implied inflation", summary="Inflation context compares realized CPI with breakevens to show whether markets are running ahead or behind the data.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("us-cpi-yoy"), histories.get("us-core-cpi-yoy"), histories.get("us-5y-breakeven")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="policy", title="Policy Context", subtitle="Front-end rates and policy stance", summary="Front-end pricing leads the policy read and frames how restrictive the macro backdrop remains.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-fed-funds"), histories.get("us-2y-yield"), histories.get("us-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="curve-shape", title="Curve Shape", subtitle="Treasury slope and curve change", summary="Curve shape highlights whether rates are steepening or re-inverting against the prior reference window.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-2s10s-slope"), histories.get("us-10y-yield"), histories.get("us-30y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="real-yields", title="Real Yields / Breakevens", subtitle="Real-rate and inflation-compensation lens", summary="Real yields and breakevens capture how much of a rates move is real tightening versus inflation compensation.", mode_target="rates_policy", target_theme="inflation", metric_histories=[histories.get("us-real-10y-yield"), histories.get("us-5y-breakeven"), histories.get("us-10y-breakeven")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
            ]
            for card_id, title, subtitle, summary, series_id, mode_target, theme_name in (
                ("dollar", "Dollar / FX Proxy", "Broad dollar positioning", "A firmer dollar often confirms tighter policy and global stress; a softer dollar often points the other way.", "us-dollar-broad", "cross_asset", "policy"),
                ("credit", "Credit / Stress Proxy", "High-yield spread as a stress lens", "Credit spreads act as a fast proxy for tightening financial conditions and recession anxiety.", "us-hy-oas", "cross_asset", "recession_risk"),
            ):
                history = histories.get(series_id)
                if history is not None:
                    cards.append(MacroSnapshotCard(card_id=card_id, title=title, subtitle=subtitle, summary=summary, mode_target=mode_target, target_theme=theme_name, metrics=[self._metric_from_history(history, timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories)], source_provider="fred", retrieved_at=history.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Snapshot cards summarize the latest level and active-timeframe change for a curated macro series, with optional cross-region comparison fields when counterparts exist."))
        if divergences:
            divergence = divergences[0]
            cards.append(
                MacroSnapshotCard(
                    card_id="divergences",
                    title="Top Divergences",
                    subtitle="Where markets disagree most",
                    summary=divergence.summary,
                    mode_target="cross_asset",
                    target_theme=divergence.theme,
                    metrics=[
                        MacroMetricRecord(
                            metric_id=f"{divergence.divergence_id}:score",
                            label=self._title_theme(divergence.theme),
                            value=divergence.score,
                            display_value=f"{divergence.score:.2f}",
                            unit="score",
                            source_provider=divergence.source_provider,
                            retrieved_at=divergence.retrieved_at,
                            origin="macro_service.snapshot_cards",
                            transformation_note="Snapshot cards surface the highest-ranked divergence score from the reusable cross-asset engine.",
                            comparison_region=divergence.comparison_region,
                            comparison_label=f"{divergence.comparison_region} score" if divergence.comparison_region else None,
                            comparison_value=divergence.comparison_score,
                            comparison_display_value=f"{divergence.comparison_score:.2f}" if divergence.comparison_score is not None else None,
                            gap_value=divergence.score_gap,
                            gap_display=divergence.score_gap_display,
                        )
                    ],
                    source_provider=divergence.source_provider,
                    retrieved_at=divergence.retrieved_at,
                    origin="macro_service.snapshot_cards",
                    transformation_note="Snapshot cards surface the highest-ranked divergence score from the reusable cross-asset engine.",
                )
            )
        if linked_expectations:
            expectation = linked_expectations[0]
            cards.append(
                MacroSnapshotCard(
                    card_id="linked-expectations",
                    title="Linked Expectations",
                    subtitle="Prediction markets versus macro proxies",
                    summary=expectation.summary,
                    mode_target="cross_asset",
                    target_theme=expectation.theme,
                    metrics=[
                        MacroMetricRecord(
                            metric_id=f"{expectation.expectation_id}:macro",
                            label="Macro",
                            value=expectation.macro_signal_score,
                            display_value=expectation.macro_signal_display,
                            unit="score",
                            source_provider=expectation.source_provider,
                            retrieved_at=expectation.retrieved_at,
                            origin="macro_service.snapshot_cards",
                            transformation_note="Linked-expectation cards summarize the macro-side directional score from the expectation bridge.",
                        ),
                        MacroMetricRecord(
                            metric_id=f"{expectation.expectation_id}:markets",
                            label="Prediction",
                            value=expectation.market_signal_score,
                            display_value=expectation.market_signal_display,
                            unit="score",
                            source_provider=expectation.source_provider,
                            retrieved_at=expectation.retrieved_at,
                            origin="macro_service.snapshot_cards",
                            transformation_note="Linked-expectation cards summarize the prediction-market-side directional score from the expectation bridge.",
                        ),
                        MacroMetricRecord(
                            metric_id=f"{expectation.expectation_id}:probability",
                            label="Avg odds",
                            value=expectation.market_probability,
                            display_value=expectation.market_probability_display,
                            unit="probability",
                            source_provider=expectation.source_provider,
                            retrieved_at=expectation.retrieved_at,
                            origin="macro_service.snapshot_cards",
                            transformation_note="Linked-expectation cards surface the average probability across the linked prediction-market set.",
                        ),
                    ],
                    source_provider=expectation.source_provider,
                    retrieved_at=expectation.retrieved_at,
                    origin="macro_service.snapshot_cards",
                    transformation_note="Snapshot cards surface the highest-priority linked expectation packet from the macro-to-prediction-market bridge.",
                )
            )
        if events:
            event = events[0]
            cards.append(MacroSnapshotCard(card_id="events", title="Upcoming Macro Events", subtitle="Next catalyst on deck", summary=f"{event.title} is the next scheduled macro catalyst in the official event feed.", mode_target="rates_policy", target_theme="policy" if event.category == "policy" else "growth", metrics=[MacroMetricRecord(metric_id=f"{event.event_id}:date", label=event.title, value=None, display_value=event.scheduled_at.strftime("%b %d, %Y"), unit="date", source_provider=event.source_provider, retrieved_at=event.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Event cards surface the next upcoming macro release or meeting from official calendars.")], source_provider=event.source_provider, retrieved_at=event.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Event cards surface the next upcoming macro release or meeting from official calendars."))
        return cards

    def _build_metric_card(self, *, card_id: str, title: str, subtitle: str, summary: str, mode_target: str, target_theme: str, metric_histories: list[MacroSeriesHistory | None], timeframe: str, comparison_region: str | None, comparison_histories: dict[str, MacroSeriesHistory]) -> MacroSnapshotCard:
        metrics = [self._metric_from_history(history, timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for history in metric_histories if history is not None]
        return MacroSnapshotCard(card_id=card_id, title=title, subtitle=subtitle, summary=summary, mode_target=mode_target, target_theme=target_theme, metrics=metrics, source_provider=metrics[0].source_provider if metrics else "fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.snapshot_cards", transformation_note="Snapshot cards summarize the latest level and active-timeframe change for curated macro series, with optional cross-region comparison fields when counterparts exist.")

    def _build_rates_policy(self, *, region: str, histories: dict[str, MacroSeriesHistory], comparison_histories: dict[str, MacroSeriesHistory], comparison_region: str | None, events: list[MacroEventRecord], timeframe: str, force_refresh: bool) -> MacroRatesPolicySummary:
        data_region = self._data_region(region)
        curve_nodes, curve_retrieved_at = self._load_curve_nodes(region=data_region, histories=histories, force_refresh=force_refresh, timeframe=timeframe)
        if data_region == "EU":
            policy_ids = ("eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-3m10y-slope")
            real_ids = ("eu-hicp-yoy", "eu-eurusd")
            headline = "ECB and money-market proxies remain the cleanest read on EU macro conditions."
            slope_metric = next((self._metric_from_history(histories[series_id], timeframe=timeframe) for series_id in ("eu-3m10y-slope",) if series_id in histories), None)
            if slope_metric and slope_metric.value is not None:
                headline = "The EU curve is inverted against the 3M rate proxy." if slope_metric.value < 0 else "The EU 3M-to-10Y slope is positive."
            summary = "EU Rates & Policy is intentionally lighter in V1 and emphasizes ECB-rate proxies, the 3M versus 10Y slope, and inflation/FX context instead of a full sovereign curve stack."
        else:
            policy_ids = ("us-fed-funds", "us-2y-yield", "us-10y-yield", "us-2s10s-slope")
            real_ids = ("us-real-10y-yield", "us-5y-breakeven", "us-10y-breakeven")
            headline = "Front-end policy pricing remains the cleanest read on US macro conditions."
            slope_metric = next((self._metric_from_history(histories[series_id], timeframe=timeframe) for series_id in ("us-2s10s-slope",) if series_id in histories), None)
            if slope_metric and slope_metric.value is not None:
                headline = "The curve is still inverted." if slope_metric.value < 0 else "The curve is positive and no longer inverted."
            summary = "Rates & Policy emphasizes the current Treasury curve, front-end policy context, and the real-yield versus breakeven split."
        policy_metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for series_id in policy_ids if series_id in histories]
        real_yield_metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for series_id in real_ids if series_id in histories]
        visible_events = events[:4] if data_region == "US" else []
        comparison_summary = f"Comparing {region} rates context against {comparison_region} where equivalent concepts exist." if comparison_region is not None else None
        return MacroRatesPolicySummary(headline=headline, summary=summary, policy_metrics=policy_metrics, curve_nodes=curve_nodes, real_yield_metrics=real_yield_metrics, events=visible_events, source_provider="treasury" if data_region == "US" else "fred", retrieved_at=max([curve_retrieved_at] + [row.retrieved_at for row in policy_metrics if row.retrieved_at is not None] + [row.retrieved_at for row in real_yield_metrics if row.retrieved_at is not None] + [row.retrieved_at for row in visible_events if row.retrieved_at is not None], default=now_utc()), origin="macro_service.rates_policy", transformation_note="Rates & Policy combines region-specific series histories, Treasury XML curve snapshots where available, and optional cross-region comparison overlays for matched concepts.", comparison_region=comparison_region, comparison_summary=comparison_summary)

    def _build_cross_asset(self, *, region: str, histories: dict[str, MacroSeriesHistory], comparison_histories: dict[str, MacroSeriesHistory], comparison_region: str | None, divergences: list[MacroDivergenceRecord], timeframe: str) -> list[MacroThemeComparison]:
        data_region = self._data_region(region)
        divergence_map = {row.theme: row for row in divergences}
        rows: list[MacroThemeComparison] = []
        for theme in [name for name in THEME_ORDER if name != "all"]:
            metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for series_id in REGION_THEME_SERIES.get(data_region, {}).get(theme, []) if series_id in histories]
            if metrics:
                divergence = divergence_map.get(theme)
                comparison_summary = None
                if divergence is not None and divergence.comparison_region is not None and divergence.comparison_score is not None:
                    comparison_summary = f"{divergence.comparison_region} divergence score {divergence.comparison_score:.2f} ({divergence.score_gap_display} vs {region})."
                rows.append(MacroThemeComparison(theme=theme, headline=f"{self._title_theme(theme)} signals", summary=divergence.summary if divergence is not None else "Theme coverage is available, but disagreement is currently muted.", agreement_label=divergence.label if divergence is not None else "low", metrics=metrics, source_provider="fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.cross_asset", transformation_note="Cross-asset theme blocks line up curated region-specific series so the user can compare whether markets agree on a macro narrative, with optional cross-region overlays where concept matches exist.", comparison_region=comparison_region, comparison_summary=comparison_summary))
        return rows

    def _load_curve_nodes(self, *, region: str, histories: dict[str, MacroSeriesHistory], force_refresh: bool, timeframe: str) -> tuple[list[MacroCurveNode], datetime]:
        if region == "EU":
            nodes: list[MacroCurveNode] = []
            retrieved_at = datetime.min
            for tenor, series_id in (("Policy", "eu-policy-rate"), ("3M", "eu-3m-rate"), ("10Y", "eu-10y-yield")):
                history = histories.get(series_id)
                if history is None:
                    continue
                metric = self._metric_from_history(history, timeframe=timeframe)
                nodes.append(MacroCurveNode(tenor=tenor, current_value=metric.value, prior_value=(metric.value - metric.delta_value) if metric.value is not None and metric.delta_value is not None else None, change_bps=(metric.delta_value * 100.0) if metric.delta_value is not None else None, source_provider=history.source_provider, retrieved_at=history.retrieved_at, origin="macro_service.rates_policy.eu_curve", transformation_note="EU V1 curve nodes are a lighter proxy grid built from policy, 3M, and 10Y FRED series instead of Treasury-style point-in-time sovereign curve snapshots."))
                if history.retrieved_at is not None:
                    retrieved_at = max(retrieved_at, history.retrieved_at)
            return nodes, (retrieved_at if retrieved_at != datetime.min else now_utc())
        current_time = now_utc()
        years = [current_time.year] + ([current_time.year - 1] if current_time.month == 1 else [])
        nominal_history, nominal_retrieved_at = self.treasury_adapter.get_curve_history("daily_treasury_yield_curve", years=years, ttl=timedelta(hours=6), force_refresh=force_refresh)
        latest_date = max((date for date in nominal_history if date <= current_time), default=None)
        if latest_date is None:
            return [], nominal_retrieved_at
        cutoff = latest_date - timedelta(days=TIMEFRAME_DAYS.get(timeframe, 93))
        prior_candidates = [date for date in nominal_history if date <= cutoff]
        prior_date = max(prior_candidates) if prior_candidates else max((date for date in nominal_history if date < latest_date), default=latest_date)
        latest_curve = nominal_history.get(latest_date, {})
        prior_curve = nominal_history.get(prior_date, {})
        nodes = [MacroCurveNode(tenor=tenor, current_value=latest_curve.get(tenor), prior_value=prior_curve.get(tenor), change_bps=((latest_curve.get(tenor) - prior_curve.get(tenor)) * 100.0) if latest_curve.get(tenor) is not None and prior_curve.get(tenor) is not None else None, source_provider="treasury", retrieved_at=nominal_retrieved_at, origin="treasury.daily_treasury_yield_curve", transformation_note="Curve comparison uses the latest available Treasury XML curve point versus the active-timeframe prior point, falling back to the nearest earlier observation when coverage is limited.") for tenor in ("3M", "2Y", "5Y", "10Y", "30Y")]
        return nodes, nominal_retrieved_at

    def _collect_signal_rows(self, region: str, theme_name: str, histories: dict[str, MacroSeriesHistory], *, timeframe: str, comparison_region: str | None, comparison_histories: dict[str, MacroSeriesHistory]) -> list[tuple[MacroMetricRecord, float]]:
        signal_rows: list[tuple[MacroMetricRecord, float]] = []
        for series_id in REGION_THEME_SERIES.get(region, {}).get(theme_name, []):
            history = histories.get(series_id)
            if history is None:
                continue
            metric = self._metric_from_history(history, timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories)
            if metric.delta_value is None:
                continue
            factor = REGION_THEME_FACTORS.get(region, {}).get(theme_name, {}).get(series_id, 1.0)
            scale = SIGNAL_SCALES.get(series_id, 1.0)
            signal_rows.append((metric, max(min((metric.delta_value / scale) * factor, 3.0), -3.0)))
        return signal_rows

    @staticmethod
    def _average_signal_score(signal_rows: list[tuple[MacroMetricRecord, float]]) -> float:
        if not signal_rows:
            return 0.0
        return round(sum(score for _, score in signal_rows) / len(signal_rows), 2)

    @staticmethod
    def _prediction_market_signal(markets: list[PredictionMarketRecord], *, direction: float) -> tuple[float, float | None, float]:
        weighted_probability = 0.0
        weighted_probability_center = 0.0
        weighted_repricing_center = 0.0
        total_weight = 0.0
        for market in markets:
            if market.current_probability is None:
                continue
            weight = max((market.research_score or 0.0) / 100.0, 0.35)
            total_weight += weight
            weighted_probability += weight * market.current_probability
            weighted_probability_center += weight * direction * ((market.current_probability - 0.5) * 2.0)
            repricing = max(min((market.recent_price_change or 0.0) / 0.12, 1.5), -1.5)
            weighted_repricing_center += weight * direction * repricing
        if total_weight == 0:
            return 0.0, None, 0.0
        probability_center = weighted_probability_center / total_weight
        repricing_center = weighted_repricing_center / total_weight
        market_signal = max(min((probability_center * 2.0) + (repricing_center * 0.7), 3.0), -3.0)
        repricing_signal = max(min(repricing_center * 2.0, 3.0), -3.0)
        return round(market_signal, 2), round(weighted_probability / total_weight, 4), round(repricing_signal, 2)

    @staticmethod
    def _expectation_agreement_label(macro_signal_score: float, market_signal_score: float) -> str:
        score_gap = abs(macro_signal_score - market_signal_score)
        if macro_signal_score * market_signal_score < 0 and score_gap >= 0.75:
            return "conflicted"
        if score_gap <= 0.9:
            return "aligned"
        return "mixed"

    @staticmethod
    def _lead_lag_summary(*, macro_signal_score: float, market_repricing_signal: float, timeframe: str) -> tuple[str, str]:
        macro_intensity = abs(macro_signal_score)
        market_intensity = abs(market_repricing_signal)
        if market_intensity > macro_intensity + 0.45:
            return (
                "Prediction markets leading",
                f"Prediction-market repricing is moving faster than the macro proxy set in the active {timeframe} window. This is a lightweight lead/lag proxy, not a causal read.",
            )
        if macro_intensity > market_intensity + 0.45:
            return (
                "Macro markets leading",
                f"Macro proxies are moving harder than the linked prediction-market set in the active {timeframe} window. This is a lightweight lead/lag proxy, not a causal read.",
            )
        return (
            "Moving together",
            f"Macro proxies and linked prediction markets are repricing at a similar intensity in the active {timeframe} window. This is a lightweight lead/lag proxy, not a causal read.",
        )

    @staticmethod
    def _theme_signal_text(theme: str, score: float | None) -> str:
        if score is None or abs(score) < 0.35:
            return "a muted read"
        if theme == "growth":
            return "firmer growth" if score > 0 else "softer growth"
        if theme == "inflation":
            return "hotter inflation" if score > 0 else "cooler inflation"
        if theme == "policy":
            return "tighter policy" if score > 0 else "easier policy"
        if theme == "recession_risk":
            return "higher recession risk" if score > 0 else "lower recession risk"
        return "the same direction" if score > 0 else "the opposite direction"

    def _metric_from_history(self, history: MacroSeriesHistory, *, timeframe: str, comparison_region: str | None = None, comparison_histories: dict[str, MacroSeriesHistory] | None = None) -> MacroMetricRecord:
        latest = history.points[-1] if history.points else None
        previous = _point_before_cutoff(history.points, days=TIMEFRAME_DAYS.get(timeframe, 93))
        delta = latest.value - previous.value if latest is not None and previous is not None else None
        comparison_history = None
        comparison_label = None
        if comparison_region is not None:
            comparison_id = self._counterpart_series_id(history.series_id, comparison_region)
            if comparison_id is not None:
                comparison_history = (comparison_histories or {}).get(comparison_id)
                comparison_label = comparison_history.title if comparison_history is not None else None
        comparison_latest = comparison_history.points[-1] if comparison_history and comparison_history.points else None
        comparison_previous = _point_before_cutoff(comparison_history.points, days=TIMEFRAME_DAYS.get(timeframe, 93)) if comparison_history else None
        comparison_delta = comparison_latest.value - comparison_previous.value if comparison_latest is not None and comparison_previous is not None else None
        gap_value = latest.value - comparison_latest.value if latest is not None and comparison_latest is not None else None
        return MacroMetricRecord(metric_id=history.series_id, label=history.title, value=latest.value if latest is not None else None, display_value=_format_metric(latest.value if latest else None, history.unit), unit=history.unit, delta_value=delta, delta_display=_format_delta(delta, history.unit), series_id=history.series_id, source_provider=history.source_provider, retrieved_at=history.retrieved_at, origin=history.origin, transformation_note=history.transformation_note, comparison_region=comparison_region if comparison_history is not None else None, comparison_label=comparison_label, comparison_value=comparison_latest.value if comparison_latest is not None else None, comparison_display_value=_format_metric(comparison_latest.value if comparison_latest else None, history.unit) if comparison_history is not None else None, comparison_delta_value=comparison_delta, comparison_delta_display=_format_delta(comparison_delta, history.unit) if comparison_history is not None else None, gap_value=gap_value, gap_display=_format_delta(gap_value, history.unit) if gap_value is not None else None)

    def _snapshot_series_ids(self, region: str, theme: str) -> list[str]:
        base = list(REGION_SNAPSHOT_SERIES.get(region, []))
        if theme == "all":
            return base
        focused = REGION_THEME_SERIES.get(region, {}).get(theme, [])
        return focused + [series_id for series_id in base if series_id not in focused]

    def _divergence_series_ids(self, region: str, theme: str) -> list[str]:
        if theme == "all":
            ordered: list[str] = []
            for theme_name in [name for name in THEME_ORDER if name != "all"]:
                for series_id in REGION_THEME_SERIES.get(region, {}).get(theme_name, []):
                    if series_id not in ordered:
                        ordered.append(series_id)
            return ordered
        return list(REGION_THEME_SERIES.get(region, {}).get(theme, []))

    @staticmethod
    def _normalize_region(region: str) -> str:
        normalized = str(region or "US").strip().upper()
        if normalized in {"GLOBAL", "GLOB"}:
            return "Global"
        if normalized in {"EU", "EMU", "EA"}:
            return "EU"
        return "US"

    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
        normalized = str(timeframe or "3M").strip().upper()
        return normalized if normalized in TIMEFRAME_DAYS else "3M"

    @staticmethod
    def _normalize_theme(theme: str) -> str:
        normalized = str(theme or "all").strip().lower().replace(" ", "_")
        return normalized if normalized in THEME_ORDER else "all"

    @staticmethod
    def _data_region(region: str) -> str:
        return "US" if region == "Global" else region

    def _normalize_comparison(self, region: str, comparison_region: str | None) -> str | None:
        if region not in PRIMARY_COMPARISON_REGIONS or comparison_region is None:
            return None
        normalized = self._normalize_region(comparison_region)
        if normalized not in PRIMARY_COMPARISON_REGIONS or normalized == region:
            return None
        return normalized

    @staticmethod
    def _snapshot_warnings(
        *,
        region: str,
        requested_comparison: str | None,
        comparison_region: str | None,
        linked_prediction_markets: bool,
    ) -> list[str]:
        warnings: list[str] = []
        if region == "Global":
            warnings.append("Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.")
        if region == "EU":
            warnings.append("EU mode is a lighter V1 region. Rates and inflation proxies are available, but event-calendar depth and curve coverage remain thinner than the US implementation.")
        if linked_prediction_markets and region != "US":
            warnings.append("Linked prediction-market expectations remain US/global-topic first in Macro V1.")
        if requested_comparison is not None and comparison_region is None:
            warnings.append("Comparison is currently available only for direct US-versus-EU views. The requested comparison target was ignored.")
        if comparison_region is not None:
            warnings.append(f"Comparison lens active: {region} versus {comparison_region}. Only concepts with curated counterparts are compared directly.")
        return warnings

    @staticmethod
    def _title_theme(theme: str) -> str:
        return theme.replace("_", " ").title()

    @staticmethod
    def _history_window(minimum_days: int, timeframe: str) -> tuple[datetime, datetime]:
        current_time = now_utc()
        return current_time - timedelta(days=max(minimum_days, TIMEFRAME_DAYS.get(timeframe, 93) + 45)), current_time

    @staticmethod
    def _counterpart_series_id(series_id: str, comparison_region: str) -> str | None:
        meta = SERIES_REGISTRY.get(series_id)
        if meta is None:
            return None
        comparison_key = meta.get("comparison_key")
        if comparison_key is None:
            return None
        return SERIES_BY_COMPARISON_KEY.get(str(comparison_key), {}).get(comparison_region)


def _compute_yoy_points(raw_points: list[MacroSeriesPoint], *, retrieved_at: datetime, note: str, periods_per_year: int) -> list[MacroSeriesPoint]:
    rows: list[MacroSeriesPoint] = []
    for index, point in enumerate(raw_points):
        prior = raw_points[index - periods_per_year] if index >= periods_per_year else None
        if prior is None or prior.value == 0:
            continue
        rows.append(MacroSeriesPoint(timestamp=point.timestamp, value=((point.value / prior.value) - 1.0) * 100.0, source_provider="fred", retrieved_at=retrieved_at, origin="macro_service.derived.yoy", transformation_note=note))
    return rows


def _periods_per_year(frequency: str) -> int:
    normalized = str(frequency or "").strip().lower()
    if normalized == "quarterly":
        return 4
    return 12


def _point_before_cutoff(points: list[MacroSeriesPoint], *, days: int) -> MacroSeriesPoint | None:
    if not points:
        return None
    latest = points[-1]
    cutoff = latest.timestamp - timedelta(days=days)
    for point in reversed(points):
        if point.timestamp <= cutoff:
            return point
    return points[0]


def _format_metric(value: float | None, unit: str | None) -> str:
    if value is None:
        return "N/A"
    if unit == "pct":
        return f"{value:.2f}%"
    if unit == "bps":
        return f"{value:.0f} bps"
    if unit == "index":
        return f"{value:.1f}"
    if unit == "fx":
        return f"{value:.3f}"
    if unit == "score":
        return f"{value:.2f}"
    return f"{value:.2f}"


def _format_probability(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100.0:.0f}%"


def _format_probability_delta(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100.0:+.1f} pp"


def _format_delta(value: float | None, unit: str | None) -> str:
    if value is None:
        return "N/A"
    if unit == "pct":
        return f"{value:+.2f} pp"
    if unit == "bps":
        return f"{value:+.0f} bps"
    if unit == "index":
        return f"{value:+.1f}"
    if unit == "fx":
        return f"{value:+.3f}"
    if unit == "score":
        return f"{value:+.2f}"
    return f"{value:+.2f}"
