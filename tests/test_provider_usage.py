from __future__ import annotations

import email.message
import io
import socket
import urllib.error
import urllib.request
import urllib.response
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import _build_copilot_provider, build_runtime
from src.services import provider_usage as provider_usage_module
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
from src.services.provider_usage import (
    ProviderActivationCondition,
    ProviderUsageLedger,
    install_http_usage_recorder,
    trace_provider,
    uninstall_http_usage_recorder,
)


class FakeProvider:
    provider_id = "fake_provider"
    source_label = "Fake Provider"

    def load(self, value: str) -> str:
        return f"loaded:{value}"

    def fail(self) -> None:
        raise RuntimeError("provider broke")


def test_provider_usage_ledger_summarizes_recent_calls():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))

    ledger.record(
        provider_id="yfinance",
        endpoint="history",
        status="success",
        cache_status="miss",
        duration_ms=12.4,
    )
    ledger.record(
        provider_id="yfinance",
        endpoint="history",
        status="unavailable",
        cache_status="miss",
        duration_ms=4.1,
        message="No history returned",
    )
    ledger.record(
        provider_id="fred",
        endpoint="series",
        status="success",
        cache_status="hit",
        duration_ms=1.3,
    )

    snapshot = ledger.snapshot()

    assert snapshot.generated_at.isoformat() == "2026-05-16T12:00:00+00:00"
    assert snapshot.total_calls == 3
    assert [row.provider_id for row in snapshot.providers] == ["yfinance", "fred"]
    yfinance = snapshot.providers[0]
    assert yfinance.call_count == 2
    assert yfinance.success_count == 1
    assert yfinance.unavailable_count == 1
    assert yfinance.cache_miss_count == 2
    assert yfinance.last_message == "No history returned"
    assert len(snapshot.recent_calls) == 3


def test_trace_provider_records_success_and_failure_without_swallowing_errors():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(FakeProvider(), ledger, endpoint_prefix="fake")

    assert provider.load("x") == "loaded:x"
    with pytest.raises(RuntimeError, match="provider broke"):
        provider.fail()

    snapshot = ledger.snapshot()
    assert snapshot.total_calls == 2
    assert [call.status for call in snapshot.recent_calls] == ["error", "success"]
    assert snapshot.providers[0].error_count == 1
    assert snapshot.providers[0].last_error == "provider broke"


class UnnamedMacroAdapter:
    """An adapter that names neither itself nor its results, like most of the
    macro, crypto and prediction adapters before GUA-20260903-10."""

    def series(self, code: str) -> list[float]:
        return [1.0, 2.0]


class ComposedSnapshot:
    """An IBKR-backed snapshot built on a reference provider, carrying that
    provider's warnings alongside its own."""

    source_provider = "ibkr"

    def __init__(self, warnings: list[str]) -> None:
        self.warnings = warnings


class ComposedCommoditiesProvider:
    def __init__(self, warnings: list[str]) -> None:
        self._warnings = warnings

    def get_snapshot(self) -> ComposedSnapshot:
        return ComposedSnapshot(self._warnings)


def test_traced_calls_are_attributed_to_the_named_provider_not_unknown():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(
        UnnamedMacroAdapter(), ledger, endpoint_prefix="macro", provider_id="fred"
    )

    provider.series("GOLDAMGBD228NLBM")

    snapshot = ledger.snapshot()
    assert [row.provider_id for row in snapshot.providers] == ["fred"]
    assert snapshot.recent_calls[0].endpoint == "macro.series"


def test_an_unnamed_provider_falls_back_to_its_adapter_name_before_unknown():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(UnnamedMacroAdapter(), ledger, endpoint_prefix="macro")

    provider.series("DGS10")

    assert [row.provider_id for row in ledger.snapshot().providers] == ["unnamed_macro"]


def test_a_provider_that_names_itself_wins_over_the_call_site():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(FakeProvider(), ledger, endpoint_prefix="fake", provider_id="assumed_id")

    provider.load("x")

    assert [row.provider_id for row in ledger.snapshot().providers] == ["fake_provider"]


def test_health_does_not_report_another_providers_failure_as_its_own():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(
        ComposedCommoditiesProvider(["FRED series GOLDAMGBD228NLBM failed."]),
        ledger,
        endpoint_prefix="commodities",
    )

    provider.get_snapshot()

    snapshot = ledger.snapshot()
    ibkr = next(row for row in snapshot.health if row.provider_id == "ibkr")
    assert ibkr.health_status == "healthy"
    assert "FRED" not in ibkr.reason
    assert "none of them about ibkr" in ibkr.reason


