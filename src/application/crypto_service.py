from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, datetime, time
from typing import Iterable

from src.models.crypto import (
    CryptoBasketConstituent,
    CryptoComparisonRecord,
    CryptoDexLiquiditySummary,
    CryptoFlowSummaryRecord,
    CryptoNarrativeBasketRecord,
    CryptoPortfolioConstituentRecord,
    CryptoPortfolioNarrativeExposureRecord,
    CryptoPortfolioPoint,
    CryptoSyntheticPortfolioRecord,
    CryptoSyntheticPortfolioRequest,
    CryptoSyntheticPositionRequest,
    CryptoScreenerRequest,
    CryptoTokenRecord,
    CryptoWorkspaceResult,
)
from src.services.crypto_adapters import CoinGeckoAdapter, GeckoTerminalAdapter


_NARRATIVE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "layer 1": ("layer 1", "layer-1", "l1"),
    "layer 2": ("layer 2", "layer-2", "l2"),
    "layer 3": ("layer 3", "layer-3", "l3"),
    "defi": ("defi", "decentralized finance"),
    "ai": ("ai", "artificial intelligence"),
    "depin": ("depin",),
    "gaming": ("gaming", "gamefi"),
    "meme": ("meme", "memecoin"),
}

_FALLBACK_LAYER_1_IDS = {
    "algorand",
    "avalanche-2",
    "bitcoin",
    "bitcoin-cash",
    "cardano",
    "ethereum",
    "litecoin",
    "near",
    "polkadot",
    "ripple",
    "solana",
    "stellar",
    "sui",
    "toncoin",
    "tron",
}

_FALLBACK_LAYER_2_IDS = {
    "arbitrum",
    "immutable-x",
    "mantle",
    "optimism",
    "polygon-ecosystem-token",
    "starknet",
    "zksync",
}

_FALLBACK_LAYER_3_IDS = {
    "cartesi",
    "degen-base",
    "orbs",
}

_STABLECOIN_SYMBOLS = {
    "dai",
    "fdusd",
    "frax",
    "gusd",
    "pyusd",
    "rlusd",
    "tusd",
    "usdc",
    "usdd",
    "usde",
    "usdp",
    "usds",
    "usdt",
    "usd1",
}


