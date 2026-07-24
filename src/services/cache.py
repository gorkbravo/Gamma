from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd


class CacheService:
    _SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
    _MAX_SAFE_PREFIX_LENGTH = 80

    def __init__(self, base_dir: str | Path = "cache", ttl_hours: int = 24) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._resolved_base_dir = self.base_dir.resolve()
        self.ttl = timedelta(hours=ttl_hours)

    def _resolve_under_base(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(self._resolved_base_dir)
        except ValueError as exc:
            raise ValueError(f"Cache path escapes base directory: {path}") from exc
        return resolved

    @classmethod
    def _safe_filename_for_key(cls, key: str) -> str:
        logical_key = str(key or "cache")
        digest = hashlib.sha256(logical_key.encode("utf-8")).hexdigest()
        prefix = cls._SAFE_FILENAME_RE.sub("_", logical_key.replace("\\", "_").replace("/", "_"))
        while ".." in prefix:
            prefix = prefix.replace("..", "_")
        prefix = re.sub(r"_+", "_", prefix)
        prefix = prefix.strip("._-").lower() or "cache"
        if len(prefix) > cls._MAX_SAFE_PREFIX_LENGTH:
            prefix = prefix[: cls._MAX_SAFE_PREFIX_LENGTH].rstrip("._-") or "cache"
        return f"{prefix}--{digest}"

    def _path_for_key(self, key: str, suffix: str) -> Path:
        return self._resolve_under_base(self.base_dir / f"{self._safe_filename_for_key(key)}{suffix}")

    def _meta_path(self, key: str) -> Path:
        return self._path_for_key(key, ".json")

    def _data_path(self, key: str) -> Path:
        return self._path_for_key(key, ".csv")

    def _value_path(self, key: str) -> Path:
        return self._path_for_key(key, ".value.json")

    def _json_path(self, key: str) -> Path:
        return self._path_for_key(key, ".payload.json")

    def get(self, key: str) -> Optional[pd.Series]:
        data_path = self._data_path(key)
        meta_path = self._meta_path(key)
        return self._read_series_paths(data_path, meta_path)

    def get_series_file(self, data_path: str | Path) -> Optional[pd.Series]:
        resolved_data_path = self._resolve_under_base(Path(data_path))
        return self._read_series_paths(resolved_data_path, resolved_data_path.with_suffix(".json"))

    def _read_series_paths(self, data_path: Path, meta_path: Path) -> Optional[pd.Series]:
        if not data_path.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text())
            ts = datetime.fromisoformat(meta.get("timestamp"))
            if datetime.utcnow() - ts > self.ttl:
                return None
            df = pd.read_csv(data_path, parse_dates=["date"], index_col="date")
            return df["close"]
        except Exception:
            return None

    def set(self, key: str, series: pd.Series) -> None:
        data_path = self._data_path(key)
        meta_path = self._meta_path(key)
        df = series.to_frame(name="close")
        df.index.name = "date"
        df.to_csv(data_path)
        meta = {"timestamp": datetime.utcnow().isoformat()}
        meta_path.write_text(json.dumps(meta))

    def get_frame(self, key: str) -> Optional[pd.DataFrame]:
        data_path = self._data_path(key)
        meta_path = self._meta_path(key)
        if not data_path.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text())
            ts = datetime.fromisoformat(meta.get("timestamp"))
            if datetime.utcnow() - ts > self.ttl:
                return None
            df = pd.read_csv(data_path, parse_dates=["date"], index_col="date")
            return df if not df.empty else None
        except Exception:
            return None

    def set_frame(self, key: str, frame: pd.DataFrame) -> None:
        data_path = self._data_path(key)
        meta_path = self._meta_path(key)
        df = frame.copy()
        df.index.name = "date"
        df.to_csv(data_path)
        meta = {"timestamp": datetime.utcnow().isoformat()}
        meta_path.write_text(json.dumps(meta))

    def get_value(self, key: str) -> Optional[float]:
        value_path = self._value_path(key)
        if not value_path.exists():
            return None
        try:
            meta = json.loads(value_path.read_text())
            ts = datetime.fromisoformat(meta.get("timestamp"))
            if datetime.utcnow() - ts > self.ttl:
                return None
            value = meta.get("value")
            return float(value) if value is not None else None
        except Exception:
            return None

    def set_value(self, key: str, value: float) -> None:
        value_path = self._value_path(key)
        meta = {"timestamp": datetime.utcnow().isoformat(), "value": float(value)}
        value_path.write_text(json.dumps(meta))

    def get_json_entry(self, key: str, *, max_age: timedelta | None = None) -> Optional[dict[str, Any]]:
        json_path = self._json_path(key)
        if not json_path.exists():
            return None
        try:
            payload = json.loads(json_path.read_text())
            ts = datetime.fromisoformat(payload.get("timestamp"))
            ttl = self.ttl if max_age is None else max_age
            if ttl is not None and datetime.utcnow() - ts > ttl:
                return None
            return payload
        except Exception:
            return None

    def get_json(self, key: str, *, max_age: timedelta | None = None) -> Optional[Any]:
        payload = self.get_json_entry(key, max_age=max_age)
        if payload is None:
            return None
        return payload.get("value")

    def set_json(self, key: str, value: Any) -> None:
        json_path = self._json_path(key)
        payload = {"timestamp": datetime.utcnow().isoformat(), "value": value}
        json_path.write_text(json.dumps(payload))

    @staticmethod
    def make_key(*parts: str) -> str:
        tokens: list[str] = []
        for part in parts:
            value = str(part or "").strip()
            if not value:
                continue
            value = re.sub(r"[\s/\\:]+", "_", value)
            value = CacheService._SAFE_FILENAME_RE.sub("_", value)
            while ".." in value:
                value = value.replace("..", "_")
            value = re.sub(r"_+", "_", value)
            value = value.strip("._-").lower()
            if value:
                tokens.append(value)
        return "_".join(tokens) or "cache"