def test_health_still_reports_a_providers_own_warning():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(
        ComposedCommoditiesProvider(
            ["FRED series GOLDAMGBD228NLBM failed.", "IBKR returned delayed quotes for 2 curve nodes."]
        ),
        ledger,
        endpoint_prefix="commodities",
    )

    provider.get_snapshot()

    ibkr = next(row for row in ledger.snapshot().health if row.provider_id == "ibkr")
    assert ibkr.reason == "IBKR returned delayed quotes for 2 curve nodes."


def test_a_generic_warning_is_still_attributable_to_the_calling_provider():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(
        ComposedCommoditiesProvider(["Curve analytics are first-pass heuristics."]),
        ledger,
        endpoint_prefix="commodities",
    )

    provider.get_snapshot()

    ibkr = next(row for row in ledger.snapshot().health if row.provider_id == "ibkr")
    assert ibkr.reason == "Curve analytics are first-pass heuristics."


def test_provider_usage_health_distinguishes_idle_by_design_from_failure():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    ledger.register_activation_condition(
        ProviderActivationCondition(
            provider_id="aisstream",
            display_name="AISstream live AIS",
            expected_when="Sealanes live map has a viewport subscription at zoom >= 4.",
            configured=True,
            active=False,
            idle_status="idle_by_design",
            idle_reason="AISstream calls are geofenced and zoom-gated to avoid unnecessary provider traffic.",
            action_label="Open Sealanes and zoom past level 4 to subscribe.",
        )
    )

    snapshot = ledger.snapshot()

    assert snapshot.health[0].provider_id == "aisstream"
    assert snapshot.health[0].health_status == "idle_by_design"
    assert snapshot.health[0].health_label == "Idle by design"
    assert "zoom >= 4" in snapshot.health[0].expected_when
    assert "geofenced" in snapshot.health[0].reason


def test_provider_usage_health_marks_recent_errors_as_degraded():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    ledger.register_activation_condition(
        ProviderActivationCondition(
            provider_id="openai_copilot",
            display_name="OpenAI Copilot",
            expected_when="Copilot research card or synthesis request is submitted.",
            configured=True,
            active=False,
            idle_status="not_requested",
            idle_reason="No Copilot request has been made in this backend session.",
            action_label="Ask Copilot for a grounded research card.",
        )
    )
    ledger.record(
        provider_id="openai_copilot",
        endpoint="copilot.generate",
        status="error",
        duration_ms=250.0,
        message="rate limited",
    )

    snapshot = ledger.snapshot()

    assert snapshot.health[0].provider_id == "openai_copilot"
    assert snapshot.health[0].health_status == "degraded"
    assert snapshot.health[0].error_count == 1
    assert snapshot.health[0].reason == "rate limited"


def test_openai_copilot_sync_and_stream_calls_use_explicit_provider_identity():
    class StubOpenAIProvider(OpenAIResponsesCopilotProvider):
        def generate_research_card(self, **kwargs):
            del kwargs
            return type(
                "Result",
                (),
                {"status": "ready", "model": "gpt-test", "warnings": ["private context warning"]},
            )()

        def stream_research_card(self, **kwargs):
            emit = kwargs["emit"]
            emit("text.delta", {"delta": "done"})
            return type(
                "Result",
                (),
                {"status": "ready", "model": "gpt-test", "warnings": ["private context warning"]},
            )()

    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    ledger.register_activation_condition(
        ProviderActivationCondition(
            provider_id="openai_copilot",
            display_name="OpenAI Copilot",
            expected_when="Copilot is requested.",
            configured=True,
        )
    )
    provider = trace_provider(
        StubOpenAIProvider(api_key="test-key", model="gpt-test", reasoning_effort="low"),
        ledger,
        endpoint_prefix="copilot",
    )

    assert provider.generate_research_card().status == "ready"
    emitted = []
    assert provider.stream_research_card(emit=lambda *event: emitted.append(event)).status == "ready"

    snapshot = ledger.snapshot()
    summary = next(row for row in snapshot.providers if row.provider_id == "openai_copilot")
    health = next(row for row in snapshot.health if row.provider_id == "openai_copilot")
    assert summary.call_count == 2
    assert summary.success_count == 2
    assert summary.endpoints == [
        "copilot.generate_research_card",
        "copilot.stream_research_card",
    ]
    assert health.health_status == "healthy"
    assert health.health_label == "Healthy"
    assert {call.provider_id for call in snapshot.recent_calls} == {"openai_copilot"}
    assert all(call.message == "status=success; model=gpt-test" for call in snapshot.recent_calls)
    assert all("private context warning" not in (call.message or "") for call in snapshot.recent_calls)
    assert emitted == [("text.delta", {"delta": "done"})]


