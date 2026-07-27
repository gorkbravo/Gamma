from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.services.portfolio_history_store as history_module
from src.models.portfolio import PortfolioHistoryState
from src.services.portfolio_history_store import (
    PortfolioHistoryCurrencyMismatchError,
    PortfolioHistoryStore,
)


def _timestamp(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 7, day, hour, 0, tzinfo=timezone.utc)


def _append(
    store: PortfolioHistoryStore,
    timestamp: datetime,
    value: float,
    currency: str = "USD",
):
    return store.append_snapshot(
        timestamp,
        netliq=value,
        market_value=value - 10.0,
        cash=10.0,
        base_ccy=currency,
    )


def test_same_day_snapshot_replacement_is_atomic_and_keeps_latest_timestamp(tmp_path):
    store = PortfolioHistoryStore(tmp_path)
    _append(store, _timestamp(20, 9), 100.0)
    first_contents = store.path.read_text(encoding="utf-8")

    _append(store, _timestamp(20, 15), 125.0)
    _append(store, _timestamp(20, 10), 110.0)

    result = store.load_result()
    assert result.health.status == PortfolioHistoryState.READY
    assert result.health.point_count == 1
    assert float(result.frame.iloc[0]["portfolio_value"]) == pytest.approx(125.0)
    assert result.frame.index[0].hour == 15
    assert store.path.read_text(encoding="utf-8") != first_contents
    assert list(tmp_path.glob(f".{store.path.name}.*.tmp")) == []


def test_failed_atomic_replace_preserves_previous_active_history(tmp_path, monkeypatch):
    store = PortfolioHistoryStore(tmp_path)
    _append(store, _timestamp(20), 100.0)
    original_contents = store.path.read_text(encoding="utf-8")
    real_replace = history_module.os.replace

    def fail_active_replace(source, target):
        if Path(target) == store.path:
            raise OSError("simulated interrupted replace")
        return real_replace(source, target)

    monkeypatch.setattr(history_module.os, "replace", fail_active_replace)
    with pytest.raises(OSError, match="simulated interrupted replace"):
        _append(store, _timestamp(21), 110.0)

    assert store.path.read_text(encoding="utf-8") == original_contents
    assert list(tmp_path.glob(f".{store.path.name}.*.tmp")) == []


def test_partial_malformed_and_duplicate_rows_preserve_valid_history_and_recover_on_append(
    tmp_path,
):
    store = PortfolioHistoryStore(tmp_path)
    original = "\n".join(
        [
            "date,timestamp,netliq,market_value,cash,portfolio_value,base_ccy",
            "2026-07-20,2026-07-20T09:00:00+00:00,100,90,10,100,USD",
            "2026-07-20,2026-07-20T15:00:00+00:00,120,110,10,120,USD",
            "2026-07-21,not-a-timestamp,broken,90,10,broken,USD",
            "2026-07-22,2026-07-22T12:00:00+00:00,130,120,10,130,USD",
            "",
        ]
    )
    store.path.write_text(original, encoding="utf-8")

    degraded = store.load_result()
    assert degraded.health.status == PortfolioHistoryState.DEGRADED
    assert degraded.health.malformed_row_count == 1
    assert degraded.health.duplicate_row_count == 1
    assert degraded.health.point_count == 2
    assert list(degraded.frame["portfolio_value"].astype(float)) == [120.0, 130.0]
    assert store.path.read_text(encoding="utf-8") == original

    recovered_health = _append(store, _timestamp(23), 140.0)
    assert recovered_health.status == PortfolioHistoryState.RECOVERED
    assert recovered_health.recovery_archive_name is not None
    backup = store.quarantine_dir / recovered_health.recovery_archive_name
    assert backup.read_text(encoding="utf-8") == original
    assert len(store.load_result().frame) == 3

    restarted = PortfolioHistoryStore(tmp_path)
    restarted_result = restarted.load_result()
    assert restarted_result.health.status == PortfolioHistoryState.RECOVERED
    assert restarted_result.health.malformed_row_count == 1
    assert restarted_result.health.duplicate_row_count == 1
    assert restarted_result.health.recovery_archive_name == recovered_health.recovery_archive_name


