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
    CommodityOverviewAnalytics,
    CommodityOverviewMarketBreadth,
    CommodityOverviewMatrixRow,
    CommodityOverviewRankingItem,
    CommodityOverviewRankings,
    CommodityOverviewScatter,
    CommodityOverviewScatterPoint,
    CommodityOverviewTermStructure,
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
        overview = self._build_overview(snapshot, selected, summaries, curves, inventories, spreads)
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
            overview=overview,
            warnings=warnings,
            source_provider="gamma",
            retrieved_at=_max_datetime(snapshot.retrieved_at, snapshot.coverage.retrieved_at),
            origin="gamma.commodities.workspace",
            transformation_note=(
                "Gamma computes commodity summaries, overview regime analytics, curve labels, spreads, inventory context, and cross-domain links from normalized provider records."
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
            ("gold-platinum-ratio", "Gold / Platinum", "gold", "platinum", "ratio"),
            ("copper-gold-ratio", "Copper / Gold", "copper", "gold", "ratio"),
            ("copper-aluminum-spread", "Copper - Aluminum", "copper", "aluminum", "substitution"),
            ("gasoline-crack", "Gasoline 1-1 Crack Proxy", "gasoline", "wti", "crack"),
            ("heating-oil-crack", "Distillate 1-1 Crack Proxy", "heating_oil", "wti", "crack"),
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
                unit=_relative_spread_unit(kind),
                formula=_relative_spread_formula(kind),
                rationale=_spread_rationale(spread_id),
                source_provider="gamma",
                retrieved_at=history[-1].retrieved_at,
                origin="gamma.commodities.spread_definition",
                transformation_note="Gamma-defined inter-commodity spread using aligned normalized price histories.",
            )
            spreads.append(_spread_snapshot(definition, value, history, history[-1].retrieved_at))

        for spread_id, label, product_weights, crude_barrels in [
            ("two-one-one-crack", "2-1-1 Crack Proxy", {"gasoline": 1.0, "heating_oil": 1.0}, 2.0),
            ("three-two-one-crack", "3-2-1 Crack Proxy", {"gasoline": 2.0, "heating_oil": 1.0}, 3.0),
        ]:
            history = _composite_crack_history(spread_id, histories_by_id, product_weights, "wti", crude_barrels)
            if not history:
                continue
            definition = CommoditySpreadDefinition(
                spread_id=spread_id,
                label=label,
                spread_type="refining_margin",
                left_leg_id="+".join(f"{weight:g}x:{instrument_id}" for instrument_id, weight in product_weights.items()),
                right_leg_id=f"{crude_barrels:g}x:wti",
                unit="USD/bbl",
                formula="weighted product barrel value minus crude cost, divided by crude barrels",
                rationale=_spread_rationale(spread_id),
                source_provider="gamma",
                retrieved_at=history[-1].retrieved_at,
                origin="gamma.commodities.spread_definition",
                transformation_note="Gamma-defined composite crack spread using aligned normalized product and crude price histories.",
            )
            spreads.append(_spread_snapshot(definition, history[-1].value, history, history[-1].retrieved_at))
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

    def _build_overview(
        self,
        snapshot: CommodityProviderSnapshot,
        selected_instrument_id: str,
        summaries: list[CommodityMarketSummary],
        curves: list[CommodityCurveSnapshot],
        inventories: list[CommodityInventorySeries],
        spreads: list[CommoditySpreadSnapshot],
    ) -> CommodityOverviewAnalytics:
        retrieved_at = _max_datetime(snapshot.retrieved_at, *(summary.retrieved_at for summary in summaries))
        market_breadth = self._build_overview_market_breadth(summaries, retrieved_at)
        matrix_rows = self._build_overview_matrix_rows(snapshot, summaries, curves, inventories)
        scatter = self._build_overview_scatter(snapshot, summaries, curves)
        rankings = self._build_overview_rankings(summaries, curves, inventories, spreads)
        term_structure = self._build_overview_term_structure(selected_instrument_id, curves)
        caveats = _dedupe(
            [
                "Overview analytics are Gamma-engineered from the loaded workspace payload and should be treated as research context, not execution signals.",
                "Loaded-history momentum uses the first and last points currently loaded for each market; it is not labeled as a fixed 30D return.",
                "Roll-yield proxy uses the current front calendar spread; it is not a realized roll-return or carry model.",
                "Previous full curve snapshots are unavailable in this workspace payload unless a future provider/storage path exposes historical curve stacks.",
                "Volatility z-scores are not computed for the Commodities overview; only spread z-scores with available spread history are ranked.",
            ]
        )
        return CommodityOverviewAnalytics(
            market_breadth=market_breadth,
            matrix_rows=matrix_rows,
            scatter=scatter,
            rankings=rankings,
            term_structure=term_structure,
            caveats=caveats,
            warnings=_dedupe(
                [
                    *(market_breadth.warnings or []),
                    *(scatter.caveats if scatter is not None else []),
                    *(rankings.caveats if rankings is not None else []),
                    *(term_structure.caveats if term_structure is not None else []),
                ]
            ),
            source_provider="gamma",
            retrieved_at=_max_datetime(
                retrieved_at,
                market_breadth.retrieved_at,
                scatter.retrieved_at if scatter is not None else None,
                rankings.retrieved_at if rankings is not None else None,
                term_structure.retrieved_at if term_structure is not None else None,
            ),
            origin="gamma.commodities.overview",
            transformation_note=(
                "Gamma builds first-class overview regime analytics by joining normalized summaries, curves, spreads, inventories, and loaded price histories."
            ),
        )

    def _build_overview_market_breadth(
        self,
        summaries: list[CommodityMarketSummary],
        retrieved_at: datetime | None,
    ) -> CommodityOverviewMarketBreadth:
        counts_by_family: dict[str, int] = {}
        backwardation_count = 0
        contango_count = 0
        flat_count = 0
        unavailable_curve_count = 0
        for summary in summaries:
            family = summary.instrument.family or "other"
            counts_by_family[family] = counts_by_family.get(family, 0) + 1
            state = summary.curve_state.lower()
            if "backward" in state:
                backwardation_count += 1
            elif "contango" in state:
                contango_count += 1
            elif "flat" in state:
                flat_count += 1
            else:
                unavailable_curve_count += 1
        return CommodityOverviewMarketBreadth(
            total_markets=len(summaries),
            counts_by_family=counts_by_family,
            backwardation_count=backwardation_count,
            contango_count=contango_count,
            flat_count=flat_count,
            unavailable_curve_count=unavailable_curve_count,
            warnings=[
                "Curve breadth counts use Gamma's current curve labels and do not imply tradable curve signals."
            ],
            source_provider="gamma",
            retrieved_at=retrieved_at,
            origin="gamma.commodities.overview.market_breadth",
            transformation_note="Gamma counts normalized commodity summaries by family and current curve state.",
        )

    def _build_overview_matrix_rows(
        self,
        snapshot: CommodityProviderSnapshot,
        summaries: list[CommodityMarketSummary],
        curves: list[CommodityCurveSnapshot],
        inventories: list[CommodityInventorySeries],
    ) -> list[CommodityOverviewMatrixRow]:
        curve_by_id = {curve.instrument_id: curve for curve in curves}
        history_by_id = {history.instrument_id: history for history in snapshot.price_histories}
        inventory_by_id = _first_inventory_by_instrument(inventories)
        rows: list[CommodityOverviewMatrixRow] = []
        for summary in sorted(
            summaries,
            key=lambda item: (_family_rank(item.instrument.family), item.instrument.name),
        ):
            instrument = summary.instrument
            history = history_by_id.get(instrument.instrument_id)
            curve = curve_by_id.get(instrument.instrument_id)
            inventory = inventory_by_id.get(instrument.instrument_id)
            provenance_summary = _dedupe(
                [
                    _provenance_summary("price", history.source_provider, history.origin) if history else "",
                    _provenance_summary("summary", summary.source_provider, summary.origin),
                    _provenance_summary("curve", curve.source_provider, curve.origin) if curve else "",
                    _provenance_summary("inventory", inventory.source_provider, inventory.origin) if inventory else "",
                ]
            )
            rows.append(
                CommodityOverviewMatrixRow(
                    instrument_id=instrument.instrument_id,
                    family=instrument.family,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    quote_unit=instrument.quote_unit,
                    latest_price=summary.latest_price,
                    latest_change=summary.latest_change,
                    latest_change_pct=summary.latest_change_pct,
                    curve_state=curve.shape_label if curve is not None else summary.curve_state,
                    front_spread=curve.front_spread if curve is not None else summary.front_spread,
                    front_basis=curve.front_spread_pct if curve is not None else None,
                    roll_yield_proxy_pct=curve.roll_yield_proxy_pct if curve is not None else None,
                    inventory_signal=inventory.interpretation if inventory is not None else summary.inventory_signal,
                    inventory_seasonal_percentile=(
                        inventory.seasonal_percentile if inventory is not None else None
                    ),
                    price_source_provider=history.source_provider if history is not None else summary.source_provider,
                    curve_source_provider=curve.source_provider if curve is not None else None,
                    inventory_source_provider=inventory.source_provider if inventory is not None else None,
                    provenance_summary=provenance_summary,
                    warnings=_dedupe(
                        [
                            *summary.warnings,
                            *(curve.warnings if curve is not None else []),
                            *(inventory.warnings if inventory is not None else []),
                        ]
                    ),
                    source_provider="gamma",
                    retrieved_at=_max_datetime(
                        summary.retrieved_at,
                        history.retrieved_at if history is not None else None,
                        curve.retrieved_at if curve is not None else None,
                        inventory.retrieved_at if inventory is not None else None,
                    ),
                    origin="gamma.commodities.overview.matrix_row",
                    transformation_note=(
                        "Gamma joins the market summary, current curve analytics, loaded price history provenance, and first linked inventory/fundamental series."
                    ),
                )
            )
        return rows

    def _build_overview_scatter(
        self,
        snapshot: CommodityProviderSnapshot,
        summaries: list[CommodityMarketSummary],
        curves: list[CommodityCurveSnapshot],
    ) -> CommodityOverviewScatter:
        curve_by_id = {curve.instrument_id: curve for curve in curves}
        history_by_id = {history.instrument_id: history for history in snapshot.price_histories}
        points: list[CommodityOverviewScatterPoint] = []
        omitted = 0
        for summary in summaries:
            instrument = summary.instrument
            history = history_by_id.get(instrument.instrument_id)
            curve = curve_by_id.get(instrument.instrument_id)
            momentum = _loaded_history_momentum_pct(history)
            roll = curve.roll_yield_proxy_pct if curve is not None else None
            if momentum is None or roll is None or not _finite(momentum) or not _finite(roll):
                omitted += 1
                continue
            points.append(
                CommodityOverviewScatterPoint(
                    instrument_id=instrument.instrument_id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    family=instrument.family,
                    x_value=round(momentum, 3),
                    y_value=round(roll, 3),
                    display_label=instrument.symbol,
                    x_source_provider=history.source_provider if history is not None else None,
                    y_source_provider=curve.source_provider if curve is not None else None,
                    warnings=_dedupe(
                        [
                            "X-axis uses loaded-history momentum, not a fixed 30D momentum window.",
                            "Y-axis uses Gamma's current front-spread roll-yield proxy.",
                            *(curve.warnings if curve is not None else []),
                        ]
                    ),
                    source_provider="gamma",
                    retrieved_at=_max_datetime(
                        history.retrieved_at if history is not None else None,
                        curve.retrieved_at if curve is not None else None,
                    ),
                    origin="gamma.commodities.overview.scatter_point",
                    transformation_note=(
                        "Gamma computes first-to-last loaded-history momentum and pairs it with the current curve roll-yield proxy."
                    ),
                )
            )
        caveats = _dedupe(
            [
                "X-axis is loaded-history momentum from the price points in this payload; it is not a fixed 30D or continuous-futures return.",
                "Y-axis is Gamma's annualized front-spread roll-yield proxy; it is not realized carry or an execution signal.",
                f"{omitted} markets were omitted because loaded price history or roll-yield proxy data was unavailable."
                if omitted
                else "",
            ]
        )
        return CommodityOverviewScatter(
            points=sorted(points, key=lambda point: (_family_rank(point.family), point.name)),
            caveats=caveats,
            source_provider="gamma",
            retrieved_at=_max_datetime(*(point.retrieved_at for point in points), snapshot.retrieved_at),
            origin="gamma.commodities.overview.scatter",
            transformation_note=(
                "Gamma builds the overview scatter from loaded commodity price histories and current curve analytics."
            ),
        )

    def _build_overview_rankings(
        self,
        summaries: list[CommodityMarketSummary],
        curves: list[CommodityCurveSnapshot],
        inventories: list[CommodityInventorySeries],
        spreads: list[CommoditySpreadSnapshot],
    ) -> CommodityOverviewRankings:
        summary_by_id = {summary.instrument.instrument_id: summary for summary in summaries}
        strongest_backwardation = [
            _curve_rank_item(curve, summary_by_id.get(curve.instrument_id), "backwardation")
            for curve in sorted(
                [curve for curve in curves if curve.front_spread is not None and curve.front_spread > 0],
                key=lambda item: item.front_spread or 0.0,
                reverse=True,
            )[:5]
        ]
        deepest_contango = [
            _curve_rank_item(curve, summary_by_id.get(curve.instrument_id), "contango")
            for curve in sorted(
                [curve for curve in curves if curve.front_spread is not None and curve.front_spread < 0],
                key=lambda item: item.front_spread or 0.0,
            )[:5]
        ]
        inventory_outliers = [
            _inventory_rank_item(series)
            for series in sorted(
                [series for series in inventories if series.seasonal_percentile is not None],
                key=lambda item: abs((item.seasonal_percentile or 50.0) - 50.0),
                reverse=True,
            )[:5]
        ]
        spread_z_score_outliers = [
            _spread_rank_item(spread)
            for spread in sorted(
                [spread for spread in spreads if spread.z_score is not None],
                key=lambda item: abs(item.z_score or 0.0),
                reverse=True,
            )[:5]
        ]
        largest_movers = [
            _mover_rank_item(summary)
            for summary in sorted(
                [summary for summary in summaries if summary.latest_change_pct is not None],
                key=lambda item: abs(item.latest_change_pct or 0.0),
                reverse=True,
            )[:5]
        ]
        return CommodityOverviewRankings(
            strongest_backwardation=strongest_backwardation,
            deepest_contango=deepest_contango,
            inventory_outliers=inventory_outliers,
            spread_z_score_outliers=spread_z_score_outliers,
            largest_movers=largest_movers,
            caveats=_dedupe(
                [
                    "Backwardation and contango ranks use current front-spread analytics from enriched curve snapshots.",
                    "Inventory outlier ranks use simple percentiles from available inventory/fundamental history, not official surprise data.",
                    "Spread z-score ranks use available spread history and may include proxy calendar-spread history where full historical futures curves are unavailable.",
                    "Largest movers use the latest consecutive loaded price points, not intraday live moves or fixed-window momentum.",
                    "Volatility z-score ranks are unavailable until Gamma stores a suitable volatility history for commodity instruments.",
                ]
            ),
            source_provider="gamma",
            retrieved_at=_max_datetime(
                *(item.retrieved_at for item in strongest_backwardation),
                *(item.retrieved_at for item in deepest_contango),
                *(item.retrieved_at for item in inventory_outliers),
                *(item.retrieved_at for item in spread_z_score_outliers),
                *(item.retrieved_at for item in largest_movers),
            ),
            origin="gamma.commodities.overview.rankings",
            transformation_note=(
                "Gamma ranks current curve states, inventory percentiles, spread z-scores, and latest loaded price changes for the overview regime dashboard."
            ),
        )

    def _build_overview_term_structure(
        self,
        selected_instrument_id: str,
        curves: list[CommodityCurveSnapshot],
    ) -> CommodityOverviewTermStructure:
        selected_curve = next((curve for curve in curves if curve.instrument_id == selected_instrument_id), None)
        caveats = [
            "Current curve uses the selected commodity's latest normalized curve snapshot.",
            "Previous full curve snapshots are not available in this workspace payload. Node-level previous_price values may reflect sample/provider prior node observations, but they are not a stored historical curve stack.",
            "Historical curve stacks require stored futures-curve history or a provider with historical curve snapshot support.",
        ]
        if selected_curve is None:
            caveats.append("No current curve is available for the selected commodity.")
        return CommodityOverviewTermStructure(
            selected_instrument_id=selected_instrument_id,
            current_curve=selected_curve,
            previous_curve_snapshots=[],
            current_curve_methodology=(
                "Current curve is the enriched curve snapshot for the selected instrument after Gamma computes shape, spreads, and roll-yield proxy."
            ),
            previous_curve_methodology=(
                "Unavailable as full historical snapshots in this payload; previous curve history requires stored futures-curve history/provider support."
            ),
            caveats=_dedupe(caveats),
            source_provider="gamma",
            retrieved_at=selected_curve.retrieved_at if selected_curve is not None else None,
            origin="gamma.commodities.overview.term_structure",
            transformation_note=(
                "Gamma exposes the selected current curve and an explicit caveat instead of fabricating a historical curve stack."
            ),
        )