def test_openai_copilot_incomplete_terminal_is_typed_and_not_successful():
    class IncompleteOpenAIProvider(OpenAIResponsesCopilotProvider):
        def stream_research_card(self, **kwargs):
            del kwargs
            return type(
                "Result",
                (),
                {"status": "incomplete", "model": "gpt-test", "warnings": []},
            )()

    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    ledger.register_activation_condition(
        ProviderActivationCondition(
            provider_id="openai_copilot",
            display_name="OpenAI Copilot",
            expected_when="Copilot is requested.",
            configured=True,
        )
    )
    provider = trace_provider(
        IncompleteOpenAIProvider(api_key="test-key", model="gpt-test", reasoning_effort="low"),
        ledger,
        endpoint_prefix="copilot",
    )

    assert provider.stream_research_card().status == "incomplete"

    snapshot = ledger.snapshot()
    summary = next(row for row in snapshot.providers if row.provider_id == "openai_copilot")
    health = next(row for row in snapshot.health if row.provider_id == "openai_copilot")
    assert summary.success_count == 0
    assert summary.error_count == 1
    assert summary.last_status == "incomplete"
    assert snapshot.recent_calls[0].status == "incomplete"
    assert health.health_status == "degraded"


def test_copilot_provider_modes_keep_distinct_diagnostic_identities(monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    assert _build_copilot_provider(allow_mock=True).provider_id == "mock_copilot"

    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "disabled")
    assert _build_copilot_provider(allow_mock=True).provider_id == "disabled_copilot"

    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _build_copilot_provider(allow_mock=True).provider_id == "unavailable_copilot"


def test_provider_usage_system_api_returns_runtime_ledger(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        runtime.provider_usage.record(
            provider_id="mock",
            endpoint="research_history.load_history",
            status="success",
            cache_status="miss",
            duration_ms=2.0,
        )

        response = client.get("/system/provider-usage")

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_provider"] == "gamma"
        assert payload["total_calls"] == 1
        assert payload["providers"][0]["provider_id"] == "mock"
        assert payload["providers"][0]["success_count"] == 1
        assert payload["recent_calls"][0]["endpoint"] == "research_history.load_history"
    finally:
        runtime.shutdown()


def test_provider_usage_system_api_reports_aisstream_idle_by_design(tmp_path, monkeypatch):
    monkeypatch.setenv("MARITIME_PROVIDER", "aisstream")
    monkeypatch.setenv("AISSTREAM_API_KEY", "test-key")
    runtime = build_runtime(
        mock_mode=False,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.get("/system/provider-usage")

        assert response.status_code == 200
        health = {row["provider_id"]: row for row in response.json()["health"]}
        assert health["aisstream"]["health_status"] == "idle_by_design"
        assert "zoom >= 4" in health["aisstream"]["expected_when"]
        assert "Sealanes" in health["aisstream"]["action_label"]
    finally:
        runtime.shutdown()


def test_health_reports_degraded_when_recent_requests_failed_even_if_the_last_one_succeeded():
    """GUA-20260903-5: a badge must not read Healthy while visible requests failed."""
    from src.services.provider_usage import ProviderUsageLedger

    ledger = ProviderUsageLedger()
    ledger.record(provider_id="ibkr", endpoint="iv.surface", status="error", message="contract request failed")
    ledger.record(provider_id="ibkr", endpoint="iv.surface", status="success", message="ok")

    health = {row.provider_id: row for row in ledger.snapshot().health}["ibkr"]

    assert health.health_status == "degraded"
    assert "1 failed" in health.reason
    assert health.session_status == "connected"


def test_partial_surface_delivery_is_counted_separately_from_outright_errors():
    from src.services.provider_usage import ProviderUsageLedger

    ledger = ProviderUsageLedger()
    ledger.record(
        provider_id="ibkr",
        endpoint="iv.surface",
        status="incomplete",
        message="GOOGL options surface returned 71 of 104 requested cells; the remainder is fitted, not quoted.",
    )

    snapshot = ledger.snapshot()
    summary = {row.provider_id: row for row in snapshot.providers}["ibkr"]
    health = {row.provider_id: row for row in snapshot.health}["ibkr"]

    assert summary.incomplete_count == 1
    assert health.health_status == "degraded"
    assert health.incomplete_count == 1
    assert "71 of 104" in health.reason


def test_clean_provider_history_still_reads_healthy():
    from src.services.provider_usage import ProviderUsageLedger

    ledger = ProviderUsageLedger()
    for _ in range(3):
        ledger.record(provider_id="yfinance", endpoint="history", status="success")

    health = {row.provider_id: row for row in ledger.snapshot().health}["yfinance"]

    assert health.health_status == "healthy"
    assert health.incomplete_count == 0


# ── GUA-20260903-10: atribución completa y filas que suman el total ─────────


class _FakeHTTPHandler(urllib.request.BaseHandler):
    """Responde a http/https sin red: código por host, o un timeout simulado."""

    handler_order = 100

    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.seen: list[str] = []

    def http_open(self, req):
        return self._respond(req)

    def https_open(self, req):
        return self._respond(req)

    def _respond(self, req):
        self.seen.append(req.full_url)
        outcome = self.responses.get(req.host, 200)
        if outcome == "timeout":
            raise urllib.error.URLError(socket.timeout("timed out"))
        response = urllib.response.addinfourl(io.BytesIO(b"{}"), email.message.Message(), req.full_url, code=outcome)
        response.msg = "Bad Request" if outcome == 400 else "OK"
        return response


@pytest.fixture
def http_recorder():
    """Instala el registrador HTTP sobre un opener falso y restaura el estado global."""

    saved_opener = getattr(urllib.request, "_opener", None)
    saved_ledger = provider_usage_module._HTTP_RECORDER_STATE["ledger"]
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 10, 21, 10, 30, tzinfo=timezone.utc))

    def install(responses: dict[str, object]) -> _FakeHTTPHandler:
        handler = _FakeHTTPHandler(responses)
        urllib.request.install_opener(urllib.request.build_opener(handler))
        install_http_usage_recorder(ledger)
        return handler

    try:
        yield ledger, install
    finally:
        urllib.request.install_opener(saved_opener)
        provider_usage_module._HTTP_RECORDER_STATE["ledger"] = saved_ledger


