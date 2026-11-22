"""Workstream 12 - Ideas, checkpoint I3c: test and risk snapshots of an idea's legs.

The route tests run on the demo runtime (sample closes, no TWS, no network);
the unit tests inject fakes for Strategy Lab and the crypto prices.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.idea_analysis import IdeaAnalysisService
from src.application.idea_service import IdeaCreateRequest, IdeaPatchRequest, IdeaService
from src.application.idea_tracking import LegCloses, SessionClose
from src.application.runtime import build_runtime
from src.models.handoff import HandoffEntity
from src.models.ideas import (
    IDEA_SCHEMA_VERSION,
    IDEA_SNAPSHOTS_MAX,
    IdeaLeg,
    IdeaLifecycleError,
    IdeaTestSnapshot,
    IdeaValidationError,
    freeze_tracking_legs,
    snapshot_staleness,
)
from src.services.idea_store import IdeaStore


def _leg(symbol: str, weight: float | None, entity_type: str = "equity") -> IdeaLeg:
    return IdeaLeg(entity=HandoffEntity(entity_type=entity_type, label=symbol, normalized_id=symbol), weight=weight)


# ---------------------------------------------------------------------------
# Routes against the demo runtime
# ---------------------------------------------------------------------------


@pytest.fixture()
def demo_client(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
    with TestClient(create_app(runtime)) as client:
        client.runtime = runtime  # type: ignore[attr-defined]
        yield client


def _create_pair(client) -> str:
    return client.post(
        "/ideas",
        json={
            "title": "AAPL over MSFT",
            "thesis": "Apple holds up better.",
            "stance": "relative",
            "legs": [
                {"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}, "weight": 1},
                {"entity": {"entity_type": "equity", "label": "Microsoft", "normalized_id": "MSFT"}, "weight": -1},
            ],
        },
    ).json()["idea_id"]


def test_a_backtest_snapshot_keeps_its_window_metrics_and_provenance(demo_client):
    idea_id = _create_pair(demo_client)
    response = demo_client.post(f"/ideas/{idea_id}/test")
    assert response.status_code == 200
    body = response.json()
    test = body["tests"][-1]
    assert test["window_start"] == "2024-12-24" and test["window_end"] == "2026-01-27"
    assert test["observations"] > 200 and test["lookback_days"] == 756
    assert test["costs_included"] is False and test["sample"] == "in_sample"
    assert [leg["weight"] for leg in test["legs"]] == [0.5, -0.5]
    assert test["source_ids"]["composition"] == "Idea: AAPL over MSFT"
    assert test["provenance"]["source_provider"] == "gamma_strategy_lab"
    assert set(test["metrics"]) >= {"total_return", "annual_volatility", "sharpe_ratio", "max_drawdown", "benchmark_total_return"}
    assert test["metrics"]["max_drawdown"] < 0
    assert set(test["leg_contributions"]) == {"Apple", "Microsoft"}
    assert 2 < len(test["equity_curve"]) <= 260 and len(test["benchmark_curve"]) > 2
    assert test["stale_reason"] is None
    assert not any("read-only research runs" in item for item in test["warnings"]), "boilerplate is not a data warning"
    entry = body["journal"][-1]
    assert entry["kind"] == "test_refreshed" and "In-sample, no costs." in entry["body"]


def test_a_risk_snapshot_keeps_var_es_and_the_stress_replay(demo_client):
    idea_id = _create_pair(demo_client)
    response = demo_client.post(f"/ideas/{idea_id}/risk")
    assert response.status_code == 200
    body = response.json()
    risk = body["risks"][-1]
    assert risk["alpha"] == 0.95 and risk["horizon_days"] == 1 and risk["lookback_days"] == 252
    metrics = risk["metrics"]
    # Cuotas del libro, no importes: no dependen de un nocional.
    assert 0 < metrics["historical_var"] < 0.2 and metrics["historical_es"] >= metrics["historical_var"]
    assert metrics["parametric_var"] > 0 and metrics["annual_volatility"] > 0
    statuses = {item["episode_id"]: item["status"] for item in risk["episodes"]}
    assert statuses["gfc_2007_2009"] == "unavailable", "the demo sample does not reach 2008"
    priced = [item for item in risk["episodes"] if item["status"] != "unavailable"]
    assert priced and risk["worst_episode_id"] == min(priced, key=lambda item: item["book_return"])["episode_id"]
    assert body["journal"][-1]["kind"] == "risk_refreshed"
    assert "historical VaR -" in body["journal"][-1]["body"], "a loss is never written as a gain"

    markdown = demo_client.get(f"/ideas/{idea_id}/export?format=md").text
    assert "## Test and risk snapshots" in markdown and "Worst replayed episode" in markdown
    demo_client.post(f"/ideas/{idea_id}/test")
    markdown = demo_client.get(f"/ideas/{idea_id}/export?format=md").text
    assert "In-sample only, no costs" in markdown
    exported = json.loads(demo_client.get(f"/ideas/{idea_id}/export?format=json").text)
    assert len(exported["idea"]["risks"]) == 1 and len(exported["idea"]["tests"]) == 1


def test_snapshots_go_stale_when_the_legs_change(demo_client):
    idea_id = _create_pair(demo_client)
    demo_client.post(f"/ideas/{idea_id}/test")
    patched = demo_client.patch(
        f"/ideas/{idea_id}",
        json={"legs": [{"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}, "weight": 1}]},
    ).json()
    assert patched["tests"][-1]["stale_reason"] == "The legs or weights changed after this run."


def test_runs_refuse_ideas_that_cannot_be_priced(demo_client):
    legless = demo_client.post("/ideas", json={"title": "No legs", "thesis": "x"}).json()["idea_id"]
    response = demo_client.post(f"/ideas/{legless}/test")
    assert response.status_code == 422 and "Add legs" in response.json()["detail"]
    commodity = demo_client.post(
        "/ideas",
        json={
            "title": "Brent",
            "thesis": "x",
            "stance": "long",
            "legs": [{"entity": {"entity_type": "commodity", "label": "Brent", "normalized_id": "BRENT"}, "weight": 1}],
        },
    ).json()["idea_id"]
    response = demo_client.post(f"/ideas/{commodity}/risk")
    assert response.status_code == 422 and "commodity legs have no price source" in response.json()["detail"]
    unknown = demo_client.post(
        "/ideas",
        json={
            "title": "Unknown",
            "thesis": "x",
            "stance": "long",
            "legs": [{"entity": {"entity_type": "equity", "label": "Nope", "normalized_id": "NOPE"}, "weight": 1}],
        },
    ).json()["idea_id"]
    response = demo_client.post(f"/ideas/{unknown}/test")
    assert response.status_code == 422 and "Strategy Lab could not compose the legs" in response.json()["detail"]
    assert demo_client.post("/ideas/missing/test").status_code == 404


# ---------------------------------------------------------------------------
# Unit tests with fakes
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class _FakeResearch:
    def __init__(self) -> None:
        self.requests = []

    def compose_strategy_lab_portfolio(self, request):
        self.requests.append(request)
        index = pd.date_range("2026-01-05", periods=5, freq="B")
        curve = pd.Series([1.0, 1.01, 1.02, 1.0, 1.03], index=index)
        return SimpleNamespace(
            name=request.name,
            origin="fake.compose",
            source_provider="fake_lab",
            retrieved_at=datetime(2026, 1, 10, 12, 0),
            transformation_note=None,
            warnings=["Strategy Lab compositions are read-only research runs.", "Short history."],
            metrics=SimpleNamespace(
                total_return=0.03,
                annual_return=0.5,
                annual_volatility=0.2,
                sharpe_ratio=1.1,
                sortino_ratio=1.5,
                max_drawdown=-0.02,
                observation_count=5,
                start_date=datetime(2026, 1, 5),
                end_date=datetime(2026, 1, 9),
                benchmark_beta=0.4,
                benchmark_correlation=0.3,
            ),
            leg_contributions={"AAPL": 0.02, "BTC": 0.01},
            equity_curve=curve,
            benchmark_equity_curve=curve * 0.99,
        )


class _FakeCrypto:
    def leg_closes(self, leg, *, since, now):
        return LegCloses(closes=tuple(SessionClose(session=date(2026, 1, day), close_at=datetime(2026, 1, day + 1), price=90_000.0 + day) for day in range(1, 8)))


def _analysis(tmp_path):
    clock = _Clock(datetime(2026, 1, 10, 12, 0))
    service = IdeaService(IdeaStore(tmp_path / "ideas"), clock=clock)
    research = _FakeResearch()
    analysis = IdeaAnalysisService(
        service,
        research_service_factory=lambda: research,
        risk_service=None,
        research_provider=None,
        crypto_prices=_FakeCrypto(),
        clock=clock,
    )
    return service, analysis, research, clock


def test_crypto_legs_reach_strategy_lab_as_inline_daily_closes(tmp_path):
    service, analysis, research, _ = _analysis(tmp_path)
    idea = service.create_idea(
        IdeaCreateRequest(title="Tech and BTC", thesis="x", stance="long", legs=(_leg("AAPL", None), _leg("BTC", None, entity_type="crypto")))
    )
    updated = analysis.run_test(idea.idea_id)
    request = research.requests[-1]
    stock, coin = request.legs
    assert (stock.identifier, stock.asset_class, stock.weight, stock.return_points) == ("AAPL", "equity", 0.5, [])
    assert coin.asset_class == "crypto" and coin.value_kind == "level" and len(coin.return_points) == 7
    assert coin.return_points[0].timestamp == "2026-01-01"
    test = updated.tests[-1]
    assert test.warnings == ("Short history.",)
    assert test.metrics["benchmark_total_return"] == pytest.approx(0.03)
    assert test.metrics["excess_total_return"] == pytest.approx(0.0)


def test_snapshots_are_capped_staleness_ages_and_closed_ideas_refuse(tmp_path):
    service, analysis, _, clock = _analysis(tmp_path)
    idea = service.create_idea(IdeaCreateRequest(title="AAPL", thesis="x", stance="long", legs=(_leg("AAPL", 1.0),)))
    for _ in range(IDEA_SNAPSHOTS_MAX + 1):
        latest = analysis.run_test(idea.idea_id)
    assert len(latest.tests) == IDEA_SNAPSHOTS_MAX
    assert sum(1 for entry in latest.journal if entry.kind == "test_refreshed") == IDEA_SNAPSHOTS_MAX + 1, "the journal keeps every run"
    snapshot = latest.tests[-1]
    assert snapshot_staleness(snapshot, latest, snapshot.created_at + timedelta(days=1)) is None
    assert snapshot_staleness(snapshot, latest, snapshot.created_at + timedelta(days=8)) == "Run 8 days ago."
    rescaled = service.update_idea(idea.idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 3.0),)))
    assert snapshot_staleness(snapshot, rescaled, snapshot.created_at) is None, "scaling a single leg keeps the same book"

    clock.now = datetime(2026, 1, 12, 12, 0)
    service.activate(idea.idea_id)
    service.archive(idea.idea_id)
    with pytest.raises(IdeaLifecycleError):
        analysis.run_test(idea.idea_id)


def test_snapshot_records_validate_and_round_trip():
    legs, _ = freeze_tracking_legs((_leg("AAPL", 1.0),), "long")
    snapshot = IdeaTestSnapshot(
        snapshot_id="s1",
        idea_id="i1",
        created_at=datetime(2026, 1, 10),
        legs=legs,
        benchmark="spy",
        lookback_days=756,
        metrics={"total_return": 0.1, "sharpe_ratio": float("nan")},
        equity_curve=tuple((f"2026-01-{day:02d}", 1.0 + day / 100) for day in range(1, 31)) * 10,
    )
    assert snapshot.benchmark == "SPY" and snapshot.metrics["sharpe_ratio"] is None
    assert len(snapshot.equity_curve) <= 260
    assert IdeaTestSnapshot.from_dict(snapshot.to_dict()).to_dict() == snapshot.to_dict()
    with pytest.raises(IdeaValidationError):
        replace(snapshot, legs=())
    with pytest.raises(IdeaValidationError):
        replace(snapshot, sample="out_of_sample")


def test_v4_files_migrate_with_no_snapshots(tmp_path):
    service, _, _, _ = _analysis(tmp_path)
    idea = service.create_idea(IdeaCreateRequest(title="Old", thesis="x"))
    path = tmp_path / "ideas" / "items" / f"{idea.idea_id}.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 4
    legacy.pop("tests")
    legacy.pop("risks")
    for key in ("evidence", "journal", "criteria", "reviews"):
        for item in legacy[key]:
            item["schema_version"] = 4
    path.write_text(json.dumps(legacy), encoding="utf-8")
    (tmp_path / "ideas" / "index.json").unlink()
    migrated = IdeaStore(tmp_path / "ideas").require(idea.idea_id)
    assert migrated.schema_version == IDEA_SCHEMA_VERSION
    assert migrated.tests == () and migrated.risks == ()


def test_a_source_failure_is_a_502_with_the_reason(demo_client):
    idea_id = _create_pair(demo_client)

    class Broken:
        def compose_strategy_lab_portfolio(self, request):
            raise TimeoutError("yfinance timed out")

    demo_client.runtime.idea_analysis._research_service = lambda: Broken()
    response = demo_client.post(f"/ideas/{idea_id}/test")
    assert response.status_code == 502
    assert response.json()["detail"] == "Strategy Lab could not read the prices: yfinance timed out"
    assert demo_client.get(f"/ideas/{idea_id}").json()["tests"] == []
