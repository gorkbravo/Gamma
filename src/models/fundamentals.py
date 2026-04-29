from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class FundamentalsSearchResult:
    ticker: str
    name: str
    cik: str
    exchange: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsMetricRecord:
    metric_id: str
    label: str
    value: float | None = None
    display_value: str | None = None
    unit: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPricePoint:
    timestamp: datetime
    price: float
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsFilingRecord:
    form: str
    filing_date: datetime
    report_period: datetime | None = None
    acceptance_datetime: datetime | None = None
    accession_number: str | None = None
    primary_document: str | None = None
    is_amendment: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsCompanyRecord:
    ticker: str
    cik: str
    name: str
    exchange: str | None = None
    sic: str | None = None
    sic_description: str | None = None
    filer_category: str | None = None
    fiscal_year_end: str | None = None
    state_of_incorporation: str | None = None
    phone: str | None = None
    website: str | None = None
    investor_website: str | None = None
    description: str | None = None
    latest_report_period: datetime | None = None
    latest_filing_date: datetime | None = None
    classification_labels: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeriodRecord:
    period_key: str
    label: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    filing_date: datetime | None = None
    form: str | None = None
    accession_number: str | None = None
    is_amendment: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsStatementCell:
    period_key: str
    value: float | None = None
    display_value: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    filing_date: datetime | None = None
    form: str | None = None
    accession_number: str | None = None
    is_amendment: bool = False
    concept_name: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsStatementLine:
    line_key: str
    label: str
    statement: str
    unit: str
    cells: list[FundamentalsStatementCell] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsStatementView:
    statement: str
    basis: str
    periods: list[FundamentalsPeriodRecord] = field(default_factory=list)
    lines: list[FundamentalsStatementLine] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeerCandidateRecord:
    ticker: str
    name: str
    reason: str | None = None
    exchange: str | None = None
    classification_label: str | None = None
    market_cap: float | None = None
    revenue: float | None = None
    selected: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeerBasketRecord:
    focal_ticker: str
    basket_label: str
    peer_tickers: list[str] = field(default_factory=list)
    display_order: list[str] = field(default_factory=list)
    user_edited: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeerHeatmapCell:
    ticker: str
    value: float | None = None
    display_value: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeerHeatmapMetricRow:
    metric_id: str
    label: str
    family: str
    cells: list[FundamentalsPeerHeatmapCell] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeerHeatmapView:
    tickers: list[str] = field(default_factory=list)
    rows: list[FundamentalsPeerHeatmapMetricRow] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeerComparisonRecord:
    ticker: str
    name: str
    selected: bool = False
    candidate_reason: str | None = None
    metrics: list[FundamentalsMetricRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeerDiagnosticsRecord:
    ticker: str
    missing_metric_ids: list[str] = field(default_factory=list)
    warning: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsPeersResult:
    company: FundamentalsCompanyRecord
    peer_basket: FundamentalsPeerBasketRecord
    peer_candidates: list[FundamentalsPeerCandidateRecord] = field(default_factory=list)
    peer_heatmap: FundamentalsPeerHeatmapView | None = None
    comparisons: list[FundamentalsPeerComparisonRecord] = field(default_factory=list)
    diagnostics: list[FundamentalsPeerDiagnosticsRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfRowRecord:
    line_key: str
    label: str
    unit: str
    values: list[float | None] = field(default_factory=list)
    display_values: list[str | None] = field(default_factory=list)
    editable: bool = False
    overridden: list[bool] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfValuationSummary:
    scenario_id: str
    label: str
    enterprise_value: float | None = None
    equity_value: float | None = None
    implied_value_per_share: float | None = None
    implied_value_low: float | None = None
    implied_value_high: float | None = None
    upside_downside_pct: float | None = None
    terminal_value: float | None = None
    discounted_terminal_value: float | None = None
    discounted_cash_flow_value: float | None = None
    current_price: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfBridgeRowRecord:
    row_id: str
    label: str
    value: float | None = None
    display_value: str | None = None
    unit: str | None = None
    note: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfSensitivityCell:
    wacc_pct: float
    terminal_growth_pct: float
    implied_value_per_share: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfSensitivityMatrix:
    wacc_values: list[float] = field(default_factory=list)
    terminal_growth_values: list[float] = field(default_factory=list)
    rows: list[list[FundamentalsDcfSensitivityCell]] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfScenarioRecord:
    scenario_id: str
    label: str
    assumptions: dict[str, list[float] | float] = field(default_factory=dict)
    overrides: dict[str, list[float | None]] = field(default_factory=dict)
    assumption_rows: list[FundamentalsDcfRowRecord] = field(default_factory=list)
    projection_rows: list[FundamentalsDcfRowRecord] = field(default_factory=list)
    cost_of_capital_rows: list[FundamentalsDcfBridgeRowRecord] = field(default_factory=list)
    valuation_bridge_rows: list[FundamentalsDcfBridgeRowRecord] = field(default_factory=list)
    summary: FundamentalsDcfValuationSummary | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfModelRecord:
    ticker: str
    company_name: str
    active_scenario_id: str
    historical_year_labels: list[str] = field(default_factory=list)
    projection_years: list[int] = field(default_factory=list)
    actual_rows: list[FundamentalsDcfRowRecord] = field(default_factory=list)
    scenarios: list[FundamentalsDcfScenarioRecord] = field(default_factory=list)
    sensitivity_matrix: FundamentalsDcfSensitivityMatrix | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsDcfSnapshotRecord:
    snapshot_id: str
    ticker: str
    name: str
    created_at: datetime
    active_scenario_id: str
    projection_years: list[int] = field(default_factory=list)
    scenario_summaries: list[FundamentalsDcfValuationSummary] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsSourceTraceRecord:
    statement: str
    basis: str
    line_key: str
    line_label: str
    period_key: str
    period_label: str | None = None
    normalized_value: float | None = None
    display_value: str | None = None
    unit: str | None = None
    concept_name: str | None = None
    accession_number: str | None = None
    filing_form: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    filing_date: datetime | None = None
    report_period: datetime | None = None
    is_amendment: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsCoverageRecord:
    statement: str
    basis: str
    line_key: str
    line_label: str
    concept_names: list[str] = field(default_factory=list)
    observed_periods: int = 0
    missing_periods: int = 0
    derived_observations: int = 0
    coverage_ratio: float | None = None
    warning: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsRawNormalizedInspectionResult:
    company: FundamentalsCompanyRecord
    traces: list[FundamentalsSourceTraceRecord] = field(default_factory=list)
    coverage: list[FundamentalsCoverageRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsReferenceResult:
    company: FundamentalsCompanyRecord
    filings: list[FundamentalsFilingRecord] = field(default_factory=list)
    inspection: FundamentalsRawNormalizedInspectionResult | None = None
    provider_warnings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsReverseValuationDriverRecord:
    driver_id: str
    label: str
    implied_value: float | None = None
    display_value: str | None = None
    base_value: float | None = None
    base_display_value: str | None = None
    gap_to_base: float | None = None
    gap_display_value: str | None = None
    target_enterprise_value: float | None = None
    solved_enterprise_value: float | None = None
    success: bool = False
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsReverseValuationSensitivityCell:
    wacc_pct: float
    terminal_growth_pct: float
    implied_revenue_growth_pct: float | None = None
    implied_ebit_margin_pct: float | None = None
    implied_fcf_cagr_pct: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsReverseValuationSensitivityMatrix:
    wacc_values: list[float] = field(default_factory=list)
    terminal_growth_values: list[float] = field(default_factory=list)
    rows: list[list[FundamentalsReverseValuationSensitivityCell]] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsReverseValuationResult:
    company: FundamentalsCompanyRecord
    current_price: float | None = None
    shares_outstanding: float | None = None
    net_debt: float | None = None
    target_equity_value: float | None = None
    target_enterprise_value: float | None = None
    base_case_summary: FundamentalsDcfValuationSummary | None = None
    scenario_gap_metrics: list[FundamentalsMetricRecord] = field(default_factory=list)
    drivers: list[FundamentalsReverseValuationDriverRecord] = field(default_factory=list)
    sensitivity_matrix: FundamentalsReverseValuationSensitivityMatrix | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class FundamentalsOverviewResult:
    company: FundamentalsCompanyRecord
    headline_metrics: list[FundamentalsMetricRecord] = field(default_factory=list)
    price_history: list[FundamentalsPricePoint] = field(default_factory=list)
    filings: list[FundamentalsFilingRecord] = field(default_factory=list)
    peer_candidates: list[FundamentalsPeerCandidateRecord] = field(default_factory=list)
    peer_basket: FundamentalsPeerBasketRecord | None = None
    peer_heatmap: FundamentalsPeerHeatmapView | None = None
    dcf_summary: list[FundamentalsDcfValuationSummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FundamentalsFinancialsResult:
    company: FundamentalsCompanyRecord
    annual_income_statement: FundamentalsStatementView
    annual_balance_sheet: FundamentalsStatementView
    annual_cash_flow_statement: FundamentalsStatementView
    quarterly_income_statement: FundamentalsStatementView
    quarterly_balance_sheet: FundamentalsStatementView
    quarterly_cash_flow_statement: FundamentalsStatementView
    annual_ratio_view: FundamentalsStatementView
    quarterly_ratio_view: FundamentalsStatementView
    filings: list[FundamentalsFilingRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
