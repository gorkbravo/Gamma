from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from src.models.iv import IVOptionContractRecord
from src.services.iv_surface_engine import IVSurfaceEngine


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

    grid, metadata = engine._fit_surface_grid(raw_grid, ["20260619", "20260717", "20260821"], [90, 95, 100, 105, 110], 100)

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

    grid, metadata = engine._fit_surface_grid(raw_grid, ["20260619", "20260717"], strikes, 100)

    assert grid is not None
    assert np.isfinite(grid).all()
    assert metadata.model == "ssvi"
    assert metadata.status == "applied"
    assert grid.shape == raw_grid.shape
