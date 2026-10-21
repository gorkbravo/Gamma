"""E4 deterministic fixtures. FixtureRuntime reports execution for gate testing only;
these tests do not execute Python and are not live runtime certification.
"""
from dataclasses import replace
from copy import deepcopy
import io
import json
import math
from types import SimpleNamespace
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.routes.research import router
from src.api.schemas.research import StrategyLabAnalyzeResponseModel
from src.application.research_script_service import ResearchScriptService, ResearchScriptValidationError
from src.application.research_service import ResearchService
from src.application.script_analytics import inspect_analytics, open_analytics, parse_payload
from src.models.research_lab import ImportedReturnStreamRequest, SavedResearchCreateRequest
from src.models.research_script import ResearchScriptCreateRequest, ResearchScriptRunCreateRequest, ResearchScriptRevisionCreateRequest
from src.models.script_analytics import MAX_BYTES
from src.services.research_script_runtime import MockResearchScriptRuntime, ResearchScriptRuntimeOutput
from src.services.research_script_store import ResearchScriptStore
from src.services.saved_research_store import SavedResearchStore


def payload():
    base = dict(result_id="returns", name="Exact experiment", meaning="Daily holding-period return", methodology="Supplied deterministic calculation", assumptions=["No costs"], limitations=["Six observations only"])
    series = dict(instrument_id="research:book", frequency="daily", observations=[
        {"date": f"2026-10-{day:02}", "value": value}
        for day, value in zip([1, 2, 5, 6, 7, 8], [1.0, -2.0, 0.5, 3.0, -1.0, 2.0])])
    return {"contract_version": "gamma-script-analytics.v1", "instruments": [dict(instrument_id="research:book", namespace="research", native_id="book", label="Hypothetical book")], "results": [
        dict(base, **series, kind="returns", unit="percent", return_type="simple", periods_per_year=252),
        dict(base, result_id="metric", kind="metric", value=0.03, unit="fraction", as_of="2026-10-08", instrument_id=None),
        dict(base, **series, result_id="signal", kind="signals", unit="score"),
        dict(base, **series, result_id="weights", kind="weights", unit="fraction_nav", weight_semantics="signed_nav_exposure", hypothetical=True),
    ]}


class NoProvider:
    def __getattr__(self, name):
        raise AssertionError(f"E4 must not acquire provider data: {name}")


class FixtureRuntime(MockResearchScriptRuntime):
    def __init__(self, data, *, executed=True, status="completed", associated=True):
        self.data, self.executed, self.status, self.associated = data, executed, status, associated

    def capabilities(self):
        return replace(super().capabilities(), provider="e4_deterministic_fixture",
                       runtime_kind="e4_fixture" if self.executed else "mock_safe_preview", executes_source=self.executed)

    def start_run(self, request):
        result = super().start_run(request)
        outputs = [ResearchScriptRuntimeOutput(output_id="log", kind="log", sequence=1, media_type="text/plain", text="Standalone retained log")]
        if self.data is not None:
            outputs.append(ResearchScriptRuntimeOutput(output_id="analytics", kind="file", sequence=2, media_type="application/json", filename="gamma_analytics.json", artifact_bytes=self.data, run_association_verified=True))
        return replace(result, status=self.status, outputs=outputs,
                       usage={**result.usage, "executed_code": self.executed},
                       executed_source_sha256=request.source_sha256 if self.associated else None)


def service_run(tmp_path, data=None, **kwargs):
    owner = ResearchService(NoProvider(), SavedResearchStore(base_dir=tmp_path / "saved"))
    service = ResearchScriptService(ResearchScriptStore(base_dir=tmp_path / "scripts"), FixtureRuntime(data, **kwargs), research_service=owner)
    detail = service.create_script(ResearchScriptCreateRequest(session_id="test", title="E4", source="print('ordinary Python')"))
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
    return service, run


