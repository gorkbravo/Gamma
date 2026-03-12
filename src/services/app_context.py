from __future__ import annotations

from dataclasses import dataclass
from typing import List
from PySide6.QtCore import QObject, Signal

from src.application.research_validation import validate_research_scope
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

    def clear_research_state(self) -> None:
        self.research_scope_type = ResearchScopeType.NONE
        self.primary_symbol = ""
        self.synthetic_positions = []
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
        validation = validate_research_scope(scope_type, primary_symbol, synthetic_positions)
        return ResearchScopeValidation(valid=validation.valid, errors=validation.errors)
