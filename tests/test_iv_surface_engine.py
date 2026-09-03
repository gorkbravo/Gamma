from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from src.models.iv import IVOptionContractRecord
from src.services.iv_surface_engine import IVSurfaceEngine


def _future_expiries(*offsets: int) -> list[str]:
    """Expiry codes relative to today, so tenor-dependent fits stay time-independent."""
    today = datetime.utcnow().date()
    return [(today + timedelta(days=offset)).strftime("%Y%m%d") for offset in offsets]


def test_choose_expiries_prefers_target_tenors_over_first_available_dates():
    engine = object.__new__(IVSurfaceEngine)
    engine.max_expiries = 4
    today = datetime.utcnow().date()
    expirations = [
        (today + timedelta(days=days)).strftime("%Y%m%d")
        for days in [0, 1, 4, 7, 14, 21, 30, 45]
    ]

    selected = engine._choose_expiries(expirations)
    selected_dtes = [
        (datetime.strptime(expiry, "%Y%m%d").date() - today).days
        for expiry in selected
    ]

    assert selected_dtes == [0, 7, 14, 30]


def test_sample_strikes_for_surface_keeps_atm_density_and_wings():
    engine = object.__new__(IVSurfaceEngine)
    engine.strike_band_pct = 0.12

    selected = engine._sample_strikes_for_surface(range(88, 113), spot=100.0, limit=9)

    assert len(selected) == 9
    assert selected == sorted(selected)
    assert min(selected) <= 89
    assert max(selected) >= 111
    assert 100 in selected


def test_pair_record_uses_display_price_fallback_for_straddle_and_move():
    engine = object.__new__(IVSurfaceEngine)
    call = IVOptionContractRecord(
        contract_id="SPY-20260619-100-C",
        symbol="SPY",
        expiry="20260619",
        strike=100.0,
        right="C",
        mark_price=2.5,
    )
    put = IVOptionContractRecord(
        contract_id="SPY-20260619-100-P",
        symbol="SPY",
        expiry="20260619",
        strike=100.0,
        right="P",
        last=2.0,
    )

    pair = engine._build_pair_record(
        pair_id="SPY-20260619-100",
        expiry="20260619",
        strike=100.0,
        call_contract=call,
        put_contract=put,
        spot=100.0,
    )

    assert pair.call_price == 2.5
    assert pair.call_price_source == "mark"
    assert pair.put_price == 2.0
    assert pair.put_price_source == "last"
    assert pair.straddle_midpoint == 4.5
    assert pair.implied_move_pct == 0.045


def test_surface_model_normalization_accepts_common_labels():
    assert IVSurfaceEngine.normalize_surface_model("Line interpolation") == "linear"
    assert IVSurfaceEngine.normalize_surface_model("spline-interpolation") == "spline"
    assert IVSurfaceEngine.normalize_surface_model("SSVI") == "ssvi"
    assert IVSurfaceEngine.normalize_surface_model("unsupported") == "linear"


def test_spline_surface_model_fills_missing_cells_with_metadata():
    engine = object.__new__(IVSurfaceEngine)
    engine.surface_model = "spline"
    raw_grid = np.array(
        [
            [0.24, np.nan, 0.2, np.nan, 0.24],
            [0.26, 0.23, np.nan, 0.23, 0.26],
            [0.28, np.nan, 0.24, np.nan, 0.28],
        ],
        dtype=float,
    )

    expiries = _future_expiries(30, 60, 90)
    grid, metadata, lineage = engine._fit_surface_grid(raw_grid, expiries, [90, 95, 100, 105, 110], 100)

    assert grid is not None
    assert np.isfinite(grid).all()
    assert metadata.model == "spline"
    assert metadata.status == "applied"


def test_ssvi_surface_model_fits_dense_smile_slices():
    engine = object.__new__(IVSurfaceEngine)
    engine.surface_model = "ssvi"
    strikes = [85, 90, 95, 100, 105, 110, 115]
    raw_grid = np.array(
        [
            [0.31, 0.27, 0.23, 0.2, 0.205, 0.22, 0.245],
            [0.34, 0.3, 0.26, 0.23, 0.235, 0.25, 0.275],
        ],
        dtype=float,
    )

    grid, metadata, lineage = engine._fit_surface_grid(raw_grid, _future_expiries(30, 60), strikes, 100)

    assert grid is not None
    assert np.isfinite(grid).all()
    assert metadata.model == "ssvi"
    assert metadata.status == "applied"
    assert grid.shape == raw_grid.shape


