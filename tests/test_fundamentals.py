from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd

from src.application.fundamentals_service import FundamentalsService
from src.models.fundamentals import (
    FundamentalsCompanyRecord,
    FundamentalsFilingRecord,
    FundamentalsPeriodRecord,
    FundamentalsPricePoint,
    FundamentalsSearchResult,
    FundamentalsStatementCell,
    FundamentalsStatementLine,
    FundamentalsStatementView,
)
from src.services.cache import CacheService
from src.services.fundamentals_adapters import IbkrPriceContext, SecCompanyData, SecFundamentalsAdapter
from src.services.fundamentals_store import FundamentalsResearchStore


NOW = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)


def test_fundamentals_overview_builds_company_context_and_peer_heatmap(tmp_path):
    service = _build_service(tmp_path)

    results = service.search_companies("aapl")
    overview = service.get_overview("aapl")

    assert results[0].ticker == "AAPL"
    assert overview is not None
    assert overview.company.ticker == "AAPL"
    assert overview.company.source_provider == "sec"
    assert overview.peer_basket is not None
    assert overview.peer_heatmap is not None
    assert overview.peer_heatmap.tickers[0] == "AAPL"
    assert len(overview.dcf_summary) == 3

    ev_to_sales = next(metric for metric in overview.headline_metrics if metric.metric_id == "ev_to_sales")
    assert ev_to_sales.value is not None
    assert ev_to_sales.transformation_note is not None
    assert overview.peer_heatmap.transformation_note is not None


def test_fundamentals_financials_include_gamma_owned_ratio_views(tmp_path):
    service = _build_service(tmp_path)

    financials = service.get_financials("AAPL")

    assert financials is not None
    assert financials.annual_income_statement.statement == "income"
    assert financials.quarterly_cash_flow_statement.basis == "quarterly"
    assert financials.annual_ratio_view.statement == "ratios"
    assert financials.annual_ratio_view.transformation_note is not None

    gross_margin = next(line for line in financials.annual_ratio_view.lines if line.line_key == "gross_margin")
    roic = next(line for line in financials.annual_ratio_view.lines if line.line_key == "roic")
    assert gross_margin.cells[-1].value is not None
    assert gross_margin.cells[-1].transformation_note is not None
    assert roic.cells[-1].value is not None


def test_fundamentals_dcf_save_load_preserves_scenario_selection_and_overrides(tmp_path):
    service = _build_service(tmp_path)

    initial = service.get_dcf_model("AAPL")
    assert initial is not None
    assert initial.active_scenario_id == "base"

    payload = {
        "active_scenario_id": "bull",
        "projection_years": list(initial.projection_years),
        "scenarios": {
            scenario.scenario_id: {
                "assumptions": deepcopy(scenario.assumptions),
                "overrides": deepcopy(scenario.overrides),
            }
            for scenario in initial.scenarios
        },
    }
    payload["scenarios"]["bull"]["overrides"]["revenue"] = [480_000_000_000.0] + [None] * (
        len(initial.projection_years) - 1
    )

    saved = service.save_dcf_model("AAPL", payload)
    reloaded = service.get_dcf_model("AAPL")

    assert saved is not None
    assert reloaded is not None
    assert saved.active_scenario_id == "bull"
    assert reloaded.active_scenario_id == "bull"

    bull = next(scenario for scenario in reloaded.scenarios if scenario.scenario_id == "bull")
    revenue_row = next(row for row in bull.projection_rows if row.line_key == "revenue")
    assert bull.summary is not None
    assert bull.summary.transformation_note is not None
    assert revenue_row.overridden[0] is True
    assert revenue_row.values[0] == 480_000_000_000.0


def test_fundamentals_peer_basket_persists_across_overview_requests(tmp_path):
    service = _build_service(tmp_path)

    basket = service.save_peer_basket("AAPL", ["MSFT", "GOOGL", "META", "AAPL"])
    overview = service.get_overview("AAPL")

    assert basket is not None
    assert basket.peer_tickers == ["MSFT", "GOOGL", "META"]
    assert overview is not None
    assert overview.peer_basket is not None
    assert overview.peer_basket.peer_tickers == ["MSFT", "GOOGL", "META"]

    selected_candidates = [candidate.ticker for candidate in overview.peer_candidates if candidate.selected]
    assert selected_candidates == ["MSFT", "GOOGL", "META"]


def test_fundamentals_peer_seed_uses_sic_instead_of_tech_fallback_for_chemicals(tmp_path):
    service = _build_service(tmp_path)

    peers = service.get_peers("ALB")

    assert peers is not None
    assert peers.peer_basket.peer_tickers == ["FMC", "CE", "DOW", "EMN", "DD"]
    assert not {"AAPL", "GOOGL", "ORCL", "SAP", "CRM"}.intersection(peers.peer_basket.peer_tickers)
    assert peers.peer_heatmap is not None
    assert peers.peer_heatmap.tickers[:3] == ["ALB", "FMC", "CE"]


def test_fundamentals_peer_seed_handles_semiconductor_equipment(tmp_path):
    service = _build_service(tmp_path)

    peers = service.get_peers("ASML")

    assert peers is not None
    assert peers.peer_basket.peer_tickers == ["AMAT", "LRCX", "KLAC", "TER", "ONTO"]
    assert not {"AAPL", "GOOGL", "ORCL", "SAP", "CRM"}.intersection(peers.peer_basket.peer_tickers)


def test_fundamentals_peer_seed_handles_broad_non_tech_buckets(tmp_path):
    service = _build_service(tmp_path)

    bank_peers = service.get_peers("JPM")
    utility_peers = service.get_peers("NEE")
    airline_peers = service.get_peers("DAL")

    assert bank_peers is not None
    assert bank_peers.peer_basket.peer_tickers == ["BAC", "WFC", "C", "PNC"]
    assert utility_peers is not None
    assert utility_peers.peer_basket.peer_tickers == ["DUK", "SO", "AEP", "EXC"]
    assert airline_peers is not None
    assert airline_peers.peer_basket.peer_tickers == ["UAL", "AAL", "LUV", "ALK"]


def test_fundamentals_peer_basket_ignores_cross_ticker_cached_payload(tmp_path):
    service = _build_service(tmp_path)
    service.store.save_peer_basket(
        "ALB",
        {
            "focal_ticker": "AAPL",
            "peer_tickers": ["AAPL", "GOOGL", "ORCL", "SAP", "CRM"],
            "display_order": ["AAPL", "GOOGL", "ORCL", "SAP", "CRM"],
            "user_edited": False,
        },
    )

    peers = service.get_peers("ALB")

    assert peers is not None
    assert peers.peer_basket.peer_tickers == ["FMC", "CE", "DOW", "EMN", "DD"]


