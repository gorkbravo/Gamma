from __future__ import annotations

import io
import json
from datetime import date

import pandas as pd

from src.services.cache import CacheService
from src.services.risk_free_rate import RiskFreeRateService


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_risk_free_service_fetches_sofrindex_and_caches(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_urlopen(url, timeout=0):
        calls["count"] += 1
        assert "series_id=SOFRINDEX" in url
        payload = {
            "observations": [
                {"date": "2026-01-02", "value": "100.0000"},
                {"date": "2026-01-05", "value": "100.0100"},
                {"date": "2026-01-06", "value": "100.0200"},
            ]
        }
        return _FakeHTTPResponse(payload)

    monkeypatch.setattr("src.services.risk_free_rate.urlopen", fake_urlopen)
    cache = CacheService(base_dir=tmp_path / "cache", ttl_hours=24)
    svc = RiskFreeRateService(cache=cache, fred_api_key="test-key")

    rf1, warnings1 = svc.get_usd_daily_returns(date(2026, 1, 1), date(2026, 1, 6))
    rf2, warnings2 = svc.get_usd_daily_returns(date(2026, 1, 2), date(2026, 1, 6))

    assert warnings1 == []
    assert warnings2 == []
    assert rf1 is not None and not rf1.empty
    assert isinstance(rf1, pd.Series)
    assert calls["count"] == 1
    assert rf2 is not None and not rf2.empty
    assert rf1.index.min() <= rf2.index.min()
