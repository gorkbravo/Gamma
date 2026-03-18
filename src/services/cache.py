from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd


class CacheService:
    def __init__(self, base_dir: str | Path = "cache", ttl_hours: int = 24) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)

    def _meta_path(self, key: str) -> Path:
        return self.base_dir / f"{key}.json"

    def _data_path(self, key: str) -> Path:
        return self.base_dir / f"{key}.csv"

    def _value_path(self, key: str) -> Path:
        return self.base_dir / f"{key}.value.json"

    def _json_path(self, key: str) -> Path:
        return self.base_dir / f"{key}.payload.json"

    def get(self, key: str) -> Optional[pd.Series]:
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

    def get_json(self, key: str) -> Optional[Any]:
        json_path = self._json_path(key)
        if not json_path.exists():
            return None
        try:
            payload = json.loads(json_path.read_text())
            ts = datetime.fromisoformat(payload.get("timestamp"))
            if datetime.utcnow() - ts > self.ttl:
                return None
            return payload.get("value")
        except Exception:
            return None

    def set_json(self, key: str, value: Any) -> None:
        json_path = self._json_path(key)
        payload = {"timestamp": datetime.utcnow().isoformat(), "value": value}
        json_path.write_text(json.dumps(payload))

    @staticmethod
    def make_key(*parts: str) -> str:
        safe = "_".join(p.replace(" ", "").replace("/", "_") for p in parts if p)
        return safe.lower()
