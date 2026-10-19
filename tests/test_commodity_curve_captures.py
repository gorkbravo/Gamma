from copy import deepcopy
from datetime import datetime, timedelta
import json

from fastapi.testclient import TestClient
import pytest

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.services.commodity_curve_store import CommodityCurveStore, CommodityRetentionLimitError


def runtime(directory):
    return build_runtime(mock_mode=True, history_dir=directory / "data", cache_dir=directory / "cache")


def capture_payload(client):
    workspace = client.post("/commodities/workspace", json={"mode": "curves_spreads", "selected_instrument_id": "wti"}).json()
    return {"instrument": next(i for i in workspace["instruments"] if i["instrument_id"] == "wti"),
            "curve": next(i for i in workspace["curves"] if i["instrument_id"] == "wti"), "coverage": workspace["coverage"]}


def observed_later(payload, minutes):
    # Cada observación sucesiva tiene su propio as_of; el mismo as_of es la misma observación.
    shifted = deepcopy(payload)
    shifted["curve"]["as_of"] = (datetime.fromisoformat(payload["curve"]["as_of"].replace("Z", "+00:00")) + timedelta(minutes=minutes)).isoformat()
    return shifted


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
        later = observed_later(payload, 1)
        later["curve"]["nodes"][0]["price"] += 2
        second = save(client, later)
        comparison = client.post("/commodities/curve-captures/compare", json={"baseline_id": original["id"], "comparison_id": second["id"]})
        assert comparison.status_code == 200
        assert comparison.json()["rows"][0]["change"] == 2
        assert comparison.json()["rows"][0]["contract_id"] == ids[0]
        rolled = observed_later(later, 1)
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
        conflict = observed_later(payload, 1)
        conflict["curve"]["nodes"][0]["contract"]["contract_month"] = "2099-01"
        b = save(client, conflict)
        missing = observed_later(payload, 2)
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


# --- Revisión 2026-10-15: procedencia y almacenamiento a largo plazo de las curvas retenidas ---

def node(contract_id, price, **evidence):
    contract = {"contract_id": contract_id, "instrument_id": "wti", "symbol": contract_id, "contract_month": "2026-12"}
    return {"contract": contract, "price": price, "source_provider": evidence.pop("source_provider", "ibkr"),
            "quote_field": "last", "delayed": False, "freshness_label": "live", **evidence}


def minimal_capture(as_of, nodes, *, coverage_status="live"):
    return {"instrument": {"instrument_id": "wti", "quote_unit": "USD/bbl", "currency": "USD"},
            "curve": {"instrument_id": "wti", "as_of": as_of, "nodes": nodes, "source_provider": nodes[0]["source_provider"]},
            "coverage": {"coverage_status": coverage_status}}


def spread_for(store, capture):
    return store.save_spread(capture["id"], "CLZ6", "CLF7", "Dec/Jan")


def test_spread_history_downgrades_legs_with_different_quote_evidence(tmp_path):
    store = CommodityCurveStore(tmp_path)
    same = store.save_capture(minimal_capture("2026-10-01T15:00:00+00:00", [node("CLZ6", 70.0), node("CLF7", 69.5)]))
    mixed = store.save_capture(minimal_capture("2026-10-02T15:00:00+00:00", [
        node("CLZ6", 71.0), node("CLF7", 70.0, delayed=True, freshness_label="delayed", quote_field="close")]))
    history = store.spread_history(spread_for(store, same)["id"])
    first, second = history["points"]
    assert (first["status"], first["evidence_mismatch"]) == ("observed", [])
    assert second["capture_id"] == mixed["id"]
    assert second["status"] == "mixed_quote_evidence"
    assert second["value"] == 1.0
    assert second["evidence_mismatch"] == ["quote_field", "delayed", "freshness_label"]
    assert any("mixed quote evidence" in warning for warning in history["warnings"])