def test_optional_and_all_four_kinds(tmp_path):
    service, run = service_run(tmp_path)
    assert inspect_analytics(service, run.run_id)["artifacts"] == []
    service, run = service_run(tmp_path / "typed", json.dumps(payload()).encode())
    artifact = inspect_analytics(service, run.run_id)["artifacts"][0]
    assert artifact["valid"] and artifact["eligible"]
    assert [r["can_open"] for r in artifact["results"]] == [True, False, False, False]
    # El calendario de pesos no se abre por sí solo: solo a través del libro causal (cierre E4).
    assert "causal weight book" in artifact["results"][3]["unsupported_reason"]
    assert artifact["results"][3]["result"]["observations"][1]["value"] == -2
    book = artifact["weight_book"]
    assert book["can_open"] and book["weight_result_ids"] == ["weights"] and book["return_result_ids"] == ["returns"]


def test_open_fidelity_restart_edit_save_and_export(tmp_path):
    service, run = service_run(tmp_path, json.dumps(payload()).encode())
    report = inspect_analytics(service, run.run_id)["artifacts"][0]
    item = report["results"][0]
    assert service.research_service.list_saved_research() == []
    analysis, evidence = open_analytics(service, run.run_id, "analytics", "returns", item["preview_sha256"])
    expected = service.research_service.analyze_strategy_lab(ImportedReturnStreamRequest(rows=item["mapping"]["rows"], date_column="date", value_column="value"))
    assert analysis.returns.equals(expected.returns)
    assert analysis.metrics == expected.metrics
    independent = math.prod(1 + v / 100 for v in [1, -2, .5, 3, -1, 2]) - 1
    assert analysis.metrics.total_return == pytest.approx(independent, abs=1e-14)
    assert service.research_service.list_saved_research() == []  # open is non-durable, including repeats
    open_analytics(service, run.run_id, "analytics", "returns", item["preview_sha256"])
    saved_payload = StrategyLabAnalyzeResponseModel.from_domain(analysis).model_dump(mode="json")
    saved_payload["analytical_provenance"] = evidence
    saved = service.research_service.save_research(SavedResearchCreateRequest(object_type="strategy_lab", title="Explicit save", payload=saved_payload))
    restarted = ResearchScriptService(ResearchScriptStore(base_dir=tmp_path / "scripts"), MockResearchScriptRuntime(), research_service=ResearchService(NoProvider(), SavedResearchStore(base_dir=tmp_path / "saved")))
    assert inspect_analytics(restarted, run.run_id) == inspect_analytics(service, run.run_id)
    assert restarted.research_service.load_saved_research(saved.id).payload["analytical_provenance"] == evidence
    service.create_revision(run.script_id, ResearchScriptRevisionCreateRequest(source="print('later')", expected_parent_sha256=run.source_sha256))
    assert inspect_analytics(service, run.run_id)["artifacts"][0]["results"][0]["preview_sha256"] == item["preview_sha256"]
    _, bundle = restarted.export_run_bundle(run.run_id)
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert json.loads(archive.read("analytical_validation.json"))["artifacts"][0]["provenance"] == report["provenance"]
        assert archive.read("outputs/analytics-gamma_analytics.json") == json.dumps(payload()).encode()
    with pytest.raises(ResearchScriptValidationError):
        open_analytics(service, run.run_id, "analytics", "returns", "0" * 64)


