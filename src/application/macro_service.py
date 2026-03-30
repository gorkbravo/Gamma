from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Any

from src.models.macro import (
    MacroCurveNode,
    MacroDivergenceRecord,
    MacroDivergenceSignal,
    MacroEventRecord,
    MacroLinkedPredictionMarket,
    MacroMetricRecord,
    MacroRatesPolicySummary,
    MacroSeriesHistory,
    MacroSeriesPoint,
    MacroSnapshotCard,
    MacroSnapshotPayload,
    MacroThemeComparison,
)
from src.application.prediction_market_service import PredictionMarketScreenerRequest, PredictionMarketService
from src.models.prediction_markets import PredictionMarketRecord
from src.services.macro_adapters import IBKRMacroFXAdapter, FredMacroAdapter, TreasuryCurveAdapter, USMacroEventsAdapter
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
    "fx-eurusd": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "EUR",
        "quote_currency": "USD",
        "title": "EUR/USD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-gbpusd": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "GBP",
        "quote_currency": "USD",
        "title": "GBP/USD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-usdjpy": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "USD",
        "quote_currency": "JPY",
        "title": "USD/JPY",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-usdchf": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "USD",
        "quote_currency": "CHF",
        "title": "USD/CHF",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-usdcad": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "USD",
        "quote_currency": "CAD",
        "title": "USD/CAD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-audusd": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "AUD",
        "quote_currency": "USD",
        "title": "AUD/USD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-usdeur": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "USD",
        "quote_currency": "EUR",
        "title": "USD/EUR",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-usdgbp": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "USD",
        "quote_currency": "GBP",
        "title": "USD/GBP",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-jpyusd": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "JPY",
        "quote_currency": "USD",
        "title": "JPY/USD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-chfusd": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "CHF",
        "quote_currency": "USD",
        "title": "CHF/USD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-cadusd": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "CAD",
        "quote_currency": "USD",
        "title": "CAD/USD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-usdaud": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "USD",
        "quote_currency": "AUD",
        "title": "USD/AUD",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
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

MACRO_PREDICTION_QUERY_TERMS = {
    "US": {
        "growth": "US economy GDP payrolls unemployment jobs",
        "inflation": "US inflation CPI PCE prices",
        "policy": "Fed FOMC rates cut hike policy",
        "recession_risk": "US recession unemployment slowdown",
    },
    "EU": {
        "growth": "eurozone economy growth unemployment",
        "inflation": "eurozone inflation HICP ECB prices",
        "policy": "ECB eurozone rates cut hike policy",
        "recession_risk": "eurozone recession slowdown unemployment",
    },
    "Global": {
        "growth": "global economy growth recession",
        "inflation": "global inflation CPI prices",
        "policy": "global rates Fed ECB policy",
        "recession_risk": "global recession slowdown",
    },
}

