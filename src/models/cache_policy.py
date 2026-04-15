from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from src.models.provenance import FreshnessLabel, FreshnessRecord, normalize_freshness_label
from src.utils.time import now_utc


class StaleBehavior(str, Enum):
    SERVE_WITH_WARNING = "serve_with_warning"
    SERVE_SILENTLY = "serve_silently"
    REFETCH_REQUIRED = "refetch_required"


@dataclass(frozen=True)
class CacheFreshnessAssessment:
    policy_id: str
    label: FreshnessLabel
    retrieved_at: datetime | None
    source_timestamp: datetime | None
    evaluated_at: datetime
    age_seconds: float | None
    ttl_seconds: float | None
    is_stale: bool
    usable: bool
    should_refresh: bool
    warnings: list[str] = field(default_factory=list)

    def to_freshness_record(self) -> FreshnessRecord:
        return FreshnessRecord(
            label=self.label,
            retrieved_at=self.retrieved_at,
            source_timestamp=self.source_timestamp,
            evaluated_at=self.evaluated_at,
            age_seconds=self.age_seconds,
            ttl_seconds=self.ttl_seconds,
            is_stale=self.is_stale,
            warnings=list(self.warnings),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "label": self.label.value,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "source_timestamp": self.source_timestamp.isoformat() if self.source_timestamp else None,
            "evaluated_at": self.evaluated_at.isoformat(),
            "age_seconds": self.age_seconds,
            "ttl_seconds": self.ttl_seconds,
            "is_stale": self.is_stale,
            "usable": self.usable,
            "should_refresh": self.should_refresh,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CacheFreshnessPolicy:
    policy_id: str
    description: str
    ttl: timedelta | None
    fresh_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    stale_behavior: StaleBehavior = StaleBehavior.SERVE_WITH_WARNING
    stale_warning: str | None = None

    def __post_init__(self) -> None:
        if not str(self.policy_id or "").strip():
            raise ValueError("policy_id is required.")
        if self.ttl is not None and self.ttl.total_seconds() < 0:
            raise ValueError("ttl cannot be negative.")

    def evaluate(
        self,
        *,
        retrieved_at: datetime | None,
        source_timestamp: datetime | None = None,
        evaluated_at: datetime | None = None,
        value_available: bool = True,
        freshness_override: str | FreshnessLabel | None = None,
    ) -> CacheFreshnessAssessment:
        evaluation_time = evaluated_at or now_utc()
        ttl_seconds = self.ttl.total_seconds() if self.ttl is not None else None
        label = normalize_freshness_label(freshness_override) if freshness_override else self.fresh_label
        warnings: list[str] = []

        if not value_available or retrieved_at is None:
            return CacheFreshnessAssessment(
                policy_id=self.policy_id,
                label=FreshnessLabel.UNAVAILABLE,
                retrieved_at=retrieved_at,
                source_timestamp=source_timestamp,
                evaluated_at=evaluation_time,
                age_seconds=None,
                ttl_seconds=ttl_seconds,
                is_stale=False,
                usable=False,
                should_refresh=True,
                warnings=["No cache value is available for this policy."],
            )

        age_seconds = max(0.0, (evaluation_time - retrieved_at).total_seconds())
        is_stale = ttl_seconds is not None and age_seconds > ttl_seconds
        usable = True
        should_refresh = False

        if is_stale:
            label = FreshnessLabel.STALE
            should_refresh = True
            if self.stale_behavior == StaleBehavior.REFETCH_REQUIRED:
                usable = False
                warnings.append(self.stale_warning or f"Cached value for {self.policy_id} is stale and must be refreshed.")
            elif self.stale_behavior == StaleBehavior.SERVE_WITH_WARNING:
                warnings.append(self.stale_warning or f"Cached value for {self.policy_id} is stale.")

        return CacheFreshnessAssessment(
            policy_id=self.policy_id,
            label=label,
            retrieved_at=retrieved_at,
            source_timestamp=source_timestamp,
            evaluated_at=evaluation_time,
            age_seconds=age_seconds,
            ttl_seconds=ttl_seconds,
            is_stale=is_stale,
            usable=usable,
            should_refresh=should_refresh,
            warnings=warnings,
        )


def default_cache_freshness_policies() -> tuple[CacheFreshnessPolicy, ...]:
    return (
        CacheFreshnessPolicy(
            policy_id="live_or_delayed_market_snapshot",
            description="Short-lived quote, surface, or snapshot payload that should refresh quickly when stale.",
            ttl=timedelta(minutes=5),
            fresh_label=FreshnessLabel.UNKNOWN,
            stale_behavior=StaleBehavior.SERVE_WITH_WARNING,
        ),
        CacheFreshnessPolicy(
            policy_id="daily_research_series",
            description="Daily market, macro, crypto, or filing-derived series cached for repeated research reads.",
            ttl=timedelta(hours=24),
            fresh_label=FreshnessLabel.HISTORICAL,
            stale_behavior=StaleBehavior.SERVE_WITH_WARNING,
        ),
        CacheFreshnessPolicy(
            policy_id="historical_reference_dataset",
            description="Slow-moving or historical reference data where stale cache is usable but should remain labeled.",
            ttl=timedelta(days=7),
            fresh_label=FreshnessLabel.HISTORICAL,
            stale_behavior=StaleBehavior.SERVE_WITH_WARNING,
        ),
        CacheFreshnessPolicy(
            policy_id="generated_or_mocked_context",
            description="Locally generated, mocked, or model-generated context that must be labeled as non-source truth.",
            ttl=None,
            fresh_label=FreshnessLabel.MOCKED,
            stale_behavior=StaleBehavior.SERVE_SILENTLY,
        ),
    )

