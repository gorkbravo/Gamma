from __future__ import annotations

from dataclasses import dataclass

from src.models.portfolio import PortfolioSnapshot, PositionItem


@dataclass(frozen=True)
class InstrumentIdentity:
    instrument_id: str
    symbol: str
    display_symbol: str
    position: PositionItem


def identity_for_position(position: PositionItem) -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id=position.resolved_instrument_id(),
        symbol=position.resolved_symbol(),
        display_symbol=position.resolved_display_symbol(),
        position=position,
    )


def snapshot_identity_map(snapshot: PortfolioSnapshot | None) -> dict[str, InstrumentIdentity]:
    if snapshot is None:
        return {}
    return {
        identity.instrument_id: identity
        for identity in (identity_for_position(position) for position in snapshot.positions)
    }


def find_identity_by_symbol(snapshot: PortfolioSnapshot | None, symbol: str | None) -> InstrumentIdentity | None:
    if snapshot is None:
        return None
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    for position in snapshot.positions:
        identity = identity_for_position(position)
        if identity.symbol == normalized:
            return identity
    return None
