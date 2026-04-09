from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

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
from src.services.fundamentals_adapters import IbkrPriceContext, SecCompanyData
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
        )
    }
    price_contexts = {
        ticker: _price_context(ticker, price, scale)
        for ticker, price, scale in (
            ("AAPL", 190.0, 1.00),
            ("MSFT", 420.0, 0.82),
            ("GOOGL", 170.0, 0.78),
            ("AMZN", 185.0, 1.35),
            ("META", 510.0, 0.48),
            ("SAP", 205.0, 0.19),
        )
    }
    return FundamentalsService(
        sec_adapter=StubSecFundamentalsAdapter(company_data),
        valuation_adapter=StubIbkrValuationAdapter(price_contexts),
        store=FundamentalsResearchStore(tmp_path / "fundamentals"),
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
