"""E5: parámetros separados del código, ligados a cada ejecución (sin ejecutar Python en el host)."""
from dataclasses import replace
import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.research import router
from src.application.research_script_service import ResearchScriptService, ResearchScriptValidationError
from src.application.script_analytics import inspect_analytics
from src.application.script_parameters import canonical_parameters, parameter_changes
from src.models.research_script import ResearchScriptInputBundleRequest, ResearchScriptInputFileCreateRequest, ResearchScriptRunCreateRequest
from src.services.research_script_runtime import MockResearchScriptRuntime, ResearchScriptRuntimeRequest
from src.services.research_script_store import ResearchScriptStore

from script_e5_fixtures import E5_SOURCE, e5_service
from test_openai_research_script_runtime import FakeOpenAIClient, INPUT_BYTES, request as runtime_request, runtime


def test_canonical_parameters_are_flat_sorted_and_hash_exact_bytes():
    values, content, digest = canonical_parameters({"slow": 50, "fast": 10, "label": "spy", "use_costs": True, "cap": None, "x": 0.5})
    assert list(values) == ["cap", "fast", "label", "slow", "use_costs", "x"]
    assert content == b'{"cap":null,"fast":10,"label":"spy","slow":50,"use_costs":true,"x":0.5}'
    assert digest == hashlib.sha256(content).hexdigest()
    assert canonical_parameters({"x": 0.5, "fast": 10})[2] == canonical_parameters({"fast": 10, "x": 0.5})[2]


@pytest.mark.parametrize("values,message", [
    ({"nested": {"a": 1}}, "nested"),
    ({"items": [1, 2]}, "nested"),
    ({"x": float("nan")}, "finite"),
    ({"x": float("inf")}, "finite"),
    ({"api_token": "x"}, "credential"),
    ({"order_size": 1}, "credential"),
    ({"1bad": 1}, "must match"),
    ({"url": "https://example.com"}, "network"),
    ({"path": "C:\\data\\x.csv"}, "host paths"),
    ({"big": 2 ** 60}, "2\\*\\*53"),
    ({"text": "x" * 300}, "256"),
    ({f"p{i}": i for i in range(40)}, "count"),
    ("not-an-object", "flat JSON object"),
])
def test_invalid_parameters_are_refused(values, message):
    with pytest.raises(ValueError, match=message):
        canonical_parameters(values)


def test_runs_bind_source_inputs_and_parameters_separately(tmp_path):
    service, detail = e5_service(tmp_path)
    script_id = detail.script.script_id
    first = service.create_run(script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 5, "leverage": 1.0}))
    second = service.create_run(script_id, ResearchScriptRunCreateRequest(revision_id=first.revision_id,
        input_snapshot_id=first.input_snapshot_id, parameters={"lookback": 20, "leverage": 1.0}))
    plain = service.create_run(script_id, ResearchScriptRunCreateRequest(input_snapshot_id=first.input_snapshot_id, parameters={}))
    assert first.source_sha256 == second.source_sha256 and first.input_manifest_sha256 == second.input_manifest_sha256
    assert first.parameters_sha256 != second.parameters_sha256
    assert first.parameters == {"leverage": 1.0, "lookback": 5}
    assert plain.parameters is None and plain.parameters_sha256 is None
    received = service.runtime.requests
    assert received[0].parameters_content == canonical_parameters({"lookback": 5, "leverage": 1.0})[1]
    assert received[0].parameters_sha256 == first.parameters_sha256 and received[2].parameters_content is None
    restarted = ResearchScriptService(ResearchScriptStore(base_dir=tmp_path / "scripts"), MockResearchScriptRuntime())
    assert restarted.get_run(first.run_id) == first
    comparison = service.compare_runs(first.run_id, second.run_id)
    assert not comparison.same_parameters and comparison.same_revision and comparison.same_input_snapshot
    assert comparison.parameter_changes == [{"name": "lookback", "base": 5, "comparison": 20, "base_present": True, "comparison_present": True}]
    provenance = inspect_analytics(service, first.run_id)["artifacts"][0]["provenance"]
    assert provenance["parameters_sha256"] == first.parameters_sha256 and provenance["parameters"]["lookback"] == 5


def test_invalid_parameters_fail_before_any_persistence(tmp_path):
    service, detail = e5_service(tmp_path)
    before = (len(service.list_runs(detail.script.script_id)), len(service.list_input_bundles(detail.script.script_id)))
    with pytest.raises(ResearchScriptValidationError, match="finite"):
        service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"x": float("inf")}))
    assert (len(service.list_runs(detail.script.script_id)), len(service.list_input_bundles(detail.script.script_id))) == before
    assert service.runtime.requests == []


def test_parameter_filename_is_reserved_only_when_parameters_are_supplied(tmp_path):
    service, detail = e5_service(tmp_path)
    bundle = service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest(input_files=[
        ResearchScriptInputFileCreateRequest(logical_filename="gamma_parameters.json", media_type="application/json", content=b"{}")]))
    with pytest.raises(ResearchScriptValidationError, match="reserved"):
        service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(input_snapshot_id=bundle.snapshot_id, parameters={"lookback": 5, "leverage": 1.0}))
    assert service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(input_snapshot_id=bundle.snapshot_id)).status == "completed"


