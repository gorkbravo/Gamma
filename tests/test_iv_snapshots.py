from types import SimpleNamespace
import json

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.services.iv_snapshot_store import IVSnapshotStore


def surface(symbol="SPY"):
    return {"symbol": symbol, "timestamp": "2026-10-06T14:00:00Z",
            "retrieved_at": "2026-10-06T14:01:00Z", "snapshot_available": True,
            "spot": 100, "points": 3, "expiries": ["20261120"], "strikes": [95, 100, 105],
            "iv_grid": [[0.3, 0.25, 0.26]], "cell_sources": [["observed"] * 3],
            "source_provider": "mock", "freshness_label": "mocked", "delayed": True,
            "warnings": ["Sample data"], "pricing_assumptions": {"risk_free_rate": 0.04,
            "dividend_yield": 0.01, "notes": ["Frozen rate input"]}}


def client(directory):
    runtime = SimpleNamespace(iv_snapshot_store=IVSnapshotStore(directory))
    return TestClient(create_app(runtime=runtime))


def test_capture_survives_restart_and_keeps_exact_evidence(tmp_path):
    original = surface()
    response = client(tmp_path).post("/iv/snapshots", json=original)
    assert response.status_code == 200
    capture = response.json()
    restarted = client(tmp_path)
    assert restarted.get(f"/iv/snapshots/{capture['snapshot_id']}").json() == capture
    retained = capture["surface"]
    for key in ("iv_grid", "cell_sources", "timestamp", "warnings", "source_provider", "delayed"):
        assert retained[key] == original[key]
    assert retained["pricing_assumptions"]["risk_free_rate"] == 0.04
    assert restarted.get("/iv/snapshots?symbol=spy").json()["snapshots"][0]["snapshot_id"] == capture["snapshot_id"]
    assert restarted.get("/iv/snapshots?symbol=AAPL").json()["snapshots"] == []


def test_corrupt_record_is_reported_and_preserved_without_hiding_valid_capture(tmp_path):
    test_client = client(tmp_path)
    first = test_client.post("/iv/snapshots", json=surface()).json()
    second = test_client.post("/iv/snapshots", json=surface()).json()
    path = tmp_path / f"{first['snapshot_id']}.json"
    changed = json.loads(path.read_text())
    changed["surface"]["iv_grid"][0][0] = 9
    path.write_text(json.dumps(changed))
    (tmp_path / f"{'a' * 32}.json").write_text("[]")
    result = test_client.get("/iv/snapshots?symbol=SPY").json()
    assert len(result["snapshots"]) == 1
    assert result["snapshots"][0]["snapshot_id"] == second["snapshot_id"]
    assert result["warnings"] and path.exists()
    assert test_client.get(f"/iv/snapshots/{first['snapshot_id']}").status_code == 503
    assert test_client.get("/iv/snapshots/not-a-valid-id").status_code == 404


def test_unavailable_malformed_and_nonfinite_surfaces_are_rejected(tmp_path):
    test_client = client(tmp_path)
    for update in ({"snapshot_available": False}, {"points": 0}, {"spot": -1},
                   {"iv_grid": [[0.2]]}, {"strikes": [100, 95, 105]},
                   {"cell_sources": [["observed"]]}, {"symbol": "../SPY"}):
        assert test_client.post("/iv/snapshots", json={**surface(), **update}).status_code == 422
    payload = surface()
    payload["iv_grid"][0][0] = float("nan")
    assert test_client.post("/iv/snapshots", content=json.dumps(payload), headers={"Content-Type": "application/json"}).status_code == 422
    assert not list(tmp_path.glob("*.json"))


def test_snapshot_routes_require_session_authorization(tmp_path):
    unauthenticated = TestClient(create_app(runtime=SimpleNamespace(iv_snapshot_store=IVSnapshotStore(tmp_path))),
                                 headers={"X-Test-No-Gamma-Session": "1"})
    assert unauthenticated.post("/iv/snapshots", json=surface()).status_code == 401


def test_partial_surface_keeps_missing_cells(tmp_path):
    payload = surface()
    payload["iv_grid"][0][0] = None
    payload["cell_sources"][0][0] = "unavailable"
    result = client(tmp_path).post("/iv/snapshots", json=payload)
    assert result.status_code == 200
    assert result.json()["surface"]["iv_grid"][0][0] is None


def test_runtime_surface_capture_and_restart_use_configured_history_directory(tmp_path):
    from src.application.runtime import build_runtime

    arguments = {"mock_mode": True, "cache_dir": tmp_path / "cache", "history_dir": tmp_path / "data",
                 "sample_data_dir": "sample_data"}
    runtime = build_runtime(**arguments)
    try:
        test_client = TestClient(create_app(runtime))
        displayed = test_client.get("/iv/surface?symbol=SPY").json()
        response = test_client.post("/iv/snapshots", json=displayed)
        assert response.status_code == 200, response.text
        retained = response.json()
        assert retained["surface"] == displayed
    finally:
        runtime.shutdown()
    restarted = build_runtime(**arguments)
    try:
        result = TestClient(create_app(restarted)).get(f"/iv/snapshots/{retained['snapshot_id']}")
        assert result.json() == retained
        assert (tmp_path / "data" / "options_snapshots" / f"{retained['snapshot_id']}.json").exists()
    finally:
        restarted.shutdown()
