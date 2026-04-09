from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

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


_SEC_TICKER_INDEX_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SEC_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
_SEC_COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

_ANNUAL_FORMS = {"10-K", "10-K/A"}
_QUARTERLY_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A"}
_FILING_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")

_POPULAR_FUNDAMENTALS_TICKERS = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "ORCL", "SAP")


@dataclass(frozen=True)
class StatementLineDefinition:
    line_key: str
    label: str
    statement: str
    unit: str
    period_kind: str
    concepts: tuple[str, ...]


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
    is_amendment: bool


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
        ),
    ),
    StatementLineDefinition("gross_profit", "Gross Profit", "income", "currency", "duration", ("us-gaap:GrossProfit",)),
    StatementLineDefinition(
        "research_and_development",
        "R&D",
        "income",
        "currency",
        "duration",
        ("us-gaap:ResearchAndDevelopmentExpense",),
    ),
    StatementLineDefinition(
        "selling_general_and_administrative",
        "SG&A",
        "income",
        "currency",
        "duration",
        ("us-gaap:SellingGeneralAndAdministrativeExpense",),
    ),
    StatementLineDefinition("operating_expenses", "Operating Expenses", "income", "currency", "duration", ("us-gaap:OperatingExpenses",)),
    StatementLineDefinition("operating_income", "Operating Income", "income", "currency", "duration", ("us-gaap:OperatingIncomeLoss",)),
    StatementLineDefinition("pretax_income", "Pre-Tax Income", "income", "currency", "duration", ("us-gaap:IncomeBeforeTaxExpenseBenefit",)),
    StatementLineDefinition("income_tax", "Income Tax", "income", "currency", "duration", ("us-gaap:IncomeTaxExpenseBenefit",)),
    StatementLineDefinition("net_income", "Net Income", "income", "currency", "duration", ("us-gaap:NetIncomeLoss",)),
    StatementLineDefinition(
        "diluted_shares",
        "Diluted Shares",
        "income",
        "shares",
        "duration",
        ("us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",),
    ),
    StatementLineDefinition("cash_and_equivalents", "Cash & Equivalents", "balance", "currency", "instant", ("us-gaap:CashAndCashEquivalentsAtCarryingValue",)),
    StatementLineDefinition(
        "marketable_securities_current",
        "Current Marketable Securities",
        "balance",
        "currency",
        "instant",
        ("us-gaap:MarketableSecuritiesCurrent", "us-gaap:AvailableForSaleSecuritiesCurrent"),
    ),
    StatementLineDefinition("accounts_receivable", "Accounts Receivable", "balance", "currency", "instant", ("us-gaap:AccountsReceivableNetCurrent",)),
    StatementLineDefinition("inventory", "Inventory", "balance", "currency", "instant", ("us-gaap:InventoryNet",)),
    StatementLineDefinition("current_assets", "Current Assets", "balance", "currency", "instant", ("us-gaap:AssetsCurrent",)),
    StatementLineDefinition("total_assets", "Total Assets", "balance", "currency", "instant", ("us-gaap:Assets",)),
    StatementLineDefinition("accounts_payable", "Accounts Payable", "balance", "currency", "instant", ("us-gaap:AccountsPayableCurrent",)),
    StatementLineDefinition(
        "short_term_debt",
        "Short-Term Debt",
        "balance",
        "currency",
        "instant",
        ("us-gaap:LongTermDebtCurrent", "us-gaap:ShortTermBorrowings", "us-gaap:CommercialPaper"),
    ),
    StatementLineDefinition("current_liabilities", "Current Liabilities", "balance", "currency", "instant", ("us-gaap:LiabilitiesCurrent",)),
    StatementLineDefinition(
        "long_term_debt",
        "Long-Term Debt",
        "balance",
        "currency",
        "instant",
        ("us-gaap:LongTermDebtAndCapitalLeaseObligations", "us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt"),
    ),
    StatementLineDefinition("total_liabilities", "Total Liabilities", "balance", "currency", "instant", ("us-gaap:Liabilities",)),
    StatementLineDefinition(
        "shareholders_equity",
        "Shareholders' Equity",
        "balance",
        "currency",
        "instant",
        ("us-gaap:StockholdersEquity", "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ),
    StatementLineDefinition(
        "shares_outstanding",
        "Shares Outstanding",
        "balance",
        "shares",
        "instant",
        ("dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding"),
    ),
    StatementLineDefinition(
        "operating_cash_flow",
        "Operating Cash Flow",
        "cashflow",
        "currency",
        "duration",
        ("us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "us-gaap:NetCashProvidedByUsedInOperatingActivities"),
    ),
    StatementLineDefinition(
        "capital_expenditures",
        "Capex",
        "cashflow",
        "currency",
        "duration",
        ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:PropertyPlantAndEquipmentAdditions"),
    ),
    StatementLineDefinition(
        "depreciation_and_amortization",
        "D&A",
        "cashflow",
        "currency",
        "duration",
        ("us-gaap:DepreciationDepletionAndAmortization", "us-gaap:Depreciation"),
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


class SecFundamentalsAdapter:
    def __init__(self, cache: CacheService) -> None:
        self.cache = cache
        # TODO: Replace this development-time SEC identity fallback with a user-configurable Gamma setting.
        self.identity_name = os.getenv("GAMMA_SEC_USER_NAME", "").strip() or "Gorka Bravo"
        self.identity_email = (
            os.getenv("GAMMA_SEC_USER_EMAIL", "").strip() or "gorka.bravo1@gmail.com"
        )

    def search_companies(
        self,
        query: str,
        *,
        limit: int = 12,
        force_refresh: bool = False,
    ) -> list[FundamentalsSearchResult]:
        index_payload = self._load_ticker_index(force_refresh=force_refresh)
        rows = index_payload["rows"]
        query_text = str(query or "").strip().upper()
        if query_text:
            exact_ticker = [row for row in rows if row["ticker"] == query_text]
            prefix_matches = [
                row for row in rows if row["ticker"].startswith(query_text) and row["ticker"] != query_text
            ]
            name_matches = [
                row
                for row in rows
                if query_text in row["name_upper"]
                and row["ticker"] not in {item["ticker"] for item in exact_ticker}
            ]
            rows = exact_ticker + prefix_matches + name_matches
        else:
            preferred = [row for row in rows if row["ticker"] in _POPULAR_FUNDAMENTALS_TICKERS]
            preferred_tickers = {row["ticker"] for row in preferred}
            rows = preferred + [row for row in rows if row["ticker"] not in preferred_tickers]
        results: list[FundamentalsSearchResult] = []
        for row in rows[: max(1, min(limit, 40))]:
            results.append(
                FundamentalsSearchResult(
                    ticker=row["ticker"],
                    name=row["name"],
                    cik=row["cik"],
                    exchange=row.get("exchange"),
                    source_provider="sec",
                    retrieved_at=index_payload["retrieved_at"],
                    origin="fundamentals.sec.company_tickers_exchange",
                )
            )
        return results

    def load_company_data(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> SecCompanyData | None:
        resolved = self._resolve_ticker(ticker, force_refresh=force_refresh)
        if resolved is None or not resolved.cik:
            return None
        submissions_payload = self._load_submissions(resolved.cik, force_refresh=force_refresh)
        facts_payload = self._load_company_facts(resolved.cik, force_refresh=force_refresh)
        filings = self._build_filing_history(
            submissions_payload["payload"],
            retrieved_at=submissions_payload["retrieved_at"],
        )
        retrieved_marks = [
            mark
            for mark in [resolved.retrieved_at, submissions_payload["retrieved_at"], facts_payload["retrieved_at"]]
            if mark is not None
        ]
        company = self._build_company_record(
            resolved,
            submissions_payload["payload"],
            filings,
            retrieved_at=max(retrieved_marks) if retrieved_marks else now_utc(),
        )
        return SecCompanyData(
            company=company,
            filings=filings,
            annual_income_statement=self._build_statement_view(
                facts_payload["payload"],
                statement="income",
                basis="annual",
                retrieved_at=facts_payload["retrieved_at"],
            ),
            annual_balance_sheet=self._build_statement_view(
                facts_payload["payload"],
                statement="balance",
                basis="annual",
                retrieved_at=facts_payload["retrieved_at"],
            ),
            annual_cash_flow_statement=self._build_statement_view(
                facts_payload["payload"],
                statement="cashflow",
                basis="annual",
                retrieved_at=facts_payload["retrieved_at"],
            ),
            quarterly_income_statement=self._build_statement_view(
                facts_payload["payload"],
                statement="income",
                basis="quarterly",
                retrieved_at=facts_payload["retrieved_at"],
            ),
            quarterly_balance_sheet=self._build_statement_view(
                facts_payload["payload"],
                statement="balance",
                basis="quarterly",
                retrieved_at=facts_payload["retrieved_at"],
            ),
            quarterly_cash_flow_statement=self._build_statement_view(
                facts_payload["payload"],
                statement="cashflow",
                basis="quarterly",
                retrieved_at=facts_payload["retrieved_at"],
            ),
        )

    def _resolve_ticker(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsSearchResult | None:
        normalized = str(ticker or "").strip().upper()
        if not normalized:
            return None
        matches = self.search_companies(normalized, limit=8, force_refresh=force_refresh)
        for row in matches:
            if row.ticker == normalized:
                return row
        return matches[0] if matches else None

    def _load_ticker_index(self, *, force_refresh: bool) -> dict[str, Any]:
        cache_key = self.cache.make_key("fundamentals", "sec", "ticker_index")
        if not force_refresh:
            cached = self.cache.get_json(cache_key, max_age=timedelta(days=30))
            if isinstance(cached, dict) and "rows" in cached and "retrieved_at" in cached:
                return {"rows": list(cached["rows"]), "retrieved_at": _parse_datetime(cached["retrieved_at"]) or now_utc()}

        try:
            payload = self._fetch_json(_SEC_TICKER_INDEX_URL)
            fields = payload.get("fields", []) or []
            rows: list[dict[str, str]] = []
            for raw_row in payload.get("data", []) or []:
                mapping = dict(zip(fields, raw_row, strict=False))
                ticker = str(mapping.get("ticker") or "").strip().upper()
                if not ticker:
                    continue
                name = str(mapping.get("name") or "").strip() or ticker
                exchange = str(mapping.get("exchange") or "").strip() or None
                cik_text = str(mapping.get("cik") or "").strip().zfill(10)
                rows.append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "name_upper": name.upper(),
                        "exchange": exchange,
                        "cik": cik_text,
                    }
                )
            retrieved_at = now_utc()
            self.cache.set_json(
                cache_key,
                {"rows": rows, "retrieved_at": retrieved_at.isoformat()},
            )
            return {"rows": rows, "retrieved_at": retrieved_at}
        except Exception:
            cached = self.cache.get_json(cache_key, max_age=None)
            if isinstance(cached, dict) and "rows" in cached and "retrieved_at" in cached:
                return {"rows": list(cached["rows"]), "retrieved_at": _parse_datetime(cached["retrieved_at"]) or now_utc()}
            fallback_rows = [
                {"ticker": ticker, "name": ticker, "name_upper": ticker, "exchange": None, "cik": ""}
                for ticker in _POPULAR_FUNDAMENTALS_TICKERS
            ]
            return {"rows": fallback_rows, "retrieved_at": now_utc()}

    def _load_submissions(self, cik: str, *, force_refresh: bool) -> dict[str, Any]:
        cache_key = self.cache.make_key("fundamentals", "sec", "submissions", cik)
        if not force_refresh:
            cached = self.cache.get_json(cache_key, max_age=timedelta(days=7))
            if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
                return {"payload": cached["payload"], "retrieved_at": _parse_datetime(cached["retrieved_at"]) or now_utc()}
        payload = self._fetch_json(_SEC_SUBMISSIONS_URL_TEMPLATE.format(cik=cik))
        retrieved_at = now_utc()
        self.cache.set_json(cache_key, {"payload": payload, "retrieved_at": retrieved_at.isoformat()})
        return {"payload": payload, "retrieved_at": retrieved_at}

    def _load_company_facts(self, cik: str, *, force_refresh: bool) -> dict[str, Any]:
        cache_key = self.cache.make_key("fundamentals", "sec", "companyfacts", cik)
        if not force_refresh:
            cached = self.cache.get_json(cache_key, max_age=timedelta(days=7))
            if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
                return {"payload": cached["payload"], "retrieved_at": _parse_datetime(cached["retrieved_at"]) or now_utc()}
        payload = self._fetch_json(_SEC_COMPANY_FACTS_URL_TEMPLATE.format(cik=cik))
        retrieved_at = now_utc()
        self.cache.set_json(cache_key, {"payload": payload, "retrieved_at": retrieved_at.isoformat()})
        return {"payload": payload, "retrieved_at": retrieved_at}

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"{self.identity_name} {self.identity_email}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def _build_company_record(
        self,
        resolved: FundamentalsSearchResult,
        submissions_payload: dict[str, Any],
        filings: list[FundamentalsFilingRecord],
        *,
        retrieved_at: datetime,
    ) -> FundamentalsCompanyRecord:
        latest_report_period = next((row.report_period for row in filings if row.report_period is not None), None)
        latest_filing_date = filings[0].filing_date if filings else None
        sic_description = _clean_text(submissions_payload.get("sicDescription"))
        filer_category = _clean_text(submissions_payload.get("category"))
        exchange = resolved.exchange or _first_string(submissions_payload.get("exchanges"))
        description_parts = [resolved.name]
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
            ticker=resolved.ticker,
            cik=resolved.cik,
            name=_clean_text(submissions_payload.get("name")) or resolved.name,
            exchange=exchange,
            sic=_clean_text(submissions_payload.get("sic")),
            sic_description=sic_description,
            filer_category=filer_category,
            fiscal_year_end=_clean_text(submissions_payload.get("fiscalYearEnd")),
            state_of_incorporation=_clean_text(submissions_payload.get("stateOfIncorporation")),
            phone=_clean_text(submissions_payload.get("phone")),
            website=_clean_text(submissions_payload.get("website")),
            investor_website=_clean_text(submissions_payload.get("investorWebsite")),
            description=description,
            latest_report_period=latest_report_period,
            latest_filing_date=latest_filing_date,
            classification_labels=[value for value in [sic_description, filer_category, exchange] if value],
            source_provider="sec",
            retrieved_at=retrieved_at,
            origin="fundamentals.sec.submissions",
            transformation_note="Gamma derives the company profile summary from SEC submissions metadata until a richer company profile source is added.",
        )

    def _build_filing_history(
        self,
        submissions_payload: dict[str, Any],
        *,
        retrieved_at: datetime,
        limit: int = 12,
    ) -> list[FundamentalsFilingRecord]:
        recent = submissions_payload.get("filings", {}).get("recent", {}) or {}
        total = len(recent.get("form", []) or [])
        rows: list[FundamentalsFilingRecord] = []
        for index in range(total):
            form = _index_value(recent.get("form"), index)
            if form not in _FILING_FORMS:
                continue
            filing_date = _parse_datetime(_index_value(recent.get("filingDate"), index))
            if filing_date is None:
                continue
            rows.append(
                FundamentalsFilingRecord(
                    form=form,
                    filing_date=filing_date,
                    report_period=_parse_datetime(_index_value(recent.get("reportDate"), index)),
                    acceptance_datetime=_parse_datetime(_index_value(recent.get("acceptanceDateTime"), index)),
                    accession_number=_index_value(recent.get("accessionNumber"), index),
                    primary_document=_index_value(recent.get("primaryDocument"), index),
                    is_amendment=form.endswith("/A"),
                    source_provider="sec",
                    retrieved_at=retrieved_at,
                    origin="fundamentals.sec.submissions.recent_filings",
                )
            )
        rows.sort(key=lambda row: row.filing_date, reverse=True)
        return rows[:limit]

    def _build_statement_view(
        self,
        company_facts_payload: dict[str, Any],
        *,
        statement: str,
        basis: str,
        retrieved_at: datetime,
    ) -> FundamentalsStatementView:
        definitions = [row for row in _STATEMENT_LINE_DEFINITIONS if row.statement == statement]
        period_map: dict[str, FundamentalsPeriodRecord] = {}
        lines: list[FundamentalsStatementLine] = []
        for definition in definitions:
            selected = self._select_observations(company_facts_payload, definition=definition, basis=basis)
            for period_key, observation in selected.items():
                period_map.setdefault(
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
                    source_provider="sec",
                    retrieved_at=retrieved_at,
                    origin=f"fundamentals.sec.company_facts.{definition.line_key}",
                )
                for period_key, observation in selected.items()
            ]
            cells.sort(key=lambda cell: _sortable_datetime(cell.end_date))
            lines.append(
                FundamentalsStatementLine(
                    line_key=definition.line_key,
                    label=definition.label,
                    statement=statement,
                    unit=definition.unit,
                    cells=cells,
                    source_provider="sec",
                    retrieved_at=retrieved_at,
                    origin=f"fundamentals.sec.company_facts.{definition.line_key}",
                )
            )
        periods = sorted(period_map.values(), key=lambda row: _sortable_datetime(row.end_date))
        keep_keys = [row.period_key for row in (periods[-6:] if basis == "annual" else periods[-8:])]
        normalized_lines = [self._ensure_line_cells(line, keep_keys) for line in lines]
        trimmed_periods = [row for row in periods if row.period_key in set(keep_keys)]
        return FundamentalsStatementView(
            statement=statement,
            basis=basis,
            periods=trimmed_periods,
            lines=normalized_lines,
            source_provider="sec",
            retrieved_at=retrieved_at,
            origin=f"fundamentals.sec.company_facts.{statement}.{basis}",
        )

    def _select_observations(
        self,
        company_facts_payload: dict[str, Any],
        *,
        definition: StatementLineDefinition,
        basis: str,
    ) -> dict[str, FactObservation]:
        observations: list[FactObservation] = []
        for concept_ref in definition.concepts:
            taxonomy, concept_name = concept_ref.split(":", 1)
            taxonomy_payload = company_facts_payload.get("facts", {}).get(taxonomy, {}) or {}
            concept_payload = taxonomy_payload.get(concept_name)
            if not isinstance(concept_payload, dict):
                continue
            units = concept_payload.get("units", {}) or {}
            unit_key = self._preferred_unit_key(units, definition.unit)
            if not unit_key:
                continue
            for raw in units.get(unit_key, []) or []:
                observation = self._build_observation(concept_name, raw)
                if observation is None or not self._matches_basis(observation, definition.period_kind, basis):
                    continue
                observations.append(observation)
        selected: dict[str, FactObservation] = {}
        for observation in observations:
            period_key = self._period_key(basis=basis, observation=observation)
            winner = selected.get(period_key)
            if winner is None or self._observation_rank(observation) > self._observation_rank(winner):
                selected[period_key] = observation
        return selected

    def _preferred_unit_key(self, units: dict[str, Any], expected_unit: str) -> str | None:
        if not isinstance(units, dict):
            return None
        if expected_unit == "currency":
            for key in units:
                if str(key).upper().startswith("USD"):
                    return key
        if expected_unit == "shares":
            for key in units:
                if str(key).lower().startswith("shares"):
                    return key
        return next(iter(units.keys()), None)

    def _build_observation(self, concept_name: str, raw: dict[str, Any]) -> FactObservation | None:
        try:
            value = float(raw.get("val"))
        except (TypeError, ValueError):
            return None
        return FactObservation(
            concept_name=concept_name,
            value=value,
            start_date=_parse_datetime(raw.get("start")),
            end_date=_parse_datetime(raw.get("end")),
            filing_date=_parse_datetime(raw.get("filed")),
            filing_date_text=_clean_text(raw.get("filed")),
            form=_clean_text(raw.get("form")),
            accession_number=_clean_text(raw.get("accn")),
            fiscal_year=_parse_int(raw.get("fy")),
            fiscal_period=_clean_text(raw.get("fp")),
            is_amendment=str(raw.get("form") or "").endswith("/A"),
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

    def _period_key(self, *, basis: str, observation: FactObservation) -> str:
        if basis == "annual":
            return f"FY-{observation.fiscal_year or _year(observation.end_date)}"
        end_label = observation.end_date.date().isoformat() if observation.end_date else "unknown"
        return f"{observation.fiscal_period or 'Q'}-{observation.fiscal_year or _year(observation.end_date)}-{end_label}"

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
