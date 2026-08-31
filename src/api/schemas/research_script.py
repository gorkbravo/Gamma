from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.research_script import (
    ResearchScript,
    ResearchScriptCreateRequest,
    ResearchScriptDataExportRequest,
    ResearchScriptDetail,
    ResearchScriptInputFile,
    ResearchScriptInputFileCreateRequest,
    ResearchScriptOutput,
    ResearchScriptRevision,
    ResearchScriptRevisionCreateRequest,
    ResearchScriptRun,
    ResearchScriptRunComparison,
    ResearchScriptRunCreateRequest,
    ResearchScriptStorageDiagnostics,
)
from src.services.research_script_runtime import ResearchScriptRuntimeCapabilities


class ResearchScriptCreateRequestModel(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1)
    created_by: Literal["user"] = "user"

    def to_domain(self) -> ResearchScriptCreateRequest:
        return ResearchScriptCreateRequest(
            session_id=self.session_id,
            title=self.title,
            source=self.source,
            created_by=self.created_by,
        )


class ResearchScriptRevisionCreateRequestModel(BaseModel):
    source: str = Field(min_length=1)
    expected_parent_sha256: str = Field(min_length=64, max_length=64)
    change_summary: str | None = Field(default=None, max_length=512)
    created_by: Literal["user"] = "user"

    def to_domain(self) -> ResearchScriptRevisionCreateRequest:
        return ResearchScriptRevisionCreateRequest(
            source=self.source,
            expected_parent_sha256=self.expected_parent_sha256,
            created_by=self.created_by,
            change_summary=self.change_summary,
        )


class ResearchScriptRevisionDecisionRequestModel(BaseModel):
    expected_parent_sha256: str = Field(min_length=64, max_length=64)


class ResearchScriptInputFileCreateRequestModel(BaseModel):
    logical_filename: str = Field(min_length=1, max_length=128)
    media_type: str = Field(default="text/plain", min_length=1, max_length=128)
    content: str = ""
    gamma_object_id: str | None = Field(default=None, max_length=128)
    provider_id: str | None = Field(default=None, max_length=128)
    source_timestamp: datetime | None = None
    retrieved_at: datetime | None = None
    transformation_note: str | None = Field(default=None, max_length=512)
    source_kind: Literal["gamma_state", "provider", "user_upload"] = "user_upload"

    def to_domain(self) -> ResearchScriptInputFileCreateRequest:
        return ResearchScriptInputFileCreateRequest(
            logical_filename=self.logical_filename,
            media_type=self.media_type,
            content=self.content.encode("utf-8"),
            gamma_object_id=self.gamma_object_id,
            provider_id=self.provider_id,
            source_timestamp=self.source_timestamp,
            retrieved_at=self.retrieved_at,
            transformation_note=self.transformation_note,
            source_kind=self.source_kind,
        )


class ResearchScriptRunCreateRequestModel(BaseModel):
    revision_id: str | None = Field(default=None, max_length=128)
    input_snapshot_id: str | None = Field(default=None, max_length=128)
    input_files: list[ResearchScriptInputFileCreateRequestModel] = Field(default_factory=list)
    dataset_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    runtime_scenario: Literal["success", "failed", "timed_out", "unavailable", "incomplete"] = "success"

    def to_domain(self) -> ResearchScriptRunCreateRequest:
        return ResearchScriptRunCreateRequest(
            revision_id=self.revision_id,
            input_snapshot_id=self.input_snapshot_id,
            input_files=[item.to_domain() for item in self.input_files],
            dataset_refs=[dict(item) for item in self.dataset_refs],
            source_refs=[dict(item) for item in self.source_refs],
            runtime_scenario=self.runtime_scenario,
        )


