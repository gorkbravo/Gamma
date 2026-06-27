from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from ib_insync import Contract

from src.api.main import create_app
from src.application.commodities_service import (
    CommoditiesService,
    CommodityWorkspaceRequest,
    _provider_sign_split_warnings,
)
from src.application.runtime import build_runtime
from src.models.commodities import (
    CommodityCoverageMetadata,
    CommodityInstrument,
    CommodityMarketSummary,
    CommodityPriceBasis,
)
from src.services.cache import CacheService
from src.services.commodities_adapters import (
    EIA_INVENTORY_SERIES,
    EIA_PRICE_SERIES,
    IBKR_FUTURES_ROOTS,
    EiaCommoditiesDataProvider,
    IbkrFutureRootConfig,
    IbkrCommoditiesDataProvider,
    SampleCommoditiesDataProvider,
)
from src.services.market_data import QuoteSnapshot


def test_commodity_coverage_rejects_unknown_status():
    with pytest.raises(ValueError, match="Unsupported commodities coverage status"):
        CommodityCoverageMetadata(
            coverage_status="tradable",
            provider_id="bad",
            provider_label="Bad",
            freshness_label="bad",
        )


def test_sample_commodities_workspace_contains_research_analytics():
    service = CommoditiesService(provider=SampleCommoditiesDataProvider())

    workspace = service.get_workspace(CommodityWorkspaceRequest(mode="energy", selected_instrument_id="CL"))

    assert workspace.mode == "energy"
    assert workspace.selected_instrument_id == "wti"
    assert workspace.coverage.coverage_status == "sample"
    assert workspace.coverage.supports_prices is True
    assert workspace.coverage.supports_curves is True
    assert workspace.coverage.supports_inventories is True
    assert {instrument.family for instrument in workspace.instruments} == {"energy", "metals"}
    assert len(workspace.market_summaries) == 16
    assert len(workspace.price_histories) == 16
    assert len(workspace.curves) == 11
    assert len(workspace.spreads) >= 6
    assert len(workspace.inventories) >= 6
    assert len(workspace.events) >= 2
    assert len(workspace.cross_domain_links) >= 3
    assert any("read-only research" in warning for warning in workspace.warnings)
    assert workspace.overview is not None
    assert workspace.overview.market_breadth.total_markets == 16
    assert workspace.overview.market_breadth.counts_by_family == {"energy": 5, "metals": 11}
    assert workspace.overview.market_breadth.backwardation_count >= 1
    assert workspace.overview.market_breadth.contango_count >= 1
    assert len(workspace.overview.matrix_rows) == 16
    assert workspace.price_reconciliations
    sample_wti_reconciliation = next(row for row in workspace.price_reconciliations if row.instrument_id == "wti")
    assert sample_wti_reconciliation.status == "aligned"
    assert sample_wti_reconciliation.headline is not None
    assert sample_wti_reconciliation.headline.basis_type == "sample_generated"
    nickel_row = next(row for row in workspace.overview.matrix_rows if row.instrument_id == "nickel")
    assert nickel_row.curve_state == "unavailable"
    assert nickel_row.latest_price is not None
    assert workspace.overview.scatter is not None
    assert workspace.overview.scatter.x_methodology_label == "Loaded-history momentum (%)"
    assert workspace.overview.scatter.points
    assert any("not a fixed 30D" in caveat for caveat in workspace.overview.scatter.caveats)
    assert workspace.overview.rankings is not None
    assert workspace.overview.rankings.strongest_backwardation
    assert workspace.overview.rankings.deepest_contango
    assert workspace.overview.rankings.inventory_outliers
    assert workspace.overview.rankings.spread_z_score_outliers
    assert workspace.overview.rankings.largest_movers
    assert any("Volatility z-score" in caveat for caveat in workspace.overview.rankings.caveats)
    assert workspace.overview.term_structure is not None
    assert workspace.overview.term_structure.current_curve is not None
    assert workspace.overview.term_structure.previous_curve_snapshots == []
    assert any("Historical curve stacks require" in caveat for caveat in workspace.overview.term_structure.caveats)

    wti_curve = next(curve for curve in workspace.curves if curve.instrument_id == "wti")
    assert wti_curve.shape_label == "backwardation"
    assert wti_curve.front_spread is not None
    assert wti_curve.m1_m6_spread is not None
    assert wti_curve.roll_yield_proxy_pct is not None
    assert any("Roll-yield proxy" in warning for warning in wti_curve.warnings)

    crude_inventory = next(
        series for series in workspace.inventories if series.metadata.series_id == "us-commercial-crude-stocks"
    )
    assert crude_inventory.latest_value is not None
    assert crude_inventory.latest_change is not None
    assert crude_inventory.seasonal_percentile is not None
    assert crude_inventory.interpretation

    rich_spread = next(spread for spread in workspace.spreads if spread.definition.spread_id == "gold-silver-ratio")
    assert rich_spread.value is not None
    assert rich_spread.z_score is not None
    assert rich_spread.percentile is not None
    assert rich_spread.history

    composite_crack = next(spread for spread in workspace.spreads if spread.definition.spread_id == "three-two-one-crack")
    assert composite_crack.value is not None
    assert composite_crack.definition.spread_type == "refining_margin"

    copper_aluminum = next(spread for spread in workspace.spreads if spread.definition.spread_id == "copper-aluminum-spread")
    assert copper_aluminum.value is not None
    assert copper_aluminum.definition.unit == "USD/mt"


