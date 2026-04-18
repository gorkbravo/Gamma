from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


MARITIME_COVERAGE_STATUSES = {
    "sample",
    "mock",
    "historical",
    "partial",
    "live",
    "unavailable",
}

MARITIME_MODES = {
    "live_map",
    "chokepoints",
    "trade_flows",
    "fleet_monitoring",
    "event_replay",
}


@dataclass(frozen=True)
class MaritimeCoverageMetadata:
    coverage_status: str
    provider_id: str
    provider_label: str
    freshness_label: str
    regions: list[str] = field(default_factory=list)
    as_of: datetime | None = None
    source_timestamp: datetime | None = None
    caveats: list[str] = field(default_factory=list)
    credential_env_vars: list[str] = field(default_factory=list)
    supports_live: bool = False
    supports_historical: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    def __post_init__(self) -> None:
        if self.coverage_status not in MARITIME_COVERAGE_STATUSES:
            raise ValueError(f"Unsupported maritime coverage status: {self.coverage_status}")


@dataclass(frozen=True)
class MaritimeVesselIdentity:
    vessel_id: str
    mmsi: str
    imo: str | None = None
    callsign: str | None = None
    normalized_id: str | None = None


@dataclass(frozen=True)
class MaritimeVesselStaticRecord:
    vessel_id: str
    name: str
    identity: MaritimeVesselIdentity
    vessel_type: str
    vessel_class: str
    flag: str | None = None
    owner_operator: str | None = None
    length_m: float | None = None
    beam_m: float | None = None
    deadweight_tons: float | None = None
    cargo_inference: str | None = None
    cargo_inference_confidence: float | None = None
    cargo_inference_caveat: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeAisPositionRecord:
    position_id: str
    vessel_id: str
    mmsi: str
    timestamp: datetime
    latitude: float
    longitude: float
    speed_knots: float | None = None
    course_degrees: float | None = None
    heading_degrees: float | None = None
    navigation_status: str | None = None
    destination: str | None = None
    draught_m: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeTrackSnippet:
    track_id: str
    vessel_id: str
    label: str
    start_port_id: str | None = None
    end_port_id: str | None = None
    chokepoint_ids: list[str] = field(default_factory=list)
    points: list[MaritimeAisPositionRecord] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimePortRecord:
    port_id: str
    name: str
    country: str
    region: str
    latitude: float
    longitude: float
    unlocode: str | None = None
    terminal_type: str | None = None
    commodity_links: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeBoundingBox:
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    def contains(self, latitude: float, longitude: float) -> bool:
        return (
            self.min_latitude <= latitude <= self.max_latitude
            and self.min_longitude <= longitude <= self.max_longitude
        )


@dataclass(frozen=True)
class MaritimeChokepointDefinition:
    chokepoint_id: str
    name: str
    region: str
    latitude: float
    longitude: float
    bounding_box: MaritimeBoundingBox
    strategic_commodities: list[str] = field(default_factory=list)
    description: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeChokepointSummary:
    chokepoint_id: str
    name: str
    region: str
    coverage_status: str
    total_vessel_count: int
    vessel_count_by_type: dict[str, int] = field(default_factory=dict)
    baseline_vessel_count: int | None = None
    congestion_score: float | None = None
    congestion_label: str = "unavailable"
    commodity_links: list[str] = field(default_factory=list)
    methodology: str | None = None
    caveats: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeFlowSummary:
    flow_id: str
    label: str
    vessel_type: str
    route_label: str
    coverage_status: str
    vessel_count: int
    affected_chokepoint_ids: list[str] = field(default_factory=list)
    inferred_commodity: str | None = None
    inference_confidence: float | None = None
    inference_caveat: str | None = None
    summary: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeEventWindow:
    event_id: str
    title: str
    event_type: str
    region: str
    start_at: datetime
    end_at: datetime
    summary: str
    linked_chokepoint_ids: list[str] = field(default_factory=list)
    linked_commodity_flows: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeFleetWatchlist:
    watchlist_id: str
    label: str
    description: str
    vessel_ids: list[str] = field(default_factory=list)
    vessel_type_filters: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeProviderSnapshot:
    coverage: MaritimeCoverageMetadata
    vessels: list[MaritimeVesselStaticRecord] = field(default_factory=list)
    positions: list[MaritimeAisPositionRecord] = field(default_factory=list)
    tracks: list[MaritimeTrackSnippet] = field(default_factory=list)
    ports: list[MaritimePortRecord] = field(default_factory=list)
    chokepoints: list[MaritimeChokepointDefinition] = field(default_factory=list)
    event_windows: list[MaritimeEventWindow] = field(default_factory=list)
    watchlists: list[MaritimeFleetWatchlist] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MaritimeWorkspaceResult:
    mode: str
    available_modes: list[str]
    coverage: MaritimeCoverageMetadata
    vessels: list[MaritimeVesselStaticRecord] = field(default_factory=list)
    positions: list[MaritimeAisPositionRecord] = field(default_factory=list)
    tracks: list[MaritimeTrackSnippet] = field(default_factory=list)
    ports: list[MaritimePortRecord] = field(default_factory=list)
    chokepoints: list[MaritimeChokepointDefinition] = field(default_factory=list)
    chokepoint_summaries: list[MaritimeChokepointSummary] = field(default_factory=list)
    flow_summaries: list[MaritimeFlowSummary] = field(default_factory=list)
    event_windows: list[MaritimeEventWindow] = field(default_factory=list)
    watchlists: list[MaritimeFleetWatchlist] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