class CryptoService:
    def __init__(
        self,
        *,
        market_adapter: CoinGeckoAdapter,
        dex_adapter: GeckoTerminalAdapter,
    ) -> None:
        self.market_adapter = market_adapter
        self.dex_adapter = dex_adapter

    def get_workspace(self, request: CryptoScreenerRequest) -> CryptoWorkspaceResult:
        fetch_limit = min(max(request.limit * 4, 120), 250)
        rows = (
            self.market_adapter.search_tokens(
                request.query,
                limit=fetch_limit,
                force_refresh=request.force_refresh,
            )
            if request.query.strip()
            else self.market_adapter.list_tokens(
                limit=fetch_limit,
                force_refresh=request.force_refresh,
            )
        )

        warnings: list[str] = []
        network_map = self._safe_network_map(force_refresh=request.force_refresh, warnings=warnings)
        enriched_rows = [self._attach_network(row, network_map) for row in rows if row.token_id]
        token_index = {row.token_id: row for row in enriched_rows}

        narratives = self._load_narratives(
            force_refresh=request.force_refresh,
            token_index=token_index,
            warnings=warnings,
        )

        visible_rows = [
            self._annotate_token(row, request, narratives)
            for row in enriched_rows
            if self._matches_filters(row, request, narratives)
        ]
        visible_rows.sort(key=lambda row: self._sort_key(row, request.sort_by))
        visible_rows = visible_rows[: max(1, min(request.limit, 80))]

        if not visible_rows:
            warnings.append("No tokens matched the current crypto screen.")

        return CryptoWorkspaceResult(
            tokens=visible_rows,
            narratives=narratives,
            warnings=warnings,
        )

    def get_token_detail(self, token_id: str, *, force_refresh: bool = False) -> CryptoTokenRecord | None:
        detail = self.market_adapter.get_token(token_id, force_refresh=force_refresh)
        if detail is None:
            return None
        network_map = self._safe_network_map(force_refresh=force_refresh, warnings=[])
        attached = self._attach_network(detail, network_map)
        narratives = self._load_narratives(
            force_refresh=force_refresh,
            token_index={attached.token_id: attached},
            warnings=[],
        )
        return self._annotate_token(attached, CryptoScreenerRequest(), narratives)

    def get_price_history(
        self,
        token_id: str,
        *,
        days: int = 30,
        force_refresh: bool = False,
    ):
        return self.market_adapter.get_price_history(
            token_id,
            days=days,
            force_refresh=force_refresh,
        )

    def get_dex_liquidity(
        self,
        token_id: str,
        *,
        force_refresh: bool = False,
    ) -> CryptoDexLiquiditySummary | None:
        detail = self.get_token_detail(token_id, force_refresh=force_refresh)
        if detail is None:
            return None
        try:
            return self.dex_adapter.get_liquidity_summary(detail, force_refresh=force_refresh)
        except Exception as exc:
            return CryptoDexLiquiditySummary(
                token_id=detail.token_id,
                lookup_strategy="failed",
                warnings=[f"DEX liquidity lookup failed: {exc}"],
                source_provider="gamma",
                retrieved_at=detail.retrieved_at,
                origin="gamma.crypto.liquidity",
                transformation_note="Gamma returns an empty liquidity summary when the upstream DEX lookup fails.",
            )

    def get_flow_summary(
        self,
        token_id: str,
        *,
        force_refresh: bool = False,
    ) -> CryptoFlowSummaryRecord | None:
        detail = self.get_token_detail(token_id, force_refresh=force_refresh)
        if detail is None:
            return None
        liquidity = self.get_dex_liquidity(token_id, force_refresh=force_refresh)
        if liquidity is None:
            return None
        return self._build_flow_summary(detail, liquidity)

    def get_comparison(
        self,
        token_id: str,
        *,
        target_token_id: str | None = None,
        basket_id: str | None = None,
        force_refresh: bool = False,
    ) -> CryptoComparisonRecord | None:
        subject = self.get_token_detail(token_id, force_refresh=force_refresh)
        if subject is None:
            return None

        if target_token_id:
            target = self.get_token_detail(target_token_id, force_refresh=force_refresh)
            if target is None:
                return None
            return self._compare_tokens(subject, target)

        basket_reference = self._resolve_basket_reference(
            subject,
            basket_id=basket_id,
            force_refresh=force_refresh,
        )
        if basket_reference is not None:
            basket, members = basket_reference
            return self._compare_against_basket(subject, basket, members)

        if subject.token_id != "bitcoin":
            bitcoin = self.get_token_detail("bitcoin", force_refresh=force_refresh)
            if bitcoin is not None:
                return self._compare_tokens(subject, bitcoin)
        return None

    def analyze_synthetic_portfolio(
        self,
        request: CryptoSyntheticPortfolioRequest,
    ) -> CryptoSyntheticPortfolioRecord | None:
        positions = [item for item in request.positions if item.identifier.strip() and item.weight > 0]
        if not positions:
            return None

        warnings: list[str] = []
        universe = self._build_token_universe(force_refresh=request.force_refresh, limit=250, warnings=warnings)
        if not universe:
            return None

        resolved_positions: list[tuple[CryptoSyntheticPositionRequest, CryptoTokenRecord]] = []
        for position in positions:
            token = self._resolve_position_identifier(
                position.identifier,
                universe,
                force_refresh=request.force_refresh,
            )
            if token is None:
                warnings.append(f"Could not resolve crypto identifier `{position.identifier}` into a token.")
                continue
            resolved_positions.append((position, token))

        if not resolved_positions:
            return None

        benchmark_token = self.get_token_detail(
            request.benchmark_token_id or "bitcoin",
            force_refresh=request.force_refresh,
        )
        if benchmark_token is None:
            benchmark_token = resolved_positions[0][1]
            warnings.append("Benchmark token lookup failed, so Gamma fell back to the first resolved basket constituent.")

        normalized_weights = _normalize_weights([item.weight for item, _ in resolved_positions])
        if not normalized_weights:
            return None

        histories: list[list] = []
        constituents: list[CryptoPortfolioConstituentRecord] = []
        retrieved_marks: list[datetime | None] = [benchmark_token.retrieved_at]
        for (position, token), normalized_weight in zip(resolved_positions, normalized_weights, strict=False):
            history = self.get_price_history(
                token.token_id,
                days=request.lookback_days,
                force_refresh=request.force_refresh,
            )
            if len(history) < 2:
                warnings.append(f"History coverage is too thin to include `{token.symbol.upper()}` in the synthetic basket.")
                continue
            histories.append(history)
            constituents.append(
                CryptoPortfolioConstituentRecord(
                    token_id=token.token_id,
                    symbol=token.symbol.upper(),
                    name=token.name,
                    input_weight=position.weight,
                    normalized_weight=normalized_weight,
                    market_cap=token.market_cap,
                    turnover_ratio_24h=token.turnover_ratio_24h,
                    narrative_labels=list(token.narrative_labels),
                    layer_bucket=token.layer_bucket,
                )
            )
            retrieved_marks.extend([token.retrieved_at, history[-1].retrieved_at if history else token.retrieved_at])

        if not constituents:
            return None

        normalized_final_weights = _normalize_weights([item.normalized_weight for item in constituents])
        constituents = [
            replace(item, normalized_weight=weight)
            for item, weight in zip(constituents, normalized_final_weights, strict=False)
        ]

        benchmark_history = self.get_price_history(
            benchmark_token.token_id,
            days=request.lookback_days,
            force_refresh=request.force_refresh,
        )
        if len(benchmark_history) < 2:
            warnings.append("Benchmark history coverage is thin, so Gamma could not build the synthetic portfolio chart.")
            return None
        retrieved_marks.append(benchmark_history[-1].retrieved_at if benchmark_history else benchmark_token.retrieved_at)

        timeline = self._portfolio_timeline(
            histories=histories[: len(constituents)],
            weights=[item.normalized_weight for item in constituents],
            benchmark_history=benchmark_history,
        )
        if timeline is None:
            warnings.append("Gamma could not align the selected token histories onto a common daily timeline.")
            return None
        portfolio_points, benchmark_points = timeline

        portfolio_returns = _series_returns(portfolio_points)
        portfolio_return = ((portfolio_points[-1].value - 1.0) * 100.0) if portfolio_points else None
        benchmark_return = ((benchmark_points[-1].value - 1.0) * 100.0) if benchmark_points else None
        relative_return = _gap(portfolio_return, benchmark_return)
        volatility_estimate = _annualized_volatility(portfolio_returns, periods_per_year=365) if portfolio_returns else None
        annualized_volatility = (volatility_estimate * 100.0) if volatility_estimate is not None else None
        weighted_turnover = _weighted_average(
            [item.turnover_ratio_24h for item in constituents],
            [item.normalized_weight for item in constituents],
        )
        weighted_market_cap = sum(
            (item.market_cap or 0.0) * item.normalized_weight
            for item in constituents
        ) or None
        concentration_hhi = sum(item.normalized_weight * item.normalized_weight for item in constituents)
        effective_positions = (1.0 / concentration_hhi) if concentration_hhi > 0 else None
        narrative_exposures = self._portfolio_narrative_exposures(constituents)
        summary = self._portfolio_summary(
            len(constituents),
            benchmark_token.name,
            portfolio_return,
            benchmark_return,
            weighted_turnover,
            effective_positions,
        )

        return CryptoSyntheticPortfolioRecord(
            lookback_days=request.lookback_days,
            benchmark_token_id=benchmark_token.token_id,
            benchmark_label=benchmark_token.name,
            constituents=constituents,
            narrative_exposures=narrative_exposures,
            portfolio_points=portfolio_points,
            benchmark_points=benchmark_points,
            cumulative_return_pct=portfolio_return,
            benchmark_return_pct=benchmark_return,
            relative_return_pct=relative_return,
            annualized_volatility_pct=annualized_volatility,
            weighted_turnover_ratio_24h=weighted_turnover,
            weighted_market_cap=weighted_market_cap,
            concentration_hhi=concentration_hhi,
            effective_positions=effective_positions,
            summary=summary,
            warnings=warnings,
            source_provider="gamma",
            retrieved_at=_max_datetime(*retrieved_marks),
            origin="gamma.crypto.synthetic_portfolio",
            transformation_note=(
                "Gamma synthetic crypto baskets normalize daily CoinGecko price histories to a shared base value and combine them using user-submitted weights."
            ),
        )

    def _resolve_basket_reference(
        self,
        subject: CryptoTokenRecord,
        *,
        basket_id: str | None,
        force_refresh: bool,
    ) -> tuple[CryptoNarrativeBasketRecord, list[CryptoTokenRecord]] | None:
        fetch_limit = 180
        network_map = self._safe_network_map(force_refresh=force_refresh, warnings=[])
        universe = [
            self._attach_network(row, network_map)
            for row in self.market_adapter.list_tokens(limit=fetch_limit, force_refresh=force_refresh)
            if row.token_id
        ]
        token_index = {row.token_id: row for row in universe}
        narratives = self._load_narratives(
            force_refresh=force_refresh,
            token_index=token_index,
            warnings=[],
        )
        if not narratives:
            return None

        basket: CryptoNarrativeBasketRecord | None = None
        if basket_id:
            basket = next((row for row in narratives if row.basket_id == basket_id), None)
        else:
            basket = self._default_basket_for_subject(subject, narratives)
        if basket is None:
            return None

        members: list[CryptoTokenRecord] = []
        for constituent in basket.top_tokens:
            candidate = token_index.get(constituent.token_id)
            if candidate is not None:
                members.append(candidate)
                continue
            detail = self.get_token_detail(constituent.token_id, force_refresh=force_refresh)
            if detail is not None:
                members.append(detail)

        return (basket, members)

    def _default_basket_for_subject(
        self,
        subject: CryptoTokenRecord,
        narratives: list[CryptoNarrativeBasketRecord],
    ) -> CryptoNarrativeBasketRecord | None:
        for basket in narratives:
            if any(row.token_id == subject.token_id for row in basket.top_tokens):
                return basket
        subject_labels = {label.lower() for label in self._narrative_labels_for_token(subject, narratives)}
        for basket in narratives:
            if basket.label.lower() in subject_labels:
                return basket
        return narratives[0] if narratives else None

    def _compare_tokens(
        self,
        subject: CryptoTokenRecord,
        target: CryptoTokenRecord,
    ) -> CryptoComparisonRecord:
        shared_categories = sorted(set(subject.categories) & set(target.categories))
        price_gap_24h = _gap(subject.price_change_pct_24h, target.price_change_pct_24h)
        price_gap_7d = _gap(subject.price_change_pct_7d, target.price_change_pct_7d)
        price_gap_30d = _gap(subject.price_change_pct_30d, target.price_change_pct_30d)
        turnover_gap = _gap(subject.turnover_ratio_24h, target.turnover_ratio_24h)
        market_cap_ratio = _safe_ratio(subject.market_cap, target.market_cap)
        summary = self._token_comparison_summary(subject, target, market_cap_ratio, price_gap_7d, turnover_gap)
        return CryptoComparisonRecord(
            subject_token_id=subject.token_id,
            target_kind="token",
            target_id=target.token_id,
            target_label=target.name,
            shared_categories=shared_categories,
            subject_price_change_pct_24h=subject.price_change_pct_24h,
            target_price_change_pct_24h=target.price_change_pct_24h,
            price_gap_pct_24h=price_gap_24h,
            subject_price_change_pct_7d=subject.price_change_pct_7d,
            target_price_change_pct_7d=target.price_change_pct_7d,
            price_gap_pct_7d=price_gap_7d,
            subject_price_change_pct_30d=subject.price_change_pct_30d,
            target_price_change_pct_30d=target.price_change_pct_30d,
            price_gap_pct_30d=price_gap_30d,
            subject_market_cap=subject.market_cap,
            target_market_cap=target.market_cap,
            market_cap_ratio=market_cap_ratio,
            subject_turnover_ratio_24h=subject.turnover_ratio_24h,
            target_turnover_ratio_24h=target.turnover_ratio_24h,
            turnover_gap=turnover_gap,
            summary=summary,
            source_provider="gamma",
            retrieved_at=_max_datetime(subject.retrieved_at, target.retrieved_at),
            origin="gamma.crypto.comparison.token",
            transformation_note="Gamma token comparisons summarize relative size, momentum, turnover, and category overlap from normalized CoinGecko records.",
        )

    def _compare_against_basket(
        self,
        subject: CryptoTokenRecord,
        basket: CryptoNarrativeBasketRecord,
        members: list[CryptoTokenRecord],
    ) -> CryptoComparisonRecord:
        weights = [max(member.market_cap or 0.0, 0.0) for member in members]
        if not any(weight > 0 for weight in weights):
            weights = [1.0 for _ in members]
        shared_categories = [
            basket.label
            for label in self._narrative_labels_for_token(subject, [basket])
            if label == basket.label
        ]
        basket_market_cap = basket.market_cap if basket.market_cap is not None else _sum_nullable(
            member.market_cap for member in members
        )
        basket_turnover = _weighted_average(
            [member.turnover_ratio_24h for member in members],
            weights,
        )
        basket_change_24h = _weighted_average(
            [member.price_change_pct_24h for member in members],
            weights,
        )
        basket_change_7d = _weighted_average(
            [member.price_change_pct_7d for member in members],
            weights,
        )
        basket_change_30d = _weighted_average(
            [member.price_change_pct_30d for member in members],
            weights,
        )
        price_gap_24h = _gap(subject.price_change_pct_24h, basket_change_24h)
        price_gap_7d = _gap(subject.price_change_pct_7d, basket_change_7d)
        price_gap_30d = _gap(subject.price_change_pct_30d, basket_change_30d)
        turnover_gap = _gap(subject.turnover_ratio_24h, basket_turnover)
        market_cap_ratio = _safe_ratio(subject.market_cap, basket_market_cap)
        summary = self._basket_comparison_summary(subject, basket, market_cap_ratio, price_gap_30d, turnover_gap)
        return CryptoComparisonRecord(
            subject_token_id=subject.token_id,
            target_kind="basket",
            target_id=basket.basket_id,
            target_label=basket.label,
            shared_categories=shared_categories,
            subject_price_change_pct_24h=subject.price_change_pct_24h,
            target_price_change_pct_24h=basket_change_24h,
            price_gap_pct_24h=price_gap_24h,
            subject_price_change_pct_7d=subject.price_change_pct_7d,
            target_price_change_pct_7d=basket_change_7d,
            price_gap_pct_7d=price_gap_7d,
            subject_price_change_pct_30d=subject.price_change_pct_30d,
            target_price_change_pct_30d=basket_change_30d,
            price_gap_pct_30d=price_gap_30d,
            subject_market_cap=subject.market_cap,
            target_market_cap=basket_market_cap,
            market_cap_ratio=market_cap_ratio,
            subject_turnover_ratio_24h=subject.turnover_ratio_24h,
            target_turnover_ratio_24h=basket_turnover,
            turnover_gap=turnover_gap,
            summary=summary,
            source_provider="gamma",
            retrieved_at=_max_datetime(subject.retrieved_at, basket.retrieved_at, *(member.retrieved_at for member in members)),
            origin="gamma.crypto.comparison.basket",
            transformation_note="Gamma basket comparisons use market-cap-weighted aggregates across the narrative basket's visible top tokens.",
        )

    def _load_narratives(
        self,
        *,
        force_refresh: bool,
        token_index: dict[str, CryptoTokenRecord] | None,
        warnings: list[str] | None,
    ) -> list[CryptoNarrativeBasketRecord]:
        try:
            narratives = self.market_adapter.get_narrative_baskets(
                force_refresh=force_refresh,
                token_index=token_index,
            )
        except Exception as exc:
            if warnings is not None:
                warnings.append(f"Narrative basket lookup failed: {exc}")
            narratives = []
        if narratives:
            return narratives
        fallback = self._build_fallback_narratives(token_index)
        if fallback and warnings is not None:
            warnings.append("Gamma fell back to internal layer baskets because the upstream narrative lookup was unavailable.")
        return fallback

    def _build_fallback_narratives(
        self,
        token_index: dict[str, CryptoTokenRecord] | None,
    ) -> list[CryptoNarrativeBasketRecord]:
        if not token_index:
            return []

        bucket_map: dict[str, list[CryptoTokenRecord]] = {"Layer 1": [], "Layer 2": [], "Layer 3": []}
        for token in token_index.values():
            bucket = self._infer_layer_bucket(token, [])
            if bucket in bucket_map:
                bucket_map[bucket].append(token)

        descriptions = {
            "Layer 1": "Gamma fallback basket for the largest core crypto assets when upstream narrative categories are unavailable.",
            "Layer 2": "Gamma fallback basket for secondary infrastructure and mid-cap protocol assets when upstream narrative categories are unavailable.",
            "Layer 3": "Gamma fallback basket for smaller or more exploratory crypto assets when upstream narrative categories are unavailable.",
        }

        records: list[CryptoNarrativeBasketRecord] = []
        for label in ("Layer 1", "Layer 2", "Layer 3"):
            members = sorted(
                bucket_map[label],
                key=lambda item: (-(item.market_cap or 0.0), item.market_cap_rank or 999_999, item.name.lower()),
            )
            if not members:
                continue
            weights = [max(member.market_cap or 0.0, 0.0) for member in members]
            if not any(weight > 0 for weight in weights):
                weights = [1.0 for _ in members]
            records.append(
                CryptoNarrativeBasketRecord(
                    basket_id=_normalize_text(label).replace(" ", "-"),
                    label=label,
                    description=descriptions[label],
                    market_cap=_sum_nullable(member.market_cap for member in members),
                    market_cap_change_pct_24h=_weighted_average(
                        [member.market_cap_change_pct_24h for member in members],
                        weights,
                    ),
                    volume_24h=_sum_nullable(member.total_volume for member in members),
                    top_tokens=[
                        CryptoBasketConstituent(
                            token_id=member.token_id,
                            name=member.name,
                            symbol=member.symbol.upper(),
                            image_url=member.image_url,
                        )
                        for member in members
                    ],
                    source_provider="gamma",
                    retrieved_at=_max_datetime(*(member.retrieved_at for member in members)),
                    origin="gamma.crypto.narratives.fallback",
                    transformation_note="Gamma fallback layer baskets are heuristic groupings used when upstream narrative categories are unavailable.",
                )
            )
        return records

    def _build_token_universe(
        self,
        *,
        force_refresh: bool,
        limit: int,
        warnings: list[str],
    ) -> list[CryptoTokenRecord]:
        network_map = self._safe_network_map(force_refresh=force_refresh, warnings=warnings)
        rows = [
            self._attach_network(row, network_map)
            for row in self.market_adapter.list_tokens(limit=limit, force_refresh=force_refresh)
            if row.token_id
        ]
        narratives = self._load_narratives(
            force_refresh=force_refresh,
            token_index={row.token_id: row for row in rows},
            warnings=warnings,
        )
        return [self._annotate_token(row, CryptoScreenerRequest(), narratives) for row in rows]

    def _resolve_position_identifier(
        self,
        identifier: str,
        universe: list[CryptoTokenRecord],
        *,
        force_refresh: bool,
    ) -> CryptoTokenRecord | None:
        needle = _normalize_text(identifier)
        if not needle:
            return None

        by_token_id = next((row for row in universe if _normalize_text(row.token_id) == needle), None)
        if by_token_id is not None:
            return by_token_id

        by_symbol = next((row for row in universe if _normalize_text(row.symbol) == needle), None)
        if by_symbol is not None:
            return by_symbol

        by_name = next((row for row in universe if _normalize_text(row.name) == needle), None)
        if by_name is not None:
            return by_name

        search_rows = self.market_adapter.search_tokens(identifier, limit=8, force_refresh=force_refresh)
        if not search_rows:
            return None
        network_map = self._safe_network_map(force_refresh=force_refresh, warnings=[])
        attached = [self._attach_network(row, network_map) for row in search_rows if row.token_id]
        narratives = self._load_narratives(
            force_refresh=force_refresh,
            token_index={row.token_id: row for row in attached},
            warnings=[],
        )
        annotated = [self._annotate_token(row, CryptoScreenerRequest(), narratives) for row in attached]
        return annotated[0] if annotated else None

    def _build_flow_summary(
        self,
        token: CryptoTokenRecord,
        liquidity: CryptoDexLiquiditySummary,
    ) -> CryptoFlowSummaryRecord:
        reserve_shares = _normalized_shares([pool.reserve_usd for pool in liquidity.pools])
        volume_shares = _normalized_shares([pool.volume_24h for pool in liquidity.pools])
        total_trades = liquidity.total_buys_24h + liquidity.total_sells_24h
        total_participants = liquidity.total_buyers_24h + liquidity.total_sellers_24h
        buy_pressure_pct = (
            (liquidity.total_buys_24h / total_trades) * 100.0
            if total_trades > 0
            else None
        )
        dex_volume_share = _safe_ratio(liquidity.total_volume_24h, token.total_volume)
        reserve_to_market_cap = _safe_ratio(liquidity.total_reserve_usd, token.market_cap)
        reserve_volume_ratio = _safe_ratio(liquidity.total_reserve_usd, liquidity.total_volume_24h)
        top_pool_reserve_share = reserve_shares[0] if reserve_shares else None
        top_pool_volume_share = volume_shares[0] if volume_shares else None
        buy_sell_ratio = _safe_ratio(float(liquidity.total_buys_24h), float(max(liquidity.total_sells_24h, 1)))
        participant_balance_ratio = _safe_ratio(float(liquidity.total_buyers_24h), float(max(liquidity.total_sellers_24h, 1)))

        if reserve_volume_ratio is None:
            slippage_proxy_label = "unknown"
        elif reserve_volume_ratio >= 4.0:
            slippage_proxy_label = "deep"
        elif reserve_volume_ratio >= 1.8:
            slippage_proxy_label = "workable"
        elif reserve_volume_ratio >= 0.9:
            slippage_proxy_label = "thin"
        else:
            slippage_proxy_label = "fragile"

        if top_pool_reserve_share is None:
            concentration_label = "unknown"
        elif top_pool_reserve_share >= 0.72:
            concentration_label = "highly concentrated"
        elif top_pool_reserve_share >= 0.48:
            concentration_label = "moderately concentrated"
        else:
            concentration_label = "distributed"

        if buy_pressure_pct is None:
            flow_signal = "unavailable"
        elif buy_pressure_pct >= 58.0:
            flow_signal = "accumulation"
        elif buy_pressure_pct <= 42.0:
            flow_signal = "distribution"
        else:
            flow_signal = "balanced"

        summary = self._flow_summary_text(
            token=token,
            dex_volume_share=dex_volume_share,
            slippage_proxy_label=slippage_proxy_label,
            concentration_label=concentration_label,
            flow_signal=flow_signal,
            buy_pressure_pct=buy_pressure_pct,
        )
        return CryptoFlowSummaryRecord(
            token_id=token.token_id,
            pool_count=len(liquidity.pools),
            matched_networks=list(liquidity.matched_networks),
            total_reserve_usd=liquidity.total_reserve_usd,
            total_volume_24h=liquidity.total_volume_24h,
            dex_volume_share_of_total_volume=dex_volume_share,
            reserve_to_market_cap_ratio=reserve_to_market_cap,
            top_pool_reserve_share=top_pool_reserve_share,
            top_pool_volume_share=top_pool_volume_share,
            buy_pressure_pct=buy_pressure_pct,
            active_trader_proxy_24h=total_participants,
            buy_sell_ratio=buy_sell_ratio,
            participant_balance_ratio=participant_balance_ratio,
            reserve_volume_ratio_24h=reserve_volume_ratio,
            slippage_proxy_label=slippage_proxy_label,
            liquidity_concentration_label=concentration_label,
            flow_signal_label=flow_signal,
            summary=summary,
            warnings=list(liquidity.warnings),
            source_provider="gamma",
            retrieved_at=_max_datetime(token.retrieved_at, liquidity.retrieved_at),
            origin="gamma.crypto.flow_summary",
            transformation_note=(
                "Gamma flow summaries are first-pass DEX and participation proxies built from GeckoTerminal pool reserve, volume, buy/sell, and buyer/seller counts layered onto normalized token metadata."
            ),
        )

    def _flow_summary_text(
        self,
        *,
        token: CryptoTokenRecord,
        dex_volume_share: float | None,
        slippage_proxy_label: str,
        concentration_label: str,
        flow_signal: str,
        buy_pressure_pct: float | None,
    ) -> str:
        market_share_text = "DEX share versus headline spot volume is unclear"
        if dex_volume_share is not None:
            if dex_volume_share >= 0.55:
                market_share_text = "DEX turnover is carrying a large share of the token's reported spot activity"
            elif dex_volume_share >= 0.2:
                market_share_text = "DEX turnover is a meaningful but not dominant slice of reported spot activity"
            else:
                market_share_text = "DEX turnover is only a small slice of reported spot activity"
        pressure_text = "buy and sell counts are balanced"
        if buy_pressure_pct is not None:
            if buy_pressure_pct >= 58.0:
                pressure_text = f"buy-side flow is dominant at roughly {buy_pressure_pct:.1f}% of tracked trades"
            elif buy_pressure_pct <= 42.0:
                pressure_text = f"sell-side flow is dominant with buys only {buy_pressure_pct:.1f}% of tracked trades"
        return (
            f"{token.name} shows {flow_signal} flow; liquidity looks {concentration_label} and {slippage_proxy_label}; "
            f"{market_share_text}; {pressure_text}."
        )

    def _portfolio_timeline(
        self,
        *,
        histories: list[list],
        weights: list[float],
        benchmark_history: list,
    ) -> tuple[list[CryptoPortfolioPoint], list[CryptoPortfolioPoint]] | None:
        series_maps: list[dict[date, float]] = []
        for history in histories:
            mapping: dict[date, float] = {}
            for point in history:
                mapping[point.timestamp.date()] = point.price
            if len(mapping) < 2:
                return None
            series_maps.append(mapping)

        benchmark_map: dict[date, float] = {}
        for point in benchmark_history:
            benchmark_map[point.timestamp.date()] = point.price
        if len(benchmark_map) < 2:
            return None

        common_dates = set(benchmark_map.keys())
        for mapping in series_maps:
            common_dates &= set(mapping.keys())
        ordered_dates = sorted(common_dates)
        if len(ordered_dates) < 2:
            return None

        base_values = [mapping[ordered_dates[0]] for mapping in series_maps]
        benchmark_base = benchmark_map[ordered_dates[0]]
        if any(value <= 0 for value in base_values) or benchmark_base <= 0:
            return None

        portfolio_points: list[CryptoPortfolioPoint] = []
        benchmark_points: list[CryptoPortfolioPoint] = []
        for current_date in ordered_dates:
            portfolio_value = 0.0
            for mapping, base_value, weight in zip(series_maps, base_values, weights, strict=False):
                price = mapping.get(current_date)
                if price is None or base_value <= 0:
                    return None
                portfolio_value += (price / base_value) * weight
            benchmark_value = benchmark_map[current_date] / benchmark_base
            portfolio_points.append(
                CryptoPortfolioPoint(
                    timestamp=datetime.combine(current_date, time.min),
                    value=portfolio_value,
                )
            )
            benchmark_points.append(
                CryptoPortfolioPoint(
                    timestamp=datetime.combine(current_date, time.min),
                    value=benchmark_value,
                )
            )
        return portfolio_points, benchmark_points

    def _portfolio_narrative_exposures(
        self,
        constituents: list[CryptoPortfolioConstituentRecord],
    ) -> list[CryptoPortfolioNarrativeExposureRecord]:
        exposure_map: dict[str, float] = {}
        count_map: dict[str, int] = {}
        for item in constituents:
            labels = list(item.narrative_labels)
            if not labels and item.layer_bucket:
                labels = [item.layer_bucket]
            labels = labels or ["Unclassified"]
            share = item.normalized_weight / len(labels)
            for label in labels:
                exposure_map[label] = exposure_map.get(label, 0.0) + share
                count_map[label] = count_map.get(label, 0) + 1
        exposures = [
            CryptoPortfolioNarrativeExposureRecord(
                label=label,
                normalized_weight=weight,
                constituent_count=count_map[label],
            )
            for label, weight in exposure_map.items()
        ]
        exposures.sort(key=lambda item: (-item.normalized_weight, item.label.lower()))
        return exposures

    def _portfolio_summary(
        self,
        constituent_count: int,
        benchmark_label: str,
        portfolio_return: float | None,
        benchmark_return: float | None,
        weighted_turnover: float | None,
        effective_positions: float | None,
    ) -> str:
        performance_text = "performance versus the benchmark is unclear"
        relative_return = _gap(portfolio_return, benchmark_return)
        if relative_return is not None:
            if relative_return >= 3.0:
                performance_text = f"the basket is ahead of {benchmark_label} by {relative_return:.1f} pts"
            elif relative_return <= -3.0:
                performance_text = f"the basket trails {benchmark_label} by {abs(relative_return):.1f} pts"
            else:
                performance_text = f"the basket is roughly in line with {benchmark_label}"
        turnover_text = (
            f"weighted 24H turnover is {weighted_turnover:.2f}x"
            if weighted_turnover is not None
            else "weighted turnover is unavailable"
        )
        structure_text = (
            f"effective positions are {effective_positions:.1f}"
            if effective_positions is not None
            else "concentration could not be estimated"
        )
        return (
            f"Synthetic basket spans {constituent_count} names; {performance_text}; "
            f"{turnover_text}; {structure_text}."
        )

    def _safe_network_map(self, *, force_refresh: bool, warnings: list[str]) -> dict[str, str]:
        try:
            return self.dex_adapter.get_network_map(force_refresh=force_refresh)
        except Exception as exc:
            if warnings is not None:
                warnings.append(f"GeckoTerminal network map lookup failed: {exc}")
            return {}

    def _attach_network(
        self,
        token: CryptoTokenRecord,
        network_map: dict[str, str],
    ) -> CryptoTokenRecord:
        geckoterminal_network = network_map.get(token.asset_platform_id or "")
        return replace(token, geckoterminal_network=geckoterminal_network)

    def _matches_filters(
        self,
        token: CryptoTokenRecord,
        request: CryptoScreenerRequest,
        narratives: list[CryptoNarrativeBasketRecord],
    ) -> bool:
        if request.min_market_cap is not None and (token.market_cap or 0.0) < request.min_market_cap:
            return False
        if request.min_volume is not None and (token.total_volume or 0.0) < request.min_volume:
            return False
        if request.min_turnover_ratio is not None and (token.turnover_ratio_24h or 0.0) < request.min_turnover_ratio:
            return False
        if request.chain and not self._chain_matches(token, request.chain):
            return False
        if request.narrative and not self._narrative_matches(token, request.narrative, narratives):
            return False
        return True

    def _annotate_token(
        self,
        token: CryptoTokenRecord,
        request: CryptoScreenerRequest,
        narratives: list[CryptoNarrativeBasketRecord],
    ) -> CryptoTokenRecord:
        screen_score = self._screen_score(token)
        narrative_labels = self._narrative_labels_for_token(token, narratives)
        layer_bucket = self._infer_layer_bucket(token, narrative_labels)
        rationale_parts = [
            f"turnover {(token.turnover_ratio_24h or 0.0):.2f}x",
            f"24H volume ${_compact_number(token.total_volume)}",
        ]
        if token.price_change_pct_7d is not None:
            rationale_parts.append(f"7D {token.price_change_pct_7d:+.1f}%")
        if token.fdv_premium_ratio is not None:
            rationale_parts.append(f"FDV premium {token.fdv_premium_ratio:+.1f}x")
        if narrative_labels:
            rationale_parts.append(f"narratives {', '.join(narrative_labels[:2])}")

        note = _join_notes(
            token.transformation_note,
            "Gamma screen score combines size, liquidity, turnover, momentum, and FDV premium heuristics.",
        )
        return replace(
            token,
            narrative_labels=narrative_labels,
            layer_bucket=layer_bucket,
            screen_score=screen_score,
            screen_rationale=" | ".join(rationale_parts),
            transformation_note=note,
        )

    def _screen_score(self, token: CryptoTokenRecord) -> float:
        size_score = _scaled_log(token.market_cap, pivot=80_000_000_000.0)
        liquidity_score = _scaled_log(token.total_volume, pivot=6_000_000_000.0)
        turnover_score = min((token.turnover_ratio_24h or 0.0) / 0.25, 1.0)
        momentum_components = [
            token.price_change_pct_24h,
            token.price_change_pct_7d,
            token.price_change_pct_30d,
        ]
        momentum_values = [value for value in momentum_components if value is not None]
        momentum_score = 0.45
        if momentum_values:
            momentum_score = min(max((sum(momentum_values) / len(momentum_values) + 10.0) / 25.0, 0.0), 1.0)
        fdv_penalty = min(max(token.fdv_premium_ratio or 0.0, 0.0) / 1.75, 1.0)
        combined = (
            (size_score * 0.28)
            + (liquidity_score * 0.28)
            + (turnover_score * 0.24)
            + (momentum_score * 0.20)
            - (fdv_penalty * 0.12)
        )
        return round(max(combined, 0.0) * 100.0, 1)

    def _sort_key(self, token: CryptoTokenRecord, sort_by: str):
        if sort_by == "volume_desc":
            return (-(token.total_volume or 0.0), -(token.market_cap or 0.0), token.name.lower())
        if sort_by == "turnover_desc":
            return (-(token.turnover_ratio_24h or 0.0), -(token.total_volume or 0.0), token.name.lower())
        if sort_by == "momentum_desc":
            return (-(token.price_change_pct_30d or -999.0), -(token.price_change_pct_7d or -999.0), token.name.lower())
        if sort_by == "screen_score_desc":
            return (-(token.screen_score or 0.0), -(token.total_volume or 0.0), token.name.lower())
        if sort_by == "fdv_premium_asc":
            return ((token.fdv_premium_ratio if token.fdv_premium_ratio is not None else 9_999.0), -(token.market_cap or 0.0), token.name.lower())
        return (-(token.market_cap or 0.0), token.market_cap_rank or 9_999_999, token.name.lower())

    def _chain_matches(self, token: CryptoTokenRecord, value: str) -> bool:
        needle = _normalize_text(value)
        haystack = " ".join(
            filter(
                None,
                [
                    token.chain,
                    token.asset_platform_id,
                    token.geckoterminal_network,
                ],
            )
        )
        normalized_haystack = _normalize_text(haystack)
        return bool(needle and needle in normalized_haystack)

    def _narrative_matches(
        self,
        token: CryptoTokenRecord,
        value: str,
        narratives: list[CryptoNarrativeBasketRecord],
    ) -> bool:
        selected = _normalize_text(value)
        if not selected:
            return True
        labels = [_normalize_text(label) for label in self._narrative_labels_for_token(token, narratives)]
        return selected in labels

    def _narrative_labels_for_token(
        self,
        token: CryptoTokenRecord,
        narratives: list[CryptoNarrativeBasketRecord],
    ) -> list[str]:
        categories = [_normalize_text(item) for item in token.categories]
        labels: list[str] = []
        for basket in narratives:
            label = basket.label
            label_key = _normalize_text(label)
            if any(row.token_id == token.token_id for row in basket.top_tokens):
                labels.append(label)
                continue
            keywords = _NARRATIVE_KEYWORDS.get(label_key, (label_key,))
            if any(any(keyword in category for keyword in keywords) for category in categories):
                labels.append(label)
        return labels

    def _infer_layer_bucket(
        self,
        token: CryptoTokenRecord,
        narrative_labels: list[str],
    ) -> str | None:
        for candidate in ("Layer 1", "Layer 2", "Layer 3"):
            if candidate in narrative_labels:
                return candidate
        category_text = " ".join(token.categories)
        normalized_categories = _normalize_text(category_text)
        if "layer 3" in normalized_categories:
            return "Layer 3"
        if "layer 2" in normalized_categories:
            return "Layer 2"
        if "layer 1" in normalized_categories:
            return "Layer 1"
        if token.token_id in _FALLBACK_LAYER_1_IDS:
            return "Layer 1"
        if token.token_id in _FALLBACK_LAYER_2_IDS:
            return "Layer 2"
        if token.token_id in _FALLBACK_LAYER_3_IDS:
            return "Layer 3"
        if self._is_stablecoin_like(token):
            return "Layer 2" if (token.market_cap or 0.0) >= 1_000_000_000 else "Layer 3"
        if token.market_cap_rank is not None:
            if token.market_cap_rank <= 15:
                return "Layer 1"
            if token.market_cap_rank <= 80:
                return "Layer 2"
            if token.market_cap_rank <= 180:
                return "Layer 3"
        if token.market_cap is not None:
            if token.market_cap >= 10_000_000_000:
                return "Layer 1"
            if token.market_cap >= 1_000_000_000:
                return "Layer 2"
            if token.market_cap >= 50_000_000:
                return "Layer 3"
        return None

    def _is_stablecoin_like(self, token: CryptoTokenRecord) -> bool:
        if _normalize_text(token.symbol) in _STABLECOIN_SYMBOLS:
            return True
        name = _normalize_text(token.name)
        category_text = _normalize_text(" ".join(token.categories))
        stable_keywords = ("stablecoin", "stable coin", "usd", "tether")
        return any(keyword in name or keyword in category_text for keyword in stable_keywords)

    def _token_comparison_summary(
        self,
        subject: CryptoTokenRecord,
        target: CryptoTokenRecord,
        market_cap_ratio: float | None,
        price_gap_7d: float | None,
        turnover_gap: float | None,
    ) -> str:
        size_text = "similar in size"
        if market_cap_ratio is not None:
            if market_cap_ratio >= 1.5:
                size_text = f"{subject.name} is about {market_cap_ratio:.1f}x the size of {target.name}"
            elif market_cap_ratio <= (1 / 1.5):
                size_text = f"{subject.name} is materially smaller than {target.name}"
        momentum_text = "7D performance is broadly in line"
        if price_gap_7d is not None:
            if price_gap_7d >= 5.0:
                momentum_text = f"{subject.name} leads by {price_gap_7d:.1f} pts over 7D"
            elif price_gap_7d <= -5.0:
                momentum_text = f"{subject.name} trails by {abs(price_gap_7d):.1f} pts over 7D"
        turnover_text = "turnover is similar"
        if turnover_gap is not None:
            if turnover_gap >= 0.05:
                turnover_text = f"{subject.name} is turning over more aggressively on 24H volume"
            elif turnover_gap <= -0.05:
                turnover_text = f"{target.name} is turning over more aggressively on 24H volume"
        return f"{size_text}; {momentum_text}; {turnover_text}."

    def _basket_comparison_summary(
        self,
        subject: CryptoTokenRecord,
        basket: CryptoNarrativeBasketRecord,
        market_cap_ratio: float | None,
        price_gap_30d: float | None,
        turnover_gap: float | None,
    ) -> str:
        size_text = f"{subject.name} is smaller than the {basket.label} basket proxy"
        if market_cap_ratio is not None:
            if market_cap_ratio >= 1.0:
                size_text = f"{subject.name} is comparable to or larger than the {basket.label} basket proxy"
            elif market_cap_ratio >= 0.5:
                size_text = f"{subject.name} is a meaningful component versus the {basket.label} basket proxy"
        momentum_text = "30D performance is near the basket"
        if price_gap_30d is not None:
            if price_gap_30d >= 8.0:
                momentum_text = f"{subject.name} is outperforming the basket by {price_gap_30d:.1f} pts over 30D"
            elif price_gap_30d <= -8.0:
                momentum_text = f"{subject.name} is lagging the basket by {abs(price_gap_30d):.1f} pts over 30D"
        turnover_text = "24H turnover is in line with the basket"
        if turnover_gap is not None:
            if turnover_gap >= 0.05:
                turnover_text = f"{subject.name} is trading with hotter turnover than the basket"
            elif turnover_gap <= -0.05:
                turnover_text = f"{subject.name} is trading with softer turnover than the basket"
        return f"{size_text}; {momentum_text}; {turnover_text}."