def test_commodity_reconciliation_flags_material_basis_conflict():
    class ConflictingProvider:
        provider_id = "fixture"
        provider_label = "Fixture Conflicting Commodities"

        def get_snapshot(self, *, force_refresh=False, selected_instrument_id=None):
            del force_refresh
            del selected_instrument_id
            snapshot = SampleCommoditiesDataProvider().get_snapshot()
            wti_history = next(history for history in snapshot.price_histories if history.instrument_id == "wti")
            fred_points = [
                replace(point, value=value, source_provider="fred", origin="fred.series.observations:DCOILWTICO")
                for point, value in zip(wti_history.points[-2:], [94.0, 95.0])
            ]
            price_histories = [
                replace(
                    history,
                    label="WTI FRED spot proxy",
                    source_provider="fred",
                    origin="fred.series.observations:DCOILWTICO",
                    transformation_note="FRED spot/proxy series for conflict testing.",
                    points=fred_points,
                )
                if history.instrument_id == "wti"
                else history
                for history in snapshot.price_histories
            ]
            wti_curve = next(curve for curve in snapshot.curve_snapshots if curve.instrument_id == "wti")
            front_contract = replace(wti_curve.nodes[0].contract, source_provider="ibkr")
            curve_nodes = [
                replace(
                    wti_curve.nodes[0],
                    contract=front_contract,
                    price=84.0,
                    previous_price=86.0,
                    change=-2.0,
                    source_provider="ibkr",
                    origin="ibkr.reqMktData:fixture",
                ),
                *wti_curve.nodes[1:],
            ]
            curve_snapshots = [
                replace(
                    curve,
                    nodes=curve_nodes,
                    source_provider="ibkr",
                    origin="ibkr.commodities.curve:CL:NYMEX",
                )
                if curve.instrument_id == "wti"
                else curve
                for curve in snapshot.curve_snapshots
            ]
            return replace(
                snapshot,
                price_histories=price_histories,
                curve_snapshots=curve_snapshots,
                source_provider="ibkr",
                transformation_note="Fixture mixes FRED spot proxy history with IBKR front futures curve.",
            )

    workspace = CommoditiesService(provider=ConflictingProvider()).get_workspace(
        CommodityWorkspaceRequest(mode="energy", selected_instrument_id="wti")
    )

    wti_summary = next(summary for summary in workspace.market_summaries if summary.instrument.instrument_id == "wti")
    assert wti_summary.latest_price == 84.0
    assert wti_summary.latest_change_pct is None
    assert wti_summary.quote_basis is not None
    assert wti_summary.quote_basis.basis_type == "front_future"
    assert wti_summary.quote_basis.provider == "ibkr"
    assert any("prior close" in warning.lower() for warning in wti_summary.warnings)
    reconciliation = next(row for row in workspace.price_reconciliations if row.instrument_id == "wti")
    assert reconciliation.status == "conflict"
    assert reconciliation.headline is not None
    assert reconciliation.headline.contract_month
    assert any("basis conflict" in warning.lower() for warning in reconciliation.warnings)
    assert any("basis conflict" in warning.lower() for warning in workspace.warnings)


