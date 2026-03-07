import numpy as np
import pandas as pd

from src.analytics.var import historical_var_cvar, monte_carlo_var_cvar, parametric_var


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


def test_gaussian_monte_carlo_is_deterministic_with_seed():
    returns = pd.DataFrame(
        {
            "A": [-0.02, 0.01, 0.015, -0.005, 0.008, 0.011],
            "B": [-0.01, 0.005, 0.012, -0.003, 0.004, 0.006],
        }
    )
    weights = pd.Series({"A": 0.6, "B": 0.4})

    first = monte_carlo_var_cvar(
        asset_returns=returns,
        weights=weights,
        alpha=0.95,
        horizon_days=5,
        model_name="Gaussian",
        num_simulations=500,
        random_seed=17,
    )
    second = monte_carlo_var_cvar(
        asset_returns=returns,
        weights=weights,
        alpha=0.95,
        horizon_days=5,
        model_name="Gaussian",
        num_simulations=500,
        random_seed=17,
    )

    assert first is not None
    assert second is not None
    assert first.model == "Gaussian"
    assert first.var_return == second.var_return
    assert first.cvar_return == second.cvar_return
    pd.testing.assert_frame_equal(first.fan_percentiles, second.fan_percentiles)
    pd.testing.assert_frame_equal(first.sample_paths, second.sample_paths)


def test_bootstrap_monte_carlo_is_deterministic_with_seed():
    returns = pd.DataFrame(
        {
            "A": [-0.03, 0.02, 0.01, -0.015, 0.012, 0.004],
            "B": [-0.015, 0.01, 0.008, -0.01, 0.005, 0.002],
        }
    )
    weights = pd.Series({"A": 0.55, "B": 0.45})

    first = monte_carlo_var_cvar(
        asset_returns=returns,
        weights=weights,
        alpha=0.95,
        horizon_days=4,
        model_name="Bootstrap",
        num_simulations=400,
        random_seed=9,
    )
    second = monte_carlo_var_cvar(
        asset_returns=returns,
        weights=weights,
        alpha=0.95,
        horizon_days=4,
        model_name="Bootstrap",
        num_simulations=400,
        random_seed=9,
    )

    assert first is not None
    assert second is not None
    assert first.model == "Bootstrap"
    assert first.var_return == second.var_return
    assert first.cvar_return == second.cvar_return
    pd.testing.assert_frame_equal(first.fan_percentiles, second.fan_percentiles)
    pd.testing.assert_frame_equal(first.sample_paths, second.sample_paths)


def test_monte_carlo_horizon_outputs_expected_shapes():
    returns = pd.DataFrame(
        {
            "A": [-0.01, 0.01, 0.02, -0.005, 0.004, 0.003],
            "B": [-0.005, 0.006, 0.01, -0.002, 0.003, 0.001],
        }
    )
    weights = pd.Series({"A": 0.5, "B": 0.5})

    result = monte_carlo_var_cvar(
        asset_returns=returns,
        weights=weights,
        alpha=0.95,
        horizon_days=7,
        model_name="Gaussian",
        num_simulations=32,
        random_seed=123,
        sample_size=8,
    )

    assert result is not None
    assert result.fan_percentiles.shape == (8, 5)
    assert list(result.fan_percentiles.columns) == ["p05", "p25", "p50", "p75", "p95"]
    assert result.sample_paths.shape == (8, 8)
    assert result.terminal_returns.shape == (32,)
    assert result.fan_percentiles.index.tolist() == list(range(8))
    assert np.allclose(result.sample_paths.iloc[0].to_numpy(), np.ones(8))


def test_monte_carlo_invalid_inputs_return_none():
    returns = pd.DataFrame()
    weights = pd.Series(dtype=float)

    assert monte_carlo_var_cvar(returns, weights, 0.95, 5, "Gaussian", 100, 1) is None
    assert monte_carlo_var_cvar(
        pd.DataFrame({"A": [0.01, 0.02]}),
        pd.Series({"B": 1.0}),
        0.95,
        5,
        "Gaussian",
        100,
        1,
    ) is None
