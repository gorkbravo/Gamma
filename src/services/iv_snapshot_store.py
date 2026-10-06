"""Immutable, checksummed Options captures; no provider calls or stream ownership."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


class IVSnapshotStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self._lock = RLock()

    @staticmethod
    def checksum(surface: dict) -> str:
        return hashlib.sha256(json.dumps(surface, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def save(self, surface: dict) -> dict:
        record = {"version": 1, "snapshot_id": uuid4().hex,
                  "captured_at": datetime.now(timezone.utc).isoformat(),
                  "surface": surface, "checksum": self.checksum(surface)}
        encoded = json.dumps(record, allow_nan=False).encode()
        if len(encoded) > 8 * 1024 * 1024:
            raise ValueError("Options capture exceeds the 8 MB storage limit.")
        with self._lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            if sum(1 for _ in self.base_dir.glob("*.json")) >= 1000:
                raise ValueError("Options snapshot storage is full (1,000 captures).")
            descriptor, temporary = tempfile.mkstemp(dir=self.base_dir, suffix=".tmp")
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.base_dir / f"{record['snapshot_id']}.json")
            finally:
                Path(temporary).unlink(missing_ok=True)
        return record

    def load(self, snapshot_id: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}", snapshot_id):
            raise FileNotFoundError(snapshot_id)
        path = self.base_dir / f"{snapshot_id}.json"
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Oversized Options capture.")
        record = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(record, dict) or record.get("version") != 1 or record.get("snapshot_id") != snapshot_id
                or record.get("checksum") != self.checksum(record["surface"])):
            raise ValueError("Invalid Options capture checksum or version.")
        return record

    def records(self) -> tuple[list[dict], list[str]]:
        rows, warnings = [], []
        for path in self.base_dir.glob("*.json"):
            try:
                rows.append(self.load(path.stem))
            except (ValueError, KeyError, TypeError, OSError):
                warnings.append(f"Unreadable Options capture {path.stem}; original file retained.")
        return rows, warnings