def test_commodity_provider_sign_split_guard_flags_uniform_ibkr_vs_fred_moves():
    def summary(
        instrument_id: str,
        symbol: str,
        provider: str,
        basis_type: str,
        change_pct: float,
    ) -> CommodityMarketSummary:
        instrument = CommodityInstrument(
            instrument_id=instrument_id,
            symbol=symbol,
            name=symbol,
            family="energy" if provider == "ibkr" else "metals",
            subgroup="fixture",
            quote_unit="USD",
        )
        basis = CommodityPriceBasis(
            basis_id=f"{instrument_id}:fixture",
            instrument_id=instrument_id,
            role="fixture",
            basis_type=basis_type,
            display_label=f"{provider} fixture",
            provider=provider,
            value=100.0,
            previous_value=100.0 / (1.0 + change_pct),
            change=100.0 - (100.0 / (1.0 + change_pct)),
            change_pct=change_pct,
        )
        return CommodityMarketSummary(
            instrument=instrument,
            latest_price=basis.value,
            latest_change=basis.change,
            latest_change_pct=basis.change_pct,
            quote_basis=basis,
        )

    warnings = _provider_sign_split_warnings(
        [
            summary("wti", "CL", "ibkr", "front_future", -0.012),
            summary("brent", "BZ", "ibkr", "front_future", -0.009),
            summary("gold", "GC", "fred", "fred_reference", 0.004),
            summary("silver", "SI", "fred", "fred_reference", 0.006),
        ]
    )

    assert any("Provider split warning" in warning for warning in warnings)


def test_ibkr_default_roots_cover_curve_capable_sample_commodities():
    snapshot = SampleCommoditiesDataProvider().get_snapshot()
    curve_capable_ids = {curve.instrument_id for curve in snapshot.curve_snapshots}
    configured_root_ids = {config.instrument_id for config in IBKR_FUTURES_ROOTS}

    assert curve_capable_ids <= configured_root_ids


def test_eia_provider_without_key_degrades_to_sample_with_warning():
    provider = EiaCommoditiesDataProvider(api_key="", reference_provider=SampleCommoditiesDataProvider())

    snapshot = provider.get_snapshot()

    assert snapshot.coverage.coverage_status == "sample"
    assert "EIA_API_KEY" in snapshot.coverage.credential_env_vars
    assert any("EIA_API_KEY is not configured" in warning for warning in snapshot.warnings)
    assert snapshot.instruments
    assert snapshot.price_histories
    assert snapshot.curve_snapshots

    workspace = CommoditiesService(provider=provider).get_workspace(CommodityWorkspaceRequest(mode="overview"))
    assert workspace.overview is not None
    assert workspace.overview.market_breadth.total_markets == len(workspace.market_summaries)
    assert workspace.overview.matrix_rows
    assert any("EIA_API_KEY is not configured" in warning for warning in workspace.warnings)
    assert any("Previous full curve snapshots" in caveat for caveat in workspace.overview.term_structure.caveats)


