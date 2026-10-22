from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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
    CommodityCurveNode,
    CommodityCurveSnapshot,
    CommodityFuturesContract,
    CommodityInstrument,
    CommodityMarketSummary,
    CommodityPriceBasis,
    CommodityPriceHistory,
    CommodityPricePoint,
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
    _select_active_contracts,
)
from src.services.fred import FredObservation
from src.services.market_data import QuoteSnapshot
from src.utils.time import now_utc


def test_curve_m1_m6_uses_sixth_contract_not_last_priced_contract():
    provider = SampleCommoditiesDataProvider()
    service = CommoditiesService(provider=provider)
    curve = provider.get_snapshot().curve_snapshots[0]
    nodes = [replace(curve.nodes[0], price=100.0 - index) for index in range(9)]
    enriched = service._enrich_curve(replace(curve, nodes=nodes))
    assert enriched.m1_m6_spread == 5.0
    assert enriched.curve_slope == -8.0
    nodes[5] = replace(nodes[5], price=None)
    assert service._enrich_curve(replace(curve, nodes=nodes)).m1_m6_spread is None


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
    assert any("No earlier retained curve observations" in caveat for caveat in workspace.overview.term_structure.caveats)

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


def test_commodity_reconciliation_reports_same_dated_futures_spot_gap_as_basis():
    # GUA-20261021-4: un futuro IBKR frente a un spot FRED del mismo día es una base económica fechada,
    # no un conflicto de datos.
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
    assert reconciliation.status == "basis"
    assert reconciliation.headline is not None
    assert reconciliation.headline.contract_month
    assert reconciliation.stale_after_days == 4
    comparison = next(row for row in reconciliation.comparisons if row.kind == "basis")
    assert comparison.value == 95.0
    assert comparison.unit == "USD/bbl"
    assert comparison.observed_at is not None
    assert comparison.headline_observed_at is not None
    assert comparison.age_days in {0, 1}
    assert comparison.difference == pytest.approx(-11.0)
    assert comparison.difference_pct == pytest.approx(-11.0 / 95.0, abs=1e-6)
    assert "economic basis, not a data conflict" in comparison.note
    assert "futures-spot basis" in (reconciliation.summary or "").lower()
    assert not any("basis conflict" in warning.lower() for warning in reconciliation.warnings)
    assert not any("basis conflict" in warning.lower() for warning in workspace.warnings)


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
    assert any("No earlier retained curve observations" in caveat for caveat in workspace.overview.term_structure.caveats)


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
    def __init__(
        self,
        prices: dict[int, float],
        delayed: set[int] | None = None,
        history: pd.Series | None = None,
    ):
        self.prices = prices
        self.delayed = delayed or set()
        self.history = (
            history
            if history is not None
            else pd.Series(
                [76.0, 77.5, 79.25],
                index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"]),
            )
        )

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
        return self.history.copy()


_FUTURES_MONTH_CODES = "FGHJKMNQUVXZ"


def _forward_contract_months(count: int, *, reference: datetime | None = None) -> list[str]:
    """`YYYYMM` keys for the next `count` contract months.

    The provider drops any contract that has already expired, so a fixture
    pinned to a hardcoded month quietly loses its front node once that month
    passes and the curve assertions start failing on their own. Months run from
    the month after the current one, so the 20th-of-the-month expiry below is
    always still ahead whatever day the suite runs on.
    """

    today = reference or now_utc()
    base = today.year * 12 + today.month
    return [f"{(base + index) // 12:04d}{(base + index) % 12 + 1:02d}" for index in range(count)]


def _forward_active_months(codes: str, count: int, *, reference: datetime | None = None) -> list[str]:
    """`YYYYMM` keys in a root's active-month calendar, starting two months ahead.

    Starting two months ahead keeps every key outside the five-day delivery roll
    window that metals roots apply, whatever day the suite runs on.
    """

    today = reference or now_utc()
    base = today.year * 12 + today.month
    months: list[str] = []
    index = 1
    while len(months) < count:
        absolute = base + index
        month = absolute % 12 + 1
        if _FUTURES_MONTH_CODES[month - 1] in codes:
            months.append(f"{absolute // 12:04d}{month:02d}")
        index += 1
    return months


def _contract_local_symbol(root: str, month: str) -> str:
    """The IBKR local symbol for a root and month, e.g. `CL` + 202610 -> CLV6."""

    return f"{root}{_FUTURES_MONTH_CODES[int(month[4:6]) - 1]}{int(month[:4]) % 10}"


def _contract_month_label(month: str) -> str:
    return datetime(int(month[:4]), int(month[4:6]), 1).strftime("%b %Y")


def _future_detail(con_id: int, month: str, symbol: str = "CL", exchange: str = "NYMEX"):
    contract = Contract(
        conId=con_id,
        symbol=symbol,
        secType="FUT",
        exchange=exchange,
        currency="USD",
        lastTradeDateOrContractMonth=month,
        localSymbol=_contract_local_symbol(symbol, month),
        tradingClass=symbol,
    )
    return SimpleNamespace(contract=contract, realExpirationDate=f"{month}20")


