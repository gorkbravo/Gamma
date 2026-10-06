from copy import deepcopy
from datetime import datetime, timedelta
import json

from fastapi.testclient import TestClient
import pytest

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.services.commodity_curve_store import CommodityCurveStore


def runtime(directory):
    return build_runtime(mock_mode=True, history_dir=directory / "data", cache_dir=directory / "cache")


def capture_payload(client):
    workspace = client.post("/commodities/workspace", json={"mode": "curves_spreads", "selected_instrument_id": "wti"}).json()
    return {"instrument": next(i for i in workspace["instruments"] if i["instrument_id"] == "wti"),
            "curve": next(i for i in workspace["curves"] if i["instrument_id"] == "wti"), "coverage": workspace["coverage"]}


def save(client, payload):
    result = client.post("/commodities/curve-captures", json=payload)
    assert result.status_code == 200, result.text
    return result.json()


def test_exact_capture_restart_roll_gaps_and_calendar_spread(tmp_path, monkeypatch):
    first = runtime(tmp_path)
    try:
        client = TestClient(create_app(first))
        payload = capture_payload(client)
        original = save(client, payload)
        assert original["payload"] == payload
        ids = [n["contract"]["contract_id"] for n in payload["curve"]["nodes"]]
        spread = client.post("/commodities/calendar-spreads", json={"capture_id": original["id"],
                             "left_contract_id": ids[0], "right_contract_id": ids[1], "label": "Fixed WTI pair"})
        assert spread.status_code == 200, spread.text
        spread_id = spread.json()["id"]
    finally:
        first.shutdown()
    restarted = runtime(tmp_path)
    try:
        client = TestClient(create_app(restarted))
        monkeypatch.setattr(restarted.commodities_service.provider, "get_snapshot",
                            lambda **kwargs: (_ for _ in ()).throw(AssertionError("Replay must not query provider")))
        assert client.get(f"/commodities/curve-captures/{original['id']}").json() == original
        assert client.get("/commodities/calendar-spreads").json()["spreads"][0]["id"] == spread_id
        later = deepcopy(payload)
        later["curve"]["as_of"] = payload["curve"]["as_of"]
        later["curve"]["nodes"][0]["price"] += 2
        second = save(client, later)
        comparison = client.post("/commodities/curve-captures/compare", json={"baseline_id": original["id"], "comparison_id": second["id"]})
        assert comparison.status_code == 200
        assert comparison.json()["rows"][0]["change"] == 2
        assert comparison.json()["rows"][0]["contract_id"] == ids[0]
        rolled = deepcopy(later)
        rolled["curve"]["nodes"].pop(0)
        rolled["curve"]["nodes"][0]["contract"]["is_front_month"] = True
        third = save(client, rolled)
        gap = client.post("/commodities/curve-captures/compare", json={"baseline_id": original["id"], "comparison_id": third["id"]}).json()["rows"][0]
        assert gap["status"] == "absent_from_comparison" and gap["change"] is None
        history = client.get(f"/commodities/calendar-spreads/{spread_id}/history").json()
        assert history["points"][1]["value"] == history["points"][0]["value"] + 2
        assert history["points"][2]["value"] is None
        assert history["points"][2]["status"] == "contract_not_in_capture"
        assert client.get(f"/commodities/curve-captures/{original['id']}").json() == original
    finally:
        restarted.shutdown()


def test_capture_validation_corruption_and_incompatible_comparison(tmp_path):
    running = runtime(tmp_path)
    try:
        client = TestClient(create_app(running))
        payload = capture_payload(client)
        a = save(client, payload)
        bad = deepcopy(payload)
        bad["curve"]["nodes"][1]["contract"]["contract_id"] = bad["curve"]["nodes"][0]["contract"]["contract_id"]
        assert client.post("/commodities/curve-captures", json=bad).status_code == 422
        bad = deepcopy(payload)
        for node in bad["curve"]["nodes"]: node["price"] = None
        assert client.post("/commodities/curve-captures", json=bad).status_code == 422
        different = deepcopy(payload)
        different["instrument"]["quote_unit"] = "cents/barrel"
        b = save(client, different)
        assert client.post("/commodities/curve-captures/compare", json={"baseline_id": a["id"], "comparison_id": b["id"]}).status_code == 422
        store = running.commodities_service.curve_store
        path = store.base_dir / "captures" / f"{a['id']}.json"
        damaged = json.loads(path.read_text())
        damaged["payload"]["curve"]["nodes"][0]["price"] += 1
        path.write_text(json.dumps(damaged))
        listing = client.get("/commodities/curve-captures").json()
        assert listing["warnings"] and len(listing["captures"]) == 1
        assert path.exists()
        assert client.get(f"/commodities/curve-captures/{a['id']}").status_code == 422
        assert client.get("/commodities/curve-captures/not-a-record").status_code == 404
    finally:
        running.shutdown()


