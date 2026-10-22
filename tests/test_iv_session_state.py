"""GUA-20261021-10: etiqueta de sesión y avisos de calidad de la superficie de opciones."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from src.api.schemas.iv import IVSurfaceResponseModel
from src.application.iv_service import IVService, IVSurfaceResult
from src.models.iv import IVOptionContractRecord, IVOptionPairRecord
from src.services.iv_surface_engine import (
    MARKET_SESSION_CLOSED,
    MARKET_SESSION_CLOSED_WARNING,
    MARKET_SESSION_REGULAR,
    IVSurfaceEngine,
    IVSurfaceSnapshot,
    put_call_iv_divergence_warning,
    us_options_market_session,
)


def _pair(strike: float, call_iv: float | None, put_iv: float | None, expiry: str = "20261021") -> IVOptionPairRecord:
    return IVOptionPairRecord(
        pair_id=f"USO:{expiry}:{strike:.2f}",
        expiry=expiry,
        strike=strike,
        call_implied_volatility=call_iv,
        put_implied_volatility=put_iv,
    )


def _contract(market_data_type: int | None = 1) -> IVOptionContractRecord:
    return IVOptionContractRecord(
        contract_id="USO:20261121:163.00:C",
        symbol="USO",
        expiry="20261121",
        strike=163.0,
        right="C",
        market_data_type=market_data_type,
    )


def test_session_is_closed_pre_market_on_the_audit_timestamp():
    # 2026-10-21 10:50 UTC = 06:50 ET (EDT): opciones USA cerradas.
    assert us_options_market_session(datetime(2026, 10, 21, 10, 50)) == MARKET_SESSION_CLOSED


def test_session_is_regular_inside_new_york_hours_and_closed_at_the_bell():
    assert us_options_market_session(datetime(2026, 10, 21, 13, 30)) == MARKET_SESSION_REGULAR  # 09:30 EDT
    assert us_options_market_session(datetime(2026, 10, 21, 19, 59)) == MARKET_SESSION_REGULAR  # 15:59 EDT
    assert us_options_market_session(datetime(2026, 10, 21, 20, 0)) == MARKET_SESSION_CLOSED  # 16:00 EDT
    assert us_options_market_session(datetime(2026, 10, 21, 13, 29)) == MARKET_SESSION_CLOSED  # 09:29 EDT


def test_session_follows_standard_time_and_weekends():
    # Diciembre: EST (UTC-5).
    assert us_options_market_session(datetime(2026, 12, 2, 14, 45)) == MARKET_SESSION_REGULAR  # 09:45 EST
    assert us_options_market_session(datetime(2026, 12, 2, 14, 15)) == MARKET_SESSION_CLOSED  # 09:15 EST
    # Sábado a mediodía de Nueva York.
    assert us_options_market_session(datetime(2026, 10, 24, 16, 0)) == MARKET_SESSION_CLOSED


def test_session_accepts_timezone_aware_inputs():
    madrid = timezone(timedelta(hours=2))
    # 17:00 CEST = 15:00 UTC = 11:00 EDT.
    assert us_options_market_session(datetime(2026, 10, 21, 17, 0, tzinfo=madrid)) == MARKET_SESSION_REGULAR


def test_put_call_divergence_flags_the_uso_zero_dte_strike():
    warning = put_call_iv_divergence_warning([_pair(163.0, 0.14, 0.986), _pair(164.0, 0.30, 0.31)], 163.2)

    assert warning is not None
    assert "1 near-the-money strike " in warning
    assert "2026/10/21 163" in warning
    assert "call 14.0% vs put 98.6%" in warning


def test_put_call_divergence_uses_both_ratio_and_vol_point_thresholds():
    # 0.50 frente a 0.95: ratio < 3x pero 45 puntos de vol > 40.
    assert put_call_iv_divergence_warning([_pair(100.0, 0.50, 0.95)], 100.0) is not None
    # 0.10 frente a 0.35: solo 25 puntos, pero ratio 3.5x.
    assert put_call_iv_divergence_warning([_pair(100.0, 0.10, 0.35)], 100.0) is not None
    # Divergencia normal de skew: sin aviso.
    assert put_call_iv_divergence_warning([_pair(100.0, 0.24, 0.27)], 100.0) is None


def test_put_call_divergence_ignores_far_wings_and_one_sided_pairs():
    pairs = [_pair(120.0, 0.10, 0.90), _pair(100.0, None, 0.90), _pair(101.0, 0.25, None)]
    assert put_call_iv_divergence_warning(pairs, 100.0) is None
    assert put_call_iv_divergence_warning([_pair(100.0, 0.14, 0.98)], None) is None


def test_snapshot_session_state_never_labels_a_closed_session_live():
    market_session, freshness, warnings = IVSurfaceEngine._snapshot_session_state(
        contracts=[_contract(1)],
        pairs=[_pair(163.0, 0.14, 0.986)],
        spot=163.2,
        delayed=False,
        now=datetime(2026, 10, 21, 10, 50),
    )

    assert market_session == MARKET_SESSION_CLOSED
    assert freshness == "stale"
    assert warnings[0] == MARKET_SESSION_CLOSED_WARNING
    assert any("Put/call IV diverge" in item for item in warnings)


def test_snapshot_session_state_keeps_live_and_delayed_inside_the_session():
    regular = datetime(2026, 10, 21, 15, 0)
    live = IVSurfaceEngine._snapshot_session_state(
        contracts=[_contract(1)], pairs=[_pair(100.0, 0.25, 0.26)], spot=100.0, delayed=False, now=regular
    )
    delayed = IVSurfaceEngine._snapshot_session_state(
        contracts=[_contract(3)], pairs=[_pair(100.0, 0.25, 0.26)], spot=100.0, delayed=True, now=regular
    )
    frozen = IVSurfaceEngine._snapshot_session_state(
        contracts=[_contract(2)], pairs=[_pair(100.0, 0.25, 0.26)], spot=100.0, delayed=False, now=regular
    )

    assert live == (MARKET_SESSION_REGULAR, "live", [])
    assert delayed == (MARKET_SESSION_REGULAR, "delayed", [])
    # marketDataType 2 = congelado (último cierre): tampoco es "live".
    assert frozen[1] == "stale"


def test_surface_response_carries_session_and_quote_warnings_first():
    snapshot = IVSurfaceSnapshot(
        symbol="USO",
        spot=163.2,
        expiries=["20261021", "20261121"],
        strikes=[160.0, 163.0],
        iv_grid=np.array([[0.5, 0.563], [0.45, 0.469]]),
        timestamp=datetime(2026, 10, 21, 10, 50),
        delayed=False,
        points=4,
        freshness_label="stale",
        market_session=MARKET_SESSION_CLOSED,
        quote_warnings=[MARKET_SESSION_CLOSED_WARNING],
    )
    result = IVSurfaceResult(snapshot=snapshot, warnings=["Requested deep options depth was unavailable.", MARKET_SESSION_CLOSED_WARNING])

    response = IVSurfaceResponseModel.from_service_result("USO", result)

    assert response.market_session == MARKET_SESSION_CLOSED
    assert response.freshness_label == "stale"
    assert response.warnings == [MARKET_SESSION_CLOSED_WARNING, "Requested deep options depth was unavailable."]


def test_unavailable_surface_has_no_market_session():
    response = IVSurfaceResponseModel.from_service_result("USO", IVSurfaceResult(snapshot=None))
    assert response.market_session is None


class _IdleClient:
    mock = False

    @staticmethod
    def is_connected() -> bool:
        return True


def test_idle_iv_service_reports_no_active_symbol():
    # GUA-20261021-10: sin sesión iniciada no se inventa "SPY".
    service = IVService(client=_IdleClient())  # type: ignore[arg-type]
    assert service.active_symbol() is None
