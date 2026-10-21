"""E5: barridos de parámetros y walk-forward causal (fixtures deterministas; no se ejecuta Python)."""
import json
import math
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.analytics.script_walk_forward import WalkForwardConfig, WalkForwardError, describe, run_walk_forward, selection_value
from src.analytics.script_weight_book import BookOptions
from src.api.routes.research import router
from src.application import script_experiments
from src.application.research_script_service import (
    ResearchScriptConflictError, ResearchScriptNotFoundError, ResearchScriptService, ResearchScriptServiceError,
    ResearchScriptValidationError,
)
from src.application.script_experiments import EvaluationTarget
from src.models.research_script import (
    ResearchScriptCreateRequest, ResearchScriptInputBundleRequest, ResearchScriptInputFileCreateRequest, ResearchScriptRevisionCreateRequest,
    ResearchScriptRunCreateRequest, ResearchScriptSweepAxis, ResearchScriptSweepCreateRequest,
)
from src.services.research_script_store import ResearchScriptStore

from script_e5_fixtures import DATES, E5_SOURCE, ParameterFixtureRuntime, e5_service

DAYS = [f"2026-{1 + i // 28:02}-{1 + i % 28:02}" for i in range(84)]


def series(values):
    return list(zip(DAYS, values))


def regime_points():
    # Punto 0 bueno al principio y malo después; punto 1 al revés; punto 2 plano con algo de ruido.
    first = [0.004 + 0.001 * math.sin(i) if i < 42 else -0.003 + 0.001 * math.sin(i) for i in range(84)]
    second = [-0.003 + 0.001 * math.cos(i) if i < 42 else 0.004 + 0.001 * math.cos(i) for i in range(84)]
    flat = [0.0005 * math.sin(3 * i) for i in range(84)]
    return {0: series(first), 1: series(second), 2: series(flat)}


def test_anchored_and_rolling_folds_are_strictly_causal():
    anchored = run_walk_forward(regime_points(), WalkForwardConfig(train_observations=21, test_observations=21))
    assert [(f["train_start"], f["test_start"], f["test_end"]) for f in anchored["folds"]] == [
        (DAYS[0], DAYS[21], DAYS[41]), (DAYS[0], DAYS[42], DAYS[62]), (DAYS[0], DAYS[63], DAYS[83])]
    rolling = run_walk_forward(regime_points(), WalkForwardConfig(train_observations=21, test_observations=21, window="rolling"))
    assert [f["train_start"] for f in rolling["folds"]] == [DAYS[0], DAYS[21], DAYS[42]]
    for report in (anchored, rolling):
        assert report["causality"]["verified"] and all(f["train_end"] < f["test_start"] for f in report["folds"])
        oos_dates = [row["date"] for row in report["out_of_sample"]["rows"]]
        assert oos_dates == DAYS[21:] and len(set(oos_dates)) == len(oos_dates)


def test_selection_never_changes_when_future_observations_change():
    points = regime_points()
    config = WalkForwardConfig(train_observations=21, test_observations=7)
    baseline = run_walk_forward(points, config)
    for fold in baseline["folds"]:
        cut = DAYS.index(fold["test_start"])
        # Futuro radicalmente distinto: el punto 2 se vuelve espectacular desde el inicio de la prueba.
        future = {index: [(day, 0.05 if index == 2 and i >= cut else value) for i, (day, value) in enumerate(rows)]
                  for index, rows in points.items()}
        changed = run_walk_forward(future, config)
        same = changed["folds"][fold["fold"] - 1]
        assert (same["selected_point"], same["train_metrics"]) == (fold["selected_point"], fold["train_metrics"])


def test_regime_change_switches_selection_and_oos_uses_selected_point_only():
    report = run_walk_forward(regime_points(), WalkForwardConfig(train_observations=21, test_observations=7, window="rolling",
                                                                 selection_metric="total_return"))
    selected = [fold["selected_point"] for fold in report["folds"]]
    assert selected[0] == 0 and selected[-1] == 1
    points = regime_points()
    for fold in report["folds"]:
        start, end = DAYS.index(fold["test_start"]), DAYS.index(fold["test_end"])
        expected = [value for _, value in points[fold["selected_point"]][start:end + 1]]
        assert fold["test_return"] == pytest.approx(math.prod(1 + v for v in expected) - 1)
    assert "unstable" in " ".join(report["warnings"])
    assert report["trials"] == 3 and "not a validation result" in report["in_sample_reference"]["label"]
    assert report["out_of_sample"]["total_return"] == pytest.approx(
        math.prod(1 + row["value"] for row in report["out_of_sample"]["rows"]) - 1)