def test_eia_provider_enriches_energy_inventory_with_official_series():
    def fake_fetch_json(url: str, params: dict[str, object] | None):
        del params
        if any(config.series_id in url for config in EIA_PRICE_SERIES):
            return {
                "response": {
                    "data": [
                        {"period": "2026-01-03", "value": 2.95},
                        {"period": "2026-01-10", "value": 3.05},
                        {"period": "2026-01-17", "value": 3.15},
                    ]
                }
            }
        return {
            "response": {
                "data": [
                    {"period": "2026-01-03", "value": 420000},
                    {"period": "2026-01-10", "value": 421500},
                    {"period": "2026-01-17", "value": 419750},
                ]
            }
        }

    provider = EiaCommoditiesDataProvider(
        api_key="test-key",
        reference_provider=SampleCommoditiesDataProvider(),
        fetch_json=fake_fetch_json,
    )

    snapshot = provider.get_snapshot(force_refresh=True)

    assert snapshot.coverage.coverage_status == "official_partial"
    assert snapshot.source_provider == "eia"
    assert any("EIA" in caveat for caveat in snapshot.coverage.caveats)
    configured_labels = {config.label for config in EIA_INVENTORY_SERIES}
    assert "US Crude Oil Production" in configured_labels
    assert "US Crude Oil Imports" in configured_labels
    assert "US Refinery Utilization" in configured_labels
    assert "US Gasoline Product Supplied" in configured_labels
    configured_price_labels = {config.label for config in EIA_PRICE_SERIES}
    assert "RBOB Gasoline New York Harbor Spot" in configured_price_labels
    assert "No. 2 Heating Oil New York Harbor Spot" in configured_price_labels
    crude = next(series for series in snapshot.inventory_series if series.metadata.series_id == "us-commercial-crude-stocks")
    assert crude.source_provider == "eia"
    assert crude.metadata.provider_series_id == "PET.WCESTUS1.W"
    assert [point.value for point in crude.points] == [420.0, 421.5, 419.75]
    assert crude.points[-1].change == -1.75
    production = next(series for series in snapshot.inventory_series if series.metadata.series_id == "us-crude-oil-production")
    assert production.source_provider == "eia"
    assert production.metadata.category == "production"
    assert production.metadata.provider_series_id == "PET.WCRFPUS2.W"
    gasoline_history = next(history for history in snapshot.price_histories if history.instrument_id == "gasoline")
    assert gasoline_history.source_provider == "eia"
    assert gasoline_history.origin == "eia.seriesid:PET.EER_EPMRU_PF4_Y35NY_DPG.D"
    assert [point.value for point in gasoline_history.points] == [2.95, 3.05, 3.15]
    heating_oil_history = next(history for history in snapshot.price_histories if history.instrument_id == "heating_oil")
    assert heating_oil_history.source_provider == "eia"
    assert heating_oil_history.origin == "eia.seriesid:PET.EER_EPD2F_PF4_Y35NY_DPG.D"


class _FakeIb:
    def __init__(self, details):
        self.details = details
        self.requests: list[str] = []

    def reqContractDetails(self, contract):
        assert contract.secType == "FUT"
        symbol = str(getattr(contract, "symbol", "") or "")
        self.requests.append(symbol)
        if isinstance(self.details, dict):
            return self.details.get(symbol, [])
        return self.details


class _FakeIbkrClient:
    mock = False

    def __init__(self, details, connected: bool = True):
        self.ib = _FakeIb(details)
        self.connected = connected
        self.requests = self.ib.requests

    def is_connected(self):
        return self.connected

    def _run_ib(self, fn, *args, timeout=None, **kwargs):
        del timeout
        return fn(*args, **kwargs)


class _FakeMarketData:
    def __init__(self, prices: dict[int, float], delayed: set[int] | None = None):
        self.prices = prices
        self.delayed = delayed or set()

    def quote_key(self, contract):
        return f"conid_{contract.conId}"

    def fetch_snapshot_quotes_batch(self, contracts, timeout_seconds=None, *, batch_size=8):
        del timeout_seconds, batch_size
        return {
            self.quote_key(contract): QuoteSnapshot(
                self.prices.get(int(contract.conId)),
                "last",
                int(contract.conId) in self.delayed,
            )
            for contract in contracts
        }, []

    def fetch_history(self, contract, lookback_days):
        del contract, lookback_days
        return pd.Series(
            [76.0, 77.5, 79.25],
            index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"]),
        )


def _future_detail(con_id: int, month: str, local_symbol: str, symbol: str = "CL", exchange: str = "NYMEX"):
    contract = Contract(
        conId=con_id,
        symbol=symbol,
        secType="FUT",
        exchange=exchange,
        currency="USD",
        lastTradeDateOrContractMonth=month,
        localSymbol=local_symbol,
        tradingClass=symbol,
    )
    return SimpleNamespace(contract=contract, realExpirationDate=f"{month}20")


