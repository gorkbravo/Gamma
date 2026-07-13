from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.application.sitrep_service import (
    SITREP_SECTIONS,
    SitrepService,
    SitrepWorkspaceRequest,
)


def _build_client(tmp_path) -> TestClient:
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    return TestClient(create_app(runtime))


def test_sitrep_workspace_returns_all_sections(tmp_path):
    client = _build_client(tmp_path)
    try:
        response = client.get("/sitrep/workspace")

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_provider"] == "gamma_sitrep"
        assert payload["sections"] == list(SITREP_SECTIONS)
        assert payload["section_warnings"] == []

        assert payload["equities_overview"]["universe_id"] == "broad_us_market"
        assert payload["indices_overview"]["universe_id"] == "global_indices"
        assert payload["macro_snapshot"]["region"] == "US"
        assert payload["macro_snapshot"]["timeframe"] == "3M"
        assert payload["commodities"]["mode"] == "overview"
        assert payload["prediction_markets"]["markets"]
        assert len(payload["prediction_markets"]["markets"]) <= 12
        assert payload["news"]["items"]
    finally:
        client.app.state.runtime.shutdown()


def test_sitrep_workspace_supports_section_subsets(tmp_path):
    client = _build_client(tmp_path)
    try:
        response = client.get("/sitrep/workspace", params={"sections": "news, macro"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["sections"] == ["macro", "news"]
        assert payload["macro_snapshot"] is not None
        assert payload["news"] is not None
        assert payload["equities_overview"] is None
        assert payload["indices_overview"] is None
        assert payload["commodities"] is None
        assert payload["prediction_markets"] is None
    finally:
        client.app.state.runtime.shutdown()


def test_sitrep_service_degrades_failing_sections_into_warnings():
    class _FailingMacroService:
        def get_snapshot(self, request):
            raise RuntimeError("macro provider exploded")

    class _NewsFeed:
        def latest(self, *, limit=25, force_refresh=False):
            from src.models.news import NewsEventFeed
            from src.models.provenance import FreshnessLabel
            from src.utils.time import now_utc

            return NewsEventFeed(
                items=[],
                source_provider="sample_news",
                retrieved_at=now_utc(),
                origin="test",
                freshness_label=FreshnessLabel.MOCKED,
                warnings=[],
                transformation_note=None,
            )

    service = SitrepService(
        research_service=None,  # type: ignore[arg-type] - sections not requested
        macro_service=_FailingMacroService(),  # type: ignore[arg-type]
        commodities_service=None,  # type: ignore[arg-type]
        prediction_market_service=None,  # type: ignore[arg-type]
        news_service=_NewsFeed(),  # type: ignore[arg-type]
    )

    result = service.get_workspace(SitrepWorkspaceRequest(sections=("macro", "news")))

    assert result.macro_snapshot is None
    assert result.news is not None
    assert result.sections == ("macro", "news")
    assert any("macro" in warning and "exploded" in warning for warning in result.section_warnings)


def test_sitrep_unknown_sections_fall_back_to_all():
    normalized = SitrepWorkspaceRequest(sections=("bogus",))
    from src.application.sitrep_service import _normalize_sections

    assert _normalize_sections(normalized.sections) == set(SITREP_SECTIONS)


def test_sitrep_follow_up_crud_roundtrip(tmp_path):
    client = _build_client(tmp_path)
    try:
        created = client.post(
            "/sitrep/follow-ups",
            json={
                "row_id": "divergence-1",
                "title": "Rates vs equities divergence",
                "source": "Macro",
                "tone": "warning",
                "detail": "Score 2.4 / high",
                "meta": "score 2.4 / high",
                "handoff": {"targetTab": "macro", "targetMode": "cross_asset"},
            },
        )
        assert created.status_code == 200
        item = created.json()
        assert item["status"] == "open"
        assert item["note"] == ""
        assert item["handoff"] == {"targetTab": "macro", "targetMode": "cross_asset"}

        # Re-creating the same row id is idempotent, not a duplicate.
        duplicate = client.post(
            "/sitrep/follow-ups",
            json={"row_id": "divergence-1", "title": "Rates vs equities divergence"},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == item["id"]

        listed = client.get("/sitrep/follow-ups")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()["items"]] == [item["id"]]

        noted = client.patch(
            f"/sitrep/follow-ups/{item['id']}",
            json={"note": "Check the 2s10s reaction after CPI."},
        )
        assert noted.status_code == 200
        assert noted.json()["note"] == "Check the 2s10s reaction after CPI."
        assert noted.json()["status"] == "open"

        resolved = client.patch(f"/sitrep/follow-ups/{item['id']}", json={"status": "resolved"})
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["resolved_at"] is not None
        assert resolved.json()["note"] == "Check the 2s10s reaction after CPI."

        reopened = client.patch(f"/sitrep/follow-ups/{item['id']}", json={"status": "open"})
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "open"
        assert reopened.json()["resolved_at"] is None

        deleted = client.delete(f"/sitrep/follow-ups/{item['id']}")
        assert deleted.status_code == 200
        assert deleted.json()["success"] is True
        assert client.get("/sitrep/follow-ups").json()["items"] == []
    finally:
        client.app.state.runtime.shutdown()


def test_sitrep_follow_up_validation_errors(tmp_path):
    client = _build_client(tmp_path)
    try:
        missing_title = client.post("/sitrep/follow-ups", json={"row_id": "x", "title": " "})
        assert missing_title.status_code == 422

        created = client.post("/sitrep/follow-ups", json={"row_id": "x", "title": "Row"})
        assert created.status_code == 200
        item_id = created.json()["id"]

        bad_status = client.patch(f"/sitrep/follow-ups/{item_id}", json={"status": "done"})
        assert bad_status.status_code == 422

        missing = client.patch("/sitrep/follow-ups/does-not-exist", json={"note": "n"})
        assert missing.status_code == 404
    finally:
        client.app.state.runtime.shutdown()


def test_sitrep_follow_up_store_persists_across_instances(tmp_path):
    from src.models.sitrep import SitrepFollowUpCreateRequest
    from src.services.sitrep_follow_up_store import SitrepFollowUpStore

    store = SitrepFollowUpStore(base_dir=tmp_path / "sitrep")
    store.create_item(SitrepFollowUpCreateRequest(row_id="r1", title="Persisted row"))

    reloaded = SitrepFollowUpStore(base_dir=tmp_path / "sitrep")
    items = reloaded.list_items()
    assert len(items) == 1
    assert items[0].row_id == "r1"
    assert items[0].status == "open"
