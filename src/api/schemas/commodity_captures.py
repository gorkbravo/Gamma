from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.api.schemas.commodities import CommodityInstrumentModel, CommodityCurveSnapshotModel, CommodityCoverageMetadataModel
from src.services.commodity_curve_store import validate_capture


class CommodityCapturePayloadModel(BaseModel):
    instrument: CommodityInstrumentModel
    curve: CommodityCurveSnapshotModel
    coverage: CommodityCoverageMetadataModel

    @model_validator(mode="after")
    def validate_observation(self):
        validate_capture(self.model_dump(mode="json"))
        return self


class CommodityCaptureRecordModel(BaseModel):
    version: int
    id: str
    captured_at: datetime
    # Entorno que produjo la captura; mode_inferred marca registros antiguos clasificados por su evidencia.
    mode: str = "live"
    mode_inferred: bool = False
    payload: CommodityCapturePayloadModel
    checksum: str


class CommodityCaptureListModel(BaseModel):
    captures: list[CommodityCaptureRecordModel]
    warnings: list[str]


class CommodityCaptureCompareRequestModel(BaseModel):
    baseline_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    comparison_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class CommodityCalendarSpreadCreateModel(BaseModel):
    capture_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    left_contract_id: str = Field(min_length=1, max_length=160)
    right_contract_id: str = Field(min_length=1, max_length=160)
    label: str = Field(default="", max_length=160)


class CommodityCaptureComparisonModel(BaseModel):
    baseline: CommodityCaptureRecordModel
    comparison: CommodityCaptureRecordModel
    unit: str
    currency: str
    rows: list[dict[str, Any]]
    warnings: list[str]


class CommodityCalendarSpreadRecordModel(BaseModel):
    version: int
    id: str
    captured_at: datetime
    mode: str = "live"
    mode_inferred: bool = False
    payload: dict[str, Any]
    checksum: str


class CommodityRecordDeleteModel(BaseModel):
    id: str
    deleted: bool


class CommodityCalendarSpreadListModel(BaseModel):
    spreads: list[CommodityCalendarSpreadRecordModel]
    warnings: list[str]


class CommodityCalendarSpreadHistoryModel(BaseModel):
    spread: CommodityCalendarSpreadRecordModel
    points: list[dict[str, Any]]
    warnings: list[str]
