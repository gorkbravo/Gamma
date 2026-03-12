from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Protocol, Tuple

import pandas as pd
from ib_insync import Contract

from src.application.workspace_service import should_auto_follow_research_symbol
from src.models.app_mode import AppMode, ResearchScopeType, SyntheticPosition
from src.models.instruments import build_instrument_id, normalize_symbol
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.services.app_context import AppDataContext
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.research_cache import ResearchHistoryCache
from src.utils.time import now_utc


def contract_for_position(position: PositionItem) -> Contract:
    contract = Contract(
        symbol=position.symbol,
        secType=position.sec_type or "STK",
        exchange=position.exchange or "SMART",
        currency=position.currency or "USD",
    )
    provider_id = str(position.provider_id or "").strip()
    if provider_id.isdigit():
        contract.conId = int(provider_id)
    primary_exchange = str(position.primary_exchange or "").strip()
    if primary_exchange:
        contract.primaryExchange = primary_exchange
    return contract


class AppDataProvider(Protocol):
    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        ...


@dataclass
class PortfolioDataProvider:
    client: IBKRClient
    market_data: MarketDataService
    mock_service: MockDataService

    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        if self.client.mock:
            prices: Dict[str, pd.Series] = {}
            missing: List[str] = []
            for pos in snapshot.positions:
                if pos.symbol.startswith("CASH"):
                    continue
                series = self.mock_service.load_history(pos.symbol)
                instrument_id = pos.resolved_instrument_id()
                display_symbol = pos.resolved_display_symbol()
                if series is None:
                    missing.append(display_symbol)
                else:
                    prices[instrument_id] = series.astype(float)
            return prices, missing

        contracts: List[Contract] = []
        keys: List[str] = []
        labels: List[str] = []
        for pos in snapshot.positions:
            if pos.symbol.startswith("CASH"):
                continue
            contracts.append(contract_for_position(pos))
            keys.append(pos.resolved_instrument_id())
            labels.append(pos.resolved_display_symbol())
        return self.market_data.fetch_histories(
            contracts,
            lookback_days,
            progress_cb=progress_cb,
            keys=keys,
            labels=labels,
        )


@dataclass
class ResearchDataProvider:
    client: IBKRClient
    market_data: MarketDataService
    mock_service: MockDataService
    context: AppDataContext | None
    base_currency: str
    history_cache: ResearchHistoryCache

    def load_symbol_history(self, symbol: str, lookback_days: int) -> pd.Series | None:
        ticker = str(symbol or "").strip().upper()
        if not ticker:
            return None
        cached = self.history_cache.get(ticker, lookback_days)
        if cached is not None and not cached.empty:
            return cached
        if self.client.mock:
            series = self.mock_service.load_history(ticker)
        else:
            contract = Contract(symbol=ticker, secType="STK", exchange="SMART", currency="USD")
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is not None and not series.empty:
            self.history_cache.set(ticker, series, lookback_days)
        return series

    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        prices: Dict[str, pd.Series] = {}
        missing: List[str] = []
        positions = [pos for pos in snapshot.positions if not pos.symbol.startswith("CASH")]
        total = len(positions)
        for idx, position in enumerate(positions, start=1):
            symbol = position.resolved_symbol()
            instrument_id = position.resolved_instrument_id()
            display_symbol = position.resolved_display_symbol()
            series = self.load_symbol_history(symbol, lookback_days)
            if series is None or series.empty:
                missing.append(display_symbol)
            else:
                prices[instrument_id] = series.astype(float)
            if progress_cb:
                progress_cb(idx, total, display_symbol)
        return prices, missing

    def build_snapshot(self) -> tuple[PortfolioSnapshot | None, List[str]]:
        if self.context is None:
            return None, ["Research scope is not configured"]
        return self.build_snapshot_for_scope(
            self.context.research_scope_type,
            primary_symbol=self.context.primary_symbol,
            synthetic_positions=self.context.synthetic_positions,
        )

    def build_snapshot_for_scope(
        self,
        scope: ResearchScopeType,
        primary_symbol: str = "",
        synthetic_positions: List[SyntheticPosition] | None = None,
    ) -> tuple[PortfolioSnapshot | None, List[str]]:
        warnings: List[str] = []
        if scope == ResearchScopeType.SINGLE_TICKER:
            symbol = str(primary_symbol or "").strip().upper()
            if not symbol:
                warnings.append("Ticker is required")
                return None, warnings
            pos = PositionItem(
                symbol=symbol,
                sec_type="STK",
                currency="USD",
                quantity=1.0,
                avg_cost=None,
                market_price=None,
                market_value=100.0,
                unrealized_pnl=None,
                weight=1.0,
                base_market_value=100.0,
                instrument_id=build_instrument_id(
                    provider="research",
                    symbol=symbol,
                    sec_type="STK",
                    exchange="SMART",
                    currency="USD",
                ),
                display_symbol=symbol,
                exchange="SMART",
                provider="research",
            )
            snapshot = PortfolioSnapshot(
                timestamp=now_utc(),
                base_currency=self.base_currency,
                account_summary={},
                positions=[pos],
                total_market_value=100.0,
                total_cash=0.0,
                net_liquidation=100.0,
                warnings=[],
            )
            return snapshot, warnings

        if scope == ResearchScopeType.SYNTHETIC_PORTFOLIO:
            positions = [p for p in list(synthetic_positions or []) if str(p.symbol or "").strip()]
            if not positions:
                warnings.append("Synthetic portfolio is empty")
                return None, warnings
            total_weight = sum(float(p.weight) for p in positions)
            if total_weight <= 0:
                warnings.append("Synthetic weights must not all be zero")
                return None, warnings
            items: List[PositionItem] = []
            total_value = 100.0
            for pos in positions:
                symbol = normalize_symbol(pos.symbol)
                norm_weight = float(pos.weight) / total_weight
                items.append(
                    PositionItem(
                        symbol=symbol,
                        sec_type=pos.sec_type or "STK",
                        currency=pos.currency or "USD",
                        quantity=norm_weight,
                        avg_cost=None,
                        market_price=None,
                        market_value=total_value * norm_weight,
                        unrealized_pnl=None,
                        weight=norm_weight,
                        base_market_value=total_value * norm_weight,
                        instrument_id=pos.resolved_instrument_id(symbol=symbol),
                        display_symbol=pos.resolved_display_symbol(symbol=symbol),
                        exchange=pos.exchange,
                        primary_exchange=pos.primary_exchange,
                        provider=pos.provider or "research",
                        provider_id=pos.provider_id,
                    )
                )
            snapshot = PortfolioSnapshot(
                timestamp=now_utc(),
                base_currency=self.base_currency,
                account_summary={},
                positions=items,
                total_market_value=total_value,
                total_cash=0.0,
                net_liquidation=total_value,
                warnings=[],
            )
            return snapshot, warnings

        warnings.append("Research scope is not configured")
        return None, warnings


def select_data_provider(
    context: AppDataContext,
    portfolio_provider: PortfolioDataProvider,
    research_provider: ResearchDataProvider,
) -> AppDataProvider:
    if context.app_mode == AppMode.RESEARCH:
        return research_provider
    return portfolio_provider