def test_fundamentals_peers_payload_deepens_comparison_and_diagnostics(tmp_path):
    service = _build_service(tmp_path)

    peers = service.get_peers("AAPL")

    assert peers is not None
    assert peers.peer_basket.display_order[0] == "AAPL"
    assert peers.peer_heatmap is not None
    assert {"valuation", "profitability", "growth", "efficiency", "leverage"}.issubset(
        {row.family for row in peers.peer_heatmap.rows}
    )
    assert peers.comparisons[0].ticker == "AAPL"
    metric_ids = {metric.metric_id for metric in peers.comparisons[0].metrics}
    assert "implied_revenue_cagr" in metric_ids
    assert peers.diagnostics
    assert peers.transformation_note is not None


def test_fundamentals_reference_exposes_raw_normalized_trace_and_coverage(tmp_path):
    service = _build_service(tmp_path)

    reference = service.get_reference("AAPL")

    assert reference is not None
    assert reference.inspection is not None
    assert reference.inspection.traces
    revenue_trace = next(row for row in reference.inspection.traces if row.line_key == "revenue")
    assert revenue_trace.concept_name == "test:revenue"
    assert revenue_trace.accession_number is not None
    assert revenue_trace.filing_form == "10-K"
    assert reference.inspection.coverage
    assert reference.inspection.transformation_note is not None


def test_fundamentals_reverse_valuation_solves_implied_expectations(tmp_path):
    service = _build_service(tmp_path)

    reverse = service.get_reverse_valuation("AAPL")

    assert reverse is not None
    assert reverse.target_enterprise_value is not None
    assert reverse.base_case_summary is not None
    assert reverse.scenario_gap_metrics
    revenue_driver = next(driver for driver in reverse.drivers if driver.driver_id == "implied_revenue_cagr")
    fcf_driver = next(driver for driver in reverse.drivers if driver.driver_id == "implied_fcf_cagr")
    assert revenue_driver.implied_value is not None
    assert revenue_driver.transformation_note is not None
    assert fcf_driver.solved_enterprise_value is not None
    assert reverse.sensitivity_matrix is not None
    assert reverse.sensitivity_matrix.rows[0][0].transformation_note is not None


def test_fundamentals_dcf_snapshots_save_list_and_load_model(tmp_path):
    service = _build_service(tmp_path)

    snapshot = service.save_dcf_snapshot("AAPL", name="Base checkpoint")
    duplicate_name_snapshot = service.save_dcf_snapshot("AAPL", name="Base checkpoint")
    snapshots = service.list_dcf_snapshots("AAPL")
    loaded = service.load_dcf_snapshot_model("AAPL", snapshot.snapshot_id if snapshot else "")

    assert snapshot is not None
    assert duplicate_name_snapshot is not None
    assert duplicate_name_snapshot.snapshot_id != snapshot.snapshot_id
    assert snapshot.name == "Base checkpoint"
    assert snapshot.scenario_summaries
    assert snapshots is not None
    assert {item.snapshot_id for item in snapshots} == {
        snapshot.snapshot_id,
        duplicate_name_snapshot.snapshot_id,
    }
    assert loaded is not None
    assert loaded.ticker == "AAPL"
    assert loaded.active_scenario_id == snapshot.active_scenario_id


def test_fundamentals_dcf_model_reanchors_stale_projection_years_from_store(tmp_path):
    service = _build_service(tmp_path)

    initial = service.get_dcf_model("AAPL")
    assert initial is not None

    stale_payload = {
        "ticker": "AAPL",
        "active_scenario_id": "base",
        "projection_years": [2020, 2021, 2022, 2023, 2024],
        "scenarios": {
            scenario.scenario_id: {
                "assumptions": deepcopy(scenario.assumptions),
                "overrides": deepcopy(scenario.overrides),
            }
            for scenario in initial.scenarios
        },
    }
    service.store.save_dcf_model("AAPL", stale_payload)

    reloaded = service.get_dcf_model("AAPL")

    assert reloaded is not None
    assert reloaded.historical_year_labels[-1] == "FY 2024"
    assert reloaded.projection_years == [2025, 2026, 2027, 2028, 2029]


def test_fundamentals_default_dcf_mean_reverts_cyclical_trough_margins(tmp_path):
    service = _build_service(tmp_path)

    model = service.get_dcf_model("ALB")

    assert model is not None
    base = next(scenario for scenario in model.scenarios if scenario.scenario_id == "base")
    revenue_growth = base.assumptions["revenue_growth_pct"]
    ebit_margin = base.assumptions["ebit_margin_pct"]

    assert isinstance(revenue_growth, list)
    assert isinstance(ebit_margin, list)
    assert revenue_growth[0] > -0.04
    assert ebit_margin[0] > 0.02
    assert ebit_margin[-1] > ebit_margin[0]
    assert ebit_margin[-1] > 0.10


def test_sec_adapter_normalizes_quarterly_periods_and_derives_missing_quarters(tmp_path):
    adapter = SecFundamentalsAdapter(CacheService(tmp_path / "cache"))
    payload = _facts_dataframe_for_quarterly_normalization()

    annual_income_view = adapter._build_statement_view(payload, statement="income", basis="annual", retrieved_at=NOW)
    income_view = adapter._build_statement_view(payload, statement="income", basis="quarterly", retrieved_at=NOW)
    cash_view = adapter._build_statement_view(payload, statement="cashflow", basis="quarterly", retrieved_at=NOW)
    balance_view = adapter._build_statement_view(payload, statement="balance", basis="quarterly", retrieved_at=NOW)

    assert [period.label for period in annual_income_view.periods] == ["FY 2024", "FY 2025"]
    assert annual_income_view.periods[-1].end_date == _dt("2025-09-27")

    expected_labels = ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025", "Q1 2026"]
    assert [period.label for period in income_view.periods] == expected_labels
    assert [period.label for period in cash_view.periods] == expected_labels
    assert [period.label for period in balance_view.periods][-5:] == expected_labels
    assert "FY 2025" not in [period.label for period in balance_view.periods]

    revenue_row = next(line for line in income_view.lines if line.line_key == "revenue")
    operating_cash_flow_row = next(line for line in cash_view.lines if line.line_key == "operating_cash_flow")
    current_assets_row = next(line for line in balance_view.lines if line.line_key == "current_assets")

    assert revenue_row.cells[0].concept_name == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    assert [cell.value for cell in revenue_row.cells] == [100.0, 110.0, 120.0, 130.0, 140.0]
    assert [cell.source_provider for cell in revenue_row.cells] == ["sec", "sec", "sec", "gamma", "sec"]
    assert [cell.value for cell in operating_cash_flow_row.cells] == [30.0, 40.0, 50.0, 50.0, 50.0]
    assert [cell.source_provider for cell in operating_cash_flow_row.cells] == ["sec", "gamma", "gamma", "gamma", "sec"]
    assert operating_cash_flow_row.cells[1].transformation_note is not None
    assert [cell.value for cell in current_assets_row.cells][-5:] == [500.0, 520.0, 540.0, 560.0, 580.0]
    assert balance_view.transformation_note is None


