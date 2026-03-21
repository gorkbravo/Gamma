from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.models.macro import (
    MacroCurveNode,
    MacroDivergenceRecord,
    MacroEventRecord,
    MacroMetricRecord,
    MacroRatesPolicySummary,
    MacroSeriesHistory,
    MacroSeriesPoint,
    MacroSnapshotCard,
    MacroSnapshotPayload,
    MacroThemeComparison,
)
from src.services.macro_adapters import FredMacroAdapter, TreasuryCurveAdapter, USMacroEventsAdapter
from src.utils.time import now_utc


RAW_FRED_SERIES: dict[str, dict[str, Any]] = {
    "us-fed-funds": {"provider_series_id": "DFF", "title": "Fed Funds Rate", "unit": "pct", "frequency": "daily", "theme": "policy", "mode_tags": ["snapshot", "rates_policy"], "history_days": 540, "ttl_hours": 24},
    "us-2y-yield": {"provider_series_id": "DGS2", "title": "US 2Y Treasury Yield", "unit": "pct", "frequency": "daily", "theme": "policy", "mode_tags": ["snapshot", "rates_policy"], "history_days": 540, "ttl_hours": 24},
    "us-10y-yield": {"provider_series_id": "DGS10", "title": "US 10Y Treasury Yield", "unit": "pct", "frequency": "daily", "theme": "policy", "mode_tags": ["snapshot", "rates_policy"], "history_days": 540, "ttl_hours": 24},
    "us-30y-yield": {"provider_series_id": "DGS30", "title": "US 30Y Treasury Yield", "unit": "pct", "frequency": "daily", "theme": "policy", "mode_tags": ["rates_policy"], "history_days": 540, "ttl_hours": 24},
    "us-real-10y-yield": {"provider_series_id": "DFII10", "title": "US 10Y Real Yield", "unit": "pct", "frequency": "daily", "theme": "policy", "mode_tags": ["snapshot", "rates_policy"], "history_days": 540, "ttl_hours": 24},
    "us-5y-breakeven": {"provider_series_id": "T5YIE", "title": "US 5Y Breakeven Inflation", "unit": "pct", "frequency": "daily", "theme": "inflation", "mode_tags": ["snapshot", "cross_asset", "rates_policy"], "history_days": 540, "ttl_hours": 24},
    "us-10y-breakeven": {"provider_series_id": "T10YIE", "title": "US 10Y Breakeven Inflation", "unit": "pct", "frequency": "daily", "theme": "inflation", "mode_tags": ["snapshot", "cross_asset", "rates_policy"], "history_days": 540, "ttl_hours": 24},
    "us-unemployment-rate": {"provider_series_id": "UNRATE", "title": "US Unemployment Rate", "unit": "pct", "frequency": "monthly", "theme": "growth", "mode_tags": ["snapshot", "cross_asset"], "history_days": 900, "ttl_hours": 36},
    "us-dollar-broad": {"provider_series_id": "DTWEXBGS", "title": "Broad Dollar Index", "unit": "index", "frequency": "daily", "theme": "policy", "mode_tags": ["snapshot", "cross_asset"], "history_days": 540, "ttl_hours": 24},
    "us-hy-oas": {"provider_series_id": "BAMLH0A0HYM2", "title": "US High Yield OAS", "unit": "pct", "frequency": "daily", "theme": "recession_risk", "mode_tags": ["snapshot", "cross_asset"], "history_days": 540, "ttl_hours": 24},
}