def test_ties_choose_lowest_point_and_partial_last_fold_is_labeled():
    same = series([0.001 * ((-1) ** i) + 0.0002 for i in range(84)])
    report = run_walk_forward({3: same, 1: same, 2: same}, WalkForwardConfig(train_observations=20, test_observations=30))
    assert {fold["selected_point"] for fold in report["folds"]} == {1}
    assert report["folds"][-1]["partial"] and report["folds"][-1]["test_observations"] == 4


@pytest.mark.parametrize("points,config,message", [
    ({0: series([0.01] * 84)}, WalkForwardConfig(20, 5), "at least two"),
    (regime_points(), WalkForwardConfig(84, 5), "train_observations \\+ 1"),
    (regime_points(), WalkForwardConfig(5, 5), "at least 10"),
    (regime_points(), WalkForwardConfig(20, 3), "at least 5"),
    ({0: series([0.0] * 84), 1: series([0.0] * 84)}, WalkForwardConfig(20, 5), "undefined"),
])
def test_walk_forward_refuses_unrepresentable_validation(points, config, message):
    with pytest.raises(WalkForwardError, match=message):
        run_walk_forward(points, config)


def test_alignment_uses_exact_common_dates_only():
    points = regime_points()
    points[1] = points[1][5:]
    report = run_walk_forward(points, WalkForwardConfig(train_observations=20, test_observations=10))
    assert report["common_window"]["start"] == DAYS[5]
    assert {a["point_index"]: a["excluded_observations"] for a in report["alignment"]} == {0: 5, 1: 0, 2: 5}
    assert selection_value([0.01, 0.01], "sharpe") is None  # varianza cero: métrica indefinida, no infinita


# ---- Barridos sobre ejecuciones retenidas ----

def sweep_request(detail, snapshot_id, axes=None):
    return ResearchScriptSweepCreateRequest(
        revision_id=detail.script.canonical_revision_id, input_snapshot_id=snapshot_id,
        axes=axes or [ResearchScriptSweepAxis("lookback", [5, 10, 20]), ResearchScriptSweepAxis("leverage", [1, 2])])


def empty_bundle(service, detail):
    return service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest()).snapshot_id


def test_sweep_definition_is_immutable_ordered_and_hash_bound(tmp_path):
    service, detail = e5_service(tmp_path)
    sweep = script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, empty_bundle(service, detail)))
    assert [(p.index, p.parameters) for p in sweep.points][:3] == [
        (0, {"leverage": 1, "lookback": 5}), (1, {"leverage": 2, "lookback": 5}), (2, {"leverage": 1, "lookback": 10})]
    assert len({p.parameters_sha256 for p in sweep.points}) == 6
    restarted = ResearchScriptService(ResearchScriptStore(base_dir=tmp_path / "scripts"), ParameterFixtureRuntime())
    assert script_experiments.get_sweep(restarted, sweep.sweep_id) == sweep
    assert script_experiments.list_sweeps(service, detail.script.script_id) == [sweep]
    path = tmp_path / "scripts" / "sweeps" / detail.script.script_id / f"{sweep.sweep_id}.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["points"][0]["parameters"]["lookback"] = 7
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ResearchScriptServiceError):
        script_experiments.get_sweep(restarted, sweep.sweep_id)


@pytest.mark.parametrize("axes,message", [
    ([ResearchScriptSweepAxis("lookback", list(range(5, 18))), ResearchScriptSweepAxis("leverage", [1, 2])], "between 2 and 12"),
    ([ResearchScriptSweepAxis("a", list(range(5))), ResearchScriptSweepAxis("b", list(range(6)))], "limit is 24"),
    ([ResearchScriptSweepAxis("lookback", [5])], "between 2 and 12"),
    ([ResearchScriptSweepAxis("lookback", [1, 1.0])], "distinct"),
    ([ResearchScriptSweepAxis("lookback", [5, {"a": 1}])], "nested"),
    ([ResearchScriptSweepAxis("lookback", [5, 10]), ResearchScriptSweepAxis("lookback", [1, 2])], "unique"),
    ([ResearchScriptSweepAxis("password", [1, 2])], "credential"),
])
def test_sweep_limits_and_invalid_axes_are_refused(tmp_path, axes, message):
    service, detail = e5_service(tmp_path)
    with pytest.raises(ResearchScriptValidationError, match=message):
        script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, empty_bundle(service, detail), axes))


