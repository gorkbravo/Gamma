from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models.copilot import (
    CopilotArtifact,
    CopilotArtifactProviderMetadata,
    CopilotArtifactReference,
    CopilotConfirmationState,
    CopilotContextSnapshot,
    CopilotDeleteResult,
    CopilotDraftMutation,
    CopilotMemo,
    CopilotMutationDiffEntry,
    CopilotOperatorConfirmationCheckpoint,
    CopilotOperatorPlan,
    CopilotOperatorPlanStep,
    CopilotOperatorProgressEvent,
    CopilotResearchCardResult,
    CopilotResearchPlan,
    CopilotResearchPlanDomain,
    CopilotResearchPlanDomainDecision,
    CopilotResearchPlanEntity,
    CopilotReportToolTraceSummary,
    CopilotReportWarningProvenance,
    CopilotRunEvent,
    CopilotSession,
    CopilotSourceRef,
    CopilotStorageStatus,
    CopilotStorageWarning,
    CopilotToolTrace,
    CopilotTraceState,
    CopilotTurn,
    CopilotUsageRecord,
    ResearchCard,
    ResearchClaim,
    new_copilot_id,
)
from src.services.copilot_evidence import resolve_result_evidence
from src.utils.time import now_utc


CURRENT_COPILOT_STORE_SCHEMA_VERSION = 3
SUPPORTED_COPILOT_STORE_LEGACY_VERSIONS = (0, 1, 2)
SUPPORTED_COPILOT_STORE_SCHEMA_VERSIONS = (
    *SUPPORTED_COPILOT_STORE_LEGACY_VERSIONS,
    CURRENT_COPILOT_STORE_SCHEMA_VERSION,
)


class CopilotStoreError(ValueError):
    pass


class CopilotStoreNotFoundError(CopilotStoreError):
    pass


class CopilotStoreConflictError(CopilotStoreError):
    pass


