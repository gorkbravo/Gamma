from __future__ import annotations

import math
from typing import Tuple

import numpy as np
import pandas as pd


def portfolio_returns(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    if returns.empty or weights.empty:
        return pd.Series(dtype=float)
    aligned = returns[weights.index]
    pr = aligned.mul(weights, axis=1).sum(axis=1)
    return pr


def compute_weights(values: pd.Series) -> pd.Series:
    total = values.sum()
    if total == 0:
        return pd.Series(dtype=float)
    return values / total


def realized_vol(returns: pd.Series) -> Tuple[float | None, float | None]:
    """Sample volatility, or absence when it cannot be computed.

    A single observation has no sample standard deviation, and pandas answers
    NaN. Returning that NaN as a number made an uncomputable metric look like a
    computed one, and it is not JSON-encodable, so it took the whole response
    down with it rather than degrading one value.
    """

    if len(returns) < 2:
        return None, None
    daily = float(returns.std())
    if not math.isfinite(daily):
        return None, None
    return daily, daily * (252 ** 0.5)


def max_drawdown(returns: pd.Series) -> float | None:
    if returns.empty:
        return None
    cumulative = (1 + returns).cumprod()
    peak = cumulative.cummax()
    drawdown = (cumulative / peak) - 1
    worst = float(drawdown.min())
    return worst if math.isfinite(worst) else None


def risk_contributions(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
    if weights is None or cov is None:
        return np.array([])
    weights = np.asarray(weights, dtype=float).reshape(-1)
    cov = np.asarray(cov, dtype=float)
    if weights.size == 0 or cov.ndim != 2 or cov.shape[0] != cov.shape[1] or cov.shape[0] != weights.size:
        return np.array([])
    if not np.isfinite(weights).all() or not np.isfinite(cov).all():
        return np.array([])
    portfolio_var = float(weights.T @ cov @ weights)
    if not np.isfinite(portfolio_var) or portfolio_var <= 0:
        return np.zeros_like(weights)
    marginal = cov @ weights
    contribution = weights * marginal / portfolio_var
    return contribution
