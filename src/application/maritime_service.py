from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from src.models.maritime import (
    MARITIME_MODES,
    MaritimeChokepointSummary,
    MaritimeFlowSummary,
    MaritimeProviderSnapshot,
    MaritimeTrackSnippet,
    MaritimeVesselStaticRecord,
    MaritimeWorkspaceResult,
)
from src.services.maritime_adapters import MaritimeDataProvider


class MaritimeService:
    def __init__(self, *, provider: MaritimeDataProvider) -> None:
        self.provider = provider

    def get_workspace(
        self,
        *,
        mode: str = "live_map",
        force_refresh: bool = False,
    ) -> MaritimeWorkspaceResult:
        normalized_mode = _normalize_mode(mode)
        snapshot = self.provider.get_snapshot(force_refresh=force_refresh)
        vessel_index = {vessel.vessel_id: vessel for vessel in snapshot.vessels}
        chokepoint_summaries = self._build_chokepoint_summaries(snapshot, vessel_index)
        flow_summaries = self._build_flow_summaries(snapshot, vessel_index)
        warnings = _dedupe(
            [
                *snapshot.warnings,
                *snapshot.coverage.caveats,
                "Risk Signals are not enabled in this Workstream 9 slice; suspicious-behavior labels need a validated methodology first.",
            ]
        )
        return MaritimeWorkspaceResult(
            mode=normalized_mode,
            available_modes=sorted(MARITIME_MODES),
            coverage=snapshot.coverage,
            vessels=snapshot.vessels,
            positions=snapshot.positions,
            tracks=snapshot.tracks,
            ports=snapshot.ports,
            chokepoints=snapshot.chokepoints,
            chokepoint_summaries=chokepoint_summaries,
            flow_summaries=flow_summaries,
            event_windows=snapshot.event_windows,
            watchlists=snapshot.watchlists,
            warnings=warnings,
            source_provider="gamma",
            retrieved_at=_max_datetime(snapshot.retrieved_at, snapshot.coverage.retrieved_at),
            origin="gamma.maritime.workspace",
            transformation_note=(
                "Gamma builds chokepoint and trade-flow research summaries from normalized sample maritime records; "
                "outputs are read-only and coverage-labeled."
            ),
        )

    def get_vessel_track(
        self,
        vessel_id: str,
        *,
        force_refresh: bool = False,
    ) -> MaritimeTrackSnippet | None:
        normalized = str(vessel_id or "").strip()
        if not normalized:
            return None
        return self.provider.get_track(normalized, force_refresh=force_refresh)

    def _build_chokepoint_summaries(
        self,
        snapshot: MaritimeProviderSnapshot,
        vessel_index: dict[str, MaritimeVesselStaticRecord],
    ) -> list[MaritimeChokepointSummary]:
        summaries: list[MaritimeChokepointSummary] = []
        for chokepoint in snapshot.chokepoints:
            latest_positions = [
                position
                for position in snapshot.positions
                if chokepoint.bounding_box.contains(position.latitude, position.longitude)
            ]
            by_type: Counter[str] = Counter()
            for position in latest_positions:
                vessel = vessel_index.get(position.vessel_id)
                by_type[_display_vessel_type(vessel)] += 1
            total = sum(by_type.values())
            baseline = _baseline_for_chokepoint(chokepoint.chokepoint_id)
            congestion_score = _congestion_score(total, baseline)
            summaries.append(
                MaritimeChokepointSummary(
                    chokepoint_id=chokepoint.chokepoint_id,
                    name=chokepoint.name,
                    region=chokepoint.region,
                    coverage_status=snapshot.coverage.coverage_status,
                    total_vessel_count=total,
                    vessel_count_by_type=dict(sorted(by_type.items())),
                    baseline_vessel_count=baseline,
                    congestion_score=congestion_score,
                    congestion_label=_congestion_label(congestion_score, total),
                    commodity_links=list(chokepoint.strategic_commodities),
                    methodology=(
                        "Counts use latest sample AIS-like points inside each chokepoint bounding box; "
                        "baseline counts are static sample references, not operational traffic baselines."
                    ),
                    caveats=[
                        "Coverage is sample/partial and cannot measure true chokepoint congestion.",
                        "Dwell time and transit-rate analytics require validated historical AIS coverage.",
                    ],
                    source_provider="gamma",
                    retrieved_at=_max_datetime(snapshot.retrieved_at, chokepoint.retrieved_at),
                    origin="gamma.maritime.chokepoint_summary",
                    transformation_note=(
                        "Gamma derives sample chokepoint summaries by intersecting latest positions with normalized chokepoint bounding boxes."
                    ),
                )
            )
        summaries.sort(key=lambda row: (-(row.congestion_score or 0.0), row.name))
        return summaries

    def _build_flow_summaries(
        self,
        snapshot: MaritimeProviderSnapshot,
        vessel_index: dict[str, MaritimeVesselStaticRecord],
    ) -> list[MaritimeFlowSummary]:
        route_groups: dict[tuple[str, str, str], list[tuple[MaritimeVesselStaticRecord, MaritimeTrackSnippet]]] = defaultdict(list)
        for track in snapshot.tracks:
            vessel = vessel_index.get(track.vessel_id)
            if vessel is None:
                continue
            inferred = vessel.cargo_inference
            if not inferred:
                continue
            key = (vessel.vessel_type, inferred or "unknown", _route_bucket(track))
            route_groups[key].append((vessel, track))

        flows: list[MaritimeFlowSummary] = []
        for (vessel_type, inferred_commodity, route_label), rows in route_groups.items():
            chokepoint_ids = sorted({chokepoint_id for _, track in rows for chokepoint_id in track.chokepoint_ids})
            vessel_confidences = [
                vessel.cargo_inference_confidence
                for vessel, _ in rows
                if vessel.cargo_inference_confidence is not None
            ]
            confidence = sum(vessel_confidences) / len(vessel_confidences) if vessel_confidences else None
            flow_id = f"{_slug(vessel_type)}-{_slug(inferred_commodity)}-{_slug(route_label)}"
            flows.append(
                MaritimeFlowSummary(
                    flow_id=flow_id,
                    label=f"{_label_vessel_type(vessel_type)} | {inferred_commodity}",
                    vessel_type=vessel_type,
                    route_label=route_label,
                    coverage_status=snapshot.coverage.coverage_status,
                    vessel_count=len(rows),
                    affected_chokepoint_ids=chokepoint_ids,
                    inferred_commodity=inferred_commodity,
                    inference_confidence=confidence,
                    inference_caveat=(
                        "Commodity flow is inferred from vessel class, route labels, and sample port context; AIS does not report cargo."
                    ),
                    summary=_flow_summary_text(vessel_type, inferred_commodity, route_label, chokepoint_ids),
                    source_provider="gamma",
                    retrieved_at=snapshot.retrieved_at,
                    origin="gamma.maritime.flow_summary",
                    transformation_note=(
                        "Gamma groups sample vessel tracks by vessel class, route bucket, and explicit cargo-inference caveat."
                    ),
                )
            )
        flows.sort(key=lambda row: (-row.vessel_count, row.label))
        return flows


