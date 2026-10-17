from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.research_script_service import (
    ResearchScriptService,
    ResearchScriptValidationError,
)
from src.models.research_script import ResearchScriptCreateRequest, ResearchScriptRunCreateRequest
from src.services.openai_research_script_runtime import OpenAICodeInterpreterRuntime
from src.services.research_script_runtime import ResearchScriptRuntimeInputFile, ResearchScriptRuntimeRequest
from src.services.research_script_store import ResearchScriptStore


SOURCE = "print('exact source fixture')\n"


class ExpiredContainerError(RuntimeError):
    status_code = 410
    code = "container_expired"


class FakeContainerContent:
    def __init__(self, files: "FakeContainerFiles") -> None:
        self.files = files

    def retrieve(self, file_id: str, *, container_id: str):
        record = self.files.records[file_id]
        assert record.container_id == container_id
        return SimpleNamespace(content=self.files.contents[file_id])


class FakeContainerFiles:
    def __init__(self) -> None:
        self.records: dict[str, SimpleNamespace] = {}
        self.contents: dict[str, bytes] = {}
        self.create_calls: list[dict[str, object]] = []
        self.content = FakeContainerContent(self)
        self._next = 0

    def create(self, *, container_id: str, file):
        filename, content, media_type = file
        self.create_calls.append(
            {"container_id": container_id, "filename": filename, "media_type": media_type, "content": content}
        )
        return self._add(container_id, filename, content, source="user")

    def add_generated(self, container_id: str, filename: str, content: bytes):
        return self._add(container_id, filename, content, source="assistant")

    def _add(self, container_id: str, filename: str, content: bytes, *, source: str):
        self._next += 1
        file_id = f"file-{self._next}"
        row = SimpleNamespace(
            id=file_id,
            container_id=container_id,
            path=f"/mnt/data/{filename}",
            bytes=len(content),
            source=source,
        )
        self.records[file_id] = row
        self.contents[file_id] = bytes(content)
        return row

    def list(self, *, container_id: str, limit: int):
        assert limit == 100
        return SimpleNamespace(
            data=[item for item in self.records.values() if item.container_id == container_id]
        )


class FakeContainers:
    def __init__(self) -> None:
        self.files = FakeContainerFiles()
        self.create_calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(id=f"container-{len(self.create_calls)}")


class FakeResponses:
    def __init__(
        self,
        containers: FakeContainers,
        *,
        expire_first: bool = False,
        returned_code: str | None = None,
        generated_filename: str = "returns.csv",
        generated_bytes: bytes = b"month,cumulative_return\n2026-01,0.01\n",
        annotation_filename: str | None = None,
        status: str = "completed",
        summary_text: str | None = None,
        fence_returned_code: bool = False,
        extra_files: tuple[tuple[str, bytes, bool], ...] = (),
        cite_uploaded_inputs: bool = False,
    ) -> None:
        # extra_files: (ruta bajo /mnt/data, contenido, citado) que la ejecución deja en el contenedor,
        # p. ej. las copias de entrada que el wrapper hace en el workspace de la ejecución.
        self.extra_files = extra_files
        # cite_uploaded_inputs: el modelo cita también los ficheros de entrada subidos originalmente.
        self.cite_uploaded_inputs = cite_uploaded_inputs
        self.fence_returned_code = fence_returned_code
        self.containers = containers
        self.expire_first = expire_first
        self.returned_code = returned_code
        self.generated_filename = generated_filename
        self.generated_bytes = generated_bytes
        self.annotation_filename = annotation_filename
        self.status = status
        self.summary_text = summary_text
        self.create_calls: list[dict[str, object]] = []
        self.cancel_calls: list[str] = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.expire_first and len(self.create_calls) == 1:
            raise ExpiredContainerError("container expired")
        container_id = kwargs["tools"][0]["container"]
        match = re.search(r"```python\n(.*?)\n```", str(kwargs["input"]), re.DOTALL)
        assert match
        code = self.returned_code if self.returned_code is not None else match.group(1)
        if self.fence_returned_code:
            code = "```python\n" + code + "\n```\n"
        generated = self.containers.files.add_generated(
            container_id,
            self.generated_filename,
            self.generated_bytes,
        )
        annotation = SimpleNamespace(
            type="container_file_citation",
            container_id=container_id,
            file_id=generated.id,
            filename=self.annotation_filename or self.generated_filename,
        )
        annotations = [annotation]
        uploaded_inputs = [
            row for row in self.containers.files.records.values()
            if row.container_id == container_id and row.source == "user" and row.path.endswith(".csv")
        ]
        for path, content, cited in self.extra_files:
            extra = self.containers.files.add_generated(container_id, path, content)
            if cited:
                annotations.append(SimpleNamespace(type="container_file_citation", container_id=container_id,
                    file_id=extra.id, filename=path.rsplit("/", 1)[-1]))
        if self.cite_uploaded_inputs:
            annotations.extend(
                SimpleNamespace(type="container_file_citation", container_id=container_id,
                    file_id=row.id, filename=row.path.rsplit("/", 1)[-1])
                for row in uploaded_inputs
            )
        call = SimpleNamespace(
            type="code_interpreter_call",
            id=f"ci-{len(self.create_calls)}",
            status="completed",
            code=code,
            outputs=[SimpleNamespace(type="logs", logs="exact source executed")],
        )
        message = SimpleNamespace(
            type="message",
            id=f"message-{len(self.create_calls)}",
            content=[
                SimpleNamespace(
                    type="output_text",
                    text=self.summary_text or (
                        f"[Download {self.generated_filename}]"
                        f"(sandbox:/mnt/data/{self.generated_filename})\n"
                        "Generated the requested retained outputs."
                    ),
                    annotations=annotations,
                )
            ],
        )
        return SimpleNamespace(
            id=f"response-{len(self.create_calls)}",
            status=self.status,
            output=[call, message],
            usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30),
            incomplete_details=None,
            error=None,
        )

    def cancel(self, response_id: str):
        self.cancel_calls.append(response_id)
        return SimpleNamespace(status="cancelled")