def _first_inventory_by_instrument(
    inventories: list[CommodityInventorySeries],
) -> dict[str, CommodityInventorySeries]:
    rows: dict[str, CommodityInventorySeries] = {}
    preferred_categories = {"inventories", "storage"}
    for series in inventories:
        instrument_id = series.metadata.instrument_id
        if not instrument_id:
            continue
        existing = rows.get(instrument_id)
        if existing is None:
            rows[instrument_id] = series
            continue
        if series.metadata.category in preferred_categories and existing.metadata.category not in preferred_categories:
            rows[instrument_id] = series
    return rows


def _family_rank(family: str | None) -> int:
    order = {"energy": 0, "metals": 1}
    return order.get(str(family or "").lower(), 2)


def _provenance_summary(label: str, source_provider: str | None, origin: str | None) -> str:
    source = str(source_provider or "").strip()
    source_origin = str(origin or "").strip()
    if not source and not source_origin:
        return ""
    if source_origin:
        return f"{label}: {source or 'unknown'} via {source_origin}"
    return f"{label}: {source}"


def _loaded_history_momentum_pct(history: CommodityPriceHistory | None) -> float | None:
    if history is None or len(history.points) < 2:
        return None
    points = sorted(history.points, key=lambda point: point.timestamp)
    first = next((point.value for point in points if _finite(point.value) and point.value != 0), None)
    last = next((point.value for point in reversed(points) if _finite(point.value)), None)
    if first is None or last is None:
        return None
    return ((last - first) / first) * 100.0


