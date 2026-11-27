"""Escritura atómica compartida por stores y caché (2026-11-27)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.services.cache import CacheService
from src.utils import atomic_io
from src.utils.atomic_io import atomic_write_text


def test_atomic_write_creates_and_replaces_without_leftovers(tmp_path):
    target = tmp_path / "nested" / "item.json"

    atomic_write_text(target, json.dumps({"v": 1}))
    atomic_write_text(target, json.dumps({"v": 2}))

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}
    assert [path.name for path in target.parent.iterdir()] == ["item.json"]


def test_failed_replace_keeps_the_previous_file_intact(tmp_path, monkeypatch):
    target = tmp_path / "item.json"
    atomic_write_text(target, json.dumps({"v": 1}))

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_io.os, "replace", broken_replace)
    with pytest.raises(OSError):
        atomic_write_text(target, json.dumps({"v": 2}))

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}
    assert [path.name for path in tmp_path.iterdir()] == ["item.json"]


def test_cache_round_trips_series_and_json_through_atomic_writes(tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache", ttl_hours=24)
    series = pd.Series([1.0, 2.5], index=pd.to_datetime(["2026-01-02", "2026-01-05"]), name="close")

    cache.set("prices", series)
    cache.set_json("payload", {"a": [1, 2]})

    loaded = cache.get("prices")
    assert loaded is not None and list(loaded.values) == [1.0, 2.5]
    assert cache.get_json("payload") == {"a": [1, 2]}
    assert not [path for path in (tmp_path / "cache").rglob("*.tmp")]


def test_spot_fx_cache_is_limited_to_thirty_minutes(tmp_path):
    """El «spot» en disco valía el TTL general de 24 h (2026-11-27)."""
    from datetime import datetime as _dt, timedelta as _td

    from src.services.fx import FXService

    cache = CacheService(base_dir=tmp_path / "cache", ttl_hours=24)
    service = FXService(None, cache=cache)
    key = service._cache_key("EUR", "USD")
    cache.set_value(key, 1.1)

    assert service.get_rate("EUR", "USD") == pytest.approx(1.1)

    path = cache._value_path(key)
    meta = json.loads(path.read_text())
    meta["timestamp"] = (_dt.utcnow() - _td(hours=2)).isoformat()
    path.write_text(json.dumps(meta))
    service._memory_cache.clear()

    assert cache.get_value(key) == pytest.approx(1.1)  # el TTL general (24 h) sigue valiendo para otros usos
    assert service.get_rate("EUR", "USD") is None  # sin TWS y con el spot caducado no hay tipo de cambio
