from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ProviderCapability:
    provider_id: str
    display_name: str
    provider_class: str
    status: str
    supported_domains: list[str] = field(default_factory=list)
    asset_classes: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    data_types: list[str] = field(default_factory=list)
    supports_live: bool = False
    supports_delayed: bool = False
    supports_historical: bool = False
    freshness_levels: list[str] = field(default_factory=list)
    historical_depth: str | None = None
    requires_api_key: bool = False
    requires_user_entitlement: bool = False
    credential_env_vars: list[str] = field(default_factory=list)
    configuration_notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance_notes: list[str] = field(default_factory=list)
    read_only_notes: list[str] = field(default_factory=list)
    source_provider_values: list[str] = field(default_factory=list)
    batch_fetching: str | None = None
    background_refresh_safe: bool = False
    safe_for_copilot: bool = True
    source_provider: str = "gamma"
    retrieved_at: datetime | None = None
    origin: str = "provider_capability_registry.static"
    transformation_note: str | None = None