class FakeOpenAIClient:
    def __init__(self, **response_options) -> None:
        self.containers = FakeContainers()
        self.responses = FakeResponses(self.containers, **response_options)


INPUT_BYTES = b"date,close\n2026-01-01,100\n"


def request(*, run_id: str = "run-1", source: str = SOURCE) -> ResearchScriptRuntimeRequest:
    input_bytes = INPUT_BYTES
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    manifest = {
        "contract_version": "research-script-input.v1",
        "script_id": "script-1",
        "files": [
            {
                "logical_filename": "prices.csv",
                "media_type": "text/csv",
                "byte_size": len(input_bytes),
                "content_sha256": hashlib.sha256(input_bytes).hexdigest(),
                "gamma_object_id": "prices-spy-monthly",
                "provider_id": "gamma-fixture",
                "source_timestamp": None,
                "retrieved_at": "2026-08-29T12:00:00",
                "transformation_note": "Gamma-provided historical-price snapshot",
                "source_kind": "gamma_state",
            }
        ],
        "dataset_refs": [{"dataset_id": "spy-monthly", "version": "v1"}],
        "source_refs": [{"provider": "gamma-fixture", "coverage": "2024-01/2026-08"}],
        "total_bytes": len(input_bytes),
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return ResearchScriptRuntimeRequest(
        run_id=run_id,
        script_id="script-1",
        revision_id="revision-1",
        source=source,
        source_sha256=source_hash,
        input_snapshot_id="snapshot-1",
        input_manifest_sha256=manifest_hash,
        input_manifest=manifest,
        input_files=[
            ResearchScriptRuntimeInputFile(
                logical_filename="prices.csv",
                media_type="text/csv",
                content_sha256=hashlib.sha256(input_bytes).hexdigest(),
                content=input_bytes,
            )
        ],
        limits={
            "run_duration_seconds": 120,
            "output_artifacts": 32,
            "total_output_bytes": 64 * 1024 * 1024,
        },
        started_at=datetime(2026, 8, 29, 12, 0, 0),
    )


def runtime(client: FakeOpenAIClient, *, model: str = "gpt-5.6-luna") -> OpenAICodeInterpreterRuntime:
    return OpenAICodeInterpreterRuntime(
        api_key="configured-test-key",
        model=model,
        client=client,
    )


def test_capability_detection_is_sanitized_and_model_specific() -> None:
    available = runtime(FakeOpenAIClient()).capabilities()
    unsupported = runtime(FakeOpenAIClient(), model="gpt-5.6-pro").capabilities()

    assert available.available is True
    assert available.network_access is False
    assert available.supports_cancellation is False
    assert available.model == "gpt-5.6-luna"
    assert set(available.supported_output_types) >= {"table", "image", "file"}
    assert unsupported.available is False
    assert "lacks_verified" in unsupported.sanitized_provider_status
    assert "key" not in repr(available).lower()


def test_explicit_sol_code_interpreter_support_preserves_unknown_model_refusal():
    capabilities = runtime(FakeOpenAIClient(), model="gpt-6.1-sol").capabilities()
    assert capabilities.available and capabilities.executes_source
    assert capabilities.model == "gpt-6.1-sol"
    assert not capabilities.network_access
    assert not runtime(FakeOpenAIClient(), model="gpt-6.1-other").capabilities().available


@pytest.mark.parametrize("path,filename,expected", [
    ("gamma-run-run-1/gamma_analytics.json", "gamma_analytics.json", True),
    ("gamma-run-older/gamma_analytics.json", "gamma_analytics.json", False),
    ("gamma_analytics.json", "gamma_analytics.json", False),
    ("gamma-run-run-1/prices.csv", "prices.csv", False),
])
def test_artifact_run_association_requires_current_workspace_and_excludes_inputs(path, filename, expected):
    client = FakeOpenAIClient(generated_filename=path, annotation_filename=filename, generated_bytes=b"{}")
    result = runtime(client).start_run(request())
    assert result.status == "completed"
    retained = next(o for o in result.outputs if o.artifact_bytes is not None)
    assert retained.run_association_verified is expected


def test_preexisting_provider_citation_cannot_establish_new_artifact_association(monkeypatch):
    client = FakeOpenAIClient(generated_filename="gamma-run-run-1/gamma_analytics.json", annotation_filename="gamma_analytics.json", generated_bytes=b"{}")
    adapter = runtime(client)
    # Provider citation/path may look right, but the file identity existed before dispatch.
    monkeypatch.setattr(adapter, "_container_file_ids", lambda *args: {f"file-{client.containers.files._next + 1}"})
    result = adapter.start_run(request())
    retained = next(o for o in result.outputs if o.artifact_bytes is not None)
    assert retained.run_association_verified is False


@pytest.mark.parametrize("cited", [False, True])
def test_unchanged_input_copies_and_uploads_are_not_retained_as_run_outputs(cited):
    # Regresión (E3 en vivo, 2026-10-16): el wrapper copia cada entrada al workspace de la ejecución
    # y esas copias se retenían como salidas `file`. Una copia sin cambios es una entrada, citada o no.
    client = FakeOpenAIClient(
        generated_filename="gamma-run-run-1/comparison.csv",
        annotation_filename="comparison.csv",
        extra_files=(("gamma-run-run-1/prices.csv", INPUT_BYTES, cited),),
        cite_uploaded_inputs=cited,
    )
    result = runtime(client).start_run(request())

    assert result.status == "completed"
    retained = [o for o in result.outputs if o.artifact_bytes is not None]
    assert [o.filename for o in retained] == ["comparison.csv"]
    # E4: el artefacto nuevo del workspace exacto sigue verificado como asociado a la ejecución.
    assert retained[0].run_association_verified is True
    assert not any("prices.csv" in warning for warning in result.warnings)
    assert result.usage["excluded_input_copies"] == [
        {"filename": "prices.csv", "content_sha256": hashlib.sha256(INPUT_BYTES).hexdigest()}
    ]


def test_input_copies_do_not_consume_the_output_artifact_limit():
    client = FakeOpenAIClient(
        generated_filename="gamma-run-run-1/comparison.csv",
        annotation_filename="comparison.csv",
        extra_files=(("gamma-run-run-1/prices.csv", INPUT_BYTES, False),),
    )
    limited = request()
    # Límite = salidas reales (log + summary + tabla); la copia de entrada no debe hacerlo saltar.
    limited = ResearchScriptRuntimeRequest(**{**limited.__dict__, "limits": {**limited.limits, "output_artifacts": 3}})
    result = runtime(client).start_run(limited)

    assert result.status == "completed"
    assert [o.filename for o in result.outputs if o.artifact_bytes is not None] == ["comparison.csv"]


def test_link_only_provider_message_is_not_retained_as_summary():
    # Regresión (E3 en vivo, 2026-10-16): el mensaje «[comparison.csv](sandbox:…)» se retenía como
    # `summary` con la plantilla literal «[comparison.csv]({retained_artifact})».
    client = FakeOpenAIClient(
        generated_filename="gamma-run-run-1/comparison.csv",
        annotation_filename="comparison.csv",
        summary_text=(
            "[comparison.csv](sandbox:/mnt/data/gamma-run-run-1/comparison.csv)\n"
            "- [prices.csv](sandbox:/mnt/data/gamma-run-run-1/prices.csv)"
        ),
    )
    result = runtime(client).start_run(request())

    assert result.status == "completed"
    assert not any(o.kind == "summary" for o in result.outputs)
    assert [o.filename for o in result.outputs if o.artifact_bytes is not None] == ["comparison.csv"]
    assert "{retained_artifact}" not in repr(result)


def test_provider_links_render_as_filenames_and_inputs_are_labeled():
    client = FakeOpenAIClient(
        generated_filename="gamma-run-run-1/returns.csv",
        annotation_filename="returns.csv",
        summary_text=(
            "Computed monthly returns.\n"
            "[returns.csv](sandbox:/mnt/data/gamma-run-run-1/returns.csv) derives from "
            "[Download prices.csv](sandbox:/mnt/data/gamma-run-run-1/prices.csv); "
            "raw path sandbox:/mnt/data/gamma-run-run-1/returns.csv"
        ),
    )
    result = runtime(client).start_run(request())

    summary = next(o for o in result.outputs if o.kind == "summary")
    assert summary.text == (
        "Computed monthly returns.\n"
        "Retained artifact: returns.csv derives from Input file: prices.csv; raw path returns.csv"
    )
    for leaked in ("{retained_artifact}", "sandbox:", "/mnt/data", "]("):
        assert leaked not in (summary.text or "")


def test_request_is_exact_source_network_disabled_and_code_interpreter_only() -> None:
    client = FakeOpenAIClient()
    adapter = runtime(client)
    result = adapter.start_run(request())

    assert result.status == "completed"
    assert result.executed_source_sha256 == request().source_sha256
    assert result.provider_response_id == "response-1"
    assert result.provider_container_id == "container-1"
    assert client.containers.create_calls[0]["network_policy"] == {"type": "disabled"}
    assert client.containers.create_calls[0]["memory_limit"] == "1g"
    call = client.responses.create_calls[0]
    assert call["tools"] == [{"type": "code_interpreter", "container": "container-1"}]
    assert call["include"] == ["code_interpreter_call.outputs"]
    assert call["tool_choice"] == "required"
    assert call["max_tool_calls"] == 1
    assert call["parallel_tool_calls"] is False
    assert call["store"] is False
    serialized = json.dumps(call, default=str).lower()
    for forbidden in ("web_search", "shell", "mcp", "localhost", "broker", "wallet", "api_key"):
        assert forbidden not in serialized
    assert result.usage["source_sha256"] == request().source_sha256
    assert result.usage["input_manifest_sha256"] == request().input_manifest_sha256
    assert "{container_root}" in result.usage["executed_wrapper"]
    assert "/mnt/data" not in json.dumps(result.usage)


def test_container_reuse_output_normalization_and_terminal_idempotency() -> None:
    client = FakeOpenAIClient()
    adapter = runtime(client)
    first = adapter.start_run(request(run_id="run-a"))
    second = adapter.start_run(request(run_id="run-b"))
    replay = adapter.start_run(request(run_id="run-a"))

    assert len(client.containers.create_calls) == 1
    assert len(client.responses.create_calls) == 2
    assert replay == first
    assert {item.kind for item in first.outputs} >= {"log", "summary", "table"}
    summary = next(item for item in first.outputs if item.kind == "summary")
    assert "sandbox:" not in (summary.text or "")
    assert "/mnt/data" not in (summary.text or "")
    assert "Retained artifact: returns.csv" in (summary.text or "")
    table = next(item for item in first.outputs if item.kind == "table")
    assert table.filename == "returns.csv"
    assert table.columns == ["month", "cumulative_return"]
    assert table.rows == [{"month": "2026-01", "cumulative_return": "0.01"}]
    assert table.artifact_bytes == b"month,cumulative_return\n2026-01,0.01\n"


def test_altered_wrapper_fails_exact_source_gate() -> None:
    client = FakeOpenAIClient(returned_code="print('provider rewrote source')")
    result = runtime(client).start_run(request())

    assert result.status == "incomplete"
    assert result.executed_source_sha256 is None
    assert any("exact-source" in warning for warning in result.warnings)
    assert result.usage["executed_wrapper_sha256"] != result.usage["expected_wrapper_sha256"]


def test_fenced_but_identical_wrapper_reports_matching_normalized_hashes() -> None:
    # Regresión (validación en vivo 2026-10-16): los hashes en bruto diferían aunque la
    # validación normalizada confirmaba el wrapper exacto, y el modelo lo sintetizaba como discrepancia.
    client = FakeOpenAIClient(fence_returned_code=True)
    result = runtime(client).start_run(request())

    assert result.status == "completed" and result.usage["executed_code"] is True
    assert result.usage["executed_wrapper_sha256"] == result.usage["expected_wrapper_sha256"]
    assert result.usage["wrapper_hash_basis"] == "normalized_code"


def test_provider_reported_python_failure_maps_to_typed_failed_terminal_state() -> None:
    client = FakeOpenAIClient(
        summary_text=(
            "Execution failed with:\n\n"
            "`FileNotFoundError: [Errno 2] No such file or directory: 'prices.csv'`"
        )
    )

    result = runtime(client).start_run(request())

    assert result.status == "failed"
    assert result.executed_source_sha256 == request().source_sha256
    assert any(item.kind == "error" for item in result.outputs)
    assert any("provider execution failed" in warning.lower() for warning in result.warnings)


def test_expired_container_replays_same_immutable_bundle_once() -> None:
    client = FakeOpenAIClient(expire_first=True)
    result = runtime(client).start_run(request())

    assert result.status == "completed"
    assert len(client.containers.create_calls) == 2
    assert result.usage["expired_container_replay"] is True
    source_uploads = [
        call for call in client.containers.files.create_calls if str(call["filename"]).endswith(".py")
    ]
    assert len(source_uploads) == 2
    assert source_uploads[0]["content"] == source_uploads[1]["content"] == SOURCE.encode("utf-8")


def test_path_traversal_and_oversized_provider_output_are_rejected(tmp_path: Path) -> None:
    traversal_client = FakeOpenAIClient(annotation_filename="../secret.csv")
    traversal_result = runtime(traversal_client).start_run(request())
    service = ResearchScriptService(ResearchScriptStore(tmp_path / "traversal"), runtime(traversal_client))
    with pytest.raises(ResearchScriptValidationError, match="filename is unsafe"):
        service._normalize_outputs("run", traversal_result.outputs, datetime(2026, 8, 29))

    oversized = FakeOpenAIClient(generated_bytes=b"x" * 11)
    oversized_request = request(run_id="oversized")
    oversized_request = ResearchScriptRuntimeRequest(
        **{**oversized_request.__dict__, "limits": {**oversized_request.limits, "total_output_bytes": 10}}
    )
    result = runtime(oversized).start_run(oversized_request)
    assert result.status == "failed"
    assert any("output bytes exceeded" in warning for warning in result.warnings)


def test_retained_artifact_survives_restart_and_has_no_provider_url(tmp_path: Path) -> None:
    store = ResearchScriptStore(tmp_path / "retained")
    service = ResearchScriptService(store, runtime(FakeOpenAIClient()))
    detail = service.create_script(
        ResearchScriptCreateRequest(session_id="session", title="Retained", source=SOURCE)
    )
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
    table = next(item for item in run.outputs if item.kind == "table")

    assert all(output.source_provider == "openai" for output in run.outputs)
    assert all(output.origin == "openai_code_interpreter_v1.collect_outputs" for output in run.outputs)

    restarted = ResearchScriptService(
        ResearchScriptStore(tmp_path / "retained"),
        runtime(FakeOpenAIClient()),
    )
    filename, media_type, content = restarted.get_output_artifact(run.run_id, table.output_id)
    assert (filename, media_type) == ("returns.csv", "text/csv")
    assert content.startswith(b"month,cumulative_return")
    assert "http" not in (table.artifact_ref or "")


def test_timeout_provider_errors_and_cancellation_are_sanitized() -> None:
    client = FakeOpenAIClient()
    adapter = runtime(client)

    class ProviderTimeoutError(RuntimeError):
        pass

    client.responses.create = lambda **kwargs: (_ for _ in ()).throw(ProviderTimeoutError("secret=do-not-leak"))
    result = adapter.start_run(request(run_id="timeout"))
    assert result.status == "timed_out"
    assert "do-not-leak" not in repr(result)
    cancelled = adapter.cancel_run("unknown-run")
    assert cancelled.cancelled is False
    assert "synchronous" in cancelled.message


def test_hash_mismatch_blocks_provider_dispatch() -> None:
    client = FakeOpenAIClient()
    adapter = runtime(client)
    invalid = request()
    invalid = ResearchScriptRuntimeRequest(**{**invalid.__dict__, "source_sha256": "0" * 64})
    result = adapter.start_run(invalid)

    assert result.status == "incomplete"
    assert result.executed_source_sha256 is None
    assert not client.containers.create_calls
    assert not client.responses.create_calls
