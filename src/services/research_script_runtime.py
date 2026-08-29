from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from src.models.research_script import ResearchScriptMockScenario, ResearchScriptRunStatus


@dataclass(frozen=True)
class ResearchScriptRuntimeCapabilities:
    configured_runtime: str
    provider: str
    runtime_kind: str
    available: bool
    executes_source: bool
    network_access: bool
    supported_output_types: tuple[str, ...]
    supports_cancellation: bool
    max_duration_seconds: int
    active_limits: dict[str, int | float] = field(default_factory=dict)
    model: str | None = None
    sanitized_provider_status: str = "available"


@dataclass(frozen=True)
class ResearchScriptRuntimeInputFile:
    logical_filename: str
    media_type: str
    content_sha256: str
    content: bytes


@dataclass(frozen=True)
class ResearchScriptRuntimeRequest:
    run_id: str
    script_id: str
    revision_id: str
    source: str
    source_sha256: str
    input_snapshot_id: str
    input_manifest_sha256: str
    input_manifest: dict[str, Any]
    input_files: list[ResearchScriptRuntimeInputFile]
    limits: dict[str, int | float]
    started_at: datetime
    scenario: ResearchScriptMockScenario = "success"


@dataclass(frozen=True)
class ResearchScriptRuntimeOutput:
    output_id: str
    kind: str
    sequence: int
    media_type: str
    text: str | None = None
    metric_name: str | None = None
    metric_value: float | int | str | None = None
    unit: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    filename: str | None = None
    alt_text: str | None = None
    provider_native_ref: str | None = None
    artifact_bytes: bytes | None = None
    transformation_note: str | None = None


@dataclass(frozen=True)
class ResearchScriptRuntimeResult:
    status: ResearchScriptRunStatus
    executed_source_sha256: str | None
    provider_container_id: str | None
    provider_response_id: str | None
    outputs: list[ResearchScriptRuntimeOutput]
    warnings: list[str]
    usage: dict[str, Any]
    completed_at: datetime


@dataclass(frozen=True)
class ResearchScriptRuntimeCancelResult:
    cancelled: bool
    status: ResearchScriptRunStatus
    message: str


class ResearchScriptRuntime(Protocol):
    def capabilities(self) -> ResearchScriptRuntimeCapabilities: ...

    def start_run(self, request: ResearchScriptRuntimeRequest) -> ResearchScriptRuntimeResult: ...

    def cancel_run(self, provider_run_id: str) -> ResearchScriptRuntimeCancelResult: ...

    def collect_outputs(self, result: ResearchScriptRuntimeResult) -> list[ResearchScriptRuntimeOutput]: ...