class ResearchScriptDataExportRequestModel(BaseModel):
    domain: Literal["equity_history", "macro_series", "saved_research"]
    object_id: str = Field(min_length=1, max_length=128)
    logical_filename: str = Field(min_length=1, max_length=128)
    region: str | None = Field(default=None, max_length=32)
    timeframe: str | None = Field(default=None, max_length=16)
    lookback_days: int | None = Field(default=None, ge=20, le=3650)
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    additional_input_files: list[ResearchScriptInputFileCreateRequestModel] = Field(default_factory=list)

    def to_domain(self) -> ResearchScriptDataExportRequest:
        return ResearchScriptDataExportRequest(
            domain=self.domain,
            object_id=self.object_id,
            logical_filename=self.logical_filename,
            region=self.region,
            timeframe=self.timeframe,
            lookback_days=self.lookback_days,
            frequency=self.frequency,
            additional_input_files=[item.to_domain() for item in self.additional_input_files],
        )


class ResearchScriptDuplicateRequestModel(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)


class ResearchScriptModel(BaseModel):
    script_id: str
    session_id: str
    title: str
    language: Literal["python"]
    status: Literal["draft", "active", "archived", "discarded"]
    canonical_revision_id: str
    created_by: Literal["operator", "user"]
    created_at: datetime
    updated_at: datetime
    source_provider: str
    origin: str
    transformation_note: str | None = None
    contract_version: str

    @classmethod
    def from_domain(cls, value: ResearchScript) -> "ResearchScriptModel":
        return cls(**value.__dict__)


class ResearchScriptRevisionModel(BaseModel):
    revision_id: str
    script_id: str
    revision_number: int
    source: str
    source_sha256: str
    created_by: Literal["operator", "user"]
    created_at: datetime
    parent_revision_id: str | None = None
    status: Literal["canonical", "staged", "superseded", "rejected"]
    change_summary: str | None = None
    operator_run_id: str | None = None
    expected_parent_sha256: str | None = None
    contract_version: str

    @classmethod
    def from_domain(cls, value: ResearchScriptRevision) -> "ResearchScriptRevisionModel":
        return cls(**value.__dict__)


class ResearchScriptDetailModel(BaseModel):
    script: ResearchScriptModel
    revisions: list[ResearchScriptRevisionModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, value: ResearchScriptDetail) -> "ResearchScriptDetailModel":
        return cls(
            script=ResearchScriptModel.from_domain(value.script),
            revisions=[ResearchScriptRevisionModel.from_domain(item) for item in value.revisions],
        )


class ResearchScriptListResponseModel(BaseModel):
    items: list[ResearchScriptModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, values: list[ResearchScript]) -> "ResearchScriptListResponseModel":
        return cls(items=[ResearchScriptModel.from_domain(item) for item in values])


class ResearchScriptInputFileModel(BaseModel):
    logical_filename: str
    media_type: str
    byte_size: int
    content_sha256: str
    gamma_object_id: str | None = None
    provider_id: str | None = None
    source_timestamp: datetime | None = None
    retrieved_at: datetime
    transformation_note: str | None = None
    source_kind: Literal["gamma_state", "provider", "user_upload"]
    artifact_ref: str

    @classmethod
    def from_domain(cls, value: ResearchScriptInputFile) -> "ResearchScriptInputFileModel":
        return cls(**value.__dict__)


class ResearchScriptInputSnapshotModel(BaseModel):
    snapshot_id: str
    script_id: str
    created_at: datetime
    files: list[ResearchScriptInputFileModel] = Field(default_factory=list)
    dataset_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manifest_sha256: str
    total_bytes: int
    source_provider: str
    origin: str
    transformation_note: str | None = None
    contract_version: str

    @classmethod
    def from_domain(cls, value) -> "ResearchScriptInputSnapshotModel":
        payload = dict(value.__dict__)
        payload["files"] = [ResearchScriptInputFileModel.from_domain(item) for item in value.files]
        return cls(**payload)


