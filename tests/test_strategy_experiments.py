from copy import deepcopy
import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime


def points(factor=1):
    return [{"timestamp": (datetime(2025, 1, 1) + timedelta(days=i)).isoformat(),
             "value": factor * (0.002 + (i % 7 - 3) * 0.001)} for i in range(260)]


def request():
    benchmark = {"object_id": "SPY-retained", "object_type": "history", "display_name": "SPY",
                 "source_tab": "strategy_lab", "resolver_capabilities": ["benchmark"], "symbols": ["SPY"],
                 "return_points": points(0.6), "provenance": {"source_provider": "fixture"}}
    return {"name": "QQQ minus SPY", "legs": [
        {"label": "QQQ", "asset_class": "etf", "identifier": "QQQ", "weight": 1,
         "value_kind": "return", "return_points": points()},
        {"label": "SPY", "asset_class": "etf", "identifier": "SPY", "weight": -1,
         "value_kind": "return", "return_points": points(0.6)}],
         "benchmark_symbol": "SPY", "benchmark_object": benchmark, "lookback_days": 260, "min_observations": 60}


def runtime(directory):
    return build_runtime(mock_mode=True, history_dir=directory / "data", cache_dir=directory / "cache", sample_data_dir="sample_data")


def snapshot():
    return {"timestamp": "2026-10-06T12:00:00", "base_currency": "USD",
            "account_summary": {"source": "strategy_lab_research_book"},
            "positions": [{"symbol": "STRATEGY_BOOK", "sec_type": "BOOK", "currency": "USD", "quantity": 1,
                           "market_value": 100000, "weight": 1, "instrument_id": "saved-pair"}],
            "total_market_value": 100000, "net_liquidation": 100000}


def test_saved_experiment_exact_restart_risk_and_revised_weight_comparison(tmp_path, monkeypatch):
    first = runtime(tmp_path)
    try:
        client = TestClient(create_app(first))
        result = client.post("/research/strategy-lab/portfolio-compose", json=request())
        assert result.status_code == 200, result.text
        composed = result.json()
        assert [leg["weight"] for leg in composed["portfolio_inputs"]["legs"]] == [1, -1]
        assert [leg["weight"] for leg in composed["risk_legs"]] == [0.5, -0.5]
        saved = client.post("/research/saved", json={"object_type": "strategy_lab", "title": "Original pair",
                           "payload": {**composed, "experiment_contract": "gamma.strategy-lab-experiment.v1"}})
        assert saved.status_code == 200, saved.text
        saved_item = saved.json()
    finally:
        first.shutdown()
    restarted = runtime(tmp_path)
    try:
        client = TestClient(create_app(restarted))
        replay = client.get(f"/research/saved/{saved_item['id']}").json()
        assert replay == saved_item
        monkeypatch.setattr(restarted.risk_service, "_load_benchmark_returns",
                            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Benchmark must not reload")))
        risk = client.post("/risk/compute", json={"snapshot": snapshot(), "source_scope": "research_book",
                           "source_label": "Saved QQQ minus SPY", "source_object_id": "saved-pair",
                           "research_book_return_points": composed["returns_points"], "research_book_legs": composed["risk_legs"],
                           "research_book_benchmark_points": composed["benchmark_points"], "benchmark_symbol": "SPY",
                           "lookback_days": 260, "beta_window": 60, "include_monte_carlo": False})
        assert risk.status_code == 200, risk.text
        assert risk.json()["source_scope"] == "research_book"
        assert risk.json()["source_object_id"] == "saved-pair"
        assert risk.json()["metrics"]["benchmark_overlap_count"] == 260
        assert risk.json()["benchmark_return_points"] == composed["benchmark_points"]
        no_benchmark = json.loads(risk.request.content)
        no_benchmark["research_book_benchmark_points"] = []
        unavailable = client.post("/risk/compute", json=no_benchmark)
        assert unavailable.status_code == 200, unavailable.text
        assert unavailable.json()["metrics"]["benchmark_overlap_count"] is None
        assert unavailable.json()["benchmark_return_points"] == []
        # Regresión: un benchmark retenido vacío no se presenta como histórico utilizado.
        assert any("uses the retained Strategy Lab experiment history" in w for w in risk.json()["warnings"])
        assert any("retained no benchmark history" in w for w in unavailable.json()["warnings"])
        assert not any("uses the retained Strategy Lab experiment history" in w for w in unavailable.json()["warnings"])
        revised = deepcopy(request())
        revised["name"] = "Revised QQQ minus SPY"
        revised["legs"][0]["weight"] = 2
        changed = client.post("/research/strategy-lab/portfolio-compose", json=revised)
        assert changed.status_code == 200
        comparison = client.post("/research/compare-scenario/analyze", json={
            "left": {"label": "Baseline", "object_type": "strategy_composition", "return_points": composed["returns_points"]},
            "right": {"label": "Revised", "object_type": "strategy_composition", "return_points": changed.json()["returns_points"]}})
        assert comparison.status_code == 200, comparison.text
        assert comparison.json()["aligned_observation_count"] == 260
        assert comparison.json()["left"]["metrics"]["total_return"] != comparison.json()["right"]["metrics"]["total_return"]
        assert client.get(f"/research/saved/{saved_item['id']}").json() == saved_item
    finally:
        restarted.shutdown()


def test_experiment_rejects_weight_mismatch_or_missing_inputs(tmp_path):
    running = runtime(tmp_path)
    try:
        client = TestClient(create_app(running))
        composed = client.post("/research/strategy-lab/portfolio-compose", json=request()).json()
        payload = {**composed, "experiment_contract": "gamma.strategy-lab-experiment.v1"}
        payload["portfolio_inputs"]["legs"][0]["weight"] = 3
        assert client.post("/research/saved", json={"object_type": "strategy_lab", "title": "Bad", "payload": payload}).status_code == 422
        payload["portfolio_inputs"] = None
        assert client.post("/research/saved", json={"object_type": "strategy_lab", "title": "Bad", "payload": payload}).status_code == 422
    finally:
        running.shutdown()