def _curve_rank_item(
    curve: CommodityCurveSnapshot,
    summary: CommodityMarketSummary | None,
    direction: str,
) -> CommodityOverviewRankingItem:
    label = summary.instrument.symbol if summary is not None else curve.instrument_id.upper()
    family = summary.instrument.family if summary is not None else None
    value = curve.front_spread
    return CommodityOverviewRankingItem(
        item_id=f"{curve.instrument_id}:{direction}",
        label=label,
        instrument_id=curve.instrument_id,
        family=family,
        value=round(value, 6) if value is not None else None,
        display_value=_format_number(value, 3),
        unit="front minus second contract",
        direction=direction,
        warnings=curve.warnings,
        source_provider="gamma",
        retrieved_at=curve.retrieved_at,
        origin="gamma.commodities.overview.rankings.curve",
        transformation_note="Gamma ranks current front calendar spreads from enriched curve analytics.",
    )


def _inventory_rank_item(series: CommodityInventorySeries) -> CommodityOverviewRankingItem:
    percentile = series.seasonal_percentile
    direction = None
    if percentile is not None:
        direction = "high_inventory_percentile" if percentile >= 50 else "low_inventory_percentile"
    return CommodityOverviewRankingItem(
        item_id=series.metadata.series_id,
        label=series.metadata.label,
        instrument_id=series.metadata.instrument_id,
        family=None,
        value=round(percentile, 2) if percentile is not None else None,
        display_value=_format_pct(percentile, from_decimal=False, digits=1),
        unit="seasonal percentile",
        direction=direction,
        warnings=series.warnings,
        source_provider="gamma",
        retrieved_at=series.retrieved_at,
        origin="gamma.commodities.overview.rankings.inventory",
        transformation_note=(
            "Gamma ranks inventory/fundamental series by distance from the middle of available-history percentile context."
        ),
    )