def test_ibkr_provider_builds_futures_curve_from_contract_details_and_quotes(tmp_path):
    details = [
        _future_detail(1003, "202610", "CLV6"),
        _future_detail(1001, "202608", "CLQ6"),
        _future_detail(1002, "202609", "CLU6"),
    ]
    provider = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient(details),
        market_data=_FakeMarketData({1001: 80.0, 1002: 79.2, 1003: 78.7}, delayed={1002}),
        cache=CacheService(tmp_path),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["wti"],
        contract_depth=3,
        history_days=3,
    )

    snapshot = provider.get_snapshot(force_refresh=True)

    assert snapshot.coverage.provider_id == "ibkr"
    assert snapshot.coverage.coverage_status == "partial"
    assert any("read-only FUT contract" in caveat for caveat in snapshot.coverage.caveats)
    assert any("Delayed quote nodes detected" in warning for warning in snapshot.warnings)

    wti_curve = next(curve for curve in snapshot.curve_snapshots if curve.instrument_id == "wti")
    assert wti_curve.source_provider == "ibkr"
    assert [node.contract.symbol for node in wti_curve.nodes] == ["CLQ6", "CLU6", "CLV6"]
    assert [node.price for node in wti_curve.nodes] == [80.0, 79.2, 78.7]
    assert [node.previous_price for node in wti_curve.nodes] == [None, None, None]
    assert [node.change for node in wti_curve.nodes] == [None, None, None]
    assert wti_curve.nodes[0].contract.contract_id == "ibkr:1001"
    assert wti_curve.nodes[0].contract.contract_month == "Aug 2026"
    assert any("Delayed IBKR quote" in warning for warning in wti_curve.warnings)

    wti_history = next(history for history in snapshot.price_histories if history.instrument_id == "wti")
    assert wti_history.source_provider == "ibkr"
    assert [point.value for point in wti_history.points] == [76.0, 77.5, 79.25]

    cached_history = provider._load_curve_history("wti")
    assert cached_history
    assert cached_history[-1]["nodes"][0]["contract_id"] == "ibkr:1001"

    service = CommoditiesService(provider=provider)
    workspace = service.get_workspace(
        CommodityWorkspaceRequest(mode="curves_spreads", selected_instrument_id="wti", force_refresh=True)
    )
    enriched_curve = next(curve for curve in workspace.curves if curve.instrument_id == "wti")
    assert enriched_curve.shape_label == "backwardation"
    assert enriched_curve.front_spread == 0.8
    wti_summary = next(summary for summary in workspace.market_summaries if summary.instrument.instrument_id == "wti")
    assert wti_summary.latest_price == 80.0
    assert wti_summary.latest_change == pytest.approx(0.75, abs=0.000001)
    assert wti_summary.latest_change_pct == pytest.approx(0.009464, abs=0.000001)
    assert wti_summary.quote_basis is not None
    assert wti_summary.quote_basis.previous_value == 79.25
    assert wti_summary.quote_basis.previous_source_timestamp is not None


