"""Local, bounded store of an idea's intraday IBKR marks (Workstream 12, I3d).

Layout, under the ideas data folder::

    intraday/<idea_id>/<YYYY-MM-DD>.json   one file per idea and UTC session day

Each file holds the rows recorded that day: ``mark`` rows (one IBKR price per
leg, with its data type and quality) and ``status`` rows (Gamma ran but could
not mark: Trader Workstation disconnected, or IBKR did not answer), each
stretch coalesced into one row with ``at`` and ``until``. A stretch with no
row at all is time Gamma was not running. The canonical daily series never
reads these files.

Bounds: at most ``ROWS_PER_SESSION_MAX`` rows per file (a five-minute cadence
writes about 290 a day) and the newest ``SESSIONS_KEPT`` files per idea; older
files are deleted on write. Writes are atomic (temporary file, then replace);
a file that cannot be read is renamed aside, never served.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

INTRADAY_SCHEMA_VERSION = 1
ROWS_PER_SESSION_MAX = 400
SESSIONS_KEPT = 10
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SESSION_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def _safe_id(idea_id: str) -> str:
    text = str(idea_id or "").strip()
    if not _SAFE_ID.match(text):
        raise ValueError(f"Unsafe idea id {idea_id!r}.")
    return text


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


class IdeaIntradayStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self._lock = threading.Lock()

    # -- lectura ---------------------------------------------------------------

    def sessions(self, idea_id: str) -> list[date]:
        """Session days with a file, newest first."""
        folder = self.base_dir / _safe_id(idea_id)
        if not folder.is_dir():
            return []
        days = []
        for path in folder.iterdir():
            if _SESSION_FILE.match(path.name):
                try:
                    days.append(date.fromisoformat(path.stem))
                except ValueError:
                    continue
        return sorted(days, reverse=True)

    def load(self, idea_id: str, session: date) -> dict[str, Any] | None:
        with self._lock:
            return self._load_unlocked(self._path(idea_id, session))

    # -- escritura -------------------------------------------------------------

    def append_mark(
        self,
        idea_id: str,
        at: datetime,
        *,
        run_id: str,
        segment: int,
        cadence_seconds: int,
        legs: Mapping[str, Mapping[str, Any]],
        missing: Mapping[str, str],
    ) -> bool:
        """Add one mark row; ``False`` when the session is full."""
        row = {
            "kind": "mark",
            "at": _iso(at),
            "run": run_id,
            "segment": int(segment),
            "cadence": int(cadence_seconds),
            "legs": {key: dict(value) for key, value in legs.items()},
            "missing": dict(missing),
        }
        return self._append(idea_id, at, row)

    def note_status(
        self, idea_id: str, at: datetime, *, run_id: str, status: str, reason: str, cadence_seconds: int
    ) -> bool:
        """Open or extend a status stretch (``disconnected`` or ``skipped``) for this run."""
        session = at.date()
        with self._lock:
            path = self._path(idea_id, session)
            payload = self._load_unlocked(path) or self._empty(idea_id, session)
            rows = payload["rows"]
            last = rows[-1] if rows else None
            if last and last.get("kind") == "status" and last.get("status") == status and last.get("run") == run_id:
                last["until"] = _iso(at)
                last["reason"] = reason
                self._write_unlocked(path, payload)
                return True
            if len(rows) >= ROWS_PER_SESSION_MAX:
                payload["truncated"] = True
                self._write_unlocked(path, payload)
                return False
            rows.append(
                {
                    "kind": "status",
                    "at": _iso(at),
                    "until": _iso(at),
                    "run": run_id,
                    "status": status,
                    "reason": reason,
                    "cadence": int(cadence_seconds),
                }
            )
            self._write_unlocked(path, payload)
            self._prune_unlocked(idea_id)
            return True

    def _append(self, idea_id: str, at: datetime, row: dict[str, Any]) -> bool:
        session = at.date()
        with self._lock:
            path = self._path(idea_id, session)
            payload = self._load_unlocked(path) or self._empty(idea_id, session)
            if len(payload["rows"]) >= ROWS_PER_SESSION_MAX:
                payload["truncated"] = True
                self._write_unlocked(path, payload)
                return False
            payload["rows"].append(row)
            self._write_unlocked(path, payload)
            self._prune_unlocked(idea_id)
            return True

    # -- internos --------------------------------------------------------------

    def _path(self, idea_id: str, session: date) -> Path:
        return self.base_dir / _safe_id(idea_id) / f"{session.isoformat()}.json"

    @staticmethod
    def _empty(idea_id: str, session: date) -> dict[str, Any]:
        return {
            "schema_version": INTRADAY_SCHEMA_VERSION,
            "idea_id": idea_id,
            "session": session.isoformat(),
            "label": "Hypothetical, not executed",
            "note": "Intraday IBKR marks; never used by the canonical daily series.",
            "truncated": False,
            "rows": [],
        }

    def _load_unlocked(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._set_aside(path, "malformed")
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            self._set_aside(path, "invalid")
            return None
        if int(payload.get("schema_version") or 0) > INTRADAY_SCHEMA_VERSION:
            # Un fichero de una versión más nueva no se toca ni se sirve.
            return None
        payload["rows"] = [row for row in payload["rows"] if isinstance(row, dict) and isinstance(row.get("at"), str)]
        return payload

    def _write_unlocked(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{uuid4().hex[:8]}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, path)

    def _prune_unlocked(self, idea_id: str) -> None:
        folder = self.base_dir / _safe_id(idea_id)
        files = sorted((path for path in folder.iterdir() if _SESSION_FILE.match(path.name)), key=lambda path: path.name)
        for path in files[: max(0, len(files) - SESSIONS_KEPT)]:
            try:
                path.unlink()
            except OSError:
                logger.info("Could not prune intraday session file %s", path, exc_info=True)

    def _set_aside(self, path: Path, reason: str) -> None:
        target = path.with_name(f"{path.name}.{reason}.{uuid4().hex[:8]}.preserved")
        try:
            os.replace(path, target)
            logger.warning("Intraday file %s could not be read; moved aside as %s", path, target.name)
        except OSError:
            logger.warning("Intraday file %s could not be read or moved aside", path)


__all__ = ["INTRADAY_SCHEMA_VERSION", "IdeaIntradayStore", "ROWS_PER_SESSION_MAX", "SESSIONS_KEPT"]