def test_export_bundle_contains_the_exact_parameter_bytes_and_tamper_fails_closed(tmp_path, monkeypatch):
    service, detail = e5_service(tmp_path)
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 5, "leverage": 2}))
    _, content = service.export_run_bundle(run.run_id)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.read("input/gamma_parameters.json") == canonical_parameters({"lookback": 5, "leverage": 2})[1]
        assert json.loads(archive.read("run.json"))["parameters_sha256"] == run.parameters_sha256
    monkeypatch.setattr(service.store, "load_run", lambda *args: replace(run, parameters={"lookback": 6, "leverage": 2}))
    artifact = inspect_analytics(service, run.run_id)["artifacts"][0]
    assert not artifact["valid"] and "parameter" in artifact["errors"][0]


def test_legacy_run_records_without_parameter_fields_still_load(tmp_path):
    service, detail = e5_service(tmp_path)
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
    path = tmp_path / "scripts" / "runs" / run.script_id / f"{run.run_id}.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    for key in ("parameters", "parameters_sha256", "sweep_id", "sweep_point_index"):
        envelope["payload"].pop(key)
    path.write_text(json.dumps(envelope), encoding="utf-8")
    reloaded = ResearchScriptStore(base_dir=tmp_path / "scripts").load_run(run.run_id)
    assert reloaded is not None and reloaded.parameters is None and reloaded.sweep_id is None


def test_parameter_changes_report_missing_and_type_changes():
    assert parameter_changes({"a": 1, "b": 2}, {"a": 1.0, "c": 3}) == [
        {"name": "a", "base": 1, "comparison": 1.0, "base_present": True, "comparison_present": True},
        {"name": "b", "base": 2, "comparison": None, "base_present": True, "comparison_present": False},
        {"name": "c", "base": None, "comparison": 3, "base_present": False, "comparison_present": True},
    ]


def test_api_run_accepts_parameters_and_refuses_invalid_ones(tmp_path):
    service, detail = e5_service(tmp_path)
    app = FastAPI(); app.include_router(router)
    app.state.runtime = SimpleNamespace(research_script_service=service, research_service=service.research_service)
    client = TestClient(app)
    path = f"/research/strategy-lab/scripts/{detail.script.script_id}/runs"
    response = client.post(path, json={"parameters": {"lookback": 10, "leverage": 1.5}})
    assert response.status_code == 201, response.text
    assert response.json()["parameters"] == {"leverage": 1.5, "lookback": 10}
    assert response.json()["parameters_sha256"] == canonical_parameters({"lookback": 10, "leverage": 1.5})[2]
    assert client.post(path, json={"parameters": {"secret_key": "x"}}).status_code == 422


# ---- Adaptador Code Interpreter (cliente falso; no hay llamada a OpenAI) ----

def parameterized_request(values):
    _, content, digest = canonical_parameters(values)
    return ResearchScriptRuntimeRequest(**{**runtime_request().__dict__, "parameters_content": content, "parameters_sha256": digest})


def test_code_interpreter_uploads_and_verifies_parameters_in_the_wrapper():
    client = FakeOpenAIClient(generated_filename="gamma-run-run-1/gamma_analytics.json", annotation_filename="gamma_analytics.json",
                              extra_files=(("gamma-run-run-1/gamma_parameters.json", canonical_parameters({"lookback": 5})[1], True),),
                              generated_bytes=b"{}")
    request = parameterized_request({"lookback": 5})
    result = runtime(client).start_run(request)
    assert result.status == "completed" and result.usage["executed_code"] is True
    uploads = {call["filename"]: call["content"] for call in client.containers.files.create_calls}
    parameter_upload = f"gamma-parameters-{request.parameters_sha256[:16]}.json"
    assert uploads[parameter_upload] == request.parameters_content
    wrapper = result.usage["executed_wrapper"]
    assert request.parameters_sha256 in wrapper and "gamma_parameters.json" in wrapper
    assert wrapper.index("copied_parameters") < wrapper.index("initial_files")
    retained = [o.filename for o in result.outputs if o.artifact_bytes is not None]
    assert retained == ["gamma_analytics.json"]  # la copia de parámetros es entrada, no resultado
    assert {"filename": "gamma_parameters.json", "content_sha256": request.parameters_sha256} in result.usage["excluded_input_copies"]
    assert result.usage["parameters_sha256"] == request.parameters_sha256


def test_container_reuse_uploads_each_parameter_set_once_and_plain_wrapper_is_unchanged():
    client = FakeOpenAIClient()
    adapter = runtime(client)
    plain = adapter.start_run(runtime_request(run_id="run-plain"))
    assert "gamma_parameters" not in plain.usage["executed_wrapper"] and plain.usage["parameters_sha256"] is None
    for run_id, values in [("run-a", {"lookback": 5}), ("run-b", {"lookback": 5}), ("run-c", {"lookback": 20})]:
        request = ResearchScriptRuntimeRequest(**{**parameterized_request(values).__dict__, "run_id": run_id})
        assert adapter.start_run(request).status == "completed"
    names = [call["filename"] for call in client.containers.files.create_calls]
    assert len(client.containers.create_calls) == 1  # mismo fuente + manifiesto: mismo contenedor
    assert sum(name.startswith("gamma-parameters-") for name in names) == 2


def test_parameter_hash_mismatch_blocks_dispatch():
    client = FakeOpenAIClient()
    request = ResearchScriptRuntimeRequest(**{**parameterized_request({"lookback": 5}).__dict__, "parameters_sha256": "0" * 64})
    result = runtime(client).start_run(request)
    assert result.status == "incomplete" and client.responses.create_calls == []
    assert INPUT_BYTES  # el resto del contrato del adaptador no cambia
