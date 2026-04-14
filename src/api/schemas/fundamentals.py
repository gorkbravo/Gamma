from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.fundamentals import (
    FundamentalsCompanyRecord,
    FundamentalsDcfModelRecord,
    FundamentalsDcfRowRecord,
    FundamentalsDcfScenarioRecord,
    FundamentalsDcfSensitivityCell,
    FundamentalsDcfSensitivityMatrix,
    FundamentalsDcfValuationSummary,
    FundamentalsFinancialsResult,
    FundamentalsMetricRecord,
    FundamentalsOverviewResult,
    FundamentalsPeerBasketRecord,
    FundamentalsPeerCandidateRecord,
    FundamentalsPeerHeatmapCell,
    FundamentalsPeerHeatmapMetricRow,
    FundamentalsPeerHeatmapView,
    FundamentalsPeriodRecord,
    FundamentalsPricePoint,
    FundamentalsSearchResult,
    FundamentalsStatementCell,
    FundamentalsStatementLine,
    FundamentalsStatementView,
)


class FundamentalsSearchResultModel(BaseModel):
    ticker: str
    name: str
    cik: str
    exchange: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsSearchResult) -> "FundamentalsSearchResultModel":
        return cls(**row.__dict__)


class FundamentalsSearchResponseModel(BaseModel):
    results: list[FundamentalsSearchResultModel] = Field(default_factory=list)


class FundamentalsMetricModel(BaseModel):
    metric_id: str
    label: str
    value: float | None = None
    display_value: str | None = None
    unit: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsMetricRecord) -> "FundamentalsMetricModel":
        return cls(**row.__dict__)


class FundamentalsPricePointModel(BaseModel):
    timestamp: datetime
    price: float
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsPricePoint) -> "FundamentalsPricePointModel":
        return cls(**row.__dict__)


class FundamentalsFilingModel(BaseModel):
    form: str
    filing_date: datetime
    report_period: datetime | None = None
    acceptance_datetime: datetime | None = None
    accession_number: str | None = None
    primary_document: str | None = None
    is_amendment: bool = False
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row) -> "FundamentalsFilingModel":
        return cls(**row.__dict__)


class FundamentalsCompanyModel(BaseModel):
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
    classification_labels: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsCompanyRecord) -> "FundamentalsCompanyModel":
        return cls(**row.__dict__)


class FundamentalsPeriodModel(BaseModel):
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
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsPeriodRecord) -> "FundamentalsPeriodModel":
        return cls(**row.__dict__)


class FundamentalsStatementCellModel(BaseModel):
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
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsStatementCell) -> "FundamentalsStatementCellModel":
        return cls(**row.__dict__)


class FundamentalsStatementLineModel(BaseModel):
    line_key: str
    label: str
    statement: str
    unit: str
    cells: list[FundamentalsStatementCellModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsStatementLine) -> "FundamentalsStatementLineModel":
        return cls(
            **{
                **row.__dict__,
                "cells": [FundamentalsStatementCellModel.from_domain(item) for item in row.cells],
            }
        )


class FundamentalsStatementViewModel(BaseModel):
    statement: str
    basis: str
    periods: list[FundamentalsPeriodModel] = Field(default_factory=list)
    lines: list[FundamentalsStatementLineModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsStatementView) -> "FundamentalsStatementViewModel":
        return cls(
            **{
                **row.__dict__,
                "periods": [FundamentalsPeriodModel.from_domain(item) for item in row.periods],
                "lines": [FundamentalsStatementLineModel.from_domain(item) for item in row.lines],
            }
        )


class FundamentalsPeerCandidateModel(BaseModel):
    ticker: str
    name: str
    reason: str | None = None
    exchange: str | None = None
    classification_label: str | None = None
    market_cap: float | None = None
    revenue: float | None = None
    selected: bool = False
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsPeerCandidateRecord) -> "FundamentalsPeerCandidateModel":
        return cls(**row.__dict__)


class FundamentalsPeerBasketModel(BaseModel):
    focal_ticker: str
    basket_label: str
    peer_tickers: list[str] = Field(default_factory=list)
    display_order: list[str] = Field(default_factory=list)
    user_edited: bool = False
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsPeerBasketRecord) -> "FundamentalsPeerBasketModel":
        return cls(**row.__dict__)