def test_missing_atm_cell_is_filled_from_same_expiry_neighbours_not_other_expiries():
    """GUA-20260903-1: a missing ATM strike must not inherit another expiry's value."""
    engine = object.__new__(IVSurfaceEngine)
    engine.surface_model = "linear"
    expiries = _future_expiries(15, 79, 135)
    strikes = [330.0, 335.0, 337.5, 340.0, 345.0]
    raw_grid = np.array(
        [
            [0.315, 0.305, np.nan, 0.300, 0.298],
            [0.340, 0.333, np.nan, 0.327, 0.322],
            [0.250, 0.248, 0.244, 0.243, 0.241],
        ],
        dtype=float,
    )

    grid, metadata, lineage = engine._fit_surface_grid(raw_grid, expiries, strikes, 337.76)

    assert grid is not None
    atm = grid[1][2]
    assert 0.327 <= atm <= 0.333, f"ATM fill {atm} escaped its own expiry's observed range"
    assert lineage[1][2] == "strike_interpolated"
    assert lineage[1][1] == "observed"
    assert metadata.status == "applied"


def test_wing_fill_extends_nearest_observed_strike_on_the_same_expiry():
    engine = object.__new__(IVSurfaceEngine)
    engine.surface_model = "linear"
    expiries = _future_expiries(15, 79)
    strikes = [300.0, 330.0, 340.0, 400.0]
    raw_grid = np.array(
        [
            [np.nan, 0.30, 0.29, np.nan],
            [0.44, 0.34, 0.33, 0.45],
        ],
        dtype=float,
    )

    grid, _metadata, lineage = engine._fit_surface_grid(raw_grid, expiries, strikes, 335.0)

    assert grid[0][0] == 0.30
    assert grid[0][3] == 0.29
    assert lineage[0][0] == "strike_extended"
    assert lineage[0][3] == "strike_extended"


def test_expiry_without_any_observation_falls_back_to_the_term_axis_and_is_clamped():
    engine = object.__new__(IVSurfaceEngine)
    engine.surface_model = "linear"
    expiries = _future_expiries(15, 79, 135)
    strikes = [330.0, 340.0]
    raw_grid = np.array(
        [
            [0.30, 0.29],
            [np.nan, np.nan],
            [0.36, 0.35],
        ],
        dtype=float,
    )

    grid, _metadata, lineage = engine._fit_surface_grid(raw_grid, expiries, strikes, 335.0)

    assert 0.30 <= grid[1][0] <= 0.36
    assert lineage[1][0] == "term_interpolated"


def test_discontinuity_detection_reports_fitted_cells_outside_observed_range():
    engine = object.__new__(IVSurfaceEngine)
    expiries = _future_expiries(79)
    strikes = [335.0, 337.5, 340.0]
    raw_grid = np.array([[0.333, np.nan, 0.327]], dtype=float)
    grid = np.array([[0.333, 0.244, 0.327]], dtype=float)
    lineage = np.array([["observed", "strike_interpolated", "observed"]], dtype=object)

    notes = engine._detect_surface_discontinuities(grid, lineage, raw_grid, expiries, strikes)

    assert notes
    assert "disagree with same-expiry observations" in notes[0]


def test_cells_with_no_observation_on_either_axis_stay_finite_but_are_marked_unavailable():
    """The grid must stay JSON-serialisable while still admitting it has no data."""
    engine = object.__new__(IVSurfaceEngine)
    engine.surface_model = "linear"
    expiries = _future_expiries(15, 79)
    strikes = [300.0, 330.0, 340.0]
    raw_grid = np.array(
        [
            [np.nan, 0.30, 0.29],
            [np.nan, np.nan, np.nan],
        ],
        dtype=float,
    )

    grid, _metadata, lineage = engine._fit_surface_grid(raw_grid, expiries, strikes, 335.0)

    assert np.isfinite(grid).all()
    assert lineage[1][0] == "unavailable"
    # Only one expiry carried observations, so the fill extends rather than interpolates.
    assert lineage[1][1] == "term_extended"
