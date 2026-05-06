from __future__ import annotations

import os
import re
from html import unescape
from html.parser import HTMLParser
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

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
from src.models.instruments import InstrumentReference
from src.services.cache import CacheService
from src.services.data_providers import ResearchDataProvider, contract_for_instrument
from src.services.market_data import MarketDataService

if TYPE_CHECKING:
    from edgar import Company


_ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
_QUARTERLY_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "6-K"}
_FILING_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K")
_CURRENCY_UNIT_PREFIXES = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CNY",
    "TWD",
    "CAD",
    "AUD",
    "CHF",
    "HKD",
    "KRW",
    "INR",
    "BRL",
    "MXN",
    "SEK",
    "DKK",
    "NOK",
    "SGD",
    "ZAR",
)

_POPULAR_FUNDAMENTALS_TICKERS = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "ORCL", "SAP")

_STATEMENT_PERIOD_ANCHORS: dict[str, tuple[str, ...]] = {
    "income": ("revenue", "operating_income", "net_income"),
    "balance": ("current_assets", "total_assets", "shareholders_equity"),
    "cashflow": ("operating_cash_flow", "capital_expenditures", "depreciation_and_amortization"),
}


@dataclass(frozen=True)
class StatementLineDefinition:
    line_key: str
    label: str
    statement: str
    unit: str
    period_kind: str
    concepts: tuple[str, ...]
    quarterly_derivable: bool = True


@dataclass(frozen=True)
class FactObservation:
    concept_name: str
    value: float
    start_date: datetime | None
    end_date: datetime | None
    filing_date: datetime | None
    filing_date_text: str | None
    form: str | None
    accession_number: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    frame: str | None
    is_amendment: bool
    source_provider: str = "sec"
    transformation_note: str | None = None


@dataclass(frozen=True)
class SecCompanyData:
    company: FundamentalsCompanyRecord
    filings: list[FundamentalsFilingRecord]
    annual_income_statement: FundamentalsStatementView
    annual_balance_sheet: FundamentalsStatementView
    annual_cash_flow_statement: FundamentalsStatementView
    quarterly_income_statement: FundamentalsStatementView
    quarterly_balance_sheet: FundamentalsStatementView
    quarterly_cash_flow_statement: FundamentalsStatementView