class FundamentalsPeerHeatmapCellModel(BaseModel):
    ticker: str
    value: float | None = None
    display_value: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsPeerHeatmapCell) -> "FundamentalsPeerHeatmapCellModel":
        return cls(**row.__dict__)


class FundamentalsPeerHeatmapMetricRowModel(BaseModel):
    metric_id: str
    label: str
    family: str
    cells: list[FundamentalsPeerHeatmapCellModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsPeerHeatmapMetricRow) -> "FundamentalsPeerHeatmapMetricRowModel":
        return cls(
            **{
                **row.__dict__,
                "cells": [FundamentalsPeerHeatmapCellModel.from_domain(item) for item in row.cells],
            }
        )


class FundamentalsPeerHeatmapViewModel(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    rows: list[FundamentalsPeerHeatmapMetricRowModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsPeerHeatmapView) -> "FundamentalsPeerHeatmapViewModel":
        return cls(
            **{
                **row.__dict__,
                "rows": [FundamentalsPeerHeatmapMetricRowModel.from_domain(item) for item in row.rows],
            }
        )


class FundamentalsDcfRowModel(BaseModel):
    line_key: str
    label: str
    unit: str
    values: list[float | None] = Field(default_factory=list)
    display_values: list[str | None] = Field(default_factory=list)
    editable: bool = False
    overridden: list[bool] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsDcfRowRecord) -> "FundamentalsDcfRowModel":
        return cls(**row.__dict__)


class FundamentalsDcfValuationSummaryModel(BaseModel):
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
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsDcfValuationSummary) -> "FundamentalsDcfValuationSummaryModel":
        return cls(**row.__dict__)


class FundamentalsDcfSensitivityCellModel(BaseModel):
    wacc_pct: float
    terminal_growth_pct: float
    implied_value_per_share: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsDcfSensitivityCell) -> "FundamentalsDcfSensitivityCellModel":
        return cls(**row.__dict__)


class FundamentalsDcfSensitivityMatrixModel(BaseModel):
    wacc_values: list[float] = Field(default_factory=list)
    terminal_growth_values: list[float] = Field(default_factory=list)
    rows: list[list[FundamentalsDcfSensitivityCellModel]] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsDcfSensitivityMatrix) -> "FundamentalsDcfSensitivityMatrixModel":
        return cls(
            **{
                **row.__dict__,
                "rows": [
                    [FundamentalsDcfSensitivityCellModel.from_domain(cell) for cell in group]
                    for group in row.rows
                ],
            }
        )


class FundamentalsDcfScenarioModel(BaseModel):
    scenario_id: str
    label: str
    assumptions: dict[str, Any] = Field(default_factory=dict)
    overrides: dict[str, list[float | None]] = Field(default_factory=dict)
    assumption_rows: list[FundamentalsDcfRowModel] = Field(default_factory=list)
    projection_rows: list[FundamentalsDcfRowModel] = Field(default_factory=list)
    summary: FundamentalsDcfValuationSummaryModel | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsDcfScenarioRecord) -> "FundamentalsDcfScenarioModel":
        return cls(
            **{
                **row.__dict__,
                "assumption_rows": [FundamentalsDcfRowModel.from_domain(item) for item in row.assumption_rows],
                "projection_rows": [FundamentalsDcfRowModel.from_domain(item) for item in row.projection_rows],
                "summary": FundamentalsDcfValuationSummaryModel.from_domain(row.summary) if row.summary else None,
            }
        )


class FundamentalsDcfModelModel(BaseModel):
    ticker: str
    company_name: str
    active_scenario_id: str
    historical_year_labels: list[str] = Field(default_factory=list)
    projection_years: list[int] = Field(default_factory=list)
    actual_rows: list[FundamentalsDcfRowModel] = Field(default_factory=list)
    scenarios: list[FundamentalsDcfScenarioModel] = Field(default_factory=list)
    sensitivity_matrix: FundamentalsDcfSensitivityMatrixModel | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: FundamentalsDcfModelRecord) -> "FundamentalsDcfModelModel":
        return cls(
            **{
                **row.__dict__,
                "actual_rows": [FundamentalsDcfRowModel.from_domain(item) for item in row.actual_rows],
                "scenarios": [FundamentalsDcfScenarioModel.from_domain(item) for item in row.scenarios],
                "sensitivity_matrix": (
                    FundamentalsDcfSensitivityMatrixModel.from_domain(row.sensitivity_matrix)
                    if row.sensitivity_matrix
                    else None
                ),
            }
        )