@pytest.mark.parametrize("change", [
    lambda p: p.update(contract_version="v2"),
    lambda p: p["results"][0]["observations"][0].update(date="2026-02-30"),
    lambda p: p["results"][0]["observations"][1].update(date="2026-10-01"),
    lambda p: p["results"][0]["observations"].reverse(),
    lambda p: p["results"][0]["observations"][0].update(value=float("inf")),
    lambda p: p["results"][0]["observations"][0].update(value=True),
    lambda p: p["results"][0].update(unit="price"),
    lambda p: p["results"][0].update(return_type="cumulative_performance"),
    lambda p: p["results"][0].update(instrument_id="other"),
    lambda p: p["results"][3].update(weight_semantics="gross_normalized"),
    lambda p: p["results"][3].update(hypothetical=False),
    lambda p: p["results"][3].update(unit="percent"),
    lambda p: p["results"][0].update(frequency="hourly"),
    lambda p: p["results"][0].update(periods_per_year=float("nan")),
    lambda p: p["instruments"].append(p["instruments"][0]),
])
def test_invalid_optional_does_not_change_execution_or_logs(tmp_path, change):
    data = payload(); change(data)
    service, run = service_run(tmp_path, json.dumps(data).encode())
    report = inspect_analytics(service, run.run_id)["artifacts"][0]
    assert not report["valid"] and not report["eligible"] and report["errors"]
    assert service.get_run(run.run_id).status == "completed"
    assert service.get_run(run.run_id).outputs[0].text == "Standalone retained log"
    assert service.get_output_artifact(run.run_id, "analytics")[2] == json.dumps(data).encode()


@pytest.mark.parametrize("data", [b"{", b'{"contract_version":"x","contract_version":"y"}', b" " * (MAX_BYTES + 1), b'{"value":1e999}'], ids=["malformed", "duplicate_keys", "oversized", "overflow"])
def test_malformed_and_oversize(data):
    with pytest.raises((ValueError, ValidationError)):
        parse_payload(data)


def test_oversized_optional_artifact_keeps_standalone_execution(tmp_path):
    service, run = service_run(tmp_path, b" " * (MAX_BYTES + 1))
    artifact = inspect_analytics(service, run.run_id)["artifacts"][0]
    assert not artifact["valid"] and "exceeds" in artifact["errors"][0]
    assert service.get_run(run.run_id).status == "completed"
    assert service.get_run(run.run_id).outputs[0].text == "Standalone retained log"


@pytest.mark.parametrize("kwargs", [dict(executed=False), dict(status="failed"), dict(status="incomplete"), dict(status="unavailable"), dict(status="timed_out"), dict(associated=False)])
def test_ineligible_run_cannot_open(tmp_path, kwargs):
    service, run = service_run(tmp_path, json.dumps(payload()).encode(), **kwargs)
    with pytest.raises(ResearchScriptValidationError):
        open_analytics(service, run.run_id, "analytics", "returns", "0" * 64)
    assert not any(a["eligible"] for a in inspect_analytics(service, run.run_id)["artifacts"])


@pytest.mark.parametrize("change,reason", [
    (lambda p: p["results"][0]["observations"][0].update(value=None), "Missing observations"),
    (lambda p: p["results"][0].update(return_type="log"), "Log returns"),
    (lambda p: p["results"][0].update(frequency="irregular"), "daily returns only"),
    (lambda p: p["results"][0].update(periods_per_year=365), "Other calendars"),
])
def test_valid_unsupported_results_preserved(tmp_path, change, reason):
    data = payload(); change(data)
    service, run = service_run(tmp_path, json.dumps(data).encode())
    report = inspect_analytics(service, run.run_id)["artifacts"][0]
    assert report["valid"]
    item = report["results"][0]
    assert not item["can_open"] and reason in item["unsupported_reason"]
    assert item["result"]["observations"] == data["results"][0]["observations"]


def test_tamper_missing_and_other_run_binding(tmp_path):
    service, run = service_run(tmp_path, json.dumps(payload()).encode())
    item = inspect_analytics(service, run.run_id)["artifacts"][0]["results"][0]
    second = service.create_run(run.script_id, ResearchScriptRunCreateRequest())
    with pytest.raises(ResearchScriptValidationError):
        open_analytics(service, second.run_id, "analytics", "returns", item["preview_sha256"])
    # Same-size tampering must fail by content hash, even after restart.
    original = service.store.load_output_artifact
    service.store.load_output_artifact = lambda *args: original(*args).replace(b"Daily", b"daily")
    assert not inspect_analytics(service, run.run_id)["artifacts"][0]["valid"]
    service.store.load_output_artifact = lambda *args: None
    assert not inspect_analytics(service, run.run_id)["artifacts"][0]["valid"]