def test_sweep_refuses_base_overlap_foreign_inputs_reserved_name_and_archived_script(tmp_path):
    service, detail = e5_service(tmp_path)
    other_detail = service.create_script(ResearchScriptCreateRequest(session_id="e5", title="Other", source=E5_SOURCE))
    snapshot = empty_bundle(service, detail)
    request = sweep_request(detail, snapshot)
    with pytest.raises(ResearchScriptValidationError, match="base parameters"):
        script_experiments.create_sweep(service, detail.script.script_id,
            ResearchScriptSweepCreateRequest(**{**request.__dict__, "base_parameters": {"lookback": 3}}))
    reserved = service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest(input_files=[
        ResearchScriptInputFileCreateRequest(logical_filename="gamma_parameters.json", media_type="application/json", content=b"{}")]))
    with pytest.raises(ResearchScriptValidationError, match="reserved"):
        script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, reserved.snapshot_id))
    with pytest.raises(ResearchScriptValidationError, match="does not belong"):
        script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, empty_bundle(service, other_detail)))
    service.archive_script(detail.script.script_id)
    with pytest.raises(ResearchScriptConflictError):
        script_experiments.create_sweep(service, detail.script.script_id, request)


def test_points_run_the_swept_revision_even_after_later_edits(tmp_path):
    service, detail = e5_service(tmp_path)
    sweep = script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, empty_bundle(service, detail)))
    revision = service.get_script(detail.script.script_id).revisions[0]
    service.create_revision(detail.script.script_id, ResearchScriptRevisionCreateRequest(
        source=E5_SOURCE + "# later edit\n", expected_parent_sha256=revision.source_sha256))
    run = script_experiments.run_sweep_point(service, sweep.sweep_id, 4)
    assert (run.revision_id, run.input_snapshot_id, run.sweep_id, run.sweep_point_index) == (
        sweep.revision_id, sweep.input_snapshot_id, sweep.sweep_id, 4)
    assert run.parameters_sha256 == sweep.points[4].parameters_sha256
    with pytest.raises(ResearchScriptNotFoundError):
        script_experiments.run_sweep_point(service, sweep.sweep_id, 6)


def test_sweep_snapshot_is_kept_by_input_retention(tmp_path):
    service, detail = e5_service(tmp_path)
    service.store = ResearchScriptStore(base_dir=tmp_path / "scripts", input_snapshot_retention=1)
    snapshot = empty_bundle(service, detail)
    sweep = script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, snapshot))
    for index in range(3):
        service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest(input_files=[
            ResearchScriptInputFileCreateRequest(logical_filename=f"x{index}.txt", media_type="text/plain", content=b"x")]))
    assert service.get_input_snapshot(sweep.input_snapshot_id).snapshot_id == snapshot


def run_all(service, sweep):
    return [script_experiments.run_sweep_point(service, sweep.sweep_id, point.index) for point in sweep.points]


def test_evaluation_is_descriptive_unranked_and_counts_every_trial(tmp_path):
    service, detail = e5_service(tmp_path)
    sweep = script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, empty_bundle(service, detail)))
    target = EvaluationTarget("returns_result", "strategy")
    before = script_experiments.evaluate_sweep(service, sweep.sweep_id, target)
    assert [p["state"] for p in before["points"]] == ["not_run"] * 6 and before["common_window"] is None
    service.runtime.failing_points = {sweep.points[5].parameters_sha256}
    run_all(service, sweep)
    report = script_experiments.evaluate_sweep(service, sweep.sweep_id, target)
    assert [p["index"] for p in report["points"]] == list(range(6))  # orden del barrido, sin ranking
    assert report["points"][5]["state"] == "run_failed" and report["ready_points"] == 5 and report["trials"] == 6
    assert "6 trials" in report["in_sample_label"] and "not ranked" in report["in_sample_label"]
    assert report["evaluation"]["timing"]["enforced_by_gamma"] is False
    first = report["points"][0]
    assert first["metrics"] == describe([(r["date"], r["value"]) for r in json.loads(
        service.get_output_artifact(first["run_id"], "analytics")[2])["results"][0]["observations"]])
    book = script_experiments.evaluate_sweep(service, sweep.sweep_id, EvaluationTarget("weight_book", book_options=BookOptions(1, 5)))
    assert book["evaluation"]["timing"] == {"enforced_by_gamma": True, "execution_lag": 1,
                                            "note": "Gamma applies each dated weight decision only from a later return period."}
    assert book["points"][0]["state"] == "ready" and book["points"][0]["coverage"]["start"] == DATES[1]


