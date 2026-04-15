from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi import HTTPException

from src.api.schemas.system import (
    ActionResponseModel,
    BaseCurrencyRequestModel,
    BaseCurrencyResponseModel,
    ConnectionStateModel,
    DiagnosticsResponseModel,
    HealthResponseModel,
    MarketDataModeRequestModel,
    ProviderCapabilityListResponseModel,
    ProviderCapabilityModel,
    ReadOnlyBoundaryModel,
    SystemStatusResponseModel,
)
from src.models.platform_boundary import build_gamma_read_only_boundary
from src.utils.time import now_utc


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponseModel)
def health() -> HealthResponseModel:
    return HealthResponseModel(status="ok", timestamp=now_utc())


@router.get("/system/status", response_model=SystemStatusResponseModel)
def system_status(request: Request) -> SystemStatusResponseModel:
    runtime = request.app.state.runtime
    return _system_status_response(runtime)


@router.get("/system/provider-capabilities", response_model=ProviderCapabilityListResponseModel)
def provider_capabilities(
    request: Request,
    status: str | None = Query(default=None),
    include_planned: bool = Query(default=True),
) -> ProviderCapabilityListResponseModel:
    runtime = request.app.state.runtime
    providers = runtime.provider_capabilities.list_capabilities(
        status=status,
        include_planned=include_planned,
    )
    generated_at = next((provider.retrieved_at for provider in providers if provider.retrieved_at is not None), now_utc())
    return ProviderCapabilityListResponseModel(
        generated_at=generated_at,
        providers=[ProviderCapabilityModel.from_domain(provider) for provider in providers],
        retrieved_at=generated_at,
        transformation_note=(
            "Static Roadmap V2 provider metadata; this endpoint does not perform provider health, entitlement, or credential checks."
        ),
    )


@router.get("/system/provider-capabilities/{provider_id}", response_model=ProviderCapabilityModel)
def provider_capability(provider_id: str, request: Request) -> ProviderCapabilityModel:
    runtime = request.app.state.runtime
    provider = runtime.provider_capabilities.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider capability not found: {provider_id}")
    return ProviderCapabilityModel.from_domain(provider)


@router.get("/system/read-only-boundary", response_model=ReadOnlyBoundaryModel)
def read_only_boundary() -> ReadOnlyBoundaryModel:
    return ReadOnlyBoundaryModel.from_domain(build_gamma_read_only_boundary())


@router.post("/system/connection/toggle", response_model=SystemStatusResponseModel)
def toggle_connection(request: Request) -> SystemStatusResponseModel:
    runtime = request.app.state.runtime
    if not runtime.mock_mode:
        if runtime.client.is_connected():
            runtime.client.disconnect()
        else:
            runtime.client.connect()
    return _system_status_response(runtime)


@router.post("/system/market-data-mode", response_model=SystemStatusResponseModel)
def set_market_data_mode(
    payload: MarketDataModeRequestModel,
    request: Request,
) -> SystemStatusResponseModel:
    runtime = request.app.state.runtime
    runtime.set_market_data_mode(payload.market_data_mode)
    return _system_status_response(runtime)


@router.post("/system/base-currency", response_model=BaseCurrencyResponseModel)
def set_base_currency(
    payload: BaseCurrencyRequestModel,
    request: Request,
) -> BaseCurrencyResponseModel:
    runtime = request.app.state.runtime
    try:
        _, lines = runtime.set_base_currency(payload.base_currency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BaseCurrencyResponseModel(**_system_status_response(runtime).model_dump(), lines=lines)


def _system_status_response(runtime) -> SystemStatusResponseModel:
    return SystemStatusResponseModel(
        healthy=True,
        app_name="Gamma API",
        backend="fastapi",
        mock_mode=runtime.mock_mode,
        base_currency=runtime.base_currency,
        market_data_mode=runtime.market_data_mode,
        connection=_connection_state(runtime),
        cached_symbols=runtime.research_cache.symbols(),
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
        cached_symbols=runtime.research_cache.symbols(),
        iv_running=runtime.iv_service.is_running(),
        iv_status_text=runtime.iv_service.status_text(),
        iv_active_symbol=runtime.iv_service.active_symbol(),
    )


@router.post("/diagnostics/run", response_model=ActionResponseModel)
def run_diagnostics(request: Request) -> ActionResponseModel:
    runtime = request.app.state.runtime
    lines = runtime.portfolio_service.run_diagnostics()
    return ActionResponseModel(lines=list(lines or ["Diagnostics returned no output."]))


@router.post("/system/account-subscribe", response_model=ActionResponseModel)
def force_account_subscribe(request: Request) -> ActionResponseModel:
    runtime = request.app.state.runtime
    lines = runtime.portfolio_service.force_account_subscribe()
    return ActionResponseModel(lines=list(lines or ["Force account subscribe returned no output."]))


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
