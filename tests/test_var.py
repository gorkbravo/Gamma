import numpy as np
import pandas as pd

from src.analytics.var import historical_var_cvar, parametric_var


def test_historical_var_cvar_simple():
    returns = pd.Series([-0.05, -0.02, 0.01, 0.03, -0.01])
    var, cvar = historical_var_cvar(returns, 0.95)
    q = returns.quantile(0.05)
    tail = returns[returns <= q]
    assert abs(var - (-q)) < 1e-12
    assert abs(cvar - (-tail.mean())) < 1e-12


def test_historical_var_cvar_tail_mean():
    returns = pd.Series([-0.10, -0.04, -0.02, 0.01, 0.02])
    var, cvar = historical_var_cvar(returns, 0.8)
    q = returns.quantile(0.2)
    tail = returns[returns <= q]
    assert round(var, 6) == round(-q, 6)
    assert round(cvar, 6) == round(-tail.mean(), 6)


def test_parametric_var_matches_sigma():
    weights = np.array([0.6, 0.4])
    cov = np.array([[0.04, 0.006], [0.006, 0.01]])
    var = parametric_var(weights, cov, 0.95)
    # Expected z * sigma
    sigma = np.sqrt(weights.T @ cov @ weights)
    expected = 1.6448536269514722 * sigma
    assert abs(var - expected) < 1e-8


def test_parametric_var_shape_mismatch_returns_none():
    weights = np.array([1.0])
    cov = np.array([[0.04, 0.0], [0.0, 0.01]])
    assert parametric_var(weights, cov, 0.95) is None
