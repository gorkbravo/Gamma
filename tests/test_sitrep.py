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