def test_fundamentals_dcf_and_reverse_do_not_assume_missing_shares(tmp_path):
    service = _build_service(tmp_path)
    sec_data = service.sec_adapter.company_data["AAPL"]
    service.sec_adapter.company_data["AAPL"] = replace(
        sec_data,
        annual_income_statement=_without_statement_lines(sec_data.annual_income_statement, {"diluted_shares"}),
        annual_balance_sheet=_without_statement_lines(sec_data.annual_balance_sheet, {"shares_outstanding"}),
        quarterly_income_statement=_without_statement_lines(sec_data.quarterly_income_statement, {"diluted_shares"}),
        quarterly_balance_sheet=_without_statement_lines(sec_data.quarterly_balance_sheet, {"shares_outstanding"}),
    )

    dcf = service.get_dcf_model("AAPL")
    reverse = service.get_reverse_valuation("AAPL")

    assert dcf is not None
    assert any("Shares outstanding are unavailable" in warning for warning in dcf.warnings)
    assert all(scenario.summary is not None and scenario.summary.implied_value_per_share is None for scenario in dcf.scenarios)
    assert reverse is not None
    assert reverse.target_equity_value is None
    assert reverse.target_enterprise_value is None
    assert reverse.drivers == []
    assert any("shares outstanding are unavailable" in warning.lower() for warning in reverse.warnings)


def test_fundamentals_peers_degrade_when_peer_price_context_fails(tmp_path):
    service = _build_service(tmp_path)
    service.valuation_adapter = FailingPeerValuationAdapter(
        service.valuation_adapter.price_contexts,
        failing_tickers={"MSFT"},
    )

    peers = service.get_peers("AAPL")

    assert peers is not None
    msft = next(comparison for comparison in peers.comparisons if comparison.ticker == "MSFT")
    assert any("MSFT price context could not be loaded" in warning for warning in msft.warnings)
    assert any(metric.metric_id == "gross_margin" and metric.value is not None for metric in msft.metrics)
    assert any(metric.metric_id == "ev_to_sales" and metric.value is None for metric in msft.metrics)


