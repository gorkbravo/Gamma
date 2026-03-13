from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class InstrumentDefaults:
    provider: str = "manual"
    sec_type: str | None = None
    exchange: str | None = None
    currency: str | None = None


@dataclass(frozen=True)
class InstrumentReference:
    symbol: str
    instrument_id: str | None = None
    display_symbol: str | None = None
    sec_type: str | None = None
    currency: str | None = None
    exchange: str | None = None
    primary_exchange: str | None = None
    provider: str | None = None
    provider_id: str | None = None

    def normalized_symbol(self) -> str:
        return normalize_symbol(self.symbol)

    def normalized_display_symbol(self) -> str:
        return normalize_symbol(self.display_symbol or self.symbol)

    def normalized_provider(self, default_provider: str | None = None) -> str:
        provider = str(self.provider or default_provider or "manual").strip().lower()
        return provider or "manual"

    def resolved_instrument_id(self, default_provider: str | None = None) -> str:
        return build_instrument_id(
            provider=self.normalized_provider(default_provider),
            provider_id=self.provider_id,
            symbol=self.normalized_symbol(),
            sec_type=self.sec_type,
            exchange=self.exchange,
            primary_exchange=self.primary_exchange,
            currency=self.currency,
        )

    def with_defaults(self, defaults: InstrumentDefaults) -> "InstrumentReference":
        provider = self.normalized_provider(defaults.provider)
        symbol = self.normalized_symbol()
        sec_type = normalize_symbol(self.sec_type or defaults.sec_type)
        exchange = normalize_symbol(self.exchange or defaults.exchange)
        primary_exchange = normalize_symbol(self.primary_exchange)
        currency = normalize_symbol(self.currency or defaults.currency)
        instrument_id = str(
            self.instrument_id
            or build_instrument_id(
                provider=provider,
                provider_id=self.provider_id,
                symbol=symbol,
                sec_type=sec_type,
                exchange=exchange,
                primary_exchange=primary_exchange,
                currency=currency,
            )
        )
        return InstrumentReference(
            symbol=symbol,
            instrument_id=instrument_id,
            display_symbol=self.normalized_display_symbol(),
            sec_type=sec_type or None,
            currency=currency or None,
            exchange=exchange or None,
            primary_exchange=primary_exchange or None,
            provider=provider,
            provider_id=self.provider_id,
        )
