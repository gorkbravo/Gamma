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

STORE_MODES = ("live", "mock")
# Evidencia de cotización que debe coincidir entre patas para llamar «observed» a un spread.
QUOTE_EVIDENCE_FIELDS = ("quote_field", "delayed", "freshness_label")
_SAMPLE_PROVIDERS = frozenset({"sample_data", "sample", "mock"})


class CommodityRecordInUseError(RuntimeError):
    """El registro es la procedencia citada por otro registro retenido."""


class CommodityRetentionLimitError(RuntimeError):
    """La retención por instrumento está llena y no se podan observaciones en vivo."""


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


def _infer_capture_mode(payload: dict) -> str:
    # Los registros guardados antes de sellar el modo no lo llevan: la evidencia de muestra los clasifica como mock.
    coverage, curve = payload.get("coverage") or {}, payload.get("curve") or {}
    providers = {str(curve.get("source_provider") or "").lower()}
    providers.update(str(node.get("source_provider") or "").lower() for node in curve.get("nodes") or [])
    if str(coverage.get("coverage_status") or "").lower() in {"sample", "mock"} or providers & _SAMPLE_PROVIDERS:
        return "mock"
    return "live"


def _evidence_mismatch(left: dict, right: dict) -> list[str]:
    return [field for field in QUOTE_EVIDENCE_FIELDS if left.get(field) != right.get(field)]


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
    # Retención por instrumento y modo. Las capturas mock (datos de muestra) se podan de la más
    # antigua a la más reciente; las observaciones en vivo nunca se borran solas: se pide borrarlas.
    MAX_CAPTURES_PER_INSTRUMENT = 500
    MAX_SPREADS_PER_INSTRUMENT = 200

    def __init__(self, base_dir: Path, *, mode: str = "live"):
        if mode not in STORE_MODES:
            raise ValueError(f"Unsupported commodity store mode: {mode!r}.")
        self.base_dir = Path(base_dir)
        self.mode = mode
        self._lock = RLock()
        # Índice por categoría: id -> ((mtime_ns, tamaño), entrada o error). Se invalida por fichero.
        self._index: dict[str, dict[str, tuple[tuple[int, int], dict]]] = {}

    @staticmethod
    def checksum(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def _write(self, category: str, payload: dict):
        record = {"version": 1, "id": uuid4().hex, "captured_at": datetime.now(timezone.utc).isoformat(),
                  "mode": self.mode, "payload": payload, "checksum": self.checksum(payload)}
        encoded = json.dumps(record, allow_nan=False).encode()
        if len(encoded) > self.MAX_BYTES:
            raise ValueError("Commodity record exceeds the 2 MB storage limit.")
        with self._lock:
            directory = self.base_dir / category
            directory.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, directory / f"{record['id']}.json")
            finally:
                Path(temporary).unlink(missing_ok=True)
        return {**record, "mode_inferred": False}

    def _read(self, category: str, identity: str):
        """Lee y valida un registro de cualquier modo; load() aplica la separación mock/live."""
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
        if "mode" in record and record["mode"] not in STORE_MODES:
            raise ValueError("Invalid commodity record mode.")
        _timestamp(record["captured_at"])
        if category == "captures":
            validate_capture(record["payload"])
        else:
            validate_spread(record["payload"])
        return record

    def _index_entry(self, category: str, identity: str) -> dict:
        try:
            record = self._read(category, identity)
        except (ValueError, KeyError, TypeError, OSError):
            return {"error": f"Unreadable commodity {category} record {identity}; original file retained."}
        payload = record["payload"]
        entry = {"id": identity, "mode": record.get("mode"), "mode_inferred": "mode" not in record,
                 "checksum": record["checksum"], "captured_at": _timestamp(record["captured_at"])}
        if category == "captures":
            entry.update(instrument_id=payload["instrument"]["instrument_id"], as_of=_timestamp(payload["curve"]["as_of"]),
                         unit=payload["instrument"]["quote_unit"], currency=payload["instrument"]["currency"])
            entry["mode"] = entry["mode"] or _infer_capture_mode(payload)
        else:
            entry.update(instrument_id=payload["instrument_id"], source_capture_id=payload["source_capture_id"])
        return entry

    def _entries(self, category: str):
        """Entradas válidas de ambos modos. Solo se releen los ficheros nuevos o modificados, así que
        cargar el workspace ya no relee ni revalida cada registro retenido."""
        directory = self.base_dir / category
        with self._lock:
            cache = self._index.setdefault(category, {})
            entries, warnings, seen = [], [], set()
            for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
                try:
                    stat = path.stat()
                except OSError:
                    warnings.append(f"Unreadable commodity {category} record {path.stem}; original file retained.")
                    continue
                signature = (stat.st_mtime_ns, stat.st_size)
                seen.add(path.stem)
                cached = cache.get(path.stem)
                if cached is None or cached[0] != signature:
                    cached = (signature, self._index_entry(category, path.stem))
                    cache[path.stem] = cached
                if "error" in cached[1]:
                    warnings.append(cached[1]["error"])
                else:
                    entries.append(cached[1])
            for stale in set(cache) - seen:
                cache.pop(stale, None)
            if category == "spreads":
                # Un spread antiguo sin modo hereda el de su captura de origen (live si ya no existe).
                capture_modes = {entry["id"]: entry["mode"] for entry in self._entries("captures")[0]}
                entries = [entry if entry["mode"] else {**entry, "mode": capture_modes.get(entry["source_capture_id"], "live")}
                           for entry in entries]
            return entries, warnings

    def _mode_entries(self, category: str, instrument_id: str | None = None):
        entries, warnings = self._entries(category)
        return [entry for entry in entries if entry["mode"] == self.mode
                and (instrument_id is None or entry["instrument_id"] == instrument_id)], warnings

    def load(self, category: str, identity: str):
        record = self._read(category, identity)
        if "mode" in record:
            record = {**record, "mode_inferred": False}
        else:
            entry = next((e for e in self._entries(category)[0] if e["id"] == identity), None)
            record = {**record, "mode": entry["mode"] if entry else "live", "mode_inferred": True}
        # Separación mock/live: un registro del otro modo no existe para este runtime.
        if record["mode"] != self.mode:
            raise FileNotFoundError(identity)
        return record

    @staticmethod
    def _observation_order(entry: dict):
        return entry.get("as_of") or entry["captured_at"], entry["captured_at"], entry["id"]

    def records(self, category: str, instrument_id: str | None = None):
        entries, warnings = self._mode_entries(category, instrument_id)
        rows = []
        # Capturas por tiempo de observación (as_of) y, a igualdad, por guardado; spreads por guardado.
        for entry in sorted(entries, key=self._observation_order, reverse=True):
            try:
                rows.append(self.load(category, entry["id"]))
            except (ValueError, KeyError, TypeError, OSError):
                warnings.append(f"Unreadable commodity {category} record {entry['id']}; original file retained.")
        return rows, warnings

    def _enforce_retention(self, category: str, instrument_id: str, entries: list[dict]) -> list[str]:
        limit = self.MAX_CAPTURES_PER_INSTRUMENT if category == "captures" else self.MAX_SPREADS_PER_INSTRUMENT
        if len(entries) < limit:
            return []
        noun = "curve captures" if category == "captures" else "calendar spreads"
        if self.mode != "mock":
            raise CommodityRetentionLimitError(
                f"Gamma retains at most {limit} live {noun} per instrument ({instrument_id}). Delete older records "
                "to save another; retained live observations are never removed automatically.")
        protected = {entry["source_capture_id"] for entry in self._entries("spreads")[0]} if category == "captures" else set()
        candidates = [entry for entry in sorted(entries, key=self._observation_order) if entry["id"] not in protected]
        pruned = []
        for entry in candidates[:len(entries) - limit + 1]:
            (self.base_dir / category / f"{entry['id']}.json").unlink(missing_ok=True)
            self._index.get(category, {}).pop(entry["id"], None)
            pruned.append(entry["id"])
        if len(entries) - len(pruned) >= limit:
            raise CommodityRetentionLimitError(
                f"Every retained mock {noun} for {instrument_id} is cited by a calendar spread; delete a spread first.")
        return pruned

    def save_capture(self, payload):
        validate_capture(payload)
        instrument_id, checksum = payload["instrument"]["instrument_id"], self.checksum(payload)
        with self._lock:
            entries, _ = self._mode_entries("captures", instrument_id)
            # Guardar dos veces la misma observación no crea un segundo punto de historia.
            duplicate = next((entry for entry in entries if entry["checksum"] == checksum), None)
            if duplicate is not None:
                return self.load("captures", duplicate["id"])
            self._enforce_retention("captures", instrument_id, entries)
            return self._write("captures", payload)

    def delete(self, category: str, identity: str):
        with self._lock:
            self.load(category, identity)
            if category == "captures":
                citing = [entry["id"] for entry in self._entries("spreads")[0] if entry["source_capture_id"] == identity]
                if citing:
                    raise CommodityRecordInUseError(
                        f"This capture is the source of {len(citing)} calendar spread(s); delete those spreads first.")
            (self.base_dir / category / f"{identity}.json").unlink()
            self._index.get(category, {}).pop(identity, None)
        return {"id": identity, "deleted": True}

    def prior_curves(self, instrument_id: str, as_of: datetime, *, unit: str, currency: str):
        entries, warnings = self._mode_entries("captures", instrument_id)
        current, selected, seen_as_of, excluded_units = _timestamp(as_of), [], set(), 0
        for entry in sorted(entries, key=self._observation_order, reverse=True):
            if entry["as_of"] >= current or entry["as_of"] in seen_as_of:
                continue
            if entry["unit"] != unit or entry["currency"] != currency:
                excluded_units += 1
                continue
            # Varias capturas con el mismo as_of cuentan como una sola observación: la última guardada.
            seen_as_of.add(entry["as_of"])
            selected.append(entry)
            if len(selected) == 8:
                break
        if excluded_units:
            warnings.append("An earlier retained curve has different quote units/currency and was excluded from the overview history.")
        curves = []
        # Solo se cargan completas las (como mucho) ocho curvas elegidas en el índice.
        for entry in selected:
            try:
                record = self.load("captures", entry["id"])
            except (ValueError, KeyError, TypeError, OSError):
                warnings.append(f"Unreadable commodity captures record {entry['id']}; original file retained.")
                continue
            row = deepcopy(record["payload"]["curve"])
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
            if status == "matched" and _evidence_mismatch(old, new):
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
        payload = {"instrument_id": instrument["instrument_id"], "unit": instrument["quote_unit"],
            "currency": instrument["currency"], "label": label.strip() or f"{nodes[left_id]['contract']['symbol']} − {nodes[right_id]['contract']['symbol']}",
            "left_contract": nodes[left_id]["contract"], "right_contract": nodes[right_id]["contract"], "source_capture_id": capture_id,
            "formula": "left_price - right_price"}
        checksum = self.checksum(payload)
        with self._lock:
            entries, _ = self._mode_entries("spreads", instrument["instrument_id"])
            duplicate = next((entry for entry in entries if entry["checksum"] == checksum), None)
            if duplicate is not None:
                return self.load("spreads", duplicate["id"])
            self._enforce_retention("spreads", instrument["instrument_id"], entries)
            return self._write("spreads", payload)

    @staticmethod
    def _spread_point(definition: dict, capture: dict) -> dict:
        payload = capture["payload"]
        nodes = {node["contract"]["contract_id"]: node for node in payload["curve"]["nodes"]}
        left, right = nodes.get(definition["left_contract"]["contract_id"]), nodes.get(definition["right_contract"]["contract_id"])
        status, mismatch = "observed", []
        if payload["instrument"]["quote_unit"] != definition["unit"] or payload["instrument"]["currency"] != definition["currency"]:
            status = "incompatible_units"
        elif left is None or right is None: status = "contract_not_in_capture"
        elif not _same_contract(left["contract"], definition["left_contract"]) or not _same_contract(right["contract"], definition["right_contract"]):
            status = "identity_conflict"
        elif any(c.get("expiry_date") and _timestamp(payload["curve"]["as_of"]).date() > _timestamp(c["expiry_date"]).date()
                 for c in (definition["left_contract"], definition["right_contract"])):
            status = "expired_contract"
        elif left["price"] is None or right["price"] is None: status = "quote_unavailable"
        elif mismatch := _evidence_mismatch(left, right):
            # Patas con distinto campo de precio, retraso o frescura: se conserva el valor, pero no es «observed».
            status = "mixed_quote_evidence"
        value = left["price"] - right["price"] if status in {"observed", "mixed_quote_evidence"} else None
        return {"capture_id": capture["id"], "captured_at": capture["captured_at"], "as_of": payload["curve"]["as_of"],
                "left": left, "right": right, "value": value, "status": status, "evidence_mismatch": mismatch,
                "superseded_capture_ids": []}

    def spread_history(self, identity: str):
        spread = self.load("spreads", identity)
        definition = spread["payload"]
        captures, warnings = self.records("captures", definition["instrument_id"])
        # Orden por tiempo de observación (as_of); el momento de guardado solo desempata.
        groups: dict[datetime, list[dict]] = {}
        for capture in sorted(captures, key=lambda c: (_timestamp(c["payload"]["curve"]["as_of"]), _timestamp(c["captured_at"]), c["id"])):
            groups.setdefault(_timestamp(capture["payload"]["curve"]["as_of"]), []).append(capture)
        points, mixed = [], 0
        for as_of, group in groups.items():
            *earlier, latest = group
            point = self._spread_point(definition, latest)
            point["superseded_capture_ids"] = [capture["id"] for capture in earlier]
            differing = []
            for capture in earlier:
                other = self._spread_point(definition, capture)
                if (other["value"], other["status"]) != (point["value"], point["status"]):
                    differing.append(capture["id"][:6])
            if differing:
                warnings.append(f"{len(group)} captures share observation time {as_of.isoformat()}; the latest saved "
                                f"({latest['id'][:6]}) is shown and earlier saves ({', '.join(differing)}) report a different spread or status.")
            mixed += point["status"] == "mixed_quote_evidence"
            points.append(point)
        if mixed:
            warnings.append(f"{mixed} point(s) combine legs with different quote field, delay or freshness evidence; "
                            "they are labelled mixed quote evidence, not observed. Inspect both legs before interpreting the spread.")
        return {"spread": spread, "points": points, "warnings": [*warnings,
            "History consists only of retained curve observations ordered by observation time; captures saved with the same observation time count once. "
            "Expired or missing contracts remain gaps; no front-month substitution, interpolation or backfill."]}