class MockResearchScriptRuntime:
    """Deterministic safe-preview adapter. It never imports or executes the supplied source."""

    PROVIDER = "gamma_mock_research_script_runtime"
    RUNTIME_KIND = "mock_safe_preview"

    def capabilities(self) -> ResearchScriptRuntimeCapabilities:
        return ResearchScriptRuntimeCapabilities(
            configured_runtime="mock",
            provider=self.PROVIDER,
            runtime_kind=self.RUNTIME_KIND,
            available=True,
            executes_source=False,
            network_access=False,
            supported_output_types=("log", "metric", "table", "image", "file", "warning", "error"),
            supports_cancellation=False,
            max_duration_seconds=0,
            active_limits={"provider_requests": 0},
            model=None,
            sanitized_provider_status="offline_safe_preview",
        )

    def start_run(self, request: ResearchScriptRuntimeRequest) -> ResearchScriptRuntimeResult:
        response_id = (
            f"mock-{request.source_sha256[:12]}-{request.input_manifest_sha256[:8]}-{request.scenario}"
        )
        common_warning = (
            "Safe preview only: Gamma did not execute Python, open a network connection, or expose app state."
        )
        if request.scenario == "failed":
            outputs = [
                ResearchScriptRuntimeOutput(
                    output_id="output-001",
                    kind="error",
                    sequence=1,
                    media_type="text/plain",
                    text="Mock runtime fixture failure. No source code was executed.",
                    transformation_note="Deterministic failure fixture from the non-executing mock runtime.",
                )
            ]
            return self._result(request, "failed", response_id, outputs, [common_warning])
        if request.scenario == "timed_out":
            outputs = [
                ResearchScriptRuntimeOutput(
                    output_id="output-001",
                    kind="error",
                    sequence=1,
                    media_type="text/plain",
                    text="Mock runtime timed-out fixture. No source code was executed.",
                    transformation_note="Deterministic timeout fixture from the non-executing mock runtime.",
                )
            ]
            return self._result(request, "timed_out", response_id, outputs, [common_warning])
        if request.scenario == "unavailable":
            return self._result(
                request,
                "unavailable",
                response_id,
                [],
                [common_warning, "Mock runtime unavailable fixture."],
            )

        hash_prefix = request.source_sha256[:12]
        manifest_prefix = request.input_manifest_sha256[:12]
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="180" viewBox="0 0 640 180">'
            '<rect width="640" height="180" fill="#070809"/>'
            '<path d="M24 142 L124 118 L224 126 L324 82 L424 94 L524 42 L616 58" '
            'fill="none" stroke="#7aa6c8" stroke-width="3"/>'
            '<text x="24" y="28" fill="#c2c8d0" font-family="monospace" font-size="14">'
            f"SAFE PREVIEW {html.escape(hash_prefix)}</text>"
            '</svg>'
        ).encode("utf-8")
        manifest_artifact = json.dumps(
            {
                "source_sha256": request.source_sha256,
                "input_manifest_sha256": request.input_manifest_sha256,
                "input_file_count": len(request.input_files),
                "executed": False,
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        outputs = [
            ResearchScriptRuntimeOutput(
                output_id="output-001",
                kind="log",
                sequence=1,
                media_type="text/plain",
                text=f"Validated immutable revision {hash_prefix}; safe preview generated without executing source.",
                transformation_note="Deterministic safe-preview log derived from immutable request metadata.",
            ),
            ResearchScriptRuntimeOutput(
                output_id="output-002",
                kind="metric",
                sequence=2,
                media_type="application/json",
                metric_name="Source bytes",
                metric_value=len(request.source.encode("utf-8")),
                unit="bytes",
                transformation_note="Measured from the submitted immutable source text without execution.",
            ),
            ResearchScriptRuntimeOutput(
                output_id="output-003",
                kind="table",
                sequence=3,
                media_type="application/json",
                columns=["field", "value"],
                rows=[
                    {"field": "source_sha256", "value": request.source_sha256},
                    {"field": "input_manifest_sha256", "value": request.input_manifest_sha256},
                    {"field": "input_files", "value": len(request.input_files)},
                    {"field": "executed", "value": False},
                ],
                transformation_note="Deterministic table derived from the immutable run request.",
            ),
            ResearchScriptRuntimeOutput(
                output_id="output-004",
                kind="image",
                sequence=4,
                media_type="image/svg+xml",
                filename="safe-preview.svg",
                alt_text="Deterministic safe-preview research chart placeholder",
                artifact_bytes=svg,
                transformation_note="Generated mock chart placeholder; it is not the result of Python execution.",
            ),
            ResearchScriptRuntimeOutput(
                output_id="output-005",
                kind="file",
                sequence=5,
                media_type="application/json",
                filename="safe-preview-manifest.json",
                artifact_bytes=manifest_artifact,
                transformation_note="Generated mock artifact containing immutable run identities only.",
            ),
            ResearchScriptRuntimeOutput(
                output_id="output-006",
                kind="warning",
                sequence=6,
                media_type="text/plain",
                text=common_warning,
                transformation_note="Runtime safety disclosure.",
            ),
        ]
        executed_hash = None if request.scenario == "incomplete" else request.source_sha256
        status: ResearchScriptRunStatus = "incomplete" if request.scenario == "incomplete" else "completed"
        warnings = [common_warning]
        if request.scenario == "incomplete":
            warnings.append("Mock incomplete fixture omitted exact-source association.")
        return ResearchScriptRuntimeResult(
            status=status,
            executed_source_sha256=executed_hash,
            provider_container_id=None,
            provider_response_id=response_id,
            outputs=outputs,
            warnings=warnings,
            usage={
                "provider_requests": 0,
                "executed_code": False,
                "network_access": False,
                "input_files": len(request.input_files),
                "source_hash_prefix": hash_prefix,
                "manifest_hash_prefix": manifest_prefix,
            },
            completed_at=request.started_at,
        )

    def cancel_run(self, provider_run_id: str) -> ResearchScriptRuntimeCancelResult:
        return ResearchScriptRuntimeCancelResult(
            cancelled=False,
            status="completed",
            message="Mock safe-preview runs are synchronous and cannot be cancelled.",
        )

    def collect_outputs(self, result: ResearchScriptRuntimeResult) -> list[ResearchScriptRuntimeOutput]:
        return list(result.outputs)

    @staticmethod
    def _result(
        request: ResearchScriptRuntimeRequest,
        status: ResearchScriptRunStatus,
        response_id: str,
        outputs: list[ResearchScriptRuntimeOutput],
        warnings: list[str],
    ) -> ResearchScriptRuntimeResult:
        return ResearchScriptRuntimeResult(
            status=status,
            executed_source_sha256=request.source_sha256,
            provider_container_id=None,
            provider_response_id=response_id,
            outputs=outputs,
            warnings=warnings,
            usage={"provider_requests": 0, "executed_code": False, "network_access": False},
            completed_at=request.started_at,
        )
