from __future__ import annotations


def normalize_symbol(value: str | None) -> str:
    return str(value or "").strip().upper()


def build_instrument_id(
    *,
    provider: str | None,
    symbol: str | None,
    sec_type: str | None = None,
    exchange: str | None = None,
    primary_exchange: str | None = None,
    currency: str | None = None,
    provider_id: str | None = None,
) -> str:
    provider_name = str(provider or "manual").strip().lower() or "manual"
    external_id = str(provider_id or "").strip()
    if external_id:
        return f"{provider_name}:{external_id}"

    parts = [
        normalize_symbol(symbol) or "UNKNOWN",
        normalize_symbol(sec_type),
        normalize_symbol(exchange),
        normalize_symbol(primary_exchange),
        normalize_symbol(currency),
    ]
    compact = [part for part in parts if part]
    return f"{provider_name}:{':'.join(compact)}"
