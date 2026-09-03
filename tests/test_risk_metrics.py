import numpy as np
import pandas as pd

from src.analytics.research_overview import compute_overview_metrics
from src.analytics.risk_metrics import max_drawdown, realized_vol, risk_contributions


def _returns(values: list[float]) -> pd.Series:
    index = pd.date_range("2026-01-02", periods=len(values), freq="D")
    return pd.Series(values, index=index, dtype=float)


def test_realized_vol_reports_absence_for_a_single_observation():
    """One observation has no sample standard deviation.

    pandas answers NaN, which is not JSON-encodable, so returning it made a
    single uncomputable metric fail the whole SITREP workspace response.
    """

    assert realized_vol(_returns([0.01])) == (None, None)
    assert realized_vol(pd.Series(dtype=float)) == (None, None)


def test_realized_vol_still_computes_from_two_observations():
    daily, annual = realized_vol(_returns([0.01, -0.01]))

    assert daily is not None and annual is not None
    assert np.isfinite(daily) and np.isfinite(annual)
    assert annual == daily * (252 ** 0.5)


def test_max_drawdown_reports_absence_rather_than_a_non_finite_number():
    assert max_drawdown(pd.Series(dtype=float)) is None
    assert max_drawdown(_returns([-1.0, 0.5])) is None
    assert max_drawdown(_returns([0.05, -0.10])) is not None


def test_overview_metrics_carry_no_non_finite_values_for_a_one_point_stream():
    metrics = compute_overview_metrics(_returns([0.01]))

    assert metrics.annual_volatility is None
    assert metrics.observation_count == 1
    assert metrics.latest_daily_return == 0.01


def test_risk_contributions_shape_mismatch_returns_empty():
    weights = np.array([1.0])
    cov = np.array([[0.04, 0.0], [0.0, 0.01]])
    contrib = risk_contributions(weights, cov)
    assert contrib.size == 0


def test_risk_contributions_nonpositive_variance_returns_zeros():
    weights = np.array([0.5, 0.5])
    cov = np.zeros((2, 2))
    contrib = risk_contributions(weights, cov)
    assert np.allclose(contrib, np.array([0.0, 0.0]))