def test_spread_history_orders_by_observation_time_and_counts_one_point_per_as_of(tmp_path):
    store = CommodityCurveStore(tmp_path)
    # Se guarda primero la observación posterior: el orden de guardado no es el de observación.
    late = store.save_capture(minimal_capture("2026-10-03T15:00:00+00:00", [node("CLZ6", 72.0), node("CLF7", 71.0)]))
    early = store.save_capture(minimal_capture("2026-10-01T15:00:00+00:00", [node("CLZ6", 70.0), node("CLF7", 69.0)]))
    resaved = store.save_capture(minimal_capture("2026-10-03T15:00:00+00:00", [node("CLZ6", 72.5), node("CLF7", 71.0)]))
    history = store.spread_history(spread_for(store, early)["id"])
    assert [point["as_of"] for point in history["points"]] == ["2026-10-01T15:00:00+00:00", "2026-10-03T15:00:00+00:00"]
    duplicate_point = history["points"][1]
    assert duplicate_point["capture_id"] == resaved["id"] and duplicate_point["value"] == 1.5
    assert duplicate_point["superseded_capture_ids"] == [late["id"]]
    assert any("share observation time" in warning for warning in history["warnings"])
    # La lista también se ordena por observación, la más reciente primero.
    assert [row["id"] for row in store.records("captures", "wti")[0]] == [resaved["id"], late["id"], early["id"]]


def test_saving_the_same_observation_twice_is_idempotent(tmp_path):
    store = CommodityCurveStore(tmp_path)
    payload = minimal_capture("2026-10-01T15:00:00+00:00", [node("CLZ6", 70.0), node("CLF7", 69.0)])
    first, again = store.save_capture(payload), store.save_capture(deepcopy(payload))
    assert again["id"] == first["id"]
    assert len(list((tmp_path / "captures").glob("*.json"))) == 1
    assert spread_for(store, first)["id"] == spread_for(store, first)["id"]


def test_mock_and_live_captures_never_mix(tmp_path):
    live, mock = CommodityCurveStore(tmp_path, mode="live"), CommodityCurveStore(tmp_path, mode="mock")
    live_capture = live.save_capture(minimal_capture("2026-10-01T15:00:00+00:00", [node("CLZ6", 70.0), node("CLF7", 69.0)]))
    mock_capture = mock.save_capture(minimal_capture("2026-10-02T15:00:00+00:00", [
        node("CLZ6", 10.0, source_provider="sample_data"), node("CLF7", 9.0, source_provider="sample_data")], coverage_status="sample"))
    assert (live_capture["mode"], mock_capture["mode"]) == ("live", "mock")
    assert [row["id"] for row in live.records("captures")[0]] == [live_capture["id"]]
    assert [row["id"] for row in mock.records("captures")[0]] == [mock_capture["id"]]
    with pytest.raises(FileNotFoundError):
        live.load("captures", mock_capture["id"])
    assert [p["capture_id"] for p in live.spread_history(spread_for(live, live_capture)["id"])["points"]] == [live_capture["id"]]
    with pytest.raises(FileNotFoundError):
        live.delete("captures", mock_capture["id"])


def test_legacy_records_without_mode_are_classified_by_their_evidence(tmp_path):
    sample = CommodityCurveStore(tmp_path, mode="mock").save_capture(minimal_capture("2026-10-01T15:00:00+00:00", [
        node("CLZ6", 10.0, source_provider="sample_data"), node("CLF7", 9.0, source_provider="sample_data")], coverage_status="sample"))
    live = CommodityCurveStore(tmp_path, mode="live").save_capture(
        minimal_capture("2026-10-02T15:00:00+00:00", [node("CLZ6", 70.0), node("CLF7", 69.0)]))
    for record in (sample, live):
        # Simula un registro guardado antes de sellar el modo en cada registro.
        path = tmp_path / "captures" / f"{record['id']}.json"
        legacy = json.loads(path.read_text())
        legacy.pop("mode")
        path.write_text(json.dumps(legacy))
    fresh_mock, fresh_live = CommodityCurveStore(tmp_path, mode="mock"), CommodityCurveStore(tmp_path, mode="live")
    loaded = fresh_mock.load("captures", sample["id"])
    assert (loaded["mode"], loaded["mode_inferred"]) == ("mock", True)
    assert [row["id"] for row in fresh_live.records("captures")[0]] == [live["id"]]
    with pytest.raises(FileNotFoundError):
        fresh_live.load("captures", sample["id"])


