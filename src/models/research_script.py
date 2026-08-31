from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ResearchScriptLanguage = Literal["python"]
ResearchScriptStatus = Literal["draft", "active", "archived", "discarded"]
ResearchScriptAuthor = Literal["operator", "user"]
ResearchScriptRevisionStatus = Literal["canonical", "staged", "superseded", "rejected"]
ResearchScriptRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    "expired",
    "unavailable",
    "incomplete",
]
ResearchScriptOutputKind = Literal[
    "log",
    "error",
    "metric",
    "table",
    "image",
    "file",
    "summary",
    "warning",
]
ResearchScriptInputSourceKind = Literal["gamma_state", "provider", "user_upload"]
ResearchScriptMockScenario = Literal["success", "failed", "timed_out", "unavailable", "incomplete"]
ResearchScriptDataExportDomain = Literal["equity_history", "macro_series", "saved_research"]


@dataclass(frozen=True)
class ResearchScript:
    script_id: str
    session_id: str
    title: str
    language: ResearchScriptLanguage
    status: ResearchScriptStatus
    canonical_revision_id: str
    created_by: ResearchScriptAuthor
    created_at: datetime
    updated_at: datetime
    source_provider: str
    origin: str
    transformation_note: str | None
    contract_version: str = "research-script.v1"


@dataclass(frozen=True)
class ResearchScriptRevision:
    revision_id: str
    script_id: str
    revision_number: int
    source: str
    source_sha256: str
    created_by: ResearchScriptAuthor
    created_at: datetime
    parent_revision_id: str | None
    status: ResearchScriptRevisionStatus
    change_summary: str | None
    operator_run_id: str | None
    expected_parent_sha256: str | None
    contract_version: str = "research-script-revision.v1"


@dataclass(frozen=True)
class ResearchScriptInputFile:
    logical_filename: str
    media_type: str
    byte_size: int
    content_sha256: str
    gamma_object_id: str | None
    provider_id: str | None
    source_timestamp: datetime | None
    retrieved_at: datetime
    transformation_note: str | None
    source_kind: ResearchScriptInputSourceKind
    artifact_ref: str


@dataclass(frozen=True)
class ResearchScriptInputSnapshot:
    snapshot_id: str
    script_id: str
    created_at: datetime
    files: list[ResearchScriptInputFile] = field(default_factory=list)
    dataset_refs: list[dict[str, Any]] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest_sha256: str = ""
    total_bytes: int = 0
    source_provider: str = "gamma_research_script"
    origin: str = "research_script_service.input_snapshot"
    transformation_note: str | None = None
    contract_version: str = "research-script-input.v1"


@dataclass(frozen=True)
class ResearchScriptOutput:
    output_id: str
    kind: ResearchScriptOutputKind
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
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    filename: str | None = None
    alt_text: str | None = None
    source_provider: str = "gamma_mock_research_script_runtime"
    origin: str = "mock_research_script_runtime"
    transformation_note: str | None = None
    generated: bool = True
    contract_version: str = "research-script-output.v1"


@dataclass(frozen=True)
class ResearchScriptRun:
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
    provider_container_id: str | None
    provider_response_id: str | None
    status: ResearchScriptRunStatus
    started_at: datetime
    completed_at: datetime | None
    outputs: list[ResearchScriptOutput] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, int | float] = field(default_factory=dict)
    source_provider: str = "gamma_mock_research_script_runtime"
    origin: str = "research_script_service.run"
    transformation_note: str | None = None
    contract_version: str = "research-script-run.v1"


@dataclass(frozen=True)
class ResearchScriptCreateRequest:
    session_id: str
    title: str
    source: str
    created_by: ResearchScriptAuthor = "user"
    research_intent: str | None = None
    operator_run_id: str | None = None


@dataclass(frozen=True)
class ResearchScriptRevisionCreateRequest:
    source: str
    expected_parent_sha256: str
    created_by: ResearchScriptAuthor = "user"
    change_summary: str | None = None
    operator_run_id: str | None = None


@dataclass(frozen=True)
class ResearchScriptInputFileCreateRequest:
    logical_filename: str
    media_type: str
    content: bytes
    gamma_object_id: str | None = None
    provider_id: str | None = None
    source_timestamp: datetime | None = None
    retrieved_at: datetime | None = None
    transformation_note: str | None = None
    source_kind: ResearchScriptInputSourceKind = "user_upload"


@dataclass(frozen=True)
class ResearchScriptRunCreateRequest:
    revision_id: str | None = None
    input_snapshot_id: str | None = None
    input_files: list[ResearchScriptInputFileCreateRequest] = field(default_factory=list)
    dataset_refs: list[dict[str, Any]] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    runtime_scenario: ResearchScriptMockScenario = "success"


@dataclass(frozen=True)
class ResearchScriptDataExportRequest:
    domain: ResearchScriptDataExportDomain
    object_id: str
    logical_filename: str
    region: str | None = None
    timeframe: str | None = None
    lookback_days: int | None = None
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    additional_input_files: list[ResearchScriptInputFileCreateRequest] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchScriptRunComparison:
    base_run_id: str
    comparison_run_id: str
    same_revision: bool
    same_input_snapshot: bool
    status_changed: bool
    duration_delta_seconds: float | None
    input_token_delta: int | None
    output_token_delta: int | None
    output_count_delta: int
    warning_count_delta: int
    metric_deltas: list[dict[str, Any]] = field(default_factory=list)
    contract_version: str = "research-script-run-comparison.v1"


@dataclass(frozen=True)
class ResearchScriptStorageDiagnostics:
    script_count: int
    archived_script_count: int
    revision_count: int
    input_snapshot_count: int
    run_count: int
    retained_output_count: int
    retained_output_bytes: int
    missing_output_count: int
    orphan_output_count: int
    storage_warnings: list[str] = field(default_factory=list)
    contract_version: str = "research-script-storage-diagnostics.v1"


@dataclass(frozen=True)
class ResearchScriptDetail:
    script: ResearchScript
    revisions: list[ResearchScriptRevision]