@dataclass(frozen=True)
class IbkrPriceContext:
    ticker: str
    current_price: float | None
    price_history: list[FundamentalsPricePoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class SecFilingBusinessSection:
    filing: FundamentalsFilingRecord
    section_text: str
    source_url: str
    section: str = "Item 1. Business"
    source_provider: str = "sec"
    retrieved_at: datetime | None = None
    origin: str = "fundamentals.sec.filing.item_1"
    transformation_note: str | None = None


class _SecHtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.lower()
        if normalized in {"script", "style", "head", "noscript"}:
            self._skip_depth += 1
        if normalized in {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "head", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if normalized in {"p", "div", "tr", "li", "table", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = unescape(data or "").strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return _normalize_filing_text(" ".join(self._chunks))


_STATEMENT_LINE_DEFINITIONS: tuple[StatementLineDefinition, ...] = (
    StatementLineDefinition(
        "revenue",
        "Revenue",
        "income",
        "currency",
        "duration",
        (
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:Revenues",
            "us-gaap:SalesRevenueNet",
            "ifrs-full:Revenue",
        ),
    ),
    StatementLineDefinition("gross_profit", "Gross Profit", "income", "currency", "duration", ("us-gaap:GrossProfit",)),
    StatementLineDefinition(
        "research_and_development",
        "R&D",
        "income",
        "currency",
        "duration",
        ("us-gaap:ResearchAndDevelopmentExpense", "ifrs-full:ResearchAndDevelopmentExpense"),
    ),
    StatementLineDefinition(
        "selling_general_and_administrative",
        "SG&A",
        "income",
        "currency",
        "duration",
        ("us-gaap:SellingGeneralAndAdministrativeExpense", "ifrs-full:SellingGeneralAndAdministrativeExpense"),
    ),
    StatementLineDefinition("operating_expenses", "Operating Expenses", "income", "currency", "duration", ("us-gaap:OperatingExpenses", "ifrs-full:OperatingExpense")),
    StatementLineDefinition("operating_income", "Operating Income", "income", "currency", "duration", ("us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities")),
    StatementLineDefinition("pretax_income", "Pre-Tax Income", "income", "currency", "duration", ("us-gaap:IncomeBeforeTaxExpenseBenefit", "ifrs-full:ProfitLossBeforeTax")),
    StatementLineDefinition("income_tax", "Income Tax", "income", "currency", "duration", ("us-gaap:IncomeTaxExpenseBenefit", "ifrs-full:IncomeTaxExpenseContinuingOperations", "ifrs-full:TaxExpenseIncome")),
    StatementLineDefinition("net_income", "Net Income", "income", "currency", "duration", ("us-gaap:NetIncomeLoss", "ifrs-full:ProfitLoss")),
    StatementLineDefinition(
        "diluted_shares",
        "Diluted Shares",
        "income",
        "shares",
        "duration",
        (
            "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
            "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
            "ifrs-full:DilutedWeightedAverageNumberOfOrdinaryShares",
            "ifrs-full:AdjustedWeightedAverageShares",
        ),
        quarterly_derivable=False,
    ),
    StatementLineDefinition("cash_and_equivalents", "Cash & Equivalents", "balance", "currency", "instant", ("us-gaap:CashAndCashEquivalentsAtCarryingValue", "ifrs-full:CashAndCashEquivalents")),
    StatementLineDefinition(
        "marketable_securities_current",
        "Current Marketable Securities",
        "balance",
        "currency",
        "instant",
        ("us-gaap:MarketableSecuritiesCurrent", "us-gaap:AvailableForSaleSecuritiesCurrent", "ifrs-full:CurrentFinancialAssets"),
    ),
    StatementLineDefinition("accounts_receivable", "Accounts Receivable", "balance", "currency", "instant", ("us-gaap:AccountsReceivableNetCurrent", "ifrs-full:TradeAndOtherCurrentReceivables")),
    StatementLineDefinition("inventory", "Inventory", "balance", "currency", "instant", ("us-gaap:InventoryNet", "ifrs-full:Inventories")),
    StatementLineDefinition("current_assets", "Current Assets", "balance", "currency", "instant", ("us-gaap:AssetsCurrent", "ifrs-full:CurrentAssets")),
    StatementLineDefinition("total_assets", "Total Assets", "balance", "currency", "instant", ("us-gaap:Assets", "ifrs-full:Assets")),
    StatementLineDefinition("accounts_payable", "Accounts Payable", "balance", "currency", "instant", ("us-gaap:AccountsPayableCurrent", "ifrs-full:TradeAndOtherCurrentPayables")),
    StatementLineDefinition(
        "short_term_debt",
        "Short-Term Debt",
        "balance",
        "currency",
        "instant",
        ("us-gaap:LongTermDebtCurrent", "us-gaap:ShortTermBorrowings", "us-gaap:CommercialPaper", "ifrs-full:CurrentBorrowings", "ifrs-full:CurrentLeaseLiabilities"),
    ),
    StatementLineDefinition("current_liabilities", "Current Liabilities", "balance", "currency", "instant", ("us-gaap:LiabilitiesCurrent", "ifrs-full:CurrentLiabilities")),
    StatementLineDefinition(
        "long_term_debt",
        "Long-Term Debt",
        "balance",
        "currency",
        "instant",
        ("us-gaap:LongTermDebtAndCapitalLeaseObligations", "us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt", "ifrs-full:NoncurrentBorrowings", "ifrs-full:NoncurrentLeaseLiabilities"),
    ),
    StatementLineDefinition("total_liabilities", "Total Liabilities", "balance", "currency", "instant", ("us-gaap:Liabilities", "ifrs-full:Liabilities")),
    StatementLineDefinition(
        "shareholders_equity",
        "Shareholders' Equity",
        "balance",
        "currency",
        "instant",
        ("us-gaap:StockholdersEquity", "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "ifrs-full:Equity", "ifrs-full:EquityAttributableToOwnersOfParent"),
    ),
    StatementLineDefinition(
        "shares_outstanding",
        "Shares Outstanding",
        "balance",
        "shares",
        "instant",
        ("dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding", "ifrs-full:NumberOfSharesOutstanding"),
    ),
    StatementLineDefinition(
        "operating_cash_flow",
        "Operating Cash Flow",
        "cashflow",
        "currency",
        "duration",
        ("us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "us-gaap:NetCashProvidedByUsedInOperatingActivities", "ifrs-full:CashFlowsFromUsedInOperatingActivities"),
    ),
    StatementLineDefinition(
        "capital_expenditures",
        "Capex",
        "cashflow",
        "currency",
        "duration",
        ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:PropertyPlantAndEquipmentAdditions", "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
    ),
    StatementLineDefinition(
        "depreciation_and_amortization",
        "D&A",
        "cashflow",
        "currency",
        "duration",
        ("us-gaap:DepreciationDepletionAndAmortization", "us-gaap:Depreciation", "ifrs-full:DepreciationAndAmortisationExpense"),
    ),
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        if "T" in text:
            parsed = datetime.fromisoformat(text)
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sortable_datetime(value: datetime | None) -> datetime:
    return value or datetime(1900, 1, 1, tzinfo=timezone.utc)


def _duration_days(start_date: datetime | None, end_date: datetime | None) -> int | None:
    if start_date is None or end_date is None:
        return None
    return max((end_date.date() - start_date.date()).days, 0)


def _year(value: datetime | None) -> int | None:
    return value.year if value is not None else None


def _index_value(values: Any, index: int) -> str | None:
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    text = str(value).strip()
    return text or None


def _first_string(values: Any) -> str | None:
    if not isinstance(values, list):
        return None
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return None


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_pydatetime"):
        converted = value.to_pydatetime()
        return converted.astimezone(timezone.utc) if converted.tzinfo else converted.replace(tzinfo=timezone.utc)
    return _parse_datetime(value) or now_utc()


def _format_statement_value(value: float | None, unit: str) -> str:
    if value is None:
        return "N/A"
    if unit == "shares":
        return f"{value:,.0f}"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def _normalize_filing_text(value: str) -> str:
    text = unescape(value or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?i)\btable of contents\b", " ", text)
    return text.strip()


def _extract_visible_text_from_html(html: str) -> str:
    parser = _SecHtmlTextParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return _normalize_filing_text(re.sub(r"<[^>]+>", " ", html or ""))
    return parser.text()


def _extract_item_1_business_text(html: str, *, max_chars: int = 24_000) -> str | None:
    text = _extract_visible_text_from_html(html)
    if not text:
        return None
    start_patterns = (
        r"(?i)\bitem\s+1[\.\-:\s]+business\b",
        r"(?i)\bpart\s+i[\.\-:\s]+item\s+1[\.\-:\s]+business\b",
        r"(?i)\bbusiness\s+overview\b",
    )
    end_patterns = (
        r"(?i)\bitem\s+1a[\.\-:\s]+risk\s+factors\b",
        r"(?i)\bitem\s+1b[\.\-:\s]+unresolved\b",
        r"(?i)\bitem\s+2[\.\-:\s]+properties\b",
    )
    start_matches = sorted(
        [match for pattern in start_patterns for match in re.finditer(pattern, text)],
        key=lambda match: match.start(),
    )
    for start_match in start_matches:
        section_start = start_match.start()
        section_body_start = start_match.end()
        end_indexes = [
            section_body_start + match.start()
            for pattern in end_patterns
            if (match := re.search(pattern, text[section_body_start:]))
        ]
        section_end = min(end_indexes) if end_indexes else len(text)
        section = _normalize_filing_text(text[section_start:section_end])
        if len(section) >= 800:
            return section[:max_chars]
    return None


def _load_edgar_tools() -> tuple[Any, Any, Any]:
    from edgar import Company, set_identity
    from edgar.reference.tickers import get_company_tickers

    return Company, set_identity, get_company_tickers


class SecFundamentalsAdapter:
    def __init__(self, cache: CacheService) -> None:
        self.cache = cache
        # TODO: Replace this development-time SEC identity fallback with a user-configurable Gamma setting.
        self.identity_name = os.getenv("GAMMA_SEC_USER_NAME", "").strip() or "Gorka Bravo"
        self.identity_email = (
            os.getenv("GAMMA_SEC_USER_EMAIL", "").strip() or "gorka.bravo1@gmail.com"
        )
        self._reference_rows: list[dict[str, str | None]] | None = None
        self._reference_retrieved_at: datetime | None = None
        self._company_cache: dict[str, SecCompanyData] = {}
        self._edgar_configured = False

    def _configure_edgar_tools(self) -> None:
        if self._edgar_configured:
            return
        _, set_identity, _ = _load_edgar_tools()
        identity = f"{self.identity_name} {self.identity_email}".strip()
        os.environ["EDGAR_IDENTITY"] = identity
        set_identity(identity)
        self._edgar_configured = True

    def search_companies(
        self,
        query: str,
        *,
        limit: int = 12,
        force_refresh: bool = False,
    ) -> list[FundamentalsSearchResult]:
        rows = list(self._load_reference_rows(force_refresh=force_refresh))
        query_text = str(query or "").strip().upper()
        if query_text:
            exact_ticker = [row for row in rows if row["ticker"] == query_text]
            exact_cik = [row for row in rows if row["cik"] == query_text.zfill(10)]
            prefix_matches = [
                row for row in rows if row["ticker"].startswith(query_text) and row["ticker"] != query_text
            ]
            name_matches = [
                row
                for row in rows
                if query_text in row["name_upper"]
                and row["ticker"] not in {item["ticker"] for item in [*exact_ticker, *exact_cik]}
            ]
            cik_prefix_matches = [
                row
                for row in rows
                if row["cik"].startswith(query_text)
                and row["ticker"] not in {item["ticker"] for item in [*exact_ticker, *exact_cik, *prefix_matches]}
            ]
            rows = exact_ticker + exact_cik + prefix_matches + cik_prefix_matches + name_matches
            if not rows:
                company = self._load_company(query_text)
                if company is not None:
                    rows = [self._search_row_from_company(company, requested_ticker=query_text)]
        else:
            preferred = [row for row in rows if row["ticker"] in _POPULAR_FUNDAMENTALS_TICKERS]
            preferred_tickers = {row["ticker"] for row in preferred}
            rows = preferred + [row for row in rows if row["ticker"] not in preferred_tickers]
        retrieved_at = self._reference_retrieved_at or now_utc()
        results: list[FundamentalsSearchResult] = []
        for row in rows[: max(1, min(limit, 40))]:
            results.append(
                FundamentalsSearchResult(
                    ticker=row["ticker"],
                    name=row["name"],
                    cik=row["cik"],
                    exchange=row.get("exchange"),
                    source_provider="sec",
                    retrieved_at=retrieved_at,
                    origin="fundamentals.sec.reference_tickers",
                    transformation_note=(
                        "Gamma resolves SEC filers through EdgarTools reference data, which prefers bundled ticker mappings and falls back to SEC-hosted reference data when needed."
                    ),
                )
            )
        return results

    def load_company_data(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> SecCompanyData | None:
        requested_ticker = str(ticker or "").strip().upper()
        if not requested_ticker:
            return None
        if force_refresh:
            self._company_cache.pop(requested_ticker, None)
        cached = self._company_cache.get(requested_ticker)
        if cached is not None:
            return cached

        company = self._load_company(requested_ticker)
        if company is None:
            return None

        retrieved_at = now_utc()
        filings = self._build_filing_history(company, retrieved_at=retrieved_at)
        facts_df = self._load_facts_dataframe(company)
        primary_ticker = self._primary_ticker(company, requested_ticker=requested_ticker)
        result = SecCompanyData(
            company=self._build_company_record(
                company,
                filings,
                retrieved_at=retrieved_at,
                primary_ticker=primary_ticker,
            ),
            filings=filings,
            annual_income_statement=self._build_statement_view(
                facts_df,
                statement="income",
                basis="annual",
                retrieved_at=retrieved_at,
            ),
            annual_balance_sheet=self._build_statement_view(
                facts_df,
                statement="balance",
                basis="annual",
                retrieved_at=retrieved_at,
            ),
            annual_cash_flow_statement=self._build_statement_view(
                facts_df,
                statement="cashflow",
                basis="annual",
                retrieved_at=retrieved_at,
            ),
            quarterly_income_statement=self._build_statement_view(
                facts_df,
                statement="income",
                basis="quarterly",
                retrieved_at=retrieved_at,
            ),
            quarterly_balance_sheet=self._build_statement_view(
                facts_df,
                statement="balance",
                basis="quarterly",
                retrieved_at=retrieved_at,
            ),
            quarterly_cash_flow_statement=self._build_statement_view(
                facts_df,
                statement="cashflow",
                basis="quarterly",
                retrieved_at=retrieved_at,
            ),
        )
        self._company_cache[requested_ticker] = result
        return result

    def load_business_section(
        self,
        company: FundamentalsCompanyRecord,
        filings: list[FundamentalsFilingRecord],
        *,
        force_refresh: bool = False,
    ) -> SecFilingBusinessSection | None:
        del force_refresh
        annual = next(
            (
                filing
                for filing in filings
                if filing.form in _ANNUAL_FORMS
                and filing.accession_number
                and filing.primary_document
            ),
            None,
        )
        if annual is None:
            return None
        source_url = self._filing_document_url(company.cik, annual.accession_number, annual.primary_document)
        if source_url is None:
            return None
        retrieved_at = now_utc()
        try:
            request = Request(
                source_url,
                headers={
                    "User-Agent": f"{self.identity_name} {self.identity_email}".strip(),
                    "Accept-Encoding": "identity",
                },
            )
            with urlopen(request, timeout=20) as response:
                raw = response.read()
        except (HTTPError, URLError, TimeoutError, OSError):
            return None
        section_text = _extract_item_1_business_text(raw.decode("utf-8", errors="ignore"))
        if not section_text:
            return None
        return SecFilingBusinessSection(
            filing=annual,
            section_text=section_text,
            source_url=source_url,
            retrieved_at=retrieved_at,
            transformation_note="Gamma extracts Item 1. Business text from the latest annual SEC filing HTML before any model summary is generated.",
        )

    @staticmethod
    def _filing_document_url(cik: str | None, accession_number: str | None, primary_document: str | None) -> str | None:
        cik_digits = re.sub(r"\D+", "", str(cik or "")).lstrip("0")
        accession = re.sub(r"[^0-9A-Za-z-]+", "", str(accession_number or ""))
        document = str(primary_document or "").strip().lstrip("/")
        if not cik_digits or not accession or not document:
            return None
        accession_path = accession.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/{accession_path}/{document}"

    def _load_reference_rows(self, *, force_refresh: bool) -> list[dict[str, str | None]]:
        if self._reference_rows is not None and not force_refresh:
            return self._reference_rows
        _, _, get_company_tickers = _load_edgar_tools()
        df = get_company_tickers(as_dataframe=True, clean_name=False, clean_suffix=False)
        rows: list[dict[str, str | None]] = []
        for record in df.to_dict(orient="records"):
            ticker = str(record.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            name = str(record.get("company") or "").strip() or ticker
            exchange_text = str(record.get("exchange") or "").strip() or None
            cik_text = str(record.get("cik") or "").strip()
            try:
                cik_text = f"{int(cik_text):010d}"
            except (TypeError, ValueError):
                cik_text = cik_text.zfill(10) if cik_text else ""
            rows.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "name_upper": name.upper(),
                    "exchange": exchange_text,
                    "cik": cik_text,
                }
            )
        self._reference_rows = rows
        self._reference_retrieved_at = now_utc()
        return rows

    def _load_company(self, identifier: str) -> Company | None:
        normalized = str(identifier or "").strip()
        if not normalized:
            return None
        self._configure_edgar_tools()
        Company, _, _ = _load_edgar_tools()
        try:
            return Company(normalized)
        except Exception:
            return None

    def _search_row_from_company(
        self,
        company: Company,
        *,
        requested_ticker: str | None,
    ) -> dict[str, str | None]:
        data = getattr(company, "data", None)
        tickers = [str(value or "").strip().upper() for value in getattr(company, "tickers", []) if str(value or "").strip()]
        ticker = requested_ticker if requested_ticker in tickers else tickers[0] if tickers else str(requested_ticker or "").strip().upper()
        exchanges = getattr(data, "exchanges", []) if data is not None else []
        exchange = _first_string(exchanges)
        cik = ""
        try:
            cik = f"{int(company.cik):010d}"
        except (TypeError, ValueError):
            cik = str(getattr(company, "cik", "") or "").strip().zfill(10)
        name = _clean_text(getattr(data, "name", None) if data is not None else None) or company.name
        return {
            "ticker": ticker,
            "name": name,
            "name_upper": name.upper(),
            "exchange": exchange,
            "cik": cik,
        }

    def _primary_ticker(self, company: Company, *, requested_ticker: str) -> str:
        tickers = [str(value or "").strip().upper() for value in getattr(company, "tickers", []) if str(value or "").strip()]
        if requested_ticker and requested_ticker in tickers:
            return requested_ticker
        return tickers[0] if tickers else requested_ticker

    def _load_facts_dataframe(self, company: Company) -> pd.DataFrame:
        facts = company.get_facts()
        if facts is None:
            return pd.DataFrame(
                columns=[
                    "concept",
                    "label",
                    "numeric_value",
                    "unit",
                    "period_start",
                    "period_end",
                    "fiscal_year",
                    "fiscal_period",
                    "filing_date",
                    "form_type",
                    "accession",
                    "statement_type",
                ]
            )
        return facts.to_dataframe(
            include_metadata=True,
            columns=[
                "concept",
                "label",
                "numeric_value",
                "unit",
                "period_start",
                "period_end",
                "fiscal_year",
                "fiscal_period",
                "filing_date",
                "form_type",
                "accession",
                "statement_type",
            ],
        )

    def _build_company_record(
        self,
        company: Company,
        filings: list[FundamentalsFilingRecord],
        *,
        retrieved_at: datetime,
        primary_ticker: str,
    ) -> FundamentalsCompanyRecord:
        data = company.data
        latest_report_period = next((row.report_period for row in filings if row.report_period is not None), None)
        latest_filing_date = filings[0].filing_date if filings else None
        sic_description = _clean_text(getattr(data, "sic_description", None)) or _clean_text(getattr(company, "industry", None))
        filer_category = _clean_text(getattr(data, "category", None))
        exchange = _first_string(getattr(data, "exchanges", []))
        description_parts = [company.name]
        if exchange:
            description_parts.append(f"is listed on {exchange}")
        if filer_category:
            description_parts.append(f"and files as a {filer_category.lower()}")
        if sic_description:
            description_parts.append(f"in {sic_description.lower()}")
        description = " ".join(description_parts)
        if description and not description.endswith("."):
            description = f"{description}."
        return FundamentalsCompanyRecord(
            ticker=primary_ticker,
            cik=f"{int(company.cik):010d}",
            name=_clean_text(getattr(data, "name", None)) or company.name,
            exchange=exchange,
            sic=_clean_text(getattr(data, "sic", None)),
            sic_description=sic_description,
            filer_category=filer_category,
            fiscal_year_end=_clean_text(getattr(data, "fiscal_year_end", None)),
            state_of_incorporation=_clean_text(getattr(data, "state_of_incorporation", None)),
            phone=_clean_text(getattr(data, "phone", None)),
            website=_clean_text(getattr(data, "website", None)),
            investor_website=_clean_text(getattr(data, "investor_website", None)),
            description=description,
            latest_report_period=latest_report_period,
            latest_filing_date=latest_filing_date,
            classification_labels=[value for value in [sic_description, filer_category, exchange] if value],
            source_provider="sec",
            retrieved_at=retrieved_at,
            origin="fundamentals.sec.company",
            transformation_note="Gamma derives the company profile summary from EdgarTools company reference data and SEC filing metadata until a richer profile source is added.",
        )

    def _build_filing_history(
        self,
        company: Company,
        *,
        retrieved_at: datetime,
        limit: int = 12,
    ) -> list[FundamentalsFilingRecord]:
        rows: list[FundamentalsFilingRecord] = []
        filings = []
        for forms, fetch_limit in (
            (_FILING_FORMS, limit * 4),
            (tuple(_ANNUAL_FORMS), limit),
        ):
            try:
                filings.extend(company.get_filings(form=list(forms), amendments=True).head(fetch_limit))
            except Exception:
                continue
        seen_accessions: set[str] = set()
        for filing in filings:
            form = _clean_text(getattr(filing, "form", None))
            if form not in _FILING_FORMS:
                continue
            accession = _clean_text(
                getattr(filing, "accession_number", None) or getattr(filing, "accession_no", None)
            )
            if accession and accession in seen_accessions:
                continue
            if accession:
                seen_accessions.add(accession)
            filing_date = _parse_datetime(getattr(filing, "filing_date", None))
            if filing_date is None:
                continue
            rows.append(
                FundamentalsFilingRecord(
                    form=form,
                    filing_date=filing_date,
                    report_period=_parse_datetime(getattr(filing, "report_date", None)),
                    acceptance_datetime=_parse_datetime(getattr(filing, "acceptance_datetime", None)),
                    accession_number=accession,
                    primary_document=_clean_text(getattr(filing, "primary_document", None)),
                    is_amendment=form.endswith("/A"),
                    source_provider="sec",
                    retrieved_at=retrieved_at,
                    origin="fundamentals.sec.filings",
                    transformation_note="Gamma preserves SEC filing chronology through EdgarTools filing objects, including amendments and report-period metadata where available.",
                )
            )
        rows.sort(key=lambda row: (row.filing_date, row.acceptance_datetime or row.filing_date), reverse=True)
        selected = rows[:limit]
        selected_accessions = {row.accession_number for row in selected if row.accession_number}
        for annual in [row for row in rows if row.form in _ANNUAL_FORMS]:
            if annual.accession_number and annual.accession_number in selected_accessions:
                continue
            selected.append(annual)
            if annual.accession_number:
                selected_accessions.add(annual.accession_number)
            if len([row for row in selected if row.form in _ANNUAL_FORMS]) >= 2:
                break
        selected.sort(key=lambda row: (row.filing_date, row.acceptance_datetime or row.filing_date), reverse=True)
        return selected

    def _build_statement_view(
        self,
        facts_df: pd.DataFrame,
        *,
        statement: str,
        basis: str,
        retrieved_at: datetime,
    ) -> FundamentalsStatementView:
        definitions = [row for row in _STATEMENT_LINE_DEFINITIONS if row.statement == statement]
        period_map: dict[str, FundamentalsPeriodRecord] = {}
        line_periods: dict[str, list[FundamentalsPeriodRecord]] = {}
        lines: list[FundamentalsStatementLine] = []
        statement_has_gamma_cells = False
        for definition in definitions:
            selected = self._select_observations(facts_df, definition=definition, basis=basis)
            selected_periods: list[FundamentalsPeriodRecord] = []
            for period_key, observation in selected.items():
                period = period_map.setdefault(
                    period_key,
                    FundamentalsPeriodRecord(
                        period_key=period_key,
                        label=self._period_label(basis=basis, observation=observation),
                        fiscal_year=observation.fiscal_year,
                        fiscal_period=observation.fiscal_period,
                        start_date=observation.start_date,
                        end_date=observation.end_date,
                        filing_date=observation.filing_date,
                        form=observation.form,
                        accession_number=observation.accession_number,
                        is_amendment=observation.is_amendment,
                        source_provider="sec",
                        retrieved_at=retrieved_at,
                        origin=f"fundamentals.sec.company_facts.{definition.line_key}",
                    ),
                )
                selected_periods.append(period)
            line_periods[definition.line_key] = sorted(selected_periods, key=lambda row: _sortable_datetime(row.end_date))
            cells = [
                FundamentalsStatementCell(
                    period_key=period_key,
                    value=observation.value,
                    display_value=_format_statement_value(observation.value, definition.unit),
                    start_date=observation.start_date,
                    end_date=observation.end_date,
                    filing_date=observation.filing_date,
                    form=observation.form,
                    accession_number=observation.accession_number,
                    is_amendment=observation.is_amendment,
                    concept_name=observation.concept_name,
                    source_provider=observation.source_provider,
                    retrieved_at=retrieved_at,
                    origin=(
                        f"fundamentals.analytics.quarterly.{definition.line_key}"
                        if observation.source_provider == "gamma"
                        else f"fundamentals.sec.company_facts.{definition.line_key}"
                    ),
                    transformation_note=observation.transformation_note,
                )
                for period_key, observation in selected.items()
            ]
            cells.sort(key=lambda cell: _sortable_datetime(cell.end_date))
            has_gamma_cells = any(cell.source_provider == "gamma" for cell in cells)
            statement_has_gamma_cells = statement_has_gamma_cells or has_gamma_cells
            lines.append(
                FundamentalsStatementLine(
                    line_key=definition.line_key,
                    label=definition.label,
                    statement=statement,
                    unit=definition.unit,
                    cells=cells,
                    source_provider="gamma" if has_gamma_cells else "sec",
                    retrieved_at=retrieved_at,
                    origin=(
                        f"fundamentals.analytics.quarterly.{definition.line_key}"
                        if has_gamma_cells
                        else f"fundamentals.sec.company_facts.{definition.line_key}"
                    ),
                    transformation_note=(
                        "Gamma preserves quarterly statement integrity by deriving missing standalone quarter values from cumulative SEC filings when the company-facts feed does not provide quarter-only observations."
                        if has_gamma_cells
                        else None
                    ),
                )
            )
        periods = sorted(period_map.values(), key=lambda row: _sortable_datetime(row.end_date))
        anchor_periods = next(
            (
                line_periods[line_key]
                for line_key in _STATEMENT_PERIOD_ANCHORS.get(statement, ())
                if line_periods.get(line_key)
            ),
            periods,
        )
        keep_keys = [row.period_key for row in (anchor_periods[-6:] if basis == "annual" else anchor_periods[-8:])]
        trimmed_periods = [row for row in anchor_periods if row.period_key in set(keep_keys)]
        normalized_lines = self._backfill_statement_lines(
            statement=statement,
            basis=basis,
            periods=trimmed_periods,
            lines=[self._ensure_line_cells(line, keep_keys) for line in lines],
            retrieved_at=retrieved_at,
        )
        statement_has_gamma_cells = statement_has_gamma_cells or any(
            cell.source_provider == "gamma"
            for line in normalized_lines
            for cell in line.cells
        )
        return FundamentalsStatementView(
            statement=statement,
            basis=basis,
            periods=trimmed_periods,
            lines=normalized_lines,
            source_provider="gamma" if statement_has_gamma_cells else "sec",
            retrieved_at=retrieved_at,
            origin=(
                f"fundamentals.analytics.{statement}.{basis}"
                if statement_has_gamma_cells
                else f"fundamentals.sec.company_facts.{statement}.{basis}"
            ),
            transformation_note=(
                "Gamma normalizes SEC company facts into retained statement periods and marks Gamma-derived cells when it derives standalone quarters or backfills safe line-item relationships."
                if statement_has_gamma_cells
                else None
            ),
        )

    def _backfill_statement_lines(
        self,
        *,
        statement: str,
        basis: str,
        periods: list[FundamentalsPeriodRecord],
        lines: list[FundamentalsStatementLine],
        retrieved_at: datetime,
    ) -> list[FundamentalsStatementLine]:
        line_map = {line.line_key: line for line in lines}
        if statement == "income":
            self._backfill_line_from_formula(
                line_map,
                periods=periods,
                target_key="operating_expenses",
                source_keys=("research_and_development", "selling_general_and_administrative"),
                formula=lambda values: values[0] + values[1],
                formula_note="R&D plus SG&A",
                retrieved_at=retrieved_at,
                basis=basis,
                unit="currency",
            )
            self._backfill_line_from_formula(
                line_map,
                periods=periods,
                target_key="operating_income",
                source_keys=("gross_profit", "operating_expenses"),
                formula=lambda values: values[0] - values[1],
                formula_note="gross profit minus operating expenses",
                retrieved_at=retrieved_at,
                basis=basis,
                unit="currency",
            )
            self._backfill_line_from_formula(
                line_map,
                periods=periods,
                target_key="pretax_income",
                source_keys=("net_income", "income_tax"),
                formula=lambda values: values[0] + values[1],
                formula_note="net income plus income tax expense",
                retrieved_at=retrieved_at,
                basis=basis,
                unit="currency",
            )
        if statement == "balance":
            self._backfill_line_from_formula(
                line_map,
                periods=periods,
                target_key="total_liabilities",
                source_keys=("total_assets", "shareholders_equity"),
                formula=lambda values: values[0] - values[1],
                formula_note="total assets minus shareholders' equity",
                retrieved_at=retrieved_at,
                basis=basis,
                unit="currency",
            )
            self._backfill_line_from_formula(
                line_map,
                periods=periods,
                target_key="shareholders_equity",
                source_keys=("total_assets", "total_liabilities"),
                formula=lambda values: values[0] - values[1],
                formula_note="total assets minus total liabilities",
                retrieved_at=retrieved_at,
                basis=basis,
                unit="currency",
            )
            self._backfill_line_from_formula(
                line_map,
                periods=periods,
                target_key="total_assets",
                source_keys=("total_liabilities", "shareholders_equity"),
                formula=lambda values: values[0] + values[1],
                formula_note="total liabilities plus shareholders' equity",
                retrieved_at=retrieved_at,
                basis=basis,
                unit="currency",
            )
        return [line_map.get(line.line_key, line) for line in lines]

    def _backfill_line_from_formula(
        self,
        line_map: dict[str, FundamentalsStatementLine],
        *,
        periods: list[FundamentalsPeriodRecord],
        target_key: str,
        source_keys: tuple[str, ...],
        formula: Any,
        formula_note: str,
        retrieved_at: datetime,
        basis: str,
        unit: str,
    ) -> None:
        target = line_map.get(target_key)
        sources = [line_map.get(source_key) for source_key in source_keys]
        if target is None or any(source is None for source in sources):
            return
        source_maps = [
            {cell.period_key: cell for cell in source.cells}
            for source in sources
            if source is not None
        ]
        next_cells: list[FundamentalsStatementCell] = []
        derived_any = False
        for period, cell in zip(periods, target.cells, strict=False):
            if cell.value is not None:
                next_cells.append(cell)
                continue
            source_cells = [source_map.get(period.period_key) for source_map in source_maps]
            source_values = [source_cell.value if source_cell is not None else None for source_cell in source_cells]
            if any(value is None for value in source_values):
                next_cells.append(cell)
                continue
            derived_value = formula([float(value) for value in source_values if value is not None])
            derived_any = True
            next_cells.append(
                FundamentalsStatementCell(
                    period_key=period.period_key,
                    value=derived_value,
                    display_value=_format_statement_value(derived_value, unit),
                    start_date=cell.start_date or period.start_date,
                    end_date=cell.end_date or period.end_date,
                    filing_date=cell.filing_date or period.filing_date,
                    form=cell.form or period.form,
                    accession_number=cell.accession_number or period.accession_number,
                    is_amendment=cell.is_amendment or period.is_amendment,
                    concept_name=None,
                    source_provider="gamma",
                    retrieved_at=retrieved_at,
                    origin=f"fundamentals.analytics.backfill.{basis}.{target_key}",
                    transformation_note=f"Gamma backfills this retained statement value from {formula_note} when SEC company facts do not provide a directly mapped cell.",
                )
            )
        if not derived_any:
            return
        line_map[target_key] = replace(
            target,
            cells=next_cells,
            source_provider="gamma",
            origin=f"fundamentals.analytics.backfill.{basis}.{target_key}",
            transformation_note=f"Gamma backfills missing {target.label} values from {formula_note} where the source statement rows are available.",
        )

    def _select_observations(
        self,
        facts_df: pd.DataFrame,
        *,
        definition: StatementLineDefinition,
        basis: str,
    ) -> dict[str, FactObservation]:
        if facts_df.empty:
            return {}
        observations: list[FactObservation] = []
        concept_set = set(definition.concepts)
        selected_rows = facts_df[facts_df["concept"].isin(concept_set)]
        for row in selected_rows.to_dict(orient="records"):
            unit = row.get("unit")
            if not self._matches_fact_unit(unit, definition.unit):
                continue
            observation = self._build_observation_from_fact_row(row)
            if observation is None:
                continue
            if basis == "quarterly":
                if not self._matches_quarterly_candidate(observation, definition.period_kind):
                    continue
            elif not self._matches_basis(observation, definition.period_kind, basis):
                continue
            observations.append(observation)
        if basis == "quarterly":
            if definition.period_kind == "instant":
                return self._select_quarterly_instant_observations(observations)
            return self._select_quarterly_duration_observations(
                observations,
                allow_derived=definition.quarterly_derivable,
            )
        return self._select_annual_observations(observations)

    def _matches_fact_unit(self, unit: Any, expected_unit: str) -> bool:
        unit_text = str(unit or "").strip()
        if expected_unit == "currency":
            unit_upper = unit_text.upper()
            return any(unit_upper.startswith(prefix) for prefix in _CURRENCY_UNIT_PREFIXES)
        if expected_unit == "shares":
            return unit_text.lower().startswith("shares")
        return bool(unit_text)

    def _build_observation_from_fact_row(self, row: dict[str, Any]) -> FactObservation | None:
        try:
            value = float(row.get("numeric_value"))
        except (TypeError, ValueError):
            return None
        concept_ref = _clean_text(row.get("concept")) or ""
        return FactObservation(
            concept_name=concept_ref,
            value=value,
            start_date=_parse_datetime(row.get("period_start")),
            end_date=_parse_datetime(row.get("period_end")),
            filing_date=_parse_datetime(row.get("filing_date")),
            filing_date_text=_clean_text(row.get("filing_date")),
            form=_clean_text(row.get("form_type")),
            accession_number=_clean_text(row.get("accession")),
            fiscal_year=_parse_int(row.get("fiscal_year")),
            fiscal_period=_clean_text(row.get("fiscal_period")),
            frame=None,
            is_amendment=str(row.get("form_type") or "").endswith("/A"),
        )

    def _matches_basis(self, observation: FactObservation, period_kind: str, basis: str) -> bool:
        form = str(observation.form or "").upper()
        if period_kind == "instant":
            return form in (_ANNUAL_FORMS if basis == "annual" else _QUARTERLY_FORMS)
        duration_days = _duration_days(observation.start_date, observation.end_date)
        if duration_days is None:
            return False
        if basis == "annual":
            return form in _ANNUAL_FORMS and 300 <= duration_days <= 380
        return form in _QUARTERLY_FORMS and 75 <= duration_days <= 110

    def _matches_quarterly_candidate(self, observation: FactObservation, period_kind: str) -> bool:
        form = str(observation.form or "").upper()
        if form not in _QUARTERLY_FORMS or observation.end_date is None:
            return False
        if period_kind == "instant":
            return True
        duration_days = _duration_days(observation.start_date, observation.end_date)
        return duration_days is not None and 75 <= duration_days <= 380

    def _period_key(self, *, basis: str, observation: FactObservation) -> str:
        if basis == "annual":
            return f"FY-{observation.fiscal_year or _year(observation.end_date)}"
        end_label = observation.end_date.date().isoformat() if observation.end_date else "unknown"
        return f"QE-{end_label}"

    def _period_label(self, *, basis: str, observation: FactObservation) -> str:
        fiscal_year = observation.fiscal_year or _year(observation.end_date)
        if basis == "annual":
            return f"FY {fiscal_year}"
        return f"{observation.fiscal_period or 'Q'} {fiscal_year}"

    def _observation_rank(self, observation: FactObservation) -> tuple[int, int, int]:
        filing_ord = int(observation.filing_date.timestamp()) if observation.filing_date else 0
        form_rank = 2 if str(observation.form or "").upper() in {"10-Q", "10-K"} else 1
        amendment_rank = 1 if observation.is_amendment else 0
        return (form_rank, amendment_rank, filing_ord)

    def _quarterly_observation_rank(self, observation: FactObservation) -> tuple[int, int, int, int]:
        filing_ord = int(observation.filing_date.timestamp()) if observation.filing_date else 0
        form_rank = 2 if str(observation.form or "").upper() in {"10-Q", "10-K"} else 1
        amendment_rank = 1 if observation.is_amendment else 0
        lag_days = 10_000
        if observation.end_date is not None and observation.filing_date is not None:
            lag_days = max((observation.filing_date.date() - observation.end_date.date()).days, 0)
        return (-lag_days, form_rank, amendment_rank, filing_ord)

    def _select_annual_observations(
        self,
        observations: list[FactObservation],
    ) -> dict[str, FactObservation]:
        grouped: dict[str, list[FactObservation]] = {}
        for observation in observations:
            if observation.end_date is None:
                continue
            grouped.setdefault(observation.end_date.date().isoformat(), []).append(observation)
        selected: dict[str, FactObservation] = {}
        for group in sorted(grouped.values(), key=lambda rows: _sortable_datetime(rows[0].end_date)):
            candidates = [
                normalized
                for observation in group
                if (normalized := self._normalize_annual_observation(observation)) is not None
            ]
            if not candidates:
                continue
            winner = max(candidates, key=self._quarterly_observation_rank)
            selected[self._period_key(basis="annual", observation=winner)] = winner
        return selected

    def _normalize_annual_observation(self, observation: FactObservation) -> FactObservation | None:
        if observation.end_date is None:
            return None
        fiscal_year = observation.fiscal_year or _year(observation.end_date)
        if fiscal_year is None:
            return None
        return replace(observation, fiscal_year=fiscal_year, fiscal_period="FY")

    def _select_quarterly_instant_observations(
        self,
        observations: list[FactObservation],
    ) -> dict[str, FactObservation]:
        grouped: dict[str, list[FactObservation]] = {}
        for observation in observations:
            if observation.end_date is None:
                continue
            grouped.setdefault(observation.end_date.date().isoformat(), []).append(observation)
        selected: dict[str, FactObservation] = {}
        for group in sorted(grouped.values(), key=lambda rows: _sortable_datetime(rows[0].end_date)):
            candidates = [
                normalized
                for observation in group
                if (normalized := self._normalize_quarterly_observation(observation)) is not None
            ]
            if not candidates:
                continue
            winner = max(candidates, key=self._quarterly_observation_rank)
            selected[self._period_key(basis="quarterly", observation=winner)] = winner
        return selected

    def _select_quarterly_duration_observations(
        self,
        observations: list[FactObservation],
        *,
        allow_derived: bool,
    ) -> dict[str, FactObservation]:
        grouped: dict[str, list[FactObservation]] = {}
        for observation in observations:
            if observation.end_date is None:
                continue
            grouped.setdefault(observation.end_date.date().isoformat(), []).append(observation)
        selected: dict[str, FactObservation] = {}
        cumulative_track: dict[tuple[int, int], FactObservation] = {}
        for group in sorted(grouped.values(), key=lambda rows: _sortable_datetime(rows[0].end_date)):
            candidates = [
                normalized
                for observation in group
                if (normalized := self._normalize_quarterly_observation(observation)) is not None
            ]
            if not candidates:
                continue
            canonical = max(candidates, key=self._quarterly_observation_rank)
            fiscal_year = canonical.fiscal_year
            quarter_index = self._quarter_index(canonical.fiscal_period)
            if fiscal_year is None or quarter_index is None:
                continue
            direct_candidates = [
                observation
                for observation in candidates
                if self._is_discrete_quarter_duration(observation)
            ]
            cumulative_candidates = [
                observation
                for observation in candidates
                if self._is_cumulative_quarter_duration(observation)
            ]
            cumulative_observation = (
                max(cumulative_candidates, key=self._quarterly_observation_rank)
                if cumulative_candidates
                else None
            )
            quarter_observation = (
                max(direct_candidates, key=self._quarterly_observation_rank)
                if direct_candidates
                else None
            )
            if allow_derived and quarter_observation is None and cumulative_observation is not None:
                if quarter_index == 1:
                    quarter_observation = cumulative_observation
                else:
                    previous_cumulative = cumulative_track.get((fiscal_year, quarter_index - 1))
                    if previous_cumulative is not None:
                        quarter_observation = self._derive_quarterly_duration_observation(
                            current=cumulative_observation,
                            previous=previous_cumulative,
                            fiscal_year=fiscal_year,
                            fiscal_period=f"Q{quarter_index}",
                        )
            if quarter_observation is None:
                continue
            selected[self._period_key(basis="quarterly", observation=quarter_observation)] = quarter_observation
            if cumulative_observation is not None:
                cumulative_track[(fiscal_year, quarter_index)] = cumulative_observation
                continue
            previous_cumulative = cumulative_track.get((fiscal_year, quarter_index - 1))
            if quarter_index == 1 or previous_cumulative is None or previous_cumulative.value is None or quarter_observation.value is None:
                cumulative_track[(fiscal_year, quarter_index)] = quarter_observation
                continue
            cumulative_track[(fiscal_year, quarter_index)] = replace(
                quarter_observation,
                value=previous_cumulative.value + quarter_observation.value,
                source_provider="gamma",
                transformation_note="Gamma reconstructs a year-to-date cumulative series from explicit quarter values when the SEC company-facts feed omits a matching cumulative observation.",
            )
        return selected

    def _normalize_quarterly_observation(self, observation: FactObservation) -> FactObservation | None:
        if observation.end_date is None:
            return None
        fiscal_period = str(observation.fiscal_period or "").upper()
        if fiscal_period == "FY":
            fiscal_period = "Q4"
        if fiscal_period not in {"Q1", "Q2", "Q3", "Q4"}:
            return None
        fiscal_year = observation.fiscal_year or _year(observation.end_date)
        if fiscal_year is None:
            return None
        return replace(observation, fiscal_period=fiscal_period, fiscal_year=fiscal_year)

    def _quarter_index(self, fiscal_period: str | None) -> int | None:
        if not fiscal_period:
            return None
        if fiscal_period.startswith("Q"):
            try:
                quarter = int(fiscal_period[1:])
            except ValueError:
                return None
            return quarter if 1 <= quarter <= 4 else None
        return None

    def _is_discrete_quarter_duration(self, observation: FactObservation) -> bool:
        duration_days = _duration_days(observation.start_date, observation.end_date)
        return duration_days is not None and 75 <= duration_days <= 110

    def _is_cumulative_quarter_duration(self, observation: FactObservation) -> bool:
        duration_days = _duration_days(observation.start_date, observation.end_date)
        return duration_days is not None and 75 <= duration_days <= 380

    def _derive_quarterly_duration_observation(
        self,
        *,
        current: FactObservation,
        previous: FactObservation,
        fiscal_year: int,
        fiscal_period: str,
    ) -> FactObservation:
        derived_start = previous.end_date + timedelta(days=1) if previous.end_date is not None else current.start_date
        return replace(
            current,
            value=current.value - previous.value,
            start_date=derived_start,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            source_provider="gamma",
            transformation_note="Gamma derives standalone quarterly values by subtracting the prior cumulative SEC filing from the current year-to-date filing so annual and quarterly views stay semantically explicit.",
        )

    def _ensure_line_cells(
        self,
        line: FundamentalsStatementLine,
        period_keys: list[str],
    ) -> FundamentalsStatementLine:
        cell_map = {cell.period_key: cell for cell in line.cells}
        cells: list[FundamentalsStatementCell] = []
        for period_key in period_keys:
            if period_key in cell_map:
                cells.append(cell_map[period_key])
                continue
            cells.append(
                FundamentalsStatementCell(
                    period_key=period_key,
                    value=None,
                    display_value="N/A",
                    source_provider="sec",
                    retrieved_at=line.retrieved_at,
                    origin=line.origin,
                )
            )
        return FundamentalsStatementLine(
            line_key=line.line_key,
            label=line.label,
            statement=line.statement,
            unit=line.unit,
            cells=cells,
            source_provider=line.source_provider,
            retrieved_at=line.retrieved_at,
            origin=line.origin,
            transformation_note=line.transformation_note,
        )


class IbkrValuationAdapter:
    def __init__(
        self,
        *,
        research_provider: ResearchDataProvider,
        market_data: MarketDataService,
    ) -> None:
        self.research_provider = research_provider
        self.market_data = market_data

    def get_price_context(
        self,
        ticker: str,
        *,
        lookback_days: int = 180,
        force_refresh: bool = False,
    ) -> IbkrPriceContext:
        del force_refresh
        normalized = str(ticker or "").strip().upper()
        if not normalized:
            return IbkrPriceContext(
                ticker="",
                current_price=None,
                warnings=["Ticker is required for price context."],
                source_provider="ibkr",
                retrieved_at=now_utc(),
                origin="fundamentals.ibkr.price_context",
                transformation_note="Gamma could not build price context without a ticker symbol.",
            )
        history = self.research_provider.load_symbol_history(normalized, lookback_days)
        history_source = "mock" if self.research_provider.client.mock else "ibkr"
        history_origin = (
            "fundamentals.ibkr.mock_history_fallback"
            if self.research_provider.client.mock
            else "fundamentals.ibkr.history"
        )
        price_points: list[FundamentalsPricePoint] = []
        if history is not None:
            for timestamp, value in list(history.items())[-lookback_days:]:
                try:
                    price = float(value)
                except (TypeError, ValueError):
                    continue
                price_points.append(
                    FundamentalsPricePoint(
                        timestamp=_ensure_datetime(timestamp),
                        price=price,
                        source_provider=history_source,
                        retrieved_at=now_utc(),
                        origin=history_origin,
                        transformation_note=(
                            "Gamma uses cached or mock daily closes for the overview mini chart."
                            if self.research_provider.client.mock
                            else None
                        ),
                    )
                )
        current_price = price_points[-1].price if price_points else None
        warnings: list[str] = []
        retrieved_at = price_points[-1].retrieved_at if price_points else now_utc()
        origin = history_origin
        transformation_note = (
            "Gamma falls back to the latest available close when a live IBKR snapshot is unavailable."
            if current_price is not None
            else None
        )
        if not self.research_provider.client.mock:
            contract = contract_for_instrument(
                InstrumentReference(symbol=normalized).with_defaults(self.research_provider.instrument_defaults)
            )
            snapshot_map, snapshot_warnings = self.market_data.fetch_snapshot_quotes([contract])
            warnings.extend(snapshot_warnings)
            snapshot = snapshot_map.get(self.market_data.quote_key(contract))
            if snapshot is not None and snapshot.price is not None:
                current_price = float(snapshot.price)
                retrieved_at = now_utc()
                origin = "fundamentals.ibkr.snapshot"
                transformation_note = (
                    "Gamma uses the current IBKR snapshot price for market-aware valuation fields."
                    if snapshot.delayed
                    else None
                )
        return IbkrPriceContext(
            ticker=normalized,
            current_price=current_price,
            price_history=price_points,
            warnings=warnings,
            source_provider="mock" if self.research_provider.client.mock else "ibkr",
            retrieved_at=retrieved_at,
            origin=origin,
            transformation_note=transformation_note,
        )
