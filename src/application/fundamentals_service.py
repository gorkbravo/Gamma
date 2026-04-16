from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from src.models.fundamentals import (
    FundamentalsCoverageRecord,
    FundamentalsCompanyRecord,
    FundamentalsDcfModelRecord,
    FundamentalsDcfRowRecord,
    FundamentalsDcfScenarioRecord,
    FundamentalsDcfSensitivityCell,
    FundamentalsDcfSensitivityMatrix,
    FundamentalsDcfSnapshotRecord,
    FundamentalsDcfValuationSummary,
    FundamentalsFinancialsResult,
    FundamentalsMetricRecord,
    FundamentalsOverviewResult,
    FundamentalsPeerBasketRecord,
    FundamentalsPeerCandidateRecord,
    FundamentalsPeerComparisonRecord,
    FundamentalsPeerDiagnosticsRecord,
    FundamentalsPeerHeatmapCell,
    FundamentalsPeerHeatmapMetricRow,
    FundamentalsPeerHeatmapView,
    FundamentalsPeersResult,
    FundamentalsRawNormalizedInspectionResult,
    FundamentalsReferenceResult,
    FundamentalsReverseValuationDriverRecord,
    FundamentalsReverseValuationResult,
    FundamentalsReverseValuationSensitivityCell,
    FundamentalsReverseValuationSensitivityMatrix,
    FundamentalsSearchResult,
    FundamentalsSourceTraceRecord,
    FundamentalsStatementCell,
    FundamentalsStatementLine,
    FundamentalsStatementView,
)
from src.services.fundamentals_adapters import (
    IbkrPriceContext,
    IbkrValuationAdapter,
    SecCompanyData,
    SecFundamentalsAdapter,
)
from src.services.fundamentals_store import FundamentalsResearchStore


_DEFAULT_PEER_SEEDS: dict[str, tuple[str, ...]] = {
    "AAPL": ("MSFT", "GOOGL", "AMZN", "META", "SAP"),
    "MSFT": ("AAPL", "GOOGL", "ORCL", "SAP", "CRM"),
    "SAP": ("MSFT", "ORCL", "CRM", "NOW", "ADBE"),
    "ORCL": ("MSFT", "SAP", "CRM", "NOW", "ADBE"),
    "CRM": ("MSFT", "ORCL", "SAP", "NOW", "ADBE"),
    "NVDA": ("AMD", "AVGO", "QCOM", "MU", "INTC"),
    "AMD": ("NVDA", "AVGO", "QCOM", "MU", "INTC"),
    "GOOGL": ("META", "AMZN", "MSFT", "ORCL", "CRM"),
    "AMZN": ("GOOGL", "META", "MSFT", "ORCL", "WMT"),
    "META": ("GOOGL", "AMZN", "MSFT", "SNAP", "RDDT"),
}

_SIC_SEED_MAP: dict[str, tuple[str, ...]] = {
    "electronic computers": ("AAPL", "MSFT", "DELL", "HPQ", "SMCI"),
    "prepackaged software": ("MSFT", "ORCL", "SAP", "CRM", "ADBE", "NOW"),
    "semiconductors": ("NVDA", "AMD", "AVGO", "QCOM", "MU", "INTC"),
    "retail-catalog": ("AMZN", "WMT", "COST", "TGT", "EBAY"),
}

_DCF_SCENARIO_LABELS = {
    "bear": "Bear",
    "base": "Base",
    "bull": "Bull",
}

_DCF_ASSUMPTION_ORDER: tuple[tuple[str, str, str], ...] = (
    ("revenue_growth_pct", "Revenue Growth", "percent"),
    ("ebit_margin_pct", "EBIT Margin", "percent"),
    ("tax_rate_pct", "Tax Rate", "percent"),
    ("da_pct_revenue", "D&A / Revenue", "percent"),
    ("capex_pct_revenue", "Capex / Revenue", "percent"),
    ("nwc_pct_incremental_revenue", "NWC / Incremental Revenue", "percent"),
    ("shares_outstanding", "Shares Outstanding", "shares"),
)

_DCF_PROJECTION_LINE_ORDER: tuple[tuple[str, str, str], ...] = (
    ("revenue", "Revenue", "currency"),
    ("ebit", "EBIT", "currency"),
    ("taxes", "Taxes", "currency"),
    ("depreciation_and_amortization", "D&A", "currency"),
    ("capital_expenditures", "Capex", "currency"),
    ("change_in_nwc", "Change In NWC", "currency"),
    ("free_cash_flow", "Free Cash Flow", "currency"),
    ("discount_factor", "Discount Factor", "ratio"),
    ("present_value_of_fcf", "PV of FCF", "currency"),
)