def _spread_rank_item(spread: CommoditySpreadSnapshot) -> CommodityOverviewRankingItem:
    z_score = spread.z_score
    return CommodityOverviewRankingItem(
        item_id=spread.definition.spread_id,
        label=spread.definition.label,
        instrument_id=None,
        family=None,
        value=round(z_score, 3) if z_score is not None else None,
        display_value=_format_number(z_score, 2),
        unit="z-score",
        direction="high_spread_z_score" if (z_score or 0) >= 0 else "low_spread_z_score",
        warnings=spread.warnings,
        source_provider="gamma",
        retrieved_at=spread.retrieved_at,
        origin="gamma.commodities.overview.rankings.spread_z_score",
        transformation_note=(
            "Gamma ranks spread z-scores where available spread history is long enough; this is not a volatility z-score."
        ),
    )


def _mover_rank_item(summary: CommodityMarketSummary) -> CommodityOverviewRankingItem:
    value = summary.latest_change_pct * 100.0 if summary.latest_change_pct is not None else None
    return CommodityOverviewRankingItem(
        item_id=f"{summary.instrument.instrument_id}:latest_move",
        label=summary.instrument.symbol,
        instrument_id=summary.instrument.instrument_id,
        family=summary.instrument.family,
        value=round(value, 3) if value is not None else None,
        display_value=_format_pct(value, from_decimal=False, digits=2),
        unit="latest loaded price change",
        direction="up" if (value or 0) >= 0 else "down",
        warnings=summary.warnings,
        source_provider="gamma",
        retrieved_at=summary.retrieved_at,
        origin="gamma.commodities.overview.rankings.latest_mover",
        transformation_note=(
            "Gamma ranks the latest consecutive loaded price-point percentage change; this is not fixed-window momentum."
        ),
    )