def test_unreadable_history_is_quarantined_and_recovery_survives_restart(tmp_path):
    store = PortfolioHistoryStore(tmp_path)
    unreadable = b"\xff\xfe\x00not-a-valid-csv"
    store.path.write_bytes(unreadable)

    result = store.load_result()
    assert result.health.status == PortfolioHistoryState.RECOVERED
    assert result.frame.empty
    assert result.health.recovery_archive_name is not None
    quarantine = store.quarantine_dir / result.health.recovery_archive_name
    assert quarantine.read_bytes() == unreadable
    assert not store.path.exists()

    restarted = PortfolioHistoryStore(tmp_path)
    restarted_result = restarted.load_result()
    assert restarted_result.health.status == PortfolioHistoryState.RECOVERED
    assert restarted_result.health.recovery_archive_name == result.health.recovery_archive_name
    assert any("preserved" in warning.lower() for warning in restarted_result.health.warnings)


def test_mixed_currency_file_is_quarantined_and_append_currency_mismatch_is_rejected(
    tmp_path,
):
    mixed_store = PortfolioHistoryStore(tmp_path / "mixed")
    mixed_store.path.write_text(
        "\n".join(
            [
                "date,timestamp,netliq,market_value,cash,portfolio_value,base_ccy",
                "2026-07-20,2026-07-20T12:00:00+00:00,100,90,10,100,USD",
                "2026-07-21,2026-07-21T12:00:00+00:00,100,90,10,100,EUR",
            ]
        ),
        encoding="utf-8",
    )
    mixed_result = mixed_store.load_result()
    assert mixed_result.health.status == PortfolioHistoryState.RECOVERED
    assert mixed_result.frame.empty
    assert not mixed_store.path.exists()
    assert list(mixed_store.quarantine_dir.glob("*.csv"))

    mismatch_store = PortfolioHistoryStore(tmp_path / "mismatch")
    _append(mismatch_store, _timestamp(20), 100.0, "USD")
    before = mismatch_store.path.read_text(encoding="utf-8")
    with pytest.raises(PortfolioHistoryCurrencyMismatchError, match="uses USD"):
        _append(mismatch_store, _timestamp(21), 110.0, "EUR")
    assert mismatch_store.path.read_text(encoding="utf-8") == before
    assert mismatch_store.load_result().health.base_currency == "USD"


def test_history_persists_across_restart_and_clear_preserves_recovery_archive(tmp_path):
    store = PortfolioHistoryStore(tmp_path)
    _append(store, _timestamp(20), 100.0)
    _append(store, _timestamp(21), 110.0)

    restarted = PortfolioHistoryStore(tmp_path)
    persisted = restarted.load_result()
    assert persisted.health.status == PortfolioHistoryState.READY
    assert persisted.health.point_count == 2
    assert list(persisted.frame["portfolio_value"].astype(float)) == [100.0, 110.0]

    clear_result = restarted.clear()
    assert clear_result.archived is True
    assert clear_result.archive_name is not None
    archive = restarted.archive_dir / clear_result.archive_name
    assert archive.exists()
    assert "2026-07-20" in archive.read_text(encoding="utf-8")
    assert not restarted.path.exists()
    assert restarted.load_result().health.status == PortfolioHistoryState.EMPTY

    repeated_clear = restarted.clear()
    assert repeated_clear.archived is False
    assert archive.exists()


def test_interrupted_complete_atomic_write_is_recovered_on_restart(tmp_path):
    temp_path = tmp_path / ".portfolio_history_live.csv.interrupted.tmp"
    temp_path.write_text(
        "\n".join(
            [
                "date,timestamp,netliq,market_value,cash,portfolio_value,base_ccy",
                "2026-07-20,2026-07-20T12:00:00+00:00,100,90,10,100,USD",
            ]
        ),
        encoding="utf-8",
    )

    store = PortfolioHistoryStore(tmp_path)
    result = store.load_result()
    assert result.health.status == PortfolioHistoryState.RECOVERED
    assert result.health.point_count == 1
    assert store.path.exists()
    assert not temp_path.exists()
    assert any("interrupted atomic" in warning.lower() for warning in result.health.warnings)


def test_concurrent_repeated_appends_keep_one_latest_snapshot_per_day(tmp_path):
    store = PortfolioHistoryStore(tmp_path)
    hours = [8, 17, 10, 14, 9, 16, 11, 13]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(_append, store, _timestamp(20, hour), float(100 + hour))
            for hour in hours
        ]
        for future in futures:
            future.result()

    result = store.load_result()
    assert result.health.status == PortfolioHistoryState.READY
    assert result.health.point_count == 1
    assert result.frame.index[0].hour == max(hours)
    assert float(result.frame.iloc[0]["portfolio_value"]) == pytest.approx(
        100.0 + max(hours)
    )
