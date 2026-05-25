from __future__ import annotations

from fastapi import APIRouter, Query, Request

from src.api.schemas.news import NewsEventFeedResponseModel


router = APIRouter(tags=["news"])


@router.get("/news/latest", response_model=NewsEventFeedResponseModel)
def news_latest(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    force_refresh: bool = Query(default=False),
) -> NewsEventFeedResponseModel:
    runtime = request.app.state.runtime
    feed = runtime.news_service.latest(limit=limit, force_refresh=force_refresh)
    return NewsEventFeedResponseModel.from_domain(feed)