def _format_number(value: float | None, digits: int = 2) -> str | None:
    if value is None or not _finite(value):
        return None
    return f"{value:.{digits}f}"


def _format_pct(value: float | None, *, from_decimal: bool = True, digits: int = 2) -> str | None:
    if value is None or not _finite(value):
        return None
    pct = value * 100.0 if from_decimal else value
    return f"{pct:+.{digits}f}%"


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


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
        elif kind == "substitution":
            value = _price_as_metric_ton(left_point.value, left.unit) - _price_as_metric_ton(right_point.value, right.unit)
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


def _composite_crack_history(
    spread_id: str,
    histories_by_id: dict[str, CommodityPriceHistory],
    product_weights: dict[str, float],
    crude_id: str,
    crude_barrels: float,
) -> list[CommoditySpreadPoint]:
    crude = histories_by_id.get(crude_id)
    product_histories = {instrument_id: histories_by_id.get(instrument_id) for instrument_id in product_weights}
    if crude is None or any(history is None for history in product_histories.values()) or crude_barrels <= 0:
        return []
    crude_by_date = {point.timestamp.date(): point for point in crude.points}
    product_by_date = {
        instrument_id: {point.timestamp.date(): point for point in history.points}
        for instrument_id, history in product_histories.items()
        if history is not None
    }
    rows: list[CommoditySpreadPoint] = []
    for date_key, crude_point in crude_by_date.items():
        product_value = 0.0
        retrieved_values = [crude_point.retrieved_at]
        missing = False
        for instrument_id, weight in product_weights.items():
            point = product_by_date.get(instrument_id, {}).get(date_key)
            if point is None:
                missing = True
                break
            product_value += weight * point.value * 42.0
            retrieved_values.append(point.retrieved_at)
        if missing:
            continue
        value = (product_value - (crude_barrels * crude_point.value)) / crude_barrels
        rows.append(
            CommoditySpreadPoint(
                spread_id=spread_id,
                timestamp=crude_point.timestamp,
                value=round(value, 6),
                source_provider="gamma",
                retrieved_at=_max_datetime(*retrieved_values),
                origin="gamma.commodities.composite_crack_history",
                transformation_note="Gamma computes this composite crack spread from aligned normalized product and crude price histories.",
            )
        )
    return rows[-120:]


