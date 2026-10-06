"""Immutable research captures and exact-contract calendar spreads; no provider access."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from src.models.commodities import CommodityCurveSnapshot, CommodityCurveNode, CommodityFuturesContract


def _timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def validate_capture(payload: dict) -> None:
    instrument, curve = payload["instrument"], payload["curve"]
    if not instrument["instrument_id"] or instrument["instrument_id"] != curve["instrument_id"]:
        raise ValueError("Capture instrument and curve must agree.")
    if not instrument["quote_unit"].strip() or not instrument["currency"].strip():
        raise ValueError("Capture requires explicit quote units and currency.")
    _timestamp(curve["as_of"])
    nodes = curve["nodes"]
    if not 1 <= len(nodes) <= 100:
        raise ValueError("A capture requires 1–100 exact contract nodes.")
    seen = set()
    for node in nodes:
        contract = node["contract"]
        identity = contract["contract_id"]
        if not identity or identity in seen or contract["instrument_id"] != curve["instrument_id"]:
            raise ValueError("Capture contains a duplicate, missing or mismatched contract identity.")
        if not contract["contract_month"] or not contract["symbol"]:
            raise ValueError("Each contract requires its exact symbol and month.")
        seen.add(identity)
        if node["price"] is not None and not math.isfinite(node["price"]):
            raise ValueError("Curve prices must be finite or unavailable.")
    if not any(node["price"] is not None for node in nodes):
        raise ValueError("No priced contracts to capture. Refresh the curve or check provider coverage.")
    json.dumps(payload, allow_nan=False)


def _compatible(left: dict, right: dict) -> bool:
    return all(left[field] == right[field] for field in ("instrument_id", "quote_unit", "currency"))


def _same_contract(left: dict, right: dict) -> bool:
    return all(left.get(field) == right.get(field) for field in
               ("contract_id", "instrument_id", "symbol", "contract_month", "expiry_date"))


def validate_spread(payload: dict):
    left, right = payload["left_contract"], payload["right_contract"]
    if left["contract_id"] == right["contract_id"] or payload["formula"] != "left_price - right_price":
        raise ValueError("Invalid exact calendar-spread definition.")
    for contract in (left, right):
        if contract["instrument_id"] != payload["instrument_id"] or not all(contract[key] for key in ("contract_id", "symbol", "contract_month")):
            raise ValueError("Calendar-spread contract identity mismatch.")
    if not payload["unit"] or not payload["currency"] or not payload["label"]:
        raise ValueError("Calendar spread requires label, unit and currency.")
    if not re.fullmatch(r"[a-f0-9]{32}", payload["source_capture_id"]):
        raise ValueError("Calendar spread requires a source capture.")


class CommodityCurveStore:
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self._lock = RLock()

    @staticmethod
    def checksum(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def _write(self, category: str, payload: dict):
        record = {"version": 1, "id": uuid4().hex, "captured_at": datetime.now(timezone.utc).isoformat(),
                  "payload": payload, "checksum": self.checksum(payload)}
        encoded = json.dumps(record, allow_nan=False).encode()
        if len(encoded) > self.MAX_BYTES:
            raise ValueError("Commodity record exceeds the 2 MB storage limit.")
        with self._lock:
            directory = self.base_dir / category
            directory.mkdir(parents=True, exist_ok=True)
            if sum(1 for _ in directory.glob("*.json")) >= 2000:
                raise ValueError("Commodity storage is full (2,000 records per category).")
            descriptor, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, directory / f"{record['id']}.json")
            finally:
                Path(temporary).unlink(missing_ok=True)
        return record

    def load(self, category: str, identity: str):
        if category not in {"captures", "spreads"} or not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise FileNotFoundError(identity)
        path = self.base_dir / category / f"{identity}.json"
        with self._lock:
            if path.stat().st_size > self.MAX_BYTES:
                raise ValueError("Oversized commodity record.")
            record = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(record, dict) or record.get("version") != 1 or record.get("id") != identity
                or record.get("checksum") != self.checksum(record["payload"])):
            raise ValueError("Invalid commodity record checksum or version.")
        _timestamp(record["captured_at"])
        if category == "captures":
            validate_capture(record["payload"])
        else:
            validate_spread(record["payload"])
        return record

    def records(self, category: str, instrument_id: str | None = None):
        rows, warnings = [], []
        for path in (self.base_dir / category).glob("*.json"):
            try:
                row = self.load(category, path.stem)
                payload = row["payload"]
                selected = payload["instrument"]["instrument_id"] if category == "captures" else payload["instrument_id"]
                if instrument_id is None or selected == instrument_id:
                    rows.append(row)
            except (ValueError, KeyError, TypeError, OSError):
                warnings.append(f"Unreadable commodity {category} record {path.stem}; original file retained.")
        return sorted(rows, key=lambda row: _timestamp(row["captured_at"]), reverse=True), warnings

    def save_capture(self, payload):
        validate_capture(payload)
        return self._write("captures", payload)

    def prior_curves(self, instrument_id: str, as_of: datetime, *, unit: str, currency: str):
        captures, warnings = self.records("captures", instrument_id)
        curves = []
        for record in captures:
            instrument = record["payload"]["instrument"]
            if instrument["quote_unit"] != unit or instrument["currency"] != currency:
                warnings.append("An earlier retained curve has different quote units/currency and was excluded from the overview history.")
                continue
            row = deepcopy(record["payload"]["curve"])
            if _timestamp(row["as_of"]) >= _timestamp(as_of):
                continue
            for key in ("as_of", "previous_as_of", "retrieved_at"):
                row[key] = datetime.fromisoformat(row[key].replace("Z", "+00:00")) if row.get(key) else None
            nodes = []
            for node in row["nodes"]:
                contract = node["contract"]
                for key in ("expiry_date", "retrieved_at"):
                    contract[key] = datetime.fromisoformat(contract[key].replace("Z", "+00:00")) if contract.get(key) else None
                node["retrieved_at"] = datetime.fromisoformat(node["retrieved_at"].replace("Z", "+00:00")) if node.get("retrieved_at") else None
                node["contract"] = CommodityFuturesContract(**contract)
                nodes.append(CommodityCurveNode(**node))
            row["nodes"] = nodes
            curves.append(CommodityCurveSnapshot(**row))
            if len(curves) == 8:
                break
        return curves, warnings

    def compare(self, baseline_id: str, comparison_id: str):
        baseline, comparison = self.load("captures", baseline_id), self.load("captures", comparison_id)
        a, b = baseline["payload"], comparison["payload"]
        if not _compatible(a["instrument"], b["instrument"]):
            raise ValueError("Compare captures of the same instrument, quote unit and currency.")
        left = {node["contract"]["contract_id"]: node for node in a["curve"]["nodes"]}
        right = {node["contract"]["contract_id"]: node for node in b["curve"]["nodes"]}
        rows = []
        warnings = ["Changes compare captured observations, not official settlement changes. Missing contracts are never rolled or substituted."]
        for identity in dict.fromkeys([*left, *right]):
            old, new = left.get(identity), right.get(identity)
            status = "matched"
            if old is None: status = "absent_from_baseline"
            elif new is None: status = "absent_from_comparison"
            elif not _same_contract(old["contract"], new["contract"]): status = "identity_conflict"
            elif old["price"] is None or new["price"] is None: status = "quote_unavailable"
            if status == "matched" and any(old.get(field) != new.get(field) for field in ("quote_field", "delayed", "freshness_label")):
                warnings.append(f"{identity} has different price-field/freshness evidence between captures; inspect both observations before interpreting the change.")
            rows.append({"contract_id": identity, "contract": (old or new)["contract"], "baseline": old,
                         "comparison": new, "change": new["price"] - old["price"] if status == "matched" else None,
                         "status": status})
        return {"baseline": baseline, "comparison": comparison, "unit": a["instrument"]["quote_unit"],
                "currency": a["instrument"]["currency"], "rows": rows,
                "warnings": warnings}

    def save_spread(self, capture_id: str, left_id: str, right_id: str, label: str):
        capture = self.load("captures", capture_id)["payload"]
        nodes = {node["contract"]["contract_id"]: node for node in capture["curve"]["nodes"]}
        if left_id == right_id or left_id not in nodes or right_id not in nodes:
            raise ValueError("Choose two distinct exact contracts from the retained capture.")
        instrument = capture["instrument"]
        return self._write("spreads", {"instrument_id": instrument["instrument_id"], "unit": instrument["quote_unit"],
            "currency": instrument["currency"], "label": label.strip() or f"{nodes[left_id]['contract']['symbol']} − {nodes[right_id]['contract']['symbol']}",
            "left_contract": nodes[left_id]["contract"], "right_contract": nodes[right_id]["contract"], "source_capture_id": capture_id,
            "formula": "left_price - right_price"})

    def spread_history(self, identity: str):
        spread = self.load("spreads", identity)
        definition = spread["payload"]
        captures, warnings = self.records("captures", definition["instrument_id"])
        points = []
        for capture in reversed(captures):
            payload = capture["payload"]
            nodes = {node["contract"]["contract_id"]: node for node in payload["curve"]["nodes"]}
            left, right = nodes.get(definition["left_contract"]["contract_id"]), nodes.get(definition["right_contract"]["contract_id"])
            status = "observed"
            if payload["instrument"]["quote_unit"] != definition["unit"] or payload["instrument"]["currency"] != definition["currency"]:
                status = "incompatible_units"
            elif left is None or right is None: status = "contract_not_in_capture"
            elif not _same_contract(left["contract"], definition["left_contract"]) or not _same_contract(right["contract"], definition["right_contract"]):
                status = "identity_conflict"
            elif any(c.get("expiry_date") and _timestamp(payload["curve"]["as_of"]).date() > _timestamp(c["expiry_date"]).date()
                     for c in (definition["left_contract"], definition["right_contract"])):
                status = "expired_contract"
            elif left["price"] is None or right["price"] is None: status = "quote_unavailable"
            points.append({"capture_id": capture["id"], "captured_at": capture["captured_at"], "as_of": payload["curve"]["as_of"],
                "left": left, "right": right, "value": left["price"] - right["price"] if status == "observed" else None, "status": status})
        return {"spread": spread, "points": points, "warnings": [*warnings,
            "History consists only of retained curve observations. Expired or missing contracts remain gaps; no front-month substitution, interpolation or backfill."]}
