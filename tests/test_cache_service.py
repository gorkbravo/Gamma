from __future__ import annotations

import hashlib
import os

import pandas as pd

from src.services.cache import CacheService


def _is_relative_to(path, base) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def test_json_cache_path_stays_under_base_for_hostile_windows_key(tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache")
    key = r"safe\..\..\outside\probe:CON"

    cache.set_json(key, {"ok": True})

    json_path = cache._json_path(key)
    assert _is_relative_to(json_path.resolve(strict=False), cache.base_dir.resolve())
    assert not (tmp_path / "outside").exists()
    assert cache.get_json(key) == {"ok": True}


def test_series_cache_path_stays_under_base_for_hostile_windows_key(tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache")
    key = r"prices\..\..\outside\SPY"
    series = pd.Series([1.0, 2.0], index=pd.date_range("2026-01-02", periods=2, freq="B"))

    cache.set(key, series)

    data_path = cache._data_path(key)
    assert _is_relative_to(data_path.resolve(strict=False), cache.base_dir.resolve())
    assert not (tmp_path / "outside").exists()
    restored = cache.get(key)
    assert restored is not None
    assert list(restored.astype(float)) == [1.0, 2.0]


def test_frame_cache_roundtrip_preserves_ohlcv_columns(tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache")
    index = pd.date_range("2026-01-02", periods=2, freq="B")
    frame = pd.DataFrame(
        {
            "open": [1.0, 2.0],
            "high": [1.5, 2.5],
            "low": [0.5, 1.5],
            "close": [1.2, 2.2],
            "volume": [100.0, 200.0],
        },
        index=index,
    )

    cache.set_frame("ohlcv_spy", frame)

    restored = cache.get_frame("ohlcv_spy")
    assert restored is not None
    assert list(restored.columns) == ["open", "high", "low", "close", "volume"]
    assert list(restored["close"].astype(float)) == [1.2, 2.2]
    assert list(restored.index) == list(index)


def test_cache_filename_uses_digest_and_bounded_debug_prefix(tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache")
    key = "CON/" + ("nested:" * 80) + r"..\payload"

    path = cache._json_path(key)

    assert path.name.endswith(f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.payload.json")
    assert len(path.name) < 170
    assert os.sep not in path.name[:-13]


def test_make_key_normalizes_separators_and_empty_parts():
    key = CacheService.make_key("Crypto Search", r"x\..\ETH:USD", "", "markets/list")

    assert key == "crypto_search_x_eth_usd_markets_list"
    assert ".." not in key
    assert "\\" not in key
    assert "/" not in key
    assert ":" not in key
