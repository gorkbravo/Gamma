from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from src.analytics.risk_metrics import max_drawdown, realized_vol


TRADING_DAYS_PER_YEAR = 252.0
MIN_RETURN_OBSERVATIONS = 5
OUTLIER_ABS_RETURN_THRESHOLD = 0.5


@dataclass(frozen=True)
class ReturnFrequency:
    label: str
    periods_per_year: float
    median_gap_days: float | None = None


@dataclass(frozen=True)
class ReturnStreamMetrics:
    total_return: float | None = None
    annual_return: float | None = None
    annual_volatility: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown: float | None = None
    max_drawdown_duration: int | None = None
    observation_count: int = 0
    frequency: str = "unknown"
    periods_per_year: float = TRADING_DAYS_PER_YEAR
    start_date: datetime | None = None
    end_date: datetime | None = None
    benchmark_beta: float | None = None
    benchmark_correlation: float | None = None
    upside_capture: float | None = None
    downside_capture: float | None = None


@dataclass(frozen=True)
class RollingReturnPoint:
    timestamp: datetime
    rolling_return: float | None = None
    rolling_volatility: float | None = None
    rolling_beta: float | None = None
    rolling_correlation: float | None = None


@dataclass(frozen=True)
class PeriodReturn:
    period: str
    value: float | None


@dataclass(frozen=True)
class ReturnStreamAnalysis:
    returns: pd.Series
    equity_curve: pd.Series
    drawdowns: pd.Series
    metrics: ReturnStreamMetrics
    rolling_points: list[RollingReturnPoint] = field(default_factory=list)
    monthly_returns: list[PeriodReturn] = field(default_factory=list)
    annual_returns: list[PeriodReturn] = field(default_factory=list)


@dataclass(frozen=True)
class ComparisonLegAnalysis:
    label: str
    object_type: str
    returns: pd.Series
    normalized_nav: pd.Series
    drawdowns: pd.Series
    metrics: ReturnStreamMetrics


@dataclass(frozen=True)
class ReturnStreamComparison:
    left: ComparisonLegAnalysis
    right: ComparisonLegAnalysis
    aligned_observation_count: int
    relative_return: float | None
    volatility_difference: float | None
    max_drawdown_difference: float | None
    correlation: float | None
    beta: float | None
    relative_nav: pd.Series
    relative_drawdown: pd.Series
    warnings: list[str]


def clean_return_series(series: pd.Series | None) -> pd.Series:
    if series is None or getattr(series, "empty", True):
        return pd.Series(dtype=float)
    clean = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if clean.empty:
        return pd.Series(dtype=float)
    clean.index = pd.to_datetime(clean.index, errors="coerce")
    clean = clean[~clean.index.isna()]
    if clean.empty:
        return pd.Series(dtype=float)
    clean = clean.sort_index()
    clean = clean[~clean.index.duplicated(keep="last")]
    return clean.astype(float)


def equity_curve_from_returns(returns: pd.Series | None) -> pd.Series:
    clean = clean_return_series(returns)
    if clean.empty:
        return pd.Series(dtype=float)
    return (1.0 + clean).cumprod().astype(float)


def drawdown_series_from_returns(returns: pd.Series | None) -> pd.Series:
    equity = equity_curve_from_returns(returns)
    if equity.empty:
        return pd.Series(dtype=float)
    peak = equity.cummax()
    return (equity / peak - 1.0).astype(float)


