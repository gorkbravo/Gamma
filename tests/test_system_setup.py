"""Asistente de primer arranque: preferencias, informe de preparación y endpoints /system/setup."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.application.setup_service import resolve_startup_settings
from src.services.setup_store import (
    SETUP_SCHEMA_VERSION,
    SecIdentity,
    SetupPreferences,
    SetupStore,
    SetupStoreError,
)

FAKE_SECRET = "sk-test-not-a-real-key-123456"


def _runtime(tmp_path, *, mock_mode: bool | None = True):
    return build_runtime(
        mock_mode=mock_mode,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )


def _client(tmp_path, *, mock_mode: bool | None = True):
    runtime = _runtime(tmp_path, mock_mode=mock_mode)
    return TestClient(create_app(runtime)), runtime


# ── Precedencia de los ajustes de arranque ───────────────────────────────


def test_startup_settings_precedence_argument_environment_setup_default(monkeypatch):
    saved = SetupPreferences(data_mode="live", base_currency="GBP", market_data_mode="live")

    monkeypatch.setenv("MOCK_DATA", "true")
    monkeypatch.setenv("BASE_CURRENCY", "chf")
    monkeypatch.setenv("IB_MARKET_DATA_MODE", "delayed")
    from_env = resolve_startup_settings(saved)
    assert (from_env.mock_mode, from_env.mock_mode_source) == (True, "environment")
    assert (from_env.base_currency, from_env.base_currency_source) == ("CHF", "environment")
    assert (from_env.market_data_mode, from_env.market_data_mode_source) == ("delayed", "environment")

    explicit = resolve_startup_settings(saved, mock_mode_argument=False)
    assert (explicit.mock_mode, explicit.mock_mode_source) == (False, "argument")

    for name in ("MOCK_DATA", "BASE_CURRENCY", "IB_MARKET_DATA_MODE"):
        monkeypatch.delenv(name, raising=False)
    from_setup = resolve_startup_settings(saved)
    assert (from_setup.mock_mode, from_setup.mock_mode_source) == (False, "setup")
    assert (from_setup.base_currency, from_setup.base_currency_source) == ("GBP", "setup")
    assert (from_setup.market_data_mode, from_setup.market_data_mode_source) == ("live", "setup")

    defaults = resolve_startup_settings(SetupPreferences())
    assert (defaults.mock_mode, defaults.mock_mode_source) == (True, "default")
    assert (defaults.base_currency, defaults.base_currency_source) == ("EUR", "default")
    assert (defaults.market_data_mode, defaults.market_data_mode_source) == ("delayed", "default")


def test_empty_mock_data_environment_keeps_previous_live_semantics(monkeypatch):
    # Antes del asistente, MOCK_DATA="" ya significaba live; no debe cambiar en silencio.
    monkeypatch.setenv("MOCK_DATA", "")
    settings = resolve_startup_settings(SetupPreferences(data_mode="demo"))
    assert (settings.mock_mode, settings.mock_mode_source) == (False, "environment")


# ── Store ────────────────────────────────────────────────────────────────


def test_setup_store_round_trip_is_atomic_and_versioned(tmp_path):
    store = SetupStore(tmp_path / "setup")
    assert store.load().preferences == SetupPreferences()
    assert not store.path.exists()

    saved = store.update(data_mode="live", base_currency="EUR", sec_identity=SecIdentity("Ada Tester", "ada@example.com"))
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SETUP_SCHEMA_VERSION
    assert payload["sec_identity"] == {"name": "Ada Tester", "email": "ada@example.com"}
    assert store.load().preferences == saved
    assert not list((tmp_path / "setup").glob("*.tmp"))


def test_setup_store_quarantines_corrupt_file_and_keeps_it(tmp_path):
    store = SetupStore(tmp_path / "setup")
    store.base_dir.mkdir(parents=True)
    store.path.write_text("{not json", encoding="utf-8")

    result = store.load()

    assert result.preferences == SetupPreferences()
    assert result.warnings and "could not be read" in result.warnings[0]
    assert not store.path.exists()
    assert len(list(store.base_dir.glob("setup.corrupt-*.json"))) == 1


def test_setup_store_refuses_to_overwrite_newer_schema(tmp_path):
    store = SetupStore(tmp_path / "setup")
    store.base_dir.mkdir(parents=True)
    newer = {"schema_version": SETUP_SCHEMA_VERSION + 1, "data_mode": "quantum"}
    store.path.write_text(json.dumps(newer), encoding="utf-8")

    result = store.load()
    assert result.read_only and result.preferences == SetupPreferences()
    with pytest.raises(SetupStoreError):
        store.update(data_mode="demo")
    assert json.loads(store.path.read_text(encoding="utf-8")) == newer


# ── Informe ──────────────────────────────────────────────────────────────


def test_setup_report_first_run_demo_coverage_and_no_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", FAKE_SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_SECRET)
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "openai")
    client, runtime = _client(tmp_path)
    try:
        response = client.get("/system/setup")
        assert response.status_code == 200
        body = response.json()
        assert FAKE_SECRET not in response.text

        assert body["first_run"] is True
        assert body["data_mode"]["current"] == "demo"
        assert body["data_mode"]["source"] == "argument"
        assert body["ibkr"]["status"] == "demo"
        assert body["sec_identity"]["status"] == "missing"
        assert body["sec_identity"]["source"] == "missing"
        assert body["sec_identity"]["name"] is None
        assert body["copilot"]["status"] == "configured"

        fred = next(row for row in body["providers"] if row["provider_id"] == "fred")
        assert fred["configured"] is True and fred["env_vars"] == ["FRED_API_KEY"]
        assert all(row["provider_id"] != "openai_copilot" for row in body["providers"])

        coverage = {row["tab_id"]: row["source"] for row in body["coverage_by_mode"]["demo"]}
        live = {row["tab_id"]: row["source"] for row in body["coverage_by_mode"]["live"]}
        assert live["portfolio"] == "broker" and live["iv"] == "broker"
        assert "not connected" in body["coverage_by_mode"]["live"][0]["detail"]
        assert coverage["portfolio"] == "sample"
        assert coverage["risk"] == "sample"
        assert coverage["iv"] == "sample"
        assert coverage["prediction_markets"] == "public"
        assert coverage["copilot"] == "model"
        assert set(coverage) == {
            "portfolio", "risk", "iv", "sitrep", "equity_research", "strategy_lab", "macro",
            "prediction_markets", "crypto", "fundamentals", "commodities", "maritime", "copilot",
        }
    finally:
        runtime.shutdown()


def test_setup_report_marks_copilot_missing_key_and_maritime_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MARITIME_PROVIDER", "aisstream")
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    client, runtime = _client(tmp_path)
    try:
        body = client.get("/system/setup").json()
        coverage = {row["tab_id"]: row for row in body["coverage_by_mode"]["demo"]}
        live = {row["tab_id"]: row for row in body["coverage_by_mode"]["live"]}
        assert live["commodities"]["source"] == "unavailable"
        assert body["copilot"]["status"] == "missing_key"
        assert coverage["copilot"]["source"] == "unavailable"
        assert coverage["maritime"]["source"] == "unavailable"
        assert "AISSTREAM_API_KEY" in coverage["maritime"]["detail"]
    finally:
        runtime.shutdown()


def test_setup_report_locks_values_set_by_environment(tmp_path):
    # La suite fija MOCK_DATA, BASE_CURRENCY e IB_MARKET_DATA_MODE en el entorno.
    client, runtime = _client(tmp_path, mock_mode=None)
    try:
        body = client.get("/system/setup").json()
        assert body["data_mode"]["locked_by"] == "MOCK_DATA"
        assert body["base_currency"]["locked_by"] == "BASE_CURRENCY"
        assert body["market_data_mode"]["locked_by"] == "IB_MARKET_DATA_MODE"

        saved = client.post("/system/setup", json={"data_mode": "live"}).json()
        assert saved["data_mode"]["restart_required"] is False
        assert saved["data_mode"]["preference"] == "live"
        assert any("MOCK_DATA" in line for line in saved["lines"])
        assert any("ignored" in warning for warning in saved["warnings"])
    finally:
        runtime.shutdown()


# ── Cambios ──────────────────────────────────────────────────────────────


def test_saving_live_preference_requires_restart_and_is_used_next_start(tmp_path, monkeypatch):
    monkeypatch.delenv("MOCK_DATA", raising=False)
    client, runtime = _client(tmp_path, mock_mode=None)
    try:
        assert runtime.mock_mode is True
        response = client.post("/system/setup", json={"data_mode": "live", "complete": True})
        assert response.status_code == 200
        body = response.json()
        assert body["first_run"] is False
        assert body["data_mode"] == {
            "current": "demo",
            "preference": "live",
            "source": "default",
            "restart_required": True,
            "locked_by": None,
            "detail": body["data_mode"]["detail"],
        }
        assert any("Restart Gamma" in line for line in body["lines"])
    finally:
        runtime.shutdown()

    # El siguiente arranque resolvería live; se comprueba sin construir un cliente IBKR real.
    preferences = SetupStore(tmp_path / "data" / "setup").load().preferences
    assert resolve_startup_settings(preferences).mock_mode is False


def test_base_currency_and_market_data_mode_persist_across_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("BASE_CURRENCY", raising=False)
    monkeypatch.delenv("IB_MARKET_DATA_MODE", raising=False)
    client, runtime = _client(tmp_path)
    try:
        assert runtime.base_currency == "EUR"
        assert client.post("/system/base-currency", json={"base_currency": "GBP"}).status_code == 200
        assert client.post("/system/market-data-mode", json={"market_data_mode": "live"}).status_code == 200
        report = client.get("/system/setup").json()
        assert report["base_currency"] == {
            "current": "GBP", "source": "setup", "locked_by": None, "options": report["base_currency"]["options"]
        }
        assert report["market_data_mode"]["source"] == "setup"
    finally:
        runtime.shutdown()

    restarted = _runtime(tmp_path)
    try:
        assert restarted.base_currency == "GBP"
        assert restarted.market_data_mode == "live"
        assert restarted.startup_settings.base_currency_source == "setup"
    finally:
        restarted.shutdown()


def test_setup_update_applies_currency_and_rejects_invalid_input_atomically(tmp_path, monkeypatch):
    monkeypatch.delenv("BASE_CURRENCY", raising=False)
    client, runtime = _client(tmp_path)
    try:
        invalid = client.post(
            "/system/setup",
            json={"base_currency": "CHF", "sec_identity": {"name": "Ada Tester", "email": "not-an-email"}},
        )
        assert invalid.status_code == 422
        # Nada se aplicó ni se guardó: la validación ocurre antes de cualquier cambio.
        assert runtime.base_currency == "EUR"
        assert not (tmp_path / "data" / "setup" / "setup.json").exists()

        applied = client.post("/system/setup", json={"base_currency": "chf", "market_data_mode": "delayed"})
        assert applied.status_code == 200
        assert runtime.base_currency == "CHF"
        assert runtime.market_data_mode == "delayed"
        assert any("Base currency set to CHF" in line for line in applied.json()["lines"])

        assert client.post("/system/setup", json={"data_mode": "paper"}).status_code == 422
        assert client.post("/system/setup", json={"market_data_mode": "turbo"}).status_code == 422
    finally:
        runtime.shutdown()


def test_sec_identity_is_saved_applied_and_cleared(tmp_path, monkeypatch):
    monkeypatch.delenv("GAMMA_SEC_USER_NAME", raising=False)
    monkeypatch.delenv("GAMMA_SEC_USER_EMAIL", raising=False)
    client, runtime = _client(tmp_path)
    try:
        saved = client.post(
            "/system/setup", json={"sec_identity": {"name": "  Ada   Tester ", "email": "ada@example.com"}}
        ).json()
        assert saved["sec_identity"]["source"] == "setup"
        assert saved["sec_identity"]["name"] == "Ada Tester"
        assert runtime.sec_fundamentals_adapter.identity_name == "Ada Tester"
        assert runtime.sec_fundamentals_adapter.identity_email == "ada@example.com"
        assert runtime.sec_fundamentals_adapter._edgar_configured is False

        cleared = client.post("/system/setup", json={"clear_sec_identity": True}).json()
        assert cleared["sec_identity"]["status"] == "missing"
        assert runtime.sec_fundamentals_adapter.identity_source == "missing"
        assert runtime.sec_fundamentals_adapter.user_agent() is None
        assert any("SEC identity removed" in line for line in cleared["lines"])
    finally:
        runtime.shutdown()

    restarted = _runtime(tmp_path)
    try:
        assert restarted.sec_fundamentals_adapter.identity_source == "missing"
    finally:
        restarted.shutdown()


def test_environment_sec_identity_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_SEC_USER_NAME", "Env Tester")
    monkeypatch.setenv("GAMMA_SEC_USER_EMAIL", "env@example.com")
    client, runtime = _client(tmp_path)
    try:
        body = client.post(
            "/system/setup", json={"sec_identity": {"name": "Ada Tester", "email": "ada@example.com"}}
        ).json()
        assert body["sec_identity"]["source"] == "environment"
        assert body["sec_identity"]["name"] is None
        assert runtime.sec_fundamentals_adapter.identity_name == "Env Tester"
        assert any("take precedence" in line for line in body["lines"])
    finally:
        runtime.shutdown()


def test_setup_update_conflicts_with_newer_schema_without_side_effects(tmp_path, monkeypatch):
    monkeypatch.delenv("BASE_CURRENCY", raising=False)
    setup_dir = tmp_path / "data" / "setup"
    setup_dir.mkdir(parents=True)
    (setup_dir / "setup.json").write_text(json.dumps({"schema_version": SETUP_SCHEMA_VERSION + 1}), encoding="utf-8")
    client, runtime = _client(tmp_path)
    try:
        response = client.post("/system/setup", json={"base_currency": "JPY", "complete": True})
        assert response.status_code == 409
        assert runtime.base_currency == "EUR"
        assert client.get("/system/setup").json()["warnings"]
    finally:
        runtime.shutdown()


def test_setup_endpoints_require_the_session_token(tmp_path):
    runtime = _runtime(tmp_path)
    try:
        client = TestClient(create_app(runtime, session_token="expected-session"))
        assert client.get("/system/setup", headers={"X-Gamma-Session": "wrong"}).status_code == 401
        assert client.post("/system/setup", json={}, headers={"X-Gamma-Session": "wrong"}).status_code == 401
    finally:
        runtime.shutdown()


# ── Sin identidad SEC ────────────────────────────────────────────────────


def test_missing_sec_identity_blocks_every_sec_request_before_network(tmp_path, monkeypatch):
    from src.services import fundamentals_adapters
    from src.services.cache import CacheService
    from src.services.fundamentals_adapters import SecFundamentalsAdapter, SecIdentityMissingError

    monkeypatch.delenv("GAMMA_SEC_USER_NAME", raising=False)
    monkeypatch.delenv("GAMMA_SEC_USER_EMAIL", raising=False)

    def forbidden_edgar_tools():
        raise AssertionError("EdgarTools must not be touched without an SEC identity")

    monkeypatch.setattr(fundamentals_adapters, "_load_edgar_tools", forbidden_edgar_tools)
    monkeypatch.setattr(fundamentals_adapters, "urlopen", lambda *_a, **_k: forbidden_edgar_tools())
    adapter = SecFundamentalsAdapter(CacheService(tmp_path / "cache"))

    assert adapter.identity_source == "missing"
    assert adapter.user_agent() is None
    with pytest.raises(SecIdentityMissingError):
        adapter.search_companies("AAPL")
    with pytest.raises(SecIdentityMissingError):
        adapter.load_company_data("AAPL")


def test_partial_environment_identity_is_ignored_and_reported(tmp_path, monkeypatch):
    from src.services.cache import CacheService
    from src.services.fundamentals_adapters import SecFundamentalsAdapter

    monkeypatch.setenv("GAMMA_SEC_USER_NAME", "Env Tester")
    monkeypatch.delenv("GAMMA_SEC_USER_EMAIL", raising=False)
    adapter = SecFundamentalsAdapter(CacheService(tmp_path / "cache"), identity=("Ada Tester", "ada@example.com"))

    assert adapter.partial_environment is True
    assert adapter.identity_source == "setup"
    assert adapter.user_agent() == "Ada Tester ada@example.com"


def test_fundamentals_routes_answer_428_with_a_stable_code_without_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("GAMMA_SEC_USER_NAME", raising=False)
    monkeypatch.delenv("GAMMA_SEC_USER_EMAIL", raising=False)
    client, runtime = _client(tmp_path)
    try:
        for path in ("/fundamentals/search?query=AAPL", "/fundamentals/AAPL/overview", "/fundamentals/AAPL/financials"):
            response = client.get(path)
            assert response.status_code == 428, path
            assert response.json()["code"] == "sec_identity_missing"
            assert "Setup" in response.json()["detail"]
        report = client.get("/system/setup").json()
        assert report["sec_identity"]["status"] == "missing"
        assert "Fundamentals" in report["sec_identity"]["detail"]
    finally:
        runtime.shutdown()


def test_script_fundamentals_discovery_and_export_explain_missing_identity(tmp_path, monkeypatch):
    from src.application.script_dataset_catalog import DatasetServiceUnavailableError
    from src.models.research_script import ResearchScriptDataExportRequest

    monkeypatch.delenv("GAMMA_SEC_USER_NAME", raising=False)
    monkeypatch.delenv("GAMMA_SEC_USER_EMAIL", raising=False)
    runtime = _runtime(tmp_path)
    try:
        catalog = runtime.research_script_service.dataset_catalog
        found = catalog.search("fundamentals", "AAPL")
        assert found["status"] == "unavailable"
        assert found["items"] == []
        assert "SEC EDGAR" in found["warnings"][0]
        with pytest.raises(DatasetServiceUnavailableError, match="SEC EDGAR"):
            catalog.acquire(ResearchScriptDataExportRequest(domain="fundamentals", object_id="AAPL", logical_filename="aapl.json"))
    finally:
        runtime.shutdown()


def test_copilot_entity_resolution_names_the_missing_identity():
    from src.application.copilot_entity_resolution import _safe_search
    from src.services.fundamentals_adapters import SecIdentityMissingError

    def search(_query, limit=12):
        raise SecIdentityMissingError()

    warnings: list[str] = []
    assert _safe_search(search, "Lockheed", warnings) == []
    assert len(warnings) == 1 and "SEC EDGAR identity" in warnings[0] and "Setup" in warnings[0]


def test_sec_press_release_feed_uses_identity_or_is_skipped():
    from src.services.news_adapters import SEC_FEED_SKIPPED_WARNING, RssFeedConfig, RssNewsEventProvider

    sec_feed = RssFeedConfig(feed_id="sec_press_releases", source_name="SEC", url="https://www.sec.gov/news/pressreleases.rss")
    other_feed = RssFeedConfig(feed_id="other", source_name="Other", url="https://example.com/rss.xml")
    seen: list[tuple[str, str]] = []

    def fetcher(feed, _timeout, user_agent):
        seen.append((feed.feed_id, user_agent))
        return b"<rss><channel></channel></rss>"

    skipped = RssNewsEventProvider(feeds=(sec_feed, other_feed), fetcher=fetcher, sec_user_agent=lambda: None).latest()
    assert seen == [("other", "GammaResearch/0.1 read-only RSS news adapter")]
    assert SEC_FEED_SKIPPED_WARNING in skipped.warnings

    seen.clear()
    RssNewsEventProvider(feeds=(sec_feed,), fetcher=fetcher, sec_user_agent=lambda: "Ada Tester ada@example.com").latest()
    assert seen == [("sec_press_releases", "Ada Tester ada@example.com")]


# ── Ruta del .env ────────────────────────────────────────────────────────


def test_env_file_path_follows_app_data_in_packaged_builds(tmp_path, monkeypatch):
    import sys

    from src.application.setup_service import REPO_ENV_FILE_PATH, resolve_env_file_path

    monkeypatch.delenv("GAMMA_ENV_FILE", raising=False)
    monkeypatch.delenv("GAMMA_APP_DATA_DIR", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert resolve_env_file_path() == REPO_ENV_FILE_PATH

    # Backend empaquetado: no hay repositorio y la app de escritorio pasa su carpeta de datos.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("GAMMA_APP_DATA_DIR", str(tmp_path / "runtime"))
    assert resolve_env_file_path() == tmp_path / "runtime" / ".env"

    # Una ruta explícita manda en cualquier modo.
    monkeypatch.setenv("GAMMA_ENV_FILE", str(tmp_path / "custom.env"))
    assert resolve_env_file_path() == tmp_path / "custom.env"
