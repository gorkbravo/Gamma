from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import NormalDist
from typing import Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MonteCarloVarResult:
    model: str
    alpha: float
    horizon_days: int
    num_simulations: int
    random_seed: int | None
    var_return: float | None
    cvar_return: float | None
    terminal_returns: pd.Series
    fan_percentiles: pd.DataFrame
    sample_paths: pd.DataFrame


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


def monte_carlo_var_cvar(
    asset_returns: pd.DataFrame,
    weights: pd.Series | np.ndarray,
    alpha: float,
    horizon_days: int,
    model_name: str,
    num_simulations: int,
    random_seed: int | None = None,
    sample_size: int = 20,
    fan_percentiles: Sequence[int] = (5, 25, 50, 75, 95),
) -> MonteCarloVarResult | None:
    if asset_returns is None or asset_returns.empty:
        return None
    if not 0.0 < float(alpha) < 1.0:
        return None
    if int(horizon_days) <= 0 or int(num_simulations) <= 0:
        return None

    cleaned_returns = asset_returns.dropna(how="any")
    if cleaned_returns.empty:
        return None

    weight_values = _coerce_weights(weights, cleaned_returns.columns)
    if weight_values is None:
        return None
    if not np.isfinite(weight_values).all():
        return None

    returns_values = cleaned_returns.to_numpy(dtype=float, copy=True)
    if returns_values.ndim != 2 or returns_values.shape[0] == 0 or returns_values.shape[1] != weight_values.size:
        return None
    if not np.isfinite(returns_values).all():
        return None

    model = _normalize_model_name(model_name)
    if model is None:
        return None

    rng = np.random.default_rng(random_seed)
    portfolio_daily_returns = _simulate_portfolio_returns(
        returns_values=returns_values,
        weights=weight_values,
        horizon_days=int(horizon_days),
        num_simulations=int(num_simulations),
        model=model,
        rng=rng,
    )
    if portfolio_daily_returns is None:
        return None

    cumulative_paths = np.cumprod(1.0 + portfolio_daily_returns, axis=1)
    cumulative_paths = np.concatenate(
        [np.ones((portfolio_daily_returns.shape[0], 1), dtype=float), cumulative_paths],
        axis=1,
    )
    terminal_returns = cumulative_paths[:, -1] - 1.0

    quantile = float(np.quantile(terminal_returns, 1.0 - float(alpha)))
    tail = terminal_returns[terminal_returns <= quantile]
    cvar_return = -float(tail.mean()) if tail.size else None

    path_index = pd.Index(range(int(horizon_days) + 1), name="day")
    fan_df = pd.DataFrame(
        {
            f"p{int(percentile):02d}": np.percentile(cumulative_paths, percentile, axis=0)
            for percentile in fan_percentiles
        },
        index=path_index,
    )
    sample_count = max(0, min(int(sample_size), cumulative_paths.shape[0]))
    sample_df = pd.DataFrame(
        cumulative_paths[:sample_count].T,
        index=path_index,
        columns=[f"path_{idx + 1}" for idx in range(sample_count)],
    )

    return MonteCarloVarResult(
        model=model,
        alpha=float(alpha),
        horizon_days=int(horizon_days),
        num_simulations=int(num_simulations),
        random_seed=random_seed,
        var_return=-quantile,
        cvar_return=cvar_return,
        terminal_returns=pd.Series(terminal_returns, name="terminal_return"),
        fan_percentiles=fan_df,
        sample_paths=sample_df,
    )


def _coerce_weights(weights: pd.Series | np.ndarray, columns: pd.Index) -> np.ndarray | None:
    if weights is None:
        return None
    if isinstance(weights, pd.Series):
        aligned = weights.reindex(columns)
        if aligned.isna().any():
            return None
        values = aligned.to_numpy(dtype=float, copy=True)
    else:
        values = np.asarray(weights, dtype=float).reshape(-1)
    if values.size != len(columns):
        return None
    return values


def _normalize_model_name(model_name: str) -> str | None:
    normalized = str(model_name or "").strip().lower()
    if normalized == "gaussian":
        return "Gaussian"
    if normalized == "bootstrap":
        return "Bootstrap"
    return None


def _simulate_portfolio_returns(
    returns_values: np.ndarray,
    weights: np.ndarray,
    horizon_days: int,
    num_simulations: int,
    model: str,
    rng: np.random.Generator,
) -> np.ndarray | None:
    if model == "Gaussian":
        covariance = np.cov(returns_values, rowvar=False, ddof=1)
        covariance = np.atleast_2d(np.asarray(covariance, dtype=float))
        if covariance.shape != (weights.size, weights.size) or not np.isfinite(covariance).all():
            return None
        safe_covariance = _nearest_positive_semidefinite(covariance)
        draws = rng.multivariate_normal(
            mean=np.zeros(weights.size, dtype=float),
            cov=safe_covariance,
            size=(num_simulations, horizon_days),
            check_valid="ignore",
        )
    elif model == "Bootstrap":
        sampled_idx = rng.integers(0, returns_values.shape[0], size=(num_simulations, horizon_days))
        draws = returns_values[sampled_idx]
    else:
        return None

    return np.einsum("shn,n->sh", draws, weights)


def _nearest_positive_semidefinite(covariance: np.ndarray) -> np.ndarray:
    sym_cov = (covariance + covariance.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(sym_cov)
    clipped = np.clip(eigenvalues, a_min=0.0, a_max=None)
    safe_cov = eigenvectors @ np.diag(clipped) @ eigenvectors.T
    safe_cov = (safe_cov + safe_cov.T) / 2.0
    return safe_cov
