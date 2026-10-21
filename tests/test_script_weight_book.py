"""Cierre del traspaso de pesos de E4: libro causal calculado por Gamma (sin ejecutar Python)."""
from copy import deepcopy
import json
import math
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.analytics.script_weight_book import BookOptions, WeightBookError, compute_weight_book
from src.api.routes.research import router
from src.application.research_script_service import ResearchScriptValidationError
from src.application.script_analytics import inspect_analytics, open_analytics
from src.models.research_lab import ImportedReturnStreamRequest
from src.models.research_script import ResearchScriptRunCreateRequest
from script_e5_fixtures import ASSET, DATES, ParameterFixtureRuntime, e5_service, strategy_payload
from test_script_analytics import service_run

D = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
R = [0.01, -0.02, 0.005, 0.03, -0.01, 0.02, 0.004]


def book(weights, returns=None, **options):
    returns = returns or {"a": list(zip(D, R))}
    return compute_weight_book(weights, returns, BookOptions(**options))


def reference_book(decisions, returns, calendar, lag=1, cost_bps=0.0):
    """Implementación independiente en unidades monetarias (posiciones y caja), no en pesos."""
    effective = {}
    for decided, target in decisions:
        k = next(k for k in range(1, len(calendar)) if calendar[k - 1] >= decided) + lag - 1
        if k < len(calendar):
            effective[k] = target
    nav, holdings, rows = 1.0, {}, []
    for k in range(min(effective), len(calendar)):
        start_nav = nav
        if k in effective:
            turnover = sum(abs(effective[k].get(i, 0.0) - holdings.get(i, 0.0) / nav) for i in set(effective[k]) | set(holdings))
            nav -= nav * cost_bps / 10_000 * turnover
            holdings = {i: w * nav for i, w in effective[k].items()}
        cash = nav - sum(holdings.values())
        holdings = {i: value * (1 + returns[i][calendar[k]]) for i, value in holdings.items()}
        nav = cash + sum(holdings.values())
        rows.append((calendar[k], nav / start_nav - 1))
    return rows


def test_decision_never_earns_its_own_date_return():
    result = book({"a": [(D[2], 1.0)]})
    assert result.rows[0] == {"date": D[3], "value": pytest.approx(R[3])}
    perturbed = book({"a": [(D[2], 1.0)]}, {"a": list(zip(D, [*R[:2], 0.5, *R[3:]]))})
    assert perturbed.rows == result.rows  # el rendimiento del día de la decisión no entra


def test_weekend_decision_waits_for_a_period_starting_after_it():
    result = book({"a": [("2026-10-03", 1.0)]})  # sábado entre D[1] (vie) y D[2] (lun)
    assert result.rows[0]["date"] == D[3] and result.rebalances[0]["effective_period_start"] == D[2]


def test_execution_lag_shifts_and_lag_zero_is_refused():
    assert book({"a": [(D[1], 1.0)]}, execution_lag=2).rows[0]["date"] == D[3]
    with pytest.raises(WeightBookError, match="lag 0"):
        book({"a": [(D[1], 1.0)]}, execution_lag=0)


def test_signed_leverage_and_cash_residual_are_exact():
    assert book({"a": [(D[0], -2.0)]}).rows[0]["value"] == pytest.approx(-2.0 * R[1])
    half = book({"a": [(D[0], 0.5)]})
    assert half.rows[0]["value"] == pytest.approx(0.5 * R[1])
    drifted = 0.5 * (1 + R[1]) / (1 + 0.5 * R[1])  # la caja no rinde: el peso deriva
    assert half.rows[1]["value"] == pytest.approx(drifted * R[2])
    assert half.rebalances[0]["cash_weight"] == pytest.approx(0.5)


def test_costs_are_charged_on_turnover_multiplicatively():
    result = book({"a": [(D[0], 1.0), (D[2], -1.0)]}, cost_bps=10)
    assert result.rows[0]["value"] == pytest.approx((1 - 0.001) * (1 + R[1]) - 1)
    assert result.rebalances[1]["turnover"] == pytest.approx(2.0)  # de +1 derivado a -1
    assert result.total_cost_fraction == pytest.approx(0.001 + 0.002)


def test_multi_instrument_book_matches_independent_currency_reference():
    rb = [0.002, 0.01, -0.004, 0.006, -0.012, 0.003, 0.009]
    returns = {"a": list(zip(D, R)), "b": list(zip(D, rb))}
    schedule = [(D[0], {"a": 0.6, "b": -0.3}), ("2026-10-04", {"a": -0.4, "b": 1.2}), (D[4], {"a": 0.0, "b": 0.5})]
    weights = {name: [(day, target[name]) for day, target in schedule] for name in ("a", "b")}
    result = book(weights, returns, cost_bps=7.5)
    reference = reference_book(schedule, {name: dict(rows) for name, rows in returns.items()}, D, cost_bps=7.5)
    assert [row["date"] for row in result.rows] == [day for day, _ in reference]
    assert [row["value"] for row in result.rows] == pytest.approx([value for _, value in reference], abs=1e-14)


