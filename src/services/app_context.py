from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
from PySide6.QtCore import QObject, Signal

from src.models.app_mode import AppMode, ResearchScopeType, SyntheticPosition
from src.models.portfolio import PortfolioSnapshot


@dataclass(frozen=True)
class ResearchScopeValidation:
    valid: bool
    errors: List[str]


class AppDataContext(QObject):
    app_mode_changed = Signal(str)
    research_scope_changed = Signal()
    research_snapshot_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.app_mode = AppMode.PORTFOLIO
        self.research_scope_type = ResearchScopeType.NONE
        self.primary_symbol = ""
        self.synthetic_positions: List[SyntheticPosition] = []
        self.cached_timeseries: Dict[str, tuple[pd.Series, int]] = {}
        self._cache_lock = threading.Lock()
        self.research_snapshot: PortfolioSnapshot | None = None

    def set_app_mode(self, mode: AppMode) -> None:
        if mode == self.app_mode:
            return
        self.app_mode = mode
        self.app_mode_changed.emit(mode.value)

    def set_research_scope(
        self,
        scope_type: ResearchScopeType,
        primary_symbol: str = "",
        synthetic_positions: List[SyntheticPosition] | None = None,
    ) -> None:
        self.research_scope_type = scope_type
        self.primary_symbol = str(primary_symbol or "").strip().upper()
        self.synthetic_positions = list(synthetic_positions or [])
        self.research_scope_changed.emit()

    def set_cached_timeseries(self, symbol: str, series: pd.Series, lookback_days: int) -> None:
        key = str(symbol or "").strip().upper()
        if not key:
            return
        lookback = max(int(lookback_days or 0), 0)
        with self._cache_lock:
            existing = self.cached_timeseries.get(key)
            if existing is not None:
                existing_series, existing_lookback = existing
                if existing_lookback > lookback and len(existing_series) >= len(series):
                    return
            self.cached_timeseries[key] = (series, lookback)

    def get_cached_timeseries(self, symbol: str, min_lookback_days: int = 0) -> pd.Series | None:
        key = str(symbol or "").strip().upper()
        if not key:
            return None
        required = max(int(min_lookback_days or 0), 0)
        with self._cache_lock:
            cached = self.cached_timeseries.get(key)
        if cached is None:
            return None
        series, lookback = cached
        if lookback < required:
            return None
        return series

    def clear_research_state(self) -> None:
        self.research_scope_type = ResearchScopeType.NONE
        self.primary_symbol = ""
        self.synthetic_positions = []
        with self._cache_lock:
            self.cached_timeseries = {}
        self.research_snapshot = None
        self.research_scope_changed.emit()
        self.research_snapshot_changed.emit(None)

    def set_research_snapshot(self, snapshot: PortfolioSnapshot | None) -> None:
        self.research_snapshot = snapshot
        self.research_snapshot_changed.emit(snapshot)

    @staticmethod
    def validate_scope(
        scope_type: ResearchScopeType,
        primary_symbol: str,
        synthetic_positions: List[SyntheticPosition],
    ) -> ResearchScopeValidation:
        errors: List[str] = []
        if scope_type == ResearchScopeType.SINGLE_TICKER:
            if not str(primary_symbol or "").strip():
                errors.append("Ticker is required for single-ticker research scope")
        elif scope_type == ResearchScopeType.SYNTHETIC_PORTFOLIO:
            if not synthetic_positions:
                errors.append("Synthetic portfolio requires at least one symbol")
            seen: set[str] = set()
            total_weight = 0.0
            for item in synthetic_positions:
                symbol = str(item.symbol or "").strip().upper()
                if not symbol:
                    errors.append("Synthetic portfolio contains an empty symbol")
                    continue
                if symbol in seen:
                    errors.append(f"Duplicate symbol in synthetic portfolio: {symbol}")
                seen.add(symbol)
                weight = float(item.weight)
                if weight <= 0:
                    errors.append(f"Synthetic weight must be positive for {symbol}")
                total_weight += weight
            if synthetic_positions and abs(total_weight) < 1e-12:
                errors.append("Synthetic portfolio weights sum to zero")
        return ResearchScopeValidation(valid=not errors, errors=errors)
