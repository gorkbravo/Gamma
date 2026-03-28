from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from statistics import fmean, pstdev
from typing import Any

from src.models.macro import (
    MacroCurveNode,
    MacroDivergenceRecord,
    MacroEventRecord,
    MacroMetricRecord,
    MacroRatesPolicySummary,
    MacroSeriesHistory,
    MacroSeriesPoint,
    MacroSnapshotCard,
    MacroSnapshotPayload,
    MacroThemeComparison,
)
from src.services.macro_adapters import IBKRMacroFXAdapter, FredMacroAdapter, TreasuryCurveAdapter, USMacroEventsAdapter
from src.utils.time import now_utc

logger = logging.getLogger(__name__)


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
    "global-oil-wti": {
        "kind": "raw",
        "region": "Global",
        "provider_series_id": "DCOILWTICO",
        "title": "WTI Crude Oil",
        "unit": "usd",
        "frequency": "daily",
        "theme": "geopolitics",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 540,
        "ttl_hours": 24,
    },
    "global-natural-gas": {
        "kind": "raw",
        "region": "Global",
        "provider_series_id": "DHHNGSP",
        "title": "Henry Hub Natural Gas",
        "unit": "usd",
        "frequency": "daily",
        "theme": "inflation",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 540,
        "ttl_hours": 24,
    },
    "global-gold": {
        "kind": "raw",
        "region": "Global",
        "provider_series_id": "GOLDAMGBD228NLBM",
        "title": "Gold Spot",
        "unit": "usd",
        "frequency": "daily",
        "theme": "risk_appetite",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 540,
        "ttl_hours": 24,
    },
    "global-copper": {
        "kind": "raw",
        "region": "Global",
        "provider_series_id": "PCOPPUSDM",
        "title": "Copper Spot",
        "unit": "usd",
        "frequency": "monthly",
        "theme": "growth",
        "mode_tags": ["snapshot", "cross_asset"],
        "history_days": 1200,
        "ttl_hours": 72,
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
THEME_ORDER = ["all", "growth", "inflation", "policy", "recession_risk", "geopolitics", "risk_appetite"]
REGION_ORDER = ["US", "EU", "Global"]
PRIMARY_COMPARISON_REGIONS = {"US", "EU"}

REGION_THEME_SERIES = {
    "US": {
        "growth": ["us-real-gdp-yoy", "us-payrolls-yoy", "us-unemployment-rate", "us-2s10s-slope", "global-copper"],
        "inflation": ["us-cpi-yoy", "us-core-cpi-yoy", "us-5y-breakeven", "us-10y-breakeven", "global-oil-wti", "global-natural-gas"],
        "policy": ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-dollar-broad", "us-real-10y-yield"],
        "recession_risk": ["us-2s10s-slope", "us-hy-oas", "us-unemployment-rate", "us-dollar-broad", "global-gold"],
        "geopolitics": ["global-oil-wti", "global-gold", "us-dollar-broad", "us-hy-oas"],
        "risk_appetite": ["us-hy-oas", "global-copper", "global-gold", "us-dollar-broad"],
    },
    "EU": {
        "growth": ["eu-industrial-production-yoy", "eu-unemployment-rate", "eu-3m10y-slope", "global-copper"],
        "inflation": ["eu-hicp-yoy", "eu-eurusd", "eu-10y-yield", "global-oil-wti", "global-natural-gas"],
        "policy": ["eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-eurusd"],
        "recession_risk": ["eu-3m10y-slope", "eu-unemployment-rate", "eu-eurusd", "global-gold"],
        "geopolitics": ["global-oil-wti", "global-gold", "eu-eurusd", "eu-10y-yield"],
        "risk_appetite": ["global-copper", "global-gold", "eu-eurusd", "eu-10y-yield"],
    },
}

REGION_THEME_FACTORS = {
    "US": {
        "growth": {"us-real-gdp-yoy": 1.0, "us-payrolls-yoy": 1.0, "us-unemployment-rate": -1.0, "us-2s10s-slope": 0.6, "global-copper": 0.8},
        "inflation": {"us-cpi-yoy": 1.0, "us-core-cpi-yoy": 1.0, "us-5y-breakeven": 0.9, "us-10y-breakeven": 0.8, "global-oil-wti": 0.7, "global-natural-gas": 0.6},
        "policy": {"us-fed-funds": 1.0, "us-2y-yield": 1.0, "us-10y-yield": 0.4, "us-dollar-broad": 0.4, "us-real-10y-yield": 0.6},
        "recession_risk": {"us-2s10s-slope": -0.8, "us-hy-oas": 1.0, "us-unemployment-rate": 0.8, "us-dollar-broad": 0.2, "global-gold": 0.5},
        "geopolitics": {"global-oil-wti": 1.0, "global-gold": 0.8, "us-dollar-broad": 0.5, "us-hy-oas": 0.6},
        "risk_appetite": {"us-hy-oas": -1.0, "global-copper": 0.9, "global-gold": -0.8, "us-dollar-broad": -0.5},
    },
    "EU": {
        "growth": {"eu-industrial-production-yoy": 1.0, "eu-unemployment-rate": -0.9, "eu-3m10y-slope": 0.5, "global-copper": 0.8},
        "inflation": {"eu-hicp-yoy": 1.0, "eu-eurusd": -0.4, "eu-10y-yield": 0.3, "global-oil-wti": 0.7, "global-natural-gas": 0.7},
        "policy": {"eu-policy-rate": 1.0, "eu-3m-rate": 0.9, "eu-10y-yield": 0.4, "eu-eurusd": -0.2},
        "recession_risk": {"eu-3m10y-slope": -0.8, "eu-unemployment-rate": 0.8, "eu-eurusd": -0.2, "global-gold": 0.5},
        "geopolitics": {"global-oil-wti": 1.0, "global-gold": 0.8, "eu-eurusd": -0.3, "eu-10y-yield": 0.3},
        "risk_appetite": {"global-copper": 0.9, "global-gold": -0.8, "eu-eurusd": 0.3, "eu-10y-yield": 0.2},
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
    "global-oil-wti": 4.0,
    "global-natural-gas": 0.45,
    "global-gold": 35.0,
    "global-copper": 0.15,
    "eu-industrial-production-yoy": 1.0,
    "eu-unemployment-rate": 0.12,
    "eu-hicp-yoy": 0.25,
    "eu-policy-rate": 0.2,
    "eu-3m-rate": 0.15,
    "eu-10y-yield": 0.12,
    "eu-eurusd": 0.02,
    "eu-3m10y-slope": 20.0,
}

LEVEL_SIGNAL_CONFIG = {
    "us-real-gdp-yoy": {"anchor": 2.0, "scale": 1.0},
    "us-payrolls-yoy": {"anchor": 1.0, "scale": 0.75},
    "us-unemployment-rate": {"anchor": 4.0, "scale": 0.35},
    "us-cpi-yoy": {"anchor": 2.0, "scale": 0.75},
    "us-core-cpi-yoy": {"anchor": 2.0, "scale": 0.6},
    "us-fed-funds": {"anchor": 3.5, "scale": 0.75},
    "us-2y-yield": {"anchor": 4.0, "scale": 0.75},
    "us-real-10y-yield": {"anchor": 1.5, "scale": 0.5},
    "us-5y-breakeven": {"anchor": 2.3, "scale": 0.3},
    "us-10y-breakeven": {"anchor": 2.3, "scale": 0.3},
    "us-hy-oas": {"anchor": 3.5, "scale": 0.6},
    "us-2s10s-slope": {"anchor": 0.0, "scale": 40.0},
    "eu-industrial-production-yoy": {"anchor": 1.0, "scale": 1.0},
    "eu-unemployment-rate": {"anchor": 6.0, "scale": 0.4},
    "eu-hicp-yoy": {"anchor": 2.0, "scale": 0.6},
    "eu-policy-rate": {"anchor": 2.5, "scale": 0.5},
    "eu-3m-rate": {"anchor": 2.5, "scale": 0.5},
    "eu-3m10y-slope": {"anchor": 0.0, "scale": 35.0},
    "global-oil-wti": {"anchor": 75.0, "scale": 10.0},
    "global-natural-gas": {"anchor": 3.0, "scale": 0.8},
    "global-gold": {"anchor": 2000.0, "scale": 120.0},
    "global-copper": {"anchor": 4.2, "scale": 0.35},
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
        "global-oil-wti",
        "global-natural-gas",
        "global-gold",
        "global-copper",
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
        "global-oil-wti",
        "global-natural-gas",
        "global-gold",
        "global-copper",
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
    ) -> None:
        self.fred_adapter = fred_adapter
        self.treasury_adapter = treasury_adapter
        self.events_adapter = events_adapter
        self.fx_adapter = fx_adapter

    def get_snapshot(self, request: MacroSnapshotRequest) -> MacroSnapshotPayload:
        region = self._normalize_region(request.region)
        timeframe = self._normalize_timeframe(request.timeframe)
        theme = self._normalize_theme(request.theme)
        comparison_region = self._normalize_comparison(region, request.comparison_region)
        warnings = self._snapshot_warnings(region=region, requested_comparison=request.comparison_region, comparison_region=comparison_region)
        if not getattr(getattr(self.fred_adapter, "client", None), "api_key", None):
            warnings.append("FRED_API_KEY is not configured. Cached macro series can still render, but uncached public macro requests will fail until a key is set.")
        data_region = self._data_region(region)
        histories = self._load_histories(self._snapshot_series_ids(data_region, theme), timeframe=timeframe, force_refresh=request.force_refresh, warnings=warnings)
        comparison_histories = self._load_comparison_histories(
            region=data_region,
            comparison_region=comparison_region,
            series_ids=list(histories),
            timeframe=timeframe,
            force_refresh=request.force_refresh,
            warnings=warnings,
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
            signal_rows = self._collect_signal_rows(
                data_region,
                theme_name,
                loaded_histories,
                timeframe=timeframe,
                comparison_region=comparison_region,
                comparison_histories=loaded_comparison_histories,
            )
            if len(signal_rows) < 2:
                continue
            analysis = self._analyze_theme_signals(theme_name, signal_rows)
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
                    comparison_analysis = self._analyze_theme_signals(theme_name, comparison_signal_rows)
                    comparison_score = comparison_analysis["divergence_score"]
                    score_gap = round(analysis["divergence_score"] - comparison_score, 2)
                    score_gap_display = f"{score_gap:+.2f}"
            summary = analysis["summary"]
            if comparison_region is not None and comparison_score is not None:
                summary = f"{summary} Divergence is {score_gap_display} versus {comparison_region} on the same theme."
            rows.append(
                MacroDivergenceRecord(
                    divergence_id=f"{region.lower()}:{theme_name}:divergence",
                    theme=theme_name,
                    region=region,
                    headline=f"{self._title_theme(theme_name)} divergence score {analysis['divergence_score']:.2f}",
                    summary=summary,
                    score=analysis["divergence_score"],
                    label=analysis["divergence_label"],
                    metrics=[row for row, _ in analysis["ordered_rows"]],
                    series_ids=[row.series_id for row, _ in analysis["ordered_rows"] if row.series_id],
                    source_provider="fred",
                    retrieved_at=max((row.retrieved_at for row, _ in signal_rows if row.retrieved_at is not None), default=now_utc()),
                    origin="macro_service.divergences",
                    transformation_note="Divergence scores compare directional changes, level-aware regime bias, and agreement dispersion across curated theme proxies, with optional cross-region comparison overlays.",
                    comparison_region=comparison_region,
                    comparison_score=comparison_score,
                    score_gap=score_gap,
                    score_gap_display=score_gap_display,
                    agreement_score=analysis["agreement_score"],
                    bias_score=analysis["bias_score"],
                    agreement_count=analysis["agreement_count"],
                    disagreement_count=analysis["disagreement_count"],
                    neutral_count=analysis["neutral_count"],
                    lead_metric_label=analysis["lead_metric_label"],
                    conflict_metric_label=analysis["conflict_metric_label"],
                    cluster_direction=analysis["cluster_direction"],
                )
            )
        rows.sort(key=lambda row: (-row.score, row.theme))
        return rows

    def get_events(self, *, region: str = "US", force_refresh: bool = False) -> list[MacroEventRecord]:
        return self.events_adapter.list_events(region=self._normalize_region(region), as_of=now_utc(), force_refresh=force_refresh)

    def _load_histories(self, series_ids: list[str], *, timeframe: str, force_refresh: bool, warnings: list[str] | None = None) -> dict[str, MacroSeriesHistory]:
        rows: dict[str, MacroSeriesHistory] = {}
        for series_id in series_ids:
            try:
                history = self._load_history(series_id, timeframe=timeframe, force_refresh=force_refresh)
            except Exception as exc:
                logger.warning("Macro series load failed: series=%s timeframe=%s error=%s", series_id, timeframe, exc)
                if warnings is not None:
                    message = self._series_load_warning(series_id, exc)
                    if message not in warnings:
                        warnings.append(message)
                continue
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
        warnings: list[str] | None = None,
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
        return self._load_histories(counterpart_ids, timeframe=timeframe, force_refresh=force_refresh, warnings=warnings)

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
        timeframe: str,
    ) -> list[MacroSnapshotCard]:
        data_region = self._data_region(region)
        if data_region == "EU":
            cards = [
                self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Activity, labor, and cyclicals", summary="Industrial output, unemployment, copper, and curve slope frame the EU growth picture.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("eu-industrial-production-yoy"), histories.get("eu-unemployment-rate"), histories.get("global-copper"), histories.get("eu-3m10y-slope")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="HICP versus market signals", summary="Headline HICP sits alongside energy and market rates to show whether inflation pressure is broadening or fading.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("eu-hicp-yoy"), histories.get("global-oil-wti"), histories.get("global-natural-gas"), histories.get("eu-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="policy", title="Policy Context", subtitle="ECB rate and front-end pricing", summary="ECB and money-market rates lead; the long end confirms direction.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("eu-policy-rate"), histories.get("eu-3m-rate"), histories.get("eu-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="curve-shape", title="Curve Shape", subtitle="3M–10Y slope", summary="Tracks the 3M-to-10Y slope as the primary EU curve signal.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("eu-3m10y-slope"), histories.get("eu-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="fx", title="EUR / USD Proxy", subtitle="Currency context", summary="EUR/USD remains the cleanest liquid macro proxy for the EU first pass.", mode_target="cross_asset", target_theme="policy", metric_histories=[histories.get("eu-eurusd")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="commodities", title="Commodity Context", subtitle="Energy and hard-asset overlays", summary="Oil, gas, gold, and copper add the macro-sensitive commodity backdrop without forcing a separate commodities mode.", mode_target="cross_asset", target_theme="geopolitics", metric_histories=[histories.get("global-oil-wti"), histories.get("global-natural-gas"), histories.get("global-gold"), histories.get("global-copper")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
            ]
        else:
            cards = [
                self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Labor, activity, and cyclicals", summary="GDP, payrolls, unemployment, and copper frame the real-economy picture.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("us-real-gdp-yoy"), histories.get("us-payrolls-yoy"), histories.get("us-unemployment-rate"), histories.get("global-copper")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="Realized, implied, and energy-sensitive", summary="CPI, breakevens, and energy inputs show whether inflation pressure is broadening or cooling.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("us-cpi-yoy"), histories.get("us-core-cpi-yoy"), histories.get("us-5y-breakeven"), histories.get("global-oil-wti"), histories.get("global-natural-gas")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="policy", title="Policy Context", subtitle="Front-end pricing and stance", summary="Front-end rates lead the policy read and frame how restrictive conditions remain.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-fed-funds"), histories.get("us-2y-yield"), histories.get("us-10y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="curve-shape", title="Curve Shape", subtitle="Treasury slope direction", summary="Steepening or re-inverting against the prior reference window.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-2s10s-slope"), histories.get("us-10y-yield"), histories.get("us-30y-yield")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="real-yields", title="Real Yields / Breakevens", subtitle="Real rates vs. inflation comp.", summary="Splits a rates move into real tightening and inflation compensation.", mode_target="rates_policy", target_theme="inflation", metric_histories=[histories.get("us-real-10y-yield"), histories.get("us-5y-breakeven"), histories.get("us-10y-breakeven")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
                self._build_metric_card(card_id="commodities", title="Commodity Context", subtitle="Energy and hard-asset overlays", summary="Oil, gas, gold, and copper add the macro-sensitive commodity backdrop without forcing a separate commodities mode.", mode_target="cross_asset", target_theme="geopolitics", metric_histories=[histories.get("global-oil-wti"), histories.get("global-natural-gas"), histories.get("global-gold"), histories.get("global-copper")], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories),
            ]
            for card_id, title, subtitle, summary, series_id, mode_target, theme_name in (
                ("dollar", "Dollar / FX Proxy", "Broad dollar positioning", "Firmer dollar confirms tighter policy and global stress; softer dollar signals the opposite.", "us-dollar-broad", "cross_asset", "policy"),
                ("credit", "Credit / Stress Proxy", "HY spread as stress gauge", "Credit spreads proxy tightening financial conditions and recession risk.", "us-hy-oas", "cross_asset", "recession_risk"),
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
                    source_provider=divergence.source_provider,
                    retrieved_at=divergence.retrieved_at,
                    origin="macro_service.snapshot_cards",
                    transformation_note="Snapshot cards surface the highest-ranked divergence score from the reusable cross-asset engine.",
                )
            )
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
            divergence = divergence_map.get(theme)
            metrics = divergence.metrics if divergence is not None else [self._metric_from_history(histories[series_id], timeframe=timeframe, comparison_region=comparison_region, comparison_histories=comparison_histories) for series_id in REGION_THEME_SERIES.get(data_region, {}).get(theme, []) if series_id in histories]
            if metrics:
                comparison_summary = None
                if divergence is not None and divergence.comparison_region is not None and divergence.comparison_score is not None:
                    comparison_summary = f"{divergence.comparison_region} divergence score {divergence.comparison_score:.2f} ({divergence.score_gap_display} vs {region})."
                rows.append(MacroThemeComparison(theme=theme, headline=f"{self._title_theme(theme)} signals", summary=divergence.summary if divergence is not None else "Theme coverage is available, but disagreement is currently muted.", agreement_label=self._agreement_label(divergence.agreement_score) if divergence is not None else "low", metrics=metrics, source_provider="fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.cross_asset", transformation_note="Cross-asset theme blocks line up curated region-specific series so the user can compare whether markets agree on a macro narrative, with level-aware bias, agreement counts, and optional cross-region overlays.", comparison_region=comparison_region, comparison_summary=comparison_summary, divergence_score=divergence.score if divergence is not None else None, agreement_score=divergence.agreement_score if divergence is not None else None, bias_score=divergence.bias_score if divergence is not None else None, agreement_count=divergence.agreement_count if divergence is not None else 0, disagreement_count=divergence.disagreement_count if divergence is not None else 0, neutral_count=divergence.neutral_count if divergence is not None else 0, lead_metric_label=divergence.lead_metric_label if divergence is not None else None, conflict_metric_label=divergence.conflict_metric_label if divergence is not None else None, cluster_direction=divergence.cluster_direction if divergence is not None else None))
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
            signal_rows.append((metric, self._signal_score(region, theme_name, metric)))
        return signal_rows

    def _signal_score(self, region: str, theme_name: str, metric: MacroMetricRecord) -> float:
        series_id = metric.series_id or metric.metric_id
        factor = REGION_THEME_FACTORS.get(region, {}).get(theme_name, {}).get(series_id, 1.0)
        scale = SIGNAL_SCALES.get(series_id, 1.0)
        delta_component = ((metric.delta_value or 0.0) / scale) * factor
        level_component = 0.0
        if metric.value is not None:
            level_component = self._level_signal(series_id, metric.value) * factor * 0.35
        return max(min(delta_component + level_component, 4.0), -4.0)

    def _level_signal(self, series_id: str, value: float) -> float:
        config = LEVEL_SIGNAL_CONFIG.get(series_id)
        if config is None:
            return 0.0
        anchor = float(config["anchor"])
        scale = max(float(config["scale"]), 0.0001)
        return max(min((value - anchor) / scale, 1.5), -1.5)

    def _analyze_theme_signals(self, theme_name: str, signal_rows: list[tuple[MacroMetricRecord, float]]) -> dict[str, Any]:
        ordered_rows = sorted(signal_rows, key=lambda item: abs(item[1]), reverse=True)
        scores = [score for _, score in ordered_rows]
        bias_score = round(fmean(scores), 2) if scores else 0.0
        dispersion = pstdev(scores) if len(scores) > 1 else 0.0
        neutral_threshold = 0.35
        if bias_score > neutral_threshold:
            agreement_count = sum(1 for score in scores if score > neutral_threshold)
            disagreement_count = sum(1 for score in scores if score < -neutral_threshold)
        elif bias_score < -neutral_threshold:
            agreement_count = sum(1 for score in scores if score < -neutral_threshold)
            disagreement_count = sum(1 for score in scores if score > neutral_threshold)
        else:
            agreement_count = sum(1 for score in scores if abs(score) <= neutral_threshold)
            disagreement_count = sum(1 for score in scores if abs(score) > neutral_threshold)
        neutral_count = max(len(scores) - agreement_count - disagreement_count, 0)
        lead_metric = ordered_rows[0][0]
        conflict_candidates = [item for item in ordered_rows if abs(item[1]) > neutral_threshold and ((bias_score > neutral_threshold and item[1] < -neutral_threshold) or (bias_score < -neutral_threshold and item[1] > neutral_threshold))]
        conflict_metric = conflict_candidates[0][0] if conflict_candidates else (ordered_rows[-1][0] if ordered_rows else None)
        agreement_score = round(max(0.0, min(4.0, ((agreement_count + (0.5 * neutral_count)) / max(len(scores), 1)) * 3.0 - (min(dispersion, 2.5) * 0.4) + (min(abs(bias_score), 1.5) * 0.5))), 2)
        divergence_score = round((max(scores) - min(scores)) + (dispersion * 0.6) + ((disagreement_count / max(len(scores), 1)) * 0.75), 2)
        cluster_direction = self._cluster_direction(theme_name, bias_score)
        if disagreement_count == 0 and agreement_count >= max(2, len(scores) - 1):
            summary = f"{agreement_count} of {len(scores)} signals are aligned in a {cluster_direction} cluster led by {lead_metric.label}."
        elif disagreement_count > 0 and conflict_metric is not None:
            summary = f"{agreement_count} of {len(scores)} signals are aligned in a {cluster_direction} backdrop, but {conflict_metric.label} is leaning the other way while {lead_metric.label} leads the move."
        else:
            summary = f"{lead_metric.label} is leading a {cluster_direction} read, but the theme still lacks a fully consistent cross-asset cluster."
        return {
            "ordered_rows": ordered_rows,
            "bias_score": bias_score,
            "agreement_score": agreement_score,
            "agreement_count": agreement_count,
            "disagreement_count": disagreement_count,
            "neutral_count": neutral_count,
            "lead_metric_label": lead_metric.label,
            "conflict_metric_label": conflict_metric.label if conflict_metric is not None else None,
            "cluster_direction": cluster_direction,
            "divergence_score": divergence_score,
            "divergence_label": "high" if divergence_score >= 3.0 else "moderate" if divergence_score >= 1.75 else "low",
            "summary": summary,
        }

    @staticmethod
    def _agreement_label(score: float | None) -> str:
        if score is None:
            return "low"
        if score >= 2.6:
            return "high"
        if score >= 1.5:
            return "moderate"
        return "low"

    @staticmethod
    def _cluster_direction(theme_name: str, bias_score: float) -> str:
        if abs(bias_score) <= 0.35:
            return "mixed"
        direction = bias_score > 0
        if theme_name == "growth":
            return "growth-firming" if direction else "growth-softening"
        if theme_name == "inflation":
            return "inflation-firming" if direction else "inflation-cooling"
        if theme_name == "policy":
            return "policy-tightening" if direction else "policy-easing"
        if theme_name == "recession_risk":
            return "stress-building" if direction else "stress-easing"
        if theme_name == "geopolitics":
            return "risk-rising" if direction else "risk-fading"
        if theme_name == "risk_appetite":
            return "risk-on" if direction else "risk-off"
        return "mixed"

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

    @staticmethod
    def _series_load_warning(series_id: str, exc: Exception) -> str:
        meta = SERIES_REGISTRY.get(series_id, {})
        title = str(meta.get("title") or series_id)
        provider = str(meta.get("provider_series_id") or series_id)
        text = str(exc)
        if "HTTP Error 400" in text:
            return f"{title} could not be loaded from FRED right now. If this environment does not have FRED_API_KEY configured, uncached macro requests will fail."
        return f"{title} could not be loaded ({provider}). Gamma skipped that series for now."


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