def test_ibkr_provider_fetches_broad_shallow_curves_and_deepens_selected(tmp_path):
    details = {
        "CL": [
            _future_detail(2001, "202608", "CLQ6"),
            _future_detail(2002, "202609", "CLU6"),
            _future_detail(2003, "202610", "CLV6"),
            _future_detail(2004, "202611", "CLX6"),
        ],
        "GC": [
            _future_detail(3001, "202608", "GCQ6", symbol="GC", exchange="COMEX"),
            _future_detail(3002, "202609", "GCU6", symbol="GC", exchange="COMEX"),
            _future_detail(3003, "202610", "GCV6", symbol="GC", exchange="COMEX"),
            _future_detail(3004, "202611", "GCX6", symbol="GC", exchange="COMEX"),
        ],
    }
    fake_client = _FakeIbkrClient(details)
    provider = IbkrCommoditiesDataProvider(
        client=fake_client,
        market_data=_FakeMarketData(
            {
                2001: 80.0,
                2002: 79.0,
                2003: 78.5,
                2004: 78.1,
                3001: 2400.0,
                3002: 2404.0,
                3003: 2408.0,
                3004: 2412.0,
            }
        ),
        cache=CacheService(tmp_path),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["wti", "gold"],
        startup_instrument_ids=["wti"],
        selected_cache_seconds=300,
        contract_depth=4,
        breadth_contract_depth=2,
        history_days=0,
    )

    startup_snapshot = provider.get_snapshot(force_refresh=True)

    assert fake_client.requests == ["CL", "GC"]
    startup_wti_curve = next(curve for curve in startup_snapshot.curve_snapshots if curve.instrument_id == "wti")
    startup_gold_curve = next(curve for curve in startup_snapshot.curve_snapshots if curve.instrument_id == "gold")
    assert startup_wti_curve.source_provider == "ibkr"
    assert startup_gold_curve.source_provider == "ibkr"
    assert [node.price for node in startup_wti_curve.nodes] == [80.0, 79.0, 78.5, 78.1]
    assert [node.price for node in startup_gold_curve.nodes] == [2400.0, 2404.0]

    selected_snapshot = provider.get_snapshot(selected_instrument_id="gold")

    assert fake_client.requests == ["CL", "GC"]
    selected_gold_curve = next(curve for curve in selected_snapshot.curve_snapshots if curve.instrument_id == "gold")
    assert selected_gold_curve.source_provider == "ibkr"
    assert [node.price for node in selected_gold_curve.nodes] == [2400.0, 2404.0, 2408.0, 2412.0]

    cached_snapshot = provider.get_snapshot(selected_instrument_id="wti")

    assert fake_client.requests == ["CL", "GC"]
    selected_wti_curve = next(curve for curve in cached_snapshot.curve_snapshots if curve.instrument_id == "wti")
    cached_gold_curve = next(curve for curve in cached_snapshot.curve_snapshots if curve.instrument_id == "gold")
    assert selected_wti_curve.source_provider == "ibkr_cached"
    assert [node.price for node in selected_wti_curve.nodes] == [80.0, 79.0, 78.5, 78.1]
    assert [node.previous_price for node in selected_wti_curve.nodes] == [None, None, None, None]
    assert [node.change for node in selected_wti_curve.nodes] == [None, None, None, None]
    assert cached_gold_curve.source_provider == "ibkr_cached"
    assert any("Using cached IBKR curve for Gold" in warning for warning in cached_snapshot.warnings)


def test_ibkr_provider_defaults_to_shallow_breadth_for_all_configured_roots(tmp_path, monkeypatch):
    monkeypatch.delenv("IBKR_COMMODITIES_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_COMMODITIES_BREADTH_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_COMMODITIES_STARTUP_ENABLED", raising=False)
    details = {
        "CL": [
            _future_detail(4001, "202608", "CLQ6"),
            _future_detail(4002, "202609", "CLU6"),
            _future_detail(4003, "202610", "CLV6"),
        ],
        "GC": [
            _future_detail(5001, "202608", "GCQ6", symbol="GC", exchange="COMEX"),
            _future_detail(5002, "202609", "GCU6", symbol="GC", exchange="COMEX"),
            _future_detail(5003, "202610", "GCV6", symbol="GC", exchange="COMEX"),
        ],
    }
    fake_client = _FakeIbkrClient(details)
    provider = IbkrCommoditiesDataProvider(
        client=fake_client,
        market_data=_FakeMarketData(
            {
                4001: 80.0,
                4002: 79.0,
                4003: 78.5,
                5001: 2400.0,
                5002: 2405.0,
                5003: 2410.0,
            }
        ),
        cache=CacheService(tmp_path),
        reference_provider=SampleCommoditiesDataProvider(),
        root_configs=(
            IbkrFutureRootConfig("wti", "CL", "NYMEX", "USD", "USD/bbl", "WTI Crude Oil", trading_class="CL"),
            IbkrFutureRootConfig("gold", "GC", "COMEX", "USD", "USD/oz", "Gold", trading_class="GC"),
        ),
        contract_depth=3,
        breadth_contract_depth=2,
        history_days=0,
    )

    snapshot = provider.get_snapshot(force_refresh=True)

    assert fake_client.requests == ["CL", "GC"]
    assert provider.enabled_instrument_ids == ("wti", "gold")
    assert provider.breadth_instrument_ids == ("wti", "gold")
    wti_curve = next(curve for curve in snapshot.curve_snapshots if curve.instrument_id == "wti")
    gold_curve = next(curve for curve in snapshot.curve_snapshots if curve.instrument_id == "gold")
    assert [node.price for node in wti_curve.nodes] == [80.0, 79.0, 78.5]
    assert [node.price for node in gold_curve.nodes] == [2400.0, 2405.0]


