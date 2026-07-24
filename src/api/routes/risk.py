from __future__ import annotations

import pandas as pd
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
    source_scope = str(payload.source_scope or "portfolio").strip().lower()
    data_provider = runtime.research_provider if source_scope == "research" else runtime.portfolio_provider
    if source_scope == "research_book":
        data_provider = runtime.research_provider
    research_book_returns = _points_to_series(payload.research_book_return_points)
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
            source_scope=source_scope,
            source_label=payload.source_label,
            source_object_id=payload.source_object_id,
            source_origin=payload.source_origin,
            research_book_returns=research_book_returns,
            research_book_legs=[leg.to_domain() for leg in payload.research_book_legs],
        ),
        data_provider=data_provider,
    )
    return RiskComputeResponseModel.from_service_payload(result)


def _points_to_series(points) -> pd.Series | None:
    if not points:
        return None
    rows: dict[pd.Timestamp, float] = {}
    for point in points:
        try:
            timestamp = pd.Timestamp(point.timestamp)
            value = float(point.value)
        except Exception:
            continue
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert(None)
        if pd.isna(timestamp) or not pd.notna(value):
            continue
        rows[timestamp] = value
    if not rows:
        return None
    return pd.Series(rows).sort_index()