def test_walk_forward_requires_every_point_and_is_reproducible(tmp_path):
    service, detail = e5_service(tmp_path)
    sweep = script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, empty_bundle(service, detail)))
    config = WalkForwardConfig(train_observations=40, test_observations=20, window="rolling")
    target = EvaluationTarget("weight_book", book_options=BookOptions(execution_lag=1, cost_bps=2))
    with pytest.raises(ResearchScriptValidationError, match="silently shrink"):
        script_experiments.walk_forward_sweep(service, sweep.sweep_id, target, config)
    run_all(service, sweep)
    report = script_experiments.walk_forward_sweep(service, sweep.sweep_id, target, config)
    assert report["causality"]["verified"] and report["trials"] == 6
    assert all(fold["selected_parameters"] == sweep.points[fold["selected_point"]].parameters for fold in report["folds"])
    assert report["in_sample_reference"]["parameters"] == sweep.points[report["in_sample_reference"]["point_index"]].parameters
    assert report["evaluation"]["timing"]["enforced_by_gamma"] is True
    restarted = ResearchScriptService(ResearchScriptStore(base_dir=tmp_path / "scripts"), ParameterFixtureRuntime(),
                                      research_service=service.research_service)
    assert script_experiments.walk_forward_sweep(restarted, sweep.sweep_id, target, config)["report_sha256"] == report["report_sha256"]
    assert service.research_service.list_saved_research() == []  # nada se guarda


def test_safe_preview_points_cannot_be_validated(tmp_path):
    service, detail = e5_service(tmp_path, ParameterFixtureRuntime(executed=False))
    sweep = script_experiments.create_sweep(service, detail.script.script_id, sweep_request(detail, empty_bundle(service, detail)))
    run_all(service, sweep)
    report = script_experiments.evaluate_sweep(service, sweep.sweep_id, EvaluationTarget("returns_result", "strategy"))
    assert {p["state"] for p in report["points"]} == {"ineligible"}
    with pytest.raises(ResearchScriptValidationError, match="ineligible"):
        script_experiments.walk_forward_sweep(service, sweep.sweep_id, EvaluationTarget("returns_result", "strategy"),
                                              WalkForwardConfig(40, 20))


def test_sweep_api_round_trip(tmp_path):
    service, detail = e5_service(tmp_path)
    app = FastAPI(); app.include_router(router)
    app.state.runtime = SimpleNamespace(research_script_service=service, research_service=service.research_service)
    client = TestClient(app)
    created = client.post(f"/research/strategy-lab/scripts/{detail.script.script_id}/sweeps", json={
        "revision_id": detail.script.canonical_revision_id, "input_snapshot_id": empty_bundle(service, detail),
        "axes": [{"name": "lookback", "values": [5, 20]}], "base_parameters": {"leverage": 1}})
    assert created.status_code == 201, created.text
    sweep_id = created.json()["sweep_id"]
    for index in range(2):
        assert client.post(f"/research/strategy-lab/script-sweeps/{sweep_id}/points/{index}/run").status_code == 200
    evaluation = client.post(f"/research/strategy-lab/script-sweeps/{sweep_id}/evaluate", json={"target": "returns_result", "result_id": "strategy"})
    assert evaluation.status_code == 200 and evaluation.json()["ready_points"] == 2
    body = {"evaluation": {"target": "weight_book", "execution_lag": 2}, "train_observations": 40, "test_observations": 30}
    walk = client.post(f"/research/strategy-lab/script-sweeps/{sweep_id}/walk-forward", json=body)
    assert walk.status_code == 200, walk.text
    assert walk.json()["evaluation"]["execution_lag"] == 2 and walk.json()["contract_version"] == "gamma-script-walk-forward.v1"
    assert client.post(f"/research/strategy-lab/script-sweeps/{sweep_id}/walk-forward", json={**body, "train_observations": 5}).status_code == 422
    assert client.post(f"/research/strategy-lab/script-sweeps/{sweep_id}/evaluate", json={"target": "returns_result"}).status_code == 422
    assert client.get(f"/research/strategy-lab/script-sweeps/missing").status_code == 404
    assert client.get(f"/research/strategy-lab/scripts/{detail.script.script_id}/sweeps").json()[0]["sweep_id"] == sweep_id