def _normalize_mode(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in MARITIME_MODES else "live_map"


def _display_vessel_type(vessel: MaritimeVesselStaticRecord | None) -> str:
    if vessel is None:
        return "unknown"
    return vessel.vessel_type


def _label_vessel_type(vessel_type: str) -> str:
    labels = {
        "dry_bulk": "Dry Bulk",
        "lng_carrier": "LNG",
        "product_tanker": "Products",
        "tanker": "Crude Tankers",
        "container": "Containers",
    }
    return labels.get(vessel_type, vessel_type.replace("_", " ").title())


def _baseline_for_chokepoint(chokepoint_id: str) -> int:
    baselines = {
        "hormuz": 3,
        "suez": 2,
        "bab-el-mandeb": 2,
        "panama": 2,
        "malacca": 3,
    }
    return baselines.get(chokepoint_id, 1)


def _congestion_score(total: int, baseline: int | None) -> float | None:
    if baseline is None or baseline <= 0:
        return None
    return round(total / baseline, 2)


def _congestion_label(score: float | None, total: int) -> str:
    if total <= 0:
        return "no sample vessels"
    if score is None:
        return "unavailable"
    if score >= 1.35:
        return "elevated sample density"
    if score >= 0.8:
        return "near sample baseline"
    return "below sample baseline"


def _commodity_from_type(vessel_type: str) -> str | None:
    mapping = {
        "tanker": "crude oil",
        "product_tanker": "refined products",
        "lng_carrier": "LNG",
        "dry_bulk": "dry bulk",
        "container": "containers",
    }
    return mapping.get(vessel_type)


def _route_bucket(track: MaritimeTrackSnippet) -> str:
    if "hormuz" in track.chokepoint_ids and "suez" in track.chokepoint_ids:
        return "Gulf energy to Suez route"
    if "hormuz" in track.chokepoint_ids:
        return "Arabian Gulf export route"
    if "bab-el-mandeb" in track.chokepoint_ids:
        return "Red Sea / Suez route"
    if "panama" in track.chokepoint_ids:
        return "Panama Canal route"
    return track.label


def _flow_summary_text(
    vessel_type: str,
    inferred_commodity: str,
    route_label: str,
    chokepoint_ids: list[str],
) -> str:
    chokepoint_text = ", ".join(chokepoint_ids) if chokepoint_ids else "no named chokepoint"
    return (
        f"{_label_vessel_type(vessel_type)} sample traffic links {inferred_commodity} context "
        f"to {route_label}; affected chokepoints: {chokepoint_text}."
    )


def _slug(value: str | None) -> str:
    text = str(value or "unknown").strip().lower()
    return "-".join(part for part in "".join(char if char.isalnum() else "-" for char in text).split("-") if part)


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