@pytest.mark.parametrize("day", [1, 15, 20, 21, 28])
@pytest.mark.parametrize("month", list(range(1, 13)))
def test_forward_contract_months_never_expire_on_the_day_the_suite_runs(month: int, day: int):
    """Guards the rot these fixtures already suffered once.

    Six curve tests failed on their own once 2026-08 passed, because the
    provider drops contracts whose expiry is behind the run date and the
    fixtures pinned 202608/202609/202610. The generated months must stay ahead
    of any run date, including the back half of a month and a December rollover.
    """

    reference = datetime(2026, month, day, tzinfo=timezone.utc)
    months = _forward_contract_months(4, reference=reference)

    assert len(months) == len(set(months)) == 4
    assert months == sorted(months)
    for key in months:
        # The fixture expiry is the 20th of the contract month.
        expiry = datetime(int(key[:4]), int(key[4:6]), 20, tzinfo=timezone.utc)
        assert expiry.date() >= reference.date()
    assert _contract_local_symbol("CL", months[0]).startswith("CL")
    assert len(_contract_local_symbol("CL", months[0])) == 4


def test_ibkr_provider_builds_futures_curve_from_contract_details_and_quotes(tmp_path):
    months = _forward_contract_months(3)
    details = [
        _future_detail(1003, months[2]),
        _future_detail(1001, months[0]),
        _future_detail(1002, months[1]),
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
    assert [node.contract.symbol for node in wti_curve.nodes] == [
        _contract_local_symbol("CL", month) for month in months
    ]
    assert [node.price for node in wti_curve.nodes] == [80.0, 79.2, 78.7]
    assert [node.previous_price for node in wti_curve.nodes] == [79.25, None, None]
    assert [node.change for node in wti_curve.nodes] == [0.75, None, None]
    assert wti_curve.previous_as_of == datetime(2026, 1, 4)
    assert wti_curve.nodes[0].contract.contract_id == "ibkr:1001"
    assert wti_curve.nodes[0].contract.contract_month == _contract_month_label(months[0])
    assert any("Delayed IBKR quote" in warning for warning in wti_curve.warnings)

    wti_history = next(history for history in snapshot.price_histories if history.instrument_id == "wti")
    assert wti_history.source_provider == "ibkr"
    assert [point.value for point in wti_history.points] == [76.0, 77.5, 79.25]

    cached_history = provider._load_curve_history("wti")
    assert cached_history
    assert cached_history[-1]["nodes"][0]["contract_id"] == "ibkr:1001"
    assert cached_history[-1]["headline_quote_context"] == {
        "current_contract_id": "ibkr:1001",
        "current_price": 80.0,
        "current_source_provider": "ibkr",
        "current_source_timestamp": wti_curve.as_of.isoformat(),
        "prior_value": 79.25,
        "prior_source_provider": "ibkr",
        "prior_source_timestamp": "2026-01-04T00:00:00",
    }

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


def test_ibkr_cached_curve_retains_exact_fresh_quote_prior_pair_across_restart(tmp_path):
    cache_dir = tmp_path / "cache"
    months = _forward_contract_months(2)
    details = [
        _future_detail(1101, months[0]),
        _future_detail(1102, months[1]),
    ]
    history = pd.Series(
        [86.83, 86.83],
        index=pd.to_datetime(["2026-07-21", "2026-07-22"]),
    )
    fresh_provider = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient(details),
        market_data=_FakeMarketData({1101: 92.10, 1102: 91.40}, history=history),
        cache=CacheService(cache_dir),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["wti"],
        selected_cache_seconds=300,
        contract_depth=2,
        history_days=3,
    )

    fresh_workspace = CommoditiesService(provider=fresh_provider).get_workspace(
        CommodityWorkspaceRequest(
            mode="overview",
            selected_instrument_id="wti",
            force_refresh=True,
        )
    )
    fresh_summary = next(
        row for row in fresh_workspace.market_summaries if row.instrument.instrument_id == "wti"
    )

    restarted_client = _FakeIbkrClient(details)
    restarted_provider = IbkrCommoditiesDataProvider(
        client=restarted_client,
        market_data=_FakeMarketData({1101: 0.0, 1102: 0.0}, history=pd.Series(dtype=float)),
        cache=CacheService(cache_dir),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["wti"],
        selected_cache_seconds=300,
        contract_depth=2,
        history_days=3,
    )
    cached_workspace = CommoditiesService(provider=restarted_provider).get_workspace(
        CommodityWorkspaceRequest(
            mode="curves_spreads",
            selected_instrument_id="wti",
            force_refresh=False,
        )
    )
    cached_summary = next(
        row for row in cached_workspace.market_summaries if row.instrument.instrument_id == "wti"
    )

    assert restarted_client.requests == []
    assert fresh_summary.latest_price == cached_summary.latest_price == pytest.approx(92.10)
    assert fresh_summary.latest_change == cached_summary.latest_change == pytest.approx(5.27)
    assert fresh_summary.latest_change_pct == cached_summary.latest_change_pct == pytest.approx(
        5.27 / 86.83,
        abs=0.000001,
    )
    assert fresh_summary.quote_basis is not None
    assert cached_summary.quote_basis is not None
    assert fresh_summary.quote_basis.provider == "ibkr"
    assert cached_summary.quote_basis.provider == "ibkr_cached"
    assert cached_summary.quote_basis.source_timestamp == fresh_summary.quote_basis.source_timestamp
    assert (
        cached_summary.quote_basis.previous_source_timestamp
        == fresh_summary.quote_basis.previous_source_timestamp
        == datetime(2026, 7, 22)
    )


