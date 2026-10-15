"""E2 deterministic contracts; these fixtures are not live-provider acceptance."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src.application.script_dataset_catalog import DATASETS, DatasetSelectionError, describe
from src.application.research_script_service import ResearchScriptService, ResearchScriptValidationError
from src.models.research_script import ResearchScriptCreateRequest, ResearchScriptDataExportRequest, ResearchScriptRunCreateRequest
from src.services.iv_snapshot_store import IVSnapshotStore
from src.services.research_script_runtime import MockResearchScriptRuntime
from src.services.research_script_store import ResearchScriptStore
from src.services.research_market_data import ResearchHistoryResult
from src.models.provenance import FreshnessLabel


STAMP = datetime(2026, 9, 1, tzinfo=timezone.utc)


@dataclass
class Company:
    ticker: str = "ABC"


@dataclass
class Financials:
    company: Company
    annual_income_statement: dict
    warnings: tuple = ("Partial normalized statements",)


def setup(tmp_path):
    # Real dataclass records exercise the serialization boundary, not arbitrary service objects.
    from src.models.commodities import CommodityPriceHistory, CommodityPricePoint, CommodityCurveSnapshot, CommodityCurveNode, CommodityFuturesContract, CommoditySpreadSnapshot, CommoditySpreadDefinition, CommodityInventorySeries, CommodityInventorySeriesMetadata, CommodityInventoryPoint
    history = CommodityPriceHistory("wti", "WTI", "USD/bbl", [CommodityPricePoint("wti", STAMP, 70, "USD/bbl", "mock", STAMP)], source_provider="mock", retrieved_at=STAMP)
    curve = CommodityCurveSnapshot("wti", STAMP, [CommodityCurveNode(CommodityFuturesContract("CLZ6", "wti", "CL", "202612"), 70)], source_provider="mock", retrieved_at=STAMP)
    spread = CommoditySpreadSnapshot(CommoditySpreadDefinition("wti-brent", "WTI/Brent", "intermarket", "wti", "brent", "USD/bbl", "wti - brent"), 2, source_provider="mock", retrieved_at=STAMP)
    inventory = CommodityInventorySeries(CommodityInventorySeriesMetadata("stocks", "wti", "Crude stocks", "inventory", "million bbl", "weekly"), [CommodityInventoryPoint("stocks", STAMP, 430)], source_provider="mock", retrieved_at=STAMP)
    commodities = SimpleNamespace(get_workspace=lambda: SimpleNamespace(instruments=[SimpleNamespace(instrument_id="wti", name="WTI", symbol="CL", quote_unit="USD/bbl")], spreads=[spread], inventories=[inventory], warnings=["Sample provider"]), get_price_history=lambda identity: history, get_curve=lambda identity: curve)
    options = IVSnapshotStore(tmp_path / "options")
    capture = options.save({"symbol": "SPY", "snapshot_available": True, "timestamp": STAMP.isoformat(), "retrieved_at": STAMP.isoformat(), "source_provider": "mock", "freshness_label": "mocked", "contracts": [{"contract_id": "exact-call", "expiry": "20261218", "strike": 600, "right": "C", "currency": "USD"}], "pairs": [{"call_contract_id": "exact-call", "blended_implied_volatility": .2}], "iv_grid": [[.21]], "cell_sources": [["fitted"]], "surface_model": "ssvi"})
    @dataclass
    class Token:
        token_id: str = "bitcoin"
        name: str = "Bitcoin"
        symbol: str = "BTC"
        source_provider: str = "mock"
        retrieved_at: datetime = STAMP
    @dataclass
    class Liquidity:
        token_id: str = "bitcoin"
        pools: tuple = ()
        warnings: tuple = ("No matching DEX pools",)
    from src.models.crypto import CryptoPricePoint
    crypto = SimpleNamespace(get_workspace=lambda r: SimpleNamespace(tokens=[Token()], warnings=[]), get_token_detail=lambda i: Token(), get_price_history=lambda i, **kw: [CryptoPricePoint(STAMP, 60000, 100000, 1000, "mock", STAMP)], get_dex_liquidity=lambda i: Liquidity())
    @dataclass
    class Outcome:
        outcome_id: str = "no"
        label: str = "No"
        token_id: str = "venue-token-no"
    @dataclass
    class Market:
        market_id: str = "venue:exact"
        title: str = "Event contract"
        venue: str = "venue"
        outcomes: tuple = (Outcome(),)
        event_id: str = "event-exact"
    from src.models.prediction_markets import PredictionProbabilityHistory, PredictionProbabilityPoint
    prediction = SimpleNamespace(screener=lambda r: SimpleNamespace(markets=[Market()], warnings=[]), get_market_detail=lambda i: Market(), get_history_series=lambda i, **kw: PredictionProbabilityHistory(i, "venue", [PredictionProbabilityPoint(STAMP, .4)], outcome_id=kw["outcome_id"], source_provider="mock", retrieved_at=STAMP))
    @dataclass
    class Saved:
        id: str = "saved-1"
        title: str = "Saved note"
        object_type: str = "research"
        source_provider: str = "gamma_saved_research"
        retrieved_at: datetime = STAMP
    research = SimpleNamespace(list_saved_research=lambda: [Saved()], load_saved_research=lambda i: Saved())
    from src.models.macro import MacroSeriesHistory, MacroSeriesPoint
    macro = SimpleNamespace(get_series_history=lambda i, **kw: MacroSeriesHistory(i, "Treasury", kw["region"], "pct", "daily", "rates", points=[MacroSeriesPoint(STAMP, 4, "mock", STAMP)], source_provider="mock", retrieved_at=STAMP))
    fundamentals = SimpleNamespace(search_companies=lambda q, **kw: [SimpleNamespace(ticker="ABC", name="ABC Inc", cik="123")], get_financials=lambda i: Financials(Company(), {"unit": "USD", "lines": [{"label": "Revenue", "unit": "USD", "cells": [{"period_key": "FY2025", "value": 100, "end_date": STAMP, "source_provider": "sec", "retrieved_at": STAMP}]}]}))
    equity = SimpleNamespace(load_instrument_history_result=lambda i, days: ResearchHistoryResult(pd.Series([100., 101.], index=pd.to_datetime(["2026-08-31", "2026-09-01"])), "mock", "Fixture", "fixture.history", FreshnessLabel.MOCKED, retrieved_at=STAMP))
    service = ResearchScriptService(ResearchScriptStore(tmp_path / "scripts"), MockResearchScriptRuntime(), research_provider=equity, research_service=research, macro_service=macro, dataset_services={"fundamentals": fundamentals, "options": options, "commodities": commodities, "crypto": crypto, "prediction": prediction})
    script = service.create_script(ResearchScriptCreateRequest("test", "E2", "print('hello')"))
    return service, script.script.script_id, capture["snapshot_id"]


def request_for(domain, capture):
    identities = {"equity_history": "SPY", "macro_series": "us-10y-yield", "saved_research": "saved-1", "fundamentals": "ABC", "options_capture": capture, "commodity_history": "wti", "commodity_curve": "wti", "commodity_spread": "wti-brent", "commodity_inventory": "stocks", "crypto_history": "bitcoin", "crypto_liquidity": "bitcoin", "prediction_history": "venue:exact"}
    return ResearchScriptDataExportRequest(domain, identities[domain], domain + ".json", region="US" if domain == "macro_series" else None, outcome_id="no" if domain == "prediction_history" else None)


@pytest.mark.parametrize("domain", DATASETS)
def test_every_catalog_slice_serializes_exact_bytes_and_metadata(tmp_path, domain):
    service, script, capture = setup(tmp_path)
    request = request_for(domain, capture)
    result = service.dataset_catalog.search(domain, request.object_id if domain == "equity_history" else "")
    assert any(r["object_id"] == request.object_id for r in result["items"])
    preview = service.dataset_catalog.preview(script, request)
    assert preview["fields"] and preview["limitations"] and preview["field_notes"]
    assert preview["retrieval_times"] == [STAMP.isoformat()]
    assert not service.list_input_bundles(script)  # inspect has no durable bundle side effect
    snapshot = service.export_domain_input(script, replace(request, preview_id=preview["preview_id"]))
    content = service.store.load_input_contents(snapshot)[request.logical_filename]
    assert hashlib.sha256(content).hexdigest() == preview["sha256"]
    payload = json.loads(content)
    assert payload["metadata"]["object_id"] == request.object_id
    assert payload["metadata"]["retrieval_times"] == [STAMP.isoformat()]
    assert snapshot.files[0].retrieved_at == STAMP
    if domain == "options_capture":
        assert payload["data"]["surface"]["contracts"][0]["contract_id"] == "exact-call"
        assert payload["data"]["surface"]["iv_grid"] == [[.21]]
        assert payload["data"]["surface"]["cell_sources"] == [["fitted"]]
    if domain == "prediction_history":
        assert payload["data"]["history"]["outcome_id"] == "no"
        assert payload["data"]["market"]["outcomes"][0]["token_id"] == "venue-token-no"
    if domain == "fundamentals":
        assert "USD" in preview["units"]
    if domain == "commodity_inventory":
        assert preview["frequencies"] == ["weekly"]
    if domain == "crypto_liquidity":
        assert "partial" in preview["states"]


def test_append_retains_prior_bytes_provenance_and_run_across_restart(tmp_path):
    service, script, capture = setup(tmp_path)
    req = request_for("equity_history", capture)
    preview = service.dataset_catalog.preview(script, req)
    first = service.export_domain_input(script, replace(req, preview_id=preview["preview_id"]))
    run = service.create_run(script, ResearchScriptRunCreateRequest(input_snapshot_id=first.snapshot_id))
    original_bytes = service.store.load_input_contents(first)
    service.dataset_catalog.services["equity"] = None  # appending must never fetch earlier inputs
    req2 = request_for("fundamentals", capture)
    second_preview = service.dataset_catalog.preview(script, req2)
    second = service.export_domain_input(script, replace(req2, preview_id=second_preview["preview_id"], base_snapshot_id=first.snapshot_id))
    assert replace(second.files[0], artifact_ref=first.files[0].artifact_ref) == first.files[0]
    restarted = ResearchScriptService(ResearchScriptStore(tmp_path / "scripts"), MockResearchScriptRuntime())
    reloaded = restarted.get_input_snapshot(second.snapshot_id)
    assert restarted.store.load_input_contents(reloaded)[req.logical_filename] == original_bytes[req.logical_filename]
    assert reloaded.dataset_refs[0] == first.dataset_refs[0]
    assert restarted.get_run(run.run_id).input_manifest_sha256 == first.manifest_sha256
    assert restarted.store.load_input_contents(restarted.get_input_snapshot(first.snapshot_id)) == original_bytes


@pytest.mark.parametrize("change", [{"object_id": "nearby"}, {"timeframe": "5Y"}, {"outcome_id": "yes"}, {"region": "EU"}, {"frequency": "weekly"}])
def test_changed_selection_cannot_add_another_preview(tmp_path, change):
    service, script, capture = setup(tmp_path)
    req = request_for("equity_history", capture)
    result = service.dataset_catalog.preview(script, req)
    with pytest.raises(ResearchScriptValidationError, match="selection changed"):
        service.export_domain_input(script, replace(req, preview_id=result["preview_id"], **change))
    assert not service.list_input_bundles(script)


def test_failures_expiry_foreign_preview_duplicates_and_limits_preserve_bundle(tmp_path, monkeypatch):
    service, script, capture = setup(tmp_path)
    req = request_for("equity_history", capture)
    preview = service.dataset_catalog.preview(script, req)
    add = replace(req, preview_id=preview["preview_id"])
    first = service.export_domain_input(script, add)
    with pytest.raises(ResearchScriptValidationError):
        service.export_domain_input(script, replace(add, base_snapshot_id=first.snapshot_id))
    other = service.create_script(ResearchScriptCreateRequest("other", "Other", "print(1)"))
    with pytest.raises(ResearchScriptValidationError, match="another script"):
        service.export_domain_input(other.script.script_id, add)
    monkeypatch.setattr(service.dataset_catalog, "TTL", -1)
    with pytest.raises(ResearchScriptValidationError, match="expired"):
        service.export_domain_input(script, add)
    service.dataset_catalog.services["equity"] = None
    with pytest.raises(DatasetSelectionError, match="unavailable"):
        service.dataset_catalog.preview(script, req)
    assert service.get_input_snapshot(first.snapshot_id) == first
    assert len(service.list_input_bundles(script)) == 1


@pytest.mark.parametrize("domain,changes", [("equity_history", {"lookback_days": 4000}), ("macro_series", {"region": "EU"}), ("crypto_history", {"timeframe": "MAX"}), ("prediction_history", {"outcome_id": "missing"}), ("commodity_history", {"object_id": "nearby"}), ("fundamentals", {"object_id": "wrong"})])
def test_unsupported_bounds_and_nearby_identity_are_rejected(tmp_path, domain, changes):
    service, script, capture = setup(tmp_path)
    with pytest.raises(DatasetSelectionError):
        service.dataset_catalog.preview(script, replace(request_for(domain, capture), **changes))


def test_empty_sensitive_nonfinite_oversized_and_preview_cache_bounds(tmp_path, monkeypatch):
    service, script, capture = setup(tmp_path)
    catalog = service.dataset_catalog
    req = request_for("saved_research", capture)
    for payload in ({"api_key": "never-copy"}, {"token": "never-copy"}, {"local_path": "C:/private"}, {"points": []}, {"value": float("nan")}):
        monkeypatch.setattr(catalog, "acquire", lambda r: payload)
        with pytest.raises(ValueError):
            catalog.preview(script, req)
    import src.application.request_limits as limits
    monkeypatch.setattr(limits, "MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES", 100)
    monkeypatch.setattr(catalog, "acquire", lambda r: {"text": "x" * 1000})
    with pytest.raises(DatasetSelectionError, match="limit"):
        catalog.preview(script, req)
    monkeypatch.setattr(limits, "MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr(catalog, "MAX_PREVIEWS", 2)
    for _ in range(3):
        catalog.preview(script, req)
    assert len(catalog._previews) == 2


def test_nested_units_sources_and_times_are_not_collapsed():
    metadata = describe({"lines": [{"unit": "USD", "value": 2, "source_provider": "sec", "retrieved_at": "2026-01-01"}, {"unit": "shares", "value": 5, "source_provider": "ibkr", "retrieved_at": "2026-02-01"}]})
    assert metadata["units"] == ["USD", "shares"]
    assert metadata["sources"] == ["ibkr", "sec"]
    assert metadata["retrieval_times"] == ["2026-01-01", "2026-02-01"]
    assert next(f for f in metadata["fields"] if f["name"] == "lines[].value")["unit"] == "USD, shares"


def test_adding_preview_does_not_refetch_and_resampling_is_declared(tmp_path):
    service, script, capture = setup(tmp_path)
    req = replace(request_for("equity_history", capture), frequency="monthly", lookback_days=40)
    preview = service.dataset_catalog.preview(script, req)
    service.dataset_catalog.services["equity"] = None
    bundle = service.export_domain_input(script, replace(req, preview_id=preview["preview_id"]))
    payload = json.loads(service.store.load_input_contents(bundle)[req.logical_filename])
    assert payload["metadata"]["frequency"] == "monthly"
    assert payload["data"]["frequency"] == "monthly"
    assert payload["metadata"]["lookback_days"] == 40
    assert payload["metadata"]["units"] == ["USD"]
    assert [point["close"] for point in payload["data"]["points"]] == [100, 101]
    assert payload["metadata"]["coverage_start"].startswith("2026-08-31")


def test_missing_capture_and_unknown_objects_never_substitute(tmp_path):
    service, script, capture = setup(tmp_path)
    with pytest.raises(FileNotFoundError):
        service.dataset_catalog.preview(script, replace(request_for("options_capture", capture), object_id="a" * 32))
    assert service.dataset_catalog.search("equity_history", "unknown-security")["items"] == []
    assert not service.list_input_bundles(script)


def test_api_discovery_preview_add_and_sanitized_provider_failure(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.main import create_app
    from dataclasses import asdict
    service, script, capture = setup(tmp_path)
    client = TestClient(create_app(SimpleNamespace(research_script_service=service), session_token="e2-test"))
    base = "/research/strategy-lab"
    assert client.get(base + "/script-datasets").status_code == 401
    client.headers["X-Gamma-Session"] = "e2-test"
    assert len(client.get(base + "/script-datasets").json()) == len(DATASETS)
    for domain in DATASETS:
        req = request_for(domain, capture)
        response = client.post(f"{base}/scripts/{script}/dataset-preview", json=asdict(req))
        assert response.status_code == 200, response.text
        payload = asdict(req)
        payload["preview_id"] = response.json()["preview_id"]
        added = client.post(f"{base}/scripts/{script}/inputs/export", json=payload)
        assert added.status_code == 201, added.text
    monkeypatch.setattr(service.dataset_catalog, "acquire", lambda req: (_ for _ in ()).throw(RuntimeError("secret-provider-credential")))
    response = client.post(f"{base}/scripts/{script}/dataset-preview", json=asdict(request_for("crypto_history", capture)))
    assert response.status_code == 503
    assert "secret-provider-credential" not in response.text
    monkeypatch.setattr(service.dataset_catalog, "search", lambda *args: (_ for _ in ()).throw(ValueError("secret-provider-credential")))
    response = client.get(base + "/script-datasets/search?domain=crypto_history")
    assert response.json()["status"] == "unavailable"
    assert "secret-provider-credential" not in response.text
