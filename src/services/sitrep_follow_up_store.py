from __future__ import annotations

"""Local JSON persistence for SITREP follow-ups.

Follows the SavedResearchStore layout: one JSON file per follow-up under a
data-directory subfolder, guarded by a process lock, loaded best-effort so a
corrupt file degrades to a skipped row instead of failing the panel.
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models.sitrep import (
    SITREP_FOLLOW_UP_STATUSES,
    SitrepFollowUp,
    SitrepFollowUpCreateRequest,
    SitrepFollowUpUpdateRequest,
)
from src.utils.time import now_utc

SITREP_FOLLOW_UP_LIMIT = 48


class SitrepFollowUpStore:
    def __init__(self, base_dir: str | Path = "data/sitrep") -> None:
        self.base_dir = Path(base_dir)
        self.items_dir = self.base_dir / "follow_ups"
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_items(self) -> list[SitrepFollowUp]:
        with self._lock:
            items = [item for path in self.items_dir.glob("*.json") if (item := self._load_path(path)) is not None]
        return sorted(items, key=lambda item: item.saved_at, reverse=True)

    def create_item(self, request: SitrepFollowUpCreateRequest) -> SitrepFollowUp:
        row_id = str(request.row_id or "").strip()
        with self._lock:
            existing = next(
                (item for item in self._load_all_unlocked() if item.row_id == row_id),
                None,
            )
            if existing is not None:
                return existing
            saved_at = request.saved_at or now_utc()
            item = SitrepFollowUp(
                id=uuid4().hex,
                row_id=row_id,
                title=str(request.title or "").strip(),
                source=str(request.source or "").strip(),
                tone=str(request.tone or "neutral").strip() or "neutral",
                detail=str(request.detail or "").strip(),
                meta=str(request.meta or "").strip(),
                note=str(request.note or "").strip(),
                status="open",
                handoff=dict(request.handoff) if request.handoff else None,
                saved_at=saved_at,
                updated_at=saved_at,
            )
            self._write_item(item)
            self._prune_unlocked()
        return item

    def update_item(self, item_id: str, request: SitrepFollowUpUpdateRequest) -> SitrepFollowUp | None:
        safe_id = self._safe_id(item_id)
        if not safe_id:
            return None
        with self._lock:
            existing = self._load_path(self.items_dir / f"{safe_id}.json")
            if existing is None:
                return None
            status = existing.status
            resolved_at = existing.resolved_at
            if request.status is not None:
                requested_status = str(request.status).strip().lower()
                if requested_status not in SITREP_FOLLOW_UP_STATUSES:
                    raise ValueError(
                        f"Follow-up status must be one of {SITREP_FOLLOW_UP_STATUSES}, got {requested_status!r}."
                    )
                status = requested_status
                resolved_at = now_utc() if requested_status == "resolved" else None
            updated = SitrepFollowUp(
                id=existing.id,
                row_id=existing.row_id,
                title=existing.title,
                source=existing.source,
                tone=existing.tone,
                detail=existing.detail,
                meta=existing.meta,
                note=existing.note if request.note is None else str(request.note).strip(),
                status=status,
                handoff=existing.handoff,
                saved_at=existing.saved_at,
                updated_at=now_utc(),
                resolved_at=resolved_at,
            )
            self._write_item(updated)
        return updated

    def delete_item(self, item_id: str) -> bool:
        safe_id = self._safe_id(item_id)
        if not safe_id:
            return False
        path = self.items_dir / f"{safe_id}.json"
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
        return True

    def delete_by_row_id(self, row_id: str) -> bool:
        normalized = str(row_id or "").strip()
        if not normalized:
            return False
        with self._lock:
            match = next((item for item in self._load_all_unlocked() if item.row_id == normalized), None)
            if match is None:
                return False
            path = self.items_dir / f"{self._safe_id(match.id)}.json"
            if path.exists():
                path.unlink()
        return True

    def _load_all_unlocked(self) -> list[SitrepFollowUp]:
        return [item for path in self.items_dir.glob("*.json") if (item := self._load_path(path)) is not None]

    def _prune_unlocked(self) -> None:
        items = sorted(self._load_all_unlocked(), key=lambda item: item.saved_at, reverse=True)
        for stale in items[SITREP_FOLLOW_UP_LIMIT:]:
            path = self.items_dir / f"{self._safe_id(stale.id)}.json"
            if path.exists():
                path.unlink()

    def _load_path(self, path: Path) -> SitrepFollowUp | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            status = str(payload.get("status") or "open").strip().lower()
            if status not in SITREP_FOLLOW_UP_STATUSES:
                status = "open"
            handoff = payload.get("handoff")
            return SitrepFollowUp(
                id=str(payload.get("id") or path.stem),
                row_id=str(payload.get("row_id") or path.stem),
                title=str(payload.get("title") or "Untitled follow-up"),
                source=str(payload.get("source") or ""),
                tone=str(payload.get("tone") or "neutral"),
                detail=str(payload.get("detail") or ""),
                meta=str(payload.get("meta") or ""),
                note=str(payload.get("note") or ""),
                status=status,
                handoff=dict(handoff) if isinstance(handoff, dict) else None,
                saved_at=self._parse_datetime(payload.get("saved_at")) or now_utc(),
                updated_at=self._parse_datetime(payload.get("updated_at")) or now_utc(),
                resolved_at=self._parse_datetime(payload.get("resolved_at")),
            )
        except Exception:
            return None

    def _write_item(self, item: SitrepFollowUp) -> None:
        path = self.items_dir / f"{self._safe_id(item.id)}.json"
        path.write_text(json.dumps(self._to_json(item), indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _to_json(item: SitrepFollowUp) -> dict[str, Any]:
        return {
            "id": item.id,
            "row_id": item.row_id,
            "title": item.title,
            "source": item.source,
            "tone": item.tone,
            "detail": item.detail,
            "meta": item.meta,
            "note": item.note,
            "status": item.status,
            "handoff": item.handoff,
            "saved_at": item.saved_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _safe_id(value: str | None) -> str:
        return "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"_", "-"})