def test_ibkr_provider_degrades_to_sample_when_disconnected():
    provider = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient([], connected=False),
        market_data=_FakeMarketData({}),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["wti"],
    )

    snapshot = provider.get_snapshot()

    assert snapshot.coverage.coverage_status == "sample"
    assert any("TWS/IBKR is not connected" in warning for warning in snapshot.warnings)
    assert "IB_HOST" in snapshot.coverage.credential_env_vars


def test_commodities_api_routes_return_workspace_and_slices(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMODITIES_PROVIDER", "sample")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime, session_token="test-gamma-session"))
    try:
        workspace_response = client.post(
            "/commodities/workspace",
            json={
                "mode": "curves_spreads",
                "selected_instrument_id": "wti",
                "force_refresh": False,
            },
        )
        assert workspace_response.status_code == 200
        workspace_payload = workspace_response.json()
        assert workspace_payload["mode"] == "curves_spreads"
        assert workspace_payload["coverage"]["coverage_status"] == "sample"
        assert len(workspace_payload["market_summaries"]) == 16
        assert len(workspace_payload["spreads"]) >= 6
        assert workspace_payload["cross_domain_links"]
        assert workspace_payload["overview"]["market_breadth"]["total_markets"] == 16
        assert workspace_payload["overview"]["matrix_rows"]
        assert workspace_payload["overview"]["scatter"]["x_methodology_label"] == "Loaded-history momentum (%)"

        overview_response = client.get("/commodities/overview")
        assert overview_response.status_code == 200
        assert overview_response.json()["mode"] == "overview"
        assert overview_response.json()["overview"]["rankings"]["largest_movers"]

        curve_response = client.get("/commodities/curve", params={"instrument_id": "wti"})
        assert curve_response.status_code == 200
        assert curve_response.json()["curve"]["shape_label"] == "backwardation"

        spreads_response = client.get("/commodities/spreads")
        assert spreads_response.status_code == 200
        assert spreads_response.json()["spreads"]

        history_response = client.get("/commodities/price-history", params={"instrument_id": "gold"})
        assert history_response.status_code == 200
        assert history_response.json()["history"]["points"]

        missing_response = client.get("/commodities/curve", params={"instrument_id": "missing"})
        assert missing_response.status_code == 404
    finally:
        runtime.shutdown()


def test_commodities_copilot_context_uses_loaded_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMODITIES_PROVIDER", "sample")
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime, session_token="test-gamma-session"))
    try:
        workspace = client.post(
            "/commodities/workspace",
            json={"mode": "overview", "selected_instrument_id": "wti", "force_refresh": False},
        ).json()
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "commodities",
                "prompt": "Frame the selected energy setup.",
                "context": {
                    "current_tab": "commodities",
                    "workspace_mode": "research",
                    "commodities_state": {"workspace": workspace},
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["provider"] == "mock"
        assert payload["domain"] == "commodities"
        assert payload["response_id"].startswith("mock_commodities_")
        assert payload["card"]["title"].startswith("Commodities:")
        assert any(trace["tool_name"] == "get_commodities_workspace_summary" for trace in payload["tool_traces"])
        assert any(source["source_id"] == "commodities.workspace" for source in payload["sources"])
        assert any(source["source_id"] == "commodities.workspace.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()
