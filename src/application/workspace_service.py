from __future__ import annotations

from src.models.app_mode import AppMode, ResearchScopeType
from src.models.portfolio import PortfolioSnapshot


def resolve_active_snapshot(
    app_mode: AppMode,
    portfolio_snapshot: PortfolioSnapshot | None,
    research_snapshot: PortfolioSnapshot | None,
) -> PortfolioSnapshot | None:
    if app_mode == AppMode.RESEARCH:
        return research_snapshot
    return portfolio_snapshot


def should_auto_follow_research_symbol(
    app_mode: AppMode,
    scope_type: ResearchScopeType,
    auto_follow_toggle: bool,
) -> bool:
    return bool(auto_follow_toggle and app_mode == AppMode.RESEARCH and scope_type == ResearchScopeType.SINGLE_TICKER)


def should_enable_research_symbol_auto_follow(
    app_mode: AppMode,
    scope_type: ResearchScopeType,
) -> bool:
    return should_auto_follow_research_symbol(app_mode, scope_type, True)


def can_forward_research_to_iv(scope_type: ResearchScopeType) -> bool:
    return scope_type == ResearchScopeType.SINGLE_TICKER


def resolve_followed_symbol(
    primary_symbol: str,
    current_symbol: str,
    follow_enabled: bool,
) -> str | None:
    if not follow_enabled:
        return None
    target = str(primary_symbol or "").strip().upper()
    if not target:
        return None
    if target == str(current_symbol or "").strip().upper():
        return None
    return target