def infer_return_frequency(index: pd.Index) -> ReturnFrequency:
    dates = pd.to_datetime(index, errors="coerce").dropna().sort_values()
    if len(dates) < 2:
        return ReturnFrequency(label="unknown", periods_per_year=TRADING_DAYS_PER_YEAR)
    gaps = pd.Series(dates).diff().dropna().dt.total_seconds() / 86_400.0
    median_gap = float(gaps.median()) if not gaps.empty else None
    if median_gap is None or not math.isfinite(median_gap) or median_gap <= 0:
        return ReturnFrequency(label="unknown", periods_per_year=TRADING_DAYS_PER_YEAR)
    if median_gap <= 2.5:
        return ReturnFrequency(label="daily", periods_per_year=252.0, median_gap_days=median_gap)
    if median_gap <= 10:
        return ReturnFrequency(label="weekly", periods_per_year=52.0, median_gap_days=median_gap)
    if median_gap <= 45:
        return ReturnFrequency(label="monthly", periods_per_year=12.0, median_gap_days=median_gap)
    if median_gap <= 120:
        return ReturnFrequency(label="quarterly", periods_per_year=4.0, median_gap_days=median_gap)
    return ReturnFrequency(label="annual", periods_per_year=1.0, median_gap_days=median_gap)


def annualized_return(returns: pd.Series, periods_per_year: float) -> float | None:
    clean = clean_return_series(returns)
    if clean.empty:
        return None
    cumulative = float((1.0 + clean).prod())
    if cumulative <= 0:
        return None
    return float(cumulative ** (float(periods_per_year) / len(clean)) - 1.0)


def max_drawdown_duration(returns: pd.Series | None) -> int | None:
    drawdowns = drawdown_series_from_returns(returns)
    if drawdowns.empty:
        return None
    longest = 0
    current = 0
    for value in drawdowns:
        if float(value) < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def beta_corr(returns: pd.Series, benchmark_returns: pd.Series | None) -> tuple[float | None, float | None]:
    clean = clean_return_series(returns)
    benchmark = clean_return_series(benchmark_returns)
    if clean.empty or benchmark.empty:
        return None, None
    aligned = clean.to_frame("strategy").join(benchmark.to_frame("benchmark"), how="inner").dropna()
    if len(aligned) < 2:
        return None, None
    corr = float(aligned["strategy"].corr(aligned["benchmark"]))
    benchmark_var = float(aligned["benchmark"].var())
    if not math.isfinite(benchmark_var) or benchmark_var <= 0:
        return None, corr if math.isfinite(corr) else None
    beta = float(aligned["strategy"].cov(aligned["benchmark"]) / benchmark_var)
    return beta if math.isfinite(beta) else None, corr if math.isfinite(corr) else None


def capture_ratios(returns: pd.Series, benchmark_returns: pd.Series | None) -> tuple[float | None, float | None]:
    clean = clean_return_series(returns)
    benchmark = clean_return_series(benchmark_returns)
    if clean.empty or benchmark.empty:
        return None, None
    aligned = clean.to_frame("strategy").join(benchmark.to_frame("benchmark"), how="inner").dropna()
    if aligned.empty:
        return None, None

    upside = aligned[aligned["benchmark"] > 0]
    downside = aligned[aligned["benchmark"] < 0]
    upside_capture = None
    downside_capture = None
    if not upside.empty and float(upside["benchmark"].mean()) != 0:
        upside_capture = float(upside["strategy"].mean() / upside["benchmark"].mean())
    if not downside.empty and float(downside["benchmark"].mean()) != 0:
        downside_capture = float(downside["strategy"].mean() / downside["benchmark"].mean())
    return upside_capture, downside_capture


