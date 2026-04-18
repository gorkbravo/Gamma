from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.maritime import (
    MaritimeAisPositionRecord,
    MaritimeBoundingBox,
    MaritimeChokepointDefinition,
    MaritimeChokepointSummary,
    MaritimeCoverageMetadata,
    MaritimeEventWindow,
    MaritimeFleetWatchlist,
    MaritimeFlowSummary,
    MaritimePortRecord,
    MaritimeTrackSnippet,
    MaritimeVesselIdentity,
    MaritimeVesselStaticRecord,
    MaritimeWorkspaceResult,
)


class MaritimeCoverageMetadataModel(BaseModel):
    coverage_status: str
    provider_id: str
    provider_label: str
    freshness_label: str
    regions: list[str] = Field(default_factory=list)
    as_of: datetime | None = None
    source_timestamp: datetime | None = None
    caveats: list[str] = Field(default_factory=list)
    credential_env_vars: list[str] = Field(default_factory=list)
    supports_live: bool = False
    supports_historical: bool = False
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeCoverageMetadata) -> "MaritimeCoverageMetadataModel":
        return cls(**row.__dict__)


class MaritimeVesselIdentityModel(BaseModel):
    vessel_id: str
    mmsi: str
    imo: str | None = None
    callsign: str | None = None
    normalized_id: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeVesselIdentity) -> "MaritimeVesselIdentityModel":
        return cls(**row.__dict__)


class MaritimeVesselStaticModel(BaseModel):
    vessel_id: str
    name: str
    identity: MaritimeVesselIdentityModel
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
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeVesselStaticRecord) -> "MaritimeVesselStaticModel":
        return cls(
            **{
                **row.__dict__,
                "identity": MaritimeVesselIdentityModel.from_domain(row.identity),
            }
        )


class MaritimeAisPositionModel(BaseModel):
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
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeAisPositionRecord) -> "MaritimeAisPositionModel":
        return cls(**row.__dict__)


class MaritimeTrackSnippetModel(BaseModel):
    track_id: str
    vessel_id: str
    label: str
    start_port_id: str | None = None
    end_port_id: str | None = None
    chokepoint_ids: list[str] = Field(default_factory=list)
    points: list[MaritimeAisPositionModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeTrackSnippet) -> "MaritimeTrackSnippetModel":
        return cls(
            **{
                **row.__dict__,
                "points": [MaritimeAisPositionModel.from_domain(point) for point in row.points],
            }
        )


class MaritimePortModel(BaseModel):
    port_id: str
    name: str
    country: str
    region: str
    latitude: float
    longitude: float
    unlocode: str | None = None
    terminal_type: str | None = None
    commodity_links: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimePortRecord) -> "MaritimePortModel":
        return cls(**row.__dict__)


class MaritimeBoundingBoxModel(BaseModel):
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    @classmethod
    def from_domain(cls, row: MaritimeBoundingBox) -> "MaritimeBoundingBoxModel":
        return cls(**row.__dict__)


class MaritimeChokepointDefinitionModel(BaseModel):
    chokepoint_id: str
    name: str
    region: str
    latitude: float
    longitude: float
    bounding_box: MaritimeBoundingBoxModel
    strategic_commodities: list[str] = Field(default_factory=list)
    description: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeChokepointDefinition) -> "MaritimeChokepointDefinitionModel":
        return cls(
            **{
                **row.__dict__,
                "bounding_box": MaritimeBoundingBoxModel.from_domain(row.bounding_box),
            }
        )


class MaritimeChokepointSummaryModel(BaseModel):
    chokepoint_id: str
    name: str
    region: str
    coverage_status: str
    total_vessel_count: int
    vessel_count_by_type: dict[str, int] = Field(default_factory=dict)
    baseline_vessel_count: int | None = None
    congestion_score: float | None = None
    congestion_label: str
    commodity_links: list[str] = Field(default_factory=list)
    methodology: str | None = None
    caveats: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeChokepointSummary) -> "MaritimeChokepointSummaryModel":
        return cls(**row.__dict__)


class MaritimeFlowSummaryModel(BaseModel):
    flow_id: str
    label: str
    vessel_type: str
    route_label: str
    coverage_status: str
    vessel_count: int
    affected_chokepoint_ids: list[str] = Field(default_factory=list)
    inferred_commodity: str | None = None
    inference_confidence: float | None = None
    inference_caveat: str | None = None
    summary: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeFlowSummary) -> "MaritimeFlowSummaryModel":
        return cls(**row.__dict__)


class MaritimeEventWindowModel(BaseModel):
    event_id: str
    title: str
    event_type: str
    region: str
    start_at: datetime
    end_at: datetime
    summary: str
    linked_chokepoint_ids: list[str] = Field(default_factory=list)
    linked_commodity_flows: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeEventWindow) -> "MaritimeEventWindowModel":
        return cls(**row.__dict__)


class MaritimeFleetWatchlistModel(BaseModel):
    watchlist_id: str
    label: str
    description: str
    vessel_ids: list[str] = Field(default_factory=list)
    vessel_type_filters: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeFleetWatchlist) -> "MaritimeFleetWatchlistModel":
        return cls(**row.__dict__)


class MaritimeWorkspaceResponseModel(BaseModel):
    mode: str
    available_modes: list[str]
    coverage: MaritimeCoverageMetadataModel
    vessels: list[MaritimeVesselStaticModel] = Field(default_factory=list)
    positions: list[MaritimeAisPositionModel] = Field(default_factory=list)
    tracks: list[MaritimeTrackSnippetModel] = Field(default_factory=list)
    ports: list[MaritimePortModel] = Field(default_factory=list)
    chokepoints: list[MaritimeChokepointDefinitionModel] = Field(default_factory=list)
    chokepoint_summaries: list[MaritimeChokepointSummaryModel] = Field(default_factory=list)
    flow_summaries: list[MaritimeFlowSummaryModel] = Field(default_factory=list)
    event_windows: list[MaritimeEventWindowModel] = Field(default_factory=list)
    watchlists: list[MaritimeFleetWatchlistModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MaritimeWorkspaceResult) -> "MaritimeWorkspaceResponseModel":
        return cls(
            **{
                **row.__dict__,
                "coverage": MaritimeCoverageMetadataModel.from_domain(row.coverage),
                "vessels": [MaritimeVesselStaticModel.from_domain(item) for item in row.vessels],
                "positions": [MaritimeAisPositionModel.from_domain(item) for item in row.positions],
                "tracks": [MaritimeTrackSnippetModel.from_domain(item) for item in row.tracks],
                "ports": [MaritimePortModel.from_domain(item) for item in row.ports],
                "chokepoints": [MaritimeChokepointDefinitionModel.from_domain(item) for item in row.chokepoints],
                "chokepoint_summaries": [
                    MaritimeChokepointSummaryModel.from_domain(item) for item in row.chokepoint_summaries
                ],
                "flow_summaries": [MaritimeFlowSummaryModel.from_domain(item) for item in row.flow_summaries],
                "event_windows": [MaritimeEventWindowModel.from_domain(item) for item in row.event_windows],
                "watchlists": [MaritimeFleetWatchlistModel.from_domain(item) for item in row.watchlists],
            }
        )


class MaritimeTrackResponseModel(BaseModel):
    vessel_id: str
    track: MaritimeTrackSnippetModel | None = None
