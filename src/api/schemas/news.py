from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.news import NewsEventEntity, NewsEventFeed, NewsEventItem, NewsReportingSource
from src.models.provenance import FreshnessLabel


class NewsEventEntityModel(BaseModel):
    label: str
    entity_type: str
    normalized_id: str | None = None
    symbol: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, row: NewsEventEntity) -> "NewsEventEntityModel":
        return cls(**row.__dict__)


class NewsReportingSourceModel(BaseModel):
    normalized_id: str
    source_provider: str
    source_name: str
    url: str
    published_at: datetime
    retrieved_at: datetime
    origin: str
    provider_item_id: str | None = None
    source_domain: str | None = None

    @classmethod
    def from_domain(cls, row: NewsReportingSource) -> "NewsReportingSourceModel":
        return cls(**row.__dict__)


class NewsEventItemModel(BaseModel):
    normalized_id: str
    title: str
    url: str
    source_provider: str
    source_name: str
    published_at: datetime
    retrieved_at: datetime
    origin: str
    summary: str | None = None
    source_domain: str | None = None
    provider_item_id: str | None = None
    detected_entities: list[NewsEventEntityModel] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    source_reliability: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    transformation_note: str | None = None
    reporting_sources: list[NewsReportingSourceModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: NewsEventItem) -> "NewsEventItemModel":
        return cls(
            **{
                **row.__dict__,
                "detected_entities": [
                    NewsEventEntityModel.from_domain(entity) for entity in row.detected_entities
                ],
                "reporting_sources": [
                    NewsReportingSourceModel.from_domain(source)
                    for source in row.reporting_sources
                ],
            }
        )


class NewsEventFeedResponseModel(BaseModel):
    items: list[NewsEventItemModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime
    origin: str
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    warnings: list[str] = Field(default_factory=list)
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: NewsEventFeed) -> "NewsEventFeedResponseModel":
        return cls(
            **{
                **row.__dict__,
                "items": [NewsEventItemModel.from_domain(item) for item in row.items],
            }
        )
