from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.models.portfolio import (
    PortfolioHistoryClearResult,
    PortfolioHistoryHealth,
    PortfolioHistoryLoadResult,
    PortfolioHistoryState,
)


HISTORY_COLUMNS = [
    "date",
    "timestamp",
    "netliq",
    "market_value",
    "cash",
    "portfolio_value",
    "base_ccy",
]
NUMERIC_COLUMNS = ["netliq", "market_value", "cash", "portfolio_value"]


class PortfolioHistoryStoreError(RuntimeError):
    """Raised when the active history cannot be changed without risking data loss."""


class PortfolioHistoryCurrencyMismatchError(PortfolioHistoryStoreError):
    """Raised when an append would mix base-currency-specific snapshot trails."""


class _UnreadableHistoryError(ValueError):
    pass


class _MixedCurrencyHistoryError(ValueError):
    pass


class PortfolioHistoryStore:
    def __init__(self, base_dir: str | Path = "data", mock: bool = False) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        filename = "portfolio_history_mock.csv" if mock else "portfolio_history_live.csv"
        self.path = self.base_dir / filename
        self.health_path = self.base_dir / f"{self.path.stem}.health.json"
        self.archive_dir = self.base_dir / "portfolio_history_archives"
        self.quarantine_dir = self.base_dir / "portfolio_history_quarantine"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._pending_recovery_warnings: list[str] = []
        self._last_health = PortfolioHistoryHealth()
        self._recovery_marker = self._read_recovery_marker_unlocked()
        with self._lock:
            self._recover_interrupted_writes_unlocked()

    def append_snapshot(
        self,
        timestamp: datetime,
        netliq: float | None,
        market_value: float | None,
        cash: float | None,
        base_ccy: str,
    ) -> PortfolioHistoryHealth:
        if netliq is None and market_value is None and cash is None:
            return self.health()

        normalized_currency = self._normalize_currency(base_ccy)
        portfolio_value = (
            float(netliq)
            if netliq is not None
            else float((market_value or 0.0) + (cash or 0.0))
        )
        row = {
            "date": timestamp.date().isoformat(),
            "timestamp": self._normalize_timestamp(timestamp).isoformat(),
            "netliq": float(netliq) if netliq is not None else None,
            "market_value": float(market_value) if market_value is not None else None,
            "cash": float(cash) if cash is not None else None,
            "portfolio_value": portfolio_value,
            "base_ccy": normalized_currency,
        }

        with self._lock:
            result = self._load_unlocked(expected_base_currency=normalized_currency)
            if result.health.status == PortfolioHistoryState.FAILED:
                raise PortfolioHistoryStoreError(
                    result.health.warnings[-1]
                    if result.health.warnings
                    else "Local portfolio history is unavailable."
                )

            frame = result.frame.reset_index(drop=False) if "timestamp" not in result.frame.columns else result.frame.copy()
            if frame.empty:
                out = pd.DataFrame([row], columns=HISTORY_COLUMNS)
            else:
                frame["timestamp"] = frame["timestamp"].map(self._normalize_timestamp)
                same_day = frame["date"].astype(str) == row["date"]
                existing_latest = (
                    frame.loc[same_day, "timestamp"].max()
                    if same_day.any()
                    else None
                )
                if existing_latest is None or self._normalize_timestamp(
                    row["timestamp"]
                ) >= self._normalize_timestamp(existing_latest):
                    frame = frame.loc[~same_day].copy()
                    out = pd.concat(
                        [frame[HISTORY_COLUMNS], pd.DataFrame([row])],
                        ignore_index=True,
                    )
                else:
                    out = frame[HISTORY_COLUMNS].copy()

            validated, malformed_count, duplicate_count, validation_warnings = self._validate_frame(
                out,
                expected_base_currency=normalized_currency,
            )
            if malformed_count:
                raise PortfolioHistoryStoreError(
                    "Refusing to write an internally invalid portfolio-history snapshot."
                )

            recovery_archive_name = result.health.recovery_archive_name
            if (
                self.path.exists()
                and result.health.status == PortfolioHistoryState.DEGRADED
                and recovery_archive_name is None
            ):
                recovery_archive_name = self._backup_active_unlocked("partial-recovery")

            self._atomic_write_unlocked(validated)
            warnings = list(
                dict.fromkeys(
                    [
                        *result.health.warnings,
                        *validation_warnings,
                        *self._pending_recovery_warnings,
                    ]
                )
            )
            self._pending_recovery_warnings.clear()
            status = (
                PortfolioHistoryState.RECOVERED
                if result.health.status
                in {PortfolioHistoryState.RECOVERED, PortfolioHistoryState.DEGRADED}
                else PortfolioHistoryState.READY
            )
            health = self._build_health(
                validated,
                status=status,
                malformed_row_count=result.health.malformed_row_count,
                duplicate_row_count=result.health.duplicate_row_count + duplicate_count,
                recovery_archive_name=recovery_archive_name,
                warnings=warnings,
            )
            if status == PortfolioHistoryState.RECOVERED:
                self._record_recovery_event_unlocked(health)
            self._last_health = health
            return health

    def load_result(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> PortfolioHistoryLoadResult:
        with self._lock:
            result = self._load_unlocked()
        frame = result.frame.copy()
        if frame.empty:
            return result

        if start is not None:
            frame = frame[frame.index >= self._normalize_timestamp(start)]
        if end is not None:
            frame = frame[frame.index <= self._normalize_timestamp(end)]
        filtered_health = self._build_health(
            frame.reset_index(drop=False),
            status=result.health.status,
            malformed_row_count=result.health.malformed_row_count,
            duplicate_row_count=result.health.duplicate_row_count,
            recovery_archive_name=result.health.recovery_archive_name,
            warnings=result.health.warnings,
        )
        return PortfolioHistoryLoadResult(frame=frame, health=filtered_health)

    def load_series(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        return self.load_result(start=start, end=end).frame

    def health(self) -> PortfolioHistoryHealth:
        return self.load_result().health

    def clear(self) -> PortfolioHistoryClearResult:
        with self._lock:
            if not self.path.exists():
                self.health_path.unlink(missing_ok=True)
                self._recovery_marker = None
                self._last_health = PortfolioHistoryHealth(status=PortfolioHistoryState.EMPTY)
                return PortfolioHistoryClearResult(archived=False)
            archive_name = self._archive_target_name("cleared")
            archive_path = self.archive_dir / archive_name
            os.replace(self.path, archive_path)
            self._flush_directory(self.base_dir)
            self.health_path.unlink(missing_ok=True)
            self._recovery_marker = None
            self._last_health = PortfolioHistoryHealth(
                status=PortfolioHistoryState.EMPTY,
                recovery_archive_name=archive_name,
                warnings=[
                    "The active local portfolio history was cleared and preserved in a local archive."
                ],
            )
            return PortfolioHistoryClearResult(archived=True, archive_name=archive_name)

    def _load_unlocked(
        self,
        *,
        expected_base_currency: str | None = None,
    ) -> PortfolioHistoryLoadResult:
        self._recover_interrupted_writes_unlocked()
        if not self.path.exists():
            status = (
                PortfolioHistoryState.RECOVERED
                if self._pending_recovery_warnings or self._recovery_marker
                else PortfolioHistoryState.EMPTY
            )
            marker_warnings = list((self._recovery_marker or {}).get("warnings") or [])
            health = PortfolioHistoryHealth(
                status=status,
                malformed_row_count=int(
                    (self._recovery_marker or {}).get("malformed_row_count") or 0
                ),
                duplicate_row_count=int(
                    (self._recovery_marker or {}).get("duplicate_row_count") or 0
                ),
                recovery_archive_name=(self._recovery_marker or {}).get(
                    "recovery_archive_name"
                ),
                warnings=list(
                    dict.fromkeys([*marker_warnings, *self._pending_recovery_warnings])
                ),
            )
            self._last_health = health
            return PortfolioHistoryLoadResult(frame=self._empty_frame(indexed=True), health=health)

        try:
            raw = pd.read_csv(self.path, dtype=str, keep_default_na=False)
            valid, malformed_count, duplicate_count, warnings = self._validate_frame(
                raw,
                expected_base_currency=expected_base_currency,
            )
        except PortfolioHistoryCurrencyMismatchError:
            raise
        except (
            _UnreadableHistoryError,
            _MixedCurrencyHistoryError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
            UnicodeError,
        ) as exc:
            return self._quarantine_unreadable_unlocked(exc)
        except Exception as exc:
            warning = (
                "Local portfolio history could not be read safely. "
                f"The active file was left untouched ({type(exc).__name__})."
            )
            health = PortfolioHistoryHealth(
                status=PortfolioHistoryState.FAILED,
                warnings=[warning],
            )
            self._last_health = health
            return PortfolioHistoryLoadResult(frame=self._empty_frame(indexed=True), health=health)

        status = PortfolioHistoryState.READY
        if valid.empty:
            status = PortfolioHistoryState.DEGRADED if malformed_count else PortfolioHistoryState.EMPTY
        elif malformed_count or duplicate_count:
            status = PortfolioHistoryState.DEGRADED
        marker_warnings = list((self._recovery_marker or {}).get("warnings") or [])
        if self._recovery_marker and status == PortfolioHistoryState.READY:
            status = PortfolioHistoryState.RECOVERED
        all_warnings = list(
            dict.fromkeys(
                [*marker_warnings, *self._pending_recovery_warnings, *warnings]
            )
        )
        indexed = valid.set_index("timestamp").sort_index() if not valid.empty else self._empty_frame(indexed=True)
        health = self._build_health(
            valid,
            status=status,
            malformed_row_count=max(
                malformed_count,
                int((self._recovery_marker or {}).get("malformed_row_count") or 0),
            ),
            duplicate_row_count=max(
                duplicate_count,
                int((self._recovery_marker or {}).get("duplicate_row_count") or 0),
            ),
            recovery_archive_name=(self._recovery_marker or {}).get(
                "recovery_archive_name"
            ),
            warnings=all_warnings,
        )
        self._last_health = health
        return PortfolioHistoryLoadResult(frame=indexed, health=health)

    def _validate_frame(
        self,
        frame: pd.DataFrame,
        *,
        expected_base_currency: str | None = None,
    ) -> tuple[pd.DataFrame, int, int, list[str]]:
        if frame is None:
            raise _UnreadableHistoryError("History payload is missing.")
        missing_columns = [column for column in HISTORY_COLUMNS if column not in frame.columns]
        if missing_columns:
            raise _UnreadableHistoryError(
                f"History schema is missing required columns: {', '.join(missing_columns)}"
            )

        working = frame[HISTORY_COLUMNS].copy()
        if working.empty:
            return self._empty_frame(indexed=False), 0, 0, []

        parsed_timestamp = pd.to_datetime(working["timestamp"], errors="coerce", utc=True)
        parsed_date = pd.to_datetime(working["date"], errors="coerce").dt.date
        normalized_currency = working["base_ccy"].astype(str).str.strip().str.upper()
        valid_currency = normalized_currency.str.fullmatch(r"[A-Z]{3}", na=False)

        invalid = parsed_timestamp.isna() | parsed_date.isna() | ~valid_currency
        for column in NUMERIC_COLUMNS:
            raw_values = (
                working[column]
                .where(working[column].notna(), "")
                .astype(str)
                .str.strip()
            )
            numeric_values = pd.to_numeric(raw_values.replace("", np.nan), errors="coerce")
            supplied = raw_values != ""
            invalid_numeric = supplied & (~np.isfinite(numeric_values))
            invalid |= invalid_numeric
            working[column] = numeric_values.astype(float)

        invalid |= working["portfolio_value"].isna()
        timestamp_dates = parsed_timestamp.dt.date
        invalid |= parsed_date != timestamp_dates
        malformed_count = int(invalid.sum())

        working["timestamp"] = parsed_timestamp
        working["date"] = parsed_date.map(lambda value: value.isoformat() if value is not pd.NaT and value is not None else "")
        working["base_ccy"] = normalized_currency
        valid = working.loc[~invalid].copy()

        currencies = sorted(set(valid["base_ccy"].astype(str)))
        if len(currencies) > 1:
            raise _MixedCurrencyHistoryError(
                "Local portfolio history contains mixed base currencies."
            )
        if expected_base_currency and currencies and currencies[0] != expected_base_currency:
            raise PortfolioHistoryCurrencyMismatchError(
                "Local portfolio history uses "
                f"{currencies[0]}, so a {expected_base_currency} snapshot was not appended. "
                "Clear or archive currency-specific history before changing the base currency."
            )

        valid = valid.sort_values(["date", "timestamp"], kind="stable")
        duplicate_mask = valid.duplicated(subset=["date"], keep="last")
        duplicate_count = int(duplicate_mask.sum())
        valid = valid.loc[~duplicate_mask, HISTORY_COLUMNS].reset_index(drop=True)

        warnings: list[str] = []
        if malformed_count:
            warnings.append(
                f"Ignored {malformed_count} malformed local portfolio history "
                f"{'row' if malformed_count == 1 else 'rows'}; valid rows remain available."
            )
        if duplicate_count:
            warnings.append(
                f"Collapsed {duplicate_count} duplicate local portfolio history "
                f"{'row' if duplicate_count == 1 else 'rows'} using the latest timestamp per day."
            )
        return valid, malformed_count, duplicate_count, warnings

    def _quarantine_unreadable_unlocked(self, exc: Exception) -> PortfolioHistoryLoadResult:
        try:
            archive_name = self._archive_target_name(f"quarantine-{type(exc).__name__}")
            target = self.quarantine_dir / archive_name
            os.replace(self.path, target)
            self._flush_directory(self.base_dir)
        except Exception as quarantine_exc:
            warning = (
                "Local portfolio history is unreadable and could not be quarantined safely; "
                f"the active file was left untouched ({type(quarantine_exc).__name__})."
            )
            health = PortfolioHistoryHealth(
                status=PortfolioHistoryState.FAILED,
                warnings=[warning],
            )
            self._last_health = health
            return PortfolioHistoryLoadResult(frame=self._empty_frame(indexed=True), health=health)

        warning = (
            "Local portfolio history was unreadable or structurally invalid. "
            f"The original was preserved as {archive_name}; a new local trail can accumulate."
        )
        health = PortfolioHistoryHealth(
            status=PortfolioHistoryState.RECOVERED,
            recovery_archive_name=archive_name,
            warnings=[warning],
        )
        self._record_recovery_event_unlocked(health)
        self._last_health = health
        return PortfolioHistoryLoadResult(frame=self._empty_frame(indexed=True), health=health)

    def _atomic_write_unlocked(self, frame: pd.DataFrame) -> None:
        temp_path = self.base_dir / f".{self.path.name}.{uuid.uuid4().hex}.tmp"
        serializable = frame[HISTORY_COLUMNS].copy()
        serializable["timestamp"] = serializable["timestamp"].map(self._normalize_timestamp)
        try:
            with temp_path.open("w", encoding="utf-8", newline="") as handle:
                serializable.to_csv(handle, index=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            self._flush_directory(self.base_dir)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _recover_interrupted_writes_unlocked(self) -> None:
        candidates = sorted(
            self.base_dir.glob(f".{self.path.name}.*.tmp"),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return

        if self.path.exists():
            for candidate in candidates:
                self._move_temp_to_quarantine_unlocked(candidate, "stale-interrupted-write")
            self._pending_recovery_warnings.append(
                "Preserved stale interrupted portfolio-history write data in quarantine."
            )
            return

        recovered = False
        for candidate in candidates:
            if recovered:
                self._move_temp_to_quarantine_unlocked(candidate, "superseded-interrupted-write")
                continue
            try:
                raw = pd.read_csv(candidate, dtype=str, keep_default_na=False)
                valid, malformed_count, duplicate_count, _ = self._validate_frame(raw)
                if valid.empty or malformed_count or duplicate_count:
                    raise _UnreadableHistoryError("Interrupted write was incomplete.")
                os.replace(candidate, self.path)
                self._flush_directory(self.base_dir)
                recovered = True
                self._pending_recovery_warnings.append(
                    "Recovered a complete interrupted atomic portfolio-history write."
                )
            except Exception:
                self._move_temp_to_quarantine_unlocked(candidate, "invalid-interrupted-write")
                self._pending_recovery_warnings.append(
                    "Preserved an incomplete interrupted portfolio-history write in quarantine."
                )
        if self._pending_recovery_warnings:
            self._record_recovery_event_unlocked(
                PortfolioHistoryHealth(
                    status=PortfolioHistoryState.RECOVERED,
                    warnings=list(self._pending_recovery_warnings),
                )
            )

    def _move_temp_to_quarantine_unlocked(self, path: Path, reason: str) -> None:
        if not path.exists():
            return
        target = self.quarantine_dir / self._archive_target_name(reason)
        os.replace(path, target)

    def _backup_active_unlocked(self, reason: str) -> str | None:
        if not self.path.exists():
            return None
        archive_name = self._archive_target_name(reason)
        target = self.quarantine_dir / archive_name
        shutil.copy2(self.path, target)
        return archive_name

    def _build_health(
        self,
        frame: pd.DataFrame,
        *,
        status: PortfolioHistoryState,
        malformed_row_count: int = 0,
        duplicate_row_count: int = 0,
        recovery_archive_name: str | None = None,
        warnings: list[str] | None = None,
    ) -> PortfolioHistoryHealth:
        if frame is None or frame.empty:
            return PortfolioHistoryHealth(
                status=status,
                malformed_row_count=malformed_row_count,
                duplicate_row_count=duplicate_row_count,
                recovery_archive_name=recovery_archive_name,
                warnings=list(warnings or []),
            )

        working = frame.reset_index(drop=False) if "timestamp" not in frame.columns else frame
        timestamps = pd.to_datetime(working["timestamp"], errors="coerce", utc=True).dropna()
        currencies = sorted(set(working["base_ccy"].dropna().astype(str)))
        last_write_at = None
        if self.path.exists():
            last_write_at = datetime.fromtimestamp(self.path.stat().st_mtime, tz=timezone.utc)
        return PortfolioHistoryHealth(
            status=status,
            point_count=int(len(working)),
            base_currency=currencies[0] if len(currencies) == 1 else None,
            first_timestamp=(
                timestamps.min().to_pydatetime() if not timestamps.empty else None
            ),
            last_timestamp=(
                timestamps.max().to_pydatetime() if not timestamps.empty else None
            ),
            malformed_row_count=malformed_row_count,
            duplicate_row_count=duplicate_row_count,
            recovery_archive_name=recovery_archive_name,
            last_write_at=last_write_at,
            warnings=list(warnings or []),
        )

    @staticmethod
    def _empty_frame(*, indexed: bool) -> pd.DataFrame:
        frame = pd.DataFrame(columns=HISTORY_COLUMNS)
        if indexed:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            return frame.set_index("timestamp")
        return frame

    @staticmethod
    def _normalize_currency(value: str | None) -> str:
        normalized = str(value or "").strip().upper()
        if re.fullmatch(r"[A-Z]{3}", normalized) is None:
            raise ValueError("Portfolio history base currency must be a 3-letter ISO code.")
        return normalized

    @staticmethod
    def _normalize_timestamp(value: datetime | pd.Timestamp) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")

    def _archive_target_name(self, reason: str) -> str:
        safe_reason = re.sub(r"[^a-z0-9-]+", "-", reason.lower()).strip("-") or "preserved"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{self.path.stem}.{stamp}.{safe_reason}{self.path.suffix}"

    def _read_recovery_marker_unlocked(self) -> dict[str, object] | None:
        if not self.health_path.exists():
            return None
        try:
            payload = json.loads(self.health_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _record_recovery_event_unlocked(
        self,
        health: PortfolioHistoryHealth,
    ) -> None:
        payload = {
            "status": PortfolioHistoryState.RECOVERED.value,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "malformed_row_count": int(health.malformed_row_count),
            "duplicate_row_count": int(health.duplicate_row_count),
            "recovery_archive_name": health.recovery_archive_name,
            "warnings": list(health.warnings),
        }
        temp_path = self.base_dir / f".{self.health_path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8", newline="") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.health_path)
            self._flush_directory(self.base_dir)
            self._recovery_marker = payload
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _flush_directory(path: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
