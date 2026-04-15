from __future__ import annotations

import math

import pandas as pd

from src.analytics.risk_metrics import max_drawdown, realized_vol
from src.models.research_overview import ResearchOverviewMetrics


def returns_from_price_series(series: pd.Series | None, lookback_days: int) -> pd.Series:
    if series is None or getattr(series, "empty", True):
        return pd.Series(dtype=float)
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if clean.empty:
        return pd.Series(dtype=float)
    window = max(int(lookback_days), 1) + 1
    clean = clean.tail(window)
    return clean.pct_change().dropna().astype(float)


def latest_price(series: pd.Series | None) -> float | None:
    if series is None or getattr(series, "empty", True):
        return None
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if clean.empty:
        return None
    return float(clean.iloc[-1])


def total_return_from_returns(returns: pd.Series | None) -> float | None:
    if returns is None or getattr(returns, "empty", True):
        return None
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return None
    return float((1.0 + clean).prod() - 1.0)


def beta_to_benchmark(returns: pd.Series, benchmark_returns: pd.Series | None) -> float | None:
    if returns.empty or benchmark_returns is None or benchmark_returns.empty:
        return None
    aligned = returns.to_frame("node").join(benchmark_returns.to_frame("benchmark"), how="inner").dropna()
    if len(aligned) < 2:
        return None
    benchmark_var = float(aligned["benchmark"].var())
    if not math.isfinite(benchmark_var) or benchmark_var <= 0:
        return None
    return float(aligned["node"].cov(aligned["benchmark"]) / benchmark_var)


def compute_overview_metrics(
    returns: pd.Series,
    *,
    benchmark_returns: pd.Series | None = None,
    benchmark_total_return: float | None = None,
    latest: float | None = None,
) -> ResearchOverviewMetrics:
    clean = pd.to_numeric(returns, errors="coerce").dropna().astype(float)
    if clean.empty:
        return ResearchOverviewMetrics(latest_price=latest)

    total_return = total_return_from_returns(clean)
    _daily_vol, annual_vol = realized_vol(clean)
    max_dd = max_drawdown(clean)
    beta = beta_to_benchmark(clean, benchmark_returns)
    relative_return = (
        float(total_return - benchmark_total_return)
        if total_return is not None and benchmark_total_return is not None
        else None
    )
    return ResearchOverviewMetrics(
        total_return=total_return,
        annual_volatility=annual_vol,
        beta=beta,
        max_drawdown=max_dd,
        relative_return=relative_return,
        latest_price=latest,
        observation_count=int(len(clean)),
    )


def weighted_group_returns(
    returns_by_symbol: dict[str, pd.Series],
    weights_by_symbol: dict[str, float],
) -> pd.Series:
    frames: list[pd.Series] = []
    for symbol, returns in returns_by_symbol.items():
        if returns.empty:
            continue
        series = returns.copy()
        series.name = symbol
        frames.append(series)
    if not frames:
        return pd.Series(dtype=float)

    returns_df = pd.concat(frames, axis=1, join="inner").dropna(how="any")
    if returns_df.empty:
        return pd.Series(dtype=float)
    weights = pd.Series({symbol: float(weights_by_symbol.get(symbol, 0.0)) for symbol in returns_df.columns})
    total_weight = float(weights.sum())
    if total_weight <= 0:
        return pd.Series(dtype=float)
    weights = weights / total_weight
    return returns_df.mul(weights, axis=1).sum(axis=1).astype(float)