def test_ibkr_cached_curve_without_prior_reference_keeps_change_unavailable(tmp_path):
    months = _forward_contract_months(2)
    details = [
        _future_detail(1201, months[0]),
        _future_detail(1202, months[1]),
    ]
    provider = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient(details),
        market_data=_FakeMarketData({1201: 92.10, 1202: 91.40}, history=pd.Series(dtype=float)),
        cache=CacheService(tmp_path),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["wti"],
        selected_cache_seconds=300,
        contract_depth=2,
        history_days=3,
    )

    provider.get_snapshot(force_refresh=True, selected_instrument_id="wti")
    cached_workspace = CommoditiesService(provider=provider).get_workspace(
        CommodityWorkspaceRequest(
            mode="curves_spreads",
            selected_instrument_id="wti",
            force_refresh=False,
        )
    )
    cached_summary = next(
        row for row in cached_workspace.market_summaries if row.instrument.instrument_id == "wti"
    )

    assert cached_summary.latest_price == pytest.approx(92.10)
    assert cached_summary.latest_change is None
    assert cached_summary.latest_change_pct is None
    assert cached_summary.quote_basis is not None
    assert cached_summary.quote_basis.previous_source_timestamp is None


def test_ibkr_cached_curve_rejects_mismatched_quote_context_timestamps(tmp_path):
    months = _forward_contract_months(2)
    details = [
        _future_detail(1301, months[0]),
        _future_detail(1302, months[1]),
    ]
    provider = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient(details),
        market_data=_FakeMarketData({1301: 92.10, 1302: 91.40}),
        cache=CacheService(tmp_path),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["wti"],
        selected_cache_seconds=300,
        contract_depth=2,
        history_days=3,
    )

    provider.get_snapshot(force_refresh=True, selected_instrument_id="wti")
    cached_rows = provider._load_curve_history("wti")
    cached_rows[-1]["headline_quote_context"]["current_source_timestamp"] = "2026-07-23T00:00:00"
    provider.cache.set_json(provider._curve_history_key("wti"), cached_rows)

    cached_workspace = CommoditiesService(provider=provider).get_workspace(
        CommodityWorkspaceRequest(
            mode="curves_spreads",
            selected_instrument_id="wti",
            force_refresh=False,
        )
    )
    cached_summary = next(
        row for row in cached_workspace.market_summaries if row.instrument.instrument_id == "wti"
    )

    assert cached_summary.latest_price == pytest.approx(92.10)
    assert cached_summary.latest_change is None
    assert cached_summary.latest_change_pct is None
    assert cached_summary.quote_basis is not None
    assert cached_summary.quote_basis.previous_source_timestamp is None


