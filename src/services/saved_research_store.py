from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models.research_lab import SavedResearchCreateRequest, SavedResearchItem
from src.utils.time import now_utc


class SavedResearchStore:
    def __init__(self, base_dir: str | Path = "data/research") -> None:
        self.base_dir = Path(base_dir)
        self.items_dir = self.base_dir / "saved"
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_items(self) -> list[SavedResearchItem]:
        with self._lock:
            items = [item for path in self.items_dir.glob("*.json") if (item := self._load_path(path)) is not None]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def load_item(self, item_id: str) -> SavedResearchItem | None:
        safe_id = self._safe_id(item_id)
        if not safe_id:
            return None
        with self._lock:
            return self._load_path(self.items_dir / f"{safe_id}.json")

    def create_item(self, request: SavedResearchCreateRequest) -> SavedResearchItem:
        created_at = now_utc()
        item = SavedResearchItem(
            id=uuid4().hex,
            schema_version=1,
            object_type=str(request.object_type or "").strip() or "research_object",
            title=str(request.title or "").strip() or "Untitled Research",
            notes=str(request.notes or "").strip(),
            payload=dict(request.payload or {}),
            created_at=created_at,
            updated_at=created_at,
            warnings=list(request.warnings or []),
            source_provider=str(request.source_provider or "gamma_saved_research"),
            retrieved_at=created_at,
            origin=str(request.origin or "research_service.saved_research.create"),
            transformation_note=request.transformation_note,
        )
        with self._lock:
            self._write_item(item)
        return item

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

    def _load_path(self, path: Path) -> SavedResearchItem | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return SavedResearchItem(
                id=str(payload.get("id") or path.stem),
                schema_version=int(payload.get("schema_version") or 1),
                object_type=str(payload.get("object_type") or "research_object"),
                title=str(payload.get("title") or "Untitled Research"),
                notes=str(payload.get("notes") or ""),
                payload=dict(payload.get("payload") or {}),
                created_at=self._parse_datetime(payload.get("created_at")) or now_utc(),
                updated_at=self._parse_datetime(payload.get("updated_at")) or now_utc(),
                warnings=list(payload.get("warnings") or []),
                source_provider=str(payload.get("source_provider") or "gamma_saved_research"),
                retrieved_at=self._parse_datetime(payload.get("retrieved_at")),
                origin=str(payload.get("origin") or "saved_research_store"),
                transformation_note=payload.get("transformation_note"),
            )
        except Exception:
            return None

    def _write_item(self, item: SavedResearchItem) -> None:
        path = self.items_dir / f"{self._safe_id(item.id)}.json"
        path.write_text(json.dumps(self._to_json(item), indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _to_json(item: SavedResearchItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "schema_version": item.schema_version,
            "object_type": item.object_type,
            "title": item.title,
            "notes": item.notes,
            "payload": item.payload,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
            "warnings": list(item.warnings),
            "source_provider": item.source_provider,
            "retrieved_at": item.retrieved_at.isoformat() if item.retrieved_at else None,
            "origin": item.origin,
            "transformation_note": item.transformation_note,
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
