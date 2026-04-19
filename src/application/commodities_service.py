from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime

from src.models.commodities import (
    COMMODITY_MODES,
    CommodityCrossDomainLink,
    CommodityCurveSnapshot,
    CommodityInventoryPoint,
    CommodityInventorySeries,
    CommodityMarketSummary,
    CommodityPriceHistory,
    CommodityProviderSnapshot,
    CommoditySpreadDefinition,
    CommoditySpreadPoint,
    CommoditySpreadSnapshot,
    CommodityWorkspaceResult,
)
from src.services.commodities_adapters import CommoditiesDataProvider


@dataclass(frozen=True)
class CommodityWorkspaceRequest:
    mode: str = "overview"
    selected_instrument_id: str = "wti"
    force_refresh: bool = False


class CommoditiesService:
    def __init__(self, *, provider: CommoditiesDataProvider) -> None:
        self.provider = provider

    def get_workspace(self, request: CommodityWorkspaceRequest | None = None) -> CommodityWorkspaceResult:
        normalized_request = request or CommodityWorkspaceRequest()
        mode = _normalize_mode(normalized_request.mode)
        snapshot = self.provider.get_snapshot(force_refresh=normalized_request.force_refresh)
        selected = _normalize_selected_instrument(normalized_request.selected_instrument_id, snapshot)
        curves = [self._enrich_curve(curve) for curve in snapshot.curve_snapshots]
        inventories = [self._enrich_inventory(series) for series in snapshot.inventory_series]
        spreads = self._build_spreads(snapshot, curves)
        summaries = self._build_market_summaries(snapshot, curves, inventories)
        links = self._build_cross_domain_links(snapshot)
        warnings = _dedupe(
            [
                *snapshot.warnings,
                *snapshot.coverage.caveats,
                "Commodities is read-only research context. It does not place orders, rebalance portfolios, or automate futures trading.",
                "Curve and roll-yield analytics are simple first-pass heuristics; inspect source coverage before treating them as market conclusions.",
            ]
        )
        return CommodityWorkspaceResult(
            mode=mode,
            selected_instrument_id=selected,
            available_modes=sorted(COMMODITY_MODES),
            coverage=snapshot.coverage,
            instruments=snapshot.instruments,
            market_summaries=summaries,
            price_histories=snapshot.price_histories,
            curves=curves,
            spreads=spreads,
            inventories=inventories,
            events=snapshot.events,
            cross_domain_links=links,
            warnings=warnings,
            source_provider="gamma",
            retrieved_at=_max_datetime(snapshot.retrieved_at, snapshot.coverage.retrieved_at),
            origin="gamma.commodities.workspace",
            transformation_note=(
                "Gamma computes commodity summaries, curve labels, spreads, inventory context, and cross-domain links from normalized provider records."
            ),
        )

    def get_price_history(
        self,
        instrument_id: str,
        *,
        force_refresh: bool = False,
    ) -> CommodityPriceHistory | None:
        selected = _slug(instrument_id)
        snapshot = self.provider.get_snapshot(force_refresh=force_refresh)
        return next((history for history in snapshot.price_histories if history.instrument_id == selected), None)

    def get_curve(
        self,
        instrument_id: str,
        *,
        force_refresh: bool = False,
    ) -> CommodityCurveSnapshot | None:
        selected = _slug(instrument_id)
        snapshot = self.provider.get_snapshot(force_refresh=force_refresh)
        curve = next((row for row in snapshot.curve_snapshots if row.instrument_id == selected), None)
        return self._enrich_curve(curve) if curve is not None else None

    def get_spreads(self, *, force_refresh: bool = False) -> list[CommoditySpreadSnapshot]:
        snapshot = self.provider.get_snapshot(force_refresh=force_refresh)
        curves = [self._enrich_curve(curve) for curve in snapshot.curve_snapshots]
        return self._build_spreads(snapshot, curves)

    def _enrich_curve(self, curve: CommodityCurveSnapshot) -> CommodityCurveSnapshot:
        nodes = [node for node in curve.nodes if node.price is not None]
        if len(nodes) < 2:
            return replace(
                curve,
                shape_label="unavailable",
                warnings=_dedupe([*curve.warnings, "At least two curve nodes are required to label term structure."]),
                source_provider="gamma",
                origin="gamma.commodities.curve_analytics",
                transformation_note="Gamma could not compute curve analytics because the curve has insufficient nodes.",
            )
        front = float(nodes[0].price or 0.0)
        second = float(nodes[1].price or 0.0)
        far = float(nodes[-1].price or 0.0)
        front_spread = front - second
        m1_m6_spread = front - far if len(nodes) >= 6 else None
        curve_slope = far - front
        front_spread_pct = front_spread / front if front else None
        roll_yield_proxy = (front_spread / front) * 12.0 if front else None
        shape_label = _curve_shape(front, far)
        return replace(
            curve,
            shape_label=shape_label,
            front_spread=round(front_spread, 4),
            front_spread_pct=round(front_spread_pct, 6) if front_spread_pct is not None else None,
            m1_m6_spread=round(m1_m6_spread, 4) if m1_m6_spread is not None else None,
            curve_slope=round(curve_slope, 4),
            roll_yield_proxy_pct=round(roll_yield_proxy * 100, 3) if roll_yield_proxy is not None else None,
            summary=_curve_summary(curve.instrument_id, shape_label, front_spread, m1_m6_spread),
            warnings=_dedupe(
                [
                    *curve.warnings,
                    "Roll-yield proxy annualizes the front calendar spread only; it is not a realized roll-return model.",
                ]
            ),
            source_provider="gamma",
            origin="gamma.commodities.curve_analytics",
            transformation_note=(
                "Gamma labels contango/backwardation and computes front spread, M1-M6 slope, and a simple annualized front-spread roll-yield proxy."
            ),
        )

    def _enrich_inventory(self, series: CommodityInventorySeries) -> CommodityInventorySeries:
        points = sorted(series.points, key=lambda point: point.timestamp)
        if not points:
            return replace(
                series,
                warnings=_dedupe([*series.warnings, "Inventory series has no usable points."]),
                source_provider="gamma",
                origin="gamma.commodities.inventory_context",
                transformation_note="Gamma could not compute inventory context because no points were available.",
            )
        latest = points[-1]
        previous = points[-2] if len(points) >= 2 else None
        latest_change = latest.change if latest.change is not None else (
            latest.value - previous.value if previous is not None else None
        )
        percentile = _percentile([point.value for point in points], latest.value) if len(points) >= 20 else None
        latest_point = replace(latest, seasonal_percentile=percentile)
        enriched_points = [*points[:-1], latest_point]
        interpretation = _inventory_interpretation(series.metadata.category, latest_change, percentile)
        return replace(
            series,
            points=enriched_points,
            latest_value=latest.value,
            latest_change=round(latest_change, 4) if latest_change is not None else None,
            seasonal_percentile=round(percentile, 2) if percentile is not None else None,
            interpretation=interpretation,
            source_provider="gamma",
            origin="gamma.commodities.inventory_context",
            transformation_note=(
                "Gamma computes latest change and a simple percentile rank from available inventory/fundamental history."
            ),
        )

    def _build_market_summaries(
        self,
        snapshot: CommodityProviderSnapshot,
        curves: list[CommodityCurveSnapshot],
        inventories: list[CommodityInventorySeries],
    ) -> list[CommodityMarketSummary]:
        curve_by_id = {curve.instrument_id: curve for curve in curves}
        history_by_id = {history.instrument_id: history for history in snapshot.price_histories}
        inventory_by_id: dict[str, CommodityInventorySeries] = {}
        for series in inventories:
            if series.metadata.instrument_id and series.metadata.instrument_id not in inventory_by_id:
                inventory_by_id[series.metadata.instrument_id] = series

        summaries: list[CommodityMarketSummary] = []
        for instrument in snapshot.instruments:
            history = history_by_id.get(instrument.instrument_id)
            latest = history.points[-1].value if history and history.points else None
            previous = history.points[-2].value if history and len(history.points) >= 2 else None
            change = latest - previous if latest is not None and previous is not None else None
            change_pct = change / previous if change is not None and previous else None
            curve = curve_by_id.get(instrument.instrument_id)
            inventory = inventory_by_id.get(instrument.instrument_id)
            inventory_signal = inventory.interpretation if inventory is not None else None
            summaries.append(
                CommodityMarketSummary(
                    instrument=instrument,
                    latest_price=round(latest, 4) if latest is not None else None,
                    latest_change=round(change, 4) if change is not None else None,
                    latest_change_pct=round(change_pct, 6) if change_pct is not None else None,
                    curve_state=curve.shape_label if curve is not None else "unavailable",
                    front_spread=curve.front_spread if curve is not None else None,
                    inventory_signal=inventory_signal,
                    summary=_market_summary_text(instrument.name, curve, inventory),
                    warnings=[
                        "Price is sample/proxy data." if history and history.source_provider in {"sample_data", "fred"} else "",
                    ],
                    source_provider="gamma",
                    retrieved_at=_max_datetime(instrument.retrieved_at, history.retrieved_at if history else None),
                    origin="gamma.commodities.market_summary",
                    transformation_note="Gamma combines latest price, curve state, and first available inventory/fundamental signal.",
                )
            )
        return summaries

    def _build_spreads(
        self,
        snapshot: CommodityProviderSnapshot,
        curves: list[CommodityCurveSnapshot],
    ) -> list[CommoditySpreadSnapshot]:
        curves_by_id = {curve.instrument_id: curve for curve in curves}
        histories_by_id = {history.instrument_id: history for history in snapshot.price_histories}
        spreads: list[CommoditySpreadSnapshot] = []

        for instrument_id, label in [
            ("wti", "WTI M1-M2"),
            ("wti", "WTI M1-M6"),
            ("henry_hub", "Henry Hub M1-M2"),
            ("brent", "Brent M1-M2"),
        ]:
            curve = curves_by_id.get(instrument_id)
            if curve is None:
                continue
            is_m6 = label.endswith("M1-M6")
            value = curve.m1_m6_spread if is_m6 else curve.front_spread
            if value is None:
                continue
            spread_id = f"{instrument_id}-{'m1-m6' if is_m6 else 'm1-m2'}"
            definition = CommoditySpreadDefinition(
                spread_id=spread_id,
                label=label,
                spread_type="calendar",
                left_leg_id=f"{instrument_id}:M1",
                right_leg_id=f"{instrument_id}:{'M6' if is_m6 else 'M2'}",
                unit="price",
                formula="front minus deferred",
                rationale="Calendar spreads expose term-structure tightness beyond the headline front price.",
                source_provider="gamma",
                retrieved_at=curve.retrieved_at,
                origin="gamma.commodities.spread_definition",
                transformation_note="Gamma-defined commodity spread for normalized curve analytics.",
            )
            history = _calendar_spread_history(spread_id, histories_by_id.get(instrument_id), value, curve)
            spreads.append(_spread_snapshot(definition, value, history, curve.retrieved_at))

        ratio_specs = [
            ("gold-silver-ratio", "Gold / Silver", "gold", "silver", "ratio"),
            ("copper-gold-ratio", "Copper / Gold", "copper", "gold", "ratio"),
            ("gasoline-crack", "Gasoline Crack Proxy", "gasoline", "wti", "crack"),
            ("heating-oil-crack", "Heating Oil Crack Proxy", "heating_oil", "wti", "crack"),
        ]
        for spread_id, label, left_id, right_id, kind in ratio_specs:
            left = histories_by_id.get(left_id)
            right = histories_by_id.get(right_id)
            history = _relative_spread_history(spread_id, left, right, kind)
            if not history:
                continue
            value = history[-1].value
            definition = CommoditySpreadDefinition(
                spread_id=spread_id,
                label=label,
                spread_type="inter_commodity",
                left_leg_id=left_id,
                right_leg_id=right_id,
                unit="ratio" if kind == "ratio" else "USD/bbl",
                formula="left / right" if kind == "ratio" else "product price * 42 - crude price",
                rationale=_spread_rationale(spread_id),
                source_provider="gamma",
                retrieved_at=history[-1].retrieved_at,
                origin="gamma.commodities.spread_definition",
                transformation_note="Gamma-defined inter-commodity spread using aligned normalized price histories.",
            )
            spreads.append(_spread_snapshot(definition, value, history, history[-1].retrieved_at))
        return sorted(spreads, key=lambda spread: spread.definition.label)

    def _build_cross_domain_links(
        self,
        snapshot: CommodityProviderSnapshot,
    ) -> list[CommodityCrossDomainLink]:
        retrieved_at = snapshot.retrieved_at
        return [
            CommodityCrossDomainLink(
                link_id="macro-inflation-energy",
                target_domain="macro",
                target_label="Macro Inflation",
                relationship="inflation_input",
                linked_instrument_ids=["wti", "brent", "gasoline", "heating_oil"],
                summary="Energy prices and product cracks can frame near-term inflation impulse research.",
                confidence=0.55,
                source_provider="gamma",
                retrieved_at=retrieved_at,
                origin="gamma.commodities.cross_domain",
                transformation_note="Heuristic cross-domain link; it is not a causal model.",
            ),
            CommodityCrossDomainLink(
                link_id="macro-growth-copper-gold",
                target_domain="macro",
                target_label="Macro Growth",
                relationship="growth_proxy",
                linked_instrument_ids=["copper", "gold"],
                summary="Copper/gold can be used as a rough growth-versus-defensive-metal framing signal.",
                confidence=0.42,
                source_provider="gamma",
                retrieved_at=retrieved_at,
                origin="gamma.commodities.cross_domain",
                transformation_note="Heuristic macro framing based on common market convention and normalized sample/proxy data.",
            ),
            CommodityCrossDomainLink(
                link_id="maritime-energy-chokepoints",
                target_domain="maritime",
                target_label="Sealanes Energy Chokepoints",
                relationship="shipping_context",
                linked_instrument_ids=["wti", "brent", "henry_hub", "heating_oil"],
                summary="Oil, products, and LNG research can be handed to maritime chokepoint context when vessel coverage is available.",
                confidence=0.50,
                source_provider="gamma",
                retrieved_at=retrieved_at,
                origin="gamma.commodities.cross_domain",
                transformation_note="Heuristic handoff link; Gamma does not infer cargo or route disruption from commodity prices alone.",
            ),
            CommodityCrossDomainLink(
                link_id="prediction-geopolitical-energy",
                target_domain="prediction_markets",
                target_label="Geopolitical / Inflation Markets",
                relationship="event_context",
                linked_instrument_ids=["wti", "brent", "gold"],
                summary="Commodity event windows can be compared with geopolitical, oil, and inflation prediction markets.",
                confidence=0.45,
                source_provider="gamma",
                retrieved_at=retrieved_at,
                origin="gamma.commodities.cross_domain",
                transformation_note="Heuristic related-context link; prediction-market retrieval is handled by the Prediction Markets workspace.",
            ),
        ]


