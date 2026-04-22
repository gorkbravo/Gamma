from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from src.models.provenance import FreshnessLabel, normalize_freshness_label
from src.utils.time import now_utc


@dataclass(frozen=True)
class NewsEventEntity:
    label: str
    entity_type: str
    normalized_id: str | None = None
    symbol: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.label, "entity label")
        _require_text(self.entity_type, "entity_type")

    def resolved_id(self) -> str:
        if self.normalized_id:
            return self.normalized_id
        if self.symbol:
            return str(self.symbol).strip().upper()
        return self.label.strip().lower().replace(" ", "_")


@dataclass(frozen=True)
class NewsEventItem:
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
    detected_entities: list[NewsEventEntity] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    warnings: list[str] = field(default_factory=list)
    transformation_note: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.normalized_id, "normalized_id")
        _require_text(self.title, "title")
        _require_text(self.url, "url")
        _require_text(self.source_provider, "source_provider")
        _require_text(self.source_name, "source_name")
        _require_text(self.origin, "origin")
        domain = self.source_domain or source_domain_from_url(self.url)
        object.__setattr__(self, "source_domain", domain)
        object.__setattr__(self, "tags", _dedupe_text(self.tags))
        object.__setattr__(self, "warnings", _dedupe_text(self.warnings))
        object.__setattr__(self, "freshness_label", normalize_freshness_label(self.freshness_label))

    def dedupe_key(self) -> str:
        provider_id = str(self.provider_item_id or "").strip()
        if provider_id:
            return f"{self.source_provider}:{provider_id}".lower()
        return canonical_news_url(self.url)


@dataclass(frozen=True)
class NewsEventFeed:
    items: list[NewsEventItem]
    source_provider: str
    retrieved_at: datetime = field(default_factory=now_utc)
    origin: str = "news_service.latest"
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    warnings: list[str] = field(default_factory=list)
    transformation_note: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_provider, "source_provider")
        object.__setattr__(self, "freshness_label", normalize_freshness_label(self.freshness_label))
        object.__setattr__(self, "warnings", _dedupe_text(self.warnings))


def source_domain_from_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def canonical_news_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{host}{path}".lower()


def _dedupe_text(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _require_text(value: Any, field_name: str) -> None:
    if not str(value or "").strip():
        raise ValueError(f"{field_name} is required.")