class ResearchScriptOutputModel(BaseModel):
    output_id: str
    kind: Literal["log", "error", "metric", "table", "image", "file", "summary", "warning"]
    sequence: int
    media_type: str
    byte_size: int
    created_at: datetime
    artifact_ref: str | None = None
    provider_native_ref: str | None = None
    text: str | None = None
    metric_name: str | None = None
    metric_value: float | int | str | None = None
    unit: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    filename: str | None = None
    alt_text: str | None = None
    source_provider: str
    origin: str
    transformation_note: str | None = None
    generated: bool
    contract_version: str

    @classmethod
    def from_domain(cls, value: ResearchScriptOutput) -> "ResearchScriptOutputModel":
        return cls(**value.__dict__)


class ResearchScriptRunModel(BaseModel):
    run_id: str
    script_id: str
    revision_id: str
    source_sha256: str
    input_snapshot_id: str
    input_manifest_sha256: str
    input_file_count: int
    input_total_bytes: int
    runtime_provider: str
    runtime_kind: str
    provider_container_id: str | None = None
    provider_response_id: str | None = None
    status: Literal[
        "queued", "running", "completed", "failed", "cancelled", "timed_out", "expired", "unavailable", "incomplete"
    ]
    started_at: datetime
    completed_at: datetime | None = None
    outputs: list[ResearchScriptOutputModel] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    limits: dict[str, int | float] = Field(default_factory=dict)
    source_provider: str
    origin: str
    transformation_note: str | None = None
    contract_version: str

    @classmethod
    def from_domain(cls, value: ResearchScriptRun) -> "ResearchScriptRunModel":
        payload = dict(value.__dict__)
        payload["outputs"] = [ResearchScriptOutputModel.from_domain(item) for item in value.outputs]
        return cls(**payload)


class ResearchScriptRunListResponseModel(BaseModel):
    items: list[ResearchScriptRunModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, values: list[ResearchScriptRun]) -> "ResearchScriptRunListResponseModel":
        return cls(items=[ResearchScriptRunModel.from_domain(item) for item in values])


class ResearchScriptRuntimeCapabilitiesModel(BaseModel):
    configured_runtime: str
    provider: str
    runtime_kind: str
    available: bool
    executes_source: bool
    network_access: bool
    supported_output_types: list[str] = Field(default_factory=list)
    supports_cancellation: bool
    max_duration_seconds: int
    active_limits: dict[str, int | float] = Field(default_factory=dict)
    model: str | None = None
    sanitized_provider_status: str

    @classmethod
    def from_domain(
        cls,
        value: ResearchScriptRuntimeCapabilities,
    ) -> "ResearchScriptRuntimeCapabilitiesModel":
        payload = dict(value.__dict__)
        payload["supported_output_types"] = list(value.supported_output_types)
        return cls(**payload)


class ResearchScriptRunComparisonModel(BaseModel):
    base_run_id: str
    comparison_run_id: str
    same_revision: bool
    same_input_snapshot: bool
    status_changed: bool
    duration_delta_seconds: float | None = None
    input_token_delta: int | None = None
    output_token_delta: int | None = None
    output_count_delta: int
    warning_count_delta: int
    metric_deltas: list[dict[str, Any]] = Field(default_factory=list)
    contract_version: str

    @classmethod
    def from_domain(cls, value: ResearchScriptRunComparison) -> "ResearchScriptRunComparisonModel":
        return cls(**value.__dict__)


class ResearchScriptStorageDiagnosticsModel(BaseModel):
    script_count: int
    archived_script_count: int
    revision_count: int
    input_snapshot_count: int
    run_count: int
    retained_output_count: int
    retained_output_bytes: int
    missing_output_count: int
    orphan_output_count: int
    storage_warnings: list[str] = Field(default_factory=list)
    contract_version: str

    @classmethod
    def from_domain(cls, value: ResearchScriptStorageDiagnostics) -> "ResearchScriptStorageDiagnosticsModel":
        return cls(**value.__dict__)