class CopilotStore:
    def __init__(self, base_dir: str | Path = "data/copilot") -> None:
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.turns_dir = self.base_dir / "turns"
        self.memos_dir = self.base_dir / "memos"
        self.artifacts_dir = self.base_dir / "artifacts"
        self.mutations_dir = self.base_dir / "mutations"
        self.quarantine_dir = self.base_dir / "quarantine"
        self.trash_dir = self.base_dir / "trash"
        self.recovery_log_path = self.base_dir / "recovery_warnings.json"
        for directory in (
            self.sessions_dir,
            self.snapshots_dir,
            self.turns_dir,
            self.memos_dir,
            self.artifacts_dir,
            self.mutations_dir,
            self.quarantine_dir,
            self.trash_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._storage_warnings: list[CopilotStorageWarning] = []
        self._load_recovery_log()
        self._recover_interrupted_writes()
        self._migrate_legacy_memos()

    def list_sessions(self, *, include_archived: bool = False, search: str | None = None) -> list[CopilotSession]:
        with self._lock:
            sessions = [item for path in self.sessions_dir.glob("*.json") if (item := self._load_session_path(path))]
        if not include_archived:
            sessions = [session for session in sessions if session.archived_at is None]
        query = str(search or "").strip().lower()
        if query:
            sessions = [
                session
                for session in sessions
                if query in session.title.lower()
                or query in session.session_id.lower()
                or query in str(session.active_domain or "").lower()
                or any(query in warning.lower() for warning in session.warnings)
            ]
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def get_session(self, session_id: str) -> CopilotSession | None:
        safe_id = self._safe_id(session_id)
        if not safe_id:
            return None
        with self._lock:
            return self._load_session_path(self.sessions_dir / f"{safe_id}.json")

    def create_session(
        self,
        *,
        title: str | None = None,
        session_id: str | None = None,
    ) -> CopilotSession:
        """Create one authoritative empty session record.

        `New chat` needs a persisted session before it can be selected, otherwise
        the client holds an id the store has never seen and normal reconciliation
        treats it as stale. Passing an explicit `session_id` is idempotent so a
        double activation reattaches to the same blank session instead of
        creating a second one.
        """
        safe_session_id = self._safe_id(session_id) if session_id else ""
        if session_id and not safe_session_id:
            raise CopilotStoreError("session_id contains no usable characters.")
        safe_session_id = safe_session_id or new_copilot_id("session")
        now = now_utc()
        with self._lock:
            session_path = self.sessions_dir / f"{safe_session_id}.json"
            existing = self._load_session_path(session_path)
            if existing is not None:
                return existing
            session = CopilotSession(
                session_id=safe_session_id,
                title=(str(title or "").strip() or "New Copilot Session")[:96],
                created_at=now,
                updated_at=now,
            )
            self._write_json(session_path, self._session_to_json(session))
        return session

    def storage_status(self) -> CopilotStorageStatus:
        with self._lock:
            warnings = list(self._storage_warnings)
        return CopilotStorageStatus(
            current_schema_version=CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            supported_legacy_versions=list(SUPPORTED_COPILOT_STORE_LEGACY_VERSIONS),
            warnings=warnings,
        )

    def get_context_snapshot(self, snapshot_id: str) -> CopilotContextSnapshot | None:
        safe_id = self._safe_id(snapshot_id)
        if not safe_id:
            return None
        with self._lock:
            return self._load_snapshot_path(self.snapshots_dir / f"{safe_id}.json")

    def list_context_snapshots(self, session_id: str) -> list[CopilotContextSnapshot]:
        turns = self.list_turns(session_id)
        snapshots: list[CopilotContextSnapshot] = []
        with self._lock:
            for turn in turns:
                snapshot = self._load_snapshot_path(self.snapshots_dir / f"{turn.context_snapshot_id}.json")
                if snapshot is not None:
                    snapshots.append(snapshot)
        return snapshots

    def list_turns(self, session_id: str) -> list[CopilotTurn]:
        safe_id = self._safe_id(session_id)
        if not safe_id:
            return []
        turns_dir = self.turns_dir / safe_id
        with self._lock:
            turns = [item for path in turns_dir.glob("*.json") if (item := self._load_turn_path(path))]
        return sorted(turns, key=lambda item: item.turn_index)

    def list_memos(self, session_id: str | None = None) -> list[CopilotMemo]:
        return [
            self._artifact_to_memo(artifact)
            for artifact in self.list_artifacts(session_id)
            if artifact.artifact_type == "memo"
        ]

    def list_artifacts(self, session_id: str | None = None) -> list[CopilotArtifact]:
        safe_session_id = self._safe_id(session_id) if session_id else None
        with self._lock:
            artifacts = [
                item
                for path in self.artifacts_dir.glob("*.json")
                if (item := self._load_artifact_path(path))
            ]
            if safe_session_id:
                available_turn_ids = {
                    turn.turn_id for turn in self._load_turns_unlocked(safe_session_id)
                }
                artifacts = [
                    self._with_artifact_availability(item, available_turn_ids)
                    for item in artifacts
                    if item.session_id == safe_session_id
                ]
        return sorted(artifacts, key=lambda item: item.updated_at, reverse=True)

    def record_turn(
        self,
        *,
        session_id: str | None,
        title: str | None,
        domain: str,
        current_tab: str,
        workspace_mode: str | None,
        prompt: str | None,
        context_fingerprint: str | None,
        context_summary: dict[str, Any],
        result: CopilotResearchCardResult,
        role: str = "research_agent",
        reasoning_effort: str | None = None,
        selected_scope_domains: list[str] | None = None,
        request_context: dict[str, Any] | None = None,
        requested_provider: str | None = None,
        requested_model: str | None = None,
        run_id: str | None = None,
        terminal_status: str | None = None,
        cancellation_outcome: str | None = None,
        usage: CopilotUsageRecord | None = None,
        research_plan: CopilotResearchPlan | None = None,
        operator_plan: CopilotOperatorPlan | None = None,
        run_events: list[CopilotRunEvent] | None = None,
        confirmations: list[CopilotConfirmationState] | None = None,
        artifact_refs: list[CopilotArtifactReference] | None = None,
        mutation_refs: list[CopilotArtifactReference] | None = None,
    ) -> tuple[CopilotSession, CopilotContextSnapshot, CopilotTurn]:
        now = now_utc()
        result = resolve_result_evidence(result)
        safe_session_id = self._safe_id(session_id) or new_copilot_id("session")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            existing_turns = self._load_turns_unlocked(safe_session_id)
            if session is None:
                session = CopilotSession(
                    session_id=safe_session_id,
                    title=self._session_title(title, domain, result, prompt),
                    created_at=now,
                    updated_at=now,
                )

            snapshot = CopilotContextSnapshot(
                snapshot_id=new_copilot_id("ctx"),
                domain=domain,
                context_fingerprint=context_fingerprint,
                current_tab=current_tab,
                workspace_mode=workspace_mode,
                summary=context_summary,
                request_context=dict(request_context or {}),
                selected_scope_domains=list(selected_scope_domains or []),
                source_ids=[source.source_id for source in result.sources],
                warnings=list(result.warnings),
                created_at=now,
            )
            turn = CopilotTurn(
                turn_id=new_copilot_id("turn"),
                session_id=safe_session_id,
                turn_index=len(existing_turns),
                domain=domain,
                prompt=str(prompt or "").strip(),
                context_snapshot_id=snapshot.snapshot_id,
                result=result,
                created_at=now,
                role=role,
                reasoning_effort=reasoning_effort,
                selected_scope_domains=list(selected_scope_domains or []),
                context_fingerprint=context_fingerprint,
                requested_provider=requested_provider,
                requested_model=requested_model,
                resolved_provider=result.provider,
                resolved_model=result.model,
                run_id=run_id or self._result_run_id(result),
                terminal_status=terminal_status or result.status,
                cancellation_outcome=cancellation_outcome or self._cancellation_outcome(result),
                usage=usage or self._usage_from_events(run_events or []),
                research_plan=research_plan or self._research_plan_from_summary(context_summary),
                operator_plan=operator_plan or self._operator_plan_from_summary(context_summary),
                run_events=list(run_events or []),
                confirmations=list(confirmations or self._confirmations_from_result(result)),
                artifact_refs=list(artifact_refs or self._artifact_refs_from_result(result)),
                mutation_refs=list(mutation_refs or self._mutation_refs_from_result(result)),
                trace_state=CopilotTraceState(
                    event_count=len(run_events or []),
                    tool_trace_count=len(result.tool_traces),
                    operator_event_count=len(result.operator_events),
                    source_count=len(result.sources),
                    warning_count=len(result.warnings),
                ),
            )
            artifacts = [
                artifact
                for artifact in self._load_artifacts_unlocked()
                if artifact.session_id == safe_session_id
            ]
            memo_count = sum(artifact.artifact_type == "memo" for artifact in artifacts)
            report_count = sum(artifact.artifact_type == "report" for artifact in artifacts)
            next_session = CopilotSession(
                session_id=safe_session_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=now,
                active_domain=domain,
                active_context_fingerprint=context_fingerprint,
                turn_count=len(existing_turns) + 1,
                memo_count=memo_count,
                report_count=report_count,
                artifact_count=len(artifacts),
                warnings=list(dict.fromkeys([*session.warnings, *result.warnings])),
                archived_at=None,
            )
            self._write_json(self.sessions_dir / f"{safe_session_id}.json", self._session_to_json(next_session))
            self._write_json(self.snapshots_dir / f"{snapshot.snapshot_id}.json", self._snapshot_to_json(snapshot))
            self._write_json(self.turns_dir / safe_session_id / f"{turn.turn_id}.json", self._turn_to_json(turn))
        return next_session, snapshot, turn

    def create_memo(
        self,
        *,
        session_id: str,
        title: str | None = None,
        notes: str | None = None,
        source_turn_ids: list[str] | None = None,
    ) -> CopilotMemo:
        artifact = self.create_artifact(
            session_id=session_id,
            artifact_type="memo",
            template="concise_memo",
            title=title,
            body=notes,
            source_turn_ids=source_turn_ids,
        )
        return self._artifact_to_memo(artifact)

    def create_artifact(
        self,
        *,
        session_id: str,
        artifact_type: str,
        template: str,
        title: str | None = None,
        body: str | None = None,
        source_turn_ids: list[str] | None = None,
        source_memo_ids: list[str] | None = None,
    ) -> CopilotArtifact:
        safe_session_id = self._safe_id(session_id)
        if not safe_session_id:
            raise CopilotStoreError("session_id is required.")
        normalized_type = str(artifact_type or "").strip().lower()
        normalized_template = str(template or "").strip().lower()
        if normalized_type not in {"memo", "report"}:
            raise CopilotStoreError("artifact_type must be `memo` or `report`.")
        expected_template = "concise_memo" if normalized_type == "memo" else "research_report"
        if normalized_template not in {expected_template, "concise_memo", "research_report"}:
            raise CopilotStoreError("Unsupported Copilot artifact template.")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            if session is None:
                raise CopilotStoreNotFoundError(f"Copilot session not found: {session_id}")
            turns = self._load_turns_unlocked(safe_session_id)
            selected_ids = self._selected_ids(source_turn_ids)
            selected_turns = [turn for turn in turns if not selected_ids or turn.turn_id in selected_ids]
            missing_turn_ids = [item for item in selected_ids if item not in {turn.turn_id for turn in selected_turns}]
            if missing_turn_ids:
                raise CopilotStoreNotFoundError(
                    f"Unknown Copilot source turn ids: {', '.join(missing_turn_ids)}"
                )
            if not selected_turns:
                raise CopilotStoreError("No Copilot turns are available for artifact generation.")
            selected_memo_ids = self._selected_ids(source_memo_ids)
            session_artifacts = [
                item for item in self._load_artifacts_unlocked() if item.session_id == safe_session_id
            ]
            selected_memos = [
                item
                for item in session_artifacts
                if item.artifact_type == "memo" and item.artifact_id in selected_memo_ids
            ]
            missing_memo_ids = [
                item for item in selected_memo_ids if item not in {memo.artifact_id for memo in selected_memos}
            ]
            if missing_memo_ids:
                raise CopilotStoreNotFoundError(
                    f"Unknown Copilot source memo ids: {', '.join(missing_memo_ids)}"
                )
            now = now_utc()
            default_suffix = "Memo" if normalized_type == "memo" else "Research Report"
            artifact_title = str(title or "").strip() or f"{session.title} {default_suffix}"
            provenance = self._artifact_provenance(selected_turns)
            if normalized_type == "memo":
                generated_body = self._build_memo_body(artifact_title, selected_turns, body)
            else:
                generated_body = self._build_report_body(artifact_title, provenance)
                if str(body or "").strip():
                    generated_body = str(body).strip()
            artifact = CopilotArtifact(
                artifact_id=new_copilot_id(normalized_type),
                session_id=safe_session_id,
                artifact_type=normalized_type,
                template=normalized_template or expected_template,
                title=artifact_title[:140],
                body=generated_body,
                source_turn_ids=[turn.turn_id for turn in selected_turns],
                source_memo_ids=[memo.artifact_id for memo in selected_memos],
                source_snapshot_ids=[turn.context_snapshot_id for turn in selected_turns],
                context_fingerprints=list(
                    dict.fromkeys(
                        turn.context_fingerprint
                        for turn in selected_turns
                        if turn.context_fingerprint
                    )
                ),
                source_backed_claims=provenance["source_backed_claims"],
                inferred_claims=provenance["inferred_claims"],
                assumptions=provenance["assumptions"],
                missing_data=provenance["missing_data"],
                warnings=provenance["warnings"],
                warning_provenance=provenance["warning_provenance"],
                tool_trace_summary=provenance["tool_trace_summary"],
                sources=provenance["sources"],
                provider_metadata=[
                    CopilotArtifactProviderMetadata(
                        turn_id=turn.turn_id,
                        role=turn.role,
                        reasoning_effort=turn.reasoning_effort,
                        requested_provider=turn.requested_provider,
                        requested_model=turn.requested_model,
                        resolved_provider=turn.resolved_provider,
                        resolved_model=turn.resolved_model,
                        run_id=turn.run_id,
                        terminal_status=turn.terminal_status,
                    )
                    for turn in selected_turns
                ],
                created_at=now,
                updated_at=now,
                origin="copilot_store.create_artifact",
                transformation_note=(
                    f"Gamma {normalized_type} created from {len(selected_turns)} persisted read-only "
                    "Copilot turn(s); later text edits do not replace the immutable provenance snapshot."
                ),
            )
            self._write_json(
                self.artifacts_dir / f"{artifact.artifact_id}.json",
                self._artifact_to_json(artifact),
            )
            self._refresh_session_counts_unlocked(session, updated_at=now)
        return artifact

    def archive_session(self, session_id: str) -> CopilotSession:
        safe_session_id = self._safe_id(session_id)
        if not safe_session_id:
            raise ValueError("session_id is required.")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            if session is None:
                raise CopilotStoreNotFoundError(f"Copilot session not found: {session_id}")
            now = now_utc()
            if session.archived_at is not None:
                return session
            archived = CopilotSession(
                session_id=session.session_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=now,
                active_domain=session.active_domain,
                active_context_fingerprint=session.active_context_fingerprint,
                turn_count=session.turn_count,
                memo_count=session.memo_count,
                report_count=session.report_count,
                artifact_count=session.artifact_count,
                warnings=session.warnings,
                archived_at=now,
            )
            self._write_json(self.sessions_dir / f"{safe_session_id}.json", self._session_to_json(archived))
        return archived

    def restore_session(self, session_id: str) -> CopilotSession:
        safe_session_id = self._safe_id(session_id)
        if not safe_session_id:
            raise CopilotStoreError("session_id is required.")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            if session is None:
                raise CopilotStoreNotFoundError(f"Copilot session not found: {session_id}")
            if session.archived_at is None:
                return session
            restored = CopilotSession(
                session_id=session.session_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=now_utc(),
                active_domain=session.active_domain,
                active_context_fingerprint=session.active_context_fingerprint,
                turn_count=session.turn_count,
                memo_count=session.memo_count,
                report_count=session.report_count,
                artifact_count=session.artifact_count,
                warnings=session.warnings,
                archived_at=None,
            )
            self._write_json(self.sessions_dir / f"{safe_session_id}.json", self._session_to_json(restored))
        return restored

    def rename_session(
        self,
        session_id: str,
        *,
        title: str,
        expected_updated_at: datetime | None = None,
    ) -> CopilotSession:
        safe_session_id = self._safe_id(session_id)
        next_title = str(title or "").strip()
        if not safe_session_id:
            raise CopilotStoreError("session_id is required.")
        if not next_title:
            raise CopilotStoreError("Session title cannot be empty.")
        with self._lock:
            session = self._load_session_path(self.sessions_dir / f"{safe_session_id}.json")
            if session is None:
                raise CopilotStoreNotFoundError(f"Copilot session not found: {session_id}")
            self._assert_not_conflicted(session.updated_at, expected_updated_at, "session")
            renamed = CopilotSession(
                session_id=session.session_id,
                title=next_title[:96],
                created_at=session.created_at,
                updated_at=now_utc(),
                active_domain=session.active_domain,
                active_context_fingerprint=session.active_context_fingerprint,
                turn_count=session.turn_count,
                memo_count=session.memo_count,
                report_count=session.report_count,
                artifact_count=session.artifact_count,
                warnings=session.warnings,
                archived_at=session.archived_at,
            )
            self._write_json(self.sessions_dir / f"{safe_session_id}.json", self._session_to_json(renamed))
        return renamed

    def delete_session(self, session_id: str, *, confirmation: str) -> CopilotDeleteResult:
        safe_session_id = self._safe_id(session_id)
        if not safe_session_id:
            raise CopilotStoreError("session_id is required.")
        if confirmation != safe_session_id:
            raise CopilotStoreConflictError("Session deletion confirmation does not match the target session id.")
        with self._lock:
            session_path = self.sessions_dir / f"{safe_session_id}.json"
            session = self._load_session_path(session_path)
            if session is None:
                raise CopilotStoreNotFoundError(f"Copilot session not found: {session_id}")
            timestamp = now_utc().strftime("%Y%m%dT%H%M%S%f")
            trash_root = self.trash_dir / f"{safe_session_id}-{timestamp}"
            trash_root.mkdir(parents=True, exist_ok=False)
            counts = {"sessions": 0, "turns": 0, "snapshots": 0, "artifacts": 0}
            self._move_to_trash(session_path, trash_root / "sessions" / session_path.name)
            counts["sessions"] = 1
            turns = self._load_turns_unlocked(safe_session_id)
            turns_path = self.turns_dir / safe_session_id
            if turns_path.exists():
                self._move_to_trash(turns_path, trash_root / "turns" / safe_session_id)
                counts["turns"] = len(turns)
            for turn in turns:
                snapshot_path = self.snapshots_dir / f"{turn.context_snapshot_id}.json"
                if snapshot_path.exists():
                    self._move_to_trash(snapshot_path, trash_root / "snapshots" / snapshot_path.name)
                    counts["snapshots"] += 1
            for artifact in self._load_artifacts_unlocked():
                if artifact.session_id != safe_session_id:
                    continue
                artifact_path = self.artifacts_dir / f"{artifact.artifact_id}.json"
                if artifact_path.exists():
                    self._move_to_trash(artifact_path, trash_root / "artifacts" / artifact_path.name)
                    counts["artifacts"] += 1
        return CopilotDeleteResult(
            deleted_id=safe_session_id,
            deleted_type="session",
            recoverable=True,
            archived_path=str(trash_root.relative_to(self.base_dir)),
            deleted_counts=counts,
        )

    def update_memo(self, memo_id: str, *, title: str | None = None, body: str | None = None) -> CopilotMemo:
        artifact = self.update_artifact(memo_id, title=title, body=body)
        if artifact.artifact_type != "memo":
            raise CopilotStoreConflictError(f"Copilot artifact is not a memo: {memo_id}")
        return self._artifact_to_memo(artifact)

    def update_artifact(
        self,
        artifact_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        expected_updated_at: datetime | None = None,
    ) -> CopilotArtifact:
        safe_artifact_id = self._safe_id(artifact_id)
        if not safe_artifact_id:
            raise CopilotStoreError("artifact_id is required.")
        with self._lock:
            artifact = self._load_artifact_path(self.artifacts_dir / f"{safe_artifact_id}.json")
            if artifact is None:
                raise CopilotStoreNotFoundError(f"Copilot artifact not found: {artifact_id}")
            self._assert_not_conflicted(artifact.updated_at, expected_updated_at, "artifact")
            next_title = str(title if title is not None else artifact.title).strip()
            next_body = str(body if body is not None else artifact.body).strip()
            if not next_title:
                raise CopilotStoreError("Artifact title cannot be empty.")
            if not next_body:
                raise CopilotStoreError("Artifact body cannot be empty.")
            updated = CopilotArtifact(
                artifact_id=artifact.artifact_id,
                session_id=artifact.session_id,
                artifact_type=artifact.artifact_type,
                template=artifact.template,
                title=next_title[:140],
                body=next_body,
                source_turn_ids=artifact.source_turn_ids,
                source_memo_ids=artifact.source_memo_ids,
                source_snapshot_ids=artifact.source_snapshot_ids,
                unavailable_source_turn_ids=artifact.unavailable_source_turn_ids,
                context_fingerprints=artifact.context_fingerprints,
                source_backed_claims=artifact.source_backed_claims,
                inferred_claims=artifact.inferred_claims,
                assumptions=artifact.assumptions,
                missing_data=artifact.missing_data,
                warnings=artifact.warnings,
                warning_provenance=artifact.warning_provenance,
                tool_trace_summary=artifact.tool_trace_summary,
                sources=artifact.sources,
                provider_metadata=artifact.provider_metadata,
                created_at=artifact.created_at,
                updated_at=now_utc(),
                source_provider=artifact.source_provider,
                origin=artifact.origin,
                transformation_note=artifact.transformation_note,
            )
            self._write_json(
                self.artifacts_dir / f"{safe_artifact_id}.json",
                self._artifact_to_json(updated),
            )
            session = self._load_session_path(self.sessions_dir / f"{artifact.session_id}.json")
            if session is not None:
                self._refresh_session_counts_unlocked(session, updated_at=updated.updated_at)
        return updated

    def duplicate_artifact(self, artifact_id: str, *, title: str | None = None) -> CopilotArtifact:
        safe_artifact_id = self._safe_id(artifact_id)
        if not safe_artifact_id:
            raise CopilotStoreError("artifact_id is required.")
        with self._lock:
            artifact = self._load_artifact_path(self.artifacts_dir / f"{safe_artifact_id}.json")
            if artifact is None:
                raise CopilotStoreNotFoundError(f"Copilot artifact not found: {artifact_id}")
            now = now_utc()
            duplicate = CopilotArtifact(
                artifact_id=new_copilot_id(artifact.artifact_type),
                session_id=artifact.session_id,
                artifact_type=artifact.artifact_type,
                template=artifact.template,
                title=(str(title or "").strip() or f"{artifact.title} Copy")[:140],
                body=artifact.body,
                source_turn_ids=artifact.source_turn_ids,
                source_memo_ids=artifact.source_memo_ids,
                source_snapshot_ids=artifact.source_snapshot_ids,
                unavailable_source_turn_ids=artifact.unavailable_source_turn_ids,
                context_fingerprints=artifact.context_fingerprints,
                source_backed_claims=artifact.source_backed_claims,
                inferred_claims=artifact.inferred_claims,
                assumptions=artifact.assumptions,
                missing_data=artifact.missing_data,
                warnings=artifact.warnings,
                warning_provenance=artifact.warning_provenance,
                tool_trace_summary=artifact.tool_trace_summary,
                sources=artifact.sources,
                provider_metadata=artifact.provider_metadata,
                created_at=now,
                updated_at=now,
                source_provider=artifact.source_provider,
                origin="copilot_store.duplicate_artifact",
                transformation_note=(
                    f"Duplicated from {artifact.artifact_id}; provenance and evidence were copied without "
                    "reclassification or source substitution."
                ),
            )
            self._write_json(
                self.artifacts_dir / f"{duplicate.artifact_id}.json",
                self._artifact_to_json(duplicate),
            )
            session = self._load_session_path(self.sessions_dir / f"{artifact.session_id}.json")
            if session is not None:
                self._refresh_session_counts_unlocked(session, updated_at=now)
        return duplicate

    def delete_artifact(self, artifact_id: str, *, confirmation: str) -> CopilotDeleteResult:
        safe_artifact_id = self._safe_id(artifact_id)
        if not safe_artifact_id:
            raise CopilotStoreError("artifact_id is required.")
        if confirmation != safe_artifact_id:
            raise CopilotStoreConflictError("Artifact deletion confirmation does not match the target artifact id.")
        with self._lock:
            artifact_path = self.artifacts_dir / f"{safe_artifact_id}.json"
            artifact = self._load_artifact_path(artifact_path)
            if artifact is None:
                raise CopilotStoreNotFoundError(f"Copilot artifact not found: {artifact_id}")
            timestamp = now_utc().strftime("%Y%m%dT%H%M%S%f")
            trash_path = self.trash_dir / f"artifact-{safe_artifact_id}-{timestamp}.json"
            self._move_to_trash(artifact_path, trash_path)
            session = self._load_session_path(self.sessions_dir / f"{artifact.session_id}.json")
            if session is not None:
                self._refresh_session_counts_unlocked(session, updated_at=now_utc())
        return CopilotDeleteResult(
            deleted_id=safe_artifact_id,
            deleted_type="artifact",
            recoverable=True,
            archived_path=str(trash_path.relative_to(self.base_dir)),
            deleted_counts={"artifacts": 1},
        )

    def save_mutation(self, mutation: CopilotDraftMutation) -> CopilotDraftMutation:
        safe_mutation_id = self._safe_id(mutation.mutation_id)
        if not safe_mutation_id:
            raise ValueError("mutation_id is required.")
        with self._lock:
            self._write_json(self.mutations_dir / f"{safe_mutation_id}.json", self._mutation_to_json(mutation))
        return mutation

    def get_mutation(self, mutation_id: str) -> CopilotDraftMutation | None:
        safe_mutation_id = self._safe_id(mutation_id)
        if not safe_mutation_id:
            return None
        with self._lock:
            return self._load_mutation_path(self.mutations_dir / f"{safe_mutation_id}.json")

    def get_memo(self, memo_id: str) -> CopilotMemo | None:
        artifact = self.get_artifact(memo_id)
        if artifact is None or artifact.artifact_type != "memo":
            return None
        return self._artifact_to_memo(artifact)

    def get_artifact(self, artifact_id: str) -> CopilotArtifact | None:
        safe_artifact_id = self._safe_id(artifact_id)
        if not safe_artifact_id:
            return None
        with self._lock:
            artifact = self._load_artifact_path(self.artifacts_dir / f"{safe_artifact_id}.json")
            if artifact is None:
                return None
            turns = self._load_turns_unlocked(artifact.session_id)
            return self._with_artifact_availability(
                artifact,
                {turn.turn_id for turn in turns},
            )

    def export_artifact_markdown(self, artifact_id: str) -> str:
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise CopilotStoreNotFoundError(f"Copilot artifact not found: {artifact_id}")
        lines = [
            artifact.body.strip(),
            "",
            "---",
            "",
            "## Artifact Provenance",
            f"- Artifact: {artifact.artifact_id}",
            f"- Type / template: {artifact.artifact_type} / {artifact.template}",
            f"- Session: {artifact.session_id}",
            f"- Source turns: {', '.join(artifact.source_turn_ids) if artifact.source_turn_ids else 'none'}",
            f"- Source memos: {', '.join(artifact.source_memo_ids) if artifact.source_memo_ids else 'none'}",
            f"- Context snapshots: {', '.join(artifact.source_snapshot_ids) if artifact.source_snapshot_ids else 'none'}",
            f"- Context fingerprints: {', '.join(artifact.context_fingerprints) if artifact.context_fingerprints else 'none'}",
            f"- Created: {artifact.created_at.isoformat()}",
            f"- Updated: {artifact.updated_at.isoformat()}",
            "",
            "## Source-Backed Claims",
            *(
                [
                    f"- {claim.claim} [{', '.join(claim.evidence_refs)}]"
                    for claim in artifact.source_backed_claims
                ]
                or ["- None recorded."]
            ),
            "",
            "## Inferred Claims",
            *([f"- {item}" for item in artifact.inferred_claims] or ["- None recorded."]),
            "",
            "## Assumptions",
            *([f"- {item}" for item in artifact.assumptions] or ["- None recorded."]),
            "",
            "## Missing Data",
            *([f"- {item}" for item in artifact.missing_data] or ["- None recorded."]),
            "",
            "## Warnings",
            *([f"- {item}" for item in artifact.warnings] or ["- None recorded."]),
            "",
            "## Warning Provenance",
            *(
                [
                    (
                        f"- {row.warning} "
                        f"[event={row.event_type or 'unknown'}; step={row.step_id or 'none'}; "
                        f"sources={', '.join(row.source_ids) or 'none'}]"
                    )
                    for row in artifact.warning_provenance
                ]
                or ["- None recorded."]
            ),
            "",
            "## Provider and Model Metadata",
            *(
                [
                    (
                        f"- Turn `{row.turn_id}`: role={row.role}; effort={row.reasoning_effort or 'unspecified'}; "
                        f"requested={row.requested_provider or 'auto'}/{row.requested_model or 'auto'}; "
                        f"resolved={row.resolved_provider or 'unknown'}/{row.resolved_model or 'unknown'}; "
                        f"run={row.run_id or 'none'}; status={row.terminal_status or 'unknown'}"
                    )
                    for row in artifact.provider_metadata
                ]
                or ["- None recorded."]
            ),
            "",
            "## Tool Trace Summary",
            *(
                [
                    (
                        f"- `{row.tool_name}`: {row.summary} "
                        f"[status={row.status}; sources={', '.join(row.source_ids) or 'none'}]"
                    )
                    for row in artifact.tool_trace_summary
                ]
                or ["- None recorded."]
            ),
            "",
            "## Sources",
            *(
                [
                    (
                        f"- `{source.source_id}`: {source.label} "
                        f"({source.provider}; {source.kind}; {source.origin}; "
                        f"retrieved={source.retrieved_at.isoformat() if source.retrieved_at else 'unknown'})"
                    )
                    for source in artifact.sources
                ]
                or ["- None recorded."]
            ),
            "",
            f"Source provider: {artifact.source_provider}",
            f"Origin: {artifact.origin}",
        ]
        if artifact.transformation_note:
            lines.append(f"Transformation: {artifact.transformation_note}")
        return "\n".join(lines).strip() + "\n"

    def _load_turns_unlocked(self, session_id: str) -> list[CopilotTurn]:
        turns_dir = self.turns_dir / session_id
        turns = [item for path in turns_dir.glob("*.json") if (item := self._load_turn_path(path))]
        return sorted(turns, key=lambda item: item.turn_index)

    def _load_memos_unlocked(self) -> list[CopilotMemo]:
        return [
            self._artifact_to_memo(item)
            for item in self._load_artifacts_unlocked()
            if item.artifact_type == "memo"
        ]

    def _load_artifacts_unlocked(self) -> list[CopilotArtifact]:
        return [
            item
            for path in self.artifacts_dir.glob("*.json")
            if (item := self._load_artifact_path(path))
        ]

    def _load_session_path(self, path: Path) -> CopilotSession | None:
        payload = self._load_json(path, record_type="session")
        if payload is None:
            return None
        return CopilotSession(
            session_id=str(payload.get("session_id") or path.stem),
            title=str(payload.get("title") or "Copilot Session"),
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            updated_at=self._parse_datetime(payload.get("updated_at")) or now_utc(),
            active_domain=payload.get("active_domain"),
            active_context_fingerprint=payload.get("active_context_fingerprint"),
            turn_count=int(payload.get("turn_count") or 0),
            memo_count=int(payload.get("memo_count") or 0),
            report_count=int(payload.get("report_count") or 0),
            artifact_count=int(payload.get("artifact_count") or payload.get("memo_count") or 0),
            warnings=list(payload.get("warnings") or []),
            archived_at=self._parse_datetime(payload.get("archived_at")),
        )

    def _load_snapshot_path(self, path: Path) -> CopilotContextSnapshot | None:
        payload = self._load_json(path, record_type="snapshot")
        if payload is None:
            return None
        return CopilotContextSnapshot(
            snapshot_id=str(payload.get("snapshot_id") or path.stem),
            domain=str(payload.get("domain") or "synthesis"),
            context_fingerprint=payload.get("context_fingerprint"),
            current_tab=str(payload.get("current_tab") or "copilot"),
            workspace_mode=payload.get("workspace_mode"),
            summary=dict(payload.get("summary") or {}),
            request_context=dict(payload.get("request_context") or {}),
            selected_scope_domains=list(payload.get("selected_scope_domains") or []),
            source_ids=list(payload.get("source_ids") or []),
            warnings=list(payload.get("warnings") or []),
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            read_only_safety=dict(payload.get("read_only_safety") or {}),
        )

    def _load_turn_path(self, path: Path) -> CopilotTurn | None:
        payload = self._load_json(path, record_type="turn")
        if payload is None:
            return None
        result = self._result_from_json(dict(payload.get("result") or {}))
        return CopilotTurn(
            turn_id=str(payload.get("turn_id") or path.stem),
            session_id=str(payload.get("session_id") or path.parent.name),
            turn_index=int(payload.get("turn_index") or 0),
            domain=str(payload.get("domain") or result.domain),
            prompt=str(payload.get("prompt") or ""),
            context_snapshot_id=str(payload.get("context_snapshot_id") or ""),
            result=result,
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            role=str(payload.get("role") or ("research_operator" if result.operator_events else "research_agent")),
            reasoning_effort=payload.get("reasoning_effort"),
            selected_scope_domains=list(payload.get("selected_scope_domains") or []),
            context_fingerprint=payload.get("context_fingerprint"),
            requested_provider=payload.get("requested_provider"),
            requested_model=payload.get("requested_model"),
            resolved_provider=payload.get("resolved_provider") or result.provider,
            resolved_model=payload.get("resolved_model") or result.model,
            run_id=payload.get("run_id") or self._result_run_id(result),
            terminal_status=payload.get("terminal_status") or result.status,
            cancellation_outcome=payload.get("cancellation_outcome") or self._cancellation_outcome(result),
            usage=self._usage_from_json(payload.get("usage")),
            research_plan=self._research_plan_from_json(payload.get("research_plan")),
            operator_plan=self._operator_plan_from_json(payload.get("operator_plan")),
            run_events=[
                self._run_event_from_json(item)
                for item in list(payload.get("run_events") or [])
                if isinstance(item, dict)
            ],
            confirmations=[
                self._confirmation_from_json(item)
                for item in list(payload.get("confirmations") or [])
                if isinstance(item, dict)
            ],
            artifact_refs=[
                self._artifact_ref_from_json(item)
                for item in list(payload.get("artifact_refs") or [])
                if isinstance(item, dict)
            ],
            mutation_refs=[
                self._artifact_ref_from_json(item)
                for item in list(payload.get("mutation_refs") or [])
                if isinstance(item, dict)
            ],
            trace_state=self._trace_state_from_json(payload.get("trace_state"), result),
        )

    def _load_memo_path(self, path: Path) -> CopilotMemo | None:
        payload = self._load_json(path, record_type="memo")
        if payload is None:
            return None
        return CopilotMemo(
            memo_id=str(payload.get("memo_id") or path.stem),
            session_id=str(payload.get("session_id") or ""),
            title=str(payload.get("title") or "Copilot Memo"),
            body=str(payload.get("body") or ""),
            source_turn_ids=list(payload.get("source_turn_ids") or []),
            source_snapshot_ids=list(payload.get("source_snapshot_ids") or []),
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            updated_at=self._parse_datetime(payload.get("updated_at")) or now_utc(),
            warnings=list(payload.get("warnings") or []),
            source_provider=str(payload.get("source_provider") or "gamma_copilot"),
            origin=str(payload.get("origin") or "copilot_store.memo"),
            transformation_note=payload.get("transformation_note"),
        )

    def _load_artifact_path(self, path: Path) -> CopilotArtifact | None:
        payload = self._load_json(path, record_type="artifact")
        if payload is None:
            return None
        sources = [
            self._source_from_json(item)
            for item in list(payload.get("sources") or [])
            if isinstance(item, dict)
        ]
        known_source_ids = {source.source_id for source in sources}
        source_backed: list[ResearchClaim] = []
        inferred = list(payload.get("inferred_claims") or [])
        warnings = list(payload.get("warnings") or [])
        for item in list(payload.get("source_backed_claims") or []):
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim") or "").strip()
            refs = list(
                dict.fromkeys(
                    str(ref)
                    for ref in list(item.get("evidence_refs") or [])
                    if str(ref) in known_source_ids
                )
            )
            if claim and refs:
                source_backed.append(ResearchClaim(claim=claim, evidence_refs=refs))
            elif claim:
                inferred.append(claim)
                warnings.append(
                    f"Reclassified artifact claim without resolvable evidence refs: {claim[:80]}"
                )
        return CopilotArtifact(
            artifact_id=str(payload.get("artifact_id") or path.stem),
            session_id=str(payload.get("session_id") or ""),
            artifact_type=str(payload.get("artifact_type") or "memo"),
            template=str(payload.get("template") or "concise_memo"),
            title=str(payload.get("title") or "Copilot Artifact"),
            body=str(payload.get("body") or ""),
            source_turn_ids=list(payload.get("source_turn_ids") or []),
            source_memo_ids=list(payload.get("source_memo_ids") or []),
            source_snapshot_ids=list(payload.get("source_snapshot_ids") or []),
            unavailable_source_turn_ids=list(payload.get("unavailable_source_turn_ids") or []),
            context_fingerprints=list(payload.get("context_fingerprints") or []),
            source_backed_claims=source_backed,
            inferred_claims=list(dict.fromkeys(item for item in inferred if item)),
            assumptions=list(payload.get("assumptions") or []),
            missing_data=list(payload.get("missing_data") or []),
            warnings=list(dict.fromkeys(item for item in warnings if item)),
            warning_provenance=[
                self._warning_provenance_from_json(item)
                for item in list(payload.get("warning_provenance") or [])
                if isinstance(item, dict)
            ],
            tool_trace_summary=[
                self._tool_trace_summary_from_json(item)
                for item in list(payload.get("tool_trace_summary") or [])
                if isinstance(item, dict)
            ],
            sources=sources,
            provider_metadata=[
                self._provider_metadata_from_json(item)
                for item in list(payload.get("provider_metadata") or [])
                if isinstance(item, dict)
            ],
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            updated_at=self._parse_datetime(payload.get("updated_at")) or now_utc(),
            source_provider=str(payload.get("source_provider") or "gamma_copilot"),
            origin=str(payload.get("origin") or "copilot_store.artifact"),
            transformation_note=payload.get("transformation_note"),
        )

    def _load_mutation_path(self, path: Path) -> CopilotDraftMutation | None:
        payload = self._load_json(path, record_type="mutation")
        if payload is None:
            return None
        return CopilotDraftMutation(
            mutation_id=str(payload.get("mutation_id") or path.stem),
            domain=str(payload.get("domain") or ""),
            tool_id=str(payload.get("tool_id") or ""),
            action_type=str(payload.get("action_type") or ""),
            target_id=str(payload.get("target_id") or ""),
            target_label=str(payload.get("target_label") or ""),
            status=str(payload.get("status") or "pending"),
            requires_confirmation=bool(payload.get("requires_confirmation", True)),
            confirmation_token=str(payload.get("confirmation_token") or ""),
            diff=[
                CopilotMutationDiffEntry(
                    path=str(item.get("path") or ""),
                    label=str(item.get("label") or ""),
                    before=item.get("before"),
                    after=item.get("after"),
                    unit=item.get("unit"),
                    change_type=str(item.get("change_type") or "update"),
                )
                for item in list(payload.get("diff") or [])
                if isinstance(item, dict)
            ],
            rendered_diff=list(payload.get("rendered_diff") or []),
            proposed_payload=dict(payload.get("proposed_payload") or {}),
            rationale=payload.get("rationale"),
            warnings=list(payload.get("warnings") or []),
            source_ids=list(payload.get("source_ids") or []),
            rollback_snapshot_id=payload.get("rollback_snapshot_id"),
            created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
            expires_at=self._parse_datetime(payload.get("expires_at")),
            applied_at=self._parse_datetime(payload.get("applied_at")),
            source_provider=str(payload.get("source_provider") or "gamma_copilot"),
            origin=str(payload.get("origin") or "copilot_store.mutation"),
            transformation_note=payload.get("transformation_note"),
        )

    def _load_json(self, path: Path, *, record_type: str) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            quarantined = self._quarantine_file(path, record_type=record_type, reason="malformed")
            self._record_storage_warning(
                record_type=record_type,
                action="quarantined",
                path=quarantined or path,
                message=(
                    f"Skipped a malformed Copilot {record_type} record and preserved it in quarantine "
                    "for inspection."
                ),
            )
            return None
        if not isinstance(payload, dict):
            quarantined = self._quarantine_file(path, record_type=record_type, reason="non-object")
            self._record_storage_warning(
                record_type=record_type,
                action="quarantined",
                path=quarantined or path,
                message=(
                    f"Skipped a non-object Copilot {record_type} record and preserved it in quarantine "
                    "for inspection."
                ),
            )
            return None
        version = self._coerce_schema_version(payload.get("schema_version"))
        if version > CURRENT_COPILOT_STORE_SCHEMA_VERSION:
            self._record_storage_warning(
                record_type=record_type,
                action="skipped_future_version",
                path=path,
                message=(
                    f"Skipped Copilot {record_type} schema version {version}; this Gamma build supports "
                    f"up to version {CURRENT_COPILOT_STORE_SCHEMA_VERSION}. The original file was not changed."
                ),
            )
            return None
        if version not in SUPPORTED_COPILOT_STORE_SCHEMA_VERSIONS:
            quarantined = self._quarantine_file(path, record_type=record_type, reason=f"unsupported-v{version}")
            self._record_storage_warning(
                record_type=record_type,
                action="quarantined_unsupported_version",
                path=quarantined or path,
                message=(
                    f"Skipped unsupported Copilot {record_type} schema version {version} and preserved "
                    "the original file in quarantine."
                ),
            )
            return None
        if version < CURRENT_COPILOT_STORE_SCHEMA_VERSION:
            payload = self._migrate_payload(record_type, payload, version)
            self._write_json(path, payload, preserve_existing=False)
            self._record_storage_warning(
                record_type=record_type,
                action="migrated",
                path=path,
                message=(
                    f"Migrated Copilot {record_type} record from schema version {version} to "
                    f"{CURRENT_COPILOT_STORE_SCHEMA_VERSION}."
                ),
            )
        required_fields = {
            "session": ("session_id", "title"),
            "snapshot": ("snapshot_id", "domain"),
            "turn": ("turn_id", "session_id", "result"),
            "memo": ("memo_id", "session_id", "body"),
            "artifact": ("artifact_id", "session_id", "artifact_type", "body"),
            "mutation": ("mutation_id", "status"),
        }.get(record_type, ())
        missing_fields = [
            field
            for field in required_fields
            if payload.get(field) is None or payload.get(field) == ""
        ]
        if missing_fields:
            self._record_storage_warning(
                record_type=record_type,
                action="recovered_partial_record",
                path=path,
                message=(
                    f"Recovered a partial Copilot {record_type} record with safe defaults for: "
                    f"{', '.join(missing_fields)}."
                ),
            )
        return payload

    def _write_json(
        self,
        path: Path,
        payload: dict[str, Any],
        *,
        preserve_existing: bool = True,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        next_payload = dict(payload)
        if preserve_existing and path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = None
            if isinstance(existing, dict):
                next_payload = {**existing, **next_payload}
        serialized = json.dumps(next_payload, indent=2, sort_keys=True, default=str)
        temp_path = path.with_name(f"{path.name}.tmp")
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)

    def _migrate_payload(
        self,
        record_type: str,
        payload: dict[str, Any],
        source_version: int,
    ) -> dict[str, Any]:
        migrated = dict(payload)
        version = source_version
        if version == 0:
            migrated.setdefault("created_at", migrated.get("updated_at"))
            migrated.setdefault("updated_at", migrated.get("created_at"))
            version = 1
        if version == 1:
            if record_type == "session":
                migrated.setdefault("report_count", 0)
                migrated.setdefault("artifact_count", migrated.get("memo_count", 0))
            elif record_type == "snapshot":
                migrated.setdefault("request_context", {})
                migrated.setdefault("selected_scope_domains", [])
            elif record_type == "turn":
                result = migrated.get("result") if isinstance(migrated.get("result"), dict) else {}
                operator_events = list(result.get("operator_events") or [])
                migrated.setdefault("role", "research_operator" if operator_events else "research_agent")
                migrated.setdefault("reasoning_effort", None)
                migrated.setdefault("selected_scope_domains", [])
                migrated.setdefault("context_fingerprint", None)
                migrated.setdefault("requested_provider", None)
                migrated.setdefault("requested_model", None)
                migrated.setdefault("resolved_provider", result.get("provider"))
                migrated.setdefault("resolved_model", result.get("model"))
                migrated.setdefault("run_id", result.get("response_id"))
                migrated.setdefault("terminal_status", result.get("status", "ready"))
                migrated.setdefault("cancellation_outcome", None)
                migrated.setdefault("research_plan", None)
                migrated.setdefault("operator_plan", None)
                migrated.setdefault("run_events", [])
            elif record_type in {"memo", "artifact"}:
                migrated.setdefault("artifact_type", "memo")
                migrated.setdefault("template", "concise_memo")
                migrated.setdefault("source_memo_ids", [])
                migrated.setdefault("context_fingerprints", [])
            version = 2
        if version == 2:
            if record_type == "session":
                migrated.setdefault("report_count", 0)
                migrated.setdefault("artifact_count", migrated.get("memo_count", 0))
            elif record_type == "snapshot":
                migrated.setdefault("request_context", {})
                migrated.setdefault("selected_scope_domains", [])
            elif record_type == "turn":
                result = migrated.get("result") if isinstance(migrated.get("result"), dict) else {}
                migrated.setdefault("usage", {})
                migrated.setdefault("confirmations", [])
                migrated.setdefault("artifact_refs", [])
                migrated.setdefault("mutation_refs", [])
                migrated.setdefault(
                    "trace_state",
                    {
                        "event_count": len(list(migrated.get("run_events") or [])),
                        "tool_trace_count": len(list(result.get("tool_traces") or [])),
                        "operator_event_count": len(list(result.get("operator_events") or [])),
                        "source_count": len(list(result.get("sources") or [])),
                        "warning_count": len(list(result.get("warnings") or [])),
                        "bounded": True,
                        "replay_complete": True,
                    },
                )
            elif record_type in {"memo", "artifact"}:
                for key, default in (
                    ("unavailable_source_turn_ids", []),
                    ("source_backed_claims", []),
                    ("inferred_claims", []),
                    ("assumptions", []),
                    ("missing_data", []),
                    ("warning_provenance", []),
                    ("tool_trace_summary", []),
                    ("sources", []),
                    ("provider_metadata", []),
                ):
                    migrated.setdefault(key, default)
            version = 3
        migrated["schema_version"] = CURRENT_COPILOT_STORE_SCHEMA_VERSION
        return migrated

    @staticmethod
    def _session_to_json(session: CopilotSession) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "active_domain": session.active_domain,
            "active_context_fingerprint": session.active_context_fingerprint,
            "turn_count": session.turn_count,
            "memo_count": session.memo_count,
            "report_count": session.report_count,
            "artifact_count": session.artifact_count,
            "warnings": list(session.warnings),
            "archived_at": session.archived_at.isoformat() if session.archived_at else None,
        }

    @staticmethod
    def _snapshot_to_json(snapshot: CopilotContextSnapshot) -> dict[str, Any]:
        payload = asdict(snapshot)
        payload["schema_version"] = CURRENT_COPILOT_STORE_SCHEMA_VERSION
        payload["created_at"] = snapshot.created_at.isoformat()
        return payload

    @classmethod
    def _turn_to_json(cls, turn: CopilotTurn) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "turn_id": turn.turn_id,
            "session_id": turn.session_id,
            "turn_index": turn.turn_index,
            "domain": turn.domain,
            "prompt": turn.prompt,
            "context_snapshot_id": turn.context_snapshot_id,
            "result": cls._result_to_json(turn.result),
            "created_at": turn.created_at.isoformat(),
            "role": turn.role,
            "reasoning_effort": turn.reasoning_effort,
            "selected_scope_domains": list(turn.selected_scope_domains),
            "context_fingerprint": turn.context_fingerprint,
            "requested_provider": turn.requested_provider,
            "requested_model": turn.requested_model,
            "resolved_provider": turn.resolved_provider,
            "resolved_model": turn.resolved_model,
            "run_id": turn.run_id,
            "terminal_status": turn.terminal_status,
            "cancellation_outcome": turn.cancellation_outcome,
            "usage": asdict(turn.usage),
            "research_plan": cls._dataclass_to_json(turn.research_plan),
            "operator_plan": cls._dataclass_to_json(turn.operator_plan),
            "run_events": [
                {
                    "run_id": event.run_id,
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data,
                    "result": cls._result_to_json(event.result) if event.result is not None else None,
                }
                for event in turn.run_events
            ],
            "confirmations": [cls._dataclass_to_json(item) for item in turn.confirmations],
            "artifact_refs": [asdict(item) for item in turn.artifact_refs],
            "mutation_refs": [asdict(item) for item in turn.mutation_refs],
            "trace_state": asdict(turn.trace_state),
        }

    @staticmethod
    def _memo_to_json(memo: CopilotMemo) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "memo_id": memo.memo_id,
            "session_id": memo.session_id,
            "title": memo.title,
            "body": memo.body,
            "source_turn_ids": list(memo.source_turn_ids),
            "source_snapshot_ids": list(memo.source_snapshot_ids),
            "created_at": memo.created_at.isoformat(),
            "updated_at": memo.updated_at.isoformat(),
            "warnings": list(memo.warnings),
            "source_provider": memo.source_provider,
            "origin": memo.origin,
            "transformation_note": memo.transformation_note,
        }

    @staticmethod
    def _artifact_to_json(artifact: CopilotArtifact) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "artifact_id": artifact.artifact_id,
            "session_id": artifact.session_id,
            "artifact_type": artifact.artifact_type,
            "template": artifact.template,
            "title": artifact.title,
            "body": artifact.body,
            "source_turn_ids": list(artifact.source_turn_ids),
            "source_memo_ids": list(artifact.source_memo_ids),
            "source_snapshot_ids": list(artifact.source_snapshot_ids),
            "unavailable_source_turn_ids": list(artifact.unavailable_source_turn_ids),
            "context_fingerprints": list(artifact.context_fingerprints),
            "source_backed_claims": [asdict(item) for item in artifact.source_backed_claims],
            "inferred_claims": list(artifact.inferred_claims),
            "assumptions": list(artifact.assumptions),
            "missing_data": list(artifact.missing_data),
            "warnings": list(artifact.warnings),
            "warning_provenance": [
                CopilotStore._dataclass_to_json(item)
                for item in artifact.warning_provenance
            ],
            "tool_trace_summary": [
                CopilotStore._dataclass_to_json(item)
                for item in artifact.tool_trace_summary
            ],
            "sources": [
                {
                    **asdict(source),
                    "retrieved_at": CopilotStore._datetime_to_json(source.retrieved_at),
                }
                for source in artifact.sources
            ],
            "provider_metadata": [asdict(item) for item in artifact.provider_metadata],
            "created_at": artifact.created_at.isoformat(),
            "updated_at": artifact.updated_at.isoformat(),
            "source_provider": artifact.source_provider,
            "origin": artifact.origin,
            "transformation_note": artifact.transformation_note,
        }

    @staticmethod
    def _mutation_to_json(mutation: CopilotDraftMutation) -> dict[str, Any]:
        return {
            "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
            "mutation_id": mutation.mutation_id,
            "domain": mutation.domain,
            "tool_id": mutation.tool_id,
            "action_type": mutation.action_type,
            "target_id": mutation.target_id,
            "target_label": mutation.target_label,
            "status": mutation.status,
            "requires_confirmation": mutation.requires_confirmation,
            "confirmation_token": mutation.confirmation_token,
            "diff": [asdict(item) for item in mutation.diff],
            "rendered_diff": list(mutation.rendered_diff),
            "proposed_payload": mutation.proposed_payload,
            "rationale": mutation.rationale,
            "warnings": list(mutation.warnings),
            "source_ids": list(mutation.source_ids),
            "rollback_snapshot_id": mutation.rollback_snapshot_id,
            "created_at": mutation.created_at.isoformat(),
            "expires_at": mutation.expires_at.isoformat() if mutation.expires_at else None,
            "applied_at": mutation.applied_at.isoformat() if mutation.applied_at else None,
            "source_provider": mutation.source_provider,
            "origin": mutation.origin,
            "transformation_note": mutation.transformation_note,
        }

    @staticmethod
    def _result_to_json(result: CopilotResearchCardResult) -> dict[str, Any]:
        return {
            "domain": result.domain,
            "current_tab": result.current_tab,
            "status": result.status,
            "provider": result.provider,
            "model": result.model,
            "response_id": result.response_id,
            "message": result.message,
            "card": asdict(result.card) if result.card else None,
            "sources": [
                {
                    **asdict(source),
                    "retrieved_at": CopilotStore._datetime_to_json(source.retrieved_at),
                }
                for source in result.sources
            ],
            "tool_traces": [asdict(trace) for trace in result.tool_traces],
            "operator_events": [
                {
                    **asdict(event),
                    "timestamp": CopilotStore._datetime_to_json(event.timestamp),
                }
                for event in result.operator_events
            ],
            "warnings": list(result.warnings),
        }

    @staticmethod
    def _datetime_to_json(value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        if value:
            return str(value)
        return None

    @classmethod
    def _result_from_json(cls, payload: dict[str, Any]) -> CopilotResearchCardResult:
        result = CopilotResearchCardResult(
            domain=str(payload.get("domain") or "synthesis"),
            current_tab=str(payload.get("current_tab") or payload.get("domain") or "copilot"),
            status=str(payload.get("status") or "ready"),
            provider=str(payload.get("provider") or "unknown"),
            model=payload.get("model"),
            response_id=payload.get("response_id"),
            message=payload.get("message"),
            card=cls._card_from_json(payload.get("card")),
            sources=[cls._source_from_json(item) for item in list(payload.get("sources") or []) if isinstance(item, dict)],
            tool_traces=[cls._trace_from_json(item) for item in list(payload.get("tool_traces") or []) if isinstance(item, dict)],
            operator_events=[
                cls._operator_event_from_json(item)
                for item in list(payload.get("operator_events") or [])
                if isinstance(item, dict)
            ],
            warnings=list(payload.get("warnings") or []),
        )
        return resolve_result_evidence(result)

    @staticmethod
    def _card_from_json(payload: Any) -> ResearchCard | None:
        if not isinstance(payload, dict):
            return None
        return ResearchCard(
            title=str(payload.get("title") or ""),
            hypothesis=str(payload.get("hypothesis") or ""),
            rationale=str(payload.get("rationale") or ""),
            required_data=list(payload.get("required_data") or []),
            proposed_test=str(payload.get("proposed_test") or ""),
            confounders=list(payload.get("confounders") or []),
            next_steps=list(payload.get("next_steps") or []),
            caveats=list(payload.get("caveats") or []),
            source_backed_claims=[
                ResearchClaim(claim=str(item.get("claim") or ""), evidence_refs=list(item.get("evidence_refs") or []))
                for item in list(payload.get("source_backed_claims") or [])
                if isinstance(item, dict)
            ],
            inferred_claims=list(payload.get("inferred_claims") or []),
        )

    @classmethod
    def _source_from_json(cls, payload: dict[str, Any]) -> CopilotSourceRef:
        return CopilotSourceRef(
            source_id=str(payload.get("source_id") or ""),
            label=str(payload.get("label") or ""),
            kind=str(payload.get("kind") or ""),
            provider=str(payload.get("provider") or ""),
            origin=str(payload.get("origin") or ""),
            description=payload.get("description"),
            retrieved_at=cls._parse_datetime(payload.get("retrieved_at")),
        )

    @staticmethod
    def _trace_from_json(payload: dict[str, Any]) -> CopilotToolTrace:
        return CopilotToolTrace(
            tool_name=str(payload.get("tool_name") or ""),
            summary=str(payload.get("summary") or ""),
            arguments=dict(payload.get("arguments") or {}),
            source_ids=list(payload.get("source_ids") or []),
        )

    @classmethod
    def _operator_event_from_json(cls, payload: dict[str, Any]) -> CopilotOperatorProgressEvent:
        return CopilotOperatorProgressEvent(
            run_id=str(payload.get("run_id") or ""),
            event_id=str(payload.get("event_id") or ""),
            sequence=int(payload.get("sequence") or 0),
            event_type=str(payload.get("event_type") or ""),
            timestamp=cls._parse_datetime(payload.get("timestamp")) or now_utc(),
            step_id=payload.get("step_id"),
            tool_id=payload.get("tool_id"),
            title=payload.get("title"),
            message=payload.get("message"),
            payload=dict(payload.get("payload") or {}),
            source_ids=list(payload.get("source_ids") or []),
            warnings=list(payload.get("warnings") or []),
        )

    @classmethod
    def _research_plan_from_json(cls, payload: Any) -> CopilotResearchPlan | None:
        if not isinstance(payload, dict) or not payload.get("intent"):
            return None
        return CopilotResearchPlan(
            intent=str(payload.get("intent") or ""),
            target_entities=[
                CopilotResearchPlanEntity(
                    kind=str(item.get("kind") or ""),
                    id=str(item.get("id") or ""),
                    label=item.get("label"),
                    confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
                )
                for item in list(payload.get("target_entities") or [])
                if isinstance(item, dict)
            ],
            depth_profile=str(payload.get("depth_profile") or "standard"),
            domain_plan=[
                CopilotResearchPlanDomain(
                    domain=str(item.get("domain") or ""),
                    depth=str(item.get("depth") or "light"),
                    reason=str(item.get("reason") or ""),
                    action_type=str(item.get("action_type") or "read_context"),
                    planned_tools=list(item.get("planned_tools") or []),
                    required_context=list(item.get("required_context") or []),
                    estimated_tool_calls=int(item.get("estimated_tool_calls") or 0),
                    estimated_provider_calls=int(item.get("estimated_provider_calls") or 0),
                    estimated_latency_ms=int(item.get("estimated_latency_ms") or 0),
                )
                for item in list(payload.get("domain_plan") or [])
                if isinstance(item, dict)
            ],
            domain_decisions=[
                CopilotResearchPlanDomainDecision(
                    domain=str(item.get("domain") or ""),
                    used=bool(item.get("used")),
                    reason=str(item.get("reason") or ""),
                )
                for item in list(payload.get("domain_decisions") or [])
                if isinstance(item, dict)
            ],
            max_tool_calls=int(payload.get("max_tool_calls") or 0),
            max_provider_calls=int(payload.get("max_provider_calls") or 0),
            max_elapsed_ms=int(payload.get("max_elapsed_ms") or 0),
            requires_confirmation=bool(payload.get("requires_confirmation")),
            expected_artifacts=list(payload.get("expected_artifacts") or []),
            warnings=list(payload.get("warnings") or []),
            generated_at=cls._parse_datetime(payload.get("generated_at")) or now_utc(),
            source_provider=str(payload.get("source_provider") or "gamma_planner"),
            origin=str(payload.get("origin") or "copilot_service.plan_research"),
            transformation_note=payload.get("transformation_note"),
        )

    @classmethod
    def _operator_plan_from_json(cls, payload: Any) -> CopilotOperatorPlan | None:
        if not isinstance(payload, dict) or not payload.get("intent"):
            return None
        return CopilotOperatorPlan(
            intent=str(payload.get("intent") or ""),
            target_entities=[
                CopilotResearchPlanEntity(
                    kind=str(item.get("kind") or ""),
                    id=str(item.get("id") or ""),
                    label=item.get("label"),
                    confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
                )
                for item in list(payload.get("target_entities") or [])
                if isinstance(item, dict)
            ],
            depth_profile=str(payload.get("depth_profile") or "standard"),
            role=str(payload.get("role") or "research_operator"),
            research_plan=cls._research_plan_from_json(payload.get("research_plan")),
            steps=[
                CopilotOperatorPlanStep(
                    step_id=str(item.get("step_id") or ""),
                    order=int(item.get("order") or 0),
                    title=str(item.get("title") or ""),
                    domain=str(item.get("domain") or ""),
                    action_type=str(item.get("action_type") or "read_context"),
                    tool_id=item.get("tool_id"),
                    status=str(item.get("status") or "planned"),
                    permission_policy=str(item.get("permission_policy") or "automatic"),
                    requires_confirmation=bool(item.get("requires_confirmation")),
                    expected_artifacts=list(item.get("expected_artifacts") or []),
                    rationale=item.get("rationale"),
                    stop_conditions=list(item.get("stop_conditions") or []),
                    estimated_latency_ms=int(item.get("estimated_latency_ms") or 0),
                    warnings=list(item.get("warnings") or []),
                )
                for item in list(payload.get("steps") or [])
                if isinstance(item, dict)
            ],
            confirmation_checkpoints=[
                CopilotOperatorConfirmationCheckpoint(
                    checkpoint_id=str(item.get("checkpoint_id") or ""),
                    after_step_id=str(item.get("after_step_id") or ""),
                    reason=str(item.get("reason") or ""),
                    required_for_tool_ids=list(item.get("required_for_tool_ids") or []),
                    default_policy=str(item.get("default_policy") or "confirmation_required"),
                )
                for item in list(payload.get("confirmation_checkpoints") or [])
                if isinstance(item, dict)
            ],
            max_tool_calls=int(payload.get("max_tool_calls") or 0),
            max_provider_calls=int(payload.get("max_provider_calls") or 0),
            max_elapsed_ms=int(payload.get("max_elapsed_ms") or 0),
            requires_confirmation=bool(payload.get("requires_confirmation")),
            expected_artifacts=list(payload.get("expected_artifacts") or []),
            warnings=list(payload.get("warnings") or []),
            generated_at=cls._parse_datetime(payload.get("generated_at")) or now_utc(),
            source_provider=str(payload.get("source_provider") or "gamma_operator_planner"),
            origin=str(payload.get("origin") or "copilot_service.plan_research_operator"),
            transformation_note=payload.get("transformation_note"),
        )

    @classmethod
    def _run_event_from_json(cls, payload: dict[str, Any]) -> CopilotRunEvent:
        return CopilotRunEvent(
            run_id=str(payload.get("run_id") or ""),
            sequence=int(payload.get("sequence") or 0),
            event_type=str(payload.get("event_type") or payload.get("event") or ""),
            timestamp=cls._parse_datetime(payload.get("timestamp")) or now_utc(),
            data=dict(payload.get("data") or {}),
            result=(
                cls._result_from_json(dict(payload.get("result") or {}))
                if isinstance(payload.get("result"), dict)
                else None
            ),
        )

    @classmethod
    def _confirmation_from_json(cls, payload: dict[str, Any]) -> CopilotConfirmationState:
        return CopilotConfirmationState(
            checkpoint_id=str(payload.get("checkpoint_id") or ""),
            status=str(payload.get("status") or "pending"),
            required_for_tool_ids=list(payload.get("required_for_tool_ids") or []),
            mutation_id=payload.get("mutation_id"),
            confirmation_token=payload.get("confirmation_token"),
            rollback_snapshot_id=payload.get("rollback_snapshot_id"),
            created_at=cls._parse_datetime(payload.get("created_at")),
            resolved_at=cls._parse_datetime(payload.get("resolved_at")),
            warnings=list(payload.get("warnings") or []),
        )

    @staticmethod
    def _artifact_ref_from_json(payload: dict[str, Any]) -> CopilotArtifactReference:
        return CopilotArtifactReference(
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_type=str(payload.get("artifact_type") or "unknown"),
            status=str(payload.get("status") or "created"),
            mutation_id=payload.get("mutation_id"),
            rollback_snapshot_id=payload.get("rollback_snapshot_id"),
        )

    @staticmethod
    def _usage_from_json(payload: Any) -> CopilotUsageRecord:
        row = payload if isinstance(payload, dict) else {}
        return CopilotUsageRecord(
            input_tokens=int(row.get("input_tokens") or 0),
            output_tokens=int(row.get("output_tokens") or 0),
            reasoning_tokens=int(row.get("reasoning_tokens") or 0),
            total_tokens=int(row.get("total_tokens") or 0),
            cache_read_tokens=int(row.get("cache_read_tokens") or row.get("cached_tokens") or 0),
            cache_write_tokens=int(row.get("cache_write_tokens") or 0),
            provider_calls=int(row.get("provider_calls") or 0),
            tool_calls=int(row.get("tool_calls") or 0),
            raw=dict(row.get("raw") or {}),
        )

    @classmethod
    def _trace_state_from_json(
        cls,
        payload: Any,
        result: CopilotResearchCardResult,
    ) -> CopilotTraceState:
        row = payload if isinstance(payload, dict) else {}
        return CopilotTraceState(
            event_count=int(row.get("event_count") or 0),
            tool_trace_count=int(row.get("tool_trace_count") or len(result.tool_traces)),
            operator_event_count=int(row.get("operator_event_count") or len(result.operator_events)),
            source_count=int(row.get("source_count") or len(result.sources)),
            warning_count=int(row.get("warning_count") or len(result.warnings)),
            bounded=bool(row.get("bounded", True)),
            replay_complete=bool(row.get("replay_complete", True)),
        )

    @staticmethod
    def _warning_provenance_from_json(payload: dict[str, Any]) -> CopilotReportWarningProvenance:
        return CopilotReportWarningProvenance(
            warning=str(payload.get("warning") or ""),
            source_ids=list(payload.get("source_ids") or []),
            tool_name=payload.get("tool_name"),
            step_id=payload.get("step_id"),
            event_type=payload.get("event_type"),
            event_id=payload.get("event_id"),
            sequence=int(payload["sequence"]) if payload.get("sequence") is not None else None,
        )

    @staticmethod
    def _tool_trace_summary_from_json(payload: dict[str, Any]) -> CopilotReportToolTraceSummary:
        return CopilotReportToolTraceSummary(
            tool_name=str(payload.get("tool_name") or ""),
            summary=str(payload.get("summary") or ""),
            source_ids=list(payload.get("source_ids") or []),
            status=str(payload.get("status") or "recorded"),
            step_id=payload.get("step_id"),
            event_type=payload.get("event_type"),
            output_summary=dict(payload.get("output_summary") or {}),
            warnings=list(payload.get("warnings") or []),
        )

    @staticmethod
    def _provider_metadata_from_json(payload: dict[str, Any]) -> CopilotArtifactProviderMetadata:
        return CopilotArtifactProviderMetadata(
            turn_id=str(payload.get("turn_id") or ""),
            role=str(payload.get("role") or "research_agent"),
            reasoning_effort=payload.get("reasoning_effort"),
            requested_provider=payload.get("requested_provider"),
            requested_model=payload.get("requested_model"),
            resolved_provider=payload.get("resolved_provider"),
            resolved_model=payload.get("resolved_model"),
            run_id=payload.get("run_id"),
            terminal_status=payload.get("terminal_status"),
        )

    @staticmethod
    def _result_run_id(result: CopilotResearchCardResult) -> str | None:
        if result.operator_events:
            return result.operator_events[0].run_id or result.response_id
        return result.response_id

    @staticmethod
    def _cancellation_outcome(result: CopilotResearchCardResult) -> str | None:
        if result.status != "cancelled":
            return None
        message = str(result.message or "").lower()
        return "timeout" if "timed out" in message else "user_cancelled"

    @classmethod
    def _usage_from_events(cls, events: list[CopilotRunEvent]) -> CopilotUsageRecord:
        usage: dict[str, Any] = {}
        tool_calls = 0
        for event in events:
            if event.event_type == "usage":
                usage.update(event.data)
            if event.event_type in {"tool.call", "tool.result"}:
                tool_calls += 1
        usage.setdefault("tool_calls", tool_calls)
        return cls._usage_from_json(usage)

    @classmethod
    def _confirmations_from_result(
        cls,
        result: CopilotResearchCardResult,
    ) -> list[CopilotConfirmationState]:
        confirmations: list[CopilotConfirmationState] = []
        for event in result.operator_events:
            if event.event_type not in {"confirmation-needed", "confirmation.needed"}:
                continue
            confirmations.append(
                CopilotConfirmationState(
                    checkpoint_id=str(
                        event.payload.get("checkpoint_id")
                        or event.step_id
                        or event.event_id
                    ),
                    status=str(event.payload.get("status") or "pending"),
                    required_for_tool_ids=list(event.payload.get("required_for_tool_ids") or []),
                    mutation_id=event.payload.get("mutation_id"),
                    confirmation_token=event.payload.get("confirmation_token"),
                    rollback_snapshot_id=event.payload.get("rollback_snapshot_id"),
                    created_at=event.timestamp,
                    warnings=list(event.warnings),
                )
            )
        return confirmations

    @staticmethod
    def _artifact_refs_from_result(
        result: CopilotResearchCardResult,
    ) -> list[CopilotArtifactReference]:
        refs: list[CopilotArtifactReference] = []
        for event in result.operator_events:
            if event.event_type not in {"artifact-created", "artifact.created"}:
                continue
            artifact_id = str(event.payload.get("artifact_id") or "")
            if artifact_id:
                refs.append(
                    CopilotArtifactReference(
                        artifact_id=artifact_id,
                        artifact_type=str(event.payload.get("artifact_type") or "operator_artifact"),
                        status=str(event.payload.get("status") or "created"),
                    )
                )
        return refs

    @staticmethod
    def _mutation_refs_from_result(
        result: CopilotResearchCardResult,
    ) -> list[CopilotArtifactReference]:
        refs: list[CopilotArtifactReference] = []
        for event in result.operator_events:
            mutation_id = event.payload.get("mutation_id")
            if not mutation_id:
                continue
            refs.append(
                CopilotArtifactReference(
                    artifact_id=str(event.payload.get("artifact_id") or mutation_id),
                    artifact_type="mutation",
                    status=str(event.payload.get("status") or "pending"),
                    mutation_id=str(mutation_id),
                    rollback_snapshot_id=event.payload.get("rollback_snapshot_id"),
                )
            )
        return refs

    @classmethod
    def _research_plan_from_summary(cls, summary: dict[str, Any]) -> CopilotResearchPlan | None:
        return cls._research_plan_from_json(summary.get("plan"))

    @classmethod
    def _operator_plan_from_summary(cls, summary: dict[str, Any]) -> CopilotOperatorPlan | None:
        return cls._operator_plan_from_json(summary.get("operator_plan"))

    @classmethod
    def _artifact_provenance(cls, turns: list[CopilotTurn]) -> dict[str, Any]:
        sources: dict[str, CopilotSourceRef] = {}
        claims: list[ResearchClaim] = []
        inferred: list[str] = []
        assumptions: list[str] = []
        warnings: list[str] = []
        warning_provenance: list[CopilotReportWarningProvenance] = []
        traces: list[CopilotReportToolTraceSummary] = []
        seen_claims: set[tuple[str, tuple[str, ...]]] = set()
        seen_traces: set[tuple[str, str]] = set()
        for turn in turns:
            for source in turn.result.sources:
                sources.setdefault(source.source_id, source)
            card = turn.result.card
            if card is not None:
                if card.hypothesis:
                    inferred.append(f"{turn.domain}: {card.hypothesis}")
                inferred.extend(card.inferred_claims)
                assumptions.extend(card.confounders)
                assumptions.extend(card.caveats)
                for claim in card.source_backed_claims:
                    refs = tuple(
                        dict.fromkeys(
                            ref for ref in claim.evidence_refs if ref in {
                                source.source_id for source in turn.result.sources
                            }
                        )
                    )
                    key = (claim.claim, refs)
                    if claim.claim and refs and key not in seen_claims:
                        seen_claims.add(key)
                        claims.append(ResearchClaim(claim=claim.claim, evidence_refs=list(refs)))
                    elif claim.claim:
                        inferred.append(claim.claim)
            warnings.extend(turn.result.warnings)
            for trace in turn.result.tool_traces:
                key = (trace.tool_name, trace.summary)
                if key in seen_traces:
                    continue
                seen_traces.add(key)
                traces.append(
                    CopilotReportToolTraceSummary(
                        tool_name=trace.tool_name,
                        summary=trace.summary,
                        source_ids=list(trace.source_ids),
                    )
                )
            for event in turn.result.operator_events:
                for warning in event.warnings:
                    warnings.append(warning)
                    warning_provenance.append(
                        CopilotReportWarningProvenance(
                            warning=warning,
                            source_ids=list(event.source_ids),
                            tool_name=event.tool_id,
                            step_id=event.step_id,
                            event_type=event.event_type,
                            event_id=event.event_id,
                            sequence=event.sequence,
                        )
                    )
                if event.event_type == "warning" and event.message:
                    warnings.append(event.message)
                    warning_provenance.append(
                        CopilotReportWarningProvenance(
                            warning=event.message,
                            source_ids=list(event.source_ids),
                            tool_name=event.tool_id,
                            step_id=event.step_id,
                            event_type=event.event_type,
                            event_id=event.event_id,
                            sequence=event.sequence,
                        )
                    )
        warnings = list(dict.fromkeys(item for item in warnings if item))
        missing_markers = ("missing", "skipped", "unavailable", "stale", "no ", "failed")
        missing_data = [
            warning
            for warning in warnings
            if any(marker in warning.lower() for marker in missing_markers)
        ]
        return {
            "source_backed_claims": claims,
            "inferred_claims": list(dict.fromkeys(item for item in inferred if item)),
            "assumptions": list(dict.fromkeys(item for item in assumptions if item)),
            "missing_data": missing_data,
            "warnings": warnings,
            "warning_provenance": warning_provenance,
            "tool_trace_summary": traces,
            "sources": list(sources.values()),
        }

    @staticmethod
    def _build_report_body(title: str, provenance: dict[str, Any]) -> str:
        lines = [f"# {title}", "", "## Source-Backed Claims"]
        claims = list(provenance.get("source_backed_claims") or [])
        lines.extend(
            f"- {claim.claim} [{', '.join(claim.evidence_refs)}]"
            for claim in claims
        )
        if not claims:
            lines.append("- None recorded.")
        sections = (
            ("Inferred Claims", provenance.get("inferred_claims") or []),
            ("Assumptions", provenance.get("assumptions") or []),
            ("Missing Data", provenance.get("missing_data") or []),
            ("Warnings", provenance.get("warnings") or []),
        )
        for heading, items in sections:
            lines.extend(["", f"## {heading}"])
            lines.extend(f"- {item}" for item in items)
            if not items:
                lines.append("- None recorded.")
        return "\n".join(lines).strip()

    @staticmethod
    def _artifact_to_memo(artifact: CopilotArtifact) -> CopilotMemo:
        return CopilotMemo(
            memo_id=artifact.artifact_id,
            session_id=artifact.session_id,
            title=artifact.title,
            body=artifact.body,
            source_turn_ids=list(artifact.source_turn_ids),
            source_snapshot_ids=list(artifact.source_snapshot_ids),
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
            warnings=list(artifact.warnings),
            source_provider=artifact.source_provider,
            origin=artifact.origin,
            transformation_note=artifact.transformation_note,
        )

    @staticmethod
    def _with_artifact_availability(
        artifact: CopilotArtifact,
        available_turn_ids: set[str],
    ) -> CopilotArtifact:
        unavailable = [
            turn_id for turn_id in artifact.source_turn_ids if turn_id not in available_turn_ids
        ]
        availability_warnings = [
            f"Source turn is unavailable after restart or recovery: {turn_id}"
            for turn_id in unavailable
        ]
        return CopilotArtifact(
            **{
                **artifact.__dict__,
                "unavailable_source_turn_ids": unavailable,
                "warnings": list(dict.fromkeys([*artifact.warnings, *availability_warnings])),
            }
        )

    def _refresh_session_counts_unlocked(
        self,
        session: CopilotSession,
        *,
        updated_at: datetime,
    ) -> CopilotSession:
        artifacts = [
            item for item in self._load_artifacts_unlocked() if item.session_id == session.session_id
        ]
        updated = CopilotSession(
            session_id=session.session_id,
            title=session.title,
            created_at=session.created_at,
            updated_at=updated_at,
            active_domain=session.active_domain,
            active_context_fingerprint=session.active_context_fingerprint,
            turn_count=len(self._load_turns_unlocked(session.session_id)),
            memo_count=sum(item.artifact_type == "memo" for item in artifacts),
            report_count=sum(item.artifact_type == "report" for item in artifacts),
            artifact_count=len(artifacts),
            warnings=session.warnings,
            archived_at=session.archived_at,
        )
        self._write_json(
            self.sessions_dir / f"{session.session_id}.json",
            self._session_to_json(updated),
        )
        return updated

    @staticmethod
    def _selected_ids(values: list[str] | None) -> list[str]:
        return list(
            dict.fromkeys(
                CopilotStore._safe_id(value)
                for value in values or []
                if CopilotStore._safe_id(value)
            )
        )

    @staticmethod
    def _assert_not_conflicted(
        actual_updated_at: datetime,
        expected_updated_at: datetime | None,
        record_type: str,
    ) -> None:
        if expected_updated_at is None:
            return
        if actual_updated_at != expected_updated_at:
            raise CopilotStoreConflictError(
                f"Copilot {record_type} changed since it was loaded. Reload before saving again."
            )

    @staticmethod
    def _move_to_trash(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)

    @staticmethod
    def _dataclass_to_json(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [CopilotStore._dataclass_to_json(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): CopilotStore._dataclass_to_json(item)
                for key, item in value.items()
            }
        if hasattr(value, "__dataclass_fields__"):
            return CopilotStore._dataclass_to_json(asdict(value))
        return value

    def _load_recovery_log(self) -> None:
        if not self.recovery_log_path.exists():
            return
        try:
            payload = json.loads(self.recovery_log_path.read_text(encoding="utf-8"))
        except Exception:
            return
        rows = payload.get("warnings") if isinstance(payload, dict) else None
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, dict):
                continue
            self._storage_warnings.append(
                CopilotStorageWarning(
                    warning_id=str(item.get("warning_id") or new_copilot_id("storage_warning")),
                    record_type=str(item.get("record_type") or "unknown"),
                    action=str(item.get("action") or "skipped"),
                    message=str(item.get("message") or "Copilot storage warning."),
                    path=str(item.get("path") or ""),
                    created_at=self._parse_datetime(item.get("created_at")) or now_utc(),
                )
            )

    def _record_storage_warning(
        self,
        *,
        record_type: str,
        action: str,
        path: Path,
        message: str,
    ) -> None:
        try:
            safe_path = str(path.relative_to(self.base_dir))
        except ValueError:
            safe_path = path.name
        key = (record_type, action, safe_path, message)
        if any(
            (item.record_type, item.action, item.path, item.message) == key
            for item in self._storage_warnings
        ):
            return
        warning = CopilotStorageWarning(
            warning_id=new_copilot_id("storage_warning"),
            record_type=record_type,
            action=action,
            message=message,
            path=safe_path,
        )
        self._storage_warnings.append(warning)
        self._storage_warnings = self._storage_warnings[-200:]
        self._write_json(
            self.recovery_log_path,
            {
                "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
                "warnings": [
                    {
                        **asdict(item),
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in self._storage_warnings
                ],
            },
            preserve_existing=False,
        )

    def _quarantine_file(
        self,
        path: Path,
        *,
        record_type: str,
        reason: str,
    ) -> Path | None:
        if not path.exists():
            return None
        timestamp = now_utc().strftime("%Y%m%dT%H%M%S%f")
        target = (
            self.quarantine_dir
            / record_type
            / f"{path.name}.{reason}.{timestamp}.{uuid4().hex[:8]}.preserved"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
        return target

    def _recover_interrupted_writes(self) -> None:
        for temp_path in list(self.base_dir.rglob("*.json.tmp")):
            if self.quarantine_dir in temp_path.parents or self.trash_dir in temp_path.parents:
                continue
            target = temp_path.with_name(temp_path.name[:-4])
            record_type = self._record_type_for_path(target)
            if target.exists():
                quarantined = self._quarantine_file(
                    temp_path,
                    record_type=record_type,
                    reason="interrupted-stale-temp",
                )
                self._record_storage_warning(
                    record_type=record_type,
                    action="preserved_interrupted_temp",
                    path=quarantined or temp_path,
                    message=(
                        f"Preserved an interrupted Copilot {record_type} temporary write; the authoritative "
                        "record was already intact."
                    ),
                )
                continue
            try:
                payload = json.loads(temp_path.read_text(encoding="utf-8"))
            except Exception:
                payload = None
            version = self._coerce_schema_version(payload.get("schema_version")) if isinstance(payload, dict) else -1
            if isinstance(payload, dict) and version <= CURRENT_COPILOT_STORE_SCHEMA_VERSION:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temp_path, target)
                self._record_storage_warning(
                    record_type=record_type,
                    action="recovered_interrupted_write",
                    path=target,
                    message=f"Recovered an interrupted Copilot {record_type} atomic write.",
                )
            else:
                quarantined = self._quarantine_file(
                    temp_path,
                    record_type=record_type,
                    reason="interrupted-invalid-temp",
                )
                self._record_storage_warning(
                    record_type=record_type,
                    action="quarantined_interrupted_write",
                    path=quarantined or temp_path,
                    message=(
                        f"Skipped an unreadable interrupted Copilot {record_type} write and preserved "
                        "the temporary file in quarantine."
                    ),
                )

    def _migrate_legacy_memos(self) -> None:
        for path in self.memos_dir.glob("*.json"):
            memo = self._load_memo_path(path)
            if memo is None:
                continue
            artifact_path = self.artifacts_dir / f"{memo.memo_id}.json"
            if artifact_path.exists():
                continue
            turns = self._load_turns_unlocked(memo.session_id)
            selected_turns = [
                turn for turn in turns if turn.turn_id in set(memo.source_turn_ids)
            ]
            provenance = self._artifact_provenance(selected_turns)
            artifact = CopilotArtifact(
                artifact_id=memo.memo_id,
                session_id=memo.session_id,
                artifact_type="memo",
                template="concise_memo",
                title=memo.title,
                body=memo.body,
                source_turn_ids=memo.source_turn_ids,
                source_snapshot_ids=memo.source_snapshot_ids,
                context_fingerprints=list(
                    dict.fromkeys(
                        turn.context_fingerprint
                        for turn in selected_turns
                        if turn.context_fingerprint
                    )
                ),
                source_backed_claims=provenance["source_backed_claims"],
                inferred_claims=provenance["inferred_claims"],
                assumptions=provenance["assumptions"],
                missing_data=provenance["missing_data"],
                warnings=list(dict.fromkeys([*memo.warnings, *provenance["warnings"]])),
                warning_provenance=provenance["warning_provenance"],
                tool_trace_summary=provenance["tool_trace_summary"],
                sources=provenance["sources"],
                provider_metadata=[
                    CopilotArtifactProviderMetadata(
                        turn_id=turn.turn_id,
                        role=turn.role,
                        reasoning_effort=turn.reasoning_effort,
                        requested_provider=turn.requested_provider,
                        requested_model=turn.requested_model,
                        resolved_provider=turn.resolved_provider,
                        resolved_model=turn.resolved_model,
                        run_id=turn.run_id,
                        terminal_status=turn.terminal_status,
                    )
                    for turn in selected_turns
                ],
                created_at=memo.created_at,
                updated_at=memo.updated_at,
                source_provider=memo.source_provider,
                origin=memo.origin,
                transformation_note=(
                    "Migrated from the legacy Copilot memo record; the original memo file is retained "
                    "for inspection and repeated migration is idempotent."
                ),
            )
            self._write_json(artifact_path, self._artifact_to_json(artifact))
            self._record_storage_warning(
                record_type="memo",
                action="migrated_to_artifact",
                path=artifact_path,
                message="Migrated a legacy Copilot memo into the unified artifact contract.",
            )

    def _record_type_for_path(self, path: Path) -> str:
        mapping = {
            self.sessions_dir: "session",
            self.snapshots_dir: "snapshot",
            self.turns_dir: "turn",
            self.memos_dir: "memo",
            self.artifacts_dir: "artifact",
            self.mutations_dir: "mutation",
        }
        for directory, record_type in mapping.items():
            if directory == path.parent or directory in path.parents:
                return record_type
        return "record"

    @staticmethod
    def _coerce_schema_version(value: Any) -> int:
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    @staticmethod
    def _build_memo_body(title: str, turns: list[CopilotTurn], notes: str | None) -> str:
        lines = [f"# {title}", "", "## Source Turns"]
        if notes:
            lines.extend(["", str(notes).strip(), ""])
        for turn in turns:
            card = turn.result.card
            lines.append(f"### Turn {turn.turn_index + 1} / {turn.domain}")
            if turn.prompt:
                lines.append(f"Prompt: {turn.prompt}")
            if card:
                lines.extend(
                    [
                        f"Hypothesis: {card.hypothesis}",
                        f"Rationale: {card.rationale}",
                        f"Proposed test: {card.proposed_test}",
                    ]
                )
                if card.next_steps:
                    lines.append("Next steps:")
                    lines.extend(f"- {item}" for item in card.next_steps)
            if turn.result.warnings:
                lines.append("Warnings:")
                lines.extend(f"- {item}" for item in turn.result.warnings)
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _session_title(
        title: str | None,
        domain: str,
        result: CopilotResearchCardResult,
        prompt: str | None = None,
    ) -> str:
        explicit = str(title or "").strip()
        if explicit:
            return explicit[:96]
        card_title = result.card.title if result.card else ""
        prompt_title = str(prompt or "").strip().replace("\n", " ")
        if prompt_title:
            return prompt_title[:96]
        return (card_title or f"{domain.replace('_', ' ').title()} Copilot Session")[:96]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _safe_id(value: str | None) -> str:
        return "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"_", "-"})