def test_http_errors_are_attributed_by_host_and_counted_without_leaking_the_query(http_recorder):
    ledger, install = http_recorder
    install({"api.stlouisfed.org": 400})

    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(
            "https://api.stlouisfed.org/fred/series/observations?series_id=GOLDAMGBD228NLBM&api_key=SECRET-KEY"
        )

    snapshot = ledger.snapshot()
    fred = {row.provider_id: row for row in snapshot.providers}["fred"]
    assert fred.call_count == 1
    assert fred.error_count == 1
    assert fred.http_request_count == 1
    call = snapshot.recent_calls[0]
    assert call.kind == "http"
    assert call.endpoint == "http:api.stlouisfed.org"
    assert "HTTP 400" in (call.message or "")
    assert "SECRET-KEY" not in (call.message or "") and "api_key" not in (call.message or "")
    health = {row.provider_id: row for row in snapshot.health}["fred"]
    assert health.health_status == "degraded"


def test_reference_calls_inside_a_composed_provider_keep_their_own_provider(http_recorder):
    """Las referencias EIA/FRED de la curva IBKR ya no se atribuyen a IBKR."""

    ledger, install = http_recorder
    install({"api.stlouisfed.org": 400, "api.eia.gov": 200})

    class IbkrCurveProvider:
        provider_id = "ibkr"

        def get_snapshot(self):
            urllib.request.urlopen("https://api.eia.gov/v2/seriesid/PET.WCESTUS1.W?api_key=SECRET")
            try:
                urllib.request.urlopen("https://api.stlouisfed.org/fred/series/observations?series_id=SLVPRUSD")
            except urllib.error.HTTPError:
                pass  # el adaptador real lo convierte en un aviso
            return ComposedSnapshot(["FRED series SLVPRUSD failed: HTTP Error 400."])

    trace_provider(IbkrCurveProvider(), ledger, endpoint_prefix="commodities").get_snapshot()

    snapshot = ledger.snapshot()
    rows = {row.provider_id: row for row in snapshot.providers}
    assert set(rows) == {"ibkr", "eia", "fred"}
    assert rows["eia"].success_count == 1
    assert rows["fred"].error_count == 1
    assert rows["ibkr"].call_count == 1 and rows["ibkr"].http_request_count == 0
    assert "http:api.eia.gov via commodities.get_snapshot" in rows["eia"].endpoints
    assert sum(row.call_count for row in snapshot.providers) == snapshot.total_calls == 3