class FundamentalsService:
    def __init__(
        self,
        *,
        sec_adapter: SecFundamentalsAdapter,
        valuation_adapter: IbkrValuationAdapter,
        store: FundamentalsResearchStore,
    ) -> None:
        self.sec_adapter = sec_adapter
        self.valuation_adapter = valuation_adapter
        self.store = store

    def search_companies(
        self,
        query: str,
        *,
        limit: int = 12,
        force_refresh: bool = False,
    ) -> list[FundamentalsSearchResult]:
        return self.sec_adapter.search_companies(query, limit=limit, force_refresh=force_refresh)

    def get_overview(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsOverviewResult | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        price_context = self.valuation_adapter.get_price_context(ticker, force_refresh=force_refresh)
        market_context = self._build_market_context(sec_data, price_context)
        peer_basket = self._load_or_create_peer_basket(sec_data.company)
        peer_candidates = self._build_peer_candidates(sec_data.company, peer_basket)
        peer_heatmap = self._build_peer_heatmap(sec_data.company, peer_basket)
        dcf_model = self.get_dcf_model(ticker, force_refresh=force_refresh)
        warnings = _dedupe_warnings(price_context.warnings, dcf_model.warnings if dcf_model else [])
        return FundamentalsOverviewResult(
            company=sec_data.company,
            headline_metrics=self._build_headline_metrics(sec_data, market_context),
            price_history=price_context.price_history[-180:],
            filings=sec_data.filings[:8],
            peer_candidates=peer_candidates,
            peer_basket=peer_basket,
            peer_heatmap=peer_heatmap,
            dcf_summary=[scenario.summary for scenario in dcf_model.scenarios if scenario.summary is not None]
            if dcf_model
            else [],
            warnings=warnings,
        )

    def get_financials(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsFinancialsResult | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        price_context = self.valuation_adapter.get_price_context(ticker, force_refresh=force_refresh)
        market_context = self._build_market_context(sec_data, price_context)
        return FundamentalsFinancialsResult(
            company=sec_data.company,
            annual_income_statement=sec_data.annual_income_statement,
            annual_balance_sheet=sec_data.annual_balance_sheet,
            annual_cash_flow_statement=sec_data.annual_cash_flow_statement,
            quarterly_income_statement=sec_data.quarterly_income_statement,
            quarterly_balance_sheet=sec_data.quarterly_balance_sheet,
            quarterly_cash_flow_statement=sec_data.quarterly_cash_flow_statement,
            annual_ratio_view=self._build_ratio_view(
                sec_data,
                basis="annual",
                market_context=market_context,
            ),
            quarterly_ratio_view=self._build_ratio_view(
                sec_data,
                basis="quarterly",
                market_context=market_context,
            ),
            filings=sec_data.filings[:12],
            warnings=_dedupe_warnings(price_context.warnings),
        )

    def get_peers(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsPeersResult | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        peer_basket = self._load_or_create_peer_basket(sec_data.company)
        peer_candidates = self._build_peer_candidates(sec_data.company, peer_basket)
        peer_heatmap = self._build_peer_heatmap(sec_data.company, peer_basket)
        comparisons = self._build_peer_comparisons(sec_data.company, peer_basket)
        diagnostics = self._build_peer_diagnostics(peer_heatmap)
        return FundamentalsPeersResult(
            company=sec_data.company,
            peer_basket=peer_basket,
            peer_candidates=peer_candidates,
            peer_heatmap=peer_heatmap,
            comparisons=comparisons,
            diagnostics=diagnostics,
            warnings=[
                item.warning
                for item in diagnostics
                if item.warning
            ],
            source_provider="gamma",
            retrieved_at=datetime.now(timezone.utc),
            origin="fundamentals.peers",
            transformation_note="Gamma materializes the persistent peer basket into valuation, profitability, growth, efficiency, leverage, and implied-expectation comparison rows.",
        )

    def get_reference(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsReferenceResult | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        inspection = self._build_raw_normalized_inspection(sec_data)
        provider_warnings = self._provider_config_warnings()
        warnings = _dedupe_warnings(inspection.warnings, provider_warnings)
        return FundamentalsReferenceResult(
            company=sec_data.company,
            filings=sec_data.filings,
            inspection=inspection,
            provider_warnings=provider_warnings,
            warnings=warnings,
            source_provider="sec",
            retrieved_at=sec_data.company.retrieved_at,
            origin="fundamentals.reference",
            transformation_note="Gamma packages SEC filing chronology, company-facts coverage, and raw-versus-normalized statement traces for audit-oriented fundamentals research.",
        )

    def get_reverse_valuation(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsReverseValuationResult | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        price_context = self.valuation_adapter.get_price_context(ticker, force_refresh=force_refresh)
        return self._build_reverse_valuation(sec_data, price_context, include_sensitivity=True)

    def get_dcf_model(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsDcfModelRecord | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        price_context = self.valuation_adapter.get_price_context(ticker, force_refresh=force_refresh)
        market_context = self._build_market_context(sec_data, price_context)
        raw_model = self.store.load_dcf_model(sec_data.company.ticker) or self._create_default_dcf_payload(sec_data, market_context)
        return self._materialize_dcf_model(sec_data, market_context, raw_model)

    def save_dcf_model(
        self,
        ticker: str,
        payload: dict[str, Any],
        *,
        force_refresh: bool = False,
    ) -> FundamentalsDcfModelRecord | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        price_context = self.valuation_adapter.get_price_context(ticker, force_refresh=force_refresh)
        market_context = self._build_market_context(sec_data, price_context)
        sanitized = self._sanitize_dcf_payload(sec_data.company.ticker, payload, sec_data, market_context)
        self.store.save_dcf_model(sec_data.company.ticker, sanitized)
        return self._materialize_dcf_model(sec_data, market_context, sanitized)

    def list_dcf_snapshots(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> list[FundamentalsDcfSnapshotRecord] | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        return [
            self._snapshot_record_from_payload(payload)
            for payload in self.store.list_dcf_snapshots(sec_data.company.ticker)
        ]

    def save_dcf_snapshot(
        self,
        ticker: str,
        *,
        name: str | None = None,
        force_refresh: bool = False,
    ) -> FundamentalsDcfSnapshotRecord | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        price_context = self.valuation_adapter.get_price_context(ticker, force_refresh=force_refresh)
        market_context = self._build_market_context(sec_data, price_context)
        raw_model = self.store.load_dcf_model(sec_data.company.ticker) or self._create_default_dcf_payload(sec_data, market_context)
        materialized = self._materialize_dcf_model(sec_data, market_context, raw_model)
        created_at = datetime.now(timezone.utc)
        clean_name = str(name or "").strip() or f"{materialized.active_scenario_id.title()} snapshot"
        snapshot_id = self._build_snapshot_id(created_at, clean_name)
        payload = {
            "snapshot_id": snapshot_id,
            "ticker": sec_data.company.ticker,
            "name": clean_name,
            "created_at": created_at.isoformat(),
            "active_scenario_id": materialized.active_scenario_id,
            "projection_years": list(materialized.projection_years),
            "model": {
                "ticker": sec_data.company.ticker,
                "active_scenario_id": materialized.active_scenario_id,
                "projection_years": list(materialized.projection_years),
                "scenarios": deepcopy(raw_model.get("scenarios", {})),
            },
            "scenario_summaries": [
                _summary_to_payload(scenario.summary)
                for scenario in materialized.scenarios
                if scenario.summary is not None
            ],
            "source_provider": "manual",
            "retrieved_at": created_at.isoformat(),
            "origin": "fundamentals.dcf.snapshot",
            "transformation_note": "Gamma snapshots the locally persisted DCF scenario inputs with the then-current computed scenario summaries for later read-only recall.",
        }
        self.store.save_dcf_snapshot(sec_data.company.ticker, snapshot_id, payload)
        return self._snapshot_record_from_payload(payload)

    def load_dcf_snapshot_model(
        self,
        ticker: str,
        snapshot_id: str,
        *,
        force_refresh: bool = False,
    ) -> FundamentalsDcfModelRecord | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        payload = self.store.load_dcf_snapshot(sec_data.company.ticker, snapshot_id)
        if payload is None:
            return None
        price_context = self.valuation_adapter.get_price_context(ticker, force_refresh=force_refresh)
        market_context = self._build_market_context(sec_data, price_context)
        raw_model = payload.get("model") if isinstance(payload.get("model"), dict) else payload
        return self._materialize_dcf_model(sec_data, market_context, raw_model)

    def save_peer_basket(
        self,
        ticker: str,
        peer_tickers: list[str],
        *,
        force_refresh: bool = False,
    ) -> FundamentalsPeerBasketRecord | None:
        sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=force_refresh)
        if sec_data is None:
            return None
        cleaned = [
            value
            for value in dict.fromkeys(
                str(item or "").strip().upper()
                for item in peer_tickers
                if str(item or "").strip()
            )
            if value != sec_data.company.ticker
        ]
        basket = self._build_peer_basket_record(
            sec_data.company,
            peer_tickers=cleaned,
            user_edited=True,
            transformation_note="Gamma persists the peer basket as a local research object so the same peer set can anchor overview and valuation comparisons.",
        )
        self.store.save_peer_basket(sec_data.company.ticker, self._peer_basket_to_payload(basket))
        return basket

    def _build_headline_metrics(
        self,
        sec_data: SecCompanyData,
        market_context: dict[str, Any],
    ) -> list[FundamentalsMetricRecord]:
        annual = self._statement_value_map(sec_data.annual_income_statement)
        balance = self._statement_value_map(sec_data.annual_balance_sheet)
        revenue = _last_non_null(annual.get("revenue", []))
        ebit = _last_non_null(annual.get("operating_income", []))
        operating_cash_flow = _last_non_null(self._statement_value_map(sec_data.annual_cash_flow_statement).get("operating_cash_flow", []))
        capex = _last_non_null(self._statement_value_map(sec_data.annual_cash_flow_statement).get("capital_expenditures", []))
        fcf = _subtract_nullable(operating_cash_flow, capex)
        diluted_shares = _first_non_null(
            _last_non_null(annual.get("diluted_shares", [])),
            _last_non_null(balance.get("shares_outstanding", [])),
        )
        metrics: list[FundamentalsMetricRecord] = [
            _metric("revenue", "Revenue", revenue, "currency", "sec", sec_data.company.retrieved_at, "fundamentals.sec.revenue"),
            _metric("ebit", "EBIT", ebit, "currency", "sec", sec_data.company.retrieved_at, "fundamentals.sec.ebit"),
            _metric(
                "free_cash_flow",
                "FCF",
                fcf,
                "currency",
                "gamma",
                market_context["retrieved_at"],
                "fundamentals.analytics.free_cash_flow",
                "Gamma derives free cash flow as operating cash flow minus capital expenditures from annual SEC cash-flow statements.",
            ),
            _metric("current_price", "Price", market_context.get("current_price"), "price", market_context["source_provider"], market_context["retrieved_at"], market_context["origin"], market_context.get("transformation_note")),
            _metric(
                "market_cap",
                "Market Cap",
                market_context.get("market_cap"),
                "currency",
                market_context["source_provider"],
                market_context["retrieved_at"],
                "fundamentals.market.market_cap",
                "Gamma derives market cap from the current price context and latest shares outstanding.",
            ),
            _metric(
                "enterprise_value",
                "Enterprise Value",
                market_context.get("enterprise_value"),
                "currency",
                market_context["source_provider"],
                market_context["retrieved_at"],
                "fundamentals.market.enterprise_value",
                "Gamma derives enterprise value from market cap plus total debt minus cash and current marketable securities.",
            ),
            _metric(
                "ev_to_sales",
                "EV / Sales",
                _safe_ratio(market_context.get("enterprise_value"), revenue),
                "ratio",
                "gamma",
                market_context["retrieved_at"],
                "fundamentals.analytics.ev_to_sales",
                "Gamma combines current enterprise value with the latest annual revenue from SEC filings.",
            ),
            _metric(
                "ev_to_ebit",
                "EV / EBIT",
                _safe_ratio(market_context.get("enterprise_value"), ebit),
                "ratio",
                "gamma",
                market_context["retrieved_at"],
                "fundamentals.analytics.ev_to_ebit",
                "Gamma combines current enterprise value with the latest annual operating income from SEC filings.",
            ),
            _metric(
                "net_debt",
                "Net Debt",
                market_context.get("net_debt"),
                "currency",
                "gamma",
                market_context["retrieved_at"],
                "fundamentals.analytics.net_debt",
                "Gamma derives net debt from debt, cash, and current marketable securities sourced from the annual SEC balance sheet.",
            ),
            _metric(
                "diluted_shares",
                "Diluted Shares",
                diluted_shares,
                "shares",
                "sec",
                sec_data.company.retrieved_at,
                "fundamentals.sec.diluted_shares",
            ),
        ]
        return metrics

    def _build_market_context(
        self,
        sec_data: SecCompanyData,
        price_context: IbkrPriceContext,
    ) -> dict[str, Any]:
        annual_income = self._statement_value_map(sec_data.annual_income_statement)
        annual_balance = self._statement_value_map(sec_data.annual_balance_sheet)
        shares = _first_non_null(
            _last_non_null(annual_income.get("diluted_shares", [])),
            _last_non_null(annual_balance.get("shares_outstanding", [])),
        )
        cash = _sum_nullable(
            _last_non_null(annual_balance.get("cash_and_equivalents", [])),
            _last_non_null(annual_balance.get("marketable_securities_current", [])),
        )
        total_debt = _sum_nullable(
            _last_non_null(annual_balance.get("short_term_debt", [])),
            _last_non_null(annual_balance.get("long_term_debt", [])),
        )
        market_cap = _multiply_nullable(price_context.current_price, shares)
        net_debt = _subtract_nullable(total_debt, cash)
        enterprise_value = None
        if market_cap is not None:
            enterprise_value = market_cap + (total_debt or 0.0) - (cash or 0.0)
        return {
            "current_price": price_context.current_price,
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "net_debt": net_debt,
            "total_debt": total_debt,
            "cash": cash,
            "shares": shares,
            "retrieved_at": price_context.retrieved_at or sec_data.company.retrieved_at,
            "source_provider": price_context.source_provider,
            "origin": price_context.origin,
            "transformation_note": price_context.transformation_note,
        }

    def _build_ratio_view(
        self,
        sec_data: SecCompanyData,
        *,
        basis: str,
        market_context: dict[str, Any],
    ) -> FundamentalsStatementView:
        income_view = sec_data.annual_income_statement if basis == "annual" else sec_data.quarterly_income_statement
        balance_view = sec_data.annual_balance_sheet if basis == "annual" else sec_data.quarterly_balance_sheet
        cash_view = sec_data.annual_cash_flow_statement if basis == "annual" else sec_data.quarterly_cash_flow_statement
        periods = list(income_view.periods)
        income = self._statement_value_map(income_view)
        balance = self._statement_value_map(balance_view)
        cash = self._statement_value_map(cash_view)
        revenues = income.get("revenue", [])
        gross_profit = income.get("gross_profit", [])
        ebit = income.get("operating_income", [])
        net_income = income.get("net_income", [])
        taxes = income.get("income_tax", [])
        current_assets = balance.get("current_assets", [])
        current_liabilities = balance.get("current_liabilities", [])
        equity = balance.get("shareholders_equity", [])
        total_assets = balance.get("total_assets", [])
        debt = _series_sum(balance.get("short_term_debt", []), balance.get("long_term_debt", []))
        cash_values = _series_sum(balance.get("cash_and_equivalents", []), balance.get("marketable_securities_current", []))
        operating_cash_flow = cash.get("operating_cash_flow", [])
        capex = cash.get("capital_expenditures", [])
        fcf = [_subtract_nullable(ocf, cx) for ocf, cx in zip(operating_cash_flow, capex, strict=False)]
        gross_margin = [_safe_ratio(gp, rev) for gp, rev in zip(gross_profit, revenues, strict=False)]
        ebit_margin = [_safe_ratio(value, rev) for value, rev in zip(ebit, revenues, strict=False)]
        fcf_margin = [_safe_ratio(value, rev) for value, rev in zip(fcf, revenues, strict=False)]
        revenue_growth = _series_growth(revenues)
        ebit_growth = _series_growth(ebit)
        fcf_growth = _series_growth(fcf)
        current_ratio = [_safe_ratio(a, l) for a, l in zip(current_assets, current_liabilities, strict=False)]
        cash_conversion = [_safe_ratio(f, n) for f, n in zip(fcf, net_income, strict=False)]
        roe = _series_return_metric(net_income, equity)
        roic = _series_roic(ebit, taxes, debt, equity, cash_values)
        net_debt_to_ebit = [
            _safe_ratio(_subtract_nullable(d, c), e)
            for d, c, e in zip(debt, cash_values, ebit, strict=False)
        ]
        asset_turnover = [_safe_ratio(rev, avg_assets) for rev, avg_assets in zip(revenues, _series_average(total_assets), strict=False)]
        rows = [
            _derived_ratio_line("gross_margin", "Gross Margin", gross_margin, periods, basis),
            _derived_ratio_line("ebit_margin", "EBIT Margin", ebit_margin, periods, basis),
            _derived_ratio_line("fcf_margin", "FCF Margin", fcf_margin, periods, basis),
            _derived_ratio_line("revenue_growth", "Revenue Growth", revenue_growth, periods, basis),
            _derived_ratio_line("ebit_growth", "EBIT Growth", ebit_growth, periods, basis),
            _derived_ratio_line("fcf_growth", "FCF Growth", fcf_growth, periods, basis),
            _derived_ratio_line("current_ratio", "Current Ratio", current_ratio, periods, basis),
            _derived_ratio_line("cash_conversion", "Cash Conversion", cash_conversion, periods, basis),
            _derived_ratio_line("roe", "ROE", roe, periods, basis),
            _derived_ratio_line("roic", "ROIC", roic, periods, basis),
            _derived_ratio_line("asset_turnover", "Asset Turnover", asset_turnover, periods, basis),
            _derived_ratio_line("net_debt_to_ebit", "Net Debt / EBIT", net_debt_to_ebit, periods, basis),
        ]
        return FundamentalsStatementView(
            statement="ratios",
            basis=basis,
            periods=periods,
            lines=rows,
            source_provider="gamma",
            retrieved_at=market_context["retrieved_at"],
            origin=f"fundamentals.analytics.ratios.{basis}",
            transformation_note="Gamma derives margin, growth, liquidity, leverage, and return metrics from normalized SEC statements, with market-aware metrics computed separately in overview and comps.",
        )

    def _load_or_create_peer_basket(self, company: FundamentalsCompanyRecord) -> FundamentalsPeerBasketRecord:
        stored = self.store.load_peer_basket(company.ticker)
        if stored:
            peer_tickers = [
                str(value or "").strip().upper()
                for value in stored.get("peer_tickers", []) or []
                if str(value or "").strip()
            ]
            return self._build_peer_basket_record(
                company,
                peer_tickers=peer_tickers,
                user_edited=bool(stored.get("user_edited")),
                transformation_note="Gamma restores the peer basket from the persisted local research object.",
            )
        defaults = self._default_peer_seed(company)
        basket = self._build_peer_basket_record(
            company,
            peer_tickers=list(defaults),
            user_edited=False,
            transformation_note="Gamma seeds the initial peer basket from a practical first-pass peer map and keeps the basket stable until the user edits it.",
        )
        self.store.save_peer_basket(company.ticker, self._peer_basket_to_payload(basket))
        return basket

    def _default_peer_seed(self, company: FundamentalsCompanyRecord) -> tuple[str, ...]:
        if company.ticker in _DEFAULT_PEER_SEEDS:
            return _DEFAULT_PEER_SEEDS[company.ticker]
        sic_text = str(company.sic_description or "").strip().lower()
        for needle, seeds in _SIC_SEED_MAP.items():
            if needle in sic_text:
                return tuple(ticker for ticker in seeds if ticker != company.ticker)
        return tuple(ticker for ticker in _DEFAULT_PEER_SEEDS.get("MSFT", ()) if ticker != company.ticker)

    def _build_peer_basket_record(
        self,
        company: FundamentalsCompanyRecord,
        *,
        peer_tickers: list[str],
        user_edited: bool,
        transformation_note: str,
    ) -> FundamentalsPeerBasketRecord:
        display_order = [company.ticker, *peer_tickers]
        return FundamentalsPeerBasketRecord(
            focal_ticker=company.ticker,
            basket_label=f"{company.ticker} peer basket",
            peer_tickers=peer_tickers,
            display_order=display_order,
            user_edited=user_edited,
            source_provider="gamma",
            retrieved_at=datetime.now(timezone.utc),
            origin="fundamentals.peer_basket",
            transformation_note=transformation_note,
        )

    def _peer_basket_to_payload(self, basket: FundamentalsPeerBasketRecord) -> dict[str, Any]:
        return {
            "focal_ticker": basket.focal_ticker,
            "peer_tickers": list(basket.peer_tickers),
            "display_order": list(basket.display_order),
            "user_edited": basket.user_edited,
        }

    def _build_peer_candidates(
        self,
        company: FundamentalsCompanyRecord,
        peer_basket: FundamentalsPeerBasketRecord,
    ) -> list[FundamentalsPeerCandidateRecord]:
        results: list[FundamentalsPeerCandidateRecord] = []
        selected = set(peer_basket.peer_tickers)
        candidate_tickers = list(peer_basket.peer_tickers)
        for seed in self._default_peer_seed(company):
            if seed not in candidate_tickers and seed != company.ticker:
                candidate_tickers.append(seed)
        for ticker in candidate_tickers[:8]:
            search_match = self.sec_adapter.search_companies(ticker, limit=1)
            result = search_match[0] if search_match else FundamentalsSearchResult(
                ticker=ticker,
                name=ticker,
                cik="",
                exchange=None,
                source_provider="sec",
                retrieved_at=datetime.now(timezone.utc),
                origin="fundamentals.peer_seed",
                transformation_note="Gamma fell back to the seeded peer ticker because the SEC search index did not return a richer match.",
            )
            results.append(
                FundamentalsPeerCandidateRecord(
                    ticker=result.ticker,
                    name=result.name,
                    reason="Peer basket member" if ticker in selected else "Seed candidate",
                    exchange=result.exchange,
                    classification_label=company.sic_description,
                    selected=ticker in selected,
                    source_provider="gamma",
                    retrieved_at=result.retrieved_at,
                    origin="fundamentals.peer_candidates",
                    transformation_note="Gamma seeds peer candidates from the current basket and the initial peer map so the user can refine a stable comps set.",
                )
            )
        return results

    def _build_peer_heatmap(
        self,
        company: FundamentalsCompanyRecord,
        peer_basket: FundamentalsPeerBasketRecord,
    ) -> FundamentalsPeerHeatmapView | None:
        ordered_tickers = [company.ticker, *[ticker for ticker in peer_basket.peer_tickers if ticker != company.ticker]]
        company_metrics: dict[str, dict[str, Any]] = {}
        for ticker in ordered_tickers[:6]:
            sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=False)
            if sec_data is None:
                continue
            price_context = self.valuation_adapter.get_price_context(ticker)
            market_context = self._build_market_context(sec_data, price_context)
            company_metrics[ticker] = self._company_metric_snapshot(sec_data, market_context)
        if not company_metrics:
            return None
        rows: list[FundamentalsPeerHeatmapMetricRow] = []
        for metric_id, label, family in (
            ("ev_to_sales", "EV / Sales", "valuation"),
            ("ev_to_ebit", "EV / EBIT", "valuation"),
            ("price_to_earnings", "P / E", "valuation"),
            ("fcf_yield", "FCF Yield", "valuation"),
            ("gross_margin", "Gross Margin", "profitability"),
            ("ebit_margin", "EBIT Margin", "profitability"),
            ("fcf_margin", "FCF Margin", "profitability"),
            ("revenue_growth", "Revenue Growth", "growth"),
            ("ebit_growth", "EBIT Growth", "growth"),
            ("fcf_growth", "FCF Growth", "growth"),
            ("roic", "ROIC", "returns"),
            ("roe", "ROE", "returns"),
            ("asset_turnover", "Asset Turnover", "efficiency"),
            ("cash_conversion", "Cash Conversion", "efficiency"),
            ("current_ratio", "Current Ratio", "leverage"),
            ("net_debt_to_ebit", "Net Debt / EBIT", "leverage"),
        ):
            cells: list[FundamentalsPeerHeatmapCell] = []
            for ticker in ordered_tickers:
                metric = company_metrics.get(ticker, {}).get(metric_id)
                cells.append(
                    FundamentalsPeerHeatmapCell(
                        ticker=ticker,
                        value=None if metric is None else metric.get("value"),
                        display_value=None if metric is None else metric.get("display"),
                        source_provider="gamma",
                        retrieved_at=datetime.now(timezone.utc),
                        origin=f"fundamentals.peer_heatmap.{metric_id}",
                        transformation_note=(
                            metric.get("note")
                            if metric is not None
                            else "Gamma preserves the peer heatmap row with a null value because the required SEC taxonomy or market context was unavailable."
                        ),
                    )
                )
            rows.append(
                FundamentalsPeerHeatmapMetricRow(
                    metric_id=metric_id,
                    label=label,
                    family=family,
                    cells=cells,
                    source_provider="gamma",
                    retrieved_at=datetime.now(timezone.utc),
                    origin=f"fundamentals.peer_heatmap.{metric_id}",
                    transformation_note="Gamma keeps the peer basket order stable across the heatmap so valuation and operating metrics remain directly comparable.",
                )
            )
        return FundamentalsPeerHeatmapView(
            tickers=ordered_tickers,
            rows=rows,
            source_provider="gamma",
            retrieved_at=datetime.now(timezone.utc),
            origin="fundamentals.peer_heatmap",
            transformation_note="Gamma derives the comps heatmap from normalized SEC statements plus the current IBKR price context where market multiples are required.",
        )

    def _company_metric_snapshot(
        self,
        sec_data: SecCompanyData,
        market_context: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        annual_income = self._statement_value_map(sec_data.annual_income_statement)
        annual_balance = self._statement_value_map(sec_data.annual_balance_sheet)
        annual_cash = self._statement_value_map(sec_data.annual_cash_flow_statement)
        revenue = annual_income.get("revenue", [])
        gross_profit = annual_income.get("gross_profit", [])
        ebit = annual_income.get("operating_income", [])
        net_income = annual_income.get("net_income", [])
        taxes = annual_income.get("income_tax", [])
        current_assets = annual_balance.get("current_assets", [])
        current_liabilities = annual_balance.get("current_liabilities", [])
        total_assets = annual_balance.get("total_assets", [])
        equity = annual_balance.get("shareholders_equity", [])
        debt = _series_sum(annual_balance.get("short_term_debt", []), annual_balance.get("long_term_debt", []))
        cash_values = _series_sum(
            annual_balance.get("cash_and_equivalents", []),
            annual_balance.get("marketable_securities_current", []),
        )
        operating_cash_flow = annual_cash.get("operating_cash_flow", [])
        capex = annual_cash.get("capital_expenditures", [])
        fcf = [_subtract_nullable(ocf, cx) for ocf, cx in zip(operating_cash_flow, capex, strict=False)]
        metrics = {
            "ev_to_sales": _heatmap_metric(
                _safe_ratio(market_context.get("enterprise_value"), _last_non_null(revenue)),
                "ratio",
                "Gamma combines current enterprise value with the latest annual revenue from SEC filings.",
            ),
            "ev_to_ebit": _heatmap_metric(
                _safe_ratio(market_context.get("enterprise_value"), _last_non_null(ebit)),
                "ratio",
                "Gamma combines current enterprise value with the latest annual operating income from SEC filings.",
            ),
            "price_to_earnings": _heatmap_metric(
                _safe_ratio(market_context.get("market_cap"), _last_non_null(net_income)),
                "ratio",
                "Gamma combines current market capitalization with the latest annual net income from SEC filings.",
            ),
            "fcf_yield": _heatmap_metric(
                _safe_ratio(_last_non_null(fcf), market_context.get("market_cap")),
                "percent",
                "Gamma derives FCF yield from the latest annual free cash flow divided by current market capitalization.",
            ),
            "gross_margin": _heatmap_metric(
                _safe_ratio(_last_non_null(gross_profit), _last_non_null(revenue)),
                "percent",
                "Gamma derives gross margin from annual SEC income-statement values.",
            ),
            "ebit_margin": _heatmap_metric(
                _safe_ratio(_last_non_null(ebit), _last_non_null(revenue)),
                "percent",
                "Gamma derives EBIT margin from annual SEC income-statement values.",
            ),
            "fcf_margin": _heatmap_metric(
                _safe_ratio(_last_non_null(fcf), _last_non_null(revenue)),
                "percent",
                "Gamma derives FCF margin from annual SEC cash-flow and income-statement values.",
            ),
            "revenue_growth": _heatmap_metric(
                _last_non_null(_series_growth(revenue)),
                "percent",
                "Gamma derives revenue growth from the latest two annual SEC revenue observations.",
            ),
            "ebit_growth": _heatmap_metric(
                _last_non_null(_series_growth(ebit)),
                "percent",
                "Gamma derives EBIT growth from the latest two annual operating-income observations.",
            ),
            "fcf_growth": _heatmap_metric(
                _last_non_null(_series_growth(fcf)),
                "percent",
                "Gamma derives free-cash-flow growth from the latest two annual cash-flow observations.",
            ),
            "roic": _heatmap_metric(
                _last_non_null(_series_roic(ebit, taxes, debt, equity, cash_values)),
                "percent",
                "Gamma approximates ROIC from annual NOPAT and average invested capital.",
            ),
            "roe": _heatmap_metric(
                _last_non_null(_series_return_metric(net_income, equity)),
                "percent",
                "Gamma approximates ROE from annual net income and average shareholder equity.",
            ),
            "asset_turnover": _heatmap_metric(
                _last_non_null([
                    _safe_ratio(rev, avg_assets)
                    for rev, avg_assets in zip(revenue, _series_average(total_assets), strict=False)
                ]),
                "ratio",
                "Gamma derives asset turnover from annual revenue and average total assets.",
            ),
            "current_ratio": _heatmap_metric(
                _safe_ratio(_last_non_null(current_assets), _last_non_null(current_liabilities)),
                "ratio",
                "Gamma derives the current ratio from annual SEC balance-sheet values.",
            ),
            "net_debt_to_ebit": _heatmap_metric(
                _safe_ratio(_subtract_nullable(_last_non_null(debt), _last_non_null(cash_values)), _last_non_null(ebit)),
                "ratio",
                "Gamma derives net debt / EBIT from annual SEC balance-sheet debt and cash values plus annual operating income.",
            ),
            "cash_conversion": _heatmap_metric(
                _safe_ratio(_last_non_null(fcf), _last_non_null(net_income)),
                "percent",
                "Gamma derives cash conversion as annual free cash flow divided by annual net income.",
            ),
        }
        return metrics

    def _build_peer_comparisons(
        self,
        company: FundamentalsCompanyRecord,
        peer_basket: FundamentalsPeerBasketRecord,
    ) -> list[FundamentalsPeerComparisonRecord]:
        comparisons: list[FundamentalsPeerComparisonRecord] = []
        selected = set(peer_basket.peer_tickers)
        ordered_tickers = [company.ticker, *[ticker for ticker in peer_basket.peer_tickers if ticker != company.ticker]]
        for ticker in ordered_tickers[:6]:
            sec_data = self.sec_adapter.load_company_data(ticker, force_refresh=False)
            if sec_data is None:
                comparisons.append(
                    FundamentalsPeerComparisonRecord(
                        ticker=ticker,
                        name=ticker,
                        selected=ticker in selected,
                        candidate_reason="Selected peer" if ticker in selected else "Focal company",
                        warnings=[f"{ticker} could not be loaded from SEC company data."],
                        source_provider="gamma",
                        retrieved_at=datetime.now(timezone.utc),
                        origin="fundamentals.peers.comparison",
                        transformation_note="Gamma preserves missing peer rows instead of silently dropping selected comparables.",
                    )
                )
                continue
            price_context = self.valuation_adapter.get_price_context(ticker)
            market_context = self._build_market_context(sec_data, price_context)
            snapshot = self._company_metric_snapshot(sec_data, market_context)
            metrics = [
                _metric(metric_id, label, snapshot.get(metric_id, {}).get("value"), unit, "gamma", datetime.now(timezone.utc), f"fundamentals.peers.metric.{metric_id}", snapshot.get(metric_id, {}).get("note"))
                for metric_id, label, unit in (
                    ("ev_to_sales", "EV / Sales", "ratio"),
                    ("ev_to_ebit", "EV / EBIT", "ratio"),
                    ("price_to_earnings", "P / E", "ratio"),
                    ("fcf_yield", "FCF Yield", "percent"),
                    ("gross_margin", "Gross Margin", "percent"),
                    ("ebit_margin", "EBIT Margin", "percent"),
                    ("fcf_margin", "FCF Margin", "percent"),
                    ("revenue_growth", "Revenue Growth", "percent"),
                    ("ebit_growth", "EBIT Growth", "percent"),
                    ("fcf_growth", "FCF Growth", "percent"),
                    ("roic", "ROIC", "percent"),
                    ("roe", "ROE", "percent"),
                    ("asset_turnover", "Asset Turnover", "ratio"),
                    ("cash_conversion", "Cash Conversion", "percent"),
                    ("net_debt_to_ebit", "Net Debt / EBIT", "ratio"),
                    ("current_ratio", "Current Ratio", "ratio"),
                )
            ]
            reverse = self._build_reverse_valuation(sec_data, price_context, include_sensitivity=False)
            for driver in reverse.drivers[:2]:
                metrics.append(
                    _metric(
                        driver.driver_id,
                        driver.label,
                        driver.implied_value,
                        "percent",
                        driver.source_provider,
                        driver.retrieved_at,
                        driver.origin,
                        driver.transformation_note,
                    )
                )
            comparisons.append(
                FundamentalsPeerComparisonRecord(
                    ticker=sec_data.company.ticker,
                    name=sec_data.company.name,
                    selected=ticker in selected,
                    candidate_reason="Selected peer" if ticker in selected else "Focal company",
                    metrics=metrics,
                    warnings=_dedupe_warnings(price_context.warnings, reverse.warnings),
                    source_provider="gamma",
                    retrieved_at=datetime.now(timezone.utc),
                    origin="fundamentals.peers.comparison",
                    transformation_note="Gamma combines normalized SEC metrics, market-aware multiples, and available reverse-valuation outputs into one peer comparison payload.",
                )
            )
        return comparisons

    def _build_peer_diagnostics(
        self,
        peer_heatmap: FundamentalsPeerHeatmapView | None,
    ) -> list[FundamentalsPeerDiagnosticsRecord]:
        if peer_heatmap is None:
            return []
        diagnostics: list[FundamentalsPeerDiagnosticsRecord] = []
        for ticker in peer_heatmap.tickers:
            missing = [
                row.metric_id
                for row in peer_heatmap.rows
                for cell in row.cells
                if cell.ticker == ticker and cell.value is None
            ]
            diagnostics.append(
                FundamentalsPeerDiagnosticsRecord(
                    ticker=ticker,
                    missing_metric_ids=missing,
                    warning=(
                        f"{ticker} is missing {len(missing)} peer metrics; market context or SEC taxonomy coverage may be incomplete."
                        if missing
                        else None
                    ),
                    source_provider="gamma",
                    retrieved_at=peer_heatmap.retrieved_at,
                    origin="fundamentals.peers.diagnostics",
                    transformation_note="Gamma reports peer missing-data diagnostics from the heatmap rather than dropping sparse companies.",
                )
            )
        return diagnostics

    def _build_raw_normalized_inspection(
        self,
        sec_data: SecCompanyData,
    ) -> FundamentalsRawNormalizedInspectionResult:
        traces: list[FundamentalsSourceTraceRecord] = []
        coverage: list[FundamentalsCoverageRecord] = []
        for view in self._statement_views_for_trace(sec_data):
            traces.extend(self._source_traces_for_view(view))
            coverage.extend(self._coverage_records_for_view(view))
        warnings = [
            record.warning
            for record in coverage
            if record.warning
        ]
        return FundamentalsRawNormalizedInspectionResult(
            company=sec_data.company,
            traces=traces,
            coverage=coverage,
            warnings=warnings,
            source_provider="sec",
            retrieved_at=sec_data.company.retrieved_at,
            origin="fundamentals.reference.raw_normalized_inspection",
            transformation_note="Gamma maps normalized statement rows back to SEC company-facts concepts, filings, accessions, amendments, and quarterly derivation notes for raw-versus-normalized inspection.",
        )

    def _statement_views_for_trace(self, sec_data: SecCompanyData) -> list[FundamentalsStatementView]:
        return [
            sec_data.annual_income_statement,
            sec_data.annual_balance_sheet,
            sec_data.annual_cash_flow_statement,
            sec_data.quarterly_income_statement,
            sec_data.quarterly_balance_sheet,
            sec_data.quarterly_cash_flow_statement,
        ]

    def _source_traces_for_view(
        self,
        view: FundamentalsStatementView,
    ) -> list[FundamentalsSourceTraceRecord]:
        period_map = {period.period_key: period for period in view.periods}
        rows: list[FundamentalsSourceTraceRecord] = []
        for line in view.lines:
            for cell in line.cells:
                period = period_map.get(cell.period_key)
                rows.append(
                    FundamentalsSourceTraceRecord(
                        statement=view.statement,
                        basis=view.basis,
                        line_key=line.line_key,
                        line_label=line.label,
                        period_key=cell.period_key,
                        period_label=period.label if period else None,
                        normalized_value=cell.value,
                        display_value=cell.display_value,
                        unit=line.unit,
                        concept_name=cell.concept_name,
                        accession_number=cell.accession_number or (period.accession_number if period else None),
                        filing_form=cell.form or (period.form if period else None),
                        fiscal_year=period.fiscal_year if period else None,
                        fiscal_period=period.fiscal_period if period else None,
                        filing_date=cell.filing_date or (period.filing_date if period else None),
                        report_period=cell.end_date or (period.end_date if period else None),
                        is_amendment=cell.is_amendment or bool(period.is_amendment if period else False),
                        source_provider=cell.source_provider,
                        retrieved_at=cell.retrieved_at or line.retrieved_at or view.retrieved_at,
                        origin=cell.origin or line.origin or view.origin,
                        transformation_note=cell.transformation_note or line.transformation_note,
                    )
                )
        return rows

    def _coverage_records_for_view(
        self,
        view: FundamentalsStatementView,
    ) -> list[FundamentalsCoverageRecord]:
        rows: list[FundamentalsCoverageRecord] = []
        period_count = len(view.periods)
        for line in view.lines:
            observed = [cell for cell in line.cells if cell.value is not None]
            concepts = sorted({cell.concept_name for cell in observed if cell.concept_name})
            missing = max(period_count - len(observed), 0)
            derived = len([cell for cell in observed if cell.source_provider == "gamma"])
            coverage_ratio = _safe_ratio(float(len(observed)), float(period_count)) if period_count else None
            warning = None
            if not observed:
                warning = f"{view.basis} {view.statement} line `{line.label}` has no mapped SEC observations in the retained periods."
            elif coverage_ratio is not None and coverage_ratio < 0.5:
                warning = f"{view.basis} {view.statement} line `{line.label}` has sparse mapped SEC coverage ({len(observed)}/{period_count})."
            rows.append(
                FundamentalsCoverageRecord(
                    statement=view.statement,
                    basis=view.basis,
                    line_key=line.line_key,
                    line_label=line.label,
                    concept_names=concepts,
                    observed_periods=len(observed),
                    missing_periods=missing,
                    derived_observations=derived,
                    coverage_ratio=coverage_ratio,
                    warning=warning,
                    source_provider=line.source_provider,
                    retrieved_at=line.retrieved_at or view.retrieved_at,
                    origin=f"fundamentals.reference.coverage.{view.basis}.{view.statement}.{line.line_key}",
                    transformation_note="Gamma computes company-facts coverage diagnostics from retained normalized statement cells and flags sparse taxonomy mappings.",
                )
            )
        return rows

    def _provider_config_warnings(self) -> list[str]:
        identity_name = str(getattr(self.sec_adapter, "identity_name", "") or "").strip()
        identity_email = str(getattr(self.sec_adapter, "identity_email", "") or "").strip()
        if identity_name == "Gorka Bravo" and identity_email == "gorka.bravo1@gmail.com":
            return [
                "SEC EDGAR access is using the existing EdgarTools development identity fallback; move to GAMMA_SEC_USER_NAME/GAMMA_SEC_USER_EMAIL when user configuration is available."
            ]
        return []

    def _build_reverse_valuation(
        self,
        sec_data: SecCompanyData,
        price_context: IbkrPriceContext,
        *,
        include_sensitivity: bool,
    ) -> FundamentalsReverseValuationResult:
        market_context = self._build_market_context(sec_data, price_context)
        raw_model = self.store.load_dcf_model(sec_data.company.ticker) or self._create_default_dcf_payload(sec_data, market_context)
        dcf_model = self._materialize_dcf_model(sec_data, market_context, raw_model)
        base_scenario = next(
            (scenario for scenario in dcf_model.scenarios if scenario.scenario_id == "base"),
            dcf_model.scenarios[0] if dcf_model.scenarios else None,
        )
        base_summary = base_scenario.summary if base_scenario else None
        actuals = self._dcf_actual_series(sec_data)
        projection_years = dcf_model.projection_years
        base_assumptions = deepcopy(base_scenario.assumptions if base_scenario else {})
        base_overrides = deepcopy(base_scenario.overrides if base_scenario else {})
        target_equity_value = _multiply_nullable(market_context.get("current_price"), market_context.get("shares"))
        target_enterprise_value = None
        if target_equity_value is not None:
            target_enterprise_value = target_equity_value + (market_context.get("net_debt") or 0.0)
        warnings = _dedupe_warnings(price_context.warnings, dcf_model.warnings)
        if market_context.get("current_price") is None:
            warnings.append("Current price context is unavailable, so reverse valuation cannot solve market-implied expectations.")
        if market_context.get("shares") in {None, 0}:
            warnings.append("Latest shares outstanding are unavailable, so reverse valuation cannot bridge price to equity value.")
        if target_enterprise_value is None:
            return FundamentalsReverseValuationResult(
                company=sec_data.company,
                current_price=market_context.get("current_price"),
                shares_outstanding=market_context.get("shares"),
                net_debt=market_context.get("net_debt"),
                target_equity_value=target_equity_value,
                target_enterprise_value=target_enterprise_value,
                base_case_summary=base_summary,
                scenario_gap_metrics=self._reverse_gap_metrics(base_summary, market_context),
                drivers=[],
                sensitivity_matrix=None,
                warnings=_dedupe_warnings(warnings),
                source_provider="gamma",
                retrieved_at=datetime.now(timezone.utc),
                origin="fundamentals.reverse_valuation",
                transformation_note="Gamma attempted to reverse the current market price into DCF expectations but lacked the market bridge inputs needed to solve.",
            )
        drivers = [
            self._solve_reverse_driver(
                driver_id="implied_revenue_cagr",
                label="Implied Revenue CAGR",
                unit="percent",
                base_value=_average_assumption(base_assumptions.get("revenue_growth_pct")),
                lower=-0.20,
                upper=0.40,
                target_enterprise_value=target_enterprise_value,
                actuals=actuals,
                projection_years=projection_years,
                base_assumptions=base_assumptions,
                base_overrides=base_overrides,
                market_context=market_context,
                mutator=lambda assumptions, value: assumptions.update({"revenue_growth_pct": [value for _ in projection_years]}),
            ),
            self._solve_reverse_driver(
                driver_id="implied_terminal_ebit_margin",
                label="Implied Terminal EBIT Margin",
                unit="percent",
                base_value=_last_assumption(base_assumptions.get("ebit_margin_pct")),
                lower=0.01,
                upper=0.65,
                target_enterprise_value=target_enterprise_value,
                actuals=actuals,
                projection_years=projection_years,
                base_assumptions=base_assumptions,
                base_overrides=base_overrides,
                market_context=market_context,
                mutator=lambda assumptions, value: assumptions.update({"ebit_margin_pct": _linear_series(_current_margin(actuals), value, len(projection_years))}),
            ),
            self._solve_reverse_driver(
                driver_id="implied_terminal_growth",
                label="Implied Terminal Growth",
                unit="percent",
                base_value=float(base_assumptions.get("terminal_growth_pct") or 0.025),
                lower=-0.02,
                upper=min(float(base_assumptions.get("wacc_pct") or 0.10) - 0.005, 0.06),
                target_enterprise_value=target_enterprise_value,
                actuals=actuals,
                projection_years=projection_years,
                base_assumptions=base_assumptions,
                base_overrides=base_overrides,
                market_context=market_context,
                mutator=lambda assumptions, value: assumptions.update({"terminal_growth_pct": value}),
            ),
            self._solve_reverse_driver(
                driver_id="implied_fcf_cagr",
                label="Implied FCF CAGR",
                unit="percent",
                base_value=_projected_cagr(
                    _compute_dcf_projection(
                        actuals=actuals,
                        projection_years=projection_years,
                        assumptions=base_assumptions,
                        overrides=base_overrides,
                        market_context=market_context,
                    )["projection_values"].get("free_cash_flow", [])
                ),
                lower=-0.20,
                upper=0.35,
                target_enterprise_value=target_enterprise_value,
                actuals=actuals,
                projection_years=projection_years,
                base_assumptions=base_assumptions,
                base_overrides=base_overrides,
                market_context=market_context,
                mutator=lambda assumptions, value: None,
                override_mutator=lambda overrides, value: overrides.update({"free_cash_flow": _fcf_growth_series(actuals, value, len(projection_years))}),
            ),
        ]
        sensitivity = (
            self._build_reverse_sensitivity_matrix(
                target_enterprise_value=target_enterprise_value,
                actuals=actuals,
                projection_years=projection_years,
                base_assumptions=base_assumptions,
                base_overrides=base_overrides,
                market_context=market_context,
            )
            if include_sensitivity
            else None
        )
        return FundamentalsReverseValuationResult(
            company=sec_data.company,
            current_price=market_context.get("current_price"),
            shares_outstanding=market_context.get("shares"),
            net_debt=market_context.get("net_debt"),
            target_equity_value=target_equity_value,
            target_enterprise_value=target_enterprise_value,
            base_case_summary=base_summary,
            scenario_gap_metrics=self._reverse_gap_metrics(base_summary, market_context),
            drivers=drivers,
            sensitivity_matrix=sensitivity,
            warnings=_dedupe_warnings(warnings, *[driver.warnings for driver in drivers]),
            source_provider="gamma",
            retrieved_at=datetime.now(timezone.utc),
            origin="fundamentals.reverse_valuation",
            transformation_note="Gamma uses the current price, latest shares, net debt, normalized annual statements, and the Base DCF mechanics to solve bounded market-implied expectation drivers.",
        )

    def _solve_reverse_driver(
        self,
        *,
        driver_id: str,
        label: str,
        unit: str,
        base_value: float | None,
        lower: float,
        upper: float,
        target_enterprise_value: float,
        actuals: dict[str, list[float | None] | list[str]],
        projection_years: list[int],
        base_assumptions: dict[str, Any],
        base_overrides: dict[str, list[float | None]],
        market_context: dict[str, Any],
        mutator: Any,
        override_mutator: Any | None = None,
    ) -> FundamentalsReverseValuationDriverRecord:
        def enterprise_value_for(value: float) -> float | None:
            assumptions = deepcopy(base_assumptions)
            overrides = deepcopy(base_overrides)
            mutator(assumptions, value)
            if override_mutator is not None:
                override_mutator(overrides, value)
            computed = _compute_dcf_projection(
                actuals=actuals,
                projection_years=projection_years,
                assumptions=assumptions,
                overrides=overrides,
                market_context=market_context,
            )
            return computed["summary"]["enterprise_value"]

        solved_value, solved_ev, success, solver_warning = _solve_bounded_expectation(
            enterprise_value_for,
            target_enterprise_value=target_enterprise_value,
            lower=lower,
            upper=upper,
        )
        warnings = [solver_warning] if solver_warning else []
        return FundamentalsReverseValuationDriverRecord(
            driver_id=driver_id,
            label=label,
            implied_value=solved_value,
            display_value=_format_metric(solved_value, unit) if solved_value is not None else "N/A",
            base_value=base_value,
            base_display_value=_format_metric(base_value, unit) if base_value is not None else "N/A",
            gap_to_base=_subtract_nullable(solved_value, base_value),
            gap_display_value=_format_metric(_subtract_nullable(solved_value, base_value), unit) if solved_value is not None and base_value is not None else "N/A",
            target_enterprise_value=target_enterprise_value,
            solved_enterprise_value=solved_ev,
            success=success,
            warnings=warnings,
            source_provider="gamma",
            retrieved_at=datetime.now(timezone.utc),
            origin=f"fundamentals.reverse_valuation.{driver_id}",
            transformation_note="Gamma solves this implied expectation with a bounded bisection over the Base DCF mechanics while holding other assumptions constant.",
        )

    def _build_reverse_sensitivity_matrix(
        self,
        *,
        target_enterprise_value: float,
        actuals: dict[str, list[float | None] | list[str]],
        projection_years: list[int],
        base_assumptions: dict[str, Any],
        base_overrides: dict[str, list[float | None]],
        market_context: dict[str, Any],
    ) -> FundamentalsReverseValuationSensitivityMatrix:
        base_wacc = float(base_assumptions.get("wacc_pct") or 0.10)
        base_terminal = float(base_assumptions.get("terminal_growth_pct") or 0.025)
        wacc_values = [round(max(base_wacc + offset, 0.005), 4) for offset in (-0.02, -0.01, 0.0, 0.01, 0.02)]
        terminal_values = [round(base_terminal + offset, 4) for offset in (-0.01, -0.005, 0.0, 0.005, 0.01)]
        rows: list[list[FundamentalsReverseValuationSensitivityCell]] = []
        for terminal_growth in terminal_values:
            row: list[FundamentalsReverseValuationSensitivityCell] = []
            for wacc in wacc_values:
                assumptions = deepcopy(base_assumptions)
                assumptions["wacc_pct"] = wacc
                assumptions["terminal_growth_pct"] = terminal_growth
                revenue_driver = self._solve_reverse_driver(
                    driver_id="implied_revenue_cagr",
                    label="Implied Revenue CAGR",
                    unit="percent",
                    base_value=_average_assumption(assumptions.get("revenue_growth_pct")),
                    lower=-0.20,
                    upper=0.40,
                    target_enterprise_value=target_enterprise_value,
                    actuals=actuals,
                    projection_years=projection_years,
                    base_assumptions=assumptions,
                    base_overrides=base_overrides,
                    market_context=market_context,
                    mutator=lambda next_assumptions, value: next_assumptions.update({"revenue_growth_pct": [value for _ in projection_years]}),
                )
                margin_driver = self._solve_reverse_driver(
                    driver_id="implied_terminal_ebit_margin",
                    label="Implied Terminal EBIT Margin",
                    unit="percent",
                    base_value=_last_assumption(assumptions.get("ebit_margin_pct")),
                    lower=0.01,
                    upper=0.65,
                    target_enterprise_value=target_enterprise_value,
                    actuals=actuals,
                    projection_years=projection_years,
                    base_assumptions=assumptions,
                    base_overrides=base_overrides,
                    market_context=market_context,
                    mutator=lambda next_assumptions, value: next_assumptions.update({"ebit_margin_pct": _linear_series(_current_margin(actuals), value, len(projection_years))}),
                )
                fcf_driver = self._solve_reverse_driver(
                    driver_id="implied_fcf_cagr",
                    label="Implied FCF CAGR",
                    unit="percent",
                    base_value=None,
                    lower=-0.20,
                    upper=0.35,
                    target_enterprise_value=target_enterprise_value,
                    actuals=actuals,
                    projection_years=projection_years,
                    base_assumptions=assumptions,
                    base_overrides=base_overrides,
                    market_context=market_context,
                    mutator=lambda next_assumptions, value: None,
                    override_mutator=lambda overrides, value: overrides.update({"free_cash_flow": _fcf_growth_series(actuals, value, len(projection_years))}),
                )
                row.append(
                    FundamentalsReverseValuationSensitivityCell(
                        wacc_pct=wacc,
                        terminal_growth_pct=terminal_growth,
                        implied_revenue_growth_pct=revenue_driver.implied_value,
                        implied_ebit_margin_pct=margin_driver.implied_value,
                        implied_fcf_cagr_pct=fcf_driver.implied_value,
                        source_provider="gamma",
                        retrieved_at=datetime.now(timezone.utc),
                        origin="fundamentals.reverse_valuation.sensitivity",
                        transformation_note="Gamma re-solves implied revenue growth, terminal EBIT margin, and FCF CAGR across a WACC and terminal-growth grid.",
                    )
                )
            rows.append(row)
        return FundamentalsReverseValuationSensitivityMatrix(
            wacc_values=wacc_values,
            terminal_growth_values=terminal_values,
            rows=rows,
            source_provider="gamma",
            retrieved_at=datetime.now(timezone.utc),
            origin="fundamentals.reverse_valuation.sensitivity",
            transformation_note="Gamma shows how market-implied expectations change as WACC and terminal-growth assumptions move around the Base case.",
        )

    def _reverse_gap_metrics(
        self,
        base_summary: FundamentalsDcfValuationSummary | None,
        market_context: dict[str, Any],
    ) -> list[FundamentalsMetricRecord]:
        current_price = market_context.get("current_price")
        base_value = base_summary.implied_value_per_share if base_summary else None
        gap = _subtract_nullable(current_price, base_value)
        gap_pct = _safe_ratio(gap, base_value)
        return [
            _metric(
                "base_case_value_per_share",
                "Base Case Value / Share",
                base_value,
                "price",
                "manual",
                base_summary.retrieved_at if base_summary else datetime.now(timezone.utc),
                "fundamentals.reverse_valuation.base_gap",
                "Gamma uses the active Base DCF scenario as the comparison anchor for market-implied expectations.",
            ),
            _metric(
                "market_price_gap_pct",
                "Market Gap vs Base",
                gap_pct,
                "percent",
                "gamma",
                market_context.get("retrieved_at"),
                "fundamentals.reverse_valuation.base_gap",
                "Gamma compares current price against the Base DCF implied value per share; this is research framing, not a recommendation.",
            ),
        ]

    def _build_snapshot_id(self, created_at: datetime, name: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "-" for char in name.strip())
        slug = "-".join(part for part in slug.split("-") if part)[:32] or "snapshot"
        return f"{created_at.strftime('%Y%m%dT%H%M%SZ')}-{slug}"

    def _snapshot_record_from_payload(self, payload: dict[str, Any]) -> FundamentalsDcfSnapshotRecord:
        created_at = _parse_iso_datetime(payload.get("created_at")) or datetime.now(timezone.utc)
        summaries = [
            _summary_from_payload(summary)
            for summary in payload.get("scenario_summaries", [])
            if isinstance(summary, dict)
        ]
        return FundamentalsDcfSnapshotRecord(
            snapshot_id=str(payload.get("snapshot_id") or ""),
            ticker=str(payload.get("ticker") or ""),
            name=str(payload.get("name") or "DCF snapshot"),
            created_at=created_at,
            active_scenario_id=str(payload.get("active_scenario_id") or "base"),
            projection_years=[int(value) for value in payload.get("projection_years", []) if str(value).strip()],
            scenario_summaries=summaries,
            source_provider=str(payload.get("source_provider") or "manual"),
            retrieved_at=_parse_iso_datetime(payload.get("retrieved_at")),
            origin=str(payload.get("origin") or "fundamentals.dcf.snapshot"),
            transformation_note=str(payload.get("transformation_note") or "Gamma restores a saved DCF model snapshot."),
        )

    def _create_default_dcf_payload(
        self,
        sec_data: SecCompanyData,
        market_context: dict[str, Any],
    ) -> dict[str, Any]:
        actuals = self._dcf_actual_series(sec_data)
        projection_years = _projection_years(sec_data.annual_income_statement)
        base_growth = _bounded(_median([value for value in _series_growth(actuals["revenue"]) if value is not None]) or 0.05, -0.05, 0.20)
        base_ebit_margin = _bounded(_safe_ratio(_last_non_null(actuals["ebit"]), _last_non_null(actuals["revenue"])) or 0.20, 0.02, 0.50)
        pretax = _last_non_null(self._statement_value_map(sec_data.annual_income_statement).get("pretax_income", []))
        base_tax = _bounded(_safe_ratio(_last_non_null(actuals["taxes"]), pretax) or 0.21, 0.10, 0.35)
        base_da = _bounded(_safe_ratio(_last_non_null(actuals["depreciation_and_amortization"]), _last_non_null(actuals["revenue"])) or 0.04, 0.00, 0.20)
        base_capex = _bounded(_safe_ratio(_last_non_null(actuals["capital_expenditures"]), _last_non_null(actuals["revenue"])) or 0.04, 0.00, 0.20)
        base_nwc = _bounded(_median([value for value in actuals["nwc_intensity"] if value is not None]) or 0.02, -0.10, 0.20)
        base_shares = _last_non_null(actuals["shares"]) or market_context.get("shares") or 1.0
        scenario_specs = {
            "bear": {"growth_shift": -0.03, "margin_shift": -0.03, "wacc": 0.11, "terminal": 0.02},
            "base": {"growth_shift": 0.00, "margin_shift": 0.00, "wacc": 0.10, "terminal": 0.025},
            "bull": {"growth_shift": 0.03, "margin_shift": 0.03, "wacc": 0.09, "terminal": 0.03},
        }
        scenarios: dict[str, Any] = {}
        for scenario_id, spec in scenario_specs.items():
            scenarios[scenario_id] = {
                "assumptions": {
                    "revenue_growth_pct": [_bounded(base_growth + spec["growth_shift"], -0.10, 0.30) for _ in projection_years],
                    "ebit_margin_pct": [_bounded(base_ebit_margin + spec["margin_shift"], 0.01, 0.60) for _ in projection_years],
                    "tax_rate_pct": [_bounded(base_tax, 0.10, 0.35) for _ in projection_years],
                    "da_pct_revenue": [_bounded(base_da, 0.0, 0.20) for _ in projection_years],
                    "capex_pct_revenue": [_bounded(base_capex + max(spec["margin_shift"], 0.0) / 2.0, 0.0, 0.25) for _ in projection_years],
                    "nwc_pct_incremental_revenue": [_bounded(base_nwc, -0.10, 0.20) for _ in projection_years],
                    "shares_outstanding": [base_shares for _ in projection_years],
                    "wacc_pct": spec["wacc"],
                    "terminal_growth_pct": spec["terminal"],
                },
                "overrides": {},
            }
        return {
            "ticker": sec_data.company.ticker,
            "active_scenario_id": "base",
            "projection_years": projection_years,
            "scenarios": scenarios,
        }

    def _sanitize_dcf_payload(
        self,
        ticker: str,
        payload: dict[str, Any],
        sec_data: SecCompanyData,
        market_context: dict[str, Any],
    ) -> dict[str, Any]:
        baseline = self._create_default_dcf_payload(sec_data, market_context)
        sanitized = deepcopy(baseline)
        sanitized["active_scenario_id"] = str(payload.get("active_scenario_id") or baseline["active_scenario_id"]).lower()
        sanitized["projection_years"] = _normalized_projection_years(
            sec_data.annual_income_statement,
            payload.get("projection_years"),
        )
        payload_scenarios = payload.get("scenarios") if isinstance(payload, dict) else None
        for scenario_id in _DCF_SCENARIO_LABELS:
            incoming = payload_scenarios.get(scenario_id, {}) if isinstance(payload_scenarios, dict) else {}
            assumptions = incoming.get("assumptions", {}) if isinstance(incoming, dict) else {}
            overrides = incoming.get("overrides", {}) if isinstance(incoming, dict) else {}
            target = sanitized["scenarios"][scenario_id]
            for key, default_value in target["assumptions"].items():
                incoming_value = assumptions.get(key)
                if isinstance(default_value, list):
                    target["assumptions"][key] = _coerce_float_list(incoming_value, len(default_value), default_value)
                else:
                    target["assumptions"][key] = _coerce_float(incoming_value, default_value)
            clean_overrides: dict[str, list[float | None]] = {}
            if isinstance(overrides, dict):
                for line_key, values in overrides.items():
                    if line_key not in {row[0] for row in _DCF_PROJECTION_LINE_ORDER}:
                        continue
                    clean_overrides[line_key] = _coerce_optional_float_list(
                        values,
                        len(sanitized["projection_years"]),
                        [None] * len(sanitized["projection_years"]),
                    )
            target["overrides"] = clean_overrides
        sanitized["ticker"] = ticker
        return sanitized

    def _materialize_dcf_model(
        self,
        sec_data: SecCompanyData,
        market_context: dict[str, Any],
        raw_model: dict[str, Any],
    ) -> FundamentalsDcfModelRecord:
        actuals = self._dcf_actual_series(sec_data)
        actual_row_order = [
            ("revenue", "Revenue", "currency"),
            ("ebit", "EBIT", "currency"),
            ("taxes", "Taxes", "currency"),
            ("depreciation_and_amortization", "D&A", "currency"),
            ("capital_expenditures", "Capex", "currency"),
            ("change_in_nwc", "Change In NWC", "currency"),
            ("free_cash_flow", "Free Cash Flow", "currency"),
        ]
        actual_rows = [
            FundamentalsDcfRowRecord(
                line_key=line_key,
                label=label,
                unit=unit,
                values=list(actuals[line_key]),
                display_values=[_format_dcf_value(value, unit) for value in actuals[line_key]],
                editable=False,
                overridden=[False for _ in actuals[line_key]],
                source_provider="gamma" if line_key in {"change_in_nwc", "free_cash_flow"} else "sec",
                retrieved_at=sec_data.company.retrieved_at,
                origin=f"fundamentals.dcf.actual.{line_key}",
                transformation_note=(
                    "Gamma derives historical free cash flow as operating cash flow minus capital expenditures."
                    if line_key == "free_cash_flow"
                    else "Gamma derives historical change in net working capital from annual balance-sheet movements."
                    if line_key == "change_in_nwc"
                    else None
                ),
            )
            for line_key, label, unit in actual_row_order
        ]
        scenarios: list[FundamentalsDcfScenarioRecord] = []
        projection_years = _normalized_projection_years(
            sec_data.annual_income_statement,
            raw_model.get("projection_years"),
        )
        for scenario_id in _DCF_SCENARIO_LABELS:
            scenario_payload = raw_model.get("scenarios", {}).get(scenario_id, {})
            assumptions = scenario_payload.get("assumptions", {})
            overrides = scenario_payload.get("overrides", {})
            computed = _compute_dcf_projection(
                actuals=actuals,
                projection_years=projection_years,
                assumptions=assumptions,
                overrides=overrides,
                market_context=market_context,
            )
            scenario_sensitivity_cells = self._sweep_scenario_sensitivity_cells(
                assumptions=assumptions,
                overrides=overrides,
                actuals=actuals,
                projection_years=projection_years,
                market_context=market_context,
            )
            scenario_implied_values = [
                cell.implied_value_per_share
                for row in scenario_sensitivity_cells
                for cell in row
                if cell.implied_value_per_share is not None
            ]
            scenario_value_low = min(scenario_implied_values) if scenario_implied_values else None
            scenario_value_high = max(scenario_implied_values) if scenario_implied_values else None
            assumption_rows = [
                FundamentalsDcfRowRecord(
                    line_key=key,
                    label=label,
                    unit=unit,
                    values=list(_ensure_list_length(assumptions.get(key), len(projection_years), default=0.0))
                    if key != "shares_outstanding"
                    else list(_ensure_list_length(assumptions.get(key), len(projection_years), default=market_context.get("shares") or 0.0)),
                    display_values=[
                        _format_dcf_value(value, unit)
                        for value in (
                            list(_ensure_list_length(assumptions.get(key), len(projection_years), default=0.0))
                            if key != "shares_outstanding"
                            else list(_ensure_list_length(assumptions.get(key), len(projection_years), default=market_context.get("shares") or 0.0))
                        )
                    ],
                    editable=True,
                    overridden=[False for _ in projection_years],
                    source_provider="manual",
                    retrieved_at=datetime.now(timezone.utc),
                    origin=f"fundamentals.dcf.assumptions.{key}",
                    transformation_note="Gamma stores scenario assumptions as editable local research inputs.",
                )
                for key, label, unit in _DCF_ASSUMPTION_ORDER
            ]
            projection_rows = [
                FundamentalsDcfRowRecord(
                    line_key=line_key,
                    label=label,
                    unit=unit,
                    values=list(computed["projection_values"].get(line_key, [])),
                    display_values=[_format_dcf_value(value, unit) for value in computed["projection_values"].get(line_key, [])],
                    editable=line_key in {"revenue", "ebit", "taxes", "depreciation_and_amortization", "capital_expenditures", "change_in_nwc"},
                    overridden=list(computed["override_flags"].get(line_key, [])),
                    source_provider="manual" if line_key in overrides else "gamma",
                    retrieved_at=datetime.now(timezone.utc),
                    origin=f"fundamentals.dcf.projection.{line_key}",
                    transformation_note=(
                        "Gamma computes projection lines from scenario assumptions and applies any stored manual cell overrides."
                        if line_key in {"revenue", "ebit", "taxes", "depreciation_and_amortization", "capital_expenditures", "change_in_nwc", "free_cash_flow"}
                        else "Gamma derives discount factors and present values from the selected scenario assumptions."
                    ),
                )
                for line_key, label, unit in _DCF_PROJECTION_LINE_ORDER
            ]
            summary = FundamentalsDcfValuationSummary(
                scenario_id=scenario_id,
                label=_DCF_SCENARIO_LABELS[scenario_id],
                enterprise_value=computed["summary"]["enterprise_value"],
                equity_value=computed["summary"]["equity_value"],
                implied_value_per_share=computed["summary"]["implied_value_per_share"],
                implied_value_low=scenario_value_low,
                implied_value_high=scenario_value_high,
                upside_downside_pct=computed["summary"]["upside_downside_pct"],
                terminal_value=computed["summary"]["terminal_value"],
                discounted_terminal_value=computed["summary"]["discounted_terminal_value"],
                discounted_cash_flow_value=computed["summary"]["discounted_cash_flow_value"],
                current_price=market_context.get("current_price"),
                source_provider="manual",
                retrieved_at=datetime.now(timezone.utc),
                origin="fundamentals.dcf.compute",
                transformation_note="Gamma derives the DCF valuation summary from scenario inputs, manual overrides, current price context, and normalized historical SEC fundamentals.",
            )
            scenarios.append(
                FundamentalsDcfScenarioRecord(
                    scenario_id=scenario_id,
                    label=_DCF_SCENARIO_LABELS[scenario_id],
                    assumptions=assumptions,
                    overrides=overrides,
                    assumption_rows=assumption_rows,
                    projection_rows=projection_rows,
                    summary=summary,
                    source_provider="manual",
                    retrieved_at=datetime.now(timezone.utc),
                    origin="fundamentals.dcf.scenario",
                    transformation_note="Gamma persists Bear, Base, and Bull DCF scenarios in parallel and surfaces the selected scenario as the working projection view.",
                )
            )
        active_scenario_id = str(raw_model.get("active_scenario_id") or "base").lower()
        sensitivity_matrix = self._build_sensitivity_matrix(scenarios, active_scenario_id, actuals, projection_years, market_context)
        warnings = []
        if market_context.get("current_price") is None:
            warnings.append("Current price context is unavailable, so valuation upside/downside may be incomplete.")
        return FundamentalsDcfModelRecord(
            ticker=sec_data.company.ticker,
            company_name=sec_data.company.name,
            active_scenario_id=active_scenario_id if active_scenario_id in _DCF_SCENARIO_LABELS else "base",
            historical_year_labels=list(actuals["labels"]),
            projection_years=projection_years,
            actual_rows=actual_rows,
            scenarios=scenarios,
            sensitivity_matrix=sensitivity_matrix,
            warnings=warnings,
            source_provider="manual",
            retrieved_at=datetime.now(timezone.utc),
            origin="fundamentals.dcf.model",
            transformation_note="Gamma builds the DCF model from normalized annual fundamentals, current market context, and locally persisted scenario inputs.",
        )

    def _sweep_scenario_sensitivity_cells(
        self,
        assumptions: dict[str, Any],
        overrides: dict[str, list[float | None]],
        actuals: dict[str, list[float | None] | list[str]],
        projection_years: list[int],
        market_context: dict[str, Any],
    ) -> list[list[FundamentalsDcfSensitivityCell]]:
        base_wacc = float(assumptions.get("wacc_pct", 0.10))
        base_terminal = float(assumptions.get("terminal_growth_pct", 0.025))
        wacc_values = [round(base_wacc + offset, 4) for offset in (-0.02, -0.01, 0.0, 0.01, 0.02)]
        terminal_values = [round(base_terminal + offset, 4) for offset in (-0.01, -0.005, 0.0, 0.005, 0.01)]
        rows: list[list[FundamentalsDcfSensitivityCell]] = []
        for terminal_growth in terminal_values:
            row: list[FundamentalsDcfSensitivityCell] = []
            for wacc in wacc_values:
                swept_assumptions = deepcopy(assumptions)
                swept_assumptions["wacc_pct"] = wacc
                swept_assumptions["terminal_growth_pct"] = terminal_growth
                computed = _compute_dcf_projection(
                    actuals=actuals,
                    projection_years=projection_years,
                    assumptions=swept_assumptions,
                    overrides=overrides,
                    market_context=market_context,
                )
                row.append(
                    FundamentalsDcfSensitivityCell(
                        wacc_pct=wacc,
                        terminal_growth_pct=terminal_growth,
                        implied_value_per_share=computed["summary"]["implied_value_per_share"],
                        source_provider="manual",
                        retrieved_at=datetime.now(timezone.utc),
                        origin="fundamentals.dcf.sensitivity",
                        transformation_note="Gamma re-runs the selected DCF scenario across WACC and terminal-growth combinations to show valuation sensitivity.",
                    )
                )
            rows.append(row)
        return rows

    def _build_sensitivity_matrix(
        self,
        scenarios: list[FundamentalsDcfScenarioRecord],
        active_scenario_id: str,
        actuals: dict[str, list[float | None] | list[str]],
        projection_years: list[int],
        market_context: dict[str, Any],
    ) -> FundamentalsDcfSensitivityMatrix:
        active = next((scenario for scenario in scenarios if scenario.scenario_id == active_scenario_id), scenarios[1] if len(scenarios) > 1 else scenarios[0])
        base_wacc = float(active.assumptions.get("wacc_pct", 0.10))
        base_terminal = float(active.assumptions.get("terminal_growth_pct", 0.025))
        wacc_values = [round(base_wacc + offset, 4) for offset in (-0.02, -0.01, 0.0, 0.01, 0.02)]
        terminal_values = [round(base_terminal + offset, 4) for offset in (-0.01, -0.005, 0.0, 0.005, 0.01)]
        rows = self._sweep_scenario_sensitivity_cells(
            assumptions=active.assumptions,
            overrides=active.overrides,
            actuals=actuals,
            projection_years=projection_years,
            market_context=market_context,
        )
        return FundamentalsDcfSensitivityMatrix(
            wacc_values=wacc_values,
            terminal_growth_values=terminal_values,
            rows=rows,
            source_provider="manual",
            retrieved_at=datetime.now(timezone.utc),
            origin="fundamentals.dcf.sensitivity",
            transformation_note="Gamma recomputes implied value per share across a WACC versus terminal-growth grid from the active DCF scenario.",
        )

    def _dcf_actual_series(self, sec_data: SecCompanyData) -> dict[str, list[float | None] | list[str]]:
        income = self._statement_value_map(sec_data.annual_income_statement)
        balance = self._statement_value_map(sec_data.annual_balance_sheet)
        cash = self._statement_value_map(sec_data.annual_cash_flow_statement)
        labels = [period.label for period in sec_data.annual_income_statement.periods]
        revenue = income.get("revenue", [])
        ebit = income.get("operating_income", [])
        taxes = income.get("income_tax", [])
        da = cash.get("depreciation_and_amortization", [])
        capex = cash.get("capital_expenditures", [])
        operating_cash_flow = cash.get("operating_cash_flow", [])
        shares = [
            _first_non_null(income_value, balance_value)
            for income_value, balance_value in zip(
                income.get("diluted_shares", []),
                balance.get("shares_outstanding", []),
                strict=False,
            )
        ]
        free_cash_flow = [_subtract_nullable(ocf, cx) for ocf, cx in zip(operating_cash_flow, capex, strict=False)]
        working_capital = [
            _subtract_nullable(_sum_nullable(ar, inv), ap)
            for ar, inv, ap in zip(
                balance.get("accounts_receivable", []),
                balance.get("inventory", []),
                balance.get("accounts_payable", []),
                strict=False,
            )
        ]
        change_in_nwc = [None]
        for previous, current in zip(working_capital, working_capital[1:], strict=False):
            change_in_nwc.append(None if previous is None or current is None else current - previous)
        nwc_intensity = []
        for nwc_change, prior_revenue, current_revenue in zip(
            change_in_nwc,
            revenue,
            revenue[1:],
            strict=False,
        ):
            delta_revenue = None if prior_revenue is None or current_revenue is None else current_revenue - prior_revenue
            nwc_intensity.append(_safe_ratio(nwc_change, delta_revenue))
        return {
            "labels": labels,
            "revenue": revenue,
            "ebit": ebit,
            "taxes": taxes,
            "depreciation_and_amortization": da,
            "capital_expenditures": capex,
            "change_in_nwc": change_in_nwc,
            "free_cash_flow": free_cash_flow,
            "shares": shares,
            "nwc_intensity": nwc_intensity,
        }

    def _statement_value_map(self, view: FundamentalsStatementView) -> dict[str, list[float | None]]:
        period_keys = [period.period_key for period in view.periods]
        values: dict[str, list[float | None]] = {}
        for line in view.lines:
            cell_map = {cell.period_key: cell.value for cell in line.cells}
            values[line.line_key] = [cell_map.get(period_key) for period_key in period_keys]
        return values


def _metric(
    metric_id: str,
    label: str,
    value: float | None,
    unit: str,
    source_provider: str,
    retrieved_at: datetime | None,
    origin: str,
    transformation_note: str | None = None,
) -> FundamentalsMetricRecord:
    return FundamentalsMetricRecord(
        metric_id=metric_id,
        label=label,
        value=value,
        display_value=_format_metric(value, unit),
        unit=unit,
        source_provider=source_provider,
        retrieved_at=retrieved_at,
        origin=origin,
        transformation_note=transformation_note,
    )


def _derived_ratio_line(
    line_key: str,
    label: str,
    values: list[float | None],
    periods: list[Any],
    basis: str,
) -> FundamentalsStatementLine:
    return FundamentalsStatementLine(
        line_key=line_key,
        label=label,
        statement="ratios",
        unit="ratio",
        cells=[
            FundamentalsStatementCell(
                period_key=period.period_key,
                value=value,
                display_value=_format_metric(value, "percent" if "growth" in line_key or "margin" in line_key or line_key in {"roe", "roic", "cash_conversion"} else "ratio"),
                source_provider="gamma",
                retrieved_at=datetime.now(timezone.utc),
                origin=f"fundamentals.analytics.{basis}.{line_key}",
                transformation_note="Gamma derives this ratio from normalized SEC statement values rather than displaying a provider-supplied field.",
            )
            for period, value in zip(periods, values, strict=False)
        ],
        source_provider="gamma",
        retrieved_at=datetime.now(timezone.utc),
        origin=f"fundamentals.analytics.{basis}.{line_key}",
        transformation_note="Gamma derives this ratio from normalized SEC statement values rather than displaying a provider-supplied field.",
    )


def _heatmap_metric(value: float | None, unit: str, note: str) -> dict[str, Any]:
    return {"value": value, "display": _format_metric(value, unit), "note": note}


def _format_metric(value: float | None, unit: str) -> str:
    if value is None:
        return "N/A"
    if unit == "currency":
        absolute = abs(value)
        if absolute >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        if absolute >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        return f"${value:,.0f}"
    if unit == "price":
        return f"${value:,.2f}"
    if unit == "shares":
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        return f"{value:,.0f}"
    if unit == "percent":
        return f"{value * 100.0:.1f}%"
    if unit == "ratio":
        return f"{value:.2f}x"
    return f"{value:.2f}"


def _format_dcf_value(value: float | None, unit: str) -> str | None:
    if value is None:
        return None
    if unit == "currency":
        return _format_metric(value, "currency")
    if unit == "shares":
        return _format_metric(value, "shares")
    if unit == "percent":
        return f"{value * 100.0:.1f}%"
    if unit == "ratio":
        return f"{value:.2f}"
    return f"{value:.2f}"


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _sum_nullable(*values: float | None) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) if clean else None


def _subtract_nullable(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _multiply_nullable(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left * right


def _last_non_null(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _first_non_null(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _series_sum(left: list[float | None], right: list[float | None]) -> list[float | None]:
    return [_sum_nullable(a, b) for a, b in zip(left, right, strict=False)]


def _series_growth(values: list[float | None]) -> list[float | None]:
    growth: list[float | None] = [None]
    for previous, current in zip(values, values[1:], strict=False):
        if previous is None or current is None or previous == 0:
            growth.append(None)
        else:
            growth.append((current / previous) - 1.0)
    return growth


def _series_average(values: list[float | None]) -> list[float | None]:
    averages: list[float | None] = [values[0] if values else None]
    for previous, current in zip(values, values[1:], strict=False):
        averages.append(_safe_ratio(_sum_nullable(previous, current), 2.0))
    return averages


def _series_return_metric(
    earnings: list[float | None],
    capital: list[float | None],
) -> list[float | None]:
    average_capital = _series_average(capital)
    return [_safe_ratio(value, base) for value, base in zip(earnings, average_capital, strict=False)]


def _series_roic(
    ebit: list[float | None],
    taxes: list[float | None],
    debt: list[float | None],
    equity: list[float | None],
    cash_values: list[float | None],
) -> list[float | None]:
    invested_capital = [
        _subtract_nullable(_sum_nullable(debt_value, equity_value), cash_value)
        for debt_value, equity_value, cash_value in zip(debt, equity, cash_values, strict=False)
    ]
    average_invested = _series_average(invested_capital)
    nopat = []
    for ebit_value, tax_value in zip(ebit, taxes, strict=False):
        if ebit_value is None:
            nopat.append(None)
            continue
        tax_rate = _safe_ratio(tax_value, ebit_value)
        nopat.append(ebit_value * (1.0 - (tax_rate or 0.21)))
    return [_safe_ratio(value, base) for value, base in zip(nopat, average_invested, strict=False)]


def _projection_years(view: FundamentalsStatementView) -> list[int]:
    latest_period = view.periods[-1].end_date if view.periods else datetime.now(timezone.utc)
    start_year = latest_period.year + 1 if latest_period is not None else datetime.now(timezone.utc).year + 1
    return [start_year + offset for offset in range(5)]


def _normalized_projection_years(
    view: FundamentalsStatementView,
    projection_years: Any,
) -> list[int]:
    baseline = _projection_years(view)
    if not isinstance(projection_years, list) or not projection_years:
        return baseline
    try:
        horizon = max(len([int(value) for value in projection_years]), 1)
    except (TypeError, ValueError):
        return baseline
    return [baseline[0] + offset for offset in range(horizon)]


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _average_assumption(value: Any) -> float | None:
    if isinstance(value, list):
        numeric = [float(item) for item in value if isinstance(item, (int, float))]
        return sum(numeric) / len(numeric) if numeric else None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _last_assumption(value: Any) -> float | None:
    if isinstance(value, list):
        for item in reversed(value):
            if isinstance(item, (int, float)):
                return float(item)
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _linear_series(start: float | None, end: float, length: int) -> list[float]:
    if length <= 0:
        return []
    start_value = start if start is not None else end
    if length == 1:
        return [float(end)]
    return [
        float(start_value + ((end - start_value) * ((index + 1) / length)))
        for index in range(length)
    ]


def _current_margin(actuals: dict[str, list[float | None] | list[str]]) -> float | None:
    return _safe_ratio(
        _last_non_null(actuals.get("ebit", [])),
        _last_non_null(actuals.get("revenue", [])),
    )


def _projected_cagr(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None and value > 0]
    if len(clean) < 2 or clean[0] == 0:
        return None
    return (clean[-1] / clean[0]) ** (1.0 / (len(clean) - 1)) - 1.0


def _fcf_growth_series(
    actuals: dict[str, list[float | None] | list[str]],
    growth_rate: float,
    length: int,
) -> list[float | None]:
    last_fcf = _last_non_null(actuals.get("free_cash_flow", []))
    if last_fcf is None:
        return [None for _ in range(length)]
    return [last_fcf * ((1.0 + growth_rate) ** (index + 1)) for index in range(length)]


def _solve_bounded_expectation(
    value_fn: Any,
    *,
    target_enterprise_value: float,
    lower: float,
    upper: float,
) -> tuple[float | None, float | None, bool, str | None]:
    if upper <= lower:
        return None, None, False, "Reverse-valuation bounds are invalid for this driver."
    lower_ev = value_fn(lower)
    upper_ev = value_fn(upper)
    if lower_ev is None or upper_ev is None:
        return None, None, False, "Reverse-valuation solver could not compute both endpoint values."
    lower_gap = lower_ev - target_enterprise_value
    upper_gap = upper_ev - target_enterprise_value
    increasing = upper_gap >= lower_gap
    if lower_gap == 0:
        return lower, lower_ev, True, None
    if upper_gap == 0:
        return upper, upper_ev, True, None
    if (lower_gap < 0 and upper_gap < 0) or (lower_gap > 0 and upper_gap > 0):
        if abs(lower_gap) <= abs(upper_gap):
            closest_value, closest_ev = lower, lower_ev
        else:
            closest_value, closest_ev = upper, upper_ev
        return (
            closest_value,
            closest_ev,
            False,
            "Current price is outside the bounded reverse-valuation range; Gamma reports the closest bounded estimate.",
        )
    low = lower
    high = upper
    best_value = lower
    best_ev = lower_ev
    for _ in range(64):
        mid = (low + high) / 2.0
        mid_ev = value_fn(mid)
        if mid_ev is None:
            break
        best_value = mid
        best_ev = mid_ev
        mid_gap = mid_ev - target_enterprise_value
        if abs(mid_gap) <= max(abs(target_enterprise_value) * 0.00001, 1.0):
            return mid, mid_ev, True, None
        if increasing:
            if mid_gap < 0:
                low = mid
            else:
                high = mid
        else:
            if mid_gap > 0:
                low = mid
            else:
                high = mid
    return best_value, best_ev, True, None


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _summary_to_payload(summary: FundamentalsDcfValuationSummary) -> dict[str, Any]:
    payload = dict(summary.__dict__)
    for key in ("retrieved_at",):
        value = payload.get(key)
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
    return payload


def _summary_from_payload(payload: dict[str, Any]) -> FundamentalsDcfValuationSummary:
    return FundamentalsDcfValuationSummary(
        scenario_id=str(payload.get("scenario_id") or ""),
        label=str(payload.get("label") or payload.get("scenario_id") or ""),
        enterprise_value=_optional_float(payload.get("enterprise_value")),
        equity_value=_optional_float(payload.get("equity_value")),
        implied_value_per_share=_optional_float(payload.get("implied_value_per_share")),
        implied_value_low=_optional_float(payload.get("implied_value_low")),
        implied_value_high=_optional_float(payload.get("implied_value_high")),
        upside_downside_pct=_optional_float(payload.get("upside_downside_pct")),
        terminal_value=_optional_float(payload.get("terminal_value")),
        discounted_terminal_value=_optional_float(payload.get("discounted_terminal_value")),
        discounted_cash_flow_value=_optional_float(payload.get("discounted_cash_flow_value")),
        current_price=_optional_float(payload.get("current_price")),
        source_provider=str(payload.get("source_provider") or "manual"),
        retrieved_at=_parse_iso_datetime(payload.get("retrieved_at")),
        origin=str(payload.get("origin") or "fundamentals.dcf.snapshot"),
        transformation_note=payload.get("transformation_note"),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _dedupe_warnings(*groups: list[str] | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for warning in group or []:
            text = str(warning or "").strip()
            if text and text not in seen:
                seen.add(text)
                ordered.append(text)
    return ordered


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_float_list(value: Any, length: int, default: list[float]) -> list[float]:
    if not isinstance(value, list):
        return list(default)
    items: list[float] = []
    for index in range(length):
        try:
            items.append(float(value[index]))
        except (IndexError, TypeError, ValueError):
            items.append(float(default[index]))
    return items


def _coerce_optional_float_list(value: Any, length: int, default: list[float | None]) -> list[float | None]:
    if not isinstance(value, list):
        return list(default)
    items: list[float | None] = []
    for index in range(length):
        try:
            raw = value[index]
        except IndexError:
            items.append(default[index])
            continue
        if raw in {"", None}:
            items.append(None)
            continue
        try:
            items.append(float(raw))
        except (TypeError, ValueError):
            items.append(default[index])
    return items


def _ensure_list_length(value: Any, length: int, default: float) -> list[float]:
    if not isinstance(value, list):
        return [float(default) for _ in range(length)]
    items: list[float] = []
    for index in range(length):
        try:
            items.append(float(value[index]))
        except (IndexError, TypeError, ValueError):
            items.append(float(default))
    return items


def _compute_dcf_projection(
    *,
    actuals: dict[str, list[float | None] | list[str]],
    projection_years: list[int],
    assumptions: dict[str, Any],
    overrides: dict[str, list[float | None]],
    market_context: dict[str, Any],
) -> dict[str, Any]:
    last_revenue = _last_non_null(actuals["revenue"]) or 0.0
    last_shares = _last_non_null(actuals["shares"]) or market_context.get("shares") or 1.0
    revenue_growth = _ensure_list_length(assumptions.get("revenue_growth_pct"), len(projection_years), 0.05)
    ebit_margin = _ensure_list_length(assumptions.get("ebit_margin_pct"), len(projection_years), 0.20)
    tax_rate = _ensure_list_length(assumptions.get("tax_rate_pct"), len(projection_years), 0.21)
    da_pct = _ensure_list_length(assumptions.get("da_pct_revenue"), len(projection_years), 0.04)
    capex_pct = _ensure_list_length(assumptions.get("capex_pct_revenue"), len(projection_years), 0.04)
    nwc_pct = _ensure_list_length(assumptions.get("nwc_pct_incremental_revenue"), len(projection_years), 0.02)
    shares_outstanding = _ensure_list_length(assumptions.get("shares_outstanding"), len(projection_years), last_shares)
    wacc = float(assumptions.get("wacc_pct") or 0.10)
    terminal_growth = float(assumptions.get("terminal_growth_pct") or 0.025)
    projection_values: dict[str, list[float | None]] = {row[0]: [] for row in _DCF_PROJECTION_LINE_ORDER}
    override_flags: dict[str, list[bool]] = {row[0]: [] for row in _DCF_PROJECTION_LINE_ORDER}
    previous_revenue = last_revenue
    for index, _year in enumerate(projection_years):
        computed_revenue = previous_revenue * (1.0 + revenue_growth[index])
        revenue = _override_or_value(overrides, "revenue", index, computed_revenue, override_flags)
        computed_ebit = (revenue or 0.0) * ebit_margin[index]
        ebit = _override_or_value(overrides, "ebit", index, computed_ebit, override_flags)
        computed_taxes = max(ebit or 0.0, 0.0) * tax_rate[index]
        taxes = _override_or_value(overrides, "taxes", index, computed_taxes, override_flags)
        computed_da = (revenue or 0.0) * da_pct[index]
        da = _override_or_value(overrides, "depreciation_and_amortization", index, computed_da, override_flags)
        computed_capex = (revenue or 0.0) * capex_pct[index]
        capex = _override_or_value(overrides, "capital_expenditures", index, computed_capex, override_flags)
        incremental_revenue = (revenue or 0.0) - previous_revenue
        computed_nwc = incremental_revenue * nwc_pct[index]
        nwc = _override_or_value(overrides, "change_in_nwc", index, computed_nwc, override_flags)
        computed_fcf = None if None in {ebit, taxes, da, capex, nwc} else (ebit - taxes + da - capex - nwc)
        fcf = _override_or_value(overrides, "free_cash_flow", index, computed_fcf, override_flags)
        projection_values["revenue"].append(revenue)
        projection_values["ebit"].append(ebit)
        projection_values["taxes"].append(taxes)
        projection_values["depreciation_and_amortization"].append(da)
        projection_values["capital_expenditures"].append(capex)
        projection_values["change_in_nwc"].append(nwc)
        projection_values["free_cash_flow"].append(fcf)
        discount_factor = 1.0 / ((1.0 + wacc) ** (index + 1))
        projection_values["discount_factor"].append(discount_factor)
        projection_values["present_value_of_fcf"].append(None if fcf is None else fcf * discount_factor)
        override_flags["discount_factor"].append(False)
        override_flags["present_value_of_fcf"].append(False)
        previous_revenue = revenue or previous_revenue
    terminal_fcf = projection_values["free_cash_flow"][-1] if projection_values["free_cash_flow"] else None
    terminal_value = None
    if terminal_fcf is not None and wacc > terminal_growth:
        terminal_value = terminal_fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)
    discounted_terminal_value = (
        terminal_value * projection_values["discount_factor"][-1]
        if terminal_value is not None and projection_values["discount_factor"]
        else None
    )
    discounted_cash_flow_value = sum(value for value in projection_values["present_value_of_fcf"] if value is not None)
    enterprise_value = None
    if discounted_terminal_value is not None:
        enterprise_value = discounted_cash_flow_value + discounted_terminal_value
    equity_value = None if enterprise_value is None else enterprise_value - (market_context.get("net_debt") or 0.0)
    implied_value_per_share = None
    final_shares = shares_outstanding[-1] if shares_outstanding else last_shares
    if equity_value is not None and final_shares not in {None, 0}:
        implied_value_per_share = equity_value / final_shares
    current_price = market_context.get("current_price")
    upside_downside_pct = None
    if implied_value_per_share is not None and current_price not in {None, 0}:
        upside_downside_pct = (implied_value_per_share / current_price) - 1.0
    return {
        "projection_values": projection_values,
        "override_flags": override_flags,
        "summary": {
            "enterprise_value": enterprise_value,
            "equity_value": equity_value,
            "implied_value_per_share": implied_value_per_share,
            "upside_downside_pct": upside_downside_pct,
            "terminal_value": terminal_value,
            "discounted_terminal_value": discounted_terminal_value,
            "discounted_cash_flow_value": discounted_cash_flow_value,
        },
    }


def _override_or_value(
    overrides: dict[str, list[float | None]],
    line_key: str,
    index: int,
    computed_value: float | None,
    override_flags: dict[str, list[bool]],
) -> float | None:
    override_values = overrides.get(line_key, [])
    override_value = override_values[index] if index < len(override_values) else None
    overridden = override_value is not None
    override_flags[line_key].append(overridden)
    return override_value if overridden else computed_value