YOY_FRED_SERIES: dict[str, dict[str, Any]] = {
    "us-cpi-yoy": {"provider_series_id": "CPIAUCSL", "title": "Headline CPI YoY", "unit": "pct", "frequency": "monthly", "theme": "inflation", "mode_tags": ["snapshot", "cross_asset"], "history_days": 1200, "ttl_hours": 36, "transformation_note": "Year-over-year percent change computed from the CPI index level."},
    "us-core-cpi-yoy": {"provider_series_id": "CPILFESL", "title": "Core CPI YoY", "unit": "pct", "frequency": "monthly", "theme": "inflation", "mode_tags": ["snapshot", "cross_asset"], "history_days": 1200, "ttl_hours": 36, "transformation_note": "Year-over-year percent change computed from the core CPI index level."},
    "us-real-gdp-yoy": {"provider_series_id": "GDPC1", "title": "Real GDP YoY", "unit": "pct", "frequency": "quarterly", "theme": "growth", "mode_tags": ["snapshot", "cross_asset"], "history_days": 1800, "ttl_hours": 72, "transformation_note": "Year-over-year percent change computed from the chained real GDP level."},
    "us-payrolls-yoy": {"provider_series_id": "PAYEMS", "title": "Nonfarm Payrolls YoY", "unit": "pct", "frequency": "monthly", "theme": "growth", "mode_tags": ["snapshot", "cross_asset"], "history_days": 1200, "ttl_hours": 36, "transformation_note": "Year-over-year percent change computed from total nonfarm payroll employment."},
}

SPREAD_SERIES: dict[str, dict[str, Any]] = {
    "us-2s10s-slope": {"left_provider_series_id": "DGS10", "right_provider_series_id": "DGS2", "title": "2s10s Treasury Slope", "unit": "bps", "frequency": "daily", "theme": "recession_risk", "mode_tags": ["snapshot", "cross_asset", "rates_policy"], "history_days": 540, "ttl_hours": 24, "transformation_note": "10Y constant-maturity Treasury yield minus 2Y Treasury yield, scaled to basis points."}
}

TIMEFRAME_DAYS = {"1M": 31, "3M": 93, "6M": 186, "1Y": 370}
THEME_ORDER = ["all", "growth", "inflation", "policy", "recession_risk"]
THEME_SERIES = {
    "growth": ["us-real-gdp-yoy", "us-payrolls-yoy", "us-unemployment-rate", "us-2s10s-slope"],
    "inflation": ["us-cpi-yoy", "us-core-cpi-yoy", "us-5y-breakeven", "us-10y-breakeven", "us-dollar-broad"],
    "policy": ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-dollar-broad", "us-real-10y-yield"],
    "recession_risk": ["us-2s10s-slope", "us-hy-oas", "us-unemployment-rate", "us-dollar-broad"],
}
THEME_FACTORS = {
    "growth": {"us-real-gdp-yoy": 1.0, "us-payrolls-yoy": 1.0, "us-unemployment-rate": -1.0, "us-2s10s-slope": 0.6},
    "inflation": {"us-cpi-yoy": 1.0, "us-core-cpi-yoy": 1.0, "us-5y-breakeven": 0.9, "us-10y-breakeven": 0.8, "us-dollar-broad": -0.5},
    "policy": {"us-fed-funds": 1.0, "us-2y-yield": 1.0, "us-10y-yield": 0.4, "us-dollar-broad": 0.4, "us-real-10y-yield": 0.6},
    "recession_risk": {"us-2s10s-slope": -0.8, "us-hy-oas": 1.0, "us-unemployment-rate": 0.8, "us-dollar-broad": 0.2},
}
SIGNAL_SCALES = {"us-real-gdp-yoy": 0.5, "us-payrolls-yoy": 1.0, "us-unemployment-rate": 0.15, "us-cpi-yoy": 0.35, "us-core-cpi-yoy": 0.25, "us-fed-funds": 0.25, "us-2y-yield": 0.2, "us-10y-yield": 0.15, "us-30y-yield": 0.15, "us-real-10y-yield": 0.12, "us-5y-breakeven": 0.12, "us-10y-breakeven": 0.12, "us-dollar-broad": 2.0, "us-hy-oas": 0.35, "us-2s10s-slope": 20.0}


@dataclass(frozen=True)
class MacroSnapshotRequest:
    region: str = "US"
    timeframe: str = "3M"
    theme: str = "all"
    comparison_region: str | None = None
    force_refresh: bool = False