def test_unknown_hosts_inherit_the_calling_provider_or_show_as_unattributed(http_recorder):
    ledger, install = http_recorder
    install({"feeds.example.org": 200, "cdn.example.net": "timeout"})

    class Feeds:
        provider_id = "rss"

        def latest(self):
            return urllib.request.urlopen("https://feeds.example.org/markets.xml")

    trace_provider(Feeds(), ledger, endpoint_prefix="news").latest()
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen("https://cdn.example.net/blob")

    snapshot = ledger.snapshot()
    rows = {row.provider_id: row for row in snapshot.providers}
    assert rows["rss"].call_count == 2 and rows["rss"].http_request_count == 1
    assert "http:feeds.example.org via news.latest" in rows["rss"].endpoints
    assert rows["unattributed"].call_count == 1
    assert rows["unattributed"].error_count == 1
    assert snapshot.recent_calls[0].status == "timeout"
    assert sum(row.call_count for row in snapshot.providers) == snapshot.total_calls
    unattributed_health = {row.provider_id: row for row in snapshot.health}["unattributed"]
    assert unattributed_health.display_name == "Unattributed calls"


def test_the_recorder_passes_through_when_no_ledger_is_active(http_recorder):
    ledger, install = http_recorder
    handler = install({})
    uninstall_http_usage_recorder()

    urllib.request.urlopen("https://api.eia.gov/v2/seriesid/X")

    assert handler.seen == ["https://api.eia.gov/v2/seriesid/X"]
    assert ledger.snapshot().total_calls == 0


def test_status_words_never_become_provider_rows_and_cached_suffix_is_a_cache_hit():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc))

    class UnavailableNews:
        provider_id = "unavailable_news"

        def latest(self):
            return type("Feed", (), {"source_provider": "unavailable", "warnings": ["No live news provider."]})()

    class CachedIbkr:
        provider_id = "ibkr_fx"

        def quote(self):
            return type("Quote", (), {"source_provider": "ibkr_cached"})()

    trace_provider(UnavailableNews(), ledger, endpoint_prefix="news").latest()
    trace_provider(CachedIbkr(), ledger, endpoint_prefix="macro").quote()
    ledger.record(provider_id="", endpoint="orphan", status="success")
    ledger.record(provider_id="unknown", endpoint="orphan", status="success")

    snapshot = ledger.snapshot()
    rows = {row.provider_id: row for row in snapshot.providers}
    assert set(rows) == {"unavailable_news", "ibkr", "unattributed"}
    assert rows["unavailable_news"].unavailable_count == 1
    assert rows["ibkr"].cache_hit_count == 1
    assert rows["unattributed"].call_count == 2


def test_rows_sum_to_the_retained_total_and_lifetime_counts_everything():
    ledger = ProviderUsageLedger(max_calls=3, clock=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc))
    for provider_id in ("fred", "fred", "eia", "kalshi", "polymarket"):
        ledger.record(provider_id=provider_id, endpoint="x", status="success")

    snapshot = ledger.snapshot()

    assert snapshot.total_calls == 3
    assert snapshot.lifetime_calls == 5
    assert snapshot.retained_limit == 3
    assert sum(row.call_count for row in snapshot.providers) == snapshot.total_calls


def test_app_lifespan_installs_the_http_recorder_for_its_runtime(tmp_path):
    saved_opener = getattr(urllib.request, "_opener", None)
    saved_ledger = provider_usage_module._HTTP_RECORDER_STATE["ledger"]
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        with TestClient(create_app(runtime)):
            assert isinstance(urllib.request._opener, provider_usage_module._UsageRecordingOpener)
            assert provider_usage_module._HTTP_RECORDER_STATE["ledger"] is runtime.provider_usage
            # Un runtime inyectado nunca lanza el auto-connect a TWS.
            assert runtime.ib_auto_connect is None
    finally:
        urllib.request.install_opener(saved_opener)
        provider_usage_module._HTTP_RECORDER_STATE["ledger"] = saved_ledger
        runtime.shutdown()


def test_provider_usage_api_exposes_window_and_http_counts(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        runtime.provider_usage.record(provider_id="fred", endpoint="http:api.stlouisfed.org", status="error", kind="http")

        payload = client.get("/system/provider-usage").json()

        assert payload["total_calls"] == 1
        assert payload["lifetime_calls"] == 1
        assert payload["retained_limit"] == runtime.provider_usage.max_calls
        assert payload["providers"][0]["http_request_count"] == 1
        assert payload["recent_calls"][0]["kind"] == "http"
    finally:
        runtime.shutdown()
