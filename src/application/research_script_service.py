from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.application.request_limits import (
    MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS,
    MAX_RESEARCH_SCRIPT_CONCURRENT_RUNS_PER_SCRIPT,
    MAX_RESEARCH_SCRIPT_DATASET_REFS,
    MAX_RESEARCH_SCRIPT_FILENAME_CHARS,
    MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES,
    MAX_RESEARCH_SCRIPT_INLINE_TABLE_COLUMNS,
    MAX_RESEARCH_SCRIPT_INLINE_TABLE_ROWS,
    MAX_RESEARCH_SCRIPT_INLINE_TEXT_BYTES,
    MAX_RESEARCH_SCRIPT_INPUT_FILES,
    MAX_RESEARCH_SCRIPT_INPUT_MANIFEST_BYTES,
    MAX_RESEARCH_SCRIPT_OUTPUT_ARTIFACTS,
    MAX_RESEARCH_SCRIPT_PROVIDER_RETRIES,
    MAX_RESEARCH_SCRIPT_RUN_DURATION_SECONDS,
    MAX_RESEARCH_SCRIPT_RUN_HISTORY,
    MAX_RESEARCH_SCRIPT_SESSION_ID_CHARS,
    MAX_RESEARCH_SCRIPT_SOURCE_BYTES,
    MAX_RESEARCH_SCRIPT_SOURCE_REFS,
    MAX_RESEARCH_SCRIPT_TITLE_CHARS,
    MAX_RESEARCH_SCRIPT_TOTAL_INPUT_BYTES,
    MAX_RESEARCH_SCRIPT_TOTAL_OUTPUT_BYTES,
)
from src.models.research_script import (
    ResearchScript,
    ResearchScriptCreateRequest,
    ResearchScriptDataExportRequest,
    ResearchScriptDetail,
    ResearchScriptInputFile,
    ResearchScriptInputFileCreateRequest,
    ResearchScriptInputSnapshot,
    ResearchScriptOutput,
    ResearchScriptRevision,
    ResearchScriptRevisionCreateRequest,
    ResearchScriptRun,
    ResearchScriptRunComparison,
    ResearchScriptRunCreateRequest,
    ResearchScriptStorageDiagnostics,
)
from src.services.research_script_runtime import (
    ResearchScriptRuntime,
    ResearchScriptRuntimeCapabilities,
    ResearchScriptRuntimeInputFile,
    ResearchScriptRuntimeOutput,
    ResearchScriptRuntimeRequest,
)
from src.services.research_script_store import (
    ResearchScriptStore,
    ResearchScriptStoreConflictError,
    is_safe_research_script_filename,
)
from src.utils.time import now_utc


class ResearchScriptServiceError(RuntimeError):
    pass


class ResearchScriptNotFoundError(ResearchScriptServiceError):
    pass


class ResearchScriptConflictError(ResearchScriptServiceError):
    pass


