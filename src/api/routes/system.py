from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.schemas.system import (
    ConnectionStateModel,
    DiagnosticsResponseModel,
    HealthResponseModel,
    SystemStatusResponseModel,
)
from src.utils.time import now_utc


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponseModel)
def health() -> HealthResponseModel:
    return HealthResponseModel(status="ok", timestamp=now_utc())


@router.get("/system/status", response_model=SystemStatusResponseModel)
def system_status(request: Request) -> SystemStatusResponseModel:
    runtime = request.app.state.runtime
    return SystemStatusResponseModel(
        healthy=True,
        app_name="StrataLab API",
        backend="fastapi",
        mock_mode=runtime.mock_mode,
        base_currency=runtime.base_currency,
        market_data_mode=runtime.market_data_mode,
        connection=_connection_state(runtime),
        cached_symbols=sorted(runtime.app_context.cached_timeseries.keys()),
    )


@router.get("/diagnostics", response_model=DiagnosticsResponseModel)
def diagnostics(request: Request) -> DiagnosticsResponseModel:
    runtime = request.app.state.runtime
    history_df = runtime.portfolio_service.load_history()
    return DiagnosticsResponseModel(
        generated_at=now_utc(),
        mock_mode=runtime.mock_mode,
        base_currency=runtime.base_currency,
        market_data_mode=runtime.market_data_mode,
        connection=_connection_state(runtime),
        history_cache=runtime.market_data.history_cache_stats(),
        local_history_entries=int(len(history_df)),
        local_history_path=str(runtime.portfolio_history.path),
        recent_errors=runtime.portfolio_service.formatted_errors(50),
        cached_symbols=sorted(runtime.app_context.cached_timeseries.keys()),
    )


def _connection_state(runtime) -> ConnectionStateModel:
    if runtime.mock_mode:
        return ConnectionStateModel(
            connected=True,
            status_text="Status: Mock",
            action_text="Mock Mode",
            action_enabled=False,
            active_account=runtime.client.account,
        )
    connected = runtime.client.is_connected()
    status_text = "Status: Connected" if connected else "Status: Disconnected"
    return ConnectionStateModel(
        connected=connected,
        status_text=status_text,
        action_text="Disconnect" if connected else "Connect to IBKR",
        action_enabled=True,
        active_account=runtime.client.active_account or runtime.client.account,
    )