def test_overview_history_reads_only_new_records_and_the_selected_curves(tmp_path, monkeypatch):
    running = runtime(tmp_path)
    try:
        client = TestClient(create_app(running))
        payload = capture_payload(client)
        for days in range(1, 11):
            save(client, observed_later(payload, -24 * 60 * days))
        # Dos guardados de la misma observación anterior cuentan como una sola curva previa.
        repeated = observed_later(payload, -24 * 60)
        repeated["curve"]["nodes"][0]["price"] += 1
        save(client, repeated)
        store = running.commodities_service.curve_store
        reads = []
        original_read = store._read
        monkeypatch.setattr(store, "_read", lambda category, identity: reads.append(identity) or original_read(category, identity))
        first = client.post("/commodities/workspace", json={"selected_instrument_id": "wti"}).json()["overview"]["term_structure"]
        assert len(first["previous_curve_snapshots"]) == 8
        assert len({snapshot["as_of"] for snapshot in first["previous_curve_snapshots"]}) == 8
        reads.clear()
        client.post("/commodities/workspace", json={"selected_instrument_id": "wti"})
        # Índice en caché: solo se cargan completas las ocho curvas elegidas, no las once retenidas.
        assert len(reads) == 8
    finally:
        running.shutdown()


def test_mock_retention_prunes_oldest_unreferenced_and_live_retention_refuses(tmp_path):
    mock = CommodityCurveStore(tmp_path / "mock", mode="mock")
    mock.MAX_CAPTURES_PER_INSTRUMENT = 3
    saved = [mock.save_capture(minimal_capture(f"2026-10-0{day}T15:00:00+00:00", [node("CLZ6", 70.0 + day), node("CLF7", 69.0)]))
             for day in (1, 2, 3)]
    spread_for(mock, saved[0])  # La captura más antigua es procedencia de un spread: no se poda.
    mock.save_capture(minimal_capture("2026-10-04T15:00:00+00:00", [node("CLZ6", 75.0), node("CLF7", 69.0)]))
    remaining = {row["id"] for row in mock.records("captures")[0]}
    assert saved[0]["id"] in remaining and saved[1]["id"] not in remaining and len(remaining) == 3

    live = CommodityCurveStore(tmp_path / "live", mode="live")
    live.MAX_CAPTURES_PER_INSTRUMENT = 2
    for day in (1, 2):
        live.save_capture(minimal_capture(f"2026-10-0{day}T15:00:00+00:00", [node("CLZ6", 70.0 + day), node("CLF7", 69.0)]))
    with pytest.raises(CommodityRetentionLimitError):
        live.save_capture(minimal_capture("2026-10-03T15:00:00+00:00", [node("CLZ6", 73.0), node("CLF7", 69.0)]))
    assert len(live.records("captures")[0]) == 2


def test_delete_routes_keep_spread_provenance_and_mode_separation(tmp_path):
    running = runtime(tmp_path)
    try:
        client = TestClient(create_app(running))
        capture = save(client, capture_payload(client))
        ids = [n["contract"]["contract_id"] for n in capture["payload"]["curve"]["nodes"]]
        spread = client.post("/commodities/calendar-spreads", json={"capture_id": capture["id"],
                             "left_contract_id": ids[0], "right_contract_id": ids[1]}).json()
        blocked = client.delete(f"/commodities/curve-captures/{capture['id']}")
        assert blocked.status_code == 409 and "delete those spreads first" in blocked.json()["detail"]
        assert client.delete(f"/commodities/calendar-spreads/{spread['id']}").json() == {"id": spread["id"], "deleted": True}
        assert client.delete(f"/commodities/curve-captures/{capture['id']}").status_code == 200
        assert client.get(f"/commodities/curve-captures/{capture['id']}").status_code == 404
        assert client.delete(f"/commodities/curve-captures/{capture['id']}").status_code == 404
        assert client.get("/commodities/curve-captures").json()["captures"] == []
        live_capture = CommodityCurveStore(running.commodities_service.curve_store.base_dir, mode="live").save_capture(
            minimal_capture("2026-10-01T15:00:00+00:00", [node("CLZ6", 70.0), node("CLF7", 69.0)]))
        # El runtime mock no ve ni borra capturas en vivo del mismo directorio.
        assert client.delete(f"/commodities/curve-captures/{live_capture['id']}").status_code == 404
        assert client.get("/commodities/curve-captures").json()["captures"] == []
    finally:
        running.shutdown()
