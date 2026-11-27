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
