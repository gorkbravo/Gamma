from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.provider_capability_registry import build_default_provider_capability_registry
from src.application.runtime import build_runtime


def test_default_provider_registry_distinguishes_active_optional_sample_and_planned_providers():
    registry = build_default_provider_capability_registry()
    rows = registry.list_capabilities()
    by_id = {row.provider_id: row for row in rows}

    assert {
        "ibkr",
        "fred",
        "us_treasury",
        "official_macro_events",
        "polymarket",
        "kalshi",
        "coingecko",
        "geckoterminal",
        "sec_edgar",
        "openai_copilot",
        "sample_data",
    }.issubset(by_id)
    assert {
        "eia",
        "bls",
        "bea",
        "ecb",
        "eurostat",
        "databento",
        "aisstream",
        "noaa_marinecadastre",
        "global_fishing_watch",
        "alchemy",
        "dune",
    }.issubset(by_id)

    assert by_id["openai_copilot"].status == "optional"
    assert by_id["sample_data"].status == "sample"
    assert all(row.status == "planned" for row in registry.list_capabilities(status="planned"))
    assert all("status=planned" in (row.transformation_note or "") for row in registry.list_capabilities(status="planned"))


def test_ibkr_capability_is_explicitly_data_only():
    registry = build_default_provider_capability_registry()
    ibkr = registry.get_provider("IBKR")

    assert ibkr is not None
    assert ibkr.status == "active"
    assert ibkr.supports_live is True
    assert ibkr.supports_delayed is True
    assert ibkr.supports_historical is True
    assert ibkr.requires_user_entitlement is True
    assert "portfolio_snapshot" in ibkr.data_types
    assert "implied_volatility_surface" in ibkr.data_types
    assert not any("order" in data_type for data_type in ibkr.data_types)
    assert any("No order placement" in note for note in ibkr.read_only_notes)
    assert any("market-data and portfolio-inspection" in note for note in ibkr.read_only_notes)


def test_registry_filters_by_domain_without_treating_planned_providers_as_active():
    registry = build_default_provider_capability_registry()

    all_crypto = {row.provider_id for row in registry.providers_for_domain("crypto")}
    active_crypto = {
        row.provider_id
        for row in registry.providers_for_domain("crypto", include_planned=False)
    }

    assert {"coingecko", "geckoterminal", "alchemy", "dune"}.issubset(all_crypto)
    assert {"coingecko", "geckoterminal"}.issubset(active_crypto)
    assert "alchemy" not in active_crypto
    assert "dune" not in active_crypto


def test_provider_capability_records_include_provenance_metadata():
    registry = build_default_provider_capability_registry()
    rows = registry.list_capabilities()

    assert rows
    assert all(row.source_provider == "gamma" for row in rows)
    assert all(row.retrieved_at is not None for row in rows)
    assert all(row.origin == "provider_capability_registry.static" for row in rows)
    assert all(row.transformation_note for row in rows)


def test_provider_capabilities_system_api(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.get("/system/provider-capabilities")
        assert response.status_code == 200
        payload = response.json()
        providers = {row["provider_id"]: row for row in payload["providers"]}

        assert payload["source_provider"] == "gamma"
        assert payload["retrieved_at"] is not None
        assert providers["ibkr"]["status"] == "active"
        assert providers["ibkr"]["requires_user_entitlement"] is True
        assert any("No order placement" in note for note in providers["ibkr"]["read_only_notes"])
        assert providers["eia"]["status"] == "planned"
        assert providers["alchemy"]["status"] == "planned"

        active_response = client.get("/system/provider-capabilities", params={"include_planned": False})
        assert active_response.status_code == 200
        active_ids = {row["provider_id"] for row in active_response.json()["providers"]}
        assert "ibkr" in active_ids
        assert "eia" not in active_ids

        planned_response = client.get("/system/provider-capabilities", params={"status": "planned"})
        assert planned_response.status_code == 200
        assert {row["status"] for row in planned_response.json()["providers"]} == {"planned"}

        single_response = client.get("/system/provider-capabilities/us_treasury")
        assert single_response.status_code == 200
        assert single_response.json()["source_provider_values"] == ["treasury"]

        missing_response = client.get("/system/provider-capabilities/not_a_provider")
        assert missing_response.status_code == 404
    finally:
        runtime.shutdown()