def _scaled_log(value: float | None, *, pivot: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return min(math.log1p(value) / math.log1p(pivot), 1.0)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _gap(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _max_datetime(*values: datetime | None) -> datetime | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return max(clean)


def _weighted_average(values: list[float | None], weights: list[float]) -> float | None:
    pairs = [
        (value, weight)
        for value, weight in zip(values, weights, strict=False)
        if value is not None and weight > 0
    ]
    if not pairs:
        return None
    denominator = sum(weight for _, weight in pairs)
    if denominator <= 0:
        return None
    return sum(value * weight for value, weight in pairs) / denominator


def _sum_nullable(values: Iterable[float | None]) -> float | None:
    total = 0.0
    seen = False
    for value in values:
        if value is None:
            continue
        total += value
        seen = True
    return total if seen else None


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").replace("_", " ").split())


def _normalize_weights(weights: list[float]) -> list[float]:
    cleaned = [weight for weight in weights if weight > 0]
    total = sum(cleaned)
    if total <= 0:
        return []
    return [weight / total for weight in cleaned]


def _normalized_shares(values: Iterable[float | None]) -> list[float]:
    cleaned = [max(value or 0.0, 0.0) for value in values]
    total = sum(cleaned)
    if total <= 0:
        return []
    return sorted((value / total for value in cleaned if value > 0), reverse=True)


def _series_returns(points: list[CryptoPortfolioPoint]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        if previous.value <= 0:
            continue
        returns.append((current.value / previous.value) - 1.0)
    return returns


def _annualized_volatility(returns: list[float], *, periods_per_year: int) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / max(len(returns) - 1, 1)
    return math.sqrt(max(variance, 0.0)) * math.sqrt(periods_per_year)


def _compact_number(value: float | None) -> str:
    if value is None:
        return "N/A"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def _join_notes(*parts: str | None) -> str | None:
    cleaned: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return " ".join(cleaned) if cleaned else None