class FundamentalsOverviewResponseModel(BaseModel):
    company: FundamentalsCompanyModel
    headline_metrics: list[FundamentalsMetricModel] = Field(default_factory=list)
    price_history: list[FundamentalsPricePointModel] = Field(default_factory=list)
    filings: list[FundamentalsFilingModel] = Field(default_factory=list)
    peer_candidates: list[FundamentalsPeerCandidateModel] = Field(default_factory=list)
    peer_basket: FundamentalsPeerBasketModel | None = None
    peer_heatmap: FundamentalsPeerHeatmapViewModel | None = None
    dcf_summary: list[FundamentalsDcfValuationSummaryModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: FundamentalsOverviewResult) -> "FundamentalsOverviewResponseModel":
        return cls(
            company=FundamentalsCompanyModel.from_domain(row.company),
            headline_metrics=[FundamentalsMetricModel.from_domain(item) for item in row.headline_metrics],
            price_history=[FundamentalsPricePointModel.from_domain(item) for item in row.price_history],
            filings=[FundamentalsFilingModel.from_domain(item) for item in row.filings],
            peer_candidates=[FundamentalsPeerCandidateModel.from_domain(item) for item in row.peer_candidates],
            peer_basket=FundamentalsPeerBasketModel.from_domain(row.peer_basket) if row.peer_basket else None,
            peer_heatmap=FundamentalsPeerHeatmapViewModel.from_domain(row.peer_heatmap) if row.peer_heatmap else None,
            dcf_summary=[FundamentalsDcfValuationSummaryModel.from_domain(item) for item in row.dcf_summary],
            warnings=list(row.warnings),
        )


class FundamentalsFinancialsResponseModel(BaseModel):
    company: FundamentalsCompanyModel
    annual_income_statement: FundamentalsStatementViewModel
    annual_balance_sheet: FundamentalsStatementViewModel
    annual_cash_flow_statement: FundamentalsStatementViewModel
    quarterly_income_statement: FundamentalsStatementViewModel
    quarterly_balance_sheet: FundamentalsStatementViewModel
    quarterly_cash_flow_statement: FundamentalsStatementViewModel
    annual_ratio_view: FundamentalsStatementViewModel
    quarterly_ratio_view: FundamentalsStatementViewModel
    filings: list[FundamentalsFilingModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: FundamentalsFinancialsResult) -> "FundamentalsFinancialsResponseModel":
        return cls(
            company=FundamentalsCompanyModel.from_domain(row.company),
            annual_income_statement=FundamentalsStatementViewModel.from_domain(row.annual_income_statement),
            annual_balance_sheet=FundamentalsStatementViewModel.from_domain(row.annual_balance_sheet),
            annual_cash_flow_statement=FundamentalsStatementViewModel.from_domain(row.annual_cash_flow_statement),
            quarterly_income_statement=FundamentalsStatementViewModel.from_domain(row.quarterly_income_statement),
            quarterly_balance_sheet=FundamentalsStatementViewModel.from_domain(row.quarterly_balance_sheet),
            quarterly_cash_flow_statement=FundamentalsStatementViewModel.from_domain(row.quarterly_cash_flow_statement),
            annual_ratio_view=FundamentalsStatementViewModel.from_domain(row.annual_ratio_view),
            quarterly_ratio_view=FundamentalsStatementViewModel.from_domain(row.quarterly_ratio_view),
            filings=[FundamentalsFilingModel.from_domain(item) for item in row.filings],
            warnings=list(row.warnings),
        )


class FundamentalsDcfScenarioInputModel(BaseModel):
    assumptions: dict[str, Any] = Field(default_factory=dict)
    overrides: dict[str, list[float | None]] = Field(default_factory=dict)


class FundamentalsDcfSaveRequestModel(BaseModel):
    active_scenario_id: str
    projection_years: list[int] = Field(default_factory=list)
    scenarios: dict[str, FundamentalsDcfScenarioInputModel] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "active_scenario_id": self.active_scenario_id,
            "projection_years": list(self.projection_years),
            "scenarios": {
                key: {
                    "assumptions": dict(value.assumptions),
                    "overrides": dict(value.overrides),
                }
                for key, value in self.scenarios.items()
            },
        }


class FundamentalsPeerBasketUpdateRequestModel(BaseModel):
    peer_tickers: list[str] = Field(default_factory=list)