@pytest.mark.parametrize("weights,returns,message", [
    ({"a": [(D[0], 1.0)], "b": [(D[1], 1.0)]}, {"a": list(zip(D, R)), "b": list(zip(D, R))}, "identical decision dates"),
    ({"a": [(D[0], 1.0)], "b": [(D[0], 1.0)]}, {"a": list(zip(D, R))}, "does not acquire histories"),
    ({"a": [(D[0], 1.0)], "b": [(D[0], 1.0)]}, {"a": list(zip(D, R)), "b": list(zip(D[:3] + D[4:], R[:3] + R[4:]))}, "does not fill"),
    ({"a": [(D[0], None)]}, None, "null targets"),
    ({"a": [(D[0], 1.0)]}, {"a": list(zip(D, [0.01, None, *R[2:]]))}, "null observations"),
    ({"a": [(D[0], 200.0)]}, {"a": list(zip(D, [0.01, -0.02, *R[2:]]))}, "non-positive"),
    ({"a": [("2026-11-01", 1.0)]}, None, "No decision takes effect"),
])
def test_unfaithful_books_fail_with_reasons(weights, returns, message):
    with pytest.raises(WeightBookError, match=message):
        book(weights, returns)


def test_alignment_trims_outside_common_span_and_reports_it():
    longer = [("2026-09-30", 0.07), *zip(D, R)]
    result = book({"a": [(D[0], 1.0)], "b": [(D[0], 0.0)]}, {"a": longer, "b": list(zip(D, R))})
    assert result.trimmed_observations == {"a": 1, "b": 0}
    assert any("excluded" in warning for warning in result.warnings)


# ---- Traspaso a Strategy Lab desde una ejecución retenida ----

def test_weight_book_opens_existing_strategy_lab_analytics_with_exact_rows(tmp_path):
    service, detail = e5_service(tmp_path)
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 5, "leverage": 1.5}))
    artifact = inspect_analytics(service, run.run_id)["artifacts"][0]
    entry = artifact["weight_book"]
    assert entry["can_open"], entry["unsupported_reason"]
    payload = strategy_payload(5, 1.5)
    decisions = [(o["date"], o["value"]) for o in payload["results"][2]["observations"]]
    expected = book({"research:asset": decisions}, {"research:asset": list(zip(DATES, ASSET))})
    assert entry["mapping"]["rows"] == expected.rows
    analysis, evidence = open_analytics(service, run.run_id, "analytics", "weight_book", entry["preview_sha256"], target="weight_book")
    owner = service.research_service.analyze_strategy_lab(ImportedReturnStreamRequest(rows=expected.rows, date_column="date", value_column="value"))
    assert analysis.metrics == owner.metrics and analysis.returns.equals(owner.returns)
    assert analysis.metrics.total_return == pytest.approx(math.prod(1 + row["value"] for row in expected.rows) - 1, abs=1e-12)
    assert evidence["target"] == "weight_book" and evidence["book_options"] == {"execution_lag": 1, "cost_bps": 0.0}
    assert evidence["parameters"] == {"leverage": 1.5, "lookback": 5}
    assert service.research_service.list_saved_research() == []  # abrir no guarda


def test_book_options_are_bound_by_the_preview_hash(tmp_path):
    service, detail = e5_service(tmp_path)
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 10, "leverage": 1.0}))
    default = inspect_analytics(service, run.run_id)["artifacts"][0]["weight_book"]
    costly = inspect_analytics(service, run.run_id, BookOptions(execution_lag=2, cost_bps=25))["artifacts"][0]["weight_book"]
    assert default["preview_sha256"] != costly["preview_sha256"]
    assert costly["mapping"]["rows"][0]["date"] > default["mapping"]["rows"][0]["date"]
    with pytest.raises(ResearchScriptValidationError):
        open_analytics(service, run.run_id, "analytics", "weight_book", costly["preview_sha256"], target="weight_book")
    open_analytics(service, run.run_id, "analytics", "weight_book", costly["preview_sha256"], target="weight_book",
                   book_options=BookOptions(execution_lag=2, cost_bps=25))


def test_weight_only_and_safe_preview_books_stay_standalone(tmp_path):
    data = strategy_payload(10, 1.0)
    data["results"] = [r for r in data["results"] if r["result_id"] != "asset_returns"]
    service, run = service_run(tmp_path, json.dumps(data).encode())
    entry = inspect_analytics(service, run.run_id)["artifacts"][0]["weight_book"]
    assert not entry["can_open"] and "does not acquire histories" in entry["unsupported_reason"]
    preview_service, detail = e5_service(tmp_path / "preview", ParameterFixtureRuntime(executed=False))
    preview_run = preview_service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
    entry = inspect_analytics(preview_service, preview_run.run_id)["artifacts"][0]["weight_book"]
    assert entry["unsupported_reason"] is None and not entry["can_open"]


def test_api_open_and_save_weight_book_revalidate_options(tmp_path):
    service, detail = e5_service(tmp_path)
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 20, "leverage": 1.0}))
    app = FastAPI(); app.include_router(router)
    app.state.runtime = SimpleNamespace(research_script_service=service, research_service=service.research_service)
    client = TestClient(app)
    path = f"/research/strategy-lab/script-runs/{run.run_id}/analytics"
    entry = client.get(path, params={"execution_lag": 1, "cost_bps": 5}).json()["artifacts"][0]["weight_book"]
    body = dict(output_id="analytics", result_id="weight_book", preview_sha256=entry["preview_sha256"], target="weight_book", cost_bps=5)
    opened = client.post(path + "/open", json=body)
    assert opened.status_code == 200, opened.text
    assert client.post(path + "/open", json={**body, "cost_bps": 0}).status_code == 422
    assert client.get(path, params={"execution_lag": 0}).status_code == 422
    save = dict(object_type="strategy_lab", title="Causal book", payload=opened.json(), source_provider="gamma_script_analytics")
    assert client.post("/research/saved", json=save).status_code == 200
    tampered = deepcopy(save)
    tampered["payload"]["analytical_provenance"]["book_options"]["cost_bps"] = 0
    assert client.post("/research/saved", json=tampered).status_code == 422
