from __future__ import annotations

import math
from dataclasses import dataclass, replace

from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.instruments import normalize_symbol


@dataclass(frozen=True)
class ResearchScopeValidationResult:
    valid: bool
    errors: list[str]
    primary_symbol: str
    synthetic_positions: list[SyntheticPosition]


class ResearchValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Invalid research scope")
        self.errors = list(errors)


def validate_research_scope(
    scope_type: ResearchScopeType,
    primary_symbol: str,
    synthetic_positions: list[SyntheticPosition] | None,
) -> ResearchScopeValidationResult:
    normalized_primary = normalize_symbol(primary_symbol)
    normalized_positions: list[SyntheticPosition] = []
    errors: list[str] = []
    items = list(synthetic_positions or [])

    if scope_type == ResearchScopeType.SINGLE_TICKER:
        if not normalized_primary:
            errors.append("Ticker is required for single-ticker research scope")
        if items:
            errors.append("Single-ticker research scope does not accept synthetic positions")
        return ResearchScopeValidationResult(
            valid=not errors,
            errors=errors,
            primary_symbol=normalized_primary,
            synthetic_positions=[],
        )

    if scope_type == ResearchScopeType.SYNTHETIC_PORTFOLIO:
        if normalized_primary:
            errors.append("Synthetic portfolio research scope does not accept a primary symbol")
        if not items:
            errors.append("Synthetic portfolio requires at least one symbol")

        seen_instruments: set[str] = set()
        total_weight = 0.0
        for item in items:
            symbol = normalize_symbol(item.symbol)
            if not symbol:
                errors.append("Synthetic portfolio contains an empty symbol")
                continue

            try:
                weight = float(item.weight)
            except (TypeError, ValueError):
                errors.append(f"Synthetic weight is invalid for {symbol}")
                continue
            if not math.isfinite(weight):
                errors.append(f"Synthetic weight is invalid for {symbol}")
                continue
            if weight <= 0:
                errors.append(f"Synthetic weight must be positive for {symbol}")
                continue

            identity_key = _synthetic_identity_key(item, symbol)
            if identity_key in seen_instruments:
                errors.append(f"Duplicate symbol in synthetic portfolio: {symbol}")
                continue
            seen_instruments.add(identity_key)

            total_weight += weight
            normalized_positions.append(
                replace(
                    item,
                    symbol=symbol,
                    weight=weight,
                    display_symbol=item.resolved_display_symbol(symbol=symbol),
                )
            )

        if normalized_positions and total_weight <= 0:
            errors.append("Synthetic portfolio weights sum to zero")

        return ResearchScopeValidationResult(
            valid=not errors,
            errors=errors,
            primary_symbol="",
            synthetic_positions=normalized_positions,
        )

    errors.append("Research scope is not configured")
    return ResearchScopeValidationResult(
        valid=False,
        errors=errors,
        primary_symbol=normalized_primary,
        synthetic_positions=normalized_positions,
    )


def ensure_valid_research_scope(
    scope_type: ResearchScopeType,
    primary_symbol: str,
    synthetic_positions: list[SyntheticPosition] | None,
) -> ResearchScopeValidationResult:
    validation = validate_research_scope(scope_type, primary_symbol, synthetic_positions)
    if not validation.valid:
        raise ResearchValidationError(validation.errors)
    return validation


def _synthetic_identity_key(item: SyntheticPosition, symbol: str) -> str:
    explicit_instrument_id = str(item.instrument_id or "").strip()
    if explicit_instrument_id:
        return explicit_instrument_id
    if (
        str(item.provider_id or "").strip()
        or str(item.provider or "").strip()
        or str(item.exchange or "").strip()
        or str(item.primary_exchange or "").strip()
        or str(item.currency or "").strip()
        or str(item.sec_type or "").strip()
    ):
        return item.resolved_instrument_id(symbol=symbol)
    return symbol