def compute_return_stream_metrics(
    returns: pd.Series,
    *,
    benchmark_returns: pd.Series | None = None,
    periods_per_year: float | None = None,
    frequency_label: str | None = None,
) -> ReturnStreamMetrics:
    clean = clean_return_series(returns)
    if clean.empty:
        return ReturnStreamMetrics()

    inferred = infer_return_frequency(clean.index)
    annual_factor = float(periods_per_year or inferred.periods_per_year or TRADING_DAYS_PER_YEAR)
    total_return = float((1.0 + clean).prod() - 1.0)
    annual_return = annualized_return(clean, annual_factor)
    daily_vol, _legacy_annual_vol = realized_vol(clean)
    annual_vol = float(clean.std() * math.sqrt(annual_factor)) if len(clean) > 1 else None
    sharpe = (
        float((clean.mean() * annual_factor) / annual_vol)
        if annual_vol is not None and annual_vol > 0
        else None
    )
    downside = clean[clean < 0]
    downside_deviation = float(downside.std() * math.sqrt(annual_factor)) if len(downside) > 1 else None
    sortino = (
        float((clean.mean() * annual_factor) / downside_deviation)
        if downside_deviation is not None and downside_deviation > 0
        else None
    )
    beta, corr = beta_corr(clean, benchmark_returns)
    upside_capture, downside_capture = capture_ratios(clean, benchmark_returns)

    return ReturnStreamMetrics(
        total_return=total_return,
        annual_return=annual_return,
        annual_volatility=annual_vol if annual_vol is not None else _legacy_annual_vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_drawdown(clean),
        max_drawdown_duration=max_drawdown_duration(clean),
        observation_count=int(len(clean)),
        frequency=frequency_label or inferred.label,
        periods_per_year=annual_factor,
        start_date=pd.Timestamp(clean.index[0]).to_pydatetime(),
        end_date=pd.Timestamp(clean.index[-1]).to_pydatetime(),
        benchmark_beta=beta,
        benchmark_correlation=corr,
        upside_capture=upside_capture,
        downside_capture=downside_capture,
    )


def rolling_return_points(
    returns: pd.Series,
    *,
    benchmark_returns: pd.Series | None = None,
    window: int | None = None,
    periods_per_year: float | None = None,
) -> list[RollingReturnPoint]:
    clean = clean_return_series(returns)
    if clean.empty:
        return []
    frequency = infer_return_frequency(clean.index)
    annual_factor = float(periods_per_year or frequency.periods_per_year)
    rolling_window = int(window or min(max(round(annual_factor / 4), 5), 63))
    if len(clean) < rolling_window:
        return []

    benchmark = clean_return_series(benchmark_returns)
    aligned = clean.to_frame("strategy")
    if not benchmark.empty:
        aligned = aligned.join(benchmark.to_frame("benchmark"), how="inner").dropna()
    points: list[RollingReturnPoint] = []
    for idx in range(rolling_window - 1, len(aligned)):
        sliced = aligned.iloc[idx + 1 - rolling_window : idx + 1]
        strategy = sliced["strategy"]
        rolling_return = float((1.0 + strategy).prod() - 1.0)
        rolling_vol = float(strategy.std() * math.sqrt(annual_factor)) if len(strategy) > 1 else None
        rolling_beta = None
        rolling_corr = None
        if "benchmark" in sliced.columns and len(sliced) > 1:
            benchmark_var = float(sliced["benchmark"].var())
            corr = float(strategy.corr(sliced["benchmark"]))
            rolling_corr = corr if math.isfinite(corr) else None
            if benchmark_var > 0 and math.isfinite(benchmark_var):
                beta = float(strategy.cov(sliced["benchmark"]) / benchmark_var)
                rolling_beta = beta if math.isfinite(beta) else None
        points.append(
            RollingReturnPoint(
                timestamp=pd.Timestamp(aligned.index[idx]).to_pydatetime(),
                rolling_return=rolling_return,
                rolling_volatility=rolling_vol,
                rolling_beta=rolling_beta,
                rolling_correlation=rolling_corr,
            )
        )
    return points


def period_returns(returns: pd.Series, frequency: str) -> list[PeriodReturn]:
    clean = clean_return_series(returns)
    if clean.empty:
        return []
    period_alias = "M" if frequency == "monthly" else "Y"
    grouped = clean.groupby(clean.index.to_period(period_alias))
    return [
        PeriodReturn(period=str(period), value=float((1.0 + values).prod() - 1.0))
        for period, values in grouped
        if not values.empty
    ]


