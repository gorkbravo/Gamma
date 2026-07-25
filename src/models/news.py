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


NEWS_SOURCE_RELIABILITY_LABELS = ("official", "major_outlet", "aggregator", "sample", "unknown")


def normalize_news_source_reliability(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in NEWS_SOURCE_RELIABILITY_LABELS else "unknown"


@dataclass(frozen=True)
class NewsReportingSource:
    """One reporting feed retained when normalized news items deduplicate."""

    normalized_id: str
    source_provider: str
    source_name: str
    url: str
    published_at: datetime
    retrieved_at: datetime
    origin: str
    provider_item_id: str | None = None
    source_domain: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.normalized_id, "reporting normalized_id")
        _require_text(self.source_provider, "reporting source_provider")
        _require_text(self.source_name, "reporting source_name")
        validated = validate_news_url(self.url)
        if validated is None:
            raise ValueError("reporting url must be a navigable http/https URL without embedded credentials.")
        object.__setattr__(self, "url", validated)
        object.__setattr__(self, "source_domain", self.source_domain or source_domain_from_url(validated))


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
    source_reliability: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    transformation_note: str | None = None
    reporting_sources: list[NewsReportingSource] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_text(self.normalized_id, "normalized_id")
        _require_text(self.title, "title")
        validated_url = validate_news_url(self.url)
        if validated_url is None:
            raise ValueError("url must be a navigable http/https URL without embedded credentials.")
        object.__setattr__(self, "url", validated_url)
        _require_text(self.source_provider, "source_provider")
        _require_text(self.source_name, "source_name")
        _require_text(self.origin, "origin")
        domain = self.source_domain or source_domain_from_url(self.url)
        object.__setattr__(self, "source_domain", domain)
        object.__setattr__(self, "tags", _dedupe_text(self.tags))
        object.__setattr__(self, "warnings", _dedupe_text(self.warnings))
        object.__setattr__(self, "freshness_label", normalize_freshness_label(self.freshness_label))
        object.__setattr__(self, "source_reliability", normalize_news_source_reliability(self.source_reliability))
        primary_source = NewsReportingSource(
            normalized_id=self.normalized_id,
            source_provider=self.source_provider,
            source_name=self.source_name,
            url=self.url,
            published_at=self.published_at,
            retrieved_at=self.retrieved_at,
            origin=self.origin,
            provider_item_id=self.provider_item_id,
            source_domain=domain,
        )
        reporting = {
            _reporting_source_key(source): source
            for source in [primary_source, *self.reporting_sources]
        }
        object.__setattr__(
            self,
            "reporting_sources",
            [reporting[key] for key in sorted(reporting)],
        )

    def dedupe_key(self) -> str:
        provider_id = str(self.provider_item_id or "").strip()
        if provider_id:
            return f"{self.source_provider}:{provider_id}".lower()
        return canonical_news_url(self.url)

    def title_dedupe_key(self) -> str:
        """Cross-feed fallback key: the same headline syndicated by two feeds."""
        normalized = "".join(ch for ch in self.title.lower() if ch.isalnum() or ch == " ")
        return "title:" + " ".join(normalized.split())


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


def validate_news_url(url: str) -> str | None:
    text = str(url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.hostname or parsed.username or parsed.password:
        return None
    return text


def canonical_news_url(url: str) -> str:
    validated = validate_news_url(url)
    if validated is None:
        return ""
    parsed = urlparse(validated)
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


def _reporting_source_key(source: NewsReportingSource) -> str:
    provider_item_id = str(source.provider_item_id or "").strip()
    if provider_item_id:
        return f"{source.source_provider}:{provider_item_id}".lower()
    return (
        f"{source.source_provider}:{canonical_news_url(source.url)}:"
        f"{source.published_at.isoformat()}"
    ).lower()
