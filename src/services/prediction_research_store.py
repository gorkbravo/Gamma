from __future__ import annotations

"""Local JSON persistence for saved Prediction Markets research.

Follows the SitrepFollowUpStore layout: one JSON file per record under a
data-directory subfolder, guarded by a process lock, loaded best-effort so a
corrupt file degrades to a skipped row instead of failing the panel.

Records carry a schema version. A file written by a newer schema is skipped and
reported rather than reinterpreted, because a watchlist that silently drops a
field is worse than one that says it could not read a row.
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models.prediction_markets import (
    PREDICTION_RESEARCH_SCHEMA_VERSION,
    PredictionComparisonSet,
    PredictionSavedResearch,
    PredictionWatchlistEntry,
)
from src.utils.time import now_utc

PREDICTION_WATCHLIST_LIMIT = 60
PREDICTION_COMPARISON_SET_LIMIT = 24
PREDICTION_COMPARISON_SET_LEG_LIMIT = 6
PREDICTION_TEXT_LIMIT = 400


class PredictionResearchStore:
    def __init__(self, base_dir: str | Path = "data/prediction_markets") -> None:
        self.base_dir = Path(base_dir)
        self.watchlist_dir = self.base_dir / "watchlist"
        self.comparison_dir = self.base_dir / "comparison_sets"
        self.watchlist_dir.mkdir(parents=True, exist_ok=True)
        self.comparison_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── Reads ────────────────────────────────────────────────────────────

    def get_saved_research(self) -> PredictionSavedResearch:
        with self._lock:
            watchlist, watchlist_warnings = self._load_watchlist_unlocked()
            sets, set_warnings = self._load_sets_unlocked()
        return PredictionSavedResearch(
            schema_version=PREDICTION_RESEARCH_SCHEMA_VERSION,
            watchlist=watchlist,
            comparison_sets=sets,
            watchlist_limit=PREDICTION_WATCHLIST_LIMIT,
            comparison_set_limit=PREDICTION_COMPARISON_SET_LIMIT,
            warnings=[*watchlist_warnings, *set_warnings],
        )

    # ── Watchlist ────────────────────────────────────────────────────────

    def add_watchlist_entry(
        self,
        *,
        market_id: str,
        venue: str,
        title: str,
        probability: float | None = None,
        note: str = "",
    ) -> PredictionWatchlistEntry:
        normalized_id = str(market_id or "").strip()
        if not normalized_id:
            raise ValueError("market_id is required.")
        with self._lock:
            existing_rows, _ = self._load_watchlist_unlocked()
            existing = next((row for row in existing_rows if row.market_id == normalized_id), None)
            saved_at = existing.saved_at if existing is not None else now_utc()
            entry = PredictionWatchlistEntry(
                id=existing.id if existing is not None else uuid4().hex,
                market_id=normalized_id,
                venue=str(venue or "").strip(),
                title=_clip(title) or normalized_id,
                probability=_optional_float(probability),
                note=_clip(note),
                saved_at=saved_at,
                updated_at=now_utc(),
            )
            self._write_watchlist_entry(entry)
            self._prune_watchlist_unlocked()
        return entry

    def remove_watchlist_entry(self, market_id: str) -> bool:
        normalized_id = str(market_id or "").strip()
        if not normalized_id:
            return False
        with self._lock:
            rows, _ = self._load_watchlist_unlocked()
            match = next((row for row in rows if row.market_id == normalized_id), None)
            if match is None:
                return False
            path = self.watchlist_dir / f"{_safe_id(match.id)}.json"
            if path.exists():
                path.unlink()
        return True

    # ── Comparison sets ──────────────────────────────────────────────────

    def save_comparison_set(
        self,
        *,
        name: str,
        market_ids: list[str],
        set_id: str | None = None,
        range_key: str = "max",
        resolution_minutes: int | None = None,
        note: str = "",
    ) -> PredictionComparisonSet:
        normalized_name = _clip(name)
        if not normalized_name:
            raise ValueError("A comparison set needs a name.")
        legs = _unique_ids(market_ids)[:PREDICTION_COMPARISON_SET_LEG_LIMIT]
        if not legs:
            raise ValueError("A comparison set needs at least one contract.")
        with self._lock:
            existing_rows, _ = self._load_sets_unlocked()
            existing = None
            if set_id:
                existing = next((row for row in existing_rows if row.id == set_id), None)
            if existing is None:
                # Saving under an existing name replaces it, so a recurring
                # comparison does not accumulate near-duplicates.
                existing = next(
                    (row for row in existing_rows if row.name.lower() == normalized_name.lower()),
                    None,
                )
            if existing is None and len(existing_rows) >= PREDICTION_COMPARISON_SET_LIMIT:
                raise ValueError(
                    f"Saved comparison sets are capped at {PREDICTION_COMPARISON_SET_LIMIT}; delete one first."
                )
            record = PredictionComparisonSet(
                id=existing.id if existing is not None else uuid4().hex,
                name=normalized_name,
                market_ids=legs,
                range_key=str(range_key or "max").strip() or "max",
                resolution_minutes=_optional_int(resolution_minutes),
                note=_clip(note),
                saved_at=existing.saved_at if existing is not None else now_utc(),
                updated_at=now_utc(),
            )
            self._write_comparison_set(record)
        return record

    def delete_comparison_set(self, set_id: str) -> bool:
        safe = _safe_id(set_id)
        if not safe:
            return False
        path = self.comparison_dir / f"{safe}.json"
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
        return True

    # ── Migration ────────────────────────────────────────────────────────

    def import_legacy_records(
        self,
        *,
        watchlist: list[dict[str, Any]] | None = None,
        comparison_basket: list[str] | None = None,
        basket_name: str = "Imported basket",
    ) -> PredictionSavedResearch:
        """One-time import of browser-local records.

        Import is additive and idempotent per market: re-running it after a
        second browser has already synced does not duplicate rows.
        """
        for row in watchlist or []:
            market_id = str(row.get("market_id") or "").strip()
            if not market_id:
                continue
            try:
                self.add_watchlist_entry(
                    market_id=market_id,
                    venue=str(row.get("venue") or "").strip(),
                    title=str(row.get("title") or market_id),
                    probability=_optional_float(row.get("probability")),
                )
            except ValueError:
                continue
        legs = _unique_ids(comparison_basket or [])
        if legs:
            try:
                self.save_comparison_set(name=basket_name, market_ids=legs)
            except ValueError:
                pass
        return self.get_saved_research()

    # ── Internals ────────────────────────────────────────────────────────

    def _load_watchlist_unlocked(self) -> tuple[list[PredictionWatchlistEntry], list[str]]:
        rows: list[PredictionWatchlistEntry] = []
        warnings: list[str] = []
        for path in self.watchlist_dir.glob("*.json"):
            payload = _read_json(path)
            if payload is None:
                warnings.append(f"Skipped an unreadable watchlist record: {path.name}.")
                continue
            if not _schema_supported(payload):
                warnings.append(
                    f"Skipped watchlist record {path.name}: it was written by schema version "
                    f"{payload.get('schema_version')}, newer than {PREDICTION_RESEARCH_SCHEMA_VERSION}."
                )
                continue
            market_id = str(payload.get("market_id") or "").strip()
            if not market_id:
                continue
            rows.append(
                PredictionWatchlistEntry(
                    id=str(payload.get("id") or path.stem),
                    market_id=market_id,
                    venue=str(payload.get("venue") or ""),
                    title=str(payload.get("title") or market_id),
                    probability=_optional_float(payload.get("probability")),
                    note=str(payload.get("note") or ""),
                    saved_at=_parse_datetime(payload.get("saved_at")),
                    updated_at=_parse_datetime(payload.get("updated_at")),
                )
            )
        rows.sort(key=lambda row: row.saved_at or datetime.min, reverse=True)
        return rows, warnings

    def _load_sets_unlocked(self) -> tuple[list[PredictionComparisonSet], list[str]]:
        rows: list[PredictionComparisonSet] = []
        warnings: list[str] = []
        for path in self.comparison_dir.glob("*.json"):
            payload = _read_json(path)
            if payload is None:
                warnings.append(f"Skipped an unreadable comparison set: {path.name}.")
                continue
            if not _schema_supported(payload):
                warnings.append(
                    f"Skipped comparison set {path.name}: it was written by schema version "
                    f"{payload.get('schema_version')}, newer than {PREDICTION_RESEARCH_SCHEMA_VERSION}."
                )
                continue
            legs = _unique_ids(payload.get("market_ids") or [])[:PREDICTION_COMPARISON_SET_LEG_LIMIT]
            if not legs:
                continue
            rows.append(
                PredictionComparisonSet(
                    id=str(payload.get("id") or path.stem),
                    name=str(payload.get("name") or "Untitled set"),
                    market_ids=legs,
                    range_key=str(payload.get("range_key") or "max"),
                    resolution_minutes=_optional_int(payload.get("resolution_minutes")),
                    note=str(payload.get("note") or ""),
                    saved_at=_parse_datetime(payload.get("saved_at")),
                    updated_at=_parse_datetime(payload.get("updated_at")),
                )
            )
        rows.sort(key=lambda row: row.updated_at or datetime.min, reverse=True)
        return rows, warnings

    def _prune_watchlist_unlocked(self) -> None:
        rows, _ = self._load_watchlist_unlocked()
        for stale in rows[PREDICTION_WATCHLIST_LIMIT:]:
            path = self.watchlist_dir / f"{_safe_id(stale.id)}.json"
            if path.exists():
                path.unlink()

    def _write_watchlist_entry(self, entry: PredictionWatchlistEntry) -> None:
        path = self.watchlist_dir / f"{_safe_id(entry.id)}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": PREDICTION_RESEARCH_SCHEMA_VERSION,
                    "id": entry.id,
                    "market_id": entry.market_id,
                    "venue": entry.venue,
                    "title": entry.title,
                    "probability": entry.probability,
                    "note": entry.note,
                    "saved_at": entry.saved_at.isoformat() if entry.saved_at else None,
                    "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _write_comparison_set(self, record: PredictionComparisonSet) -> None:
        path = self.comparison_dir / f"{_safe_id(record.id)}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": PREDICTION_RESEARCH_SCHEMA_VERSION,
                    "id": record.id,
                    "name": record.name,
                    "market_ids": list(record.market_ids),
                    "range_key": record.range_key,
                    "resolution_minutes": record.resolution_minutes,
                    "note": record.note,
                    "saved_at": record.saved_at.isoformat() if record.saved_at else None,
                    "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _schema_supported(payload: dict[str, Any]) -> bool:
    try:
        version = int(payload.get("schema_version") or PREDICTION_RESEARCH_SCHEMA_VERSION)
    except (TypeError, ValueError):
        return False
    return version <= PREDICTION_RESEARCH_SCHEMA_VERSION


def _unique_ids(values: Any) -> list[str]:
    ordered: list[str] = []
    for value in values if isinstance(values, list) else []:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def _clip(value: Any) -> str:
    return str(value or "").strip()[:PREDICTION_TEXT_LIMIT]


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _safe_id(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"_", "-"})
