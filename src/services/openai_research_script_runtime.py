from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import mimetypes
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from openai import OpenAI

from src.models.research_script import ResearchScriptRunStatus
from src.services.research_script_runtime import (
    ResearchScriptRuntimeCancelResult,
    ResearchScriptRuntimeCapabilities,
    ResearchScriptRuntimeOutput,
    ResearchScriptRuntimeRequest,
    ResearchScriptRuntimeResult,
)
from src.utils.time import now_utc


_SUPPORTED_OUTPUT_TYPES = ("log", "summary", "table", "image", "file", "warning", "error")
_ALLOWED_ARTIFACT_MIME_TYPES = {
    "application/json",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "text/csv",
    "text/plain",
}
_CODE_INTERPRETER_MODEL = re.compile(r"^gpt-5\.(?:4|5|6)(?:$|-)", re.IGNORECASE)


@dataclass(frozen=True)
class _UploadedFile:
    role: str
    file_id: str
    filename: str
    content_sha256: str
    provider_path: str


@dataclass(frozen=True)
class _ContainerBinding:
    container_id: str
    source_path: str
    manifest_path: str
    uploads: tuple[_UploadedFile, ...]


class OpenAICodeInterpreterRuntime:
    """Provider adapter for exact-source, network-disabled Code Interpreter runs.

    OpenAI SDK objects and provider paths intentionally stop at this module. The
    provider-neutral result contains only sanitized identities, typed output
    bytes, and evidence needed to validate the immutable execution association.
    """

    PROVIDER = "openai"
    RUNTIME_KIND = "openai_code_interpreter_v1"
    CONTAINER_EXPIRY_MINUTES = 20

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        client: Any | None = None,
        configured_runtime: str = "openai",
        max_duration_seconds: int = 120,
    ) -> None:
        self.model = str(model or "").strip()
        self.configured_runtime = str(configured_runtime or "openai").strip().lower()
        self.max_duration_seconds = max(int(max_duration_seconds), 1)
        self._api_key_present = bool(str(api_key or "").strip())
        self._client = client
        self._bindings: dict[str, _ContainerBinding] = {}
        self._results: dict[str, tuple[str, ResearchScriptRuntimeResult]] = {}
        self._response_ids: dict[str, str] = {}
        self._cancelled_runs: set[str] = set()
        self._lock = threading.RLock()
        self._interfaces_available = self._detect_interfaces(client)
        if self._client is None and self._api_key_present and self._model_supports_code_interpreter():
            try:
                self._client = OpenAI(api_key=api_key)
            except Exception:
                self._client = None
            self._interfaces_available = self._detect_interfaces(self._client)

    def capabilities(self) -> ResearchScriptRuntimeCapabilities:
        model_supported = self._model_supports_code_interpreter()
        available = bool(
            self.configured_runtime == "openai"
            and self._api_key_present
            and model_supported
            and self._interfaces_available
            and self._client is not None
        )
        if self.configured_runtime != "openai":
            status = "runtime_not_selected"
        elif not self._api_key_present:
            status = "provider_configuration_missing"
        elif not model_supported:
            status = "configured_model_lacks_verified_code_interpreter_support"
        elif not self._interfaces_available:
            status = "installed_sdk_lacks_required_interfaces"
        elif self._client is None:
            status = "provider_client_unavailable"
        else:
            status = "available_experimental_exact_source_gate"
        return ResearchScriptRuntimeCapabilities(
            configured_runtime=self.configured_runtime,
            provider=self.PROVIDER,
            runtime_kind=self.RUNTIME_KIND,
            available=available,
            executes_source=available,
            network_access=False,
            supported_output_types=_SUPPORTED_OUTPUT_TYPES,
            # The synchronous v1 route cannot expose an in-progress response id
            # soon enough for honest interactive cancellation.
            supports_cancellation=False,
            max_duration_seconds=self.max_duration_seconds,
            active_limits={
                "container_expiry_minutes": self.CONTAINER_EXPIRY_MINUTES,
                "provider_transport_retries": 1,
                "max_tool_calls": 1,
            },
            model=self.model or None,
            sanitized_provider_status=status,
        )

    def start_run(self, request: ResearchScriptRuntimeRequest) -> ResearchScriptRuntimeResult:
        fingerprint = self._request_fingerprint(request)
        with self._lock:
            existing = self._results.get(request.run_id)
            if existing is not None:
                if existing[0] != fingerprint:
                    return self._unavailable_result(
                        request,
                        "A terminal run id cannot be replayed with different immutable inputs.",
                        status="incomplete",
                    )
                return existing[1]

        capabilities = self.capabilities()
        if not capabilities.available:
            result = self._unavailable_result(
                request,
                "The configured Research Script provider capability is unavailable; use the mock runtime.",
                status="unavailable",
            )
            self._remember_result(request.run_id, fingerprint, result)
            return result

        source_hash = hashlib.sha256(request.source.encode("utf-8")).hexdigest()
        manifest_bytes = self._canonical_json_bytes(request.input_manifest)
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        if source_hash != request.source_sha256 or manifest_hash != request.input_manifest_sha256:
            result = self._unavailable_result(
                request,
                "Gamma rejected dispatch because immutable source or input-manifest verification failed.",
                status="incomplete",
            )
            self._remember_result(request.run_id, fingerprint, result)
            return result
        for item in request.input_files:
            if hashlib.sha256(item.content).hexdigest() != item.content_sha256:
                result = self._unavailable_result(
                    request,
                    "Gamma rejected dispatch because an immutable input file hash did not match.",
                    status="incomplete",
                )
                self._remember_result(request.run_id, fingerprint, result)
                return result

        replayed = False
        try:
            result = self._dispatch(request, manifest_bytes, replayed=False)
        except Exception as exc:
            if self._is_expired_container_error(exc):
                replayed = True
                with self._lock:
                    self._bindings.pop(self._binding_key(request), None)
                try:
                    result = self._dispatch(request, manifest_bytes, replayed=True)
                except Exception as retry_exc:
                    result = self._provider_error_result(request, retry_exc, replayed=True)
            else:
                result = self._provider_error_result(request, exc, replayed=False)

        if request.run_id in self._cancelled_runs and result.status not in {
            "cancelled",
            "failed",
            "timed_out",
            "unavailable",
            "incomplete",
        }:
            result = ResearchScriptRuntimeResult(
                status="cancelled",
                executed_source_sha256=result.executed_source_sha256,
                provider_container_id=result.provider_container_id,
                provider_response_id=result.provider_response_id,
                outputs=[],
                warnings=[*result.warnings, "A late provider result was ignored after local cancellation."],
                usage={**result.usage, "late_result_ignored": True},
                completed_at=result.completed_at,
            )
        if replayed and "Expired provider container was replaced" not in " ".join(result.warnings):
            result = ResearchScriptRuntimeResult(
                status=result.status,
                executed_source_sha256=result.executed_source_sha256,
                provider_container_id=result.provider_container_id,
                provider_response_id=result.provider_response_id,
                outputs=result.outputs,
                warnings=[
                    *result.warnings,
                    "Expired provider container was replaced and the same immutable source and inputs were replayed once.",
                ],
                usage={**result.usage, "expired_container_replay": True},
                completed_at=result.completed_at,
            )
        self._remember_result(request.run_id, fingerprint, result)
        return result

    def cancel_run(self, provider_run_id: str) -> ResearchScriptRuntimeCancelResult:
        run_id = str(provider_run_id or "").strip()
        with self._lock:
            self._cancelled_runs.add(run_id)
            response_id = self._response_ids.get(run_id)
        if not response_id or self._client is None:
            return ResearchScriptRuntimeCancelResult(
                cancelled=False,
                status="incomplete",
                message="Provider cancellation is unavailable before the synchronous response id is known.",
            )
        try:
            response = self._client.responses.cancel(response_id)
            status = self._status(str(getattr(response, "status", "cancelled")))
            return ResearchScriptRuntimeCancelResult(
                cancelled=status == "cancelled",
                status=status,
                message="Provider cancellation was requested for the active response.",
            )
        except Exception:
            return ResearchScriptRuntimeCancelResult(
                cancelled=False,
                status="incomplete",
                message="The provider could not confirm cancellation; late results will be ignored locally.",
            )

    @staticmethod
    def collect_outputs(result: ResearchScriptRuntimeResult) -> list[ResearchScriptRuntimeOutput]:
        return list(result.outputs)

    def _dispatch(
        self,
        request: ResearchScriptRuntimeRequest,
        manifest_bytes: bytes,
        *,
        replayed: bool,
    ) -> ResearchScriptRuntimeResult:
        binding = self._container_binding(request, manifest_bytes)
        before_ids = self._container_file_ids(binding.container_id)
        wrapper = self._execution_wrapper(
            binding.source_path,
            request.source_sha256,
            binding.manifest_path,
            request.input_manifest_sha256,
            [
                (item.filename, item.provider_path, item.content_sha256)
                for item in binding.uploads
                if item.role == "input"
            ],
            request.run_id,
        )
        response = self._client.responses.create(
            model=self.model,
            instructions=(
                "Act only as Gamma's deterministic Python execution transport. "
                "Use exactly one Code Interpreter call. Do not use network access, install packages, "
                "rewrite the research source, or substitute different inputs."
            ),
            input=(
                "Execute the following wrapper verbatim in Code Interpreter. Do not add, remove, or "
                "change any Python statement. After it finishes, return a download link for every "
                "generated file using its exact filename so each file is present as a container-file citation.\n\n"
                f"```python\n{wrapper}\n```"
            ),
            tools=[{"type": "code_interpreter", "container": binding.container_id}],
            tool_choice="required",
            parallel_tool_calls=False,
            max_tool_calls=1,
            max_output_tokens=2048,
            store=False,
            timeout=float(min(self.max_duration_seconds, int(request.limits.get("run_duration_seconds", self.max_duration_seconds)))),
        )
        response_id = str(getattr(response, "id", "") or "") or None
        with self._lock:
            if response_id:
                self._response_ids[request.run_id] = response_id

        code_calls = [item for item in list(getattr(response, "output", []) or []) if getattr(item, "type", None) == "code_interpreter_call"]
        returned_codes = [str(getattr(item, "code", "") or "") for item in code_calls]
        exact_wrapper = len(returned_codes) == 1 and self._normalized_code(returned_codes[0]) == self._normalized_code(wrapper)
        warnings: list[str] = []
        if not exact_wrapper:
            warnings.append(
                "The provider did not return one verbatim execution wrapper; exact-source association was not established."
            )

        outputs: list[ResearchScriptRuntimeOutput] = []
        provider_execution_failed = False
        sequence = 1
        for call in code_calls:
            if str(getattr(call, "status", "") or "").strip().lower() == "failed":
                provider_execution_failed = True
            for call_output in list(getattr(call, "outputs", []) or []):
                if getattr(call_output, "type", None) == "logs":
                    logs = str(getattr(call_output, "logs", "") or "")
                    if logs:
                        sanitized_logs = self._sanitize_provider_text(logs)
                        log_failed = self._reports_execution_failure(sanitized_logs)
                        provider_execution_failed = provider_execution_failed or log_failed
                        outputs.append(
                            ResearchScriptRuntimeOutput(
                                output_id=f"provider-log-{sequence}",
                                kind="error" if log_failed else "log",
                                sequence=sequence,
                                media_type="text/plain",
                                text=sanitized_logs,
                                provider_native_ref=str(getattr(call, "id", "") or "") or None,
                                transformation_note=(
                                    "Code Interpreter failure retained from the exact-source wrapper call."
                                    if log_failed
                                    else "Code Interpreter logs retained from the exact-source wrapper call."
                                ),
                            )
                        )
                        sequence += 1
                elif getattr(call_output, "type", None) == "image":
                    image = self._inline_image_output(call_output, sequence, getattr(call, "id", None))
                    if image is not None:
                        outputs.append(image)
                        sequence += 1
                    else:
                        warnings.append("A transient provider image URL was not retained because no durable bytes were available.")

        cited_files: dict[str, str] = {}
        for item in list(getattr(response, "output", []) or []):
            if getattr(item, "type", None) != "message":
                continue
            for content in list(getattr(item, "content", []) or []):
                if getattr(content, "type", None) != "output_text":
                    continue
                text = str(getattr(content, "text", "") or "")
                if text:
                    sanitized_text = self._sanitize_provider_text(text)
                    summary_failed = self._reports_execution_failure(sanitized_text)
                    provider_execution_failed = provider_execution_failed or summary_failed
                    outputs.append(
                        ResearchScriptRuntimeOutput(
                            output_id=f"provider-summary-{sequence}",
                            kind="error" if summary_failed else "summary",
                            sequence=sequence,
                            media_type="text/plain",
                            text=sanitized_text,
                            provider_native_ref=str(getattr(item, "id", "") or "") or None,
                            transformation_note=(
                                "Provider-reported execution failure retained as a typed error."
                                if summary_failed
                                else "Provider completion message; analytical claims remain subordinate to retained artifacts."
                            ),
                        )
                    )
                    sequence += 1
                for annotation in list(getattr(content, "annotations", []) or []):
                    if getattr(annotation, "type", None) == "container_file_citation":
                        file_id = str(getattr(annotation, "file_id", "") or "")
                        filename = str(getattr(annotation, "filename", "") or "")
                        if file_id:
                            cited_files[file_id] = filename

        after_files = self._container_files(binding.container_id)
        upload_ids = {item.file_id for item in binding.uploads}
        generated: dict[str, str] = dict(cited_files)
        for item in after_files:
            file_id = str(getattr(item, "id", "") or "")
            if not file_id or file_id in before_ids or file_id in upload_ids:
                continue
            raw_path = str(getattr(item, "path", "") or "")
            generated.setdefault(file_id, PurePosixPath(raw_path).name)

        max_outputs = int(request.limits.get("output_artifacts", 32))
        max_bytes = int(request.limits.get("total_output_bytes", 64 * 1024 * 1024))
        downloaded_bytes = 0
        for file_id, filename in generated.items():
            if len(outputs) >= max_outputs:
                raise ValueError("provider_output_count_limit")
            content = self._download_container_file(binding.container_id, file_id)
            downloaded_bytes += len(content)
            if downloaded_bytes > max_bytes:
                raise ValueError("provider_output_size_limit")
            media_type = self._media_type(filename)
            if media_type not in _ALLOWED_ARTIFACT_MIME_TYPES:
                warnings.append(f"Generated file {filename or file_id} used an unsupported media type and was not retained.")
                continue
            outputs.append(self._artifact_output(file_id, filename, content, media_type, sequence))
            sequence += 1
            for artifact_warning in self._artifact_warnings(content, media_type):
                artifact_warning = self._sanitize_provider_text(artifact_warning)
                warnings.append(artifact_warning)
                outputs.append(
                    ResearchScriptRuntimeOutput(
                        output_id=f"provider-warning-{sequence}",
                        kind="warning",
                        sequence=sequence,
                        media_type="text/plain",
                        text=artifact_warning,
                        provider_native_ref=file_id,
                        transformation_note="Generated warning normalized from a retained runtime summary artifact.",
                    )
                )
                sequence += 1

        response_status = self._status(str(getattr(response, "status", "completed") or "completed"))
        provider_execution_failed = provider_execution_failed or getattr(response, "error", None) is not None
        status: ResearchScriptRunStatus = response_status if exact_wrapper else "incomplete"
        if response_status == "completed" and not exact_wrapper:
            status = "incomplete"
        elif provider_execution_failed and exact_wrapper:
            status = "failed"
            warnings.append("The isolated provider execution failed; see the retained typed error output.")
        usage = self._usage(response)
        usage.update(
            {
                "provider_requests": 1,
                "executed_code": exact_wrapper,
                "network_access": False,
                "model": self.model,
                "uploaded_files": [
                    {
                        "role": item.role,
                        "file_id": item.file_id,
                        "filename": item.filename,
                        "content_sha256": item.content_sha256,
                    }
                    for item in binding.uploads
                ],
                "code_interpreter_calls": [
                    {
                        "call_id": str(getattr(item, "id", "") or ""),
                        "status": str(getattr(item, "status", "") or ""),
                        "code_sha256": hashlib.sha256(str(getattr(item, "code", "") or "").encode("utf-8")).hexdigest(),
                    }
                    for item in code_calls
                ],
                "executed_wrapper": self._sanitize_wrapper(returned_codes[0]) if len(returned_codes) == 1 else None,
                "executed_wrapper_sha256": hashlib.sha256(returned_codes[0].encode("utf-8")).hexdigest() if len(returned_codes) == 1 else None,
                "expected_wrapper_sha256": hashlib.sha256(wrapper.encode("utf-8")).hexdigest(),
                "source_sha256": request.source_sha256,
                "input_manifest_sha256": request.input_manifest_sha256,
                "expired_container_replay": replayed,
            }
        )
        if getattr(response, "incomplete_details", None) is not None:
            warnings.append("The provider reported an incomplete response.")
        if getattr(response, "error", None) is not None:
            warnings.append("The provider reported a sanitized execution error.")
        return ResearchScriptRuntimeResult(
            status=status,
            executed_source_sha256=request.source_sha256 if exact_wrapper else None,
            provider_container_id=binding.container_id,
            provider_response_id=response_id,
            outputs=outputs,
            warnings=list(dict.fromkeys(warnings)),
            usage=usage,
            completed_at=now_utc(),
        )

    def _container_binding(self, request: ResearchScriptRuntimeRequest, manifest_bytes: bytes) -> _ContainerBinding:
        key = self._binding_key(request)
        with self._lock:
            existing = self._bindings.get(key)
        if existing is not None:
            return existing
        container = self._client.containers.create(
            name=f"gamma-research-{request.run_id[:12]}",
            expires_after={"anchor": "last_active_at", "minutes": self.CONTAINER_EXPIRY_MINUTES},
            memory_limit="1g",
            network_policy={"type": "disabled"},
        )
        container_id = str(getattr(container, "id", "") or "")
        if not container_id:
            raise RuntimeError("provider_container_identity_missing")
        source_name = f"gamma-source-{request.source_sha256[:16]}.py"
        manifest_name = f"gamma-input-manifest-{request.input_manifest_sha256[:16]}.json"
        uploads: list[_UploadedFile] = []
        source = self._upload(container_id, "source", source_name, request.source.encode("utf-8"), "text/x-python")
        uploads.append(source)
        manifest = self._upload(container_id, "manifest", manifest_name, manifest_bytes, "application/json")
        uploads.append(manifest)
        for item in request.input_files:
            uploads.append(
                self._upload(
                    container_id,
                    "input",
                    item.logical_filename,
                    item.content,
                    item.media_type,
                )
            )
        binding = _ContainerBinding(
            container_id=container_id,
            source_path=source.provider_path,
            manifest_path=manifest.provider_path,
            uploads=tuple(uploads),
        )
        with self._lock:
            self._bindings[key] = binding
        return binding

    def _upload(self, container_id: str, role: str, filename: str, content: bytes, media_type: str) -> _UploadedFile:
        uploaded = self._client.containers.files.create(
            container_id=container_id,
            file=(filename, content, media_type),
        )
        file_id = str(getattr(uploaded, "id", "") or "")
        provider_path = str(getattr(uploaded, "path", "") or "")
        if not file_id or not provider_path:
            raise RuntimeError("provider_file_identity_missing")
        return _UploadedFile(
            role=role,
            file_id=file_id,
            filename=filename,
            content_sha256=hashlib.sha256(content).hexdigest(),
            provider_path=provider_path,
        )

    def _container_files(self, container_id: str) -> list[Any]:
        result = self._client.containers.files.list(container_id=container_id, limit=100)
        return list(getattr(result, "data", result) or [])

    def _container_file_ids(self, container_id: str) -> set[str]:
        return {str(getattr(item, "id", "") or "") for item in self._container_files(container_id)}

    def _download_container_file(self, container_id: str, file_id: str) -> bytes:
        response = self._client.containers.files.content.retrieve(file_id, container_id=container_id)
        content = getattr(response, "content", None)
        if isinstance(content, bytes):
            return content
        if callable(getattr(response, "read", None)):
            return bytes(response.read())
        if isinstance(response, bytes):
            return response
        raise RuntimeError("provider_artifact_download_failed")

    @staticmethod
    def _execution_wrapper(
        source_path: str,
        source_hash: str,
        manifest_path: str,
        manifest_hash: str,
        inputs: list[tuple[str, str, str]],
        run_id: str,
    ) -> str:
        return "\n".join(
            [
                "import hashlib, os, runpy, shutil",
                f"source_path = {source_path!r}",
                f"manifest_path = {manifest_path!r}",
                f"assert hashlib.sha256(open(source_path, 'rb').read()).hexdigest() == {source_hash!r}",
                f"assert hashlib.sha256(open(manifest_path, 'rb').read()).hexdigest() == {manifest_hash!r}",
                f"input_files = {inputs!r}",
                f"workspace = os.path.join('/mnt/data', {'gamma-run-' + run_id[:16]!r})",
                "os.makedirs(workspace, exist_ok=True)",
                "for logical_name, provider_path, expected_hash in input_files:",
                "    assert hashlib.sha256(open(provider_path, 'rb').read()).hexdigest() == expected_hash",
                "    copied_path = os.path.join(workspace, logical_name)",
                "    shutil.copyfile(provider_path, copied_path)",
                "    assert hashlib.sha256(open(copied_path, 'rb').read()).hexdigest() == expected_hash",
                "initial_files = set(os.listdir(workspace))",
                "os.chdir(workspace)",
                "runpy.run_path(source_path, run_name='__main__')",
                "for generated_name in sorted(set(os.listdir(workspace)) - initial_files):",
                "    print('GAMMA_GENERATED_FILE:' + os.path.join(workspace, generated_name))",
            ]
        )

    @staticmethod
    def _normalized_code(value: str) -> str:
        text = str(value or "").strip()
        if text.startswith("```python") and text.endswith("```"):
            text = text[9:-3].strip()
        elif text.startswith("```") and text.endswith("```"):
            text = text[3:-3].strip()
        return text.replace("\r\n", "\n")

    @staticmethod
    def _sanitize_wrapper(value: str) -> str:
        text = str(value or "")
        text = re.sub(r"(?:/mnt/data|/home/oai/share|/tmp)", "{container_root}", text)
        return text

    @classmethod
    def _sanitize_provider_text(cls, value: str) -> str:
        text = str(value or "")
        text = re.sub(
            r"\[Download\s+([^\]]+)\]\(sandbox:[^)]+\)",
            r"Retained artifact: \1",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"sandbox:(?:/mnt/data|/home/oai/share|/tmp)[^\s)\]]*",
            "{retained_artifact}",
            text,
            flags=re.IGNORECASE,
        )
        return cls._sanitize_wrapper(text)

    @staticmethod
    def _inline_image_output(value: Any, sequence: int, call_id: Any) -> ResearchScriptRuntimeOutput | None:
        url = str(getattr(value, "url", "") or "")
        match = re.fullmatch(r"data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=]+)", url)
        if match is None:
            return None
        content = base64.b64decode(match.group(2), validate=True)
        extension = "png" if match.group(1) == "image/png" else "jpg"
        return ResearchScriptRuntimeOutput(
            output_id=f"provider-image-{sequence}",
            kind="image",
            sequence=sequence,
            media_type=match.group(1),
            filename=f"code-interpreter-image-{sequence}.{extension}",
            alt_text="Generated Code Interpreter image",
            provider_native_ref=str(call_id or "") or None,
            artifact_bytes=content,
            transformation_note="Generated/derived image downloaded immediately from the provider response.",
        )

    @staticmethod
    def _artifact_output(
        file_id: str,
        filename: str,
        content: bytes,
        media_type: str,
        sequence: int,
    ) -> ResearchScriptRuntimeOutput:
        kind = "image" if media_type.startswith("image/") else "file"
        columns: list[str] = []
        rows: list[dict[str, Any]] = []
        if media_type == "text/csv":
            decoded = content.decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(decoded))
            columns = [str(item) for item in (reader.fieldnames or [])]
            rows = [dict(row) for row in reader]
            kind = "table"
        elif media_type == "application/json":
            try:
                payload = json.loads(content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
                columns = list(dict.fromkeys(str(key) for item in payload for key in item))
                rows = [dict(item) for item in payload]
                kind = "table"
        return ResearchScriptRuntimeOutput(
            output_id=f"provider-file-{sequence}",
            kind=kind,
            sequence=sequence,
            media_type=media_type,
            filename=filename,
            alt_text="Generated Code Interpreter chart" if kind == "image" else None,
            provider_native_ref=file_id,
            artifact_bytes=content,
            columns=columns,
            rows=rows,
            transformation_note="Generated/derived artifact downloaded immediately into Gamma retention.",
        )

    @staticmethod
    def _artifact_warnings(content: bytes, media_type: str) -> list[str]:
        if media_type != "application/json":
            return []
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict) or not isinstance(payload.get("warnings"), list):
            return []
        return [
            str(item).strip()
            for item in payload["warnings"][:20]
            if str(item).strip()
        ]

    @staticmethod
    def _media_type(filename: str) -> str:
        suffix = PurePosixPath(str(filename or "")).suffix.lower()
        overrides = {
            ".csv": "text/csv",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
        }
        return overrides.get(suffix) or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    @staticmethod
    def _usage(response: Any) -> dict[str, Any]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        result: dict[str, Any] = {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if isinstance(value, int):
                result[key] = value
        return result

    @staticmethod
    def _status(value: str) -> ResearchScriptRunStatus:
        return {
            "queued": "queued",
            "in_progress": "running",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
            "incomplete": "incomplete",
            "expired": "expired",
        }.get(value.strip().lower(), "incomplete")  # type: ignore[return-value]

    @staticmethod
    def _reports_execution_failure(text: str) -> bool:
        normalized = str(text or "").strip()
        return bool(
            re.search(r"(?im)^execution failed with\s*:", normalized)
            or re.search(r"(?im)^traceback \(most recent call last\):", normalized)
        )

    def _provider_error_result(
        self,
        request: ResearchScriptRuntimeRequest,
        exc: Exception,
        *,
        replayed: bool,
    ) -> ResearchScriptRuntimeResult:
        name = type(exc).__name__.lower()
        if "timeout" in name:
            status: ResearchScriptRunStatus = "timed_out"
            message = "The provider runtime exceeded Gamma's duration limit."
        elif "authentication" in name or "permission" in name:
            status = "unavailable"
            message = "The configured provider rejected Research Script access."
        elif "rate" in name:
            status = "unavailable"
            message = "The provider temporarily rate-limited Research Script execution."
        elif "provider_output_count_limit" in str(exc):
            status = "failed"
            message = "Generated output count exceeded Gamma's retention limit."
        elif "provider_output_size_limit" in str(exc):
            status = "failed"
            message = "Generated output bytes exceeded Gamma's retention limit."
        else:
            status = "failed"
            message = "The provider could not complete the bounded Research Script run."
        return ResearchScriptRuntimeResult(
            status=status,
            executed_source_sha256=None,
            provider_container_id=None,
            provider_response_id=None,
            outputs=[
                ResearchScriptRuntimeOutput(
                    output_id="provider-error",
                    kind="error",
                    sequence=1,
                    media_type="text/plain",
                    text=message,
                    transformation_note="Sanitized provider-domain error; raw provider payloads were not retained.",
                )
            ],
            warnings=[message],
            usage={"provider_requests": 1 + int(replayed), "network_access": False},
            completed_at=now_utc(),
        )

    @staticmethod
    def _unavailable_result(
        request: ResearchScriptRuntimeRequest,
        message: str,
        *,
        status: ResearchScriptRunStatus,
    ) -> ResearchScriptRuntimeResult:
        return ResearchScriptRuntimeResult(
            status=status,
            executed_source_sha256=None,
            provider_container_id=None,
            provider_response_id=None,
            outputs=[],
            warnings=[message],
            usage={"provider_requests": 0, "executed_code": False, "network_access": False},
            completed_at=now_utc(),
        )

    def _model_supports_code_interpreter(self) -> bool:
        normalized = self.model.lower()
        return bool(_CODE_INTERPRETER_MODEL.match(normalized) and "-pro" not in normalized)

    @staticmethod
    def _detect_interfaces(client: Any | None) -> bool:
        try:
            return bool(
                client is not None
                and callable(client.responses.create)
                and callable(client.responses.cancel)
                and callable(client.containers.create)
                and callable(client.containers.files.create)
                and callable(client.containers.files.list)
                and callable(client.containers.files.content.retrieve)
            )
        except (AttributeError, TypeError):
            return False

    @staticmethod
    def _is_expired_container_error(exc: Exception) -> bool:
        code = str(getattr(exc, "code", "") or "").lower()
        status_code = getattr(exc, "status_code", None)
        message = str(exc).lower()
        return code in {"container_expired", "expired_container"} or (
            status_code in {404, 410} and "container" in message and "expir" in message
        )

    @staticmethod
    def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _binding_key(request: ResearchScriptRuntimeRequest) -> str:
        return f"{request.source_sha256}:{request.input_manifest_sha256}"

    @staticmethod
    def _request_fingerprint(request: ResearchScriptRuntimeRequest) -> str:
        payload = {
            "script_id": request.script_id,
            "revision_id": request.revision_id,
            "source_sha256": request.source_sha256,
            "input_snapshot_id": request.input_snapshot_id,
            "input_manifest_sha256": request.input_manifest_sha256,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _remember_result(self, run_id: str, fingerprint: str, result: ResearchScriptRuntimeResult) -> None:
        with self._lock:
            self._results[run_id] = (fingerprint, result)
