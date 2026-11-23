"""Workstream 12 - Ideas, checkpoint I4c: attaching books from Strategy Lab and Risk.

The snapshot is recomputed from the attached legs with the same services as an
idea's own test and risk (demo sample closes, injected clock, no network).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture()
def demo_client(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
    clock = _Clock(datetime(2026, 1, 20, 14, 0))
    runtime.idea_service._clock = clock
    runtime.idea_analysis._clock = clock
    with TestClient(create_app(runtime)) as client:
        yield client


BOOK = {
    "source": "strategy_lab",
    "label": "Megacap pair",
    "benchmark": "SPY",
    "lookback_days": 252,
    "legs": [
        {"entity_type": "equity", "symbol": "AAPL", "weight": 1, "label": "Apple"},
        {"entity_type": "equity", "symbol": "MSFT", "weight": -1, "label": "Microsoft"},
    ],
}


def _idea(client, legs=None):
    response = client.post("/ideas", json={
        "title": "Attached books", "thesis": "Books built elsewhere, frozen here.", "stance": "long",
        "legs": legs if legs is not None else [{"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}}],
    })
    assert response.status_code == 200
    return response.json()["idea_id"]


def test_a_strategy_lab_book_attaches_as_a_recomputed_test_snapshot(demo_client):
    idea_id = _idea(demo_client)
    response = demo_client.post(f"/ideas/{idea_id}/test", json=BOOK)
    assert response.status_code == 200, response.text
    idea = response.json()
    snapshot = idea["tests"][-1]
    assert snapshot["source"] == "strategy_lab"
    assert snapshot["source_ids"]["attached_from"] == "Strategy Lab" and snapshot["source_ids"]["attached_label"] == "Megacap pair"
    assert [(leg["key"], leg["weight"]) for leg in snapshot["legs"]] == [("equity:AAPL", 0.5), ("equity:MSFT", -0.5)]
    assert snapshot["lookback_days"] == 252 and snapshot["observations"] > 60
    assert snapshot["sample"] == "in_sample" and snapshot["costs_included"] is False
    # Un libro distinto de las patas de la idea queda marcado como tal, y cuenta como prueba.
    assert snapshot["stale_reason"] == "Attached from Strategy Lab: a different book from the idea's legs."
    assert snapshot["trial_count"] == 1 and idea["trial_count"] == 1
    entry = idea["journal"][-1]
    assert entry["kind"] == "test_refreshed" and entry["body"].startswith("Attached a Strategy Lab backtest of Megacap pair")
    # Las patas de la idea no cambian: adjuntar un resultado no es editarla.
    assert [leg["entity"]["normalized_id"] for leg in idea["legs"]] == ["AAPL"]


def test_a_risk_book_attaches_as_a_risk_snapshot(demo_client):
    idea_id = _idea(demo_client)
    response = demo_client.post(f"/ideas/{idea_id}/risk", json={**BOOK, "source": "risk_tab", "label": "Risk research book"})
    assert response.status_code == 200, response.text
    snapshot = response.json()["risks"][-1]
    assert snapshot["source"] == "risk_tab" and snapshot["source_ids"]["attached_from"] == "Risk"
    assert snapshot["metrics"]["historical_var"] is not None
    assert snapshot["stale_reason"] == "Attached from Risk: a different book from the idea's legs."
    assert response.json()["journal"][-1]["body"].startswith("Attached a Risk risk run of Risk research book")


def test_an_attached_book_matching_the_legs_is_fresh_and_an_empty_body_runs_the_legs(demo_client):
    idea_id = _idea(demo_client, legs=[
        {"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}, "weight": 1},
        {"entity": {"entity_type": "equity", "label": "Microsoft", "normalized_id": "MSFT"}, "weight": -1},
    ])
    attached = demo_client.post(f"/ideas/{idea_id}/test", json=BOOK).json()
    # El reloj de la respuesta es el real, así que solo puede quedar el motivo por antigüedad, nunca "otro libro".
    assert "different book" not in (attached["tests"][-1]["stale_reason"] or "")
    # El mismo libro desde la idea no es una prueba nueva.
    own = demo_client.post(f"/ideas/{idea_id}/test", json={}).json()
    assert own["tests"][-1]["source"] == "idea_legs" and own["trial_count"] == 1


def test_attached_books_are_validated(demo_client):
    idea_id = _idea(demo_client)
    bad_type = demo_client.post(f"/ideas/{idea_id}/test", json={**BOOK, "legs": [{"entity_type": "macro", "symbol": "CPI", "weight": 1}]})
    assert bad_type.status_code == 422
    flat = demo_client.post(f"/ideas/{idea_id}/test", json={**BOOK, "legs": [{"entity_type": "equity", "symbol": "AAPL", "weight": 0}]})
    assert flat.status_code == 422 and "no exposure" in flat.json()["detail"]
    unknown = demo_client.post(f"/ideas/{idea_id}/test", json={**BOOK, "source": "portfolio"})
    assert unknown.status_code == 422
    assert demo_client.get(f"/ideas/{idea_id}").json()["tests"] == []


def test_script_runs_are_listed_for_the_signal_picker(demo_client):
    response = demo_client.get("/research/strategy-lab/scripts/missing/runs")
    assert response.status_code == 404