THEME_ALIGNMENT_LABELS = {
    "growth": {1: "growth-up", -1: "growth-down"},
    "inflation": {1: "inflation-up", -1: "inflation-down"},
    "policy": {1: "policy-tighter", -1: "policy-easier"},
    "recession_risk": {1: "recession-risk-up", -1: "recession-risk-down"},
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
        fx_adapter: IBKRMacroFXAdapter | None = None,
        prediction_market_service: PredictionMarketService | None = None,
    ) -> None:
        self.fred_adapter = fred_adapter
        self.treasury_adapter = treasury_adapter
        self.events_adapter = events_adapter
        self.fx_adapter = fx_adapter
        self.prediction_market_service = prediction_market_service

    def get_snapshot(self, request: MacroSnapshotRequest) -> MacroSnapshotPayload:
        region = self._normalize_region(request.region)
        timeframe = self._normalize_timeframe(request.timeframe)
        theme = self._normalize_theme(request.theme)
        comparison_region = self._normalize_comparison(region, request.comparison_region)
        warnings = self._snapshot_warnings(region=region, requested_comparison=request.comparison_region, comparison_region=comparison_region)
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
        linked_markets = self._build_linked_prediction_market_map(
            region=region,
            timeframe=timeframe,
            histories=histories,
            force_refresh=request.force_refresh,
        )
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
        rates_policy = self._build_rates_policy(
            region=region,
            histories=histories,
            comparison_histories=comparison_histories,
            comparison_region=comparison_region,
            events=events,
            linked_markets=linked_markets.get("policy", []),
            timeframe=timeframe,
            force_refresh=request.force_refresh,
        )
        retrieved_at = max(
            [row.retrieved_at for row in histories.values() if row.retrieved_at is not None]
            + [row.retrieved_at for row in comparison_histories.values() if row.retrieved_at is not None]
            + [row.retrieved_at for row in events if row.retrieved_at is not None]
            + [row.retrieved_at for row in divergences if row.retrieved_at is not None]
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
                linked_markets=linked_markets,
                timeframe=timeframe,
            ),
            rates_policy=rates_policy,
            cross_asset=self._build_cross_asset(
                region=region,
                histories=histories,
                comparison_histories=comparison_histories,
                comparison_region=comparison_region,
                divergences=divergences,
                linked_markets=linked_markets,
                timeframe=timeframe,
            ),
            top_divergences=divergences[:3],
            upcoming_events=events[:5],
            warnings=warnings,
            source_provider="fred",
            retrieved_at=retrieved_at,
            origin="macro_service.snapshot",
            transformation_note="Snapshot combines normalized FRED series histories, Treasury curve snapshots where available, comparison-aware metric overlays, and official calendar events into a mode-oriented macro workspace.",
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
            primary_driver = self._build_divergence_signal(theme_name, strongest_positive[0], strongest_positive[1], role="driver")
            counter_signal = self._build_divergence_signal(theme_name, strongest_negative[0], strongest_negative[1], role="counter")
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
            summary = self._divergence_summary(theme_name, primary_driver, counter_signal)
            if comparison_region is not None and comparison_score is not None:
                summary = f"{summary} Divergence is {score_gap_display} versus {comparison_region} on the same theme."
            research_focus = self._divergence_research_focus(
                theme_name,
                primary_driver=primary_driver,
                counter_signal=counter_signal,
                comparison_region=comparison_region,
                score_gap_display=score_gap_display,
            )
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
                    primary_driver=primary_driver,
                    counter_signal=counter_signal,
                    research_focus=research_focus,
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
        if kind == "fx":
            return self._load_fx_history(series_id, meta, timeframe=timeframe, force_refresh=force_refresh)
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

    def _load_fx_history(self, series_id: str, meta: dict[str, Any], *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory:
        start, end = self._history_window(meta["history_days"], timeframe)
        if self.fx_adapter is None:
            points: list[MacroSeriesPoint] = []
            retrieved_at = now_utc()
        else:
            points, retrieved_at = self.fx_adapter.get_series(
                meta["base_currency"],
                meta["quote_currency"],
                start=start,
                end=end,
                force_refresh=force_refresh,
            )
        return MacroSeriesHistory(
            series_id=series_id,
            title=meta["title"],
            region=meta["region"],
            unit=meta["unit"],
            frequency=meta["frequency"],
            theme=meta["theme"],
            mode_tags=list(meta["mode_tags"]),
            points=[point for point in points if point.timestamp >= start],
            source_provider="ibkr",
            retrieved_at=retrieved_at,
            origin=f"ibkr.fx_history:{meta['base_currency']}{meta['quote_currency']}",
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
        linked_markets: dict[str, list[MacroLinkedPredictionMarket]],
        timeframe: str,
    ) -> list[MacroSnapshotCard]:
        data_region = self._data_region(region)
        if data_region == "EU":
            cards = [
                self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Activity and labor backdrop", summary="Industrial output, unemployment, and curve slope frame the EU growth picture.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("eu-industrial-production-yoy"), histories.get("eu-unemployment-rate"), histories.get("eu-3m10y-slope"), histories.get("eu-10y-yield"), histories.get("eu-eurusd")], linked_markets=linked_markets.get("growth", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="HICP versus market signals", summary="Headline HICP alongside FX and long rates shows whether markets are absorbing the inflation narrative.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("eu-hicp-yoy"), histories.get("eu-eurusd"), histories.get("eu-10y-yield"), histories.get("eu-policy-rate"), histories.get("eu-3m10y-slope")], linked_markets=linked_markets.get("inflation", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="policy", title="Policy Context", subtitle="ECB rate and front-end pricing", summary="ECB and money-market rates lead; the long end confirms direction.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("eu-policy-rate"), histories.get("eu-3m-rate"), histories.get("eu-10y-yield"), histories.get("eu-eurusd"), histories.get("eu-3m10y-slope")], linked_markets=linked_markets.get("policy", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="curve-shape", title="Curve Shape", subtitle="3M–10Y slope", summary="Tracks the 3M-to-10Y slope as the primary EU curve signal.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("eu-3m10y-slope"), histories.get("eu-10y-yield"), histories.get("eu-3m-rate"), histories.get("eu-policy-rate")], linked_markets=linked_markets.get("policy", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="fx", title="EUR / USD Proxy", subtitle="Currency context", summary="EUR/USD often carries the policy and risk signal when deeper EU tooling is limited.", mode_target="cross_asset", target_theme="policy", metric_histories=[histories.get("eu-eurusd"), histories.get("eu-10y-yield"), histories.get("eu-hicp-yoy")], linked_markets=linked_markets.get("policy", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
            ]
        else:
            cards = [
                self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Labor and activity backdrop", summary="GDP, payrolls, unemployment, and copper frame the real-economy picture.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("us-real-gdp-yoy"), histories.get("us-payrolls-yoy"), histories.get("us-unemployment-rate"), histories.get("us-2s10s-slope"), histories.get("us-hy-oas")], linked_markets=linked_markets.get("growth", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="Realized vs. market-implied", summary="CPI, breakevens, and energy inputs show whether inflation pressure is broadening or cooling.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("us-cpi-yoy"), histories.get("us-core-cpi-yoy"), histories.get("us-5y-breakeven"), histories.get("us-10y-breakeven"), histories.get("us-dollar-broad")], linked_markets=linked_markets.get("inflation", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="policy", title="Policy Context", subtitle="Front-end pricing and stance", summary="Front-end rates lead the policy read and frame how restrictive conditions remain.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-fed-funds"), histories.get("us-2y-yield"), histories.get("us-10y-yield"), histories.get("us-real-10y-yield"), histories.get("us-dollar-broad")], linked_markets=linked_markets.get("policy", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="curve-shape", title="Curve Shape", subtitle="Treasury slope direction", summary="Steepening or re-inverting against the prior reference window.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-2s10s-slope"), histories.get("us-10y-yield"), histories.get("us-30y-yield"), histories.get("us-2y-yield"), histories.get("us-real-10y-yield")], linked_markets=linked_markets.get("policy", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="real-yields", title="Real Yields / Breakevens", subtitle="Real rates vs. inflation comp.", summary="Splits a rates move into real tightening and inflation compensation.", mode_target="rates_policy", target_theme="inflation", metric_histories=[histories.get("us-real-10y-yield"), histories.get("us-5y-breakeven"), histories.get("us-10y-breakeven"), histories.get("us-10y-yield"), histories.get("us-cpi-yoy")], linked_markets=linked_markets.get("inflation", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
            ]
            dollar_history = histories.get("us-dollar-broad")
            if dollar_history is not None:
                cards.append(self._build_metric_card(card_id="dollar", title="Dollar / FX Proxy", subtitle="Broad dollar positioning", summary="Firmer dollar confirms tighter policy and global stress; softer dollar signals the opposite.", mode_target="cross_asset", target_theme="policy", metric_histories=[histories.get("us-dollar-broad"), histories.get("us-10y-yield"), histories.get("us-fed-funds")], linked_markets=linked_markets.get("policy", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories))
            credit_history = histories.get("us-hy-oas")
            if credit_history is not None:
                cards.append(self._build_metric_card(card_id="credit", title="Credit / Stress Proxy", subtitle="HY spread as stress gauge", summary="Credit spreads proxy tightening financial conditions and recession risk.", mode_target="cross_asset", target_theme="recession_risk", metric_histories=[histories.get("us-hy-oas"), histories.get("us-2s10s-slope"), histories.get("us-unemployment-rate")], linked_markets=linked_markets.get("recession_risk", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories))
        if divergences:
            divergence = divergences[0]
            cards.append(
                MacroSnapshotCard(
                    card_id="divergences",
                    title="Top Divergences",
                    subtitle="Largest market disagreement",
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
                    linked_markets=list(linked_markets.get(divergence.theme, [])),
                    source_provider=divergence.source_provider,
                    retrieved_at=divergence.retrieved_at,
                    origin="macro_service.snapshot_cards",
                    transformation_note="Snapshot cards surface the highest-ranked divergence score from the reusable cross-asset engine.",
                )
            )
        return cards

    def _build_metric_card(self, *, card_id: str, title: str, subtitle: str, summary: str, mode_target: str, target_theme: str, metric_histories: list[MacroSeriesHistory | None], linked_markets: list[MacroLinkedPredictionMarket], timeframe: str, comparison_region: str | None, comparison_histories: dict[str, MacroSeriesHistory]) -> MacroSnapshotCard:
        metrics = [self._metric_from_history(history, timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for history in metric_histories if history is not None]
        return MacroSnapshotCard(card_id=card_id, title=title, subtitle=subtitle, summary=summary, mode_target=mode_target, target_theme=target_theme, metrics=metrics, linked_markets=list(linked_markets), source_provider=metrics[0].source_provider if metrics else "fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.snapshot_cards", transformation_note="Snapshot cards summarize the latest level and active-timeframe change for curated macro series, with optional cross-region comparison fields when counterparts exist.")

    def _build_rates_policy(self, *, region: str, histories: dict[str, MacroSeriesHistory], comparison_histories: dict[str, MacroSeriesHistory], comparison_region: str | None, events: list[MacroEventRecord], linked_markets: list[MacroLinkedPredictionMarket], timeframe: str, force_refresh: bool) -> MacroRatesPolicySummary:
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
        return MacroRatesPolicySummary(headline=headline, summary=summary, policy_metrics=policy_metrics, curve_nodes=curve_nodes, real_yield_metrics=real_yield_metrics, events=visible_events, linked_markets=list(linked_markets), source_provider="treasury" if data_region == "US" else "fred", retrieved_at=max([curve_retrieved_at] + [row.retrieved_at for row in policy_metrics if row.retrieved_at is not None] + [row.retrieved_at for row in real_yield_metrics if row.retrieved_at is not None] + [row.retrieved_at for row in visible_events if row.retrieved_at is not None], default=now_utc()), origin="macro_service.rates_policy", transformation_note="Rates & Policy combines region-specific series histories, Treasury XML curve snapshots where available, optional cross-region comparison overlays for matched concepts, and linked prediction-market context for policy-sensitive contracts.", comparison_region=comparison_region, comparison_summary=comparison_summary)

    def _build_cross_asset(self, *, region: str, histories: dict[str, MacroSeriesHistory], comparison_histories: dict[str, MacroSeriesHistory], comparison_region: str | None, divergences: list[MacroDivergenceRecord], linked_markets: dict[str, list[MacroLinkedPredictionMarket]], timeframe: str) -> list[MacroThemeComparison]:
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
                rows.append(MacroThemeComparison(theme=theme, headline=f"{self._title_theme(theme)} signals", summary=divergence.summary if divergence is not None else "Theme coverage is available, but disagreement is currently muted.", agreement_label=divergence.label if divergence is not None else "low", metrics=metrics, linked_markets=list(linked_markets.get(theme, [])), primary_driver=divergence.primary_driver if divergence is not None else None, counter_signal=divergence.counter_signal if divergence is not None else None, divergence_score=divergence.score if divergence is not None else None, research_focus=divergence.research_focus if divergence is not None else None, source_provider="fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.cross_asset", transformation_note="Cross-asset theme blocks line up curated region-specific series so the user can compare whether markets agree on a macro narrative, with optional cross-region overlays where concept matches exist and linked prediction contracts for the same theme.", comparison_region=comparison_region, comparison_summary=comparison_summary))
        return rows

    def _build_linked_prediction_market_map(
        self,
        *,
        region: str,
        timeframe: str,
        histories: dict[str, MacroSeriesHistory],
        force_refresh: bool,
    ) -> dict[str, list[MacroLinkedPredictionMarket]]:
        if self.prediction_market_service is None:
            return {}
        rows: dict[str, list[MacroLinkedPredictionMarket]] = {}
        for theme in [name for name in THEME_ORDER if name != "all"]:
            rows[theme] = self._linked_prediction_markets_for_theme(
                region=region,
                theme=theme,
                timeframe=timeframe,
                histories=histories,
                force_refresh=force_refresh,
            )
        return rows

    def _linked_prediction_markets_for_theme(
        self,
        *,
        region: str,
        theme: str,
        timeframe: str,
        histories: dict[str, MacroSeriesHistory],
        force_refresh: bool,
    ) -> list[MacroLinkedPredictionMarket]:
        if self.prediction_market_service is None:
            return []
        query = MACRO_PREDICTION_QUERY_TERMS.get(region, MACRO_PREDICTION_QUERY_TERMS["US"]).get(theme)
        if not query:
            return []
        try:
            result = self.prediction_market_service.screener(
                PredictionMarketScreenerRequest(
                    query=query,
                    status="open",
                    force_refresh=force_refresh,
                    category="Economy",
                    min_volume=5_000.0,
                    sort_by="research_rank",
                    limit=6,
                )
            )
        except Exception:
            return []
        bias_score, bias_summary = self._theme_bias_summary(
            region=self._data_region(region),
            theme=theme,
            histories=histories,
            timeframe=timeframe,
        )
        linked: list[MacroLinkedPredictionMarket] = []
        for market in result.markets[:3]:
            linked.append(
                self._linked_prediction_market_record(
                    market,
                    theme=theme,
                    bias_score=bias_score,
                    bias_summary=bias_summary,
                )
            )
        return linked

    def _linked_prediction_market_record(
        self,
        market: PredictionMarketRecord,
        *,
        theme: str,
        bias_score: float,
        bias_summary: str,
    ) -> MacroLinkedPredictionMarket:
        stance = self._infer_prediction_contract_stance(theme, market)
        alignment = "mixed"
        if abs(bias_score) < 0.25 or stance == 0:
            alignment = "mixed"
        elif (stance == 1 and bias_score > 0) or (stance == -1 and bias_score < 0):
            alignment = "aligned"
        else:
            alignment = "diverging"
        stance_label = THEME_ALIGNMENT_LABELS.get(theme, {}).get(stance)
        alignment_summary = bias_summary if stance_label is None else f"Gamma maps this contract as {stance_label}; {bias_summary}"
        return MacroLinkedPredictionMarket(
            market_id=market.market_id,
            venue=market.venue,
            title=market.title,
            status=market.status,
            category=market.category,
            end_time=market.end_time,
            current_probability=market.current_probability,
            probability_label=market.probability_label or (_format_probability(market.current_probability) if market.current_probability is not None else None),
            recent_price_change=market.recent_price_change,
            change_display=_format_prediction_change(market.recent_price_change),
            research_score=market.research_score,
            macro_alignment=alignment,
            macro_alignment_summary=alignment_summary,
            source_provider=market.source_provider,
            retrieved_at=market.retrieved_at,
            origin="macro_service.linked_prediction_markets",
            transformation_note="Linked prediction-market context reuses Gamma's normalized prediction screener, filtered by macro-theme queries and annotated with a lightweight macro-bias alignment heuristic.",
        )

    def _theme_bias_summary(
        self,
        *,
        region: str,
        theme: str,
        histories: dict[str, MacroSeriesHistory],
        timeframe: str,
    ) -> tuple[float, str]:
        signal_rows = self._collect_signal_rows(region, theme, histories, timeframe=timeframe, comparison_region=None, comparison_histories={})
        if not signal_rows:
            return 0.0, "Macro proxies are currently mixed."
        average_signal = sum(score for _, score in signal_rows) / len(signal_rows)
        if theme == "inflation":
            if average_signal >= 0.25:
                return average_signal, "Macro inflation proxies are firming."
            if average_signal <= -0.25:
                return average_signal, "Macro inflation proxies are cooling."
        if theme == "policy":
            if average_signal >= 0.25:
                return average_signal, "Macro policy proxies lean tighter."
            if average_signal <= -0.25:
                return average_signal, "Macro policy proxies lean easier."
        if theme == "growth":
            if average_signal >= 0.25:
                return average_signal, "Macro growth proxies are improving."
            if average_signal <= -0.25:
                return average_signal, "Macro growth proxies are softening."
        if theme == "recession_risk":
            if average_signal >= 0.25:
                return average_signal, "Macro stress proxies are worsening."
            if average_signal <= -0.25:
                return average_signal, "Macro stress proxies are easing."
        return average_signal, "Macro proxies are currently mixed."

    def _build_divergence_signal(
        self,
        theme: str,
        metric: MacroMetricRecord,
        signal_score: float,
        *,
        role: str,
    ) -> MacroDivergenceSignal:
        rounded_score = round(signal_score, 2)
        return MacroDivergenceSignal(
            role=role,
            tone=self._divergence_signal_tone(signal_score, role=role),
            signal_score=rounded_score,
            signal_score_display=f"{rounded_score:+.2f}",
            interpretation=self._divergence_signal_interpretation(theme, metric, signal_score, role=role),
            metric=metric,
            source_provider=metric.source_provider,
            retrieved_at=metric.retrieved_at,
            origin="macro_service.divergence_signal",
            transformation_note="Divergence signal annotations package the lead driver and counter-signal behind each theme score using scaled directional proxy moves.",
        )

    def _divergence_summary(
        self,
        theme: str,
        primary_driver: MacroDivergenceSignal,
        counter_signal: MacroDivergenceSignal,
    ) -> str:
        if counter_signal.signal_score <= -0.2:
            return f"{primary_driver.metric.label} is driving the {theme.replace('_', ' ')} read while {counter_signal.metric.label} is the clearest counter-signal."
        return f"{primary_driver.metric.label} is driving the {theme.replace('_', ' ')} read while {counter_signal.metric.label} is lagging as the weakest confirmation."

    def _divergence_research_focus(
        self,
        theme: str,
        *,
        primary_driver: MacroDivergenceSignal,
        counter_signal: MacroDivergenceSignal,
        comparison_region: str | None,
        score_gap_display: str | None,
    ) -> str:
        if counter_signal.signal_score <= -0.2:
            focus = f"Test whether {primary_driver.metric.label} or {counter_signal.metric.label} is more likely to reset first; that disagreement is carrying most of the {theme.replace('_', ' ')} divergence."
        else:
            focus = f"Test whether {counter_signal.metric.label} eventually catches up to {primary_driver.metric.label}; the theme currently depends on a narrow set of confirming proxies."
        if comparison_region is not None and score_gap_display is not None:
            focus = f"{focus} Versus {comparison_region}, the divergence spread is {score_gap_display}."
        return focus

    def _divergence_signal_tone(self, signal_score: float, *, role: str) -> str:
        if role == "driver":
            return "reinforcing" if signal_score >= 0.2 else "mixed"
        if signal_score <= -0.2:
            return "opposing"
        if signal_score >= 0.2:
            return "mixed"
        return "mixed"

    def _divergence_signal_interpretation(
        self,
        theme: str,
        metric: MacroMetricRecord,
        signal_score: float,
        *,
        role: str,
    ) -> str:
        move_text = metric.delta_display or metric.display_value or "latest move"
        supportive_state, opposing_state = self._theme_signal_states(theme)
        if role == "driver":
            if signal_score >= 0.2:
                return f"{metric.label} is the lead driver. Its {move_text} move points to {supportive_state}."
            return f"{metric.label} is still the strongest available proxy, but its {move_text} move is only weakly supportive."
        if signal_score <= -0.2:
            return f"{metric.label} is the clearest counter-signal. Its {move_text} move points to {opposing_state}."
        return f"{metric.label} is not outright opposing the theme, but its {move_text} move is lagging the stronger proxies."

    def _theme_signal_states(self, theme: str) -> tuple[str, str]:
        if theme == "inflation":
            return "firmer inflation pressure", "cooling inflation pressure"
        if theme == "policy":
            return "tighter policy conditions", "easier policy conditions"
        if theme == "growth":
            return "improving growth momentum", "softer growth momentum"
        if theme == "recession_risk":
            return "worsening stress conditions", "easing stress conditions"
        return "stronger macro pressure", "softer macro pressure"

    def _infer_prediction_contract_stance(self, theme: str, market: PredictionMarketRecord) -> int:
        text = f" {_normalize_text(' '.join(filter(None, [market.title, market.subtitle, market.event_title, market.series_title, ' '.join(market.tags)])))} "
        if theme == "inflation":
            if any(token in text for token in (" above ", " over ", " higher ", " hotter ", " rise ", " rising ", " increase ", " sticky ")):
                return 1
            if any(token in text for token in (" below ", " under ", " lower ", " cooler ", " fall ", " falling ", " decline ", " disinflation ")):
                return -1
        if theme == "policy":
            if any(token in text for token in (" hike ", " hikes ", " hold ", " higher ", " above ", " no cut ", " fewer cuts ", " hawkish ")):
                return 1
            if any(token in text for token in (" cut ", " cuts ", " lower ", " below ", " easing ", " dovish ")):
                return -1
        if theme == "growth":
            if any(token in text for token in (" soft landing ", " above ", " stronger ", " accelerate ", " expansion ", " payrolls beat ", " growth beats ")):
                return 1
            if any(token in text for token in (" below ", " weaker ", " slowdown ", " contraction ", " miss ", " unemployment rises ")):
                return -1
        if theme == "recession_risk":
            if any(token in text for token in (" recession ", " hard landing ", " unemployment above ", " layoffs ", " contraction ")):
                return 1
            if any(token in text for token in (" no recession ", " avoid recession ", " soft landing ")):
                return -1
        return 0

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
    def _snapshot_warnings(*, region: str, requested_comparison: str | None, comparison_region: str | None) -> list[str]:
        warnings: list[str] = []
        if region == "Global":
            warnings.append("Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.")
        if region == "EU":
            warnings.append("EU mode is a lighter V1 region. Rates and inflation proxies are available, but event-calendar depth and curve coverage remain thinner than the US implementation.")
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


def _format_prediction_change(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value * 100.0:+.1f} pts"


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