class StubSecFundamentalsAdapter:
    def __init__(self, company_data: dict[str, SecCompanyData]):
        self.company_data = company_data
        self.results = {
            ticker: FundamentalsSearchResult(
                ticker=ticker,
                name=data.company.name,
                cik=data.company.cik,
                exchange=data.company.exchange,
                source_provider="sec",
                retrieved_at=NOW,
                origin="fundamentals.sec.company_tickers_exchange",
            )
            for ticker, data in company_data.items()
        }

    def search_companies(self, query: str, *, limit: int = 12, force_refresh: bool = False):
        del force_refresh
        normalized = str(query or "").strip().upper()
        rows = list(self.results.values())
        if not normalized:
            return rows[:limit]
        exact = [row for row in rows if row.ticker == normalized]
        prefix = [row for row in rows if row.ticker.startswith(normalized) and row.ticker != normalized]
        by_name = [
            row
            for row in rows
            if normalized in row.name.upper() and row.ticker not in {item.ticker for item in exact}
        ]
        return (exact + prefix + by_name)[:limit]

    def load_company_data(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        return self.company_data.get(str(ticker or "").strip().upper())


class StubIbkrValuationAdapter:
    def __init__(self, price_contexts: dict[str, IbkrPriceContext]):
        self.price_contexts = price_contexts

    def get_price_context(self, ticker: str, *, lookback_days: int = 180, force_refresh: bool = False):
        del lookback_days, force_refresh
        return self.price_contexts[str(ticker or "").strip().upper()]


class FailingPeerValuationAdapter(StubIbkrValuationAdapter):
    def __init__(self, price_contexts: dict[str, IbkrPriceContext], *, failing_tickers: set[str]):
        super().__init__(price_contexts)
        self.failing_tickers = {ticker.upper() for ticker in failing_tickers}

    def get_price_context(self, ticker: str, *, lookback_days: int = 180, force_refresh: bool = False):
        normalized = str(ticker or "").strip().upper()
        if normalized in self.failing_tickers:
            raise RuntimeError("price feed unavailable")
        return super().get_price_context(ticker, lookback_days=lookback_days, force_refresh=force_refresh)


def _build_service(tmp_path) -> FundamentalsService:
    company_data = {
        ticker: _company_data(ticker, name, revenue_scale, price)
        for ticker, name, revenue_scale, price in (
            ("AAPL", "Apple Inc.", 1.00, 190.0),
            ("MSFT", "Microsoft Corporation", 0.82, 420.0),
            ("GOOGL", "Alphabet Inc.", 0.78, 170.0),
            ("AMZN", "Amazon.com, Inc.", 1.35, 185.0),
            ("META", "Meta Platforms, Inc.", 0.48, 510.0),
            ("SAP", "SAP SE", 0.19, 205.0),
            ("FMC", "FMC Corporation", 0.07, 58.0),
            ("CE", "Celanese Corporation", 0.08, 145.0),
            ("DOW", "Dow Inc.", 0.16, 56.0),
            ("EMN", "Eastman Chemical Company", 0.09, 88.0),
            ("DD", "DuPont de Nemours, Inc.", 0.12, 76.0),
            ("ASML", "ASML Holding N.V.", 0.22, 980.0),
            ("AMAT", "Applied Materials, Inc.", 0.18, 210.0),
            ("LRCX", "Lam Research Corporation", 0.13, 930.0),
            ("KLAC", "KLA Corporation", 0.08, 710.0),
            ("TER", "Teradyne, Inc.", 0.04, 125.0),
            ("ONTO", "Onto Innovation Inc.", 0.02, 185.0),
            ("JPM", "JPMorgan Chase & Co.", 0.30, 210.0),
            ("BAC", "Bank of America Corporation", 0.22, 38.0),
            ("WFC", "Wells Fargo & Company", 0.18, 62.0),
            ("C", "Citigroup Inc.", 0.19, 64.0),
            ("PNC", "The PNC Financial Services Group, Inc.", 0.09, 170.0),
            ("NEE", "NextEra Energy, Inc.", 0.11, 74.0),
            ("DUK", "Duke Energy Corporation", 0.10, 108.0),
            ("SO", "The Southern Company", 0.10, 82.0),
            ("AEP", "American Electric Power Company, Inc.", 0.08, 95.0),
            ("EXC", "Exelon Corporation", 0.08, 38.0),
            ("DAL", "Delta Air Lines, Inc.", 0.12, 48.0),
            ("UAL", "United Airlines Holdings, Inc.", 0.11, 55.0),
            ("AAL", "American Airlines Group Inc.", 0.10, 14.0),
            ("LUV", "Southwest Airlines Co.", 0.08, 31.0),
            ("ALK", "Alaska Air Group, Inc.", 0.03, 44.0),
        )
    }
    company_data["ALB"] = _cyclical_alb_data()
    for ticker in ("FMC", "CE", "DOW", "EMN", "DD"):
        company_data[ticker] = _with_company_classification(
            company_data[ticker],
            sic="2821",
            sic_description="Plastic Materials, Synthetic Resins, and Nonvulcanizable Elastomers",
        )
    for ticker in ("ASML", "AMAT", "LRCX", "KLAC", "TER", "ONTO"):
        company_data[ticker] = _with_company_classification(
            company_data[ticker],
            sic="3559",
            sic_description="Special Industry Machinery, Not Elsewhere Classified",
        )
    for ticker in ("JPM", "BAC", "WFC", "C", "PNC"):
        company_data[ticker] = _with_company_classification(
            company_data[ticker],
            sic="6021",
            sic_description="National Commercial Banks",
        )
    for ticker in ("NEE", "DUK", "SO", "AEP", "EXC"):
        company_data[ticker] = _with_company_classification(
            company_data[ticker],
            sic="4911",
            sic_description="Electric Services",
        )
    for ticker in ("DAL", "UAL", "AAL", "LUV", "ALK"):
        company_data[ticker] = _with_company_classification(
            company_data[ticker],
            sic="4512",
            sic_description="Air Transportation, Scheduled",
        )
    price_contexts = {
        ticker: _price_context(ticker, price, scale)
        for ticker, price, scale in (
            ("AAPL", 190.0, 1.00),
            ("MSFT", 420.0, 0.82),
            ("GOOGL", 170.0, 0.78),
            ("AMZN", 185.0, 1.35),
            ("META", 510.0, 0.48),
            ("SAP", 205.0, 0.19),
            ("ALB", 118.0, 0.05),
            ("FMC", 58.0, 0.07),
            ("CE", 145.0, 0.08),
            ("DOW", 56.0, 0.16),
            ("EMN", 88.0, 0.09),
            ("DD", 76.0, 0.12),
            ("ASML", 980.0, 0.22),
            ("AMAT", 210.0, 0.18),
            ("LRCX", 930.0, 0.13),
            ("KLAC", 710.0, 0.08),
            ("TER", 125.0, 0.04),
            ("ONTO", 185.0, 0.02),
            ("JPM", 210.0, 0.30),
            ("BAC", 38.0, 0.22),
            ("WFC", 62.0, 0.18),
            ("C", 64.0, 0.19),
            ("PNC", 170.0, 0.09),
            ("NEE", 74.0, 0.11),
            ("DUK", 108.0, 0.10),
            ("SO", 82.0, 0.10),
            ("AEP", 95.0, 0.08),
            ("EXC", 38.0, 0.08),
            ("DAL", 48.0, 0.12),
            ("UAL", 55.0, 0.11),
            ("AAL", 14.0, 0.10),
            ("LUV", 31.0, 0.08),
            ("ALK", 44.0, 0.03),
        )
    }
    return FundamentalsService(
        sec_adapter=StubSecFundamentalsAdapter(company_data),
        valuation_adapter=StubIbkrValuationAdapter(price_contexts),
        store=FundamentalsResearchStore(tmp_path / "fundamentals"),
    )


def _without_statement_lines(
    view: FundamentalsStatementView,
    line_keys: set[str],
) -> FundamentalsStatementView:
    return replace(view, lines=[line for line in view.lines if line.line_key not in line_keys])


def _with_company_classification(
    sec_data: SecCompanyData,
    *,
    sic: str,
    sic_description: str,
) -> SecCompanyData:
    return replace(
        sec_data,
        company=replace(
            sec_data.company,
            sic=sic,
            sic_description=sic_description,
            classification_labels=[sic_description, sec_data.company.filer_category or "", sec_data.company.exchange or ""],
        ),
    )


def _cyclical_alb_data() -> SecCompanyData:
    periods = [
        _period(f"FY-{year}", f"FY {year}", year, "FY", f"{year}-12-31", form="10-K")
        for year in (2020, 2021, 2022, 2023, 2024)
    ]
    quarterly_periods = [
        _period(f"Q{quarter}-2025-{quarter}", f"Q{quarter} 2025", 2025, f"Q{quarter}", f"2025-0{quarter + 2}-30", form="10-Q")
        for quarter in range(1, 5)
    ]
    revenues = [3_100_000_000.0, 3_300_000_000.0, 7_300_000_000.0, 9_600_000_000.0, 5_400_000_000.0]
    gross_profit = [1_020_000_000.0, 1_150_000_000.0, 2_900_000_000.0, 3_840_000_000.0, 1_300_000_000.0]
    operating_income = [372_000_000.0, 462_000_000.0, 1_752_000_000.0, 2_688_000_000.0, 108_000_000.0]
    net_income = [84_000_000.0, 124_000_000.0, 1_050_000_000.0, 1_573_000_000.0, -45_000_000.0]
    income_tax = [70_000_000.0, 88_000_000.0, 330_000_000.0, 510_000_000.0, 18_000_000.0]
    diluted_shares = [117_000_000.0, 117_000_000.0, 117_500_000.0, 117_600_000.0, 117_700_000.0]
    cash = [720_000_000.0, 680_000_000.0, 1_500_000_000.0, 1_900_000_000.0, 1_100_000_000.0]
    marketable = [0.0 for _ in periods]
    receivables = [420_000_000.0, 460_000_000.0, 930_000_000.0, 1_120_000_000.0, 760_000_000.0]
    inventory = [750_000_000.0, 810_000_000.0, 1_400_000_000.0, 1_580_000_000.0, 1_220_000_000.0]
    current_assets = [2_200_000_000.0, 2_320_000_000.0, 4_600_000_000.0, 5_200_000_000.0, 4_100_000_000.0]
    total_assets = [10_200_000_000.0, 10_700_000_000.0, 15_800_000_000.0, 17_300_000_000.0, 16_100_000_000.0]
    payables = [380_000_000.0, 410_000_000.0, 820_000_000.0, 920_000_000.0, 700_000_000.0]
    short_term_debt = [150_000_000.0, 200_000_000.0, 250_000_000.0, 300_000_000.0, 320_000_000.0]
    current_liabilities = [1_000_000_000.0, 1_060_000_000.0, 1_850_000_000.0, 2_100_000_000.0, 1_900_000_000.0]
    long_term_debt = [2_100_000_000.0, 2_300_000_000.0, 3_400_000_000.0, 3_900_000_000.0, 4_100_000_000.0]
    total_liabilities = [4_200_000_000.0, 4_500_000_000.0, 6_800_000_000.0, 7_500_000_000.0, 7_700_000_000.0]
    equity = [6_000_000_000.0, 6_200_000_000.0, 9_000_000_000.0, 9_800_000_000.0, 8_400_000_000.0]
    shares_outstanding = [117_000_000.0, 117_000_000.0, 117_500_000.0, 117_600_000.0, 117_700_000.0]
    operating_cash_flow = [560_000_000.0, 610_000_000.0, 1_860_000_000.0, 2_420_000_000.0, 420_000_000.0]
    capex = [330_000_000.0, 360_000_000.0, 620_000_000.0, 760_000_000.0, 690_000_000.0]
    da = [260_000_000.0, 275_000_000.0, 360_000_000.0, 410_000_000.0, 430_000_000.0]

    company = FundamentalsCompanyRecord(
        ticker="ALB",
        cik="0000915913",
        name="Albemarle Corporation",
        exchange="NYSE",
        sic="2821",
        sic_description="Plastic Materials, Synthetic Resins, and Nonvulcanizable Elastomers",
        filer_category="Large accelerated filer",
        fiscal_year_end="1231",
        state_of_incorporation="NC",
        phone=None,
        website="https://alb.example.com",
        investor_website="https://investors.alb.example.com",
        description="Albemarle fixture with cyclical lithium trough economics.",
        latest_report_period=_dt("2024-12-31"),
        latest_filing_date=_dt("2025-02-20"),
        classification_labels=["Plastic Materials, Synthetic Resins, and Nonvulcanizable Elastomers", "Large accelerated filer", "NYSE"],
        source_provider="sec",
        retrieved_at=NOW,
        origin="fundamentals.sec.submissions",
        transformation_note="Fixture company metadata.",
    )
    filings = [
        FundamentalsFilingRecord(
            form="10-K",
            filing_date=_dt("2025-02-20"),
            report_period=_dt("2024-12-31"),
            accession_number="ALB-2024",
            is_amendment=False,
            source_provider="sec",
            retrieved_at=NOW,
            origin="fundamentals.sec.submissions.recent_filings",
        )
    ]
    quarter_revenue = [revenues[-1] / 4.0 for _ in quarterly_periods]
    quarter_ebit = [operating_income[-1] / 4.0 for _ in quarterly_periods]
    quarter_tax = [income_tax[-1] / 4.0 for _ in quarterly_periods]
    quarter_net_income = [net_income[-1] / 4.0 for _ in quarterly_periods]
    quarter_gross = [gross_profit[-1] / 4.0 for _ in quarterly_periods]
    return SecCompanyData(
        company=company,
        filings=filings,
        annual_income_statement=_statement_view(
            "income",
            "annual",
            periods,
            {
                "revenue": ("Revenue", "currency", revenues),
                "gross_profit": ("Gross Profit", "currency", gross_profit),
                "operating_income": ("Operating Income", "currency", operating_income),
                "net_income": ("Net Income", "currency", net_income),
                "income_tax": ("Income Tax", "currency", income_tax),
                "diluted_shares": ("Diluted Shares", "shares", diluted_shares),
            },
        ),
        annual_balance_sheet=_statement_view(
            "balance",
            "annual",
            periods,
            {
                "cash_and_equivalents": ("Cash & Equivalents", "currency", cash),
                "marketable_securities_current": ("Current Marketable Securities", "currency", marketable),
                "accounts_receivable": ("Accounts Receivable", "currency", receivables),
                "inventory": ("Inventory", "currency", inventory),
                "current_assets": ("Current Assets", "currency", current_assets),
                "total_assets": ("Total Assets", "currency", total_assets),
                "accounts_payable": ("Accounts Payable", "currency", payables),
                "short_term_debt": ("Short-Term Debt", "currency", short_term_debt),
                "current_liabilities": ("Current Liabilities", "currency", current_liabilities),
                "long_term_debt": ("Long-Term Debt", "currency", long_term_debt),
                "total_liabilities": ("Total Liabilities", "currency", total_liabilities),
                "shareholders_equity": ("Shareholders' Equity", "currency", equity),
                "shares_outstanding": ("Shares Outstanding", "shares", shares_outstanding),
            },
        ),
        annual_cash_flow_statement=_statement_view(
            "cashflow",
            "annual",
            periods,
            {
                "operating_cash_flow": ("Operating Cash Flow", "currency", operating_cash_flow),
                "capital_expenditures": ("Capex", "currency", capex),
                "depreciation_and_amortization": ("D&A", "currency", da),
            },
        ),
        quarterly_income_statement=_statement_view(
            "income",
            "quarterly",
            quarterly_periods,
            {
                "revenue": ("Revenue", "currency", quarter_revenue),
                "gross_profit": ("Gross Profit", "currency", quarter_gross),
                "operating_income": ("Operating Income", "currency", quarter_ebit),
                "net_income": ("Net Income", "currency", quarter_net_income),
                "income_tax": ("Income Tax", "currency", quarter_tax),
                "diluted_shares": ("Diluted Shares", "shares", [diluted_shares[-1] for _ in quarterly_periods]),
            },
        ),
        quarterly_balance_sheet=_statement_view(
            "balance",
            "quarterly",
            quarterly_periods,
            {
                "cash_and_equivalents": ("Cash & Equivalents", "currency", [cash[-1] for _ in quarterly_periods]),
                "marketable_securities_current": ("Current Marketable Securities", "currency", [0.0 for _ in quarterly_periods]),
                "accounts_receivable": ("Accounts Receivable", "currency", [receivables[-1] for _ in quarterly_periods]),
                "inventory": ("Inventory", "currency", [inventory[-1] for _ in quarterly_periods]),
                "current_assets": ("Current Assets", "currency", [current_assets[-1] for _ in quarterly_periods]),
                "total_assets": ("Total Assets", "currency", [total_assets[-1] for _ in quarterly_periods]),
                "accounts_payable": ("Accounts Payable", "currency", [payables[-1] for _ in quarterly_periods]),
                "short_term_debt": ("Short-Term Debt", "currency", [short_term_debt[-1] for _ in quarterly_periods]),
                "current_liabilities": ("Current Liabilities", "currency", [current_liabilities[-1] for _ in quarterly_periods]),
                "long_term_debt": ("Long-Term Debt", "currency", [long_term_debt[-1] for _ in quarterly_periods]),
                "total_liabilities": ("Total Liabilities", "currency", [total_liabilities[-1] for _ in quarterly_periods]),
                "shareholders_equity": ("Shareholders' Equity", "currency", [equity[-1] for _ in quarterly_periods]),
                "shares_outstanding": ("Shares Outstanding", "shares", [shares_outstanding[-1] for _ in quarterly_periods]),
            },
        ),
        quarterly_cash_flow_statement=_statement_view(
            "cashflow",
            "quarterly",
            quarterly_periods,
            {
                "operating_cash_flow": ("Operating Cash Flow", "currency", [operating_cash_flow[-1] / 4.0 for _ in quarterly_periods]),
                "capital_expenditures": ("Capex", "currency", [capex[-1] / 4.0 for _ in quarterly_periods]),
                "depreciation_and_amortization": ("D&A", "currency", [da[-1] / 4.0 for _ in quarterly_periods]),
            },
        ),
    )


def _company_data(ticker: str, name: str, revenue_scale: float, price: float) -> SecCompanyData:
    annual_periods = [
        _period(f"FY-{year}", f"FY {year}", year, "FY", f"{year}-09-30", form="10-K")
        for year in (2022, 2023, 2024)
    ]
    quarterly_periods = [
        _period(f"Q{quarter}-2025-{quarter}", f"Q{quarter} 2025", 2025, f"Q{quarter}", f"2025-0{quarter + 2}-30", form="10-Q")
        for quarter in range(1, 5)
    ]

    revenues = [365_000_000_000.0 * revenue_scale, 383_000_000_000.0 * revenue_scale, 391_000_000_000.0 * revenue_scale]
    gross_profit = [156_000_000_000.0 * revenue_scale, 170_000_000_000.0 * revenue_scale, 177_000_000_000.0 * revenue_scale]
    operating_income = [119_000_000_000.0 * revenue_scale, 123_000_000_000.0 * revenue_scale, 129_000_000_000.0 * revenue_scale]
    net_income = [99_000_000_000.0 * revenue_scale, 97_000_000_000.0 * revenue_scale, 103_000_000_000.0 * revenue_scale]
    income_tax = [19_000_000_000.0 * revenue_scale, 18_000_000_000.0 * revenue_scale, 20_000_000_000.0 * revenue_scale]
    diluted_shares = [16_000_000_000.0, 15_800_000_000.0, 15_600_000_000.0]

    current_assets = [135_000_000_000.0 * revenue_scale, 143_000_000_000.0 * revenue_scale, 152_000_000_000.0 * revenue_scale]
    total_assets = [352_000_000_000.0 * revenue_scale, 364_000_000_000.0 * revenue_scale, 372_000_000_000.0 * revenue_scale]
    current_liabilities = [154_000_000_000.0 * revenue_scale, 149_000_000_000.0 * revenue_scale, 146_000_000_000.0 * revenue_scale]
    equity = [52_000_000_000.0 * revenue_scale, 61_000_000_000.0 * revenue_scale, 68_000_000_000.0 * revenue_scale]
    cash = [48_000_000_000.0 * revenue_scale, 58_000_000_000.0 * revenue_scale, 67_000_000_000.0 * revenue_scale]
    marketable = [24_000_000_000.0 * revenue_scale, 22_000_000_000.0 * revenue_scale, 20_000_000_000.0 * revenue_scale]
    receivables = [29_000_000_000.0 * revenue_scale, 31_000_000_000.0 * revenue_scale, 33_000_000_000.0 * revenue_scale]
    inventory = [5_000_000_000.0 * revenue_scale, 5_200_000_000.0 * revenue_scale, 5_600_000_000.0 * revenue_scale]
    payables = [64_000_000_000.0 * revenue_scale, 61_000_000_000.0 * revenue_scale, 59_000_000_000.0 * revenue_scale]
    short_term_debt = [13_000_000_000.0 * revenue_scale, 12_000_000_000.0 * revenue_scale, 11_000_000_000.0 * revenue_scale]
    long_term_debt = [98_000_000_000.0 * revenue_scale, 95_000_000_000.0 * revenue_scale, 93_000_000_000.0 * revenue_scale]
    total_liabilities = [300_000_000_000.0 * revenue_scale, 303_000_000_000.0 * revenue_scale, 304_000_000_000.0 * revenue_scale]
    shares_outstanding = [15_950_000_000.0, 15_700_000_000.0, 15_500_000_000.0]

    operating_cash_flow = [122_000_000_000.0 * revenue_scale, 128_000_000_000.0 * revenue_scale, 134_000_000_000.0 * revenue_scale]
    capex = [11_000_000_000.0 * revenue_scale, 10_000_000_000.0 * revenue_scale, 10_500_000_000.0 * revenue_scale]
    da = [11_500_000_000.0 * revenue_scale, 12_000_000_000.0 * revenue_scale, 12_400_000_000.0 * revenue_scale]

    quarter_revenue = [revenue / 4.0 for revenue in revenues[-1:] * 4]
    quarter_ebit = [operating_income[-1] / 4.0 * factor for factor in (0.94, 0.98, 1.01, 1.07)]
    quarter_net_income = [net_income[-1] / 4.0 * factor for factor in (0.95, 0.99, 1.0, 1.06)]
    quarter_tax = [income_tax[-1] / 4.0 for _ in quarterly_periods]
    quarter_gross = [gross_profit[-1] / 4.0 * factor for factor in (0.97, 0.99, 1.0, 1.04)]
    quarter_cashflow = [operating_cash_flow[-1] / 4.0 * factor for factor in (0.9, 0.95, 1.0, 1.15)]
    quarter_capex = [capex[-1] / 4.0 * factor for factor in (0.95, 1.0, 1.02, 1.03)]
    quarter_da = [da[-1] / 4.0 for _ in quarterly_periods]
    quarter_cash = [cash[-1] * factor for factor in (0.92, 0.95, 0.98, 1.0)]
    quarter_marketable = [marketable[-1] * factor for factor in (1.0, 1.0, 1.0, 1.0)]
    quarter_receivables = [receivables[-1] * factor for factor in (0.95, 0.97, 0.99, 1.0)]
    quarter_inventory = [inventory[-1] * factor for factor in (0.98, 1.0, 1.02, 1.03)]
    quarter_current_assets = [current_assets[-1] * factor for factor in (0.95, 0.97, 0.99, 1.0)]
    quarter_total_assets = [total_assets[-1] * factor for factor in (0.97, 0.98, 0.99, 1.0)]
    quarter_payables = [payables[-1] * factor for factor in (1.03, 1.02, 1.01, 1.0)]
    quarter_short_debt = [short_term_debt[-1] for _ in quarterly_periods]
    quarter_current_liabilities = [current_liabilities[-1] * factor for factor in (1.02, 1.01, 1.0, 0.99)]
    quarter_long_debt = [long_term_debt[-1] for _ in quarterly_periods]
    quarter_total_liabilities = [total_liabilities[-1] * factor for factor in (1.01, 1.01, 1.0, 1.0)]
    quarter_equity = [equity[-1] * factor for factor in (0.98, 0.99, 1.0, 1.01)]
    quarter_shares = [shares_outstanding[-1] for _ in quarterly_periods]
    quarter_diluted = [diluted_shares[-1] for _ in quarterly_periods]

    company = FundamentalsCompanyRecord(
        ticker=ticker,
        cik=f"0000{hash(ticker) % 10_000_000:07d}",
        name=name,
        exchange="Nasdaq",
        sic="3571",
        sic_description="Electronic Computers",
        filer_category="Large accelerated filer",
        fiscal_year_end="0930",
        state_of_incorporation="CA",
        phone=None,
        website=f"https://{ticker.lower()}.example.com",
        investor_website=f"https://investors.{ticker.lower()}.example.com",
        description=f"{name} files as a US SEC issuer and is used here as a fundamentals service test fixture.",
        latest_report_period=_dt("2024-09-30"),
        latest_filing_date=_dt("2024-11-01"),
        classification_labels=["Electronic Computers", "Large accelerated filer", "Nasdaq"],
        source_provider="sec",
        retrieved_at=NOW,
        origin="fundamentals.sec.submissions",
        transformation_note="Fixture company metadata.",
    )
    filings = [
        FundamentalsFilingRecord(
            form=form,
            filing_date=_dt(filed),
            report_period=_dt(report),
            accession_number=f"{ticker}-{index}",
            is_amendment=False,
            source_provider="sec",
            retrieved_at=NOW,
            origin="fundamentals.sec.submissions.recent_filings",
        )
        for index, (form, report, filed) in enumerate(
            (
                ("10-K", "2024-09-30", "2024-11-01"),
                ("10-Q", "2024-06-30", "2024-08-02"),
                ("10-Q", "2024-03-31", "2024-05-03"),
                ("10-Q", "2023-12-31", "2024-02-02"),
            ),
            start=1,
        )
    ]
    return SecCompanyData(
        company=company,
        filings=filings,
        annual_income_statement=_statement_view(
            "income",
            "annual",
            annual_periods,
            {
                "revenue": ("Revenue", "currency", revenues),
                "gross_profit": ("Gross Profit", "currency", gross_profit),
                "operating_income": ("Operating Income", "currency", operating_income),
                "net_income": ("Net Income", "currency", net_income),
                "income_tax": ("Income Tax", "currency", income_tax),
                "diluted_shares": ("Diluted Shares", "shares", diluted_shares),
            },
        ),
        annual_balance_sheet=_statement_view(
            "balance",
            "annual",
            annual_periods,
            {
                "cash_and_equivalents": ("Cash & Equivalents", "currency", cash),
                "marketable_securities_current": ("Current Marketable Securities", "currency", marketable),
                "accounts_receivable": ("Accounts Receivable", "currency", receivables),
                "inventory": ("Inventory", "currency", inventory),
                "current_assets": ("Current Assets", "currency", current_assets),
                "total_assets": ("Total Assets", "currency", total_assets),
                "accounts_payable": ("Accounts Payable", "currency", payables),
                "short_term_debt": ("Short-Term Debt", "currency", short_term_debt),
                "current_liabilities": ("Current Liabilities", "currency", current_liabilities),
                "long_term_debt": ("Long-Term Debt", "currency", long_term_debt),
                "total_liabilities": ("Total Liabilities", "currency", total_liabilities),
                "shareholders_equity": ("Shareholders' Equity", "currency", equity),
                "shares_outstanding": ("Shares Outstanding", "shares", shares_outstanding),
            },
        ),
        annual_cash_flow_statement=_statement_view(
            "cashflow",
            "annual",
            annual_periods,
            {
                "operating_cash_flow": ("Operating Cash Flow", "currency", operating_cash_flow),
                "capital_expenditures": ("Capex", "currency", capex),
                "depreciation_and_amortization": ("D&A", "currency", da),
            },
        ),
        quarterly_income_statement=_statement_view(
            "income",
            "quarterly",
            quarterly_periods,
            {
                "revenue": ("Revenue", "currency", quarter_revenue),
                "gross_profit": ("Gross Profit", "currency", quarter_gross),
                "operating_income": ("Operating Income", "currency", quarter_ebit),
                "net_income": ("Net Income", "currency", quarter_net_income),
                "income_tax": ("Income Tax", "currency", quarter_tax),
                "diluted_shares": ("Diluted Shares", "shares", quarter_diluted),
            },
        ),
        quarterly_balance_sheet=_statement_view(
            "balance",
            "quarterly",
            quarterly_periods,
            {
                "cash_and_equivalents": ("Cash & Equivalents", "currency", quarter_cash),
                "marketable_securities_current": ("Current Marketable Securities", "currency", quarter_marketable),
                "accounts_receivable": ("Accounts Receivable", "currency", quarter_receivables),
                "inventory": ("Inventory", "currency", quarter_inventory),
                "current_assets": ("Current Assets", "currency", quarter_current_assets),
                "total_assets": ("Total Assets", "currency", quarter_total_assets),
                "accounts_payable": ("Accounts Payable", "currency", quarter_payables),
                "short_term_debt": ("Short-Term Debt", "currency", quarter_short_debt),
                "current_liabilities": ("Current Liabilities", "currency", quarter_current_liabilities),
                "long_term_debt": ("Long-Term Debt", "currency", quarter_long_debt),
                "total_liabilities": ("Total Liabilities", "currency", quarter_total_liabilities),
                "shareholders_equity": ("Shareholders' Equity", "currency", quarter_equity),
                "shares_outstanding": ("Shares Outstanding", "shares", quarter_shares),
            },
        ),
        quarterly_cash_flow_statement=_statement_view(
            "cashflow",
            "quarterly",
            quarterly_periods,
            {
                "operating_cash_flow": ("Operating Cash Flow", "currency", quarter_cashflow),
                "capital_expenditures": ("Capex", "currency", quarter_capex),
                "depreciation_and_amortization": ("D&A", "currency", quarter_da),
            },
        ),
    )


def _price_context(ticker: str, price: float, scale: float) -> IbkrPriceContext:
    return IbkrPriceContext(
        ticker=ticker,
        current_price=price,
        price_history=[
            FundamentalsPricePoint(
                timestamp=_dt("2026-01-09"),
                price=price * 0.92,
                source_provider="ibkr",
                retrieved_at=NOW,
                origin="fundamentals.ibkr.history",
            ),
            FundamentalsPricePoint(
                timestamp=_dt("2026-03-09"),
                price=price * 0.97,
                source_provider="ibkr",
                retrieved_at=NOW,
                origin="fundamentals.ibkr.history",
            ),
            FundamentalsPricePoint(
                timestamp=_dt("2026-04-09"),
                price=price,
                source_provider="ibkr",
                retrieved_at=NOW,
                origin="fundamentals.ibkr.snapshot",
                transformation_note=f"Fixture price context scale {scale:.2f}.",
            ),
        ],
        warnings=[],
        source_provider="ibkr",
        retrieved_at=NOW,
        origin="fundamentals.ibkr.snapshot",
        transformation_note="Fixture price context.",
    )


def _facts_dataframe_for_quarterly_normalization() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 400.0, "USD", "2023-10-01", "2024-09-28", 2024, "FY", "10-K", "2024-11-01"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 400.0, "USD", "2023-10-01", "2024-09-28", 2025, "FY", "10-K", "2025-10-31"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 100.0, "USD", "2024-09-29", "2024-12-28", 2025, "Q1", "10-Q", "2025-01-31"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 100.0, "USD", "2024-09-29", "2024-12-28", 2026, "Q1", "10-Q", "2026-01-30"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 210.0, "USD", "2024-09-29", "2025-03-29", 2025, "Q2", "10-Q", "2025-05-02"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 110.0, "USD", "2024-12-29", "2025-03-29", 2025, "Q2", "10-Q", "2025-05-02"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 330.0, "USD", "2024-09-29", "2025-06-28", 2025, "Q3", "10-Q", "2025-08-01"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 120.0, "USD", "2025-03-30", "2025-06-28", 2025, "Q3", "10-Q", "2025-08-01"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 460.0, "USD", "2024-09-29", "2025-09-27", 2025, "FY", "10-K", "2025-10-31"),
            _fact_row("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", 140.0, "USD", "2025-09-28", "2025-12-27", 2026, "Q1", "10-Q", "2026-01-30"),
            _fact_row("us-gaap:NetCashProvidedByUsedInOperatingActivities", 150.0, "USD", "2023-10-01", "2024-09-28", 2024, "FY", "10-K", "2024-11-01"),
            _fact_row("us-gaap:NetCashProvidedByUsedInOperatingActivities", 30.0, "USD", "2024-09-29", "2024-12-28", 2025, "Q1", "10-Q", "2025-01-31"),
            _fact_row("us-gaap:NetCashProvidedByUsedInOperatingActivities", 30.0, "USD", "2024-09-29", "2024-12-28", 2026, "Q1", "10-Q", "2026-01-30"),
            _fact_row("us-gaap:NetCashProvidedByUsedInOperatingActivities", 70.0, "USD", "2024-09-29", "2025-03-29", 2025, "Q2", "10-Q", "2025-05-02"),
            _fact_row("us-gaap:NetCashProvidedByUsedInOperatingActivities", 120.0, "USD", "2024-09-29", "2025-06-28", 2025, "Q3", "10-Q", "2025-08-01"),
            _fact_row("us-gaap:NetCashProvidedByUsedInOperatingActivities", 170.0, "USD", "2024-09-29", "2025-09-27", 2025, "FY", "10-K", "2025-10-31"),
            _fact_row("us-gaap:NetCashProvidedByUsedInOperatingActivities", 50.0, "USD", "2025-09-28", "2025-12-27", 2026, "Q1", "10-Q", "2026-01-30"),
            _fact_row("us-gaap:AssetsCurrent", 530.0, "USD", None, "2024-09-28", 2024, "FY", "10-K", "2024-11-01"),
            _fact_row("us-gaap:AssetsCurrent", 500.0, "USD", None, "2024-12-28", 2025, "Q1", "10-Q", "2025-01-31"),
            _fact_row("us-gaap:AssetsCurrent", 520.0, "USD", None, "2025-03-29", 2025, "Q2", "10-Q", "2025-05-02"),
            _fact_row("us-gaap:AssetsCurrent", 540.0, "USD", None, "2025-06-28", 2025, "Q3", "10-Q", "2025-08-01"),
            _fact_row("us-gaap:AssetsCurrent", 560.0, "USD", None, "2025-09-27", 2025, "FY", "10-K", "2025-10-31"),
            _fact_row("us-gaap:AssetsCurrent", 560.0, "USD", None, "2025-09-27", 2026, "Q1", "10-Q", "2026-01-30"),
            _fact_row("us-gaap:AssetsCurrent", 580.0, "USD", None, "2025-12-27", 2026, "Q1", "10-Q", "2026-01-30"),
        ]
    )


