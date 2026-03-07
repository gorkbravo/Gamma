from __future__ import annotations

from math import sqrt
from statistics import NormalDist
from typing import Tuple

import numpy as np
import pandas as pd


def historical_var_cvar(portfolio_returns: pd.Series, alpha: float) -> Tuple[float | None, float | None]:
    if portfolio_returns.empty:
        return None, None
    quantile = portfolio_returns.quantile(1 - alpha)
    var = -quantile
    tail = portfolio_returns[portfolio_returns <= quantile]
    if tail.empty:
        cvar = None
    else:
        cvar = -tail.mean()
    return var, cvar


def parametric_var(weights: np.ndarray, cov: np.ndarray, alpha: float) -> float | None:
    if weights is None or cov is None:
        return None
    weights = np.asarray(weights, dtype=float).reshape(-1)
    cov = np.asarray(cov, dtype=float)
    if weights.size == 0 or cov.ndim != 2 or cov.shape[0] != cov.shape[1] or cov.shape[0] != weights.size:
        return None
    if not np.isfinite(weights).all() or not np.isfinite(cov).all():
        return None
    variance = float(weights.T @ cov @ weights)
    if not np.isfinite(variance) or variance <= 0:
        return None
    sigma = sqrt(variance)
    z = NormalDist().inv_cdf(alpha)
    return z * sigma
