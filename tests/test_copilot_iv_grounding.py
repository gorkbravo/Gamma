"""Grounding guarantees for Copilot runs launched from the Options tab.

Covers GUA-20260903-2: the context must fingerprint the expiry, strategy and
realized-vs-implied state the user is actually looking at, and must keep tenor
identity attached to every implied-volatility figure it carries.
"""

from __future__ import annotations

from src.application.copilot_context_helpers import summarize_iv_state, summarize_iv_workbench


SURFACE = {
    "symbol": "GOOGL",
    "snapshot_available": True,
    "spot": 337.76,
    "points": 71,
    "delayed": False,
    "expiries": ["20260905", "20261120", "20270116"],
    "strikes": [330.0, 335.0, 337.5, 340.0, 345.0],
    "iv_grid": [
        [0.320, 0.312, 0.305, 0.301, 0.298],
        [0.340, 0.333, 0.330, 0.327, 0.322],
        [0.352, 0.347, 0.344, 0.341, 0.338],
    ],
    "cell_sources": [
        ["observed", "observed", "observed", "observed", "observed"],
        ["observed", "observed", "strike_interpolated", "observed", "observed"],
        ["observed", "observed", "observed", "observed", "observed"],
    ],
    "surface_model": "linear",
    "surface_model_label": "Line interpolation",
    "surface_model_status": "applied",
    "surface_model_discontinuities": [],
}

WORKBENCH = {
    "mode": "strategies",
    "symbol": "GOOGL",
    "selected_expiry": "20261120",
    "selected_expiry_days": 79,
    "contracts": 1,
    "contract_multiplier": 100,
    "legs": [
        {
            "side": "long",
            "option_type": "put",
            "expiry": "20261120",
            "days_to_expiry": 79,
            "strike": 340.0,
            "premium": 18.0,
            "quantity": 1,
        },
        {
            "side": "short",
            "option_type": "put",
            "expiry": "20261120",
            "days_to_expiry": 79,
            "strike": 315.0,
            "premium": 7.33,
            "quantity": 1,
        },
    ],
    "strategy": {
        "net_premium_per_share": -10.67,
        "net_premium_total": -1067.0,
        "premium_direction": "debit",
        "max_profit_per_share": 14.33,
        "max_loss_per_share": -10.67,
        "max_profit_total": 1433.0,
        "max_loss_total": -1067.0,
        "breakevens": [329.33],
        "net_delta": -0.31,
        "net_gamma": 0.004,
        "net_vega": 0.12,
        "net_theta": -0.02,
        "shares_represented": 100,
        "live_position_shares": 60,
        "coverage_ratio": 1.6667,
        "sizing_warnings": ["One 100-share contract already exceeds the live 60-share position; no whole-contract size matches this exposure."],
    },
    "realized_vs_implied": [
        {
            "window_days": 60,
            "realized_vol": 0.366,
            "reference_iv": 0.330,
            "reference_iv_expiry": "20261120",
            "reference_iv_days": 79,
            "spread": -0.036,
        }
    ],
}


def test_selected_expiry_drives_the_iv_slice_instead_of_the_front_month():
    summary = summarize_iv_state(SURFACE, None, WORKBENCH)

    assert summary is not None
    assert summary["selected_expiry"] == "20261120"
    assert summary["selected_expiry_days"] == 79
    assert summary["selected_expiry_is_front"] is False
    assert summary["front_expiry"] == "20260905"
    assert summary["selected_slice"]["expiry"] == "20261120"
    assert summary["selected_slice"]["atm_iv"] == 0.330
    assert summary["front_slice"]["atm_iv"] == 0.330


def test_missing_workbench_state_still_falls_back_to_the_front_expiry():
    summary = summarize_iv_state(SURFACE, None, None)

    assert summary is not None
    assert summary["selected_expiry"] == "20260905"
    assert summary["selected_expiry_is_front"] is True
    assert summary["workbench"] is None


def test_selected_atm_cell_carries_its_provenance():
    summary = summarize_iv_state(SURFACE, None, WORKBENCH)

    assert summary["selected_slice"]["atm_iv_source"] == "strike_interpolated"


def test_visible_strategy_terms_travel_with_the_context():
    summary = summarize_iv_state(SURFACE, None, WORKBENCH)
    workbench = summary["workbench"]

    assert workbench["mode"] == "strategies"
    assert workbench["contracts"] == 1
    assert workbench["contract_multiplier"] == 100
    assert len(workbench["legs"]) == 2
    assert workbench["strategy"]["net_premium_per_share"] == -10.67
    assert workbench["strategy"]["net_premium_total"] == -1067.0
    assert workbench["strategy"]["premium_direction"] == "debit"
    assert workbench["strategy"]["max_profit_total"] == 1433.0
    assert workbench["strategy"]["breakevens"] == [329.33]
    assert workbench["strategy"]["coverage_ratio"] == 1.6667


def test_realized_vs_implied_rows_name_the_expiry_they_compare_against():
    summary = summarize_iv_state(SURFACE, None, WORKBENCH)
    rows = summary["workbench"]["realized_vs_implied"]

    assert rows[0]["window_days"] == 60
    assert rows[0]["reference_iv_expiry"] == "20261120"
    assert rows[0]["reference_iv_days"] == 79
    assert rows[0]["reference_iv"] == 0.330


def test_surface_model_discontinuities_reach_the_context():
    surface = dict(SURFACE)
    surface["surface_model_discontinuities"] = ["20261120 337.5 fitted 24.4% vs observed 32.7%-33.3%"]

    summary = summarize_iv_state(surface, None, WORKBENCH)

    assert summary["surface_model"]["discontinuities"] == [
        "20261120 337.5 fitted 24.4% vs observed 32.7%-33.3%"
    ]


def test_summarize_iv_workbench_handles_an_empty_builder():
    assert summarize_iv_workbench(None) is None
    assert summarize_iv_workbench({}) is None
    empty = summarize_iv_workbench({"mode": "chain", "selected_expiry": "20261120"})
    assert empty is not None
    assert empty["strategy"] is None
    assert empty["legs"] == []


def test_workbench_for_a_different_symbol_is_discarded_with_a_warning():
    """GUA-20260903-6: an AAPL surface must never carry a GOOGL structure."""
    stale = dict(WORKBENCH)
    stale["symbol"] = "AAPL"

    summary = summarize_iv_state(SURFACE, None, stale)

    assert summary["workbench"] is None
    assert any("Discarded an Options workbench snapshot for AAPL" in warning for warning in summary["warnings"])


def test_legs_priced_against_another_symbol_are_stripped_but_the_view_state_survives():
    stale = dict(WORKBENCH)
    stale["strategy_symbol"] = "AAPL"

    summary = summarize_iv_state(SURFACE, None, stale)
    workbench = summary["workbench"]

    assert workbench is not None
    assert workbench["selected_expiry"] == "20261120"
    assert workbench["legs"] == []
    assert workbench["strategy"] is None
    assert any("Discarded strategy legs priced against AAPL" in warning for warning in summary["warnings"])


def test_matching_symbols_keep_the_full_workbench():
    matching = dict(WORKBENCH)
    matching["strategy_symbol"] = "GOOGL"

    summary = summarize_iv_state(SURFACE, None, matching)

    assert summary["workbench"]["strategy"] is not None
    assert len(summary["workbench"]["legs"]) == 2
    assert not any("Discarded" in warning for warning in summary["warnings"])