def _normalize_mode(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_").replace("&", "")
    normalized = normalized.replace("__", "_")
    aliases = {
        "curves_spreads": "curves_spreads",
        "curves_and_spreads": "curves_spreads",
        "inventories": "inventories_fundamentals",
        "fundamentals": "inventories_fundamentals",
        "events": "events_cross_domain",
        "cross_domain": "events_cross_domain",
        "events_crossdomain": "events_cross_domain",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in COMMODITY_MODES else "overview"


def _normalize_selected_instrument(value: str, snapshot: CommodityProviderSnapshot) -> str:
    candidate = _slug(value)
    instrument_ids = {instrument.instrument_id for instrument in snapshot.instruments}
    if candidate in instrument_ids:
        return candidate
    symbol_map = {instrument.symbol.lower(): instrument.instrument_id for instrument in snapshot.instruments}
    return symbol_map.get(str(value or "").strip().lower(), "wti")


def _curve_shape(front: float, far: float) -> str:
    if not front:
        return "unavailable"
    slope_pct = (far - front) / front
    if slope_pct >= 0.004:
        return "contango"
    if slope_pct <= -0.004:
        return "backwardation"
    return "flat"


def _curve_summary(
    instrument_id: str,
    shape_label: str,
    front_spread: float,
    m1_m6_spread: float | None,
) -> str:
    label = instrument_id.replace("_", " ").title()
    if m1_m6_spread is None:
        return f"{label} curve is {shape_label}; front spread is {front_spread:.2f}."
    return f"{label} curve is {shape_label}; M1-M2 is {front_spread:.2f} and M1-M6 is {m1_m6_spread:.2f}."


def _inventory_interpretation(
    category: str,
    latest_change: float | None,
    percentile: float | None,
) -> str:
    direction = "flat"
    if latest_change is not None:
        if latest_change > 0:
            direction = "build"
        elif latest_change < 0:
            direction = "draw"
    context = ""
    if percentile is not None:
        if percentile >= 75:
            context = "high versus available history"
        elif percentile <= 25:
            context = "low versus available history"
        else:
            context = "near middle of available history"
    if category in {"inventories", "storage"}:
        return f"{direction} | {context or 'seasonal context unavailable'}"
    return f"{direction} | {context or 'history context unavailable'}"


def _market_summary_text(
    name: str,
    curve: CommodityCurveSnapshot | None,
    inventory: CommodityInventorySeries | None,
) -> str:
    curve_text = curve.shape_label if curve is not None else "curve unavailable"
    inventory_text = inventory.interpretation if inventory is not None else "no linked inventory series"
    return f"{name}: {curve_text}; {inventory_text}."


def _calendar_spread_history(
    spread_id: str,
    history: CommodityPriceHistory | None,
    latest_value: float,
    curve: CommodityCurveSnapshot,
) -> list[CommoditySpreadPoint]:
    source_points = (history.points[-80:] if history is not None else []) or []
    if len(source_points) < 20:
        timestamp = curve.as_of
        return [
            CommoditySpreadPoint(
                spread_id=spread_id,
                timestamp=timestamp,
                value=latest_value,
                source_provider="gamma",
                retrieved_at=curve.retrieved_at,
                origin="gamma.commodities.calendar_spread_history",
                transformation_note="Insufficient history for spread context; only latest curve spread is available.",
            )
        ]
    points: list[CommoditySpreadPoint] = []
    for index, point in enumerate(source_points):
        proxy = latest_value + math.sin(index / 6.0) * max(abs(latest_value) * 0.18, 0.04)
        points.append(
            CommoditySpreadPoint(
                spread_id=spread_id,
                timestamp=point.timestamp,
                value=round(proxy, 4),
                source_provider="gamma",
                retrieved_at=curve.retrieved_at,
                origin="gamma.commodities.calendar_spread_history",
                transformation_note=(
                    "Calendar-spread history is a proxy from sample/proxy price history until historical futures-curve data is configured."
                ),
            )
        )
    points[-1] = replace(points[-1], value=round(latest_value, 4), timestamp=curve.as_of)
    return points


def _relative_spread_history(
    spread_id: str,
    left: CommodityPriceHistory | None,
    right: CommodityPriceHistory | None,
    kind: str,
) -> list[CommoditySpreadPoint]:
    if left is None or right is None:
        return []
    right_by_date = {point.timestamp.date(): point for point in right.points}
    rows: list[CommoditySpreadPoint] = []
    for left_point in left.points:
        right_point = right_by_date.get(left_point.timestamp.date())
        if right_point is None or right_point.value == 0:
            continue
        if kind == "crack":
            value = (left_point.value * 42.0) - right_point.value
        else:
            value = left_point.value / right_point.value
        rows.append(
            CommoditySpreadPoint(
                spread_id=spread_id,
                timestamp=left_point.timestamp,
                value=round(value, 6),
                source_provider="gamma",
                retrieved_at=_max_datetime(left_point.retrieved_at, right_point.retrieved_at),
                origin="gamma.commodities.relative_spread_history",
                transformation_note="Gamma computes this spread from aligned normalized commodity price histories.",
            )
        )
    return rows[-120:]


def _spread_snapshot(
    definition: CommoditySpreadDefinition,
    value: float,
    history: list[CommoditySpreadPoint],
    retrieved_at: datetime | None,
) -> CommoditySpreadSnapshot:
    previous = history[-2].value if len(history) >= 2 else None
    change = value - previous if previous is not None else None
    values = [point.value for point in history]
    z_score = _z_score(values, value) if len(values) >= 20 else None
    percentile = _percentile(values, value) if len(values) >= 20 else None
    warnings = []
    if len(values) < 20:
        warnings.append("Spread history is too short for z-score or percentile context.")
    elif any("proxy" in (point.transformation_note or "").lower() for point in history):
        warnings.append("Spread z-score uses proxy history until historical futures curves are configured.")
    return CommoditySpreadSnapshot(
        definition=definition,
        value=round(value, 6),
        previous_value=round(previous, 6) if previous is not None else None,
        change=round(change, 6) if change is not None else None,
        z_score=round(z_score, 3) if z_score is not None else None,
        percentile=round(percentile, 2) if percentile is not None else None,
        interpretation=_spread_interpretation(definition.spread_type, value, z_score, percentile),
        history=history,
        warnings=warnings,
        source_provider="gamma",
        retrieved_at=retrieved_at,
        origin="gamma.commodities.spread_snapshot",
        transformation_note=(
            "Gamma computes latest spread value, change, z-score, and percentile where enough history exists."
        ),
    )


def _spread_rationale(spread_id: str) -> str:
    mapping = {
        "gold-silver-ratio": "Precious-metal ratio often frames defensive metal leadership and liquidity preference.",
        "copper-gold-ratio": "Industrial-versus-defensive metal ratio can frame growth sensitivity.",
        "gasoline-crack": "Gasoline crack proxy frames refining margin pressure around crude and product prices.",
        "heating-oil-crack": "Heating oil crack proxy frames distillate tightness around crude and product prices.",
    }
    return mapping.get(spread_id, "Gamma-defined spread for commodity research.")


def _spread_interpretation(
    spread_type: str,
    value: float | None,
    z_score: float | None,
    percentile: float | None,
) -> str:
    if value is None:
        return "unavailable"
    if z_score is not None:
        if z_score >= 1.5:
            return "high versus available history"
        if z_score <= -1.5:
            return "low versus available history"
    if percentile is not None:
        if percentile >= 80:
            return "upper historical bucket"
        if percentile <= 20:
            return "lower historical bucket"
    if spread_type == "calendar":
        return "positive front premium" if value > 0 else "deferred premium"
    return "near available-history middle"


def _percentile(values: list[float], value: float) -> float | None:
    clean = sorted(item for item in values if item == item)
    if not clean:
        return None
    count = sum(1 for item in clean if item <= value)
    return (count / len(clean)) * 100.0


def _z_score(values: list[float], value: float) -> float | None:
    clean = [item for item in values if item == item]
    if len(clean) < 2:
        return None
    mean = sum(clean) / len(clean)
    variance = sum((item - mean) ** 2 for item in clean) / (len(clean) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return None
    return (value - mean) / stdev


def _slug(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return "_".join(part for part in "".join(char if char.isalnum() else "_" for char in text).split("_") if part)


def _max_datetime(*values: datetime | None) -> datetime | None:
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