class ResearchScriptValidationError(ResearchScriptServiceError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = list(dict.fromkeys(errors))
        super().__init__("; ".join(self.errors))


class ResearchScriptService:
    def __init__(
        self,
        store: ResearchScriptStore,
        runtime: ResearchScriptRuntime,
        *,
        research_provider: Any | None = None,
        research_service: Any | None = None,
        macro_service: Any | None = None,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.research_provider = research_provider
        self.research_service = research_service
        self.macro_service = macro_service

    @staticmethod
    def source_sha256(source: str) -> str:
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @staticmethod
    def manifest_sha256(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def limits() -> dict[str, int | float]:
        return {
            "source_bytes": MAX_RESEARCH_SCRIPT_SOURCE_BYTES,
            "input_files": MAX_RESEARCH_SCRIPT_INPUT_FILES,
            "individual_input_bytes": MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES,
            "total_input_bytes": MAX_RESEARCH_SCRIPT_TOTAL_INPUT_BYTES,
            "run_duration_seconds": MAX_RESEARCH_SCRIPT_RUN_DURATION_SECONDS,
            "inline_text_bytes": MAX_RESEARCH_SCRIPT_INLINE_TEXT_BYTES,
            "output_artifacts": MAX_RESEARCH_SCRIPT_OUTPUT_ARTIFACTS,
            "total_output_bytes": MAX_RESEARCH_SCRIPT_TOTAL_OUTPUT_BYTES,
            "inline_table_rows": MAX_RESEARCH_SCRIPT_INLINE_TABLE_ROWS,
            "inline_table_columns": MAX_RESEARCH_SCRIPT_INLINE_TABLE_COLUMNS,
            "concurrent_runs_per_script": MAX_RESEARCH_SCRIPT_CONCURRENT_RUNS_PER_SCRIPT,
            "provider_transport_retries": MAX_RESEARCH_SCRIPT_PROVIDER_RETRIES,
            "stored_run_history": MAX_RESEARCH_SCRIPT_RUN_HISTORY,
        }

    def capabilities(self) -> ResearchScriptRuntimeCapabilities:
        capabilities = self.runtime.capabilities()
        return replace(capabilities, active_limits={**self.limits(), **capabilities.active_limits})

    def create_script(
        self,
        request: ResearchScriptCreateRequest,
        *,
        _allow_operator: bool = False,
    ) -> ResearchScriptDetail:
        title = str(request.title or "").strip()
        session_id = str(request.session_id or "").strip()
        errors = self._validate_source(request.source)
        if not title:
            errors.append("Script title is required.")
        if len(title) > MAX_RESEARCH_SCRIPT_TITLE_CHARS:
            errors.append(f"Script title exceeds {MAX_RESEARCH_SCRIPT_TITLE_CHARS} characters.")
        if not session_id:
            errors.append("Session id is required.")
        if len(session_id) > MAX_RESEARCH_SCRIPT_SESSION_ID_CHARS:
            errors.append(f"Session id exceeds {MAX_RESEARCH_SCRIPT_SESSION_ID_CHARS} characters.")
        if request.created_by != "user" and not (
            _allow_operator and request.created_by == "operator"
        ):
            errors.append("Only user-authored script creation is allowed through this interface.")
        if errors:
            raise ResearchScriptValidationError(errors)

        created_at = now_utc()
        script_id = uuid4().hex
        revision_id = uuid4().hex
        source_hash = self.source_sha256(request.source)
        revision = ResearchScriptRevision(
            revision_id=revision_id,
            script_id=script_id,
            revision_number=1,
            source=request.source,
            source_sha256=source_hash,
            created_by=request.created_by,
            created_at=created_at,
            parent_revision_id=None,
            status="canonical",
            change_summary=(
                f"Initial Operator-authored Script draft: {str(request.research_intent or 'research workflow').strip()}"[
                    :MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS
                ]
                if request.created_by == "operator"
                else "Initial user-authored revision"
            ),
            operator_run_id=(
                str(request.operator_run_id or "").strip() or None
                if request.created_by == "operator"
                else None
            ),
            expected_parent_sha256=None,
        )
        script = ResearchScript(
            script_id=script_id,
            session_id=session_id,
            title=title,
            language="python",
            status="draft",
            canonical_revision_id=revision_id,
            created_by=request.created_by,
            created_at=created_at,
            updated_at=created_at,
            source_provider="gamma_operator" if request.created_by == "operator" else "gamma_user",
            origin=(
                "research_script_service.create_operator_draft"
                if request.created_by == "operator"
                else "research_script_service.create_script"
            ),
            transformation_note=(
                "Operator-drafted source persisted as the initial immutable canonical revision for a session-ephemeral Script."
                if request.created_by == "operator"
                else "User-authored source persisted as an immutable canonical revision."
            ),
        )
        try:
            self.store.create_script(script, revision)
        except ResearchScriptStoreConflictError as exc:
            raise ResearchScriptConflictError(str(exc)) from exc
        return ResearchScriptDetail(script=script, revisions=[revision])

    def list_scripts(self, *, include_archived: bool = False) -> list[ResearchScript]:
        scripts = self.store.list_scripts()
        if include_archived:
            return scripts
        return [item for item in scripts if item.status not in {"archived", "discarded"}]

    def get_script(self, script_id: str) -> ResearchScriptDetail:
        script = self.store.load_script(script_id)
        if script is None:
            raise ResearchScriptNotFoundError("Research script not found.")
        revisions = self.store.list_revisions(script.script_id)
        if not any(item.revision_id == script.canonical_revision_id for item in revisions):
            raise ResearchScriptServiceError("Research script canonical revision is unavailable.")
        return ResearchScriptDetail(script=script, revisions=revisions)

    def create_revision(
        self,
        script_id: str,
        request: ResearchScriptRevisionCreateRequest,
    ) -> ResearchScriptDetail:
        detail = self.get_script(script_id)
        if detail.script.status in {"archived", "discarded"}:
            raise ResearchScriptConflictError("Restore the archived script before creating a revision.")
        parent = next(
            item for item in detail.revisions if item.revision_id == detail.script.canonical_revision_id
        )
        errors = self._validate_source(request.source)
        expected_hash = str(request.expected_parent_sha256 or "").strip().lower()
        if not expected_hash:
            errors.append("expected_parent_sha256 is required for optimistic concurrency.")
        if request.created_by != "user":
            errors.append("Operator-authored revisions are deferred to Slice 4.")
        if request.change_summary and len(request.change_summary) > MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS:
            errors.append(
                f"Change summary exceeds {MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS} characters."
            )
        if errors:
            raise ResearchScriptValidationError(errors)
        if expected_hash != parent.source_sha256:
            raise ResearchScriptConflictError(
                "The canonical source changed. Reload the script before saving a new revision."
            )
        next_hash = self.source_sha256(request.source)
        if next_hash == parent.source_sha256:
            raise ResearchScriptValidationError(["The edited source is identical to the canonical revision."])
        created_at = now_utc()
        revision = ResearchScriptRevision(
            revision_id=uuid4().hex,
            script_id=detail.script.script_id,
            revision_number=parent.revision_number + 1,
            source=request.source,
            source_sha256=next_hash,
            created_by=request.created_by,
            created_at=created_at,
            parent_revision_id=parent.revision_id,
            status="canonical",
            change_summary=(str(request.change_summary).strip() if request.change_summary else None),
            operator_run_id=request.operator_run_id,
            expected_parent_sha256=expected_hash,
        )
        try:
            updated_script = self.store.append_canonical_revision(
                revision,
                expected_parent_sha256=expected_hash,
            )
        except ResearchScriptStoreConflictError as exc:
            raise ResearchScriptConflictError(str(exc)) from exc
        return self.get_script(updated_script.script_id)

    def create_operator_draft(
        self,
        *,
        session_id: str,
        title: str,
        research_intent: str,
        source: str,
        authorized_input_references: list[dict[str, Any]],
        operator_run_id: str,
        acquired_input_files: list[ResearchScriptInputFileCreateRequest] | None = None,
        acquisition_warnings: list[str] | None = None,
    ) -> tuple[ResearchScriptDetail, ResearchScriptInputSnapshot]:
        detail = self.create_script(
            ResearchScriptCreateRequest(
                session_id=session_id,
                title=title,
                source=source,
                created_by="operator",
                research_intent=research_intent,
                operator_run_id=operator_run_id,
            ),
            _allow_operator=True,
        )
        snapshot = self.create_authorized_input_snapshot(
            detail.script.script_id,
            authorized_input_references,
            acquired_input_files=acquired_input_files,
            acquisition_warnings=acquisition_warnings,
        )
        return detail, snapshot

    def create_authorized_input_snapshot(
        self,
        script_id: str,
        authorized_input_references: list[dict[str, Any]],
        *,
        acquired_input_files: list[ResearchScriptInputFileCreateRequest] | None = None,
        acquisition_warnings: list[str] | None = None,
    ) -> ResearchScriptInputSnapshot:
        self.get_script(script_id)
        references = self._validate_authorized_input_references(authorized_input_references)
        dataset_refs = [
            {
                "reference_id": item["reference_id"],
                "dataset_id": item["dataset_id"],
                "provider": item["provider"],
                "logical_filename": item["logical_filename"],
                "media_type": item["media_type"],
                "coverage_start": item["coverage_start"],
                "coverage_end": item["coverage_end"],
                "symbol": item["symbol"],
                "benchmark_symbol": item["benchmark_symbol"],
                "timeframe": item["timeframe"],
                "lookback_days": item["lookback_days"],
                "frequency": item["frequency"],
                "source_kind": item["source_kind"],
            }
            for item in references
        ]
        source_refs = [
            {
                "source_id": item["reference_id"],
                "provider": item["provider"],
                "coverage_start": item["coverage_start"],
                "coverage_end": item["coverage_end"],
                "symbol": item["symbol"],
                "benchmark_symbol": item["benchmark_symbol"],
                "timeframe": item["timeframe"],
            }
            for item in references
        ]
        warnings = list(acquisition_warnings or [])
        input_files = list(acquired_input_files or [])
        if references and not input_files:
            warnings.append(
                "Authorized input references were recorded, but bytes must be acquired by Gamma and copied into a bounded snapshot before data-dependent execution."
            )
        snapshot = self._create_input_snapshot(
            script_id,
            ResearchScriptRunCreateRequest(
                input_files=input_files,
                dataset_refs=dataset_refs,
                source_refs=source_refs,
            ),
            extra_warnings=warnings,
        )
        return snapshot

    def stage_operator_revision(
        self,
        script_id: str,
        *,
        source: str,
        expected_parent_sha256: str,
        change_summary: str | None,
        operator_run_id: str,
    ) -> ResearchScriptDetail:
        detail = self.get_script(script_id)
        parent = next(
            item for item in detail.revisions if item.revision_id == detail.script.canonical_revision_id
        )
        errors = self._validate_source(source)
        expected_hash = str(expected_parent_sha256 or "").strip().lower()
        if expected_hash != parent.source_sha256:
            raise ResearchScriptConflictError(
                "The canonical source changed before the Operator candidate could be staged."
            )
        if self.source_sha256(source) == parent.source_sha256:
            errors.append("The Operator candidate is identical to the canonical revision.")
        if change_summary and len(change_summary) > MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS:
            errors.append(
                f"Change summary exceeds {MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS} characters."
            )
        if errors:
            raise ResearchScriptValidationError(errors)
        revision = ResearchScriptRevision(
            revision_id=uuid4().hex,
            script_id=detail.script.script_id,
            revision_number=max(item.revision_number for item in detail.revisions) + 1,
            source=source,
            source_sha256=self.source_sha256(source),
            created_by="operator",
            created_at=now_utc(),
            parent_revision_id=parent.revision_id,
            status="staged",
            change_summary=str(change_summary or "Operator candidate revision").strip(),
            operator_run_id=str(operator_run_id or "").strip() or None,
            expected_parent_sha256=expected_hash,
        )
        try:
            self.store.append_staged_revision(
                revision,
                expected_parent_sha256=expected_hash,
            )
        except ResearchScriptStoreConflictError as exc:
            raise ResearchScriptConflictError(str(exc)) from exc
        return self.get_script(detail.script.script_id)

    def accept_staged_revision(
        self,
        script_id: str,
        revision_id: str,
        *,
        expected_parent_sha256: str,
    ) -> ResearchScriptDetail:
        return self._resolve_staged_revision(
            script_id,
            revision_id,
            expected_parent_sha256=expected_parent_sha256,
            accept=True,
        )

    def reject_staged_revision(
        self,
        script_id: str,
        revision_id: str,
        *,
        expected_parent_sha256: str,
    ) -> ResearchScriptDetail:
        return self._resolve_staged_revision(
            script_id,
            revision_id,
            expected_parent_sha256=expected_parent_sha256,
            accept=False,
        )

    def _resolve_staged_revision(
        self,
        script_id: str,
        revision_id: str,
        *,
        expected_parent_sha256: str,
        accept: bool,
    ) -> ResearchScriptDetail:
        self.get_script(script_id)
        try:
            self.store.resolve_staged_revision(
                script_id,
                revision_id,
                expected_parent_sha256=str(expected_parent_sha256 or "").strip().lower(),
                accept=accept,
            )
        except ResearchScriptStoreConflictError as exc:
            raise ResearchScriptConflictError(str(exc)) from exc
        return self.get_script(script_id)

    def create_exact_run(
        self,
        script_id: str,
        *,
        revision_id: str,
        input_snapshot_id: str,
        source_sha256: str,
        manifest_sha256: str,
    ) -> ResearchScriptRun:
        revision = self.store.load_revision(script_id, revision_id)
        snapshot = self.store.load_input_snapshot(input_snapshot_id)
        if revision is None or snapshot is None:
            raise ResearchScriptNotFoundError("Exact Script revision or input snapshot not found.")
        if revision.script_id != script_id or snapshot.script_id != script_id:
            raise ResearchScriptValidationError(
                ["Exact Script revision and input snapshot must belong to the requested script."]
            )
        if revision.source_sha256 != str(source_sha256 or "").strip().lower():
            raise ResearchScriptConflictError("Requested source hash does not match the immutable revision.")
        if snapshot.manifest_sha256 != str(manifest_sha256 or "").strip().lower():
            raise ResearchScriptConflictError("Requested manifest hash does not match the immutable input snapshot.")
        return self.create_run(
            script_id,
            ResearchScriptRunCreateRequest(
                revision_id=revision_id,
                input_snapshot_id=input_snapshot_id,
            ),
        )

    def create_run(self, script_id: str, request: ResearchScriptRunCreateRequest) -> ResearchScriptRun:
        detail = self.get_script(script_id)
        if detail.script.status in {"archived", "discarded"}:
            raise ResearchScriptConflictError("Restore the archived script before creating a run.")
        revision_id = request.revision_id or detail.script.canonical_revision_id
        revision = self.store.load_revision(detail.script.script_id, revision_id)
        if revision is None:
            raise ResearchScriptNotFoundError("Research script revision not found.")
        if revision.script_id != detail.script.script_id:
            raise ResearchScriptValidationError(["Revision does not belong to the requested script."])
        if revision.status in {"staged", "rejected"}:
            raise ResearchScriptValidationError(
                ["A staged or rejected Operator revision cannot run as canonical source. Accept it first."]
            )
        computed_source_hash = self.source_sha256(revision.source)
        if computed_source_hash != revision.source_sha256:
            raise ResearchScriptServiceError("Persisted revision source hash does not match its source text.")
        if request.input_snapshot_id and (request.input_files or request.dataset_refs or request.source_refs):
            raise ResearchScriptValidationError(
                ["Use either input_snapshot_id or new input files/references, not both."]
            )
        if request.input_snapshot_id:
            snapshot = self.store.load_input_snapshot(request.input_snapshot_id)
            if snapshot is None:
                raise ResearchScriptNotFoundError("Research script input snapshot not found.")
            if snapshot.script_id != detail.script.script_id:
                raise ResearchScriptValidationError(["Input snapshot does not belong to the requested script."])
        else:
            snapshot = self._create_input_snapshot(detail.script.script_id, request)

        input_contents = self.store.load_input_contents(snapshot)
        input_manifest = self._input_manifest_identity(snapshot)
        computed_manifest_hash = self.manifest_sha256(input_manifest)
        if computed_manifest_hash != snapshot.manifest_sha256:
            raise ResearchScriptServiceError(
                "Persisted input manifest hash does not match the immutable snapshot."
            )
        started_at = now_utc()
        run_id = uuid4().hex
        runtime_request = ResearchScriptRuntimeRequest(
            run_id=run_id,
            script_id=detail.script.script_id,
            revision_id=revision.revision_id,
            source=revision.source,
            source_sha256=revision.source_sha256,
            input_snapshot_id=snapshot.snapshot_id,
            input_manifest_sha256=snapshot.manifest_sha256,
            input_manifest=input_manifest,
            input_files=[
                ResearchScriptRuntimeInputFile(
                    logical_filename=item.logical_filename,
                    media_type=item.media_type,
                    content_sha256=item.content_sha256,
                    content=input_contents[item.logical_filename],
                )
                for item in snapshot.files
            ],
            limits=self.limits(),
            started_at=started_at,
            scenario=request.runtime_scenario,
        )
        result = self.runtime.start_run(runtime_request)
        capabilities = self.capabilities()
        run_warnings = list(dict.fromkeys([*snapshot.warnings, *result.warnings]))
        runtime_outputs = self.runtime.collect_outputs(result)
        if result.executed_source_sha256 != revision.source_sha256:
            run_warnings.append(
                "Exact-source association was not established; this run is incomplete and is not "
                "presented as output of the visible revision."
            )
            result = replace(result, status="incomplete")
            runtime_outputs = [
                ResearchScriptRuntimeOutput(
                    output_id="output-source-association-error",
                    kind="error",
                    sequence=1,
                    media_type="text/plain",
                    text=(
                        "The runtime did not confirm the exact source SHA-256. "
                        "Gamma withheld provider outputs from this incomplete run."
                    ),
                    transformation_note="Gamma-generated exact-source safety error; provider outputs were withheld.",
                )
            ]

        try:
            outputs, artifacts, output_warnings = self._normalize_outputs(
                run_id,
                runtime_outputs,
                result.completed_at,
                source_provider=capabilities.provider,
                origin=f"{capabilities.runtime_kind}.collect_outputs",
            )
            run_warnings.extend(output_warnings)
            status = result.status
        except ResearchScriptValidationError as exc:
            outputs = [
                ResearchScriptOutput(
                    output_id="output-validation-error",
                    kind="error",
                    sequence=1,
                    media_type="text/plain",
                    byte_size=len(str(exc).encode("utf-8")),
                    created_at=result.completed_at,
                    text=str(exc),
                    source_provider=capabilities.provider,
                    origin="research_script_service.normalize_outputs",
                    transformation_note="Gamma rejected runtime output that exceeded the retained-output contract.",
                )
            ]
            artifacts = {}
            run_warnings.extend(exc.errors)
            status = "failed"

        run = ResearchScriptRun(
            run_id=run_id,
            script_id=detail.script.script_id,
            revision_id=revision.revision_id,
            source_sha256=revision.source_sha256,
            input_snapshot_id=snapshot.snapshot_id,
            input_manifest_sha256=snapshot.manifest_sha256,
            input_file_count=len(snapshot.files),
            input_total_bytes=snapshot.total_bytes,
            runtime_provider=capabilities.provider,
            runtime_kind=capabilities.runtime_kind,
            provider_container_id=result.provider_container_id,
            provider_response_id=result.provider_response_id,
            status=status,
            started_at=started_at,
            completed_at=result.completed_at,
            outputs=outputs,
            source_refs=list(snapshot.source_refs),
            warnings=list(dict.fromkeys(run_warnings)),
            usage={
                **dict(result.usage),
                **self._estimated_token_cost(result.usage, capabilities.model),
                "executes_source": capabilities.executes_source,
                "network_access": capabilities.network_access,
            },
            limits=self.limits(),
            source_provider=capabilities.provider,
            origin="research_script_service.create_run",
            transformation_note=(
                "Normalized deterministic mock outputs; source was hashed and persisted but not executed."
                if capabilities.executes_source is False
                else "Normalized provider runtime outputs for the immutable source and input snapshot."
            ),
        )
        try:
            self.store.create_run(run, artifacts)
        except ResearchScriptStoreConflictError as exc:
            raise ResearchScriptConflictError(str(exc)) from exc
        return run

    def list_runs(self, script_id: str) -> list[ResearchScriptRun]:
        if self.store.load_script(script_id) is None:
            raise ResearchScriptNotFoundError("Research script not found.")
        return self.store.list_runs(script_id)

    def get_run(self, run_id: str) -> ResearchScriptRun:
        run = self.store.load_run(run_id)
        if run is None:
            raise ResearchScriptNotFoundError("Research script run not found.")
        return run

    def get_output_artifact(self, run_id: str, output_id: str) -> tuple[str, str, bytes]:
        run = self.get_run(run_id)
        output = next((item for item in run.outputs if item.output_id == output_id), None)
        if output is None or not output.artifact_ref or not output.filename:
            raise ResearchScriptNotFoundError("Research script output artifact not found.")
        content = self.store.load_output_artifact(run.run_id, output.output_id, output.filename)
        if content is None:
            raise ResearchScriptNotFoundError("Retained research script artifact is unavailable.")
        if len(content) != output.byte_size:
            raise ResearchScriptServiceError("Retained research script artifact size does not match metadata.")
        return output.filename, output.media_type, content

    def get_input_snapshot(self, snapshot_id: str) -> ResearchScriptInputSnapshot:
        snapshot = self.store.load_input_snapshot(snapshot_id)
        if snapshot is None:
            raise ResearchScriptNotFoundError("Research script input snapshot not found.")
        self.store.load_input_contents(snapshot)
        return snapshot

    def duplicate_script(self, script_id: str, *, title: str | None = None) -> ResearchScriptDetail:
        detail = self.get_script(script_id)
        canonical = next(
            item for item in detail.revisions if item.revision_id == detail.script.canonical_revision_id
        )
        duplicate_title = str(title or f"{detail.script.title} copy").strip()
        return self.create_script(
            ResearchScriptCreateRequest(
                session_id=detail.script.session_id,
                title=duplicate_title,
                source=canonical.source,
                created_by="user",
            )
        )

    def archive_script(self, script_id: str) -> ResearchScriptDetail:
        try:
            self.store.set_script_status(script_id, "archived")
        except ResearchScriptStoreConflictError as exc:
            if self.store.load_script(script_id) is None:
                raise ResearchScriptNotFoundError("Research script not found.") from exc
            raise ResearchScriptConflictError(str(exc)) from exc
        return self.get_script(script_id)

    def restore_script(self, script_id: str) -> ResearchScriptDetail:
        try:
            self.store.set_script_status(script_id, "active")
        except ResearchScriptStoreConflictError as exc:
            if self.store.load_script(script_id) is None:
                raise ResearchScriptNotFoundError("Research script not found.") from exc
            raise ResearchScriptConflictError(str(exc)) from exc
        return self.get_script(script_id)

    def export_domain_input(
        self,
        script_id: str,
        request: ResearchScriptDataExportRequest,
    ) -> ResearchScriptInputSnapshot:
        detail = self.get_script(script_id)
        if detail.script.status in {"archived", "discarded"}:
            raise ResearchScriptConflictError("Restore the archived script before exporting inputs.")
        object_id = str(request.object_id or "").strip()
        filename = self._safe_output_filename(str(request.logical_filename or "").strip())
        if not object_id:
            raise ResearchScriptValidationError(["A Gamma object identifier is required for export."])

        retrieved_at = now_utc()
        dataset_ref: dict[str, Any]
        source_ref: dict[str, Any]
        warnings: list[str] = []
        if request.domain == "equity_history":
            if self.research_provider is None or not hasattr(self.research_provider, "load_symbol_history"):
                raise ResearchScriptValidationError(["Gamma equity-history export is unavailable."])
            symbol = object_id.upper()
            lookback_days = int(request.lookback_days or 756)
            if lookback_days < 20 or lookback_days > 3650:
                raise ResearchScriptValidationError(["Equity-history lookback_days must be between 20 and 3650."])
            frequency = request.frequency or "daily"
            try:
                series = self.research_provider.load_symbol_history(symbol, lookback_days)
                if series is None or getattr(series, "empty", True):
                    raise ValueError("empty history")
                if frequency == "weekly":
                    series = series.resample("W-FRI").last().dropna()
                elif frequency == "monthly":
                    series = series.resample("ME").last().dropna()
                content = series.rename("close").to_csv(index_label="date").encode("utf-8")
            except Exception as exc:
                raise ResearchScriptValidationError(
                    [f"Gamma could not export bounded equity history for {symbol}."]
                ) from exc
            provider_id = "gamma_research_market_data"
            transformation = (
                f"Gamma copied bounded {frequency} historical prices for {symbol}; "
                "the isolated runtime receives only this immutable CSV snapshot."
            )
            dataset_ref = {
                "contract_version": "research-script-domain-export.v1",
                "domain": request.domain,
                "object_id": symbol,
                "frequency": frequency,
                "lookback_days": lookback_days,
                "logical_filename": filename,
            }
            source_ref = {
                "source_id": f"equity_history:{symbol}",
                "provider": provider_id,
                "retrieved_at": retrieved_at.isoformat(),
            }
            media_type = "text/csv"
        elif request.domain == "macro_series":
            if self.macro_service is None or not hasattr(self.macro_service, "get_series_history"):
                raise ResearchScriptValidationError(["Gamma macro-series export is unavailable."])
            region = str(request.region or "US").strip() or "US"
            timeframe = str(request.timeframe or "1Y").strip() or "1Y"
            history = self.macro_service.get_series_history(
                object_id,
                region=region,
                timeframe=timeframe,
                force_refresh=False,
            )
            if history is None or not history.points:
                raise ResearchScriptValidationError([f"Gamma macro series is unavailable: {object_id}."])
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(("timestamp", "value"))
            for point in history.points:
                writer.writerow((point.timestamp.isoformat(), point.value))
            content = buffer.getvalue().encode("utf-8")
            provider_id = str(history.source_provider or "gamma_macro")
            transformation = (
                f"Gamma copied the normalized {region}/{timeframe} macro series {history.series_id}; "
                "the isolated runtime receives only this immutable CSV snapshot."
            )
            dataset_ref = {
                "contract_version": "research-script-domain-export.v1",
                "domain": request.domain,
                "object_id": history.series_id,
                "region": region,
                "timeframe": timeframe,
                "frequency": history.frequency,
                "logical_filename": filename,
            }
            source_ref = {
                "source_id": f"macro_series:{history.series_id}",
                "provider": provider_id,
                "retrieved_at": (history.retrieved_at or retrieved_at).isoformat(),
            }
            warnings.extend([])
            media_type = "text/csv"
        elif request.domain == "saved_research":
            if self.research_service is None or not hasattr(self.research_service, "load_saved_research"):
                raise ResearchScriptValidationError(["Gamma saved-research export is unavailable."])
            saved = self.research_service.load_saved_research(object_id)
            if saved is None:
                raise ResearchScriptNotFoundError("Saved Gamma research object not found.")
            payload = asdict(saved) if is_dataclass(saved) else dict(saved)
            if self._payload_contains_sensitive_key(payload):
                raise ResearchScriptValidationError(
                    ["The selected saved research object contains fields outside the Script export boundary."]
                )
            content = json.dumps(
                payload,
                sort_keys=True,
                ensure_ascii=False,
                indent=2,
                default=self._json_default,
            ).encode("utf-8")
            provider_id = str(getattr(saved, "source_provider", "gamma_saved_research") or "gamma_saved_research")
            transformation = (
                "Gamma serialized one selected saved research object into a bounded immutable JSON snapshot; "
                "no live service handle or local path was exposed."
            )
            dataset_ref = {
                "contract_version": "research-script-domain-export.v1",
                "domain": request.domain,
                "object_id": str(saved.id),
                "object_type": str(saved.object_type),
                "logical_filename": filename,
            }
            source_ref = {
                "source_id": f"saved_research:{saved.id}",
                "provider": provider_id,
                "retrieved_at": (saved.retrieved_at or saved.updated_at).isoformat(),
            }
            warnings.extend(list(saved.warnings))
            media_type = "application/json"
        else:
            raise ResearchScriptValidationError([f"Unsupported Gamma export domain: {request.domain}."])

        exported_file = ResearchScriptInputFileCreateRequest(
            logical_filename=filename,
            media_type=media_type,
            content=content,
            gamma_object_id=object_id,
            provider_id=provider_id,
            retrieved_at=retrieved_at,
            transformation_note=transformation,
            source_kind="gamma_state",
        )
        return self._create_input_snapshot(
            script_id,
            ResearchScriptRunCreateRequest(
                input_files=[exported_file, *request.additional_input_files],
                dataset_refs=[dataset_ref],
                source_refs=[source_ref],
            ),
            extra_warnings=warnings,
        )

    def compare_runs(
        self,
        base_run_id: str,
        comparison_run_id: str,
    ) -> ResearchScriptRunComparison:
        base = self.get_run(base_run_id)
        comparison = self.get_run(comparison_run_id)
        if base.script_id != comparison.script_id:
            raise ResearchScriptValidationError(["Research Script runs must belong to the same script."])
        base_metrics = {
            item.metric_name or item.output_id: item.metric_value
            for item in base.outputs
            if item.kind == "metric"
        }
        comparison_metrics = {
            item.metric_name or item.output_id: item.metric_value
            for item in comparison.outputs
            if item.kind == "metric"
        }
        metric_deltas: list[dict[str, Any]] = []
        for name in sorted(set(base_metrics) | set(comparison_metrics)):
            left = base_metrics.get(name)
            right = comparison_metrics.get(name)
            delta = (
                float(right) - float(left)
                if isinstance(left, (int, float)) and isinstance(right, (int, float))
                else None
            )
            metric_deltas.append({"name": name, "base": left, "comparison": right, "delta": delta})
        return ResearchScriptRunComparison(
            base_run_id=base.run_id,
            comparison_run_id=comparison.run_id,
            same_revision=base.revision_id == comparison.revision_id,
            same_input_snapshot=base.input_snapshot_id == comparison.input_snapshot_id,
            status_changed=base.status != comparison.status,
            duration_delta_seconds=self._duration_seconds(comparison) - self._duration_seconds(base)
            if base.completed_at and comparison.completed_at
            else None,
            input_token_delta=self._usage_delta(base, comparison, "input_tokens"),
            output_token_delta=self._usage_delta(base, comparison, "output_tokens"),
            output_count_delta=len(comparison.outputs) - len(base.outputs),
            warning_count_delta=len(comparison.warnings) - len(base.warnings),
            metric_deltas=metric_deltas,
        )

    def export_run_bundle(self, run_id: str) -> tuple[str, bytes]:
        run = self.get_run(run_id)
        detail = self.get_script(run.script_id)
        revision = next(
            (item for item in detail.revisions if item.revision_id == run.revision_id),
            None,
        )
        snapshot = self.get_input_snapshot(run.input_snapshot_id)
        if revision is None or revision.source_sha256 != run.source_sha256:
            raise ResearchScriptServiceError("Run export source association is unavailable.")
        input_contents = self.store.load_input_contents(snapshot)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("source.py", revision.source)
            bundle.writestr(
                "input/manifest.json",
                json.dumps(asdict(snapshot), indent=2, sort_keys=True, default=self._json_default),
            )
            for logical_filename, content in input_contents.items():
                bundle.writestr(f"input/files/{logical_filename}", content)
            bundle.writestr(
                "run.json",
                json.dumps(asdict(run), indent=2, sort_keys=True, default=self._json_default),
            )
            bundle.writestr(
                "README.txt",
                "Gamma Research Script export\n"
                "Read-only research artifact. No broker, wallet, account, order, host, or network authority is included.\n",
            )
            for output in run.outputs:
                if not output.artifact_ref or not output.filename:
                    continue
                content = self.store.load_output_artifact(run.run_id, output.output_id, output.filename)
                if content is None:
                    raise ResearchScriptServiceError(
                        f"Retained output is unavailable for export: {output.output_id}."
                    )
                bundle.writestr(f"outputs/{output.output_id}-{output.filename}", content)
        return f"gamma-research-script-{run.run_id[:12]}.zip", stream.getvalue()

    def storage_diagnostics(self) -> ResearchScriptStorageDiagnostics:
        return self.store.storage_diagnostics()

    def cleanup_retained_outputs(self) -> ResearchScriptStorageDiagnostics:
        self.store.cleanup_retained_outputs()
        return self.store.storage_diagnostics()

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"Unsupported research export value: {type(value).__name__}")

    @classmethod
    def _payload_contains_sensitive_key(cls, value: Any) -> bool:
        sensitive_fragments = {
            "account",
            "api_key",
            "authorization",
            "broker",
            "cookie",
            "credential",
            "order",
            "password",
            "secret",
            "token",
            "wallet",
        }
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).strip().lower()
                if any(fragment in normalized for fragment in sensitive_fragments):
                    return True
                if cls._payload_contains_sensitive_key(item):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(cls._payload_contains_sensitive_key(item) for item in value)
        return False

    @staticmethod
    def _duration_seconds(run: ResearchScriptRun) -> float:
        if run.completed_at is None:
            return 0.0
        return max((run.completed_at - run.started_at).total_seconds(), 0.0)

    @staticmethod
    def _usage_delta(base: ResearchScriptRun, comparison: ResearchScriptRun, key: str) -> int | None:
        left = base.usage.get(key)
        right = comparison.usage.get(key)
        if isinstance(left, int) and isinstance(right, int):
            return right - left
        return None

    @staticmethod
    def _estimated_token_cost(usage: dict[str, Any], model: str | None) -> dict[str, Any]:
        if str(model or "").strip().lower() != "gpt-5.6-luna":
            return {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            return {}
        return {
            "estimated_token_cost_usd": round(
                (input_tokens * 0.20 + output_tokens * 1.20) / 1_000_000,
                8,
            ),
            "estimated_cost_scope": "gpt-5.6-luna text tokens only; tool charges excluded",
        }

    def _create_input_snapshot(
        self,
        script_id: str,
        request: ResearchScriptRunCreateRequest,
        *,
        extra_warnings: list[str] | None = None,
    ) -> ResearchScriptInputSnapshot:
        errors: list[str] = []
        if len(request.input_files) > MAX_RESEARCH_SCRIPT_INPUT_FILES:
            errors.append(f"Input file count exceeds {MAX_RESEARCH_SCRIPT_INPUT_FILES}.")
        if len(request.dataset_refs) > MAX_RESEARCH_SCRIPT_DATASET_REFS:
            errors.append(f"Dataset reference count exceeds {MAX_RESEARCH_SCRIPT_DATASET_REFS}.")
        if len(request.source_refs) > MAX_RESEARCH_SCRIPT_SOURCE_REFS:
            errors.append(f"Source reference count exceeds {MAX_RESEARCH_SCRIPT_SOURCE_REFS}.")
        filenames: set[str] = set()
        total_bytes = 0
        for item in request.input_files:
            filename = str(item.logical_filename or "").strip()
            if not self._is_safe_filename(filename):
                errors.append(f"Unsafe input filename: {filename or '<empty>'}.")
            if len(filename) > MAX_RESEARCH_SCRIPT_FILENAME_CHARS:
                errors.append(
                    f"Input filename {filename!r} exceeds {MAX_RESEARCH_SCRIPT_FILENAME_CHARS} characters."
                )
            if filename in filenames:
                errors.append(f"Duplicate input filename: {filename}.")
            filenames.add(filename)
            byte_size = len(item.content)
            total_bytes += byte_size
            if byte_size > MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES:
                errors.append(
                    f"Input file {filename!r} exceeds {MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES} bytes."
                )
        if total_bytes > MAX_RESEARCH_SCRIPT_TOTAL_INPUT_BYTES:
            errors.append(f"Input bundle exceeds {MAX_RESEARCH_SCRIPT_TOTAL_INPUT_BYTES} bytes.")
        manifest_refs = {
            "dataset_refs": request.dataset_refs,
            "source_refs": request.source_refs,
        }
        if len(self._canonical_json(manifest_refs).encode("utf-8")) > MAX_RESEARCH_SCRIPT_INPUT_MANIFEST_BYTES:
            errors.append(f"Input manifest exceeds {MAX_RESEARCH_SCRIPT_INPUT_MANIFEST_BYTES} bytes.")
        if errors:
            raise ResearchScriptValidationError(errors)

        created_at = now_utc()
        snapshot_id = uuid4().hex
        files: list[ResearchScriptInputFile] = []
        contents: dict[str, bytes] = {}
        for item in request.input_files:
            filename = str(item.logical_filename).strip()
            content_hash = hashlib.sha256(item.content).hexdigest()
            files.append(
                ResearchScriptInputFile(
                    logical_filename=filename,
                    media_type=str(item.media_type or "application/octet-stream").strip(),
                    byte_size=len(item.content),
                    content_sha256=content_hash,
                    gamma_object_id=item.gamma_object_id,
                    provider_id=item.provider_id,
                    source_timestamp=item.source_timestamp,
                    retrieved_at=item.retrieved_at or created_at,
                    transformation_note=item.transformation_note,
                    source_kind=item.source_kind,
                    artifact_ref=f"research-script-input:{snapshot_id}:{filename}",
                )
            )
            contents[filename] = item.content
        manifest_identity = {
            "contract_version": "research-script-input.v1",
            "script_id": script_id,
            "files": [
                {
                    "logical_filename": item.logical_filename,
                    "media_type": item.media_type,
                    "byte_size": item.byte_size,
                    "content_sha256": item.content_sha256,
                    "gamma_object_id": item.gamma_object_id,
                    "provider_id": item.provider_id,
                    "source_timestamp": item.source_timestamp.isoformat() if item.source_timestamp else None,
                    "retrieved_at": item.retrieved_at.isoformat(),
                    "transformation_note": item.transformation_note,
                    "source_kind": item.source_kind,
                }
                for item in files
            ],
            "dataset_refs": request.dataset_refs,
            "source_refs": request.source_refs,
            "total_bytes": total_bytes,
        }
        snapshot = ResearchScriptInputSnapshot(
            snapshot_id=snapshot_id,
            script_id=script_id,
            created_at=created_at,
            files=files,
            dataset_refs=[dict(item) for item in request.dataset_refs],
            source_refs=[dict(item) for item in request.source_refs],
            warnings=list(extra_warnings or []),
            manifest_sha256=self.manifest_sha256(manifest_identity),
            total_bytes=total_bytes,
            source_provider="gamma_research_script",
            origin="research_script_service.create_input_snapshot",
            transformation_note="Immutable copied input manifest for a bounded research-script run.",
        )
        self.store.create_input_snapshot(snapshot, contents)
        return snapshot

    @staticmethod
    def _input_manifest_identity(snapshot: ResearchScriptInputSnapshot) -> dict[str, Any]:
        return {
            "contract_version": snapshot.contract_version,
            "script_id": snapshot.script_id,
            "files": [
                {
                    "logical_filename": item.logical_filename,
                    "media_type": item.media_type,
                    "byte_size": item.byte_size,
                    "content_sha256": item.content_sha256,
                    "gamma_object_id": item.gamma_object_id,
                    "provider_id": item.provider_id,
                    "source_timestamp": item.source_timestamp.isoformat() if item.source_timestamp else None,
                    "retrieved_at": item.retrieved_at.isoformat(),
                    "transformation_note": item.transformation_note,
                    "source_kind": item.source_kind,
                }
                for item in snapshot.files
            ],
            "dataset_refs": snapshot.dataset_refs,
            "source_refs": snapshot.source_refs,
            "total_bytes": snapshot.total_bytes,
        }

    def _normalize_outputs(
        self,
        run_id: str,
        runtime_outputs: list[ResearchScriptRuntimeOutput],
        created_at,
        *,
        source_provider: str = "gamma_mock_research_script_runtime",
        origin: str = "mock_research_script_runtime",
    ) -> tuple[list[ResearchScriptOutput], dict[str, tuple[str, bytes]], list[str]]:
        if len(runtime_outputs) > MAX_RESEARCH_SCRIPT_OUTPUT_ARTIFACTS:
            raise ResearchScriptValidationError(
                [f"Runtime output count exceeds {MAX_RESEARCH_SCRIPT_OUTPUT_ARTIFACTS}."]
            )
        outputs: list[ResearchScriptOutput] = []
        artifacts: dict[str, tuple[str, bytes]] = {}
        warnings: list[str] = []
        retained_bytes = 0
        seen_ids: set[str] = set()
        allowed_kinds = {
            "log",
            "error",
            "metric",
            "table",
            "image",
            "file",
            "summary",
            "warning",
        }
        allowed_media_types = {
            "application/json",
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/svg+xml",
            "text/csv",
            "text/plain",
            "text/x-python",
        }
        for index, raw in enumerate(runtime_outputs, start=1):
            if raw.output_id in seen_ids:
                raise ResearchScriptValidationError([f"Duplicate runtime output id: {raw.output_id}."])
            seen_ids.add(raw.output_id)
            if raw.kind not in allowed_kinds:
                raise ResearchScriptValidationError([f"Unsupported runtime output kind: {raw.kind}."])
            if raw.media_type not in allowed_media_types:
                raise ResearchScriptValidationError(
                    [f"Unsupported runtime output media type: {raw.media_type}."]
                )
            if not raw.output_id or any(
                ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for ch in raw.output_id
            ):
                raise ResearchScriptValidationError(["Runtime output id contains unsafe characters."])
            columns = list(raw.columns[:MAX_RESEARCH_SCRIPT_INLINE_TABLE_COLUMNS])
            rows = [
                {column: row.get(column) for column in columns}
                for row in raw.rows[:MAX_RESEARCH_SCRIPT_INLINE_TABLE_ROWS]
            ]
            if len(raw.columns) > len(columns):
                warnings.append(
                    f"Output {raw.output_id} table preview was limited to "
                    f"{MAX_RESEARCH_SCRIPT_INLINE_TABLE_COLUMNS} columns."
                )
            if len(raw.rows) > len(rows):
                warnings.append(
                    f"Output {raw.output_id} table preview was limited to "
                    f"{MAX_RESEARCH_SCRIPT_INLINE_TABLE_ROWS} rows."
                )
            text = raw.text
            artifact_ref: str | None = None
            filename = raw.filename
            artifact_bytes = raw.artifact_bytes
            if text is not None:
                text_bytes = text.encode("utf-8")
                if len(text_bytes) > MAX_RESEARCH_SCRIPT_INLINE_TEXT_BYTES:
                    filename = filename or f"{raw.output_id}.txt"
                    artifact_bytes = text_bytes
                    text = text_bytes[:MAX_RESEARCH_SCRIPT_INLINE_TEXT_BYTES].decode(
                        "utf-8",
                        errors="ignore",
                    )
                    warnings.append(
                        f"Output {raw.output_id} inline text was truncated to "
                        f"{MAX_RESEARCH_SCRIPT_INLINE_TEXT_BYTES} bytes; the retained full text is an artifact."
                    )
            if artifact_bytes is not None:
                filename = self._safe_output_filename(filename or f"{raw.output_id}.bin")
                artifacts[raw.output_id] = (filename, artifact_bytes)
                artifact_ref = f"research-script-output:{run_id}:{raw.output_id}"
                retained_bytes += len(artifact_bytes)
            inline_payload = {
                "text": text,
                "metric_name": raw.metric_name,
                "metric_value": raw.metric_value,
                "unit": raw.unit,
                "columns": columns,
                "rows": rows,
            }
            inline_bytes = len(self._canonical_json(inline_payload).encode("utf-8"))
            retained_bytes += inline_bytes
            outputs.append(
                ResearchScriptOutput(
                    output_id=raw.output_id,
                    kind=raw.kind,
                    sequence=raw.sequence or index,
                    media_type=raw.media_type,
                    byte_size=len(artifact_bytes) if artifact_bytes is not None else inline_bytes,
                    created_at=created_at,
                    artifact_ref=artifact_ref,
                    provider_native_ref=raw.provider_native_ref,
                    text=text,
                    metric_name=raw.metric_name,
                    metric_value=raw.metric_value,
                    unit=raw.unit,
                    columns=columns,
                    rows=rows,
                    filename=filename,
                    alt_text=raw.alt_text,
                    source_provider=source_provider,
                    origin=origin,
                    transformation_note=raw.transformation_note,
                )
            )
        if retained_bytes > MAX_RESEARCH_SCRIPT_TOTAL_OUTPUT_BYTES:
            raise ResearchScriptValidationError(
                [f"Retained runtime output exceeds {MAX_RESEARCH_SCRIPT_TOTAL_OUTPUT_BYTES} bytes."]
            )
        return sorted(outputs, key=lambda item: (item.sequence, item.output_id)), artifacts, warnings

    @staticmethod
    def _validate_source(source: str) -> list[str]:
        errors: list[str] = []
        if not isinstance(source, str) or not source.strip():
            errors.append("Python source is required.")
            return errors
        source_bytes = source.encode("utf-8")
        if len(source_bytes) > MAX_RESEARCH_SCRIPT_SOURCE_BYTES:
            errors.append(f"Python source exceeds {MAX_RESEARCH_SCRIPT_SOURCE_BYTES} bytes.")
        if "\x00" in source:
            errors.append("Python source cannot contain NUL bytes.")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            errors.append("Python source must parse successfully before it can become canonical.")
            return errors
        prohibited_modules = {
            "ctypes",
            "ftplib",
            "http",
            "httpx",
            "ib_insync",
            "multiprocessing",
            "openai",
            "paramiko",
            "pip",
            "requests",
            "shlex",
            "socket",
            "subprocess",
            "urllib",
            "webbrowser",
        }
        prohibited_calls = {
            "eval",
            "exec",
            "compile",
            "__import__",
            "breakpoint",
            "globals",
            "locals",
            "vars",
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                if any(name.split(".", 1)[0] in prohibited_modules for name in names):
                    errors.append("Python source requests a prohibited network, shell, broker, or package module.")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in prohibited_calls:
                    errors.append("Python source cannot use dynamic code execution helpers.")
                if isinstance(node.func, ast.Attribute):
                    owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                    if owner == "os" and (
                        node.func.attr in {"system", "popen", "getenv"}
                        or node.func.attr.startswith(("exec", "spawn"))
                    ):
                        errors.append("Python source cannot invoke shell commands or environment access.")
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "os" and node.attr == "environ":
                    errors.append("Python source cannot access environment variables.")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                errors.append("Python source cannot traverse Python runtime internals.")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                if re.search(r"(?:https?://|localhost|127\.0\.0\.1|\\\\\.\\pipe)", lowered):
                    errors.append("Python source cannot contain network or localhost destinations.")
                if (
                    lowered.startswith(("/", "\\\\", "file:"))
                    or re.match(r"^[a-z]:[\\/]", lowered)
                    or "../" in lowered
                    or "..\\" in lowered
                ):
                    errors.append("Python source cannot contain absolute or parent-traversing file paths.")
        return errors

    @classmethod
    def _validate_authorized_input_references(
        cls,
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(references) > MAX_RESEARCH_SCRIPT_DATASET_REFS:
            raise ResearchScriptValidationError(
                [f"Authorized input reference count exceeds {MAX_RESEARCH_SCRIPT_DATASET_REFS}."]
            )
        allowed_keys = {
            "reference_id",
            "source_kind",
            "provider",
            "dataset_id",
            "logical_filename",
            "media_type",
            "coverage_start",
            "coverage_end",
            "symbol",
            "benchmark_symbol",
            "timeframe",
            "lookback_days",
            "frequency",
        }
        rows: list[dict[str, Any]] = []
        for raw in references:
            if not isinstance(raw, dict) or set(raw) != allowed_keys:
                raise ResearchScriptValidationError(
                    ["Authorized input references must use the exact bounded Script reference contract."]
                )
            row = {
                key: (
                    int(raw[key])
                    if key == "lookback_days" and raw[key] is not None
                    else str(raw[key]).strip()
                    if raw[key] is not None
                    else None
                )
                for key in allowed_keys
            }
            if not row["reference_id"] or row["source_kind"] not in {"gamma_state", "provider", "user_upload"}:
                raise ResearchScriptValidationError(["Authorized input reference identity or source kind is invalid."])
            if row["logical_filename"] and not cls._is_safe_filename(str(row["logical_filename"])):
                raise ResearchScriptValidationError(["Authorized input reference filename is unsafe."])
            if row["lookback_days"] is not None and not 20 <= int(row["lookback_days"]) <= 3650:
                raise ResearchScriptValidationError(["Authorized input lookback_days must be between 20 and 3650."])
            if row["frequency"] not in {None, "daily", "weekly", "monthly"}:
                raise ResearchScriptValidationError(["Authorized input frequency is invalid."])
            serialized = json.dumps(row, sort_keys=True).lower()
            if any(
                term in serialized
                for term in (
                    "http://",
                    "https://",
                    "localhost",
                    "127.0.0.1",
                    "api_key",
                    "secret",
                    "password",
                    "broker",
                    "account",
                    "wallet",
                    "order",
                    "shell",
                )
            ):
                raise ResearchScriptValidationError(
                    ["Authorized input references cannot contain destinations, credentials, or execution authority."]
                )
            if len(serialized.encode("utf-8")) > 2048:
                raise ResearchScriptValidationError(["Authorized input reference is too large."])
            rows.append(row)
        return rows

    @staticmethod
    def _is_safe_filename(value: str) -> bool:
        return is_safe_research_script_filename(value)

    @classmethod
    def _safe_output_filename(cls, value: str) -> str:
        filename = str(value or "").strip()
        if not cls._is_safe_filename(filename):
            raise ResearchScriptValidationError(["Runtime output filename is unsafe."])
        if len(filename) > MAX_RESEARCH_SCRIPT_FILENAME_CHARS:
            raise ResearchScriptValidationError(
                [f"Runtime output filename exceeds {MAX_RESEARCH_SCRIPT_FILENAME_CHARS} characters."]
            )
        return filename

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
