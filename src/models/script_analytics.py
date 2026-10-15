"""Optional on-disk research interchange, independent of Python authoring/runtime."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VERSION = "gamma-script-analytics.v1"
FILENAME = "gamma_analytics.json"
MAX_BYTES = 512 * 1024

# A source example, not an injected helper. Copied into an ordinary immutable
# revision if the author chooses it; it acquires nothing and uses stdlib only.
AUTHORING_EXAMPLE = '''import csv
import json

# Add an external CSV named observations.csv containing date,return_fraction.
with open("observations.csv", newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
points = [{"date": row["date"],
           "value": float(row["return_fraction"]) if row["return_fraction"] else None}
          for row in rows]
common = {"name": "Supplied research", "meaning": "Describe the analytical meaning",
          "methodology": "Describe calculation and timing; no filling",
          "assumptions": ["No transaction costs"], "limitations": ["Supplied-file coverage only"]}
series = {"instrument_id": "research:example", "frequency": "daily", "observations": points}
payload = {"contract_version": "gamma-script-analytics.v1",
           "instruments": [{"instrument_id": "research:example", "namespace": "research",
                            "native_id": "example", "label": "Supplied hypothetical stream"}],
           "results": [
               {**common, **series, "result_id": "returns", "kind": "returns",
                "unit": "fraction", "return_type": "simple", "periods_per_year": 252},
               {**common, "result_id": "count", "kind": "metric", "unit": "count",
                "value": len(points), "as_of": points[-1]["date"], "instrument_id": None},
               {**common, **series, "result_id": "signal", "kind": "signals", "unit": "score",
                "meaning": "Example research score equal to supplied return; not a position"},
               {**common, **series, "result_id": "weight", "kind": "weights", "unit": "fraction_nav",
                "weight_semantics": "signed_nav_exposure", "hypothetical": True,
                "meaning": "Example signed exposure equal to supplied value; not realized performance"}
           ]}
with open("gamma_analytics.json", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, allow_nan=False, indent=2)
print("Optional analytical file written; Gamma validates retained bytes separately.")
'''


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Instrument(Contract):
    instrument_id: str = Field(min_length=1, max_length=160)
    namespace: str = Field(min_length=1, max_length=80)
    native_id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=160)

    @field_validator("instrument_id", "namespace", "native_id")
    @classmethod
    def exact_identity(cls, value):
        if value != value.strip() or not value.strip():
            raise ValueError("Exact instrument identity cannot be blank or require whitespace normalization.")
        return value


class Observation(Contract):
    date: str
    value: float | None

    @field_validator("date")
    @classmethod
    def iso_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use exact YYYY-MM-DD calendar dates.")
        return value


class Result(Contract):
    result_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=160)
    meaning: str = Field(min_length=1, max_length=1000)
    methodology: str = Field(min_length=1, max_length=4000)
    assumptions: list[str] = Field(max_length=32)
    limitations: list[str] = Field(max_length=32)

    @field_validator("name", "meaning", "methodology")
    @classmethod
    def explicit_description(cls, value):
        if not value.strip():
            raise ValueError("Analytical descriptions cannot be blank.")
        return value

    @field_validator("assumptions", "limitations")
    @classmethod
    def bounded_notes(cls, values):
        if any(not value.strip() or len(value) > 1000 for value in values):
            raise ValueError("Notes must contain 1-1000 characters.")
        return values


class Metric(Result):
    kind: Literal["metric"]
    value: float | None
    unit: Literal["fraction", "percent", "ratio", "count", "currency"]
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    as_of: str
    instrument_id: str | None

    @field_validator("as_of")
    @classmethod
    def as_of_date(cls, value):
        return Observation.iso_date(value)

    @model_validator(mode="after")
    def currency_semantics(self):
        if (self.unit == "currency") != (self.currency is not None):
            raise ValueError("Currency metrics require an explicit ISO currency; other units cannot carry currency.")
        if self.unit == "count" and self.value is not None and (self.value < 0 or not self.value.is_integer()):
            raise ValueError("Count metrics require a nonnegative integer value.")
        return self


class Series(Result):
    instrument_id: str
    frequency: Literal["daily", "weekly", "monthly", "irregular"]
    observations: list[Observation] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def ordered(self):
        dates = [point.date for point in self.observations]
        if dates != sorted(set(dates)):
            raise ValueError("Dates must be strictly increasing without duplicates.")
        # A declared frequency is a constraint, never permission to resample.
        gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(dates, dates[1:])]
        if self.frequency == "weekly" and any(gap % 7 for gap in gaps):
            raise ValueError("Weekly observations must use the same weekday.")
        if self.frequency == "monthly" and len({value[:7] for value in dates}) != len(dates):
            raise ValueError("Monthly observations cannot repeat a calendar month.")
        return self


class Returns(Series):
    kind: Literal["returns"]
    unit: Literal["fraction", "percent"]
    return_type: Literal["simple", "log"]
    periods_per_year: float = Field(gt=0, le=366)

    @model_validator(mode="after")
    def simple_floor(self):
        floor = -1 if self.unit == "fraction" else -100
        if self.return_type == "simple" and any(p.value is not None and p.value < floor for p in self.observations):
            raise ValueError("Simple returns cannot be below -100%.")
        return self


class Signals(Series):
    kind: Literal["signals"]
    unit: Literal["score", "probability", "indicator"]

    @model_validator(mode="after")
    def signal_bounds(self):
        values = [p.value for p in self.observations if p.value is not None]
        if self.unit == "probability" and any(not 0 <= v <= 1 for v in values):
            raise ValueError("Probabilities must be fractional values in [0, 1].")
        if self.unit == "indicator" and any(v not in (-1, 0, 1) for v in values):
            raise ValueError("Indicators must be -1, 0 or 1.")
        return self


class Weights(Series):
    """One exact instrument's signed, hypothetical exposure schedule."""
    kind: Literal["weights"]
    unit: Literal["fraction_nav"]
    weight_semantics: Literal["signed_nav_exposure"]
    hypothetical: Literal[True]

    @field_validator("hypothetical", mode="before")
    @classmethod
    def true_boolean(cls, value):
        if value is not True:
            raise ValueError("Weights must explicitly declare hypothetical=true.")
        return value


AnalyticalResult = Annotated[Metric | Returns | Signals | Weights, Field(discriminator="kind")]


class AnalyticalPayload(Contract):
    contract_version: Literal["gamma-script-analytics.v1"]
    instruments: list[Instrument] = Field(max_length=64)
    results: list[AnalyticalResult] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def identities(self):
        ids = [i.instrument_id for i in self.instruments]
        native = [(i.namespace, i.native_id) for i in self.instruments]
        if len(set(ids)) != len(ids) or len(set(native)) != len(native):
            raise ValueError("Instrument identities must be unique and unambiguous.")
        if len({r.result_id for r in self.results}) != len(self.results):
            raise ValueError("Result ids must be unique.")
        for result in self.results:
            if result.instrument_id is not None and result.instrument_id not in ids:
                raise ValueError("Result references an unknown exact instrument identity.")
        return self
