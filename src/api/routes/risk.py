from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.schemas.risk import RiskComputeRequestModel, RiskComputeResponseModel
from src.application.risk_service import RiskComputeRequest


router = APIRouter(tags=["risk"])


@router.post("/risk/compute", response_model=RiskComputeResponseModel)
def compute_risk(
    payload: RiskComputeRequestModel,
    request: Request,
) -> RiskComputeResponseModel:
    runtime = request.app.state.runtime
    result = runtime.risk_service.compute(
        RiskComputeRequest(
            snapshot=payload.snapshot.to_domain(),
            alpha=payload.alpha,
            lookback_days=payload.lookback_days,
            horizon_days=payload.horizon_days,
            mc_horizon_days=payload.mc_horizon_days,
            mc_simulation_model=payload.mc_simulation_model,
            mc_num_simulations=payload.mc_num_simulations,
            beta_window=payload.beta_window,
            benchmark_symbol=payload.benchmark_symbol,
            base_currency=payload.snapshot.base_currency,
            include_monte_carlo=payload.include_monte_carlo,
        )
    )
    return RiskComputeResponseModel.from_service_payload(result)
