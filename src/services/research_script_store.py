from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from src.application.request_limits import MAX_RESEARCH_SCRIPT_RUN_HISTORY
from src.models.research_script import (
    ResearchScript,
    ResearchScriptInputFile,
    ResearchScriptInputSnapshot,
    ResearchScriptOutput,
    ResearchScriptRevision,
    ResearchScriptRun,
    ResearchScriptStorageDiagnostics,
)
from src.utils.time import now_utc


CURRENT_RESEARCH_SCRIPT_STORE_SCHEMA_VERSION = 1
T = TypeVar("T")
_SAFE_FILENAME_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
_WINDOWS_RESERVED_FILENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def is_safe_research_script_filename(value: str | None) -> bool:
    text = str(value or "").strip()
    stem = text.split(".", 1)[0].upper()
    return bool(
        text
        and text not in {".", ".."}
        and all(character in _SAFE_FILENAME_CHARS for character in text)
        and stem not in _WINDOWS_RESERVED_FILENAMES
        and Path(text).name == text
    )


class ResearchScriptStoreError(RuntimeError):
    pass


class ResearchScriptStoreConflictError(ResearchScriptStoreError):
    pass


class ResearchScriptStoreCorruptionError(ResearchScriptStoreError):
    pass


class ResearchScriptStore:
    """Versioned, atomic local persistence for immutable Script workspace records."""

    def __init__(
        self,
        base_dir: str | Path = "data/research_scripts",
        *,
        run_history_limit: int = MAX_RESEARCH_SCRIPT_RUN_HISTORY,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.scripts_dir = self.base_dir / "scripts"
        self.revisions_dir = self.base_dir / "revisions"
        self.inputs_dir = self.base_dir / "inputs"
        self.runs_dir = self.base_dir / "runs"
        self.outputs_dir = self.base_dir / "outputs"
        self.quarantine_dir = self.base_dir / "quarantine"
        self.run_history_limit = max(int(run_history_limit), 1)
        self._lock = threading.RLock()
        self._storage_warnings: list[str] = []
        for path in (
            self.scripts_dir,
            self.revisions_dir,
            self.inputs_dir,
            self.runs_dir,
            self.outputs_dir,
            self.quarantine_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._recover_interrupted_writes_unlocked()
            removed_count, removed_bytes = self._cleanup_orphaned_outputs_unlocked()
            if removed_count:
                self._storage_warnings.append(
                    f"Removed {removed_count} orphaned retained output artifacts ({removed_bytes} bytes)."
                )

    @property
    def storage_warnings(self) -> list[str]:
        with self._lock:
            return list(self._storage_warnings)

    def create_script(self, script: ResearchScript, revision: ResearchScriptRevision) -> None:
        safe_script_id = self._require_safe_id(script.script_id, "script_id")
        safe_revision_id = self._require_safe_id(revision.revision_id, "revision_id")
        if revision.script_id != script.script_id or revision.revision_id != script.canonical_revision_id:
            raise ResearchScriptStoreConflictError("Initial revision does not match the script canonical revision.")
        script_path = self.scripts_dir / f"{safe_script_id}.json"
        revision_path = self.revisions_dir / safe_script_id / f"{safe_revision_id}.json"
        with self._lock:
            if script_path.exists() or revision_path.exists():
                raise ResearchScriptStoreConflictError(f"Research script already exists: {script.script_id}")
            self._write_record_atomic(revision_path, "research_script_revision", revision)
            try:
                self._write_record_atomic(script_path, "research_script", script)
            except Exception:
                revision_path.unlink(missing_ok=True)
                raise

    def list_scripts(self) -> list[ResearchScript]:
        with self._lock:
            scripts = [
                item
                for path in sorted(self.scripts_dir.glob("*.json"))
                if (item := self._load_record(path, "research_script", self._parse_script)) is not None
            ]
        return sorted(scripts, key=lambda item: (item.updated_at, item.script_id), reverse=True)

    def load_script(self, script_id: str) -> ResearchScript | None:
        safe_id = self._safe_id(script_id)
        if not safe_id:
            return None
        with self._lock:
            return self._load_record(
                self.scripts_dir / f"{safe_id}.json",
                "research_script",
                self._parse_script,
            )

    def set_script_status(self, script_id: str, status: str) -> ResearchScript:
        safe_id = self._require_safe_id(script_id, "script_id")
        if status not in {"active", "archived", "discarded"}:
            raise ResearchScriptStoreConflictError(f"Unsupported research script status: {status}")
        script_path = self.scripts_dir / f"{safe_id}.json"
        with self._lock:
            script = self._load_record(script_path, "research_script", self._parse_script)
            if script is None:
                raise ResearchScriptStoreConflictError(f"Research script not found: {script_id}")
            if script.status == status:
                return script
            updated = replace(script, status=status, updated_at=now_utc())
            self._write_record_atomic(script_path, "research_script", updated)
            return updated

    def list_revisions(self, script_id: str) -> list[ResearchScriptRevision]:
        safe_id = self._safe_id(script_id)
        if not safe_id:
            return []
        with self._lock:
            revisions = [
                item
                for path in sorted((self.revisions_dir / safe_id).glob("*.json"))
                if (item := self._load_record(path, "research_script_revision", self._parse_revision)) is not None
            ]
        return sorted(revisions, key=lambda item: (item.revision_number, item.created_at))

    def load_revision(self, script_id: str, revision_id: str) -> ResearchScriptRevision | None:
        safe_script_id = self._safe_id(script_id)
        safe_revision_id = self._safe_id(revision_id)
        if not safe_script_id or not safe_revision_id:
            return None
        with self._lock:
            return self._load_record(
                self.revisions_dir / safe_script_id / f"{safe_revision_id}.json",
                "research_script_revision",
                self._parse_revision,
            )

    def append_canonical_revision(
        self,
        revision: ResearchScriptRevision,
        *,
        expected_parent_sha256: str,
    ) -> ResearchScript:
        safe_script_id = self._require_safe_id(revision.script_id, "script_id")
        safe_revision_id = self._require_safe_id(revision.revision_id, "revision_id")
        revision_path = self.revisions_dir / safe_script_id / f"{safe_revision_id}.json"
        script_path = self.scripts_dir / f"{safe_script_id}.json"
        with self._lock:
            script = self._load_record(script_path, "research_script", self._parse_script)
            if script is None:
                raise ResearchScriptStoreConflictError(f"Research script not found: {revision.script_id}")
            parent = self.load_revision(script.script_id, script.canonical_revision_id)
            if parent is None:
                raise ResearchScriptStoreCorruptionError("Canonical revision metadata is missing.")
            if parent.source_sha256 != expected_parent_sha256:
                raise ResearchScriptStoreConflictError(
                    "The canonical source changed. Reload the script before saving a new revision."
                )
            if revision.parent_revision_id != parent.revision_id:
                raise ResearchScriptStoreConflictError("Revision parent does not match the current canonical revision.")
            if revision.revision_number != parent.revision_number + 1:
                raise ResearchScriptStoreConflictError("Revision number is not the next immutable sequence value.")
            if revision_path.exists():
                raise ResearchScriptStoreConflictError(f"Revision already exists: {revision.revision_id}")
            if revision.status != "canonical":
                raise ResearchScriptStoreConflictError("Canonical append requires canonical revision status.")
            updated_script = replace(
                script,
                canonical_revision_id=revision.revision_id,
                status="active",
                updated_at=revision.created_at,
            )
            self._write_record_atomic(revision_path, "research_script_revision", revision)
            try:
                self._write_record_atomic(script_path, "research_script", updated_script)
            except Exception:
                revision_path.unlink(missing_ok=True)
                raise
            return updated_script

    def append_staged_revision(
        self,
        revision: ResearchScriptRevision,
        *,
        expected_parent_sha256: str,
    ) -> None:
        safe_script_id = self._require_safe_id(revision.script_id, "script_id")
        safe_revision_id = self._require_safe_id(revision.revision_id, "revision_id")
        script = self.load_script(safe_script_id)
        if script is None:
            raise ResearchScriptStoreConflictError("Research script does not exist.")
        parent = self.load_revision(safe_script_id, script.canonical_revision_id)
        if parent is None:
            raise ResearchScriptStoreCorruptionError("Canonical revision is unavailable.")
        if revision.status != "staged" or revision.created_by != "operator":
            raise ResearchScriptStoreConflictError("Only Operator-authored staged revisions may be appended.")
        if parent.source_sha256 != expected_parent_sha256:
            raise ResearchScriptStoreConflictError("Staged revision parent hash is stale.")
        if revision.parent_revision_id != parent.revision_id:
            raise ResearchScriptStoreConflictError("Staged revision parent is not canonical.")
        revision_path = self.revisions_dir / safe_script_id / f"{safe_revision_id}.json"
        with self._lock:
            if revision_path.exists():
                raise ResearchScriptStoreConflictError(f"Revision already exists: {revision.revision_id}")
            self._write_record_atomic(revision_path, "research_script_revision", revision)

    def resolve_staged_revision(
        self,
        script_id: str,
        revision_id: str,
        *,
        expected_parent_sha256: str,
        accept: bool,
    ) -> ResearchScript:
        safe_script_id = self._require_safe_id(script_id, "script_id")
        safe_revision_id = self._require_safe_id(revision_id, "revision_id")
        script_path = self.scripts_dir / f"{safe_script_id}.json"
        revision_path = self.revisions_dir / safe_script_id / f"{safe_revision_id}.json"
        with self._lock:
            script = self._load_record(script_path, "research_script", self._parse_script)
            revision = self._load_record(
                revision_path,
                "research_script_revision",
                self._parse_revision,
            )
            if script is None or revision is None:
                raise ResearchScriptStoreConflictError("Staged revision is unavailable.")
            if revision.status == ("canonical" if accept else "rejected"):
                return script
            if revision.status != "staged":
                raise ResearchScriptStoreConflictError(
                    f"Revision is already terminal with status {revision.status}."
                )
            if not accept:
                self._write_record_atomic(
                    revision_path,
                    "research_script_revision",
                    replace(revision, status="rejected"),
                )
                return script

            parent = self.load_revision(safe_script_id, script.canonical_revision_id)
            if parent is None:
                raise ResearchScriptStoreCorruptionError("Canonical revision is unavailable.")
            if (
                revision.parent_revision_id != parent.revision_id
                or revision.expected_parent_sha256 != expected_parent_sha256
                or parent.source_sha256 != expected_parent_sha256
            ):
                raise ResearchScriptStoreConflictError(
                    "The canonical source changed after this Operator candidate was staged."
                )
            promoted = replace(revision, status="canonical")
            updated_script = replace(
                script,
                canonical_revision_id=promoted.revision_id,
                status="active",
                updated_at=now_utc(),
            )
            self._write_record_atomic(revision_path, "research_script_revision", promoted)
            self._write_record_atomic(script_path, "research_script", updated_script)
            return updated_script

    def create_input_snapshot(
        self,
        snapshot: ResearchScriptInputSnapshot,
        contents: dict[str, bytes],
    ) -> None:
        safe_snapshot_id = self._require_safe_id(snapshot.snapshot_id, "snapshot_id")
        snapshot_dir = self.inputs_dir / safe_snapshot_id
        manifest_path = snapshot_dir / "manifest.json"
        with self._lock:
            if manifest_path.exists():
                raise ResearchScriptStoreConflictError(f"Input snapshot already exists: {snapshot.snapshot_id}")
            files_dir = snapshot_dir / "files"
            files_dir.mkdir(parents=True, exist_ok=True)
            written: list[Path] = []
            try:
                for item in snapshot.files:
                    if item.logical_filename not in contents:
                        raise ResearchScriptStoreError(f"Missing bytes for input file: {item.logical_filename}")
                    target = files_dir / self._require_safe_filename(item.logical_filename)
                    self._write_bytes_atomic(target, contents[item.logical_filename])
                    written.append(target)
                self._write_record_atomic(manifest_path, "research_script_input", snapshot)
            except Exception:
                manifest_path.unlink(missing_ok=True)
                for path in written:
                    path.unlink(missing_ok=True)
                raise

    def load_input_snapshot(self, snapshot_id: str) -> ResearchScriptInputSnapshot | None:
        safe_id = self._safe_id(snapshot_id)
        if not safe_id:
            return None
        with self._lock:
            return self._load_record(
                self.inputs_dir / safe_id / "manifest.json",
                "research_script_input",
                self._parse_snapshot,
            )

    def load_input_contents(self, snapshot: ResearchScriptInputSnapshot) -> dict[str, bytes]:
        safe_id = self._require_safe_id(snapshot.snapshot_id, "snapshot_id")
        contents: dict[str, bytes] = {}
        with self._lock:
            for item in snapshot.files:
                filename = self._require_safe_filename(item.logical_filename)
                path = self.inputs_dir / safe_id / "files" / filename
                try:
                    content = path.read_bytes()
                except OSError as exc:
                    raise ResearchScriptStoreCorruptionError(
                        f"Persisted input bytes are unavailable: {item.logical_filename}"
                    ) from exc
                if len(content) != item.byte_size or hashlib.sha256(content).hexdigest() != item.content_sha256:
                    raise ResearchScriptStoreCorruptionError(
                        f"Persisted input bytes do not match the immutable manifest: {item.logical_filename}"
                    )
                contents[item.logical_filename] = content
        return contents

    def create_run(
        self,
        run: ResearchScriptRun,
        artifacts: dict[str, tuple[str, bytes]],
    ) -> None:
        safe_script_id = self._require_safe_id(run.script_id, "script_id")
        safe_run_id = self._require_safe_id(run.run_id, "run_id")
        run_path = self.runs_dir / safe_script_id / f"{safe_run_id}.json"
        with self._lock:
            if run_path.exists():
                raise ResearchScriptStoreConflictError(f"Research script run already exists: {run.run_id}")
            written: list[Path] = []
            try:
                for output_id, (filename, content) in artifacts.items():
                    safe_output_id = self._require_safe_id(output_id, "output_id")
                    safe_filename = self._require_safe_filename(filename)
                    target = self.outputs_dir / safe_run_id / f"{safe_output_id}-{safe_filename}"
                    self._write_bytes_atomic(target, content)
                    written.append(target)
                self._write_record_atomic(run_path, "research_script_run", run)
            except Exception:
                run_path.unlink(missing_ok=True)
                for path in written:
                    path.unlink(missing_ok=True)
                raise
            self._prune_runs_unlocked(safe_script_id)

    def list_runs(self, script_id: str) -> list[ResearchScriptRun]:
        safe_id = self._safe_id(script_id)
        if not safe_id:
            return []
        with self._lock:
            runs = [
                item
                for path in sorted((self.runs_dir / safe_id).glob("*.json"))
                if (item := self._load_record(path, "research_script_run", self._parse_run)) is not None
            ]
        return sorted(runs, key=lambda item: (item.started_at, item.run_id), reverse=True)

    def load_run(self, run_id: str) -> ResearchScriptRun | None:
        safe_id = self._safe_id(run_id)
        if not safe_id:
            return None
        with self._lock:
            for script_dir in sorted(self.runs_dir.iterdir()):
                if not script_dir.is_dir() or not self._safe_id(script_dir.name):
                    continue
                path = script_dir / f"{safe_id}.json"
                if path.exists():
                    return self._load_record(path, "research_script_run", self._parse_run)
        return None

    def load_output_artifact(self, run_id: str, output_id: str, filename: str) -> bytes | None:
        safe_run_id = self._safe_id(run_id)
        safe_output_id = self._safe_id(output_id)
        if not safe_run_id or not safe_output_id or not is_safe_research_script_filename(filename):
            return None
        target = self.outputs_dir / safe_run_id / f"{safe_output_id}-{filename}"
        resolved_root = (self.outputs_dir / safe_run_id).resolve()
        resolved_target = target.resolve()
        if resolved_target.parent != resolved_root or not resolved_target.is_file():
            return None
        try:
            return resolved_target.read_bytes()
        except OSError:
            return None

    def cleanup_retained_outputs(self) -> tuple[int, int]:
        with self._lock:
            return self._cleanup_orphaned_outputs_unlocked()

    def storage_diagnostics(self) -> ResearchScriptStorageDiagnostics:
        with self._lock:
            scripts = self.list_scripts()
            revisions = [
                revision
                for script in scripts
                for revision in self.list_revisions(script.script_id)
            ]
            snapshots = [
                snapshot
                for path in sorted(self.inputs_dir.glob("*/manifest.json"))
                if (snapshot := self._load_record(path, "research_script_input", self._parse_snapshot)) is not None
            ]
            runs = [
                run
                for script in scripts
                for run in self.list_runs(script.script_id)
            ]
            retained_output_count = 0
            retained_output_bytes = 0
            missing_output_count = 0
            run_ids = {run.run_id for run in runs}
            for run in runs:
                for output in run.outputs:
                    if not output.artifact_ref or not output.filename:
                        continue
                    content = self.load_output_artifact(run.run_id, output.output_id, output.filename)
                    if content is None:
                        missing_output_count += 1
                    else:
                        retained_output_count += 1
                        retained_output_bytes += len(content)
            orphan_output_count = sum(
                1
                for path in self.outputs_dir.iterdir()
                if path.is_dir() and self._safe_id(path.name) and path.name not in run_ids
            )
            return ResearchScriptStorageDiagnostics(
                script_count=len(scripts),
                archived_script_count=sum(1 for script in scripts if script.status == "archived"),
                revision_count=len(revisions),
                input_snapshot_count=len(snapshots),
                run_count=len(runs),
                retained_output_count=retained_output_count,
                retained_output_bytes=retained_output_bytes,
                missing_output_count=missing_output_count,
                orphan_output_count=orphan_output_count,
                storage_warnings=list(self._storage_warnings),
            )

    def _cleanup_orphaned_outputs_unlocked(self) -> tuple[int, int]:
        known_run_ids = {
            path.stem
            for path in self.runs_dir.glob("*/*.json")
            if self._safe_id(path.stem)
        }
        removed_count = 0
        removed_bytes = 0
        resolved_root = self.outputs_dir.resolve()
        for output_dir in sorted(self.outputs_dir.iterdir()):
            safe_run_id = self._safe_id(output_dir.name)
            if not output_dir.is_dir() or not safe_run_id or safe_run_id in known_run_ids:
                continue
            resolved_dir = output_dir.resolve()
            if resolved_dir.parent != resolved_root:
                self._storage_warnings.append(
                    f"Skipped unsafe orphan output directory {output_dir.name}."
                )
                continue
            nested = False
            for output_path in list(output_dir.iterdir()):
                if not output_path.is_file() or output_path.resolve().parent != resolved_dir:
                    nested = True
                    continue
                try:
                    removed_bytes += output_path.stat().st_size
                except OSError:
                    pass
                output_path.unlink(missing_ok=True)
                removed_count += 1
            if not nested:
                try:
                    output_dir.rmdir()
                except OSError:
                    pass
        return removed_count, removed_bytes

    def _prune_runs_unlocked(self, safe_script_id: str) -> None:
        runs = self.list_runs(safe_script_id)
        for stale in runs[self.run_history_limit :]:
            run_path = self.runs_dir / safe_script_id / f"{self._require_safe_id(stale.run_id, 'run_id')}.json"
            run_path.unlink(missing_ok=True)
            output_dir = self.outputs_dir / stale.run_id
            if output_dir.is_dir():
                for output_path in output_dir.iterdir():
                    if output_path.is_file():
                        output_path.unlink(missing_ok=True)
                try:
                    output_dir.rmdir()
                except OSError:
                    pass

    def _write_record_atomic(self, path: Path, record_type: str, value: Any) -> None:
        payload = {
            "schema_version": CURRENT_RESEARCH_SCRIPT_STORE_SCHEMA_VERSION,
            "record_type": record_type,
            "payload": self._jsonable(value),
        }
        serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        self._write_bytes_atomic(path, serialized.encode("utf-8"))

    @staticmethod
    def _write_bytes_atomic(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.tmp")
        try:
            with temp_path.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _load_record(
        self,
        path: Path,
        record_type: str,
        parser: Callable[[dict[str, Any]], T],
    ) -> T | None:
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(envelope, dict):
                raise ValueError("record envelope is not an object")
            version = int(envelope.get("schema_version", -1))
            if version != CURRENT_RESEARCH_SCRIPT_STORE_SCHEMA_VERSION:
                raise ValueError(f"unsupported schema version {version}")
            if envelope.get("record_type") != record_type:
                raise ValueError("record type does not match its storage location")
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("record payload is not an object")
            return parser(payload)
        except Exception as exc:
            quarantined = self._quarantine_file_unlocked(path, record_type, "malformed")
            location = quarantined.name if quarantined is not None else path.name
            self._storage_warnings.append(
                f"Skipped malformed {record_type} metadata and preserved it as {location}: {type(exc).__name__}."
            )
            return None

    def _recover_interrupted_writes_unlocked(self) -> None:
        for temp_path in list(self.base_dir.rglob("*.tmp")):
            if self.quarantine_dir in temp_path.parents:
                continue
            if not temp_path.name.endswith(".json.tmp"):
                self._quarantine_file_unlocked(temp_path, "interrupted_write", "orphaned-bytes")
                self._storage_warnings.append(
                    f"Preserved interrupted artifact write {temp_path.name} in quarantine."
                )
                continue
            target = temp_path.with_name(temp_path.name[:-4])
            if target.exists():
                self._quarantine_file_unlocked(temp_path, "interrupted_write", "stale-temp")
                self._storage_warnings.append(
                    f"Preserved interrupted temporary write {temp_path.name}; the authoritative record exists."
                )
                continue
            try:
                payload = json.loads(temp_path.read_text(encoding="utf-8"))
            except Exception:
                payload = None
            if (
                isinstance(payload, dict)
                and int(payload.get("schema_version", -1))
                == CURRENT_RESEARCH_SCRIPT_STORE_SCHEMA_VERSION
            ):
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temp_path, target)
                self._storage_warnings.append(f"Recovered interrupted atomic write {target.name}.")
            else:
                self._quarantine_file_unlocked(temp_path, "interrupted_write", "invalid-temp")
                self._storage_warnings.append(
                    f"Preserved unreadable interrupted write {temp_path.name} in quarantine."
                )

    def _quarantine_file_unlocked(self, path: Path, record_type: str, reason: str) -> Path | None:
        if not path.exists():
            return None
        timestamp = now_utc().strftime("%Y%m%dT%H%M%S%f")
        target = self.quarantine_dir / record_type / f"{path.name}.{reason}.{timestamp}.{uuid4().hex[:8]}.preserved"
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
        return target

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value):
            return cls._jsonable(asdict(value))
        if isinstance(value, dict):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._jsonable(item) for item in value]
        return value

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def _parse_optional_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        return ResearchScriptStore._parse_datetime(value)

    @classmethod
    def _parse_script(cls, payload: dict[str, Any]) -> ResearchScript:
        return ResearchScript(
            script_id=str(payload["script_id"]),
            session_id=str(payload["session_id"]),
            title=str(payload["title"]),
            language=payload["language"],
            status=payload["status"],
            canonical_revision_id=str(payload["canonical_revision_id"]),
            created_by=payload["created_by"],
            created_at=cls._parse_datetime(payload["created_at"]),
            updated_at=cls._parse_datetime(payload["updated_at"]),
            source_provider=str(payload["source_provider"]),
            origin=str(payload["origin"]),
            transformation_note=payload.get("transformation_note"),
            contract_version=str(payload["contract_version"]),
        )

    @classmethod
    def _parse_revision(cls, payload: dict[str, Any]) -> ResearchScriptRevision:
        return ResearchScriptRevision(
            revision_id=str(payload["revision_id"]),
            script_id=str(payload["script_id"]),
            revision_number=int(payload["revision_number"]),
            source=str(payload["source"]),
            source_sha256=str(payload["source_sha256"]),
            created_by=payload["created_by"],
            created_at=cls._parse_datetime(payload["created_at"]),
            parent_revision_id=payload.get("parent_revision_id"),
            status=payload["status"],
            change_summary=payload.get("change_summary"),
            operator_run_id=payload.get("operator_run_id"),
            expected_parent_sha256=payload.get("expected_parent_sha256"),
            contract_version=str(payload["contract_version"]),
        )

    @classmethod
    def _parse_input_file(cls, payload: dict[str, Any]) -> ResearchScriptInputFile:
        return ResearchScriptInputFile(
            logical_filename=str(payload["logical_filename"]),
            media_type=str(payload["media_type"]),
            byte_size=int(payload["byte_size"]),
            content_sha256=str(payload["content_sha256"]),
            gamma_object_id=payload.get("gamma_object_id"),
            provider_id=payload.get("provider_id"),
            source_timestamp=cls._parse_optional_datetime(payload.get("source_timestamp")),
            retrieved_at=cls._parse_datetime(payload["retrieved_at"]),
            transformation_note=payload.get("transformation_note"),
            source_kind=payload["source_kind"],
            artifact_ref=str(payload["artifact_ref"]),
        )

    @classmethod
    def _parse_snapshot(cls, payload: dict[str, Any]) -> ResearchScriptInputSnapshot:
        return ResearchScriptInputSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            script_id=str(payload["script_id"]),
            created_at=cls._parse_datetime(payload["created_at"]),
            files=[cls._parse_input_file(dict(item)) for item in payload.get("files", [])],
            dataset_refs=[dict(item) for item in payload.get("dataset_refs", [])],
            source_refs=[dict(item) for item in payload.get("source_refs", [])],
            warnings=[str(item) for item in payload.get("warnings", [])],
            manifest_sha256=str(payload["manifest_sha256"]),
            total_bytes=int(payload["total_bytes"]),
            source_provider=str(payload["source_provider"]),
            origin=str(payload["origin"]),
            transformation_note=payload.get("transformation_note"),
            contract_version=str(payload["contract_version"]),
        )

    @classmethod
    def _parse_output(cls, payload: dict[str, Any]) -> ResearchScriptOutput:
        return ResearchScriptOutput(
            output_id=str(payload["output_id"]),
            kind=payload["kind"],
            sequence=int(payload["sequence"]),
            media_type=str(payload["media_type"]),
            byte_size=int(payload["byte_size"]),
            created_at=cls._parse_datetime(payload["created_at"]),
            artifact_ref=payload.get("artifact_ref"),
            provider_native_ref=payload.get("provider_native_ref"),
            text=payload.get("text"),
            metric_name=payload.get("metric_name"),
            metric_value=payload.get("metric_value"),
            unit=payload.get("unit"),
            columns=[str(item) for item in payload.get("columns", [])],
            rows=[dict(item) for item in payload.get("rows", [])],
            filename=payload.get("filename"),
            alt_text=payload.get("alt_text"),
            source_provider=str(payload["source_provider"]),
            origin=str(payload["origin"]),
            transformation_note=payload.get("transformation_note"),
            generated=bool(payload.get("generated", True)),
            contract_version=str(payload["contract_version"]),
        )

    @classmethod
    def _parse_run(cls, payload: dict[str, Any]) -> ResearchScriptRun:
        return ResearchScriptRun(
            run_id=str(payload["run_id"]),
            script_id=str(payload["script_id"]),
            revision_id=str(payload["revision_id"]),
            source_sha256=str(payload["source_sha256"]),
            input_snapshot_id=str(payload["input_snapshot_id"]),
            input_manifest_sha256=str(payload["input_manifest_sha256"]),
            input_file_count=int(payload["input_file_count"]),
            input_total_bytes=int(payload["input_total_bytes"]),
            runtime_provider=str(payload["runtime_provider"]),
            runtime_kind=str(payload["runtime_kind"]),
            provider_container_id=payload.get("provider_container_id"),
            provider_response_id=payload.get("provider_response_id"),
            status=payload["status"],
            started_at=cls._parse_datetime(payload["started_at"]),
            completed_at=cls._parse_optional_datetime(payload.get("completed_at")),
            outputs=[cls._parse_output(dict(item)) for item in payload.get("outputs", [])],
            source_refs=[dict(item) for item in payload.get("source_refs", [])],
            warnings=[str(item) for item in payload.get("warnings", [])],
            usage=dict(payload.get("usage", {})),
            limits={str(key): value for key, value in dict(payload.get("limits", {})).items()},
            source_provider=str(payload["source_provider"]),
            origin=str(payload["origin"]),
            transformation_note=payload.get("transformation_note"),
            contract_version=str(payload["contract_version"]),
        )

    @staticmethod
    def _safe_id(value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in text):
            return None
        return text

    @classmethod
    def _require_safe_id(cls, value: str | None, field_name: str) -> str:
        safe = cls._safe_id(value)
        if safe is None:
            raise ResearchScriptStoreError(f"Unsafe {field_name}.")
        return safe

    @staticmethod
    def _require_safe_filename(value: str) -> str:
        text = str(value or "").strip()
        if not is_safe_research_script_filename(text):
            raise ResearchScriptStoreError("Unsafe artifact filename.")
        return text
