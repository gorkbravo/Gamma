from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.api.schemas.commodities import CommodityWorkspaceResponseModel
from src.api.schemas.macro import MacroSnapshotResponseModel
from src.api.schemas.news import NewsEventFeedResponseModel
from src.api.schemas.prediction_markets import PredictionMarketListResponseModel
from src.api.schemas.research import ResearchOverviewResponseModel
from src.application.sitrep_service import SitrepWorkspaceResult
from src.models.sitrep import SitrepFollowUp


class SitrepWorkspaceResponseModel(BaseModel):
    equities_overview: ResearchOverviewResponseModel | None = None
    indices_overview: ResearchOverviewResponseModel | None = None
    macro_snapshot: MacroSnapshotResponseModel | None = None
    commodities: CommodityWorkspaceResponseModel | None = None
    prediction_markets: PredictionMarketListResponseModel | None = None
    news: NewsEventFeedResponseModel | None = None
    sections: list[str]
    section_warnings: list[str]
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, result: SitrepWorkspaceResult) -> "SitrepWorkspaceResponseModel":
        return cls(
            equities_overview=(
                ResearchOverviewResponseModel.from_domain(result.equities_overview)
                if result.equities_overview is not None
                else None
            ),
            indices_overview=(
                ResearchOverviewResponseModel.from_domain(result.indices_overview)
                if result.indices_overview is not None
                else None
            ),
            macro_snapshot=(
                MacroSnapshotResponseModel.from_domain(result.macro_snapshot)
                if result.macro_snapshot is not None
                else None
            ),
            commodities=(
                CommodityWorkspaceResponseModel.from_domain(result.commodities)
                if result.commodities is not None
                else None
            ),
            prediction_markets=(
                PredictionMarketListResponseModel.from_domain(result.prediction_markets)
                if result.prediction_markets is not None
                else None
            ),
            news=NewsEventFeedResponseModel.from_domain(result.news) if result.news is not None else None,
            sections=list(result.sections),
            section_warnings=list(result.section_warnings),
            source_provider=result.source_provider,
            retrieved_at=result.retrieved_at,
            origin=result.origin,
            transformation_note=result.transformation_note,
        )


class SitrepFollowUpModel(BaseModel):
    id: str
    row_id: str
    title: str
    source: str = ""
    tone: str = "neutral"
    detail: str = ""
    meta: str = ""
    note: str = ""
    status: str = "open"
    handoff: dict[str, Any] | None = None
    saved_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None

    @classmethod
    def from_domain(cls, item: SitrepFollowUp) -> "SitrepFollowUpModel":
        return cls(
            id=item.id,
            row_id=item.row_id,
            title=item.title,
            source=item.source,
            tone=item.tone,
            detail=item.detail,
            meta=item.meta,
            note=item.note,
            status=item.status,
            handoff=dict(item.handoff) if item.handoff else None,
            saved_at=item.saved_at,
            updated_at=item.updated_at,
            resolved_at=item.resolved_at,
        )


class SitrepFollowUpListResponseModel(BaseModel):
    items: list[SitrepFollowUpModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, items: list[SitrepFollowUp]) -> "SitrepFollowUpListResponseModel":
        return cls(items=[SitrepFollowUpModel.from_domain(item) for item in items])


class SitrepFollowUpCreateRequestModel(BaseModel):
    row_id: str
    title: str
    source: str = ""
    tone: str = "neutral"
    detail: str = ""
    meta: str = ""
    note: str = ""
    handoff: dict[str, Any] | None = None
    saved_at: datetime | None = None


class SitrepFollowUpUpdateRequestModel(BaseModel):
    note: str | None = None
    status: str | None = None


class SitrepFollowUpDeleteResponseModel(BaseModel):
    success: bool