def _fact_row(
    concept: str,
    value: float,
    unit: str,
    start: str | None,
    end: str,
    fiscal_year: int,
    fiscal_period: str,
    form: str,
    filed: str,
) -> dict:
    return {
        "concept": concept,
        "label": concept.split(":", 1)[-1],
        "numeric_value": value,
        "unit": unit,
        "period_start": start,
        "period_end": end,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "filing_date": filed,
        "form_type": form,
        "accession": f"{concept}-{fiscal_year}-{fiscal_period}-{end}",
        "statement_type": None,
    }


def _period(period_key: str, label: str, fiscal_year: int, fiscal_period: str, end_date: str, *, form: str) -> FundamentalsPeriodRecord:
    return FundamentalsPeriodRecord(
        period_key=period_key,
        label=label,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        start_date=_dt(f"{fiscal_year - 1 if fiscal_period == 'FY' else fiscal_year}-01-01"),
        end_date=_dt(end_date),
        filing_date=_dt(end_date),
        form=form,
        accession_number=f"{period_key}-{form}",
        is_amendment=False,
        source_provider="sec",
        retrieved_at=NOW,
        origin="fundamentals.test.period",
    )


def _statement_view(
    statement: str,
    basis: str,
    periods: list[FundamentalsPeriodRecord],
    rows: dict[str, tuple[str, str, list[float | None]]],
) -> FundamentalsStatementView:
    return FundamentalsStatementView(
        statement=statement,
        basis=basis,
        periods=periods,
        lines=[
            FundamentalsStatementLine(
                line_key=line_key,
                label=label,
                statement=statement,
                unit=unit,
                cells=[
                    FundamentalsStatementCell(
                        period_key=period.period_key,
                        value=value,
                        display_value=_display_value(value, unit),
                        start_date=period.start_date,
                        end_date=period.end_date,
                        filing_date=period.filing_date,
                        form=period.form,
                        accession_number=period.accession_number,
                        is_amendment=False,
                        concept_name=f"test:{line_key}",
                        source_provider="sec",
                        retrieved_at=NOW,
                        origin=f"fundamentals.test.{statement}.{line_key}",
                    )
                    for period, value in zip(periods, values, strict=False)
                ],
                source_provider="sec",
                retrieved_at=NOW,
                origin=f"fundamentals.test.{statement}.{line_key}",
            )
            for line_key, (label, unit, values) in rows.items()
        ],
        source_provider="sec",
        retrieved_at=NOW,
        origin=f"fundamentals.test.{statement}.{basis}",
    )


def _display_value(value: float | None, unit: str) -> str:
    if value is None:
        return "N/A"
    if unit == "shares":
        return f"{value:,.0f}"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:,.0f}"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(f"{value}T00:00:00+00:00")
