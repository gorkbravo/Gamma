from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from typing import Iterable

from src.models.crypto import (
    CryptoComparisonRecord,
    CryptoDexLiquiditySummary,
    CryptoNarrativeBasketRecord,
    CryptoScreenerRequest,
    CryptoTokenRecord,
    CryptoWorkspaceResult,
)
from src.services.crypto_adapters import CoinGeckoAdapter, GeckoTerminalAdapter


_NARRATIVE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "layer 1": ("layer 1", "layer-1", "l1"),
    "layer 2": ("layer 2", "layer-2", "l2"),
    "defi": ("defi", "decentralized finance"),
    "ai": ("ai", "artificial intelligence"),
    "depin": ("depin",),
    "gaming": ("gaming", "gamefi"),
    "meme": ("meme", "memecoin"),
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

        narratives: list[CryptoNarrativeBasketRecord] = []
        try:
            narratives = self.market_adapter.get_narrative_baskets(
                force_refresh=request.force_refresh,
                token_index=token_index,
            )
        except Exception as exc:
            warnings.append(f"Narrative basket lookup failed: {exc}")

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
        return self._attach_network(detail, network_map)

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
        try:
            narratives = self.market_adapter.get_narrative_baskets(
                force_refresh=force_refresh,
                token_index=token_index,
            )
        except Exception:
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