class MacroService:
    def __init__(self, *, fred_adapter: FredMacroAdapter, treasury_adapter: TreasuryCurveAdapter, events_adapter: USMacroEventsAdapter) -> None:
        self.fred_adapter = fred_adapter
        self.treasury_adapter = treasury_adapter
        self.events_adapter = events_adapter

    def get_snapshot(self, request: MacroSnapshotRequest) -> MacroSnapshotPayload:
        region = self._normalize_region(request.region)
        timeframe = self._normalize_timeframe(request.timeframe)
        theme = self._normalize_theme(request.theme)
        requested_comparison = self._parse_comparison(request.comparison_region)
        warnings = self._snapshot_warnings(region=region, requested_comparison=requested_comparison)
        histories = self._load_histories(self._snapshot_series_ids(theme), timeframe=timeframe, force_refresh=request.force_refresh)
        events = self.get_events(region=region, force_refresh=request.force_refresh)
        divergences = self.get_divergences(request, histories=histories)
        rates_policy = self._build_rates_policy(histories, events, timeframe=timeframe, force_refresh=request.force_refresh)
        retrieved_at = max([row.retrieved_at for row in histories.values() if row.retrieved_at is not None] + [row.retrieved_at for row in events if row.retrieved_at is not None] + [row.retrieved_at for row in divergences if row.retrieved_at is not None] + ([rates_policy.retrieved_at] if rates_policy.retrieved_at is not None else []), default=now_utc())
        return MacroSnapshotPayload(region=region, timeframe=timeframe, theme=theme, comparison_region=self._normalize_comparison(request.comparison_region), available_regions=["US", "Global"], available_timeframes=list(TIMEFRAME_DAYS), available_themes=THEME_ORDER, snapshot_cards=self._build_snapshot_cards(histories=histories, divergences=divergences, events=events, timeframe=timeframe), rates_policy=rates_policy, cross_asset=self._build_cross_asset(histories, divergences, timeframe=timeframe), top_divergences=divergences[:3], upcoming_events=events[:5], warnings=warnings, source_provider="fred", retrieved_at=retrieved_at, origin="macro_service.snapshot", transformation_note="Snapshot combines FRED series histories, Treasury curve snapshots, and official calendar events into a mode-oriented macro workspace.")

    def get_series_history(self, series_id: str, *, region: str = "US", timeframe: str = "1Y", force_refresh: bool = False) -> MacroSeriesHistory | None:
        if self._normalize_region(region) == "Global" and not series_id.startswith("us-"):
            return None
        return self._load_histories([series_id], timeframe=self._normalize_timeframe(timeframe), force_refresh=force_refresh).get(series_id)

    def get_divergences(self, request: MacroSnapshotRequest, *, histories: dict[str, MacroSeriesHistory] | None = None) -> list[MacroDivergenceRecord]:
        theme = self._normalize_theme(request.theme)
        timeframe = self._normalize_timeframe(request.timeframe)
        loaded_histories = histories or self._load_histories(self._divergence_series_ids(theme), timeframe=timeframe, force_refresh=request.force_refresh)
        themes = [theme] if theme != "all" else [name for name in THEME_ORDER if name != "all"]
        rows: list[MacroDivergenceRecord] = []
        for theme_name in themes:
            signal_rows: list[tuple[MacroMetricRecord, float]] = []
            for series_id in THEME_SERIES.get(theme_name, []):
                history = loaded_histories.get(series_id)
                if history is None:
                    continue
                metric = self._metric_from_history(history, timeframe=timeframe)
                if metric.delta_value is None:
                    continue
                factor = THEME_FACTORS.get(theme_name, {}).get(series_id, 1.0)
                scale = SIGNAL_SCALES.get(series_id, 1.0)
                signal_rows.append((metric, max(min((metric.delta_value / scale) * factor, 3.0), -3.0)))
            if len(signal_rows) < 2:
                continue
            strongest_positive = max(signal_rows, key=lambda item: item[1])
            strongest_negative = min(signal_rows, key=lambda item: item[1])
            score = round(strongest_positive[1] - strongest_negative[1], 2)
            label = "high" if score >= 2.4 else "moderate" if score >= 1.2 else "low"
            rows.append(MacroDivergenceRecord(divergence_id=f"{request.region.lower()}:{theme_name}:divergence", theme=theme_name, region=self._normalize_region(request.region), headline=f"{self._title_theme(theme_name)} divergence score {score:.2f}", summary=f"{strongest_positive[0].label} is reinforcing the theme while {strongest_negative[0].label} is leaning the other way.", score=score, label=label, metrics=[row for row, _ in signal_rows], series_ids=[row.series_id for row, _ in signal_rows if row.series_id], source_provider="fred", retrieved_at=max((row.retrieved_at for row, _ in signal_rows if row.retrieved_at is not None), default=now_utc()), origin="macro_service.divergences", transformation_note="Divergence scores compare directional changes across curated theme proxies, scaled by series-specific thresholds and theme orientation."))
        rows.sort(key=lambda row: (-row.score, row.theme))
        return rows

    def get_events(self, *, region: str = "US", force_refresh: bool = False) -> list[MacroEventRecord]:
        return self.events_adapter.list_events(region=self._normalize_region(region), as_of=now_utc(), force_refresh=force_refresh)

    def _load_histories(self, series_ids: list[str], *, timeframe: str, force_refresh: bool) -> dict[str, MacroSeriesHistory]:
        rows: dict[str, MacroSeriesHistory] = {}
        for series_id in series_ids:
            history = self._load_history(series_id, timeframe=timeframe, force_refresh=force_refresh)
            if history is not None:
                rows[series_id] = history
        return rows

    def _load_history(self, series_id: str, *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory | None:
        if series_id in RAW_FRED_SERIES:
            return self._load_raw_history(series_id, RAW_FRED_SERIES[series_id], timeframe=timeframe, force_refresh=force_refresh)
        if series_id in YOY_FRED_SERIES:
            return self._load_yoy_history(series_id, YOY_FRED_SERIES[series_id], timeframe=timeframe, force_refresh=force_refresh)
        if series_id in SPREAD_SERIES:
            return self._load_spread_history(series_id, SPREAD_SERIES[series_id], timeframe=timeframe, force_refresh=force_refresh)
        return None

    def _load_raw_history(self, series_id: str, meta: dict[str, Any], *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory:
        start, end = self._history_window(meta["history_days"], timeframe)
        points, retrieved_at = self.fred_adapter.get_series(meta["provider_series_id"], start=start, end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        return MacroSeriesHistory(series_id=series_id, title=meta["title"], region="US", unit=meta["unit"], frequency=meta["frequency"], theme=meta["theme"], mode_tags=list(meta["mode_tags"]), points=[point for point in points if point.timestamp >= start], source_provider="fred", retrieved_at=retrieved_at, origin=f"fred.series.observations:{meta['provider_series_id']}", transformation_note=None)

    def _load_yoy_history(self, series_id: str, meta: dict[str, Any], *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory:
        start, end = self._history_window(meta["history_days"], timeframe)
        raw_points, retrieved_at = self.fred_adapter.get_series(meta["provider_series_id"], start=start - timedelta(days=400), end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        yoy_points = _compute_yoy_points(
            raw_points,
            retrieved_at=retrieved_at,
            note=meta["transformation_note"],
            periods_per_year=_periods_per_year(meta["frequency"]),
        )
        return MacroSeriesHistory(series_id=series_id, title=meta["title"], region="US", unit=meta["unit"], frequency=meta["frequency"], theme=meta["theme"], mode_tags=list(meta["mode_tags"]), points=[point for point in yoy_points if point.timestamp >= start], source_provider="fred", retrieved_at=retrieved_at, origin="macro_service.derived.yoy", transformation_note=meta["transformation_note"])

    def _load_spread_history(self, series_id: str, meta: dict[str, Any], *, timeframe: str, force_refresh: bool) -> MacroSeriesHistory:
        start, end = self._history_window(meta["history_days"], timeframe)
        left_points, left_retrieved_at = self.fred_adapter.get_series(meta["left_provider_series_id"], start=start, end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        right_points, right_retrieved_at = self.fred_adapter.get_series(meta["right_provider_series_id"], start=start, end=end, ttl=timedelta(hours=meta["ttl_hours"]), force_refresh=force_refresh)
        left_map = {point.timestamp.date(): point for point in left_points}
        right_map = {point.timestamp.date(): point for point in right_points}
        points: list[MacroSeriesPoint] = []
        for key in sorted(set(left_map) & set(right_map)):
            left = left_map[key]
            right = right_map[key]
            points.append(MacroSeriesPoint(timestamp=datetime.combine(key, datetime.min.time()), value=(left.value - right.value) * 100.0, source_provider="fred", retrieved_at=max(filter(None, [left.retrieved_at, right.retrieved_at]), default=now_utc()), origin="macro_service.derived.spread", transformation_note=meta["transformation_note"]))
        return MacroSeriesHistory(series_id=series_id, title=meta["title"], region="US", unit=meta["unit"], frequency=meta["frequency"], theme=meta["theme"], mode_tags=list(meta["mode_tags"]), points=points, source_provider="fred", retrieved_at=max(left_retrieved_at, right_retrieved_at), origin="macro_service.derived.spread", transformation_note=meta["transformation_note"])

    def _build_snapshot_cards(self, *, histories: dict[str, MacroSeriesHistory], divergences: list[MacroDivergenceRecord], events: list[MacroEventRecord], timeframe: str) -> list[MacroSnapshotCard]:
        cards = [
            self._build_metric_card(card_id="growth", title="Growth Context", subtitle="Labor and activity backdrop", summary="Growth context blends real activity, payrolls, and labor-market slack.", mode_target="cross_asset", target_theme="growth", metric_histories=[histories.get("us-real-gdp-yoy"), histories.get("us-payrolls-yoy"), histories.get("us-unemployment-rate")], timeframe=timeframe),
            self._build_metric_card(card_id="inflation", title="Inflation Context", subtitle="Realized inflation versus market-implied inflation", summary="Inflation context compares realized CPI with breakevens to show whether markets are running ahead or behind the data.", mode_target="cross_asset", target_theme="inflation", metric_histories=[histories.get("us-cpi-yoy"), histories.get("us-core-cpi-yoy"), histories.get("us-5y-breakeven")], timeframe=timeframe),
            self._build_metric_card(card_id="policy", title="Policy Context", subtitle="Front-end rates and policy stance", summary="Front-end pricing leads the policy read and frames how restrictive the macro backdrop remains.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-fed-funds"), histories.get("us-2y-yield"), histories.get("us-10y-yield")], timeframe=timeframe),
            self._build_metric_card(card_id="curve-shape", title="Curve Shape", subtitle="Treasury slope and curve change", summary="Curve shape highlights whether rates are steepening or re-inverting against the prior reference window.", mode_target="rates_policy", target_theme="policy", metric_histories=[histories.get("us-2s10s-slope"), histories.get("us-10y-yield"), histories.get("us-30y-yield")], timeframe=timeframe),
            self._build_metric_card(card_id="real-yields", title="Real Yields / Breakevens", subtitle="Real-rate and inflation-compensation lens", summary="Real yields and breakevens capture how much of a rates move is real tightening versus inflation compensation.", mode_target="rates_policy", target_theme="inflation", metric_histories=[histories.get("us-real-10y-yield"), histories.get("us-5y-breakeven"), histories.get("us-10y-breakeven")], timeframe=timeframe),
        ]
        for card_id, title, subtitle, summary, series_id, mode_target, theme_name in (
            ("dollar", "Dollar / FX Proxy", "Broad dollar positioning", "A firmer dollar often confirms tighter policy and global stress; a softer dollar often points the other way.", "us-dollar-broad", "cross_asset", "policy"),
            ("credit", "Credit / Stress Proxy", "High-yield spread as a stress lens", "Credit spreads act as a fast proxy for tightening financial conditions and recession anxiety.", "us-hy-oas", "cross_asset", "recession_risk"),
        ):
            history = histories.get(series_id)
            if history is not None:
                cards.append(MacroSnapshotCard(card_id=card_id, title=title, subtitle=subtitle, summary=summary, mode_target=mode_target, target_theme=theme_name, metrics=[self._metric_from_history(history, timeframe=timeframe)], source_provider="fred", retrieved_at=history.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Snapshot cards summarize the latest level and active-timeframe change for a curated macro series."))
        if divergences:
            divergence = divergences[0]
            cards.append(MacroSnapshotCard(card_id="divergences", title="Top Divergences", subtitle="Where markets disagree most", summary=divergence.summary, mode_target="cross_asset", target_theme=divergence.theme, metrics=[MacroMetricRecord(metric_id=f"{divergence.divergence_id}:score", label=self._title_theme(divergence.theme), value=divergence.score, display_value=f"{divergence.score:.2f}", unit="score", source_provider=divergence.source_provider, retrieved_at=divergence.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Snapshot cards surface the highest-ranked divergence score from the reusable cross-asset engine.")], source_provider=divergence.source_provider, retrieved_at=divergence.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Snapshot cards surface the highest-ranked divergence score from the reusable cross-asset engine."))
        if events:
            event = events[0]
            cards.append(MacroSnapshotCard(card_id="events", title="Upcoming Macro Events", subtitle="Next catalyst on deck", summary=f"{event.title} is the next scheduled macro catalyst in the official event feed.", mode_target="rates_policy", target_theme="policy" if event.category == "policy" else "growth", metrics=[MacroMetricRecord(metric_id=f"{event.event_id}:date", label=event.title, value=None, display_value=event.scheduled_at.strftime('%b %d, %Y'), unit="date", source_provider=event.source_provider, retrieved_at=event.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Event cards surface the next upcoming macro release or meeting from official calendars.")], source_provider=event.source_provider, retrieved_at=event.retrieved_at, origin="macro_service.snapshot_cards", transformation_note="Event cards surface the next upcoming macro release or meeting from official calendars."))
        return cards

    def _build_metric_card(self, *, card_id: str, title: str, subtitle: str, summary: str, mode_target: str, target_theme: str, metric_histories: list[MacroSeriesHistory | None], timeframe: str) -> MacroSnapshotCard:
        metrics = [self._metric_from_history(history, timeframe=timeframe) for history in metric_histories if history is not None]
        return MacroSnapshotCard(card_id=card_id, title=title, subtitle=subtitle, summary=summary, mode_target=mode_target, target_theme=target_theme, metrics=metrics, source_provider=metrics[0].source_provider if metrics else "fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.snapshot_cards", transformation_note="Snapshot cards summarize the latest level and active-timeframe change for curated macro series.")

    def _build_rates_policy(self, histories: dict[str, MacroSeriesHistory], events: list[MacroEventRecord], *, timeframe: str, force_refresh: bool) -> MacroRatesPolicySummary:
        curve_nodes, curve_retrieved_at = self._load_curve_nodes(force_refresh=force_refresh, timeframe=timeframe)
        policy_metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe) for series_id in ("us-fed-funds", "us-2y-yield", "us-10y-yield", "us-2s10s-slope") if series_id in histories]
        real_yield_metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe) for series_id in ("us-real-10y-yield", "us-5y-breakeven", "us-10y-breakeven") if series_id in histories]
        slope_metric = next((metric for metric in policy_metrics if metric.series_id == "us-2s10s-slope"), None)
        headline = "Front-end policy pricing remains the cleanest read on US macro conditions."
        if slope_metric and slope_metric.value is not None:
            headline = "The curve is still inverted." if slope_metric.value < 0 else "The curve is positive and no longer inverted."
        return MacroRatesPolicySummary(headline=headline, summary="Rates & Policy emphasizes the current Treasury curve, front-end policy context, and the real-yield versus breakeven split.", policy_metrics=policy_metrics, curve_nodes=curve_nodes, real_yield_metrics=real_yield_metrics, events=events[:4], source_provider="treasury", retrieved_at=max([curve_retrieved_at] + [row.retrieved_at for row in policy_metrics if row.retrieved_at is not None] + [row.retrieved_at for row in real_yield_metrics if row.retrieved_at is not None] + [row.retrieved_at for row in events[:4] if row.retrieved_at is not None], default=now_utc()), origin="macro_service.rates_policy", transformation_note="Rates & Policy combines Treasury XML curve snapshots with FRED series histories and official calendar events.")

    def _build_cross_asset(self, histories: dict[str, MacroSeriesHistory], divergences: list[MacroDivergenceRecord], timeframe: str) -> list[MacroThemeComparison]:
        divergence_map = {row.theme: row for row in divergences}
        rows: list[MacroThemeComparison] = []
        for theme in [name for name in THEME_ORDER if name != "all"]:
            metrics = [self._metric_from_history(histories[series_id], timeframe=timeframe) for series_id in THEME_SERIES.get(theme, []) if series_id in histories]
            if metrics:
                divergence = divergence_map.get(theme)
                rows.append(MacroThemeComparison(theme=theme, headline=f"{self._title_theme(theme)} signals", summary=divergence.summary if divergence is not None else "Theme coverage is available, but disagreement is currently muted.", agreement_label=divergence.label if divergence is not None else "low", metrics=metrics, source_provider="fred", retrieved_at=max((metric.retrieved_at for metric in metrics if metric.retrieved_at is not None), default=now_utc()), origin="macro_service.cross_asset", transformation_note="Cross-asset theme blocks line up curated series so the user can compare whether markets agree on a macro narrative."))
        return rows

    def _load_curve_nodes(self, *, force_refresh: bool, timeframe: str) -> tuple[list[MacroCurveNode], datetime]:
        current_time = now_utc()
        years = [current_time.year] + ([current_time.year - 1] if current_time.month == 1 else [])
        nominal_history, nominal_retrieved_at = self.treasury_adapter.get_curve_history("daily_treasury_yield_curve", years=years, ttl=timedelta(hours=6), force_refresh=force_refresh)
        latest_date = max((date for date in nominal_history if date <= current_time), default=None)
        if latest_date is None:
            return [], nominal_retrieved_at
        cutoff = latest_date - timedelta(days=TIMEFRAME_DAYS.get(timeframe, 93))
        prior_candidates = [date for date in nominal_history if date <= cutoff]
        if prior_candidates:
            prior_date = max(prior_candidates)
        else:
            prior_date = max((date for date in nominal_history if date < latest_date), default=latest_date)
        latest_curve = nominal_history.get(latest_date, {})
        prior_curve = nominal_history.get(prior_date, {})
        nodes = [MacroCurveNode(tenor=tenor, current_value=latest_curve.get(tenor), prior_value=prior_curve.get(tenor), change_bps=((latest_curve.get(tenor) - prior_curve.get(tenor)) * 100.0) if latest_curve.get(tenor) is not None and prior_curve.get(tenor) is not None else None, source_provider="treasury", retrieved_at=nominal_retrieved_at, origin="treasury.daily_treasury_yield_curve", transformation_note="Curve comparison uses the latest available Treasury XML curve point versus the active-timeframe prior point, falling back to the nearest earlier observation when coverage is limited.") for tenor in ("3M", "2Y", "5Y", "10Y", "30Y")]
        return nodes, nominal_retrieved_at

    def _metric_from_history(self, history: MacroSeriesHistory, *, timeframe: str) -> MacroMetricRecord:
        latest = history.points[-1] if history.points else None
        previous = _point_before_cutoff(history.points, days=TIMEFRAME_DAYS.get(timeframe, 93))
        delta = latest.value - previous.value if latest is not None and previous is not None else None
        return MacroMetricRecord(metric_id=history.series_id, label=history.title, value=latest.value if latest is not None else None, display_value=_format_metric(latest.value if latest else None, history.unit), unit=history.unit, delta_value=delta, delta_display=_format_delta(delta, history.unit), series_id=history.series_id, source_provider=history.source_provider, retrieved_at=history.retrieved_at, origin=history.origin, transformation_note=history.transformation_note)

    def _history_window(self, minimum_days: int, timeframe: str) -> tuple[datetime, datetime]:
        current_time = now_utc()
        return current_time - timedelta(days=max(minimum_days, TIMEFRAME_DAYS.get(timeframe, 93) + 45)), current_time

    def _snapshot_series_ids(self, theme: str) -> list[str]:
        base = ["us-real-gdp-yoy", "us-payrolls-yoy", "us-unemployment-rate", "us-cpi-yoy", "us-core-cpi-yoy", "us-fed-funds", "us-2y-yield", "us-10y-yield", "us-30y-yield", "us-2s10s-slope", "us-real-10y-yield", "us-5y-breakeven", "us-10y-breakeven", "us-dollar-broad", "us-hy-oas"]
        if theme == "all":
            return base
        focused = THEME_SERIES.get(theme, [])
        return focused + [series_id for series_id in base if series_id not in focused]

    def _divergence_series_ids(self, theme: str) -> list[str]:
        if theme == "all":
            ordered: list[str] = []
            for theme_name in [name for name in THEME_ORDER if name != "all"]:
                for series_id in THEME_SERIES.get(theme_name, []):
                    if series_id not in ordered:
                        ordered.append(series_id)
            return ordered
        return list(THEME_SERIES.get(theme, []))

    @staticmethod
    def _normalize_region(region: str) -> str:
        return "Global" if str(region or "US").strip().upper() in {"GLOBAL", "GLOB"} else "US"

    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
        normalized = str(timeframe or "3M").strip().upper()
        return normalized if normalized in TIMEFRAME_DAYS else "3M"

    @staticmethod
    def _normalize_theme(theme: str) -> str:
        normalized = str(theme or "all").strip().lower().replace(" ", "_")
        return normalized if normalized in THEME_ORDER else "all"

    @staticmethod
    def _normalize_comparison(comparison_region: str | None) -> str | None:
        _ = comparison_region
        return None

    @staticmethod
    def _parse_comparison(comparison_region: str | None) -> str | None:
        if comparison_region is None:
            return None
        normalized = str(comparison_region).strip().upper()
        if normalized in {"GLOBAL", "GLOB"}:
            return "Global"
        if normalized == "US":
            return "US"
        return None

    @staticmethod
    def _snapshot_warnings(*, region: str, requested_comparison: str | None) -> list[str]:
        warnings: list[str] = []
        if region == "Global":
            warnings.append("Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.")
        if requested_comparison is not None:
            warnings.append("Comparison targets are not applied analytically in Macro V1; the comparison selection was ignored.")
        return warnings

    @staticmethod
    def _title_theme(theme: str) -> str:
        return theme.replace("_", " ").title()


def _compute_yoy_points(
    raw_points: list[MacroSeriesPoint],
    *,
    retrieved_at: datetime,
    note: str,
    periods_per_year: int,
) -> list[MacroSeriesPoint]:
    rows: list[MacroSeriesPoint] = []
    for index, point in enumerate(raw_points):
        prior = raw_points[index - periods_per_year] if index >= periods_per_year else None
        if prior is None or prior.value == 0:
            continue
        rows.append(MacroSeriesPoint(timestamp=point.timestamp, value=((point.value / prior.value) - 1.0) * 100.0, source_provider="fred", retrieved_at=retrieved_at, origin="macro_service.derived.yoy", transformation_note=note))
    return rows


def _periods_per_year(frequency: str) -> int:
    normalized = str(frequency or "").strip().lower()
    if normalized == "quarterly":
        return 4
    return 12


def _point_before_cutoff(points: list[MacroSeriesPoint], *, days: int) -> MacroSeriesPoint | None:
    if not points:
        return None
    latest = points[-1]
    cutoff = latest.timestamp - timedelta(days=days)
    for point in reversed(points):
        if point.timestamp <= cutoff:
            return point
    return points[0]


def _format_metric(value: float | None, unit: str | None) -> str:
    if value is None:
        return "N/A"
    if unit == "pct":
        return f"{value:.2f}%"
    if unit == "bps":
        return f"{value:.0f} bps"
    if unit == "index":
        return f"{value:.1f}"
    return f"{value:.2f}"


def _format_delta(value: float | None, unit: str | None) -> str:
    if value is None:
        return "N/A"
    if unit == "pct":
        return f"{value:+.2f} pp"
    if unit == "bps":
        return f"{value:+.0f} bps"
    if unit == "index":
        return f"{value:+.1f}"
    return f"{value:+.2f}"