def analyze_return_stream(
    returns: pd.Series,
    *,
    benchmark_returns: pd.Series | None = None,
    min_observations: int = MIN_RETURN_OBSERVATIONS,
) -> ReturnStreamAnalysis:
    clean = clean_return_series(returns)
    if len(clean) < min_observations:
        raise ValueError(f"At least {min_observations} return observations are required.")
    frequency = infer_return_frequency(clean.index)
    benchmark = clean_return_series(benchmark_returns)
    if not benchmark.empty:
        aligned = clean.to_frame("strategy").join(benchmark.to_frame("benchmark"), how="inner").dropna()
        clean = aligned["strategy"]
        benchmark = aligned["benchmark"]
    metrics = compute_return_stream_metrics(
        clean,
        benchmark_returns=benchmark if not benchmark.empty else None,
        periods_per_year=frequency.periods_per_year,
        frequency_label=frequency.label,
    )
    return ReturnStreamAnalysis(
        returns=clean,
        equity_curve=equity_curve_from_returns(clean),
        drawdowns=drawdown_series_from_returns(clean),
        metrics=metrics,
        rolling_points=rolling_return_points(
            clean,
            benchmark_returns=benchmark if not benchmark.empty else None,
            periods_per_year=frequency.periods_per_year,
        ),
        monthly_returns=period_returns(clean, "monthly"),
        annual_returns=period_returns(clean, "annual"),
    )


def compare_return_streams(
    left_label: str,
    left_type: str,
    left_returns: pd.Series,
    right_label: str,
    right_type: str,
    right_returns: pd.Series,
) -> ReturnStreamComparison:
    warnings: list[str] = []
    left_clean = clean_return_series(left_returns)
    right_clean = clean_return_series(right_returns)
    aligned = left_clean.to_frame("left").join(right_clean.to_frame("right"), how="inner").dropna()
    if len(aligned) < 2:
        raise ValueError("At least two aligned return observations are required for comparison.")
    if len(aligned) < len(left_clean) or len(aligned) < len(right_clean):
        warnings.append(
            f"Comparison uses {len(aligned)} aligned observations after intersecting both return calendars."
        )

    left_series = aligned["left"]
    right_series = aligned["right"]
    frequency = infer_return_frequency(aligned.index)
    left_metrics = compute_return_stream_metrics(
        left_series,
        benchmark_returns=right_series,
        periods_per_year=frequency.periods_per_year,
        frequency_label=frequency.label,
    )
    right_metrics = compute_return_stream_metrics(
        right_series,
        benchmark_returns=left_series,
        periods_per_year=frequency.periods_per_year,
        frequency_label=frequency.label,
    )
    left_nav = equity_curve_from_returns(left_series)
    right_nav = equity_curve_from_returns(right_series)
    relative_nav = (left_nav / right_nav - 1.0).dropna().astype(float)
    left_drawdowns = drawdown_series_from_returns(left_series)
    right_drawdowns = drawdown_series_from_returns(right_series)
    relative_drawdown = (left_drawdowns - right_drawdowns).dropna().astype(float)
    beta, corr = beta_corr(left_series, right_series)

    return ReturnStreamComparison(
        left=ComparisonLegAnalysis(
            label=left_label,
            object_type=left_type,
            returns=left_series,
            normalized_nav=left_nav,
            drawdowns=left_drawdowns,
            metrics=left_metrics,
        ),
        right=ComparisonLegAnalysis(
            label=right_label,
            object_type=right_type,
            returns=right_series,
            normalized_nav=right_nav,
            drawdowns=right_drawdowns,
            metrics=right_metrics,
        ),
        aligned_observation_count=int(len(aligned)),
        relative_return=(
            left_metrics.total_return - right_metrics.total_return
            if left_metrics.total_return is not None and right_metrics.total_return is not None
            else None
        ),
        volatility_difference=(
            left_metrics.annual_volatility - right_metrics.annual_volatility
            if left_metrics.annual_volatility is not None and right_metrics.annual_volatility is not None
            else None
        ),
        max_drawdown_difference=(
            left_metrics.max_drawdown - right_metrics.max_drawdown
            if left_metrics.max_drawdown is not None and right_metrics.max_drawdown is not None
            else None
        ),
        correlation=corr,
        beta=beta,
        relative_nav=relative_nav,
        relative_drawdown=relative_drawdown,
        warnings=warnings,
    )