def _relative_spread_unit(kind: str) -> str:
    if kind == "ratio":
        return "ratio"
    if kind == "substitution":
        return "USD/mt"
    return "USD/bbl"


def _relative_spread_formula(kind: str) -> str:
    if kind == "ratio":
        return "left / right"
    if kind == "substitution":
        return "left USD/mt - right USD/mt"
    return "product price * 42 - crude price"


def _price_as_metric_ton(value: float, unit: str | None) -> float:
    normalized = str(unit or "").lower()
    if "lb" in normalized:
        return value * 2204.62262185
    return value


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
        "gold-platinum-ratio": "Gold/platinum frames defensive monetary metal strength against industrial precious-metal demand.",
        "copper-gold-ratio": "Industrial-versus-defensive metal ratio can frame growth sensitivity.",
        "copper-aluminum-spread": "Copper and aluminum can substitute in selected industrial uses, so the normalized spread can frame relative-value pressure.",
        "gasoline-crack": "Gasoline 1-1 crack proxy frames refining margin pressure around crude and product prices.",
        "heating-oil-crack": "Distillate 1-1 crack proxy frames diesel and heating-oil tightness around crude and product prices.",
        "two-one-one-crack": "2-1-1 crack proxy summarizes a balanced gasoline/distillate refining barrel against crude input cost.",
        "three-two-one-crack": "3-2-1 crack proxy is a common refinery-margin shorthand for two gasoline barrels and one distillate barrel against three crude barrels.",
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
