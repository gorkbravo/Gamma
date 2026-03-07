import numpy as np

from src.analytics.risk_metrics import risk_contributions


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