def test_api_preview_exact_open_and_unavailable_target(tmp_path):
    service, run = service_run(tmp_path, json.dumps(payload()).encode())
    app = FastAPI(); app.include_router(router)
    app.state.runtime = SimpleNamespace(research_script_service=service, research_service=service.research_service)
    client = TestClient(app)
    path = f"/research/strategy-lab/script-runs/{run.run_id}/analytics"
    item = client.get(path).json()["artifacts"][0]["results"][0]
    body = dict(output_id="analytics", result_id="returns", preview_sha256=item["preview_sha256"])
    response = client.post(path + "/open", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["analytical_provenance"]["run_id"] == run.run_id
    assert service.research_service.list_saved_research() == []
    save_body = dict(object_type="strategy_lab", title="Explicit separate save", payload=response.json(), source_provider="gamma_script_analytics")
    assert client.post("/research/saved", json=save_body).status_code == 200
    modified = deepcopy(save_body)
    modified["payload"]["returns_points"][0]["value"] = .99
    assert client.post("/research/saved", json=modified).status_code == 422
    modified = deepcopy(save_body)
    modified["payload"]["analytical_provenance"]["source_sha256"] = "0" * 64
    assert client.post("/research/saved", json=modified).status_code == 422
    assert client.post(path + "/open", json={**body, "preview_sha256": "0" * 64}).status_code == 422
    service.research_service = None
    assert client.post(path + "/open", json=body).status_code == 422


@pytest.mark.parametrize("association", ["source", "manifest", "legacy_hash", "stale_artifact"])
def test_retained_associations_fail_closed(tmp_path, monkeypatch, association):
    service, run = service_run(tmp_path, json.dumps(payload()).encode())
    if association == "source":
        original = service.store.load_revision(run.script_id, run.revision_id)
        monkeypatch.setattr(service.store, "load_revision", lambda *args: replace(original, source="print('changed')"))
    elif association == "manifest":
        original = service.store.load_input_snapshot(run.input_snapshot_id)
        monkeypatch.setattr(service.store, "load_input_snapshot", lambda *args: replace(original, manifest_sha256="0" * 64))
    elif association == "legacy_hash":
        monkeypatch.setattr(service.store, "load_run", lambda *args: replace(run, outputs=[replace(o, content_sha256=None) for o in run.outputs]))
    else:
        monkeypatch.setattr(service.store, "load_run", lambda *args: replace(run, outputs=[replace(o, run_association_verified=False) for o in run.outputs]))
    artifact = inspect_analytics(service, run.run_id)["artifacts"][0]
    assert not artifact["eligible"]
    if association != "stale_artifact":
        assert not artifact["valid"] and artifact["errors"]


def test_authoring_example_stays_ordinary_python_and_schema_inspectable():
    from src.models.script_analytics import AUTHORING_EXAMPLE, AnalyticalPayload
    assert ResearchScriptService._validate_source(AUTHORING_EXAMPLE) == []
    schema = AnalyticalPayload.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "periods_per_year" in schema["$defs"]["Returns"]["required"]


def test_analytical_routes_preserve_session_authorization():
    from src.api.session_auth import GammaSessionMiddleware
    app = FastAPI(); app.include_router(router)
    app.add_middleware(GammaSessionMiddleware, session_token="test-gamma-session")
    client = TestClient(app, headers={"X-Test-No-Gamma-Session": "1"})
    assert client.get("/research/strategy-lab/scripts/analytical-contract").status_code == 401
    assert client.get("/research/strategy-lab/script-runs/foreign/analytics").status_code == 401
    assert client.post("/research/strategy-lab/script-runs/foreign/analytics/open", json={}).status_code == 401
    assert client.post("/research/saved", json={}).status_code == 401
