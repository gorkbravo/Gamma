"""Workstream 12 - Ideas, checkpoint I4b: the read-only Python client in clients/python.

The client runs against the real routes of a demo runtime (FastAPI's TestClient
is an httpx client, so it is passed as the transport). No network, no TWS.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "clients" / "python"))

from gamma_client import ALLOWED_ROUTES, Gamma, GammaClientError, RouteNotAllowedError, route_allowed, signal_rows  # noqa: E402
from src.api.main import create_app  # noqa: E402
from src.application.runtime import build_runtime  # noqa: E402

TOKEN = "client-test-token"


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture()
def gamma(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_SESSION_TOKEN", TOKEN)
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
    clock = _Clock(datetime(2026, 1, 20, 14, 0))
    runtime.idea_service._clock = clock
    runtime.idea_signals._clock = clock
    app = create_app(runtime)
    with TestClient(app) as http:
        client = Gamma(token=TOKEN, http=http)
        client.app = app  # type: ignore[attr-defined]
        client.raw = http  # type: ignore[attr-defined]
        yield client


def _create_idea(gamma) -> str:
    response = gamma.raw.post(
        "/ideas",
        json={"title": "Notebook book", "thesis": "Weights computed in a notebook.", "stance": "long",
              "legs": [{"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}}]},
        headers={"X-Gamma-Session": TOKEN},
    )
    assert response.status_code == 200, response.text
    gamma.raw.post(f"/ideas/{response.json()['idea_id']}/activate", headers={"X-Gamma-Session": TOKEN})
    return response.json()["idea_id"]


def test_history_reads_final_closes_with_provenance(gamma):
    frame = gamma.history("AAPL", days=400)
    assert list(frame.columns) == ["close", "close_at", "source_provider", "retrieved_at", "origin"]
    assert isinstance(frame.index, pd.DatetimeIndex) and frame.index.is_monotonic_increasing
    assert frame.index.max() <= pd.Timestamp("2026-01-27")  # la muestra de demo termina ahí
    assert frame["close"].gt(0).all() and frame.attrs["symbol"] == "AAPL"
    assert frame.attrs["provenance"]["source_provider"]
    assert any("demo sample history" in item for item in frame.attrs["warnings"])
    with pytest.raises(GammaClientError, match="NOPE"):
        gamma.history("NOPE")


def test_ideas_and_observables_are_read(gamma):
    idea_id = _create_idea(gamma)
    assert [item["idea_id"] for item in gamma.ideas.list(status="active")] == [idea_id]
    assert gamma.ideas.get(idea_id)["title"] == "Notebook book"
    assert gamma.ideas.tracking(idea_id)["label"] == "Hypothetical, not executed"
    assert any(item["observable_id"] == "equity_close" for item in gamma.observables())


def test_a_dataframe_signal_is_validated_like_a_strategy_lab_import(gamma):
    idea_id = _create_idea(gamma)
    weights = pd.DataFrame({"AAPL": ["50%", "60%"], "MSFT": [0.5, -0.2]}, index=pd.to_datetime(["2026-01-12", "2026-01-13"]))
    idea = gamma.ideas.attach_signal(idea_id, weights, kind="weights", label="Notebook weights")
    signal = idea["signals"][-1]
    assert signal["source"] == "import" and signal["label"] == "Notebook weights" and signal["as_of"] == "2026-01-13"
    assert [(leg["key"], leg["weight"]) for leg in signal["legs"]] == [("equity:AAPL", 0.6), ("equity:MSFT", -0.2)]
    assert idea["tracking"]["segments"][-1]["signal_id"] == signal["signal_id"]
    assert idea["trial_count"] == 1
    # La misma regla que una importación CSV: una fila futura se rechaza con su motivo.
    future = pd.DataFrame({"AAPL": [1.0]}, index=pd.to_datetime(["2026-02-20"]))
    with pytest.raises(GammaClientError, match="after today") as raised:
        gamma.ideas.attach_signal(idea_id, future)
    assert raised.value.status == 422


def test_a_returns_series_attaches_as_validation_only(gamma):
    idea_id = _create_idea(gamma)
    returns = pd.Series([0.001 * ((-1) ** i) for i in range(40)], index=pd.bdate_range("2025-10-01", periods=40), name="strategy")
    idea = gamma.ideas.attach_signal(idea_id, returns, kind="returns")
    signal = idea["signals"][-1]
    assert signal["output_kind"] == "returns" and signal["drives_tracking"] is False
    assert signal["supplied"]["observations"] == 40
    assert [segment["start_reason"] for segment in idea["tracking"]["segments"]] == ["activated"]


def test_the_client_only_calls_read_routes_and_the_signal_import(gamma):
    # Cada ruta permitida existe en la API y es una lectura o la importación de la señal.
    app_routes = {(method, route.path) for route in gamma.app.routes for method in getattr(route, "methods", set())}
    samples = {
        r"/ideas": "/ideas",
        r"/ideas/observables": "/ideas/observables",
        r"/ideas/history": "/ideas/history",
        r"/ideas/[A-Za-z0-9_-]+": "/ideas/{idea_id}",
        r"/ideas/[A-Za-z0-9_-]+/tracking": "/ideas/{idea_id}/tracking",
        r"/macro/series/[A-Za-z0-9_.:-]+/history": "/macro/series/{series_id}/history",
        r"/ideas/[A-Za-z0-9_-]+/signal": "/ideas/{idea_id}/signal",
    }
    for method, pattern in ALLOWED_ROUTES:
        assert (method, samples[pattern]) in app_routes, pattern
        assert method == "GET" or samples[pattern] == "/ideas/{idea_id}/signal"
        assert not re.search(r"order|trade|execut|account|broker|wallet|portfolio|rebalanc", pattern)
    for method, path in [("DELETE", "/ideas/abc"), ("POST", "/ideas/abc/activate"), ("PATCH", "/ideas/abc"),
                         ("POST", "/research/strategy-lab/scripts/s1/runs"), ("GET", "/portfolio/history"), ("DELETE", "/ideas/abc/signal")]:
        assert not route_allowed(method, path)
    with pytest.raises(RouteNotAllowedError):
        gamma._request("POST", "/ideas/abc/activate")


def test_rows_from_lists_and_frames_and_the_token_requirement(monkeypatch):
    rows, columns = signal_rows([{"date": "2026-01-02", "AAPL": 0.5, "MSFT": None}])
    assert rows == [{"date": "2026-01-02", "AAPL": "0.5", "MSFT": ""}] and columns == ["AAPL", "MSFT"]
    frame = pd.DataFrame({"day": pd.to_datetime(["2026-01-02"]), "SPY": [1.0]})
    assert signal_rows(frame, date_column="day")[0] == [{"day": "2026-01-02", "SPY": "1.0"}]
    with pytest.raises(TypeError):
        signal_rows({"date": "2026-01-02"})
    monkeypatch.delenv("GAMMA_SESSION_TOKEN", raising=False)
    with pytest.raises(GammaClientError, match="GAMMA_SESSION_TOKEN"):
        Gamma()


def test_macro_series_keep_their_provenance():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Gamma-Session"] == TOKEN and request.method == "GET"
        return httpx.Response(200, json={
            "series_id": "us-10y-yield", "title": "Headline CPI YoY", "unit": "%", "points": [
                {"timestamp": "2026-09-01T00:00:00", "value": 3.9, "source_provider": "fred", "retrieved_at": "2026-11-01T00:00:00", "origin": "macro_service"},
                {"timestamp": "2026-10-01T00:00:00", "value": 4.08, "source_provider": "fred", "retrieved_at": "2026-11-01T00:00:00", "origin": "macro_service"},
            ], "source_provider": "fred", "origin": "macro_service",
        })

    http = httpx.Client(base_url="http://gamma.local", transport=httpx.MockTransport(handler))
    frame = Gamma(token=TOKEN, http=http).macro("us-10y-yield")
    assert list(frame["value"]) == [3.9, 4.08] and set(frame["source_provider"]) == {"fred"}
    assert frame.attrs["title"] == "Headline CPI YoY"