def test_ibkr_provider_fetches_broad_shallow_curves_and_deepens_selected(tmp_path):
    months = _forward_contract_months(4)
    # El oro usa solo sus meses activos fuera de la ventana de entrega (GUA-20261021-8).
    gold_months = _forward_active_months("GJMQZ", 4)
    details = {
        "CL": [
            _future_detail(2001, months[0]),
            _future_detail(2002, months[1]),
            _future_detail(2003, months[2]),
            _future_detail(2004, months[3]),
        ],
        "GC": [
            _future_detail(3001, gold_months[0], symbol="GC", exchange="COMEX"),
            _future_detail(3002, gold_months[1], symbol="GC", exchange="COMEX"),
            _future_detail(3003, gold_months[2], symbol="GC", exchange="COMEX"),
            _future_detail(3004, gold_months[3], symbol="GC", exchange="COMEX"),
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
    startup_wti_history = next(history for history in startup_snapshot.price_histories if history.instrument_id == "wti")
    startup_gold_history = next(history for history in startup_snapshot.price_histories if history.instrument_id == "gold")
    assert startup_wti_curve.source_provider == "ibkr"
    assert startup_gold_curve.source_provider == "ibkr"
    assert [node.price for node in startup_wti_curve.nodes] == [80.0, 79.0, 78.5, 78.1]
    assert [node.price for node in startup_gold_curve.nodes] == [2400.0, 2404.0]
    assert startup_wti_history.source_provider == "unavailable"
    assert startup_wti_history.points == []
    assert any("No daily reference history" in warning for warning in startup_wti_history.warnings)
    assert startup_gold_history.source_provider == "unavailable"
    assert startup_gold_history.points == []

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
    selected_wti_history = next(history for history in cached_snapshot.price_histories if history.instrument_id == "wti")
    assert selected_wti_history.source_provider == "unavailable"
    assert any("No daily reference history" in warning for warning in selected_wti_history.warnings)
    assert cached_gold_curve.source_provider == "ibkr_cached"
    assert any("Using cached IBKR curve for Gold" in warning for warning in cached_snapshot.warnings)


def test_ibkr_provider_defaults_to_shallow_breadth_for_all_configured_roots(tmp_path, monkeypatch):
    monkeypatch.delenv("IBKR_COMMODITIES_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_COMMODITIES_BREADTH_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_COMMODITIES_STARTUP_ENABLED", raising=False)
    months = _forward_contract_months(3)
    details = {
        "CL": [
            _future_detail(4001, months[0]),
            _future_detail(4002, months[1]),
            _future_detail(4003, months[2]),
        ],
        "GC": [
            _future_detail(5001, months[0], symbol="GC", exchange="COMEX"),
            _future_detail(5002, months[1], symbol="GC", exchange="COMEX"),
            _future_detail(5003, months[2], symbol="GC", exchange="COMEX"),
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


# --- GUA-20261021-2 / -4 / -8: fechas de observación, base con unidades y contratos activos ---

_AUDIT_NOW = datetime(2026, 10, 21, 10, 31)


def _daily_history(
    instrument_id: str,
    values: list[float],
    *,
    end: datetime,
    unit: str,
    provider: str = "fred",
    step_days: int = 1,
) -> CommodityPriceHistory:
    points = [
        CommodityPricePoint(
            instrument_id=instrument_id,
            timestamp=end - timedelta(days=step_days * (len(values) - 1 - index)),
            value=value,
            unit=unit,
            source_provider=provider,
            retrieved_at=_AUDIT_NOW,
            origin=f"{provider}.fixture:{instrument_id}",
            transformation_note="Fixture spot/proxy series.",
        )
        for index, value in enumerate(values)
    ]
    return CommodityPriceHistory(
        instrument_id=instrument_id,
        label=f"{instrument_id} fixture",
        unit=unit,
        points=points,
        source_provider=provider,
        retrieved_at=_AUDIT_NOW,
        origin=f"{provider}.fixture:{instrument_id}",
        transformation_note="Fixture spot/proxy series.",
    )


def _front_curve(
    instrument_id: str,
    symbols_and_prices: list[tuple[str, float]],
    *,
    as_of: datetime = _AUDIT_NOW,
    provider: str = "ibkr",
) -> CommodityCurveSnapshot:
    nodes = [
        CommodityCurveNode(
            contract=CommodityFuturesContract(
                contract_id=f"ibkr:{instrument_id}:{index}",
                instrument_id=instrument_id,
                symbol=symbol,
                contract_month=f"M{index + 1}",
                is_front_month=index == 0,
                source_provider=provider,
            ),
            price=price,
            source_provider=provider,
            retrieved_at=as_of,
        )
        for index, (symbol, price) in enumerate(symbols_and_prices)
    ]
    return CommodityCurveSnapshot(
        instrument_id=instrument_id,
        as_of=as_of,
        nodes=nodes,
        source_provider=provider,
        retrieved_at=as_of,
        origin=f"ibkr.commodities.curve:{instrument_id}",
    )


class _FixtureCommoditiesProvider:
    provider_id = "fixture"
    provider_label = "Fixture Commodities"

    def __init__(self, histories: list[CommodityPriceHistory], curves: list[CommodityCurveSnapshot]):
        self.histories = histories
        self.curves = curves

    def get_snapshot(self, *, force_refresh=False, selected_instrument_id=None):
        del force_refresh, selected_instrument_id
        sample = SampleCommoditiesDataProvider().get_snapshot()
        return replace(
            sample,
            price_histories=self.histories,
            curve_snapshots=self.curves,
            inventory_series=[],
            source_provider="ibkr",
        )


def _audit_energy_provider(*, wti_as_of: datetime = _AUDIT_NOW) -> _FixtureCommoditiesProvider:
    # Réplica de la auditoría: spot FRED/EIA hasta el 2026-10-14 junto a futuros IBKR del 2026-10-21.
    end = datetime(2026, 10, 14)
    return _FixtureCommoditiesProvider(
        histories=[
            _daily_history("wti", [95.0 + index * 0.25 for index in range(27)] + [101.91], end=end, unit="USD/bbl"),
            _daily_history("gasoline", [2.9 + index * 0.003 for index in range(27)] + [2.99], end=end, unit="USD/gal", provider="eia"),
            _daily_history("heating_oil", [4.4 + index * 0.004 for index in range(27)] + [4.83], end=end, unit="USD/gal", provider="eia"),
            _daily_history("brent", [120.0 + index * 0.2 for index in range(27)] + [126.55], end=end, unit="USD/bbl"),
        ],
        curves=[
            _front_curve("wti", [("CLZ6", 100.05), ("CLF7", 98.17)], as_of=wti_as_of),
            _front_curve("gasoline", [("RBX6", 3.18), ("RBZ6", 3.05)]),
            _front_curve("heating_oil", [("HOX6", 4.95), ("HOZ6", 4.81)]),
            _front_curve("brent", [("BZZ6", 111.05), ("BZF7", 107.35)], provider="ibkr_cached"),
        ],
    )


def test_spreads_expose_latest_aligned_observation_and_flag_week_old_history_as_stale():
    service = CommoditiesService(provider=_audit_energy_provider(), clock=lambda: _AUDIT_NOW)

    spreads = {spread.definition.spread_id: spread for spread in service.get_spreads()}

    crack = spreads["gasoline-crack"]
    assert crack.observed_at == datetime(2026, 10, 14)
    assert crack.observation_lag_days == 7
    assert crack.freshness == "stale"
    assert crack.stale_after_days == 4
    assert crack.leg_observed_at == {"gasoline": datetime(2026, 10, 14), "wti": datetime(2026, 10, 14)}
    assert crack.value == pytest.approx(2.99 * 42 - 101.91, abs=1e-6)
    assert any("is stale" in warning and "2026-10-14" in warning for warning in crack.warnings)
    # retrieved_at sigue siendo la hora de descarga y nunca sustituye a la observación.
    assert crack.retrieved_at == _AUDIT_NOW
    assert crack.observed_at != crack.retrieved_at

    # Valor actual con las cotizaciones front IBKR de la misma instantánea, etiquetado aparte.
    assert crack.current_value == pytest.approx(3.18 * 42 - 100.05, abs=1e-6)
    assert crack.current_value_as_of == _AUDIT_NOW
    assert "RBX6 / CLZ6" in (crack.current_value_source or "")
    three_two_one = spreads["three-two-one-crack"]
    assert three_two_one.freshness == "stale"
    assert three_two_one.current_value == pytest.approx(((2 * 3.18 + 4.95) * 42 - 3 * 100.05) / 3, abs=1e-6)

    wti_calendar = spreads["wti-m1-m2"]
    assert wti_calendar.observed_at == _AUDIT_NOW
    assert wti_calendar.freshness == "current"
    assert wti_calendar.current_value is None


def test_spread_current_value_is_withheld_when_leg_quotes_are_different_vintages():
    provider = _audit_energy_provider(wti_as_of=_AUDIT_NOW - timedelta(hours=1))
    service = CommoditiesService(provider=provider, clock=lambda: _AUDIT_NOW)

    spreads = {spread.definition.spread_id: spread for spread in service.get_spreads()}

    assert spreads["gasoline-crack"].current_value is None
    assert spreads["gasoline-crack"].current_value_source is None
    assert spreads["two-one-one-crack"].current_value is None
    # El valor histórico, con su fecha, se mantiene.
    assert spreads["gasoline-crack"].observed_at == datetime(2026, 10, 14)


def test_spreads_with_recent_history_are_current_and_monthly_metals_are_stale():
    provider = _FixtureCommoditiesProvider(
        histories=[
            _daily_history("gasoline", [3.0 + index * 0.01 for index in range(25)], end=datetime(2026, 10, 20), unit="USD/gal", provider="eia"),
            _daily_history("wti", [99.0 + index * 0.05 for index in range(25)], end=datetime(2026, 10, 20), unit="USD/bbl"),
            _daily_history("copper", [13000.0 + index * 20 for index in range(25)], end=datetime(2026, 7, 1), unit="USD/metric ton"),
            _daily_history("aluminum", [2600.0 + index * 5 for index in range(25)], end=datetime(2026, 7, 1), unit="USD/metric ton"),
        ],
        curves=[],
    )
    service = CommoditiesService(provider=provider, clock=lambda: _AUDIT_NOW)

    spreads = {spread.definition.spread_id: spread for spread in service.get_spreads()}

    assert spreads["gasoline-crack"].freshness == "current"
    assert spreads["gasoline-crack"].observation_lag_days == 1
    assert not any("is stale" in warning for warning in spreads["gasoline-crack"].warnings)
    assert spreads["copper-aluminum-spread"].freshness == "stale"
    assert spreads["copper-aluminum-spread"].observed_at == datetime(2026, 7, 1)
    assert spreads["copper-aluminum-spread"].observation_lag_days == 112


def test_spread_freshness_survives_the_api_schema():
    from src.api.schemas.commodities import CommoditySpreadSnapshotModel

    service = CommoditiesService(provider=_audit_energy_provider(), clock=lambda: _AUDIT_NOW)
    crack = next(spread for spread in service.get_spreads() if spread.definition.spread_id == "gasoline-crack")

    payload = CommoditySpreadSnapshotModel.from_domain(crack).model_dump(mode="json")

    assert payload["observed_at"].startswith("2026-10-14")
    assert payload["freshness"] == "stale"
    assert payload["observation_lag_days"] == 7
    assert payload["leg_observed_at"]["wti"].startswith("2026-10-14")
    assert payload["current_value"] == pytest.approx(3.18 * 42 - 100.05, abs=1e-6)


def test_basis_reconciliation_reports_week_old_references_as_stale_not_conflict():
    service = CommoditiesService(provider=_audit_energy_provider(), clock=lambda: _AUDIT_NOW)

    workspace = service.get_workspace(CommodityWorkspaceRequest(mode="energy", selected_instrument_id="brent"))

    rows = {row.instrument_id: row for row in workspace.price_reconciliations}
    for instrument_id, reference_value in [("wti", 101.91), ("brent", 126.55)]:
        row = rows[instrument_id]
        assert row.status == "stale_reference"
        stale = next(item for item in row.comparisons if item.kind == "stale_reference")
        assert stale.value == pytest.approx(reference_value)
        assert stale.unit == "USD/bbl"
        assert stale.observed_at == datetime(2026, 10, 14)
        assert stale.age_days == 7
        assert stale.difference_pct is None
        assert any("Stale commodity reference" in warning and "2026-10-14" in warning for warning in row.warnings)
        assert not any("basis conflict" in warning.lower() for warning in row.warnings)
    assert not any("basis conflict" in warning.lower() for warning in workspace.warnings)
    assert "stale" in (rows["brent"].summary or "").lower()


def _copper_provider(reference_value: float, reference_unit: str, *, reference_end: datetime) -> _FixtureCommoditiesProvider:
    return _FixtureCommoditiesProvider(
        histories=[_daily_history("copper", [reference_value] * 3, end=reference_end, unit=reference_unit)],
        curves=[_front_curve("copper", [("HGZ6", 6.49), ("HGH7", 6.55)])],
    )


def test_basis_reconciliation_converts_copper_tonnes_to_pounds_before_comparing():
    service = CommoditiesService(
        provider=_copper_provider(13542.82, "USD/metric ton", reference_end=datetime(2026, 10, 20)),
        clock=lambda: _AUDIT_NOW,
    )

    row = next(item for item in service.get_workspace().price_reconciliations if item.instrument_id == "copper")

    comparison = next(item for item in row.comparisons if item.basis_id == "copper:history_latest")
    assert comparison.kind == "basis"
    assert comparison.converted_value == pytest.approx(13542.82 / 2204.62262185, rel=1e-6)
    assert comparison.difference == pytest.approx(6.49 - 13542.82 / 2204.62262185, rel=1e-5)
    assert abs(comparison.difference_pct) < 0.1
    assert "Converted from 13542.82 USD/metric ton to USD/lb" in comparison.note
    assert row.status == "basis"
    assert not any("208636" in warning for warning in row.warnings)


def test_basis_reconciliation_stale_copper_reference_keeps_converted_value():
    service = CommoditiesService(
        provider=_copper_provider(13542.82, "USD/metric ton", reference_end=datetime(2026, 7, 1)),
        clock=lambda: _AUDIT_NOW,
    )

    row = next(item for item in service.get_workspace().price_reconciliations if item.instrument_id == "copper")

    comparison = next(item for item in row.comparisons if item.basis_id == "copper:history_latest")
    assert row.status == "stale_reference"
    assert comparison.kind == "stale_reference"
    assert comparison.converted_value == pytest.approx(6.1429, abs=1e-3)
    assert comparison.age_days == 112


def test_basis_reconciliation_reports_unknown_units_without_a_percentage():
    service = CommoditiesService(
        provider=_copper_provider(5.0, "USD/bu", reference_end=datetime(2026, 10, 20)),
        clock=lambda: _AUDIT_NOW,
    )

    row = next(item for item in service.get_workspace().price_reconciliations if item.instrument_id == "copper")

    comparison = next(item for item in row.comparisons if item.basis_id == "copper:history_latest")
    assert comparison.kind == "units_differ"
    assert comparison.difference_pct is None
    assert comparison.converted_value is None
    assert row.status == "insufficient"
    assert any("units differ" in warning.lower() for warning in row.warnings)


def test_basis_reconciliation_flags_implausible_gap_after_conversion_and_same_basis_conflicts():
    mislabeled = CommoditiesService(
        provider=_copper_provider(13542.82, "USD/lb", reference_end=datetime(2026, 10, 20)),
        clock=lambda: _AUDIT_NOW,
    )
    row = next(item for item in mislabeled.get_workspace().price_reconciliations if item.instrument_id == "copper")
    assert row.status == "conflict"
    assert any("more than 3x" in warning for warning in row.warnings)

    # Mismo tipo de base (futuro front) de dos fuentes distintas y fechas cercanas: conflicto de datos.
    same_basis = CommoditiesService(
        provider=_FixtureCommoditiesProvider(
            histories=[_daily_history("wti", [79.0, 80.0], end=datetime(2026, 10, 20), unit="USD/bbl", provider="ibkr")],
            curves=[_front_curve("wti", [("CLZ6", 92.10), ("CLF7", 91.40)], provider="ibkr_cached")],
        ),
        clock=lambda: _AUDIT_NOW,
    )
    row = next(item for item in same_basis.get_workspace().price_reconciliations if item.instrument_id == "wti")
    assert row.status == "conflict"
    assert any("basis conflict (data conflict)" in warning for warning in row.warnings)


def _metal_contracts(symbol: str, exchange: str, months: list[str]):
    return [
        (detail.contract, detail)
        for detail in (
            _future_detail(9000 + index, month, symbol=symbol, exchange=exchange) for index, month in enumerate(months)
        )
    ]


def _root(instrument_id: str) -> IbkrFutureRootConfig:
    return next(config for config in IBKR_FUTURES_ROOTS if config.instrument_id == instrument_id)


@pytest.mark.parametrize(
    ("instrument_id", "symbol", "exchange", "months", "expected"),
    [
        ("gold", "GC", "COMEX", ["202610", "202611", "202612", "202702", "202704"], ["GCZ6", "GCG7", "GCJ7"]),
        ("silver", "SI", "COMEX", ["202610", "202611", "202612", "202701", "202703"], ["SIZ6", "SIH7"]),
        ("platinum", "PL", "NYMEX", ["202610", "202701", "202704"], ["PLF7", "PLJ7"]),
        ("copper", "HG", "COMEX", ["202610", "202611", "202612", "202703"], ["HGZ6", "HGH7"]),
        ("aluminum", "ALI", "COMEX", ["202610", "202611", "202612"], ["ALIX6", "ALIZ6"]),
        ("wti", "CL", "NYMEX", ["202612", "202701", "202702"], ["CLZ6", "CLF7", "CLG7"]),
    ],
)
def test_metals_front_selection_skips_delivery_and_thin_months(instrument_id, symbol, exchange, months, expected):
    selected, notes = _select_active_contracts(
        _root(instrument_id), _metal_contracts(symbol, exchange, months), datetime(2026, 10, 21, 10, 31)
    )

    assert [contract.localSymbol for contract, _detail in selected] == expected
    if instrument_id == "wti":
        assert notes == []
    else:
        assert any(f"{symbol}V6" in note for note in notes)


def test_metals_front_selection_rolls_before_the_delivery_month_starts():
    selected, notes = _select_active_contracts(
        _root("gold"), _metal_contracts("GC", "COMEX", ["202612", "202702", "202704"]), datetime(2026, 11, 27)
    )

    assert [contract.localSymbol for contract, _detail in selected] == ["GCG7", "GCJ7"]
    assert any("GCZ6" in note for note in notes)


def test_ibkr_gold_curve_front_is_the_active_month_from_a_fake_contract_list(tmp_path):
    today = now_utc()
    base = today.year * 12 + today.month - 1
    months = [f"{(base + index) // 12:04d}{(base + index) % 12 + 1:02d}" for index in range(10)]
    details = [_future_detail(7000 + index, month, symbol="GC", exchange="COMEX") for index, month in enumerate(months)]
    prices = {7000 + index: 2400.0 + index for index in range(len(months))}
    provider = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient({"GC": details}),
        market_data=_FakeMarketData(prices, history=pd.Series(dtype=float)),
        cache=CacheService(tmp_path),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["gold"],
        contract_depth=3,
        history_days=0,
    )

    snapshot = provider.get_snapshot(force_refresh=True, selected_instrument_id="gold")

    gold_curve = next(curve for curve in snapshot.curve_snapshots if curve.instrument_id == "gold")
    assert gold_curve.source_provider == "ibkr"
    assert all(node.contract.symbol[2] in "GJMQZ" for node in gold_curve.nodes)
    cutoff = (today + timedelta(days=5)).date()
    front_month = next(
        month
        for month in months
        if _FUTURES_MONTH_CODES[int(month[4:6]) - 1] in "GJMQZ"
        and datetime(int(month[:4]), int(month[4:6]), 1).date() > cutoff
    )
    assert gold_curve.nodes[0].contract.symbol == _contract_local_symbol("GC", front_month)
    assert any("active delivery months" in warning for warning in gold_curve.warnings)


class _RaisingIb(_FakeIb):
    def reqContractDetails(self, contract):
        self.requests.append(str(getattr(contract, "symbol", "") or ""))
        raise TimeoutError("contract details timed out")


def test_failed_zinc_discovery_is_negatively_cached_for_the_session(tmp_path):
    client = _FakeIbkrClient({"ZS": []})
    provider = IbkrCommoditiesDataProvider(
        client=client,
        market_data=_FakeMarketData({}),
        cache=CacheService(tmp_path),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["zinc"],
        history_days=0,
    )

    first = provider.get_snapshot(force_refresh=True, selected_instrument_id="zinc")
    second = provider.get_snapshot(force_refresh=True, selected_instrument_id="zinc")
    third = provider.get_snapshot(selected_instrument_id="zinc")

    assert client.requests == ["ZS"]
    assert any("returned no futures contract definitions for Zinc" in warning for warning in first.warnings)
    for snapshot in (second, third):
        assert any("failed earlier this session" in warning and "Zinc" in warning for warning in snapshot.warnings)


def test_discovery_exceptions_are_cached_and_zero_ttl_disables_the_negative_cache(tmp_path):
    raising_client = _FakeIbkrClient({})
    raising_client.ib = _RaisingIb({})
    raising_client.requests = raising_client.ib.requests
    provider = IbkrCommoditiesDataProvider(
        client=raising_client,
        market_data=_FakeMarketData({}),
        cache=CacheService(tmp_path / "raising"),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["zinc"],
        history_days=0,
    )
    provider.get_snapshot(force_refresh=True, selected_instrument_id="zinc")
    provider.get_snapshot(force_refresh=True, selected_instrument_id="zinc")
    assert raising_client.requests == ["ZS"]

    retrying_client = _FakeIbkrClient({"ZS": []})
    retrying = IbkrCommoditiesDataProvider(
        client=retrying_client,
        market_data=_FakeMarketData({}),
        cache=CacheService(tmp_path / "retrying"),
        reference_provider=SampleCommoditiesDataProvider(),
        enabled_instrument_ids=["zinc"],
        history_days=0,
        discovery_failure_ttl_seconds=0,
    )
    retrying.get_snapshot(force_refresh=True, selected_instrument_id="zinc")
    retrying.get_snapshot(force_refresh=True, selected_instrument_id="zinc")
    assert retrying_client.requests == ["ZS", "ZS"]


class _BoilerplateReferenceProvider:
    provider_id = "fixture_reference"
    provider_label = "Fixture Reference"

    def get_snapshot(self, *, force_refresh=False, selected_instrument_id=None):
        del force_refresh, selected_instrument_id
        snapshot = SampleCommoditiesDataProvider().get_snapshot()
        return replace(
            snapshot,
            warnings=[
                "Futures curves are unavailable in this provider slice; add IBKR/Databento-style futures-chain coverage for live curves.",
                *snapshot.warnings,
            ],
            coverage=replace(
                snapshot.coverage,
                caveats=[
                    "FRED price histories are spot or proxy series where configured; futures curves remain unavailable unless a futures provider is added.",
                    *snapshot.coverage.caveats,
                ],
            ),
        )


def test_curve_unavailable_boilerplate_is_dropped_once_ibkr_curves_load(tmp_path):
    months = _forward_contract_months(2)
    loaded = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient([_future_detail(8101, months[0]), _future_detail(8102, months[1])]),
        market_data=_FakeMarketData({8101: 80.0, 8102: 79.5}),
        cache=CacheService(tmp_path),
        reference_provider=_BoilerplateReferenceProvider(),
        enabled_instrument_ids=["wti"],
        contract_depth=2,
        history_days=0,
    ).get_snapshot(force_refresh=True)

    assert not any("Futures curves are unavailable" in warning for warning in loaded.warnings)
    assert not any("futures curves remain unavailable" in caveat for caveat in loaded.coverage.caveats)
    assert "FRED price histories are spot or proxy series where configured." in loaded.coverage.caveats

    disconnected = IbkrCommoditiesDataProvider(
        client=_FakeIbkrClient([], connected=False),
        market_data=_FakeMarketData({}),
        reference_provider=_BoilerplateReferenceProvider(),
        enabled_instrument_ids=["wti"],
    ).get_snapshot()
    assert any("Futures curves are unavailable" in warning for warning in disconnected.warnings)


class _RecordingFredClient:
    def __init__(self):
        self.requested: list[str] = []

    def get_series_observations(self, series_id, **kwargs):
        del kwargs
        self.requested.append(series_id)
        return [FredObservation(timestamp=datetime(2026, 10, 14), value=100.0)], _AUDIT_NOW


def test_fred_precious_metal_fallbacks_are_explicitly_absent_unless_configured(monkeypatch):
    def fake_fetch_json(url, params):
        del url, params
        return {"response": {"data": []}}

    monkeypatch.delenv("COMMODITIES_FRED_GOLD_SERIES_ID", raising=False)
    fred = _RecordingFredClient()
    snapshot = EiaCommoditiesDataProvider(
        api_key="test-key",
        reference_provider=SampleCommoditiesDataProvider(),
        fred_client=fred,
        fetch_json=fake_fetch_json,
    ).get_snapshot(force_refresh=True)

    assert not {"GOLDAMGBD228NLBM", "SLVPRUSD", "PPLTUSDM"} & set(fred.requested)
    assert "DCOILWTICO" in fred.requested
    assert any("No FRED fallback is configured for Gold, Silver, Platinum" in warning for warning in snapshot.warnings)

    monkeypatch.setenv("COMMODITIES_FRED_GOLD_SERIES_ID", "VERIFIEDGOLD")
    configured = _RecordingFredClient()
    snapshot = EiaCommoditiesDataProvider(
        api_key="test-key",
        reference_provider=SampleCommoditiesDataProvider(),
        fred_client=configured,
        fetch_json=fake_fetch_json,
    ).get_snapshot(force_refresh=True)
    assert "VERIFIEDGOLD" in configured.requested
    gold = next(history for history in snapshot.price_histories if history.instrument_id == "gold")
    assert gold.source_provider == "fred"
    assert any("No FRED fallback is configured for Silver, Platinum" in warning for warning in snapshot.warnings)


def test_cross_domain_links_declare_navigable_targets():
    workspace = CommoditiesService(provider=SampleCommoditiesDataProvider()).get_workspace()

    targets = {link.link_id: (link.target_tab, link.target_mode, link.target_ids) for link in workspace.cross_domain_links}

    assert targets["maritime-energy-chokepoints"] == ("maritime", "chokepoints", {})
    assert targets["macro-inflation-energy"] == ("macro", "snapshot", {"theme": "inflation"})
    assert targets["macro-growth-copper-gold"] == ("macro", "snapshot", {"theme": "growth"})
    assert targets["prediction-geopolitical-energy"] == ("prediction_markets", "screener", {})