def test_identity_conflict_and_missing_quote_never_produce_spread_value(tmp_path):
    running = runtime(tmp_path)
    try:
        client = TestClient(create_app(running))
        payload = capture_payload(client)
        a = save(client, payload)
        ids = [n["contract"]["contract_id"] for n in payload["curve"]["nodes"]]
        spread = client.post("/commodities/calendar-spreads", json={"capture_id": a["id"], "left_contract_id": ids[0], "right_contract_id": ids[1]}).json()
        conflict = deepcopy(payload)
        conflict["curve"]["nodes"][0]["contract"]["contract_month"] = "2099-01"
        b = save(client, conflict)
        missing = deepcopy(payload)
        missing["curve"]["nodes"][0]["price"] = None
        save(client, missing)
        expired = deepcopy(payload)
        expired["curve"]["as_of"] = "2099-01-01T00:00:00"
        save(client, expired)
        history = client.get(f"/commodities/calendar-spreads/{spread['id']}/history").json()
        assert [p["status"] for p in history["points"]] == ["observed", "identity_conflict", "quote_unavailable", "expired_contract"]
        assert [p["value"] for p in history["points"]][1:] == [None, None, None]
        result = client.post("/commodities/curve-captures/compare", json={"baseline_id": a["id"], "comparison_id": b["id"]}).json()
        assert result["rows"][0]["status"] == "identity_conflict" and result["rows"][0]["change"] is None
        assert client.post("/commodities/calendar-spreads", json={"capture_id": a["id"], "left_contract_id": "unknown", "right_contract_id": ids[1]}).status_code == 422
    finally:
        running.shutdown()


def test_failed_atomic_write_preserves_existing_record(tmp_path, monkeypatch):
    store = CommodityCurveStore(tmp_path)
    contract = {"contract_id": "CL1", "instrument_id": "wti", "symbol": "CL1", "contract_month": "2026-12"}
    definition = {"instrument_id": "wti", "label": "Pair", "unit": "USD/barrel", "currency": "USD", "left_contract": contract,
                  "right_contract": {**contract, "contract_id": "CL2", "symbol": "CL2"}, "source_capture_id": "a" * 32, "formula": "left_price - right_price"}
    original = store._write("spreads", definition)
    monkeypatch.setattr("src.services.commodity_curve_store.os.replace", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError): store._write("spreads", definition)
    assert store.load("spreads", original["id"]) == original
    assert list((tmp_path / "spreads").glob("*.tmp")) == []


def test_overview_exposes_earlier_retained_curves_without_mixing_units(tmp_path):
    running = runtime(tmp_path)
    try:
        client = TestClient(create_app(running))
        payload = capture_payload(client)
        earlier = deepcopy(payload)
        earlier["curve"]["as_of"] = (datetime.fromisoformat(payload["curve"]["as_of"].replace("Z", "+00:00")) - timedelta(days=1)).isoformat()
        original = save(client, earlier)
        incompatible = deepcopy(earlier)
        incompatible["instrument"]["quote_unit"] = "cents/barrel"
        save(client, incompatible)
        workspace = client.post("/commodities/workspace", json={"selected_instrument_id": "wti"}).json()
        structure = workspace["overview"]["term_structure"]
        assert len(structure["previous_curve_snapshots"]) == 1
        assert structure["previous_curve_snapshots"][0]["nodes"] == original["payload"]["curve"]["nodes"]
        assert any("different quote units" in warning for warning in structure["caveats"])
    finally:
        running.shutdown()
