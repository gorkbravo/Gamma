from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from src.models.macro import (
    MacroCoherenceProfile,
    MacroCurveNode,
    MacroDivergenceRecord,
    MacroDivergenceSignal,
    MacroEventRecord,
    MacroEventReactionSignal,
    MacroEventStudy,
    MacroLeadLagSignal,
    MacroLinkedPredictionMarket,
    MacroMetricRecord,
    MacroPolicyMeetingPathRow,
    MacroPolicyMeetingPathSummary,
    MacroRatesPolicySummary,
    MacroSeriesHistory,
    MacroSeriesPoint,
    MacroSnapshotCard,
    MacroSnapshotFocusItem,
    MacroSnapshotPayload,
    MacroThemeComparison,
)
from src.application.prediction_market_service import PredictionMarketScreenerRequest, PredictionMarketService
from src.models.prediction_markets import PredictionMarketRecord
from src.services.macro_adapters import (
    DBnomicsMacroAdapter,
    IBKRMacroFXAdapter,
    FredMacroAdapter,
    TreasuryCurveAdapter,
    USMacroEventsAdapter,
)
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
    "fx-eurgbp": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "EUR",
        "quote_currency": "GBP",
        "title": "EUR/GBP",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service.",
    },
    "fx-eurchf": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "EUR",
        "quote_currency": "CHF",
        "title": "EUR/CHF",
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
    "fx-usdcnh": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "USD",
        "quote_currency": "CNH",
        "title": "USD/CNH",
        "unit": "fx",
        "frequency": "daily",
        "theme": "policy",
        "mode_tags": ["snapshot"],
        "history_days": 540,
        "ttl_hours": 12,
        "transformation_note": "Daily FX history is sourced from IBKR midpoint market data through Gamma's existing market-data service. Gamma uses CNH for the traded offshore yuan pair rather than onshore CNY.",
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
    "fx-nzdusd": {
        "kind": "fx",
        "region": "Global",
        "base_currency": "NZD",
        "quote_currency": "USD",
        "title": "NZD/USD",
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

EVENT_STUDY_LOOKBACK_DAYS = 120
EVENT_STUDY_RECENT_LIMIT = 4
EVENT_STUDY_UPCOMING_LIMIT = 6
POLICY_MEETING_PATH_LIMIT = 4
COHERENCE_SIGNAL_THRESHOLD = 0.2
COHERENCE_PROGRESS_THRESHOLD = 0.6
EVENT_WINDOW_DAYS = {
    "daily": 7,
    "monthly": 40,
    "quarterly": 120,
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
        "fx-eurusd",
        "fx-gbpusd",
        "fx-eurgbp",
        "fx-eurchf",
        "fx-usdjpy",
        "fx-usdchf",
        "fx-usdcnh",
        "fx-usdcad",
        "fx-audusd",
        "fx-nzdusd",
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


@dataclass(frozen=True)
class _LeadLagCandidate:
    metric: MacroMetricRecord
    signal_score: float
    tone: str
    observed_at: datetime | None
    lag_days: float | None
    lag_label: str | None


@dataclass(frozen=True)
class _EventWindowContext:
    before_point: MacroSeriesPoint
    after_point: MacroSeriesPoint
    observed_at: datetime
    lag_days: float
    lag_label: str


class MacroService:
    def __init__(
        self,
        *,
        fred_adapter: FredMacroAdapter,
        treasury_adapter: TreasuryCurveAdapter,
        events_adapter: USMacroEventsAdapter,
        fx_adapter: IBKRMacroFXAdapter | None = None,
        dbnomics_adapter: DBnomicsMacroAdapter | None = None,
        prediction_market_service: PredictionMarketService | None = None,
    ) -> None:
        self.fred_adapter = fred_adapter
        self.treasury_adapter = treasury_adapter
        self.events_adapter = events_adapter
        self.fx_adapter = fx_adapter
        self.dbnomics_adapter = dbnomics_adapter
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
        event_studies = self._build_event_studies(
            region=region,
            histories=histories,
            linked_markets=linked_markets,
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
        retrieved_at = _max_timestamp(
            [row.retrieved_at for row in histories.values()]
            + [row.retrieved_at for row in comparison_histories.values()]
            + [row.retrieved_at for row in events]
            + [row.retrieved_at for row in event_studies]
            + [row.retrieved_at for row in divergences]
            + [rates_policy.retrieved_at],
        )
        return MacroSnapshotPayload(
            region=region,
            timeframe=timeframe,
            theme=theme,
            comparison_region=comparison_region,
            available_regions=list(REGION_ORDER),
            available_timeframes=list(TIMEFRAME_DAYS),
            available_themes=THEME_ORDER,
            focus_items=self._build_snapshot_focus_items(
                region=region,
                divergences=divergences,
                rates_policy=rates_policy,
                event_studies=event_studies,
                events=events,
            ),
            snapshot_cards=self._build_snapshot_cards(
                region=region,
                histories=histories,
                comparison_histories=comparison_histories,
                comparison_region=comparison_region,
                divergences=divergences,
                events=events,
                event_studies=event_studies,
                rates_policy=rates_policy,
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
            event_studies=event_studies,
            upcoming_events=events[:5],
            warnings=warnings,
            source_provider="fred",
            retrieved_at=retrieved_at,
            origin="macro_service.snapshot",
            transformation_note="Snapshot combines normalized FRED series histories, Treasury curve snapshots where available, comparison-aware metric overlays, event-window studies, and official calendar events into a mode-oriented macro workspace.",
        )

    def get_series_history(self, series_id: str, *, region: str = "US", timeframe: str = "1Y", force_refresh: bool = False) -> MacroSeriesHistory | None:
        normalized_region = self._normalize_region(region)
        data_region = self._data_region(normalized_region)
        if data_region == "US" and series_id.startswith("eu-"):
            return None
        if data_region == "EU" and series_id.startswith("us-"):
            return None
        return self._load_histories([series_id], timeframe=self._normalize_timeframe(timeframe), force_refresh=force_refresh).get(series_id)

    def get_dbnomics_series_history(
        self,
        *,
        provider_code: str,
        dataset_code: str,
        series_code: str,
        region: str = "Global",
        theme: str = "macro",
        timeframe: str = "1Y",
        force_refresh: bool = False,
    ) -> MacroSeriesHistory | None:
        if self.dbnomics_adapter is None:
            return None
        normalized_timeframe = self._normalize_timeframe(timeframe)
        start, end = self._history_window(TIMEFRAME_DAYS.get(normalized_timeframe, 370) + 45, normalized_timeframe)
        result = self.dbnomics_adapter.get_series(
            provider_code,
            dataset_code,
            series_code,
            start=start,
            end=end,
            ttl=timedelta(hours=24),
            force_refresh=force_refresh,
        )
        metadata = result.metadata
        full_id = f"{metadata.provider_code}/{metadata.dataset_code}/{metadata.series_code}"
        title = metadata.series_name or full_id
        note = (
            "External DB.nomics series loaded on demand for macro research. Gamma preserves provider/dataset/series identifiers, "
            "keeps the response read-only, and does not fill missing periods."
        )
        return MacroSeriesHistory(
            series_id=f"dbnomics:{full_id}",
            title=title,
            region=str(region or "Global").strip() or "Global",
            unit=None,
            frequency=metadata.frequency or "unknown",
            theme=str(theme or "macro").strip() or "macro",
            mode_tags=["external", "dbnomics"],
            points=result.points,
            source_provider="dbnomics",
            retrieved_at=result.retrieved_at,
            origin=f"dbnomics.series.observations:{full_id}",
            transformation_note=note,
        )

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
            coherence = self._build_timeframe_coherence_profile(
                region=data_region,
                theme=theme_name,
                signal_rows=signal_rows,
                histories=loaded_histories,
                timeframe=timeframe,
            )
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
            summary = self._divergence_summary(theme_name, primary_driver, counter_signal, coherence=coherence)
            if comparison_region is not None and comparison_score is not None:
                summary = f"{summary} Divergence is {score_gap_display} versus {comparison_region} on the same theme."
            research_focus = self._divergence_research_focus(
                theme_name,
                primary_driver=primary_driver,
                counter_signal=counter_signal,
                coherence=coherence,
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
                    coherence=coherence,
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

    def _build_event_studies(
        self,
        *,
        region: str,
        histories: dict[str, MacroSeriesHistory],
        linked_markets: dict[str, list[MacroLinkedPredictionMarket]],
        force_refresh: bool,
    ) -> list[MacroEventStudy]:
        normalized_region = self._normalize_region(region)
        current_time = now_utc()
        source_events = self.events_adapter.list_events(
            region=normalized_region,
            as_of=current_time - timedelta(days=EVENT_STUDY_LOOKBACK_DAYS),
            force_refresh=force_refresh,
            limit=(EVENT_STUDY_RECENT_LIMIT + EVENT_STUDY_UPCOMING_LIMIT) * 3,
        )
        recent_events = sorted(
            [event for event in source_events if event.scheduled_at <= current_time],
            key=lambda event: event.scheduled_at,
            reverse=True,
        )[:EVENT_STUDY_RECENT_LIMIT]
        upcoming_events = sorted(
            [event for event in source_events if event.scheduled_at > current_time],
            key=lambda event: event.scheduled_at,
        )[:EVENT_STUDY_UPCOMING_LIMIT]
        rows: list[MacroEventStudy] = []
        for event in [*recent_events, *upcoming_events]:
            theme = self._event_study_theme(event.category)
            if theme is None:
                continue
            study = self._build_event_study(
                region=region,
                theme=theme,
                event=event,
                histories=histories,
                linked_markets=linked_markets.get(theme, []),
                current_time=current_time,
            )
            if study is not None:
                rows.append(study)
        return rows

    def _build_event_study(
        self,
        *,
        region: str,
        theme: str,
        event: MacroEventRecord,
        histories: dict[str, MacroSeriesHistory],
        linked_markets: list[MacroLinkedPredictionMarket],
        current_time: datetime,
    ) -> MacroEventStudy | None:
        data_region = self._data_region(region)
        reactions: list[MacroEventReactionSignal] = []
        window_contexts: list[_EventWindowContext] = []
        for series_id in REGION_THEME_SERIES.get(data_region, {}).get(theme, []):
            history = histories.get(series_id)
            if history is None:
                continue
            signal, window_context = self._build_event_reaction_signal(
                region=data_region,
                theme=theme,
                event=event,
                history=history,
                current_time=current_time,
            )
            if signal is not None:
                reactions.append(signal)
            if window_context is not None:
                window_contexts.append(window_context)
        if len(reactions) < 2:
            return None
        primary_reaction = max(reactions, key=lambda row: row.signal_score)
        counter_reaction = min(reactions, key=lambda row: row.signal_score)
        sorted_reactions = sorted(reactions, key=lambda row: (-abs(row.signal_score), row.metric.label))
        timing = "recent" if event.scheduled_at <= current_time else "upcoming"
        coherence = self._build_event_coherence_profile(
            theme=theme,
            timing=timing,
            event=event,
            reactions=reactions,
        )
        window_start = min((context.before_point.timestamp for context in window_contexts), default=None)
        window_end = max((context.after_point.timestamp for context in window_contexts), default=None)
        return MacroEventStudy(
            study_id=f"{event.event_id}:{theme}",
            theme=theme,
            timing=timing,
            headline=self._event_study_headline(event, theme=theme, timing=timing),
            summary=self._event_study_summary(
                theme,
                timing=timing,
                primary_reaction=primary_reaction,
                counter_reaction=counter_reaction,
                coherence=coherence,
            ),
            window_label="Post-event window" if timing == "recent" else "Pre-event window",
            window_start=window_start,
            window_end=window_end,
            window_start_label=window_start.date().isoformat() if window_start is not None else None,
            window_end_label=window_end.date().isoformat() if window_end is not None else None,
            event=event,
            reactions=sorted_reactions[:4],
            primary_reaction=primary_reaction,
            counter_reaction=counter_reaction,
            coherence=coherence,
            linked_markets=list(linked_markets),
            research_focus=self._event_study_research_focus(
                theme,
                timing=timing,
                primary_reaction=primary_reaction,
                counter_reaction=counter_reaction,
                coherence=coherence,
            ),
            source_provider=event.source_provider,
            retrieved_at=_max_timestamp(
                [event.retrieved_at] + [row.retrieved_at for row in reactions],
            ),
            origin="macro_service.event_studies",
            transformation_note="Event studies compare curated proxies across explicit pre-event and post-event observation windows, highlight the strongest confirming and opposing reactions, and attach a transparent first-pass lead-lag/coherence summary.",
        )

    def _build_event_reaction_signal(
        self,
        *,
        region: str,
        theme: str,
        event: MacroEventRecord,
        history: MacroSeriesHistory,
        current_time: datetime,
    ) -> tuple[MacroEventReactionSignal | None, _EventWindowContext | None]:
        timing = "recent" if event.scheduled_at <= current_time else "upcoming"
        window_context = self._event_window_context(history=history, event_time=event.scheduled_at, current_time=current_time)
        if window_context is None:
            return None, None
        before_point = window_context.before_point
        after_point = window_context.after_point
        if after_point.timestamp <= before_point.timestamp:
            return None, None
        move_value = after_point.value - before_point.value
        factor = REGION_THEME_FACTORS.get(region, {}).get(theme, {}).get(history.series_id, 1.0)
        scale = SIGNAL_SCALES.get(history.series_id, 1.0)
        signal_score = round(max(min((move_value / scale) * factor, 3.0), -3.0), 2)
        metric = MacroMetricRecord(
            metric_id=f"{event.event_id}:{history.series_id}",
            label=history.title,
            value=after_point.value,
            display_value=_format_metric(after_point.value, history.unit),
            unit=history.unit,
            delta_value=move_value,
            delta_display=_format_delta(move_value, history.unit),
            series_id=history.series_id,
            source_provider=history.source_provider,
            retrieved_at=max(filter(None, [history.retrieved_at, before_point.retrieved_at, after_point.retrieved_at]), default=history.retrieved_at),
            origin="macro_service.event_study_metric",
            transformation_note="Event-study metrics anchor each curated proxy to the nearest pre-event and post-event observations so macro reactions can be compared across series frequencies.",
        )
        return MacroEventReactionSignal(
            role="lead" if signal_score >= 0.2 else "counter" if signal_score <= -0.2 else "lagging",
            tone="reinforcing" if signal_score >= 0.2 else "opposing" if signal_score <= -0.2 else "mixed",
            signal_score=signal_score,
            signal_score_display=f"{signal_score:+.2f}",
            move_value=move_value,
            move_display=metric.delta_display,
            before_display_value=_format_metric(before_point.value, history.unit),
            after_display_value=metric.display_value,
            observed_at=window_context.observed_at,
            observed_label=window_context.observed_at.date().isoformat(),
            lag_days=window_context.lag_days,
            lag_label=window_context.lag_label,
            interpretation=self._event_reaction_interpretation(
                theme,
                timing=timing,
                metric=metric,
                signal_score=signal_score,
                event_title=event.title,
            ),
            metric=metric,
            source_provider=history.source_provider,
            retrieved_at=metric.retrieved_at,
            origin="macro_service.event_reaction_signal",
            transformation_note="Event-reaction signals rank which curated proxies are leading, confirming, or lagging around a scheduled catalyst.",
        ), window_context

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
        event_studies: list[MacroEventStudy],
        rates_policy: MacroRatesPolicySummary,
        linked_markets: dict[str, list[MacroLinkedPredictionMarket]],
        timeframe: str,
    ) -> list[MacroSnapshotCard]:
        data_region = self._data_region(region)
        divergence_map = {row.theme: row for row in divergences}
        recent_study_by_theme = {
            study.theme: study
            for study in sorted((row for row in event_studies if row.timing == "recent"), key=lambda item: item.event.scheduled_at, reverse=True)
        }
        next_event_by_theme = {
            theme: next((event for event in events if self._event_study_theme(event.category) == theme), None)
            for theme in [name for name in THEME_ORDER if name != "all"]
        }
        if data_region == "EU":
            cards = [
                self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Activity and labor backdrop", summary="Industrial output, unemployment, and curve slope frame the EU growth picture.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("eu-industrial-production-yoy"), histories.get("eu-unemployment-rate"), histories.get("eu-3m10y-slope"), histories.get("eu-10y-yield"), histories.get("eu-eurusd")], linked_markets=linked_markets.get("growth", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories, why_now=self._snapshot_card_why_now(theme="growth", divergence=divergence_map.get("growth"), recent_study=recent_study_by_theme.get("growth"), next_event=next_event_by_theme.get("growth"), fallback=None), signal_label=self._snapshot_card_signal_label(divergence_map.get("growth")), drilldown_label=self._snapshot_card_drilldown_label(mode_target="cross_asset", target_theme="growth")),
                self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="HICP versus market signals", summary="Headline HICP alongside FX and long rates shows whether markets are absorbing the inflation narrative.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("eu-hicp-yoy"), histories.get("eu-eurusd"), histories.get("eu-10y-yield"), histories.get("eu-policy-rate"), histories.get("eu-3m10y-slope")], linked_markets=linked_markets.get("inflation", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories, why_now=self._snapshot_card_why_now(theme="inflation", divergence=divergence_map.get("inflation"), recent_study=recent_study_by_theme.get("inflation"), next_event=next_event_by_theme.get("inflation"), fallback=None), signal_label=self._snapshot_card_signal_label(divergence_map.get("inflation")), drilldown_label=self._snapshot_card_drilldown_label(mode_target="cross_asset", target_theme="inflation")),
                self._build_metric_card(card_id="policy", title="Policy Context", subtitle="ECB rate and front-end pricing", summary="ECB and money-market rates lead; the long end confirms direction.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("eu-policy-rate"), histories.get("eu-3m-rate"), histories.get("eu-10y-yield"), histories.get("eu-eurusd"), histories.get("eu-3m10y-slope")], linked_markets=linked_markets.get("policy", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories, why_now=self._snapshot_card_why_now(theme="policy", divergence=divergence_map.get("policy"), recent_study=recent_study_by_theme.get("policy"), next_event=next_event_by_theme.get("policy"), fallback=rates_policy.path_headline), signal_label=rates_policy.market_alignment_label or self._snapshot_card_signal_label(divergence_map.get("policy")), drilldown_label=self._snapshot_card_drilldown_label(mode_target="rates_policy", target_theme="policy")),
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
                cards.append(
                    self._build_metric_card(
                        card_id="dollar",
                        title="Dollar / FX Proxy",
                        subtitle="IBKR major pairs",
                        summary="Major FX pairs frame the dollar tape around policy and global stress catalysts.",
                        mode_target="cross_asset",
                        target_theme="policy",
                        metric_histories=[
                            histories.get("us-dollar-broad"),
                            histories.get("fx-eurusd"),
                            histories.get("fx-gbpusd"),
                            histories.get("fx-eurgbp"),
                            histories.get("fx-eurchf"),
                            histories.get("fx-usdjpy"),
                            histories.get("fx-usdchf"),
                            histories.get("fx-usdcnh"),
                            histories.get("fx-usdcad"),
                            histories.get("fx-audusd"),
                            histories.get("fx-nzdusd"),
                        ],
                        linked_markets=linked_markets.get("policy", []),
                        timeframe=timeframe,
                        comparison_region=comparison_region,
                        comparison_histories=comparison_histories,
                    )
                )
            credit_history = histories.get("us-hy-oas")
            if credit_history is not None:
                cards.append(self._build_metric_card(card_id="credit", title="Credit / Stress Proxy", subtitle="HY spread as stress gauge", summary="Credit spreads proxy tightening financial conditions and recession risk.", mode_target="cross_asset", target_theme="recession_risk", metric_histories=[histories.get("us-hy-oas"), histories.get("us-2s10s-slope"), histories.get("us-unemployment-rate")], linked_markets=linked_markets.get("recession_risk", []), timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories))
        return self._hydrate_snapshot_cards(
            cards=cards,
            divergences=divergence_map,
            recent_studies=recent_study_by_theme,
            next_events=next_event_by_theme,
            rates_policy=rates_policy,
        )

    def _build_metric_card(self, *, card_id: str, title: str, subtitle: str, summary: str, mode_target: str, target_theme: str, metric_histories: list[MacroSeriesHistory | None], linked_markets: list[MacroLinkedPredictionMarket], timeframe: str, comparison_region: str | None, comparison_histories: dict[str, MacroSeriesHistory], why_now: str | None = None, signal_label: str | None = None, drilldown_label: str | None = None) -> MacroSnapshotCard:
        metrics = [self._metric_from_history(history, timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for history in metric_histories if history is not None]
        return MacroSnapshotCard(card_id=card_id, title=title, subtitle=subtitle, summary=summary, why_now=why_now, mode_target=mode_target, target_theme=target_theme, signal_label=signal_label, drilldown_label=drilldown_label, metrics=metrics, linked_markets=list(linked_markets), source_provider=metrics[0].source_provider if metrics else "fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.snapshot_cards", transformation_note="Snapshot cards summarize the latest level and active-timeframe change for curated macro series, add a backend why-now interpretation where available, and keep the next drill-down explicit.")

    def _hydrate_snapshot_cards(
        self,
        *,
        cards: list[MacroSnapshotCard],
        divergences: dict[str, MacroDivergenceRecord],
        recent_studies: dict[str, MacroEventStudy],
        next_events: dict[str, MacroEventRecord | None],
        rates_policy: MacroRatesPolicySummary,
    ) -> list[MacroSnapshotCard]:
        fallback_by_card = {
            "policy": rates_policy.path_headline,
            "curve-shape": rates_policy.path_summary or rates_policy.path_headline,
            "real-yields": rates_policy.expectation_summary or rates_policy.path_research_focus,
            "dollar": "The broad dollar remains a liquid policy-and-stress proxy between catalysts.",
            "credit": "Credit remains the cleanest liquid stress proxy inside the macro workspace.",
            "fx": "FX remains a policy-sensitive cross-asset proxy when deeper sovereign coverage is limited.",
        }
        signal_by_card = {
            "policy": rates_policy.market_alignment_label,
            "curve-shape": rates_policy.market_alignment_label,
        }
        hydrated_cards: list[MacroSnapshotCard] = []
        for card in cards:
            theme = card.target_theme or card.card_id
            divergence = divergences.get(theme)
            hydrated_cards.append(
                replace(
                    card,
                    why_now=card.why_now
                    if card.why_now is not None
                    else self._snapshot_card_why_now(
                        theme=theme,
                        divergence=divergence,
                        recent_study=recent_studies.get(theme),
                        next_event=next_events.get(theme),
                        fallback=fallback_by_card.get(card.card_id),
                    ),
                    signal_label=card.signal_label
                    if card.signal_label is not None
                    else signal_by_card.get(card.card_id) or self._snapshot_card_signal_label(divergence),
                    drilldown_label=card.drilldown_label
                    if card.drilldown_label is not None
                    else self._snapshot_card_drilldown_label(mode_target=card.mode_target, target_theme=card.target_theme),
                )
            )
        return hydrated_cards

    def _build_snapshot_focus_items(
        self,
        *,
        region: str,
        divergences: list[MacroDivergenceRecord],
        rates_policy: MacroRatesPolicySummary,
        event_studies: list[MacroEventStudy],
        events: list[MacroEventRecord],
    ) -> list[MacroSnapshotFocusItem]:
        items: list[MacroSnapshotFocusItem] = []
        if divergences:
            divergence = divergences[0]
            items.append(
                MacroSnapshotFocusItem(
                    focus_id="top-divergence",
                    title="Biggest disagreement",
                    summary=divergence.summary,
                    why_now=divergence.research_focus or "Cross-asset disagreement is currently the cleanest research setup.",
                    mode_target="cross_asset",
                    target_theme=divergence.theme,
                    signal_label=divergence.coherence.coherence_label if divergence.coherence is not None else divergence.label,
                    source_provider=divergence.source_provider,
                    retrieved_at=divergence.retrieved_at,
                    origin="macro_service.snapshot_focus",
                    transformation_note="Snapshot focus items rank the most actionable current macro questions from the reusable divergence, rates, and event-study layers.",
                )
            )
        if rates_policy.path_headline is not None:
            items.append(
                MacroSnapshotFocusItem(
                    focus_id="policy-path",
                    title="Policy expectations",
                    summary=rates_policy.path_headline,
                    why_now=rates_policy.expectation_summary or rates_policy.path_research_focus or "Front-end rates remain the cleanest policy read.",
                    mode_target="rates_policy",
                    target_theme="policy",
                    signal_label=rates_policy.market_alignment_label,
                    source_provider=rates_policy.source_provider,
                    retrieved_at=rates_policy.retrieved_at,
                    origin="macro_service.snapshot_focus",
                    transformation_note="Snapshot focus items rank the most actionable current macro questions from the reusable divergence, rates, and event-study layers.",
                )
            )
        recent_study = next((study for study in event_studies if study.timing == "recent"), None)
        if recent_study is not None:
            items.append(
                MacroSnapshotFocusItem(
                    focus_id="recent-catalyst",
                    title="Fresh catalyst",
                    summary=recent_study.summary,
                    why_now=recent_study.research_focus or "Recent event absorption is still shaping the macro tape.",
                    mode_target="events_regimes",
                    target_theme=recent_study.theme,
                    signal_label=recent_study.coherence.coherence_label if recent_study.coherence is not None else recent_study.window_label,
                    source_provider=recent_study.source_provider,
                    retrieved_at=recent_study.retrieved_at,
                    origin="macro_service.snapshot_focus",
                    transformation_note="Snapshot focus items rank the most actionable current macro questions from the reusable divergence, rates, and event-study layers.",
                )
            )
        elif events:
            next_event = events[0]
            items.append(
                MacroSnapshotFocusItem(
                    focus_id="next-catalyst",
                    title="Next catalyst",
                    summary=f"{next_event.title} is the next scheduled macro event for the {region} lens.",
                    why_now=f"Scheduled for {next_event.scheduled_at.date().isoformat()}. Use Events / Regimes to inspect the setup window and which proxies have already moved.",
                    mode_target="events_regimes",
                    target_theme=self._event_study_theme(next_event.category),
                    signal_label=next_event.category,
                    source_provider=next_event.source_provider,
                    retrieved_at=next_event.retrieved_at,
                    origin="macro_service.snapshot_focus",
                    transformation_note="Snapshot focus items rank the most actionable current macro questions from the reusable divergence, rates, and event-study layers.",
                )
            )
        return items[:3]

    @staticmethod
    def _snapshot_card_signal_label(divergence: MacroDivergenceRecord | None) -> str | None:
        if divergence is None:
            return None
        return divergence.coherence.coherence_label if divergence.coherence is not None else divergence.label

    def _snapshot_card_why_now(
        self,
        *,
        theme: str,
        divergence: MacroDivergenceRecord | None,
        recent_study: MacroEventStudy | None,
        next_event: MacroEventRecord | None,
        fallback: str | None,
    ) -> str | None:
        if divergence is not None and divergence.coherence is not None:
            return divergence.coherence.summary
        if divergence is not None:
            return divergence.summary
        if recent_study is not None:
            return f"Recent catalyst: {recent_study.event.title}. {recent_study.summary}"
        if next_event is not None:
            return f"Next {theme.replace('_', ' ')} catalyst: {next_event.title} on {next_event.scheduled_at.date().isoformat()}."
        return fallback

    @staticmethod
    def _snapshot_card_drilldown_label(*, mode_target: str, target_theme: str | None) -> str:
        mode_label = {
            "snapshot": "Snapshot",
            "cross_asset": "Cross-Asset",
            "rates_policy": "Rates & Policy",
            "events_regimes": "Events / Regimes",
        }.get(mode_target, mode_target.replace("_", " ").title())
        if target_theme is None:
            return f"Open {mode_label}"
        return f"Open {mode_label} ({target_theme.replace('_', ' ')})"

    def _build_timeframe_coherence_profile(
        self,
        *,
        region: str,
        theme: str,
        signal_rows: list[tuple[MacroMetricRecord, float]],
        histories: dict[str, MacroSeriesHistory],
        timeframe: str,
    ) -> MacroCoherenceProfile | None:
        if len(signal_rows) < 2:
            return None
        direction_sign = 1 if sum(score for _, score in signal_rows) >= 0 else -1
        supporting = [(metric, score) for metric, score in signal_rows if score * direction_sign >= COHERENCE_SIGNAL_THRESHOLD]
        opposing = [(metric, score) for metric, score in signal_rows if score * direction_sign <= -COHERENCE_SIGNAL_THRESHOLD]
        neutral = [(metric, score) for metric, score in signal_rows if abs(score) < COHERENCE_SIGNAL_THRESHOLD]
        candidates = [
            candidate
            for metric, score in supporting
            for candidate in [self._build_timeframe_lead_lag_candidate(region=region, theme=theme, history=histories.get(metric.series_id or ""), metric=metric, signal_score=score, direction_sign=direction_sign, timeframe=timeframe)]
            if candidate is not None
        ]
        lead_candidate = min(candidates, key=lambda item: (item.observed_at or now_utc(), item.metric.label)) if candidates else None
        lag_candidate = max(candidates, key=lambda item: (item.observed_at or datetime.min, item.metric.label)) if len(candidates) >= 2 else None
        lag_span_days = (
            max((lag_candidate.observed_at - lead_candidate.observed_at).total_seconds() / 86400.0, 0.0)
            if lead_candidate is not None and lag_candidate is not None and lead_candidate.observed_at is not None and lag_candidate.observed_at is not None
            else None
        )
        lag_span_display = _format_day_span(lag_span_days)
        direction_label = self._theme_direction_label(theme, direction_sign)
        active_signals = len(supporting) + len(opposing)
        if lead_candidate is not None and lag_candidate is not None and lag_span_display is not None:
            summary = f"{lead_candidate.metric.label} moved first on the current {direction_label} read; {lag_candidate.metric.label} only aligned roughly {lag_span_display} later."
        elif lead_candidate is not None:
            summary = f"{lead_candidate.metric.label} is the clearest first mover in the current {direction_label} read."
        else:
            summary = f"No single series has taken clean ownership of the current {direction_label} read yet."
        if active_signals:
            summary = f"{summary} {len(supporting)} of {active_signals} active signals confirm while {len(opposing)} lean the other way."
        note = "Lead-lag is a first-pass heuristic: within the active timeframe, Gamma marks when each supportive proxy reached roughly 60% of its current themed move. Sparse monthly or quarterly series naturally lag daily markets in this view."
        return MacroCoherenceProfile(
            theme=theme,
            direction_label=direction_label,
            coherence_label=self._coherence_label(supporting_count=len(supporting), opposing_count=len(opposing), lag_span_days=lag_span_days, lag_tolerance_days=max(14.0, TIMEFRAME_DAYS.get(timeframe, 93) * 0.35)),
            supporting_signals=len(supporting),
            opposing_signals=len(opposing),
            neutral_signals=len(neutral),
            lead_signal=self._lead_lag_signal_from_candidate(lead_candidate, role="leader", note=note) if lead_candidate is not None else None,
            lag_signal=self._lead_lag_signal_from_candidate(lag_candidate, role="laggard", note=note) if lag_candidate is not None else None,
            lag_span_days=lag_span_days,
            lag_span_display=lag_span_display,
            summary=summary,
            methodology=note,
            source_provider=signal_rows[0][0].source_provider,
            retrieved_at=max((metric.retrieved_at for metric, _ in signal_rows if metric.retrieved_at is not None), default=now_utc()),
            origin="macro_service.coherence",
            transformation_note=note,
        )

    def _build_event_coherence_profile(
        self,
        *,
        theme: str,
        timing: str,
        event: MacroEventRecord,
        reactions: list[MacroEventReactionSignal],
    ) -> MacroCoherenceProfile | None:
        if len(reactions) < 2:
            return None
        direction_sign = 1 if sum(row.signal_score for row in reactions) >= 0 else -1
        supporting = [row for row in reactions if row.signal_score * direction_sign >= COHERENCE_SIGNAL_THRESHOLD]
        opposing = [row for row in reactions if row.signal_score * direction_sign <= -COHERENCE_SIGNAL_THRESHOLD]
        neutral = [row for row in reactions if abs(row.signal_score) < COHERENCE_SIGNAL_THRESHOLD]
        candidates = [
            _LeadLagCandidate(
                metric=row.metric,
                signal_score=row.signal_score,
                tone=row.tone,
                observed_at=row.observed_at,
                lag_days=row.lag_days,
                lag_label=row.lag_label,
            )
            for row in supporting
            if row.observed_at is not None
        ]
        lead_candidate = min(candidates, key=lambda item: (item.observed_at or event.scheduled_at, item.metric.label)) if candidates else None
        lag_candidate = max(candidates, key=lambda item: (item.observed_at or event.scheduled_at, item.metric.label)) if len(candidates) >= 2 else None
        lag_span_days = (
            max((lag_candidate.observed_at - lead_candidate.observed_at).total_seconds() / 86400.0, 0.0)
            if lead_candidate is not None and lag_candidate is not None and lead_candidate.observed_at is not None and lag_candidate.observed_at is not None
            else None
        )
        lag_span_display = _format_day_span(lag_span_days)
        direction_label = self._theme_direction_label(theme, direction_sign)
        active_signals = len(supporting) + len(opposing)
        if timing == "recent":
            if lead_candidate is not None and lag_candidate is not None and lag_span_display is not None:
                summary = f"{lead_candidate.metric.label} reacted first after {event.title}; {lag_candidate.metric.label} only confirmed roughly {lag_span_display} later."
            elif lead_candidate is not None:
                summary = f"{lead_candidate.metric.label} was the cleanest first responder after {event.title}."
            else:
                summary = f"No single proxy has taken clean ownership of the post-event move after {event.title} yet."
        else:
            if lead_candidate is not None and lag_candidate is not None and lag_span_display is not None:
                summary = f"{lead_candidate.metric.label} has moved first into {event.title}; {lag_candidate.metric.label} is following more slowly across the setup window."
            elif lead_candidate is not None:
                summary = f"{lead_candidate.metric.label} is setting the cleanest pre-event tone into {event.title}."
            else:
                summary = f"No proxy has established a decisive setup lead into {event.title} yet."
        if active_signals:
            summary = f"{summary} {len(supporting)} of {active_signals} active proxies align while {len(opposing)} still lean the other way."
        note = "Event lead-lag is a first-pass heuristic: Gamma compares the nearest pre-event and post-event observations for each curated proxy. Monthly or quarterly releases naturally lag daily markets in this view."
        return MacroCoherenceProfile(
            theme=theme,
            direction_label=direction_label,
            coherence_label=self._coherence_label(supporting_count=len(supporting), opposing_count=len(opposing), lag_span_days=lag_span_days, lag_tolerance_days=10.0),
            supporting_signals=len(supporting),
            opposing_signals=len(opposing),
            neutral_signals=len(neutral),
            lead_signal=self._lead_lag_signal_from_candidate(lead_candidate, role="leader", note=note) if lead_candidate is not None else None,
            lag_signal=self._lead_lag_signal_from_candidate(lag_candidate, role="laggard", note=note) if lag_candidate is not None else None,
            lag_span_days=lag_span_days,
            lag_span_display=lag_span_display,
            summary=summary,
            methodology=note,
            source_provider=event.source_provider,
            retrieved_at=max(
                ([event.retrieved_at] if event.retrieved_at is not None else [])
                + [row.retrieved_at for row in reactions if row.retrieved_at is not None],
                default=now_utc(),
            ),
            origin="macro_service.event_coherence",
            transformation_note=note,
        )

    def _build_timeframe_lead_lag_candidate(
        self,
        *,
        region: str,
        theme: str,
        history: MacroSeriesHistory | None,
        metric: MacroMetricRecord,
        signal_score: float,
        direction_sign: int,
        timeframe: str,
    ) -> _LeadLagCandidate | None:
        if history is None or not history.points:
            return None
        latest = history.points[-1]
        anchor = _point_before_cutoff(history.points, days=TIMEFRAME_DAYS.get(timeframe, 93))
        if anchor is None:
            return None
        factor = REGION_THEME_FACTORS.get(region, {}).get(theme, {}).get(history.series_id, 1.0) * direction_sign
        total_progress = (latest.value - anchor.value) * factor
        observed_at = latest.timestamp
        if total_progress > 0:
            threshold = total_progress * COHERENCE_PROGRESS_THRESHOLD
            for point in history.points:
                if point.timestamp < anchor.timestamp:
                    continue
                progress = (point.value - anchor.value) * factor
                if progress >= threshold:
                    observed_at = point.timestamp
                    break
        lag_days = max((observed_at - anchor.timestamp).total_seconds() / 86400.0, 0.0)
        return _LeadLagCandidate(
            metric=metric,
            signal_score=signal_score,
            tone="reinforcing" if signal_score * direction_sign >= COHERENCE_SIGNAL_THRESHOLD else "mixed",
            observed_at=observed_at,
            lag_days=lag_days,
            lag_label=f"{lag_days:.0f}d from window start" if lag_days >= 1.0 else "at window start",
        )

    @staticmethod
    def _lead_lag_signal_from_candidate(candidate: _LeadLagCandidate, *, role: str, note: str) -> MacroLeadLagSignal:
        return MacroLeadLagSignal(
            label=candidate.metric.label,
            series_id=candidate.metric.series_id,
            role=role,
            tone=candidate.tone,
            signal_score=round(candidate.signal_score, 2),
            signal_score_display=f"{candidate.signal_score:+.2f}",
            move_value=candidate.metric.delta_value,
            move_display=candidate.metric.delta_display,
            observed_at=candidate.observed_at,
            observed_label=candidate.observed_at.date().isoformat() if candidate.observed_at is not None else None,
            lag_days=candidate.lag_days,
            lag_label=candidate.lag_label,
            source_provider=candidate.metric.source_provider,
            retrieved_at=candidate.metric.retrieved_at,
            origin="macro_service.lead_lag",
            transformation_note=note,
        )

    @staticmethod
    def _coherence_label(*, supporting_count: int, opposing_count: int, lag_span_days: float | None, lag_tolerance_days: float) -> str:
        if supporting_count == 0 and opposing_count == 0:
            return "mixed"
        if opposing_count == 0 and supporting_count >= 3 and (lag_span_days is None or lag_span_days <= lag_tolerance_days):
            return "coherent"
        if supporting_count > opposing_count:
            return "narrow"
        return "fractured"

    @staticmethod
    def _theme_direction_label(theme: str, direction_sign: int) -> str:
        if theme == "inflation":
            return "firming inflation" if direction_sign >= 0 else "cooling inflation"
        if theme == "policy":
            return "tighter policy" if direction_sign >= 0 else "easier policy"
        if theme == "growth":
            return "improving growth" if direction_sign >= 0 else "softening growth"
        if theme == "recession_risk":
            return "rising stress" if direction_sign >= 0 else "easing stress"
        return "macro direction"

    def _build_policy_path_proxy(
        self,
        *,
        region: str,
        histories: dict[str, MacroSeriesHistory],
        comparison_histories: dict[str, MacroSeriesHistory],
        comparison_region: str | None,
        timeframe: str,
        events: list[MacroEventRecord],
        linked_markets: list[MacroLinkedPredictionMarket],
        policy_id: str,
        front_id: str,
        slope_id: str,
        policy_label: str,
        front_label: str,
    ) -> tuple[str | None, str | None, list[MacroMetricRecord], str | None, str | None, str | None]:
        policy_history = histories.get(policy_id)
        front_history = histories.get(front_id)
        slope_history = histories.get(slope_id)
        if policy_history is None or front_history is None:
            return None, None, [], None, None, None
        policy_metric = self._metric_from_history(
            policy_history,
            timeframe=timeframe,
            comparison_region=comparison_region,
            comparison_histories=comparison_histories,
        )
        front_metric = self._metric_from_history(
            front_history,
            timeframe=timeframe,
            comparison_region=comparison_region,
            comparison_histories=comparison_histories,
        )
        slope_metric = (
            self._metric_from_history(
                slope_history,
                timeframe=timeframe,
                comparison_region=comparison_region,
                comparison_histories=comparison_histories,
            )
            if slope_history is not None
            else None
        )
        gap_metric = self._build_difference_metric(
            label=f"{front_label} minus {policy_label}",
            left_history=front_history,
            right_history=policy_history,
            timeframe=timeframe,
            unit="bps",
            factor=100.0,
            comparison_region=comparison_region,
            comparison_histories=comparison_histories,
            metric_id=f"{front_id}:{policy_id}:gap",
            note="Policy-path proxy uses the front-end rates instrument minus the current policy rate/proxy. It is a research aid, not a full meeting-by-meeting curve.",
        )
        path_metrics = [policy_metric, front_metric, gap_metric]
        if slope_metric is not None:
            path_metrics.append(slope_metric)
        gap_bps = gap_metric.value
        if gap_bps is None:
            return None, None, path_metrics, None, None, None
        if gap_bps <= -25.0:
            stance = "easier"
            headline = f"{front_label} sits {abs(gap_bps):.0f} bps below {policy_label}; the path proxy leans toward cuts."
        elif gap_bps >= 25.0:
            stance = "tighter"
            headline = f"{front_label} sits {gap_bps:.0f} bps above {policy_label}; the path proxy leans toward further tightening."
        else:
            stance = "hold"
            headline = f"{front_label} is within {abs(gap_bps):.0f} bps of {policy_label}; hold remains the cleanest path proxy."
        next_policy_event = next((event for event in events if event.category == "policy"), None)
        next_event_text = (
            f" Next policy catalyst: {next_policy_event.title} on {next_policy_event.scheduled_at.date().isoformat()}."
            if next_policy_event is not None
            else ""
        )
        alignment_label, alignment_summary = self._linked_market_alignment(linked_markets=linked_markets)
        summary = (
            f"This is a front-end path proxy rather than a full meeting curve: compare {front_label}, {policy_label}, "
            f"and the active curve slope to judge whether easing or tightening is actually being priced.{next_event_text}"
        )
        research_focus = self._policy_path_research_focus(
            stance=stance,
            front_label=front_label,
            policy_label=policy_label,
            alignment_label=alignment_label,
        )
        return headline, summary, path_metrics, research_focus, alignment_label, alignment_summary

    def _build_policy_meeting_path(
        self,
        *,
        histories: dict[str, MacroSeriesHistory],
        events: list[MacroEventRecord],
        timeframe: str,
        policy_id: str,
        front_id: str,
        policy_label: str,
        front_label: str,
        alignment_label: str | None,
    ) -> MacroPolicyMeetingPathSummary | None:
        policy_history = histories.get(policy_id)
        front_history = histories.get(front_id)
        if policy_history is None or front_history is None:
            return None
        policy_metric = self._metric_from_history(policy_history, timeframe=timeframe)
        front_metric = self._metric_from_history(front_history, timeframe=timeframe)
        if policy_metric.value is None or front_metric.value is None:
            return None
        policy_events = [event for event in events if event.category == "policy"][:POLICY_MEETING_PATH_LIMIT]
        if not policy_events:
            return None
        meeting_count = len(policy_events)
        total_gap_bps = (front_metric.value - policy_metric.value) * 100.0
        incremental_bps = total_gap_bps / meeting_count
        note = (
            "Meeting ladder proxy spreads the current front-end minus policy gap evenly across the next scheduled "
            "policy meetings. It is a transparent research aid, not a futures-implied meeting curve."
        )
        meetings: list[MacroPolicyMeetingPathRow] = []
        for index, event in enumerate(policy_events, start=1):
            cumulative_bps = incremental_bps * index
            implied_policy_rate = policy_metric.value + (cumulative_bps / 100.0)
            meetings.append(
                MacroPolicyMeetingPathRow(
                    meeting_id=event.event_id,
                    title=event.title,
                    scheduled_at=event.scheduled_at,
                    meeting_index=index,
                    implied_policy_rate=implied_policy_rate,
                    implied_policy_rate_display=_format_metric(implied_policy_rate, "pct"),
                    incremental_change_bps=incremental_bps,
                    incremental_change_display=_format_delta(incremental_bps, "bps"),
                    cumulative_change_bps=cumulative_bps,
                    cumulative_change_display=_format_delta(cumulative_bps, "bps"),
                    source_provider=policy_history.source_provider,
                    retrieved_at=_max_timestamp(
                        [policy_history.retrieved_at, front_history.retrieved_at, event.retrieved_at],
                    ),
                    origin="macro_service.policy_meeting_path",
                    transformation_note=note,
                )
            )
        terminal_rate = meetings[-1].implied_policy_rate if meetings else None
        metrics = [
            MacroMetricRecord(
                metric_id=f"{policy_id}:{front_id}:meeting_count",
                label="Meetings",
                value=float(meeting_count),
                display_value=str(meeting_count),
                unit=None,
                source_provider=policy_history.source_provider,
                retrieved_at=policy_history.retrieved_at,
                origin="macro_service.policy_meeting_path_metric",
                transformation_note=note,
            ),
            MacroMetricRecord(
                metric_id=f"{policy_id}:{front_id}:cumulative_move",
                label="Cum. move",
                value=total_gap_bps,
                display_value=_format_delta(total_gap_bps, "bps"),
                unit="bps",
                source_provider=policy_history.source_provider,
                retrieved_at=policy_history.retrieved_at,
                origin="macro_service.policy_meeting_path_metric",
                transformation_note=note,
            ),
            MacroMetricRecord(
                metric_id=f"{policy_id}:{front_id}:avg_move",
                label="Avg / meeting",
                value=incremental_bps,
                display_value=_format_delta(incremental_bps, "bps"),
                unit="bps",
                source_provider=policy_history.source_provider,
                retrieved_at=policy_history.retrieved_at,
                origin="macro_service.policy_meeting_path_metric",
                transformation_note=note,
            ),
            MacroMetricRecord(
                metric_id=f"{policy_id}:{front_id}:terminal_rate",
                label="Terminal proxy",
                value=terminal_rate,
                display_value=_format_metric(terminal_rate, "pct"),
                unit="pct",
                source_provider=policy_history.source_provider,
                retrieved_at=policy_history.retrieved_at,
                origin="macro_service.policy_meeting_path_metric",
                transformation_note=note,
            ),
        ]
        if total_gap_bps <= -25.0:
            headline = f"Next {meeting_count} meetings spread an easing ladder toward {metrics[-1].display_value}."
        elif total_gap_bps >= 25.0:
            headline = f"Next {meeting_count} meetings spread a tightening ladder toward {metrics[-1].display_value}."
        else:
            headline = f"Next {meeting_count} meetings keep policy near {metrics[-1].display_value} if the hold proxy persists."
        summary = (
            f"The ladder spreads the current {front_label} versus {policy_label} gap evenly across the next "
            f"{meeting_count} scheduled policy meetings. Use it to judge whether current front-end pricing implies "
            "a gradual easing, hold, or tightening path."
        )
        return MacroPolicyMeetingPathSummary(
            headline=headline,
            summary=summary,
            window_label=f"Next {meeting_count} policy meetings",
            metrics=metrics,
            meetings=meetings,
            research_focus=self._policy_meeting_path_research_focus(
                total_gap_bps=total_gap_bps,
                front_label=front_label,
                policy_label=policy_label,
                alignment_label=alignment_label,
            ),
            source_provider=policy_history.source_provider,
            retrieved_at=_max_timestamp(
                [metric.retrieved_at for metric in metrics]
                + [meeting.retrieved_at for meeting in meetings],
            ),
            origin="macro_service.policy_meeting_path",
            transformation_note=note,
        )

    def _linked_market_alignment(self, *, linked_markets: list[MacroLinkedPredictionMarket]) -> tuple[str | None, str | None]:
        if not linked_markets:
            return None, None
        aligned = sum(1 for market in linked_markets if market.macro_alignment == "aligned")
        diverging = sum(1 for market in linked_markets if market.macro_alignment == "diverging")
        if aligned > diverging:
            return "aligned", "Linked policy contracts broadly agree with the rates-path proxy."
        if diverging > aligned:
            return "diverging", "Linked policy contracts are leaning the other way versus the rates-path proxy."
        return "mixed", "Linked policy contracts are mixed relative to the rates-path proxy."

    def _build_policy_expectation_view(
        self,
        *,
        linked_markets: list[MacroLinkedPredictionMarket],
        path_headline: str | None,
        alignment_label: str | None,
    ) -> tuple[list[MacroMetricRecord], str | None, str | None]:
        if not linked_markets:
            return [], None, None
        retrieved_at = _max_timestamp([market.retrieved_at for market in linked_markets])
        easier_contracts = [market for market in linked_markets if market.macro_stance == "policy-easier"]
        tighter_contracts = [market for market in linked_markets if market.macro_stance == "policy-tighter"]
        average_probability = (
            sum(market.current_probability for market in linked_markets if market.current_probability is not None) / len([market for market in linked_markets if market.current_probability is not None])
            if any(market.current_probability is not None for market in linked_markets)
            else None
        )
        average_repricing = (
            sum(market.recent_price_change for market in linked_markets if market.recent_price_change is not None) / len([market for market in linked_markets if market.recent_price_change is not None])
            if any(market.recent_price_change is not None for market in linked_markets)
            else None
        )
        if len(easier_contracts) > len(tighter_contracts):
            bias_label = "easier"
        elif len(tighter_contracts) > len(easier_contracts):
            bias_label = "tighter"
        else:
            bias_label = "mixed"
        metrics = [
            MacroMetricRecord(
                metric_id="policy-linked-count",
                label="Linked contracts",
                value=float(len(linked_markets)),
                display_value=str(len(linked_markets)),
                unit=None,
                source_provider="prediction_markets",
                retrieved_at=retrieved_at,
                origin="macro_service.policy_expectations",
                transformation_note="Policy expectation metrics summarize linked policy prediction contracts as a qualitative cross-check on the front-end rates path proxy.",
            ),
            MacroMetricRecord(
                metric_id="policy-linked-bias",
                label="Market bias",
                value={"easier": -1.0, "mixed": 0.0, "tighter": 1.0}[bias_label],
                display_value=bias_label.title(),
                unit=None,
                source_provider="prediction_markets",
                retrieved_at=retrieved_at,
                origin="macro_service.policy_expectations",
                transformation_note="Bias is a contract-count heuristic based on whether linked policy markets reference easier or tighter outcomes.",
            ),
            MacroMetricRecord(
                metric_id="policy-linked-average-probability",
                label="Avg probability",
                value=(average_probability * 100.0) if average_probability is not None else None,
                display_value=_format_probability(average_probability),
                unit=None,
                source_provider="prediction_markets",
                retrieved_at=retrieved_at,
                origin="macro_service.policy_expectations",
                transformation_note="Average probability is shown only as a light orientation aid across the linked policy-contract set and should not be treated as an implied rate path.",
            ),
            MacroMetricRecord(
                metric_id="policy-linked-average-repricing",
                label="Avg repricing",
                value=(average_repricing * 100.0) if average_repricing is not None else None,
                display_value=_format_prediction_change(average_repricing) if average_repricing is not None else "N/A",
                unit=None,
                source_provider="prediction_markets",
                retrieved_at=retrieved_at,
                origin="macro_service.policy_expectations",
                transformation_note="Average repricing aggregates recent policy-contract price changes to show whether the linked set is moving toward easier or tighter outcomes.",
            ),
        ]
        if alignment_label == "diverging":
            summary = f"Linked policy contracts skew {bias_label} while the front-end path proxy is pointing the other way. Use the contract set as a challenge case to the rates ladder rather than as a precise curve replacement."
        elif bias_label == "mixed":
            summary = "Linked policy contracts are not leaning cleanly one way, so the rates-path proxy still carries the cleaner directional signal."
        else:
            summary = f"Linked policy contracts are currently skewing {bias_label}; use that as a qualitative cross-check against the path proxy headline rather than a substitute for derivatives pricing."
        if path_headline is not None:
            summary = f"{summary} Current proxy read: {path_headline}"
        caveat = "Prediction-market contracts are mapped by text and topic rather than by exact policy-meeting payoff, so Gamma treats them as qualitative expectation overlays, not a meeting-implied curve."
        return metrics, summary, caveat

    @staticmethod
    def _policy_path_research_focus(*, stance: str, front_label: str, policy_label: str, alignment_label: str | None) -> str:
        if alignment_label == "diverging":
            return f"Test why linked policy contracts disagree with the {front_label} versus {policy_label} path proxy before the next policy event."
        if stance == "easier":
            return f"Watch whether {front_label} continues to move below {policy_label} or snaps back as the next policy meeting approaches."
        if stance == "tighter":
            return f"Watch whether {front_label} keeps pushing above {policy_label} or rolls over into the next policy meeting."
        return f"Watch whether {front_label} breaks away from {policy_label}; that move would be the first sign the hold proxy is no longer stable."

    @staticmethod
    def _policy_meeting_path_research_focus(
        *,
        total_gap_bps: float,
        front_label: str,
        policy_label: str,
        alignment_label: str | None,
    ) -> str:
        if alignment_label == "diverging":
            return f"Check whether linked policy contracts disagree with the meeting ladder because the {front_label} gap is overstating the path versus {policy_label}."
        if total_gap_bps <= -25.0:
            return f"Watch whether the next meetings actually validate the easing ladder implied by {front_label} versus {policy_label}."
        if total_gap_bps >= 25.0:
            return f"Watch whether the next meetings validate the tightening ladder implied by {front_label} versus {policy_label}."
        return f"Focus on what would break the hold ladder first: {front_label}, {policy_label}, or linked policy contracts."

    def _build_rates_policy(self, *, region: str, histories: dict[str, MacroSeriesHistory], comparison_histories: dict[str, MacroSeriesHistory], comparison_region: str | None, events: list[MacroEventRecord], linked_markets: list[MacroLinkedPredictionMarket], timeframe: str, force_refresh: bool) -> MacroRatesPolicySummary:
        data_region = self._data_region(region)
        curve_nodes, curve_retrieved_at = self._load_curve_nodes(region=data_region, histories=histories, force_refresh=force_refresh, timeframe=timeframe)
        if data_region == "EU":
            policy_ids = ("eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-3m10y-slope")
            real_ids = ("eu-hicp-yoy", "eu-eurusd")
            path_config = {
                "policy_id": "eu-policy-rate",
                "front_id": "eu-3m-rate",
                "slope_id": "eu-3m10y-slope",
                "policy_label": "ECB policy proxy",
                "front_label": "3M rate proxy",
            }
            headline = "ECB and money-market proxies remain the cleanest read on EU macro conditions."
            slope_metric = next((self._metric_from_history(histories[series_id], timeframe=timeframe) for series_id in ("eu-3m10y-slope",) if series_id in histories), None)
            if slope_metric and slope_metric.value is not None:
                headline = "The EU curve is inverted against the 3M rate proxy." if slope_metric.value < 0 else "The EU 3M-to-10Y slope is positive."
            summary = "EU Rates & Policy is intentionally lighter in V1 and emphasizes ECB-rate proxies, the 3M versus 10Y slope, and inflation/FX context instead of a full sovereign curve stack."
        else:
            policy_ids = ("us-fed-funds", "us-2y-yield", "us-10y-yield", "us-2s10s-slope")
            real_ids = ("us-real-10y-yield", "us-5y-breakeven", "us-10y-breakeven")
            path_config = {
                "policy_id": "us-fed-funds",
                "front_id": "us-2y-yield",
                "slope_id": "us-2s10s-slope",
                "policy_label": "Fed Funds",
                "front_label": "2Y Treasury",
            }
            headline = "Front-end policy pricing remains the cleanest read on US macro conditions."
            slope_metric = next((self._metric_from_history(histories[series_id], timeframe=timeframe) for series_id in ("us-2s10s-slope",) if series_id in histories), None)
            if slope_metric and slope_metric.value is not None:
                headline = "The curve is still inverted." if slope_metric.value < 0 else "The curve is positive and no longer inverted."
            summary = "Rates & Policy emphasizes the current Treasury curve, front-end policy context, and the real-yield versus breakeven split."
        policy_metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for series_id in policy_ids if series_id in histories]
        real_yield_metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for series_id in real_ids if series_id in histories]
        visible_events = events[:4]
        comparison_summary = f"Comparing {region} rates context against {comparison_region} where equivalent concepts exist." if comparison_region is not None else None
        path_headline, path_summary, path_metrics, path_research_focus, market_alignment_label, market_alignment_summary = self._build_policy_path_proxy(
            region=region,
            histories=histories,
            comparison_histories=comparison_histories,
            comparison_region=comparison_region,
            timeframe=timeframe,
            events=visible_events,
            linked_markets=linked_markets,
            policy_id=path_config["policy_id"],
            front_id=path_config["front_id"],
            slope_id=path_config["slope_id"],
            policy_label=path_config["policy_label"],
            front_label=path_config["front_label"],
        )
        expectation_metrics, expectation_summary, expectation_caveat = self._build_policy_expectation_view(
            linked_markets=linked_markets,
            path_headline=path_headline,
            alignment_label=market_alignment_label,
        )
        meeting_path = self._build_policy_meeting_path(
            histories=histories,
            events=events,
            timeframe=timeframe,
            policy_id=path_config["policy_id"],
            front_id=path_config["front_id"],
            policy_label=path_config["policy_label"],
            front_label=path_config["front_label"],
            alignment_label=market_alignment_label,
        )
        return MacroRatesPolicySummary(headline=headline, summary=summary, policy_metrics=policy_metrics, curve_nodes=curve_nodes, real_yield_metrics=real_yield_metrics, events=visible_events, linked_markets=list(linked_markets), path_headline=path_headline, path_summary=path_summary, path_metrics=path_metrics, path_research_focus=path_research_focus, expectation_metrics=expectation_metrics, expectation_summary=expectation_summary, expectation_caveat=expectation_caveat, meeting_path=meeting_path, market_alignment_label=market_alignment_label, market_alignment_summary=market_alignment_summary, source_provider="treasury" if data_region == "US" else "fred", retrieved_at=_max_timestamp([curve_retrieved_at] + [row.retrieved_at for row in policy_metrics] + [row.retrieved_at for row in real_yield_metrics] + [row.retrieved_at for row in path_metrics] + [row.retrieved_at for row in expectation_metrics] + [row.retrieved_at for row in visible_events] + ([meeting_path.retrieved_at] if meeting_path is not None else [])), origin="macro_service.rates_policy", transformation_note="Rates & Policy combines region-specific series histories, Treasury XML curve snapshots where available, optional cross-region comparison overlays for matched concepts, linked prediction-market context, a front-end policy-path proxy, a transparent policy-expectation interpretation layer, and a meeting-ladder proxy derived from scheduled policy events.", comparison_region=comparison_region, comparison_summary=comparison_summary)

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
                rows.append(MacroThemeComparison(theme=theme, headline=f"{self._title_theme(theme)} signals", summary=divergence.summary if divergence is not None else "Theme coverage is available, but disagreement is currently muted.", agreement_label=divergence.label if divergence is not None else "low", metrics=metrics, linked_markets=list(linked_markets.get(theme, [])), primary_driver=divergence.primary_driver if divergence is not None else None, counter_signal=divergence.counter_signal if divergence is not None else None, coherence=divergence.coherence if divergence is not None else None, divergence_score=divergence.score if divergence is not None else None, research_focus=divergence.research_focus if divergence is not None else None, source_provider="fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.cross_asset", transformation_note="Cross-asset theme blocks line up curated region-specific series so the user can compare whether markets agree on a macro narrative, with optional cross-region overlays where concept matches exist, lead-lag/coherence annotations from the backend engine, and linked prediction contracts for the same theme.", comparison_region=comparison_region, comparison_summary=comparison_summary))
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
            macro_stance=stance_label,
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
        *,
        coherence: MacroCoherenceProfile | None,
    ) -> str:
        base_summary: str
        if counter_signal.signal_score <= -0.2:
            base_summary = f"{primary_driver.metric.label} is driving the {theme.replace('_', ' ')} read while {counter_signal.metric.label} is the clearest counter-signal."
        else:
            base_summary = f"{primary_driver.metric.label} is driving the {theme.replace('_', ' ')} read while {counter_signal.metric.label} is lagging as the weakest confirmation."
        if coherence is None:
            return base_summary
        return f"{base_summary} {coherence.summary}"

    def _divergence_research_focus(
        self,
        theme: str,
        *,
        primary_driver: MacroDivergenceSignal,
        counter_signal: MacroDivergenceSignal,
        coherence: MacroCoherenceProfile | None,
        comparison_region: str | None,
        score_gap_display: str | None,
    ) -> str:
        if counter_signal.signal_score <= -0.2:
            focus = f"Test whether {primary_driver.metric.label} or {counter_signal.metric.label} is more likely to reset first; that disagreement is carrying most of the {theme.replace('_', ' ')} divergence."
        else:
            focus = f"Test whether {counter_signal.metric.label} eventually catches up to {primary_driver.metric.label}; the theme currently depends on a narrow set of confirming proxies."
        if coherence is not None and coherence.lag_signal is not None and coherence.lead_signal is not None and coherence.lag_span_display is not None:
            focus = f"{focus} Gamma's lead-lag heuristic currently shows {coherence.lead_signal.label} first and {coherence.lag_signal.label} later by roughly {coherence.lag_span_display}."
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

    @staticmethod
    def _event_study_theme(category: str) -> str | None:
        normalized = str(category or "").strip().lower().replace(" ", "_")
        if normalized in {"growth", "inflation", "policy", "recession_risk"}:
            return normalized
        return None

    def _event_window_context(
        self,
        *,
        history: MacroSeriesHistory,
        event_time: datetime,
        current_time: datetime,
    ) -> _EventWindowContext | None:
        frequency = str(history.frequency or "").strip().lower()
        window_days = EVENT_WINDOW_DAYS.get(frequency, 30)
        if event_time <= current_time:
            before_point = _latest_point_at_or_before(history.points, event_time)
            after_point = _earliest_point_at_or_after(history.points, event_time, max_days=window_days)
            if before_point is None or after_point is None:
                return None
            lag_days = max((after_point.timestamp - event_time).total_seconds() / 86400.0, 0.0)
            return _EventWindowContext(
                before_point=before_point,
                after_point=after_point,
                observed_at=after_point.timestamp,
                lag_days=lag_days,
                lag_label=f"{lag_days:.0f}d after event" if lag_days >= 1.0 else "same-day follow-through",
            )
        before_anchor = event_time - timedelta(days=window_days)
        before_point = _latest_point_at_or_before(history.points, before_anchor)
        after_point = _latest_point_at_or_before(history.points, current_time)
        if before_point is None or after_point is None:
            return None
        lag_days = max((event_time - after_point.timestamp).total_seconds() / 86400.0, 0.0)
        return _EventWindowContext(
            before_point=before_point,
            after_point=after_point,
            observed_at=after_point.timestamp,
            lag_days=lag_days,
            lag_label=f"{lag_days:.0f}d before event" if lag_days >= 1.0 else "latest point is event-adjacent",
        )

    def _event_study_headline(self, event: MacroEventRecord, *, theme: str, timing: str) -> str:
        if timing == "recent":
            return f"{event.title}: how {theme.replace('_', ' ')} proxies absorbed the release"
        return f"{event.title}: what is repricing into the event"

    def _event_study_summary(
        self,
        theme: str,
        *,
        timing: str,
        primary_reaction: MacroEventReactionSignal,
        counter_reaction: MacroEventReactionSignal,
        coherence: MacroCoherenceProfile | None,
    ) -> str:
        theme_label = theme.replace("_", " ")
        base_summary: str
        if timing == "recent":
            if counter_reaction.signal_score <= -0.2:
                base_summary = (
                    f"After the event, {primary_reaction.metric.label} absorbed the clearest {theme_label} move "
                    f"while {counter_reaction.metric.label} pushed the other way."
                )
            else:
                base_summary = (
                    f"After the event, {primary_reaction.metric.label} led the {theme_label} repricing "
                    f"while {counter_reaction.metric.label} lagged as the weakest confirmation."
                )
        elif counter_reaction.signal_score <= -0.2:
            base_summary = (
                f"Into the event, {primary_reaction.metric.label} is leading the {theme_label} setup "
                f"while {counter_reaction.metric.label} is the clearest counter-signal."
            )
        else:
            base_summary = (
                f"Into the event, {primary_reaction.metric.label} is setting the {theme_label} tone "
                f"while {counter_reaction.metric.label} is lagging the move."
            )
        if coherence is None:
            return base_summary
        return f"{base_summary} {coherence.summary}"

    def _event_study_research_focus(
        self,
        theme: str,
        *,
        timing: str,
        primary_reaction: MacroEventReactionSignal,
        counter_reaction: MacroEventReactionSignal,
        coherence: MacroCoherenceProfile | None,
    ) -> str:
        theme_label = theme.replace("_", " ")
        if timing == "recent":
            focus = (
                f"Test whether the post-event move in {primary_reaction.metric.label} broadens into the rest of the "
                f"{theme_label} complex or mean-reverts first, especially versus {counter_reaction.metric.label}."
            )
        else:
            focus = (
                f"Track whether {counter_reaction.metric.label} catches up to {primary_reaction.metric.label} into the event; "
                f"that gap is the main pre-event research question."
            )
        if coherence is not None and coherence.lag_signal is not None and coherence.lead_signal is not None:
            focus = f"{focus} Gamma's lead-lag heuristic currently shows {coherence.lead_signal.label} first and {coherence.lag_signal.label} later."
        return focus

    def _event_reaction_interpretation(
        self,
        theme: str,
        *,
        timing: str,
        metric: MacroMetricRecord,
        signal_score: float,
        event_title: str,
    ) -> str:
        move_text = metric.delta_display or metric.display_value or "latest move"
        supportive_state, opposing_state = self._theme_signal_states(theme)
        if timing == "recent":
            if signal_score >= 0.2:
                return f"After {event_title}, {metric.label} moved {move_text} and points to {supportive_state}."
            if signal_score <= -0.2:
                return f"After {event_title}, {metric.label} moved {move_text} and points to {opposing_state}."
            return f"After {event_title}, {metric.label} moved {move_text} but remains a muted confirmation."
        if signal_score >= 0.2:
            return f"Into {event_title}, {metric.label} has moved {move_text} and is reinforcing {supportive_state}."
        if signal_score <= -0.2:
            return f"Into {event_title}, {metric.label} has moved {move_text} and is leaning toward {opposing_state}."
        return f"Into {event_title}, {metric.label} has moved {move_text} but is not yet a decisive signal."

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

    def _build_difference_metric(
        self,
        *,
        label: str,
        left_history: MacroSeriesHistory,
        right_history: MacroSeriesHistory,
        timeframe: str,
        unit: str,
        factor: float,
        comparison_region: str | None,
        comparison_histories: dict[str, MacroSeriesHistory],
        metric_id: str,
        note: str,
    ) -> MacroMetricRecord:
        latest_left = left_history.points[-1] if left_history.points else None
        latest_right = right_history.points[-1] if right_history.points else None
        previous_left = _point_before_cutoff(left_history.points, days=TIMEFRAME_DAYS.get(timeframe, 93))
        previous_right = _point_before_cutoff(right_history.points, days=TIMEFRAME_DAYS.get(timeframe, 93))
        current_value = (latest_left.value - latest_right.value) * factor if latest_left is not None and latest_right is not None else None
        previous_value = (previous_left.value - previous_right.value) * factor if previous_left is not None and previous_right is not None else None
        delta_value = current_value - previous_value if current_value is not None and previous_value is not None else None
        comparison_value = None
        comparison_delta_value = None
        if comparison_region is not None:
            comparison_left_id = self._counterpart_series_id(left_history.series_id, comparison_region)
            comparison_right_id = self._counterpart_series_id(right_history.series_id, comparison_region)
            comparison_left = comparison_histories.get(comparison_left_id) if comparison_left_id is not None else None
            comparison_right = comparison_histories.get(comparison_right_id) if comparison_right_id is not None else None
            if comparison_left is not None and comparison_right is not None and comparison_left.points and comparison_right.points:
                comparison_latest_left = comparison_left.points[-1]
                comparison_latest_right = comparison_right.points[-1]
                comparison_previous_left = _point_before_cutoff(comparison_left.points, days=TIMEFRAME_DAYS.get(timeframe, 93))
                comparison_previous_right = _point_before_cutoff(comparison_right.points, days=TIMEFRAME_DAYS.get(timeframe, 93))
                comparison_value = (comparison_latest_left.value - comparison_latest_right.value) * factor
                if comparison_previous_left is not None and comparison_previous_right is not None:
                    comparison_previous_value = (comparison_previous_left.value - comparison_previous_right.value) * factor
                    comparison_delta_value = comparison_value - comparison_previous_value
        gap_value = current_value - comparison_value if current_value is not None and comparison_value is not None else None
        return MacroMetricRecord(
            metric_id=metric_id,
            label=label,
            value=current_value,
            display_value=_format_metric(current_value, unit),
            unit=unit,
            delta_value=delta_value,
            delta_display=_format_delta(delta_value, unit),
            series_id=None,
            source_provider=left_history.source_provider,
            retrieved_at=max(filter(None, [left_history.retrieved_at, right_history.retrieved_at]), default=now_utc()),
            origin="macro_service.derived.policy_path_gap",
            transformation_note=note,
            comparison_region=comparison_region if comparison_value is not None else None,
            comparison_label=f"{comparison_region} gap" if comparison_value is not None and comparison_region is not None else None,
            comparison_value=comparison_value,
            comparison_display_value=_format_metric(comparison_value, unit) if comparison_value is not None else None,
            comparison_delta_value=comparison_delta_value,
            comparison_delta_display=_format_delta(comparison_delta_value, unit) if comparison_delta_value is not None else None,
            gap_value=gap_value,
            gap_display=_format_delta(gap_value, unit) if gap_value is not None else None,
        )

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


def _latest_point_at_or_before(points: list[MacroSeriesPoint], anchor: datetime) -> MacroSeriesPoint | None:
    for point in reversed(points):
        if point.timestamp <= anchor:
            return point
    return None


def _earliest_point_at_or_after(points: list[MacroSeriesPoint], anchor: datetime, *, max_days: int) -> MacroSeriesPoint | None:
    deadline = anchor + timedelta(days=max_days)
    for point in points:
        if point.timestamp < anchor:
            continue
        if point.timestamp <= deadline:
            return point
        break
    return None


def _utc_naive_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _max_timestamp(values: list[datetime | None], *, default: datetime | None = None) -> datetime:
    normalized = [
        normalized_value
        for value in values
        if (normalized_value := _utc_naive_timestamp(value)) is not None
    ]
    fallback = _utc_naive_timestamp(default) or now_utc()
    return max(normalized, default=fallback)


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


def _format_day_span(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 1.0:
        return "<1d"
    return f"{value:.0f}d"


def _format_prediction_change(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value * 100.0:+.1f} pts"


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
