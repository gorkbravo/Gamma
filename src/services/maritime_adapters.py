from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from src.models.maritime import (
    MaritimeAisPositionRecord,
    MaritimeBoundingBox,
    MaritimeChokepointDefinition,
    MaritimeCoverageMetadata,
    MaritimeEventWindow,
    MaritimeFleetWatchlist,
    MaritimePortRecord,
    MaritimeProviderSnapshot,
    MaritimeTrackSnippet,
    MaritimeVesselIdentity,
    MaritimeVesselStaticRecord,
)
from src.utils.time import now_utc


AISSTREAM_DEFAULT_ENDPOINT = "wss://stream.aisstream.io/v0/stream"
AISSTREAM_DEFAULT_MESSAGE_TYPES = [
    "PositionReport",
    "ExtendedClassBPositionReport",
    "StandardClassBPositionReport",
    "ShipStaticData",
    "StaticDataReport",
]


class MaritimeDataProvider(Protocol):
    provider_id: str
    provider_label: str

    def get_snapshot(self, *, force_refresh: bool = False) -> MaritimeProviderSnapshot:
        ...

    def get_track(self, vessel_id: str, *, force_refresh: bool = False) -> MaritimeTrackSnippet | None:
        ...


class AisstreamMaritimeDataProvider:
    provider_id = "aisstream"
    provider_label = "AISstream"

    def __init__(
        self,
        *,
        api_key: str | None,
        reference_provider: MaritimeDataProvider | None = None,
        endpoint: str = AISSTREAM_DEFAULT_ENDPOINT,
        bounding_boxes: list[list[list[float]]] | None = None,
        message_types: list[str] | None = None,
        sample_seconds: float = 6.0,
        max_messages: int = 500,
        cache_seconds: int = 30,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.reference_provider = reference_provider or SampleMaritimeDataProvider()
        self.endpoint = endpoint
        self.bounding_boxes = bounding_boxes
        self.message_types = message_types or AISSTREAM_DEFAULT_MESSAGE_TYPES
        self.sample_seconds = max(0.5, float(sample_seconds))
        self.max_messages = max(1, int(max_messages))
        self.cache_seconds = max(0, int(cache_seconds))
        self._cached_snapshot: MaritimeProviderSnapshot | None = None

    def get_snapshot(self, *, force_refresh: bool = False) -> MaritimeProviderSnapshot:
        if not force_refresh and self._cached_snapshot is not None and self.cache_seconds > 0:
            cached_at = self._cached_snapshot.retrieved_at
            if cached_at is not None and (now_utc() - cached_at).total_seconds() <= self.cache_seconds:
                return self._cached_snapshot

        reference = self.reference_provider.get_snapshot(force_refresh=False)
        retrieved_at = now_utc()
        if not self.api_key:
            snapshot = self._unavailable_snapshot(
                reference,
                retrieved_at,
                warning="AISSTREAM_API_KEY is not configured; live AISstream coverage is unavailable.",
            )
            self._cached_snapshot = snapshot
            return snapshot

        try:
            messages = self._collect_messages_sync(reference)
        except RuntimeError as exc:
            snapshot = self._unavailable_snapshot(reference, retrieved_at, warning=str(exc))
            self._cached_snapshot = snapshot
            return snapshot
        except Exception as exc:
            snapshot = self._unavailable_snapshot(
                reference,
                retrieved_at,
                warning=f"AISstream connection failed: {exc.__class__.__name__}.",
            )
            self._cached_snapshot = snapshot
            return snapshot

        snapshot = self._snapshot_from_messages(messages, reference, retrieved_at)
        self._cached_snapshot = snapshot
        return snapshot

    def get_track(self, vessel_id: str, *, force_refresh: bool = False) -> MaritimeTrackSnippet | None:
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        return next((track for track in snapshot.tracks if track.vessel_id == vessel_id), None)

    def _collect_messages_sync(self, reference: MaritimeProviderSnapshot) -> list[dict[str, Any]]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._collect_messages(reference))
        raise RuntimeError("AISstream collection cannot run inside an active event loop.")

    async def _collect_messages(self, reference: MaritimeProviderSnapshot) -> list[dict[str, Any]]:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("Python package 'websockets' is required for AISstream live collection.") from exc

        boxes = self.bounding_boxes or _aisstream_boxes_from_chokepoints(reference.chokepoints)
        subscription = {
            "APIKey": self.api_key,
            "BoundingBoxes": boxes,
            "FilterMessageTypes": self.message_types,
        }
        messages: list[dict[str, Any]] = []
        async with websockets.connect(self.endpoint, open_timeout=10, ping_interval=20, ping_timeout=20) as websocket:
            await websocket.send(json.dumps(subscription))
            deadline = asyncio.get_running_loop().time() + self.sample_seconds
            while len(messages) < self.max_messages:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    messages.append(payload)
        return messages

    def _snapshot_from_messages(
        self,
        messages: list[dict[str, Any]],
        reference: MaritimeProviderSnapshot,
        retrieved_at,
    ) -> MaritimeProviderSnapshot:
        positions: list[MaritimeAisPositionRecord] = []
        vessel_by_id: dict[str, MaritimeVesselStaticRecord] = {}
        source_timestamps: list[datetime] = []
        warnings = [
            "AISstream is treated as partial live AIS coverage, not complete global vessel truth.",
            "AISstream beta coverage is coastal/receiver dependent; offshore gaps and outages are expected.",
            "Cargo links are not inferred from AISstream live messages in this provider slice.",
        ]

        for index, message in enumerate(messages):
            parsed = _position_from_aisstream_message(message, index=index, retrieved_at=retrieved_at)
            if parsed is None:
                continue
            position, vessel = parsed
            positions.append(position)
            source_timestamps.append(position.timestamp)
            vessel_by_id.setdefault(vessel.vessel_id, vessel)

        latest_positions = _latest_positions_by_vessel(positions)
        if not latest_positions:
            warnings.append(
                f"No AIS positions were received during the {self.sample_seconds:g}-second AISstream sample window."
            )

        coverage_status = "partial" if latest_positions else "unavailable"
        coverage = MaritimeCoverageMetadata(
            coverage_status=coverage_status,
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="live_stream_sample" if latest_positions else "live_stream_empty_sample",
            regions=[item.name for item in reference.chokepoints],
            as_of=retrieved_at,
            source_timestamp=max(source_timestamps) if source_timestamps else None,
            caveats=[
                *warnings,
                f"Workspace positions are sampled for {self.sample_seconds:g} seconds and cached for {self.cache_seconds} seconds.",
                "Use provider evaluation before drawing market conclusions from AISstream counts.",
            ],
            credential_env_vars=["AISSTREAM_API_KEY"],
            supports_live=True,
            supports_historical=False,
            source_provider="aisstream",
            retrieved_at=retrieved_at,
            origin="aisstream.coverage",
            transformation_note=(
                "Gamma subscribed to AISstream chokepoint bounding boxes and normalized received AIS messages into read-only position records."
            ),
        )
        return MaritimeProviderSnapshot(
            coverage=coverage,
            vessels=list(vessel_by_id.values()),
            positions=latest_positions,
            tracks=[],
            ports=reference.ports,
            chokepoints=reference.chokepoints,
            event_windows=reference.event_windows,
            watchlists=[],
            warnings=warnings,
            source_provider="aisstream",
            retrieved_at=retrieved_at,
            origin="aisstream.snapshot",
            transformation_note=(
                "Live AISstream messages are sampled over a short window and combined with Gamma's static chokepoint definitions."
            ),
        )

    def _unavailable_snapshot(
        self,
        reference: MaritimeProviderSnapshot,
        retrieved_at,
        *,
        warning: str,
    ) -> MaritimeProviderSnapshot:
        coverage = MaritimeCoverageMetadata(
            coverage_status="unavailable",
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="unavailable",
            regions=[item.name for item in reference.chokepoints],
            as_of=retrieved_at,
            caveats=[
                warning,
                "Gamma keeps the Maritime workspace read-only and falls back to reference chokepoint definitions only.",
                "No live AIS conclusions should be drawn until provider collection succeeds.",
            ],
            credential_env_vars=["AISSTREAM_API_KEY"],
            supports_live=True,
            supports_historical=False,
            source_provider="aisstream",
            retrieved_at=retrieved_at,
            origin="aisstream.coverage",
            transformation_note="AISstream coverage is unavailable for this request.",
        )
        return MaritimeProviderSnapshot(
            coverage=coverage,
            vessels=[],
            positions=[],
            tracks=[],
            ports=reference.ports,
            chokepoints=reference.chokepoints,
            event_windows=reference.event_windows,
            watchlists=[],
            warnings=[warning],
            source_provider="aisstream",
            retrieved_at=retrieved_at,
            origin="aisstream.snapshot",
            transformation_note="Gamma returned provider metadata and reference definitions without live AIS positions.",
        )


class SampleMaritimeDataProvider:
    provider_id = "sample_maritime"
    provider_label = "Sample Maritime Dataset"

    def get_snapshot(self, *, force_refresh: bool = False) -> MaritimeProviderSnapshot:
        del force_refresh
        retrieved_at = now_utc()
        sample_time = retrieved_at.replace(microsecond=0)
        coverage = _coverage(retrieved_at)
        vessels = _vessels(retrieved_at)
        ports = _ports(retrieved_at)
        chokepoints = _chokepoints(retrieved_at)
        tracks = _tracks(retrieved_at, sample_time)
        latest_positions = [track.points[-1] for track in tracks if track.points]
        events = _event_windows(retrieved_at, sample_time)
        watchlists = _watchlists(retrieved_at)
        warnings = [
            "Maritime Intelligence is using a sample partial dataset; it is not live global AIS coverage.",
            "Cargo links are inferred from vessel class and route context only; AIS does not identify cargo.",
            "Provider evaluation for live AIS remains unresolved, so risk/suspicious-behavior labels are intentionally excluded.",
        ]
        return MaritimeProviderSnapshot(
            coverage=coverage,
            vessels=vessels,
            positions=latest_positions,
            tracks=tracks,
            ports=ports,
            chokepoints=chokepoints,
            event_windows=events,
            watchlists=watchlists,
            warnings=warnings,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.snapshot",
            transformation_note=(
                "Static Gamma sample records are materialized into normalized maritime entities for Workstream 9 development."
            ),
        )

    def get_track(self, vessel_id: str, *, force_refresh: bool = False) -> MaritimeTrackSnippet | None:
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        return next((track for track in snapshot.tracks if track.vessel_id == vessel_id), None)


def _coverage(retrieved_at) -> MaritimeCoverageMetadata:
    return MaritimeCoverageMetadata(
        coverage_status="sample",
        provider_id=SampleMaritimeDataProvider.provider_id,
        provider_label=SampleMaritimeDataProvider.provider_label,
        freshness_label="mocked",
        regions=["Hormuz", "Suez", "Bab el-Mandeb", "Panama", "Malacca", "Cape of Good Hope"],
        as_of=retrieved_at,
        source_timestamp=retrieved_at,
        caveats=[
            "Sample positions are hand-curated to exercise the domain model and UI.",
            "Counts and congestion scores are not operational measurements.",
            "Use a live or historical AIS provider before drawing market conclusions.",
        ],
        supports_live=False,
        supports_historical=True,
        source_provider="sample_data",
        retrieved_at=retrieved_at,
        origin="sample_maritime.coverage",
        transformation_note="Coverage is labeled sample because Gamma has no live AIS adapter configured.",
    )


def _vessels(retrieved_at) -> list[MaritimeVesselStaticRecord]:
    cargo_caveat = "AIS vessel class and route context are proxies; cargo is not directly identified by AIS."
    return [
        MaritimeVesselStaticRecord(
            vessel_id="vessel-gulf-horizon",
            name="Gulf Horizon",
            identity=MaritimeVesselIdentity(
                vessel_id="vessel-gulf-horizon",
                mmsi="538009991",
                imo="9876543",
                callsign="V7GH9",
                normalized_id="imo:9876543",
            ),
            vessel_type="tanker",
            vessel_class="VLCC crude tanker",
            flag="Marshall Islands",
            length_m=333.0,
            beam_m=60.0,
            deadweight_tons=299_000.0,
            cargo_inference="crude oil",
            cargo_inference_confidence=0.56,
            cargo_inference_caveat=cargo_caveat,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.vessels",
            transformation_note="Sample vessel metadata normalizes MMSI/IMO identifiers and adds explicit cargo-inference caveats.",
        ),
        MaritimeVesselStaticRecord(
            vessel_id="vessel-desert-methane",
            name="Desert Methane",
            identity=MaritimeVesselIdentity(
                vessel_id="vessel-desert-methane",
                mmsi="310777000",
                imo="9765432",
                callsign="ZCDM4",
                normalized_id="imo:9765432",
            ),
            vessel_type="lng_carrier",
            vessel_class="LNG carrier",
            flag="Bermuda",
            length_m=294.0,
            beam_m=46.0,
            deadweight_tons=82_000.0,
            cargo_inference="LNG",
            cargo_inference_confidence=0.62,
            cargo_inference_caveat=cargo_caveat,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.vessels",
            transformation_note="Sample vessel metadata normalizes MMSI/IMO identifiers and adds explicit cargo-inference caveats.",
        ),
        MaritimeVesselStaticRecord(
            vessel_id="vessel-red-sea-trader",
            name="Red Sea Trader",
            identity=MaritimeVesselIdentity(
                vessel_id="vessel-red-sea-trader",
                mmsi="636021111",
                imo="9654321",
                callsign="D5RT8",
                normalized_id="imo:9654321",
            ),
            vessel_type="container",
            vessel_class="Panamax container ship",
            flag="Liberia",
            length_m=294.0,
            beam_m=32.0,
            deadweight_tons=68_000.0,
            cargo_inference="containerized goods",
            cargo_inference_confidence=0.44,
            cargo_inference_caveat=cargo_caveat,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.vessels",
            transformation_note="Sample vessel metadata normalizes MMSI/IMO identifiers and adds explicit cargo-inference caveats.",
        ),
        MaritimeVesselStaticRecord(
            vessel_id="vessel-cape-iron",
            name="Cape Iron",
            identity=MaritimeVesselIdentity(
                vessel_id="vessel-cape-iron",
                mmsi="477888123",
                imo="9543210",
                callsign="VRCP7",
                normalized_id="imo:9543210",
            ),
            vessel_type="dry_bulk",
            vessel_class="Capesize bulker",
            flag="Hong Kong",
            length_m=289.0,
            beam_m=45.0,
            deadweight_tons=181_000.0,
            cargo_inference="iron ore or coal",
            cargo_inference_confidence=0.48,
            cargo_inference_caveat=cargo_caveat,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.vessels",
            transformation_note="Sample vessel metadata normalizes MMSI/IMO identifiers and adds explicit cargo-inference caveats.",
        ),
        MaritimeVesselStaticRecord(
            vessel_id="vessel-pacific-lock",
            name="Pacific Lock",
            identity=MaritimeVesselIdentity(
                vessel_id="vessel-pacific-lock",
                mmsi="352010234",
                imo="9432109",
                callsign="3EPL6",
                normalized_id="imo:9432109",
            ),
            vessel_type="product_tanker",
            vessel_class="MR product tanker",
            flag="Panama",
            length_m=183.0,
            beam_m=32.0,
            deadweight_tons=50_000.0,
            cargo_inference="refined products",
            cargo_inference_confidence=0.52,
            cargo_inference_caveat=cargo_caveat,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.vessels",
            transformation_note="Sample vessel metadata normalizes MMSI/IMO identifiers and adds explicit cargo-inference caveats.",
        ),
    ]


def _ports(retrieved_at) -> list[MaritimePortRecord]:
    return [
        MaritimePortRecord(
            port_id="port-ras-tanura",
            name="Ras Tanura",
            country="Saudi Arabia",
            region="Arabian Gulf",
            latitude=26.64,
            longitude=50.16,
            unlocode="SARTA",
            terminal_type="oil export terminal",
            commodity_links=["crude oil", "refined products"],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.ports",
        ),
        MaritimePortRecord(
            port_id="port-fujairah",
            name="Fujairah",
            country="United Arab Emirates",
            region="Arabian Gulf",
            latitude=25.13,
            longitude=56.36,
            unlocode="AEFJR",
            terminal_type="bunker and oil terminal",
            commodity_links=["crude oil", "refined products"],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.ports",
        ),
        MaritimePortRecord(
            port_id="port-ras-laffan",
            name="Ras Laffan",
            country="Qatar",
            region="Arabian Gulf",
            latitude=25.93,
            longitude=51.56,
            unlocode="QARLF",
            terminal_type="LNG export terminal",
            commodity_links=["LNG"],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.ports",
        ),
        MaritimePortRecord(
            port_id="port-suez",
            name="Suez",
            country="Egypt",
            region="Red Sea / Mediterranean",
            latitude=29.97,
            longitude=32.55,
            unlocode="EGSUZ",
            terminal_type="canal transit",
            commodity_links=["crude oil", "LNG", "containers"],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.ports",
        ),
        MaritimePortRecord(
            port_id="port-balboa",
            name="Balboa",
            country="Panama",
            region="Central America",
            latitude=8.96,
            longitude=-79.56,
            unlocode="PABLB",
            terminal_type="canal transit",
            commodity_links=["containers", "refined products"],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.ports",
        ),
    ]


def _chokepoints(retrieved_at) -> list[MaritimeChokepointDefinition]:
    return [
        MaritimeChokepointDefinition(
            chokepoint_id="hormuz",
            name="Strait of Hormuz",
            region="Arabian Gulf",
            latitude=26.57,
            longitude=56.25,
            bounding_box=MaritimeBoundingBox(25.0, 27.3, 55.0, 57.4),
            strategic_commodities=["crude oil", "refined products", "LNG"],
            description="Energy chokepoint between the Arabian Gulf and Gulf of Oman.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.chokepoints",
        ),
        MaritimeChokepointDefinition(
            chokepoint_id="suez",
            name="Suez Canal",
            region="Egypt",
            latitude=30.45,
            longitude=32.35,
            bounding_box=MaritimeBoundingBox(29.75, 31.3, 31.85, 32.75),
            strategic_commodities=["crude oil", "LNG", "containers"],
            description="Canal link between the Red Sea and Mediterranean shipping lanes.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.chokepoints",
        ),
        MaritimeChokepointDefinition(
            chokepoint_id="bab-el-mandeb",
            name="Bab el-Mandeb",
            region="Red Sea / Gulf of Aden",
            latitude=12.58,
            longitude=43.33,
            bounding_box=MaritimeBoundingBox(11.8, 13.3, 42.7, 44.1),
            strategic_commodities=["crude oil", "refined products", "containers"],
            description="Southern Red Sea chokepoint linking Suez routes with the Gulf of Aden.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.chokepoints",
        ),
        MaritimeChokepointDefinition(
            chokepoint_id="panama",
            name="Panama Canal",
            region="Panama",
            latitude=9.08,
            longitude=-79.68,
            bounding_box=MaritimeBoundingBox(8.75, 9.45, -80.1, -79.35),
            strategic_commodities=["containers", "refined products", "LNG"],
            description="Transit corridor connecting Atlantic and Pacific lanes.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.chokepoints",
        ),
        MaritimeChokepointDefinition(
            chokepoint_id="malacca",
            name="Strait of Malacca",
            region="Southeast Asia",
            latitude=2.8,
            longitude=101.0,
            bounding_box=MaritimeBoundingBox(1.0, 5.8, 99.0, 104.5),
            strategic_commodities=["crude oil", "LNG", "containers", "dry bulk"],
            description="Dense Asia-Europe and energy transit lane.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.chokepoints",
        ),
    ]


def _tracks(retrieved_at, sample_time) -> list[MaritimeTrackSnippet]:
    return [
        MaritimeTrackSnippet(
            track_id="track-gulf-horizon-hormuz",
            vessel_id="vessel-gulf-horizon",
            label="Ras Tanura to Fujairah via Hormuz",
            start_port_id="port-ras-tanura",
            end_port_id="port-fujairah",
            chokepoint_ids=["hormuz"],
            points=[
                _position("gulf-horizon-1", "vessel-gulf-horizon", "538009991", sample_time - timedelta(hours=6), 26.62, 50.35, 12.4, 88.0, retrieved_at, "Under way"),
                _position("gulf-horizon-2", "vessel-gulf-horizon", "538009991", sample_time - timedelta(hours=3), 26.55, 54.15, 12.1, 94.0, retrieved_at, "Under way"),
                _position("gulf-horizon-3", "vessel-gulf-horizon", "538009991", sample_time - timedelta(minutes=45), 26.33, 56.35, 9.8, 105.0, retrieved_at, "Under way"),
            ],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.tracks",
            transformation_note="Sample route snippets preserve AIS-like points but are not live tracks.",
        ),
        MaritimeTrackSnippet(
            track_id="track-desert-methane-suez",
            vessel_id="vessel-desert-methane",
            label="Ras Laffan to Mediterranean via Suez",
            start_port_id="port-ras-laffan",
            end_port_id="port-suez",
            chokepoint_ids=["hormuz", "bab-el-mandeb", "suez"],
            points=[
                _position("desert-methane-1", "vessel-desert-methane", "310777000", sample_time - timedelta(hours=12), 25.88, 51.72, 14.1, 78.0, retrieved_at, "Under way"),
                _position("desert-methane-2", "vessel-desert-methane", "310777000", sample_time - timedelta(hours=4), 12.42, 43.18, 13.4, 321.0, retrieved_at, "Under way"),
                _position("desert-methane-3", "vessel-desert-methane", "310777000", sample_time - timedelta(minutes=35), 30.02, 32.55, 7.2, 354.0, retrieved_at, "Constrained by draught"),
            ],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.tracks",
            transformation_note="Sample route snippets preserve AIS-like points but are not live tracks.",
        ),
        MaritimeTrackSnippet(
            track_id="track-red-sea-trader-reroute",
            vessel_id="vessel-red-sea-trader",
            label="Asia-Europe container route near Bab el-Mandeb",
            start_port_id=None,
            end_port_id="port-suez",
            chokepoint_ids=["bab-el-mandeb", "suez"],
            points=[
                _position("red-sea-trader-1", "vessel-red-sea-trader", "636021111", sample_time - timedelta(hours=10), 13.02, 46.15, 15.6, 291.0, retrieved_at, "Under way"),
                _position("red-sea-trader-2", "vessel-red-sea-trader", "636021111", sample_time - timedelta(hours=5), 12.52, 43.42, 12.3, 300.0, retrieved_at, "Under way"),
                _position("red-sea-trader-3", "vessel-red-sea-trader", "636021111", sample_time - timedelta(minutes=25), 12.08, 42.95, 8.0, 196.0, retrieved_at, "Under way"),
            ],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.tracks",
            transformation_note="Sample track includes a route-change proxy near Bab el-Mandeb for event-replay development.",
        ),
        MaritimeTrackSnippet(
            track_id="track-cape-iron-cape",
            vessel_id="vessel-cape-iron",
            label="Capesize bulker around Cape of Good Hope",
            start_port_id=None,
            end_port_id=None,
            chokepoint_ids=[],
            points=[
                _position("cape-iron-1", "vessel-cape-iron", "477888123", sample_time - timedelta(hours=9), -34.90, 18.25, 10.6, 96.0, retrieved_at, "Under way"),
                _position("cape-iron-2", "vessel-cape-iron", "477888123", sample_time - timedelta(hours=4), -34.48, 20.15, 10.2, 89.0, retrieved_at, "Under way"),
                _position("cape-iron-3", "vessel-cape-iron", "477888123", sample_time - timedelta(minutes=40), -34.22, 22.40, 10.1, 84.0, retrieved_at, "Under way"),
            ],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.tracks",
            transformation_note="Sample route snippet supports Cape rerouting context but is not a complete voyage.",
        ),
        MaritimeTrackSnippet(
            track_id="track-pacific-lock-panama",
            vessel_id="vessel-pacific-lock",
            label="Product tanker queued near Panama Canal",
            start_port_id="port-balboa",
            end_port_id=None,
            chokepoint_ids=["panama"],
            points=[
                _position("pacific-lock-1", "vessel-pacific-lock", "352010234", sample_time - timedelta(hours=7), 8.72, -79.78, 8.2, 12.0, retrieved_at, "Under way"),
                _position("pacific-lock-2", "vessel-pacific-lock", "352010234", sample_time - timedelta(hours=2), 8.91, -79.62, 3.1, 28.0, retrieved_at, "Restricted manoeuverability"),
                _position("pacific-lock-3", "vessel-pacific-lock", "352010234", sample_time - timedelta(minutes=20), 9.08, -79.69, 0.4, 0.0, retrieved_at, "At anchor"),
            ],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.tracks",
            transformation_note="Sample route snippet supports canal queue and dwell-time proxy development.",
        ),
    ]


def _position(
    position_id: str,
    vessel_id: str,
    mmsi: str,
    timestamp,
    latitude: float,
    longitude: float,
    speed_knots: float,
    course_degrees: float,
    retrieved_at,
    navigation_status: str,
) -> MaritimeAisPositionRecord:
    return MaritimeAisPositionRecord(
        position_id=position_id,
        vessel_id=vessel_id,
        mmsi=mmsi,
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        speed_knots=speed_knots,
        course_degrees=course_degrees,
        heading_degrees=course_degrees,
        navigation_status=navigation_status,
        source_provider="sample_data",
        retrieved_at=retrieved_at,
        origin="sample_maritime.ais_positions",
        transformation_note="Sample AIS-like point for offline Maritime Intelligence development.",
    )


def _event_windows(retrieved_at, sample_time) -> list[MaritimeEventWindow]:
    return [
        MaritimeEventWindow(
            event_id="event-red-sea-route-watch",
            title="Red Sea Route Watch",
            event_type="geopolitical_shipping_window",
            region="Red Sea / Gulf of Aden",
            start_at=sample_time - timedelta(days=3),
            end_at=sample_time + timedelta(days=2),
            summary=(
                "Sample event window for studying route-change and chokepoint traffic around Bab el-Mandeb and Suez."
            ),
            linked_chokepoint_ids=["bab-el-mandeb", "suez"],
            linked_commodity_flows=["containers", "crude oil", "refined products"],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.events",
            transformation_note="Sample event window is manually curated and not sourced from a live event feed.",
        ),
        MaritimeEventWindow(
            event_id="event-panama-draft-watch",
            title="Panama Draft Restriction Watch",
            event_type="canal_capacity_window",
            region="Panama",
            start_at=sample_time - timedelta(days=5),
            end_at=sample_time + timedelta(days=4),
            summary="Sample event window for canal queue, dwell-time, and refined-product flow research.",
            linked_chokepoint_ids=["panama"],
            linked_commodity_flows=["refined products", "containers", "LNG"],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.events",
            transformation_note="Sample event window is manually curated and not sourced from a live event feed.",
        ),
    ]


def _watchlists(retrieved_at) -> list[MaritimeFleetWatchlist]:
    return [
        MaritimeFleetWatchlist(
            watchlist_id="energy-chokepoint-sample",
            label="Energy Chokepoint Sample",
            description="Tankers and LNG carriers in the sample set near energy-relevant chokepoints.",
            vessel_ids=["vessel-gulf-horizon", "vessel-desert-methane", "vessel-pacific-lock"],
            vessel_type_filters=["tanker", "product_tanker", "lng_carrier"],
            caveats=[
                "Watchlist membership is sample-only and not a sanctions, ownership, or shadow-fleet classification.",
            ],
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_maritime.watchlists",
            transformation_note="Sample watchlist groups vessels by class for UI and service development.",
        )
    ]


def parse_aisstream_bounding_boxes(value: str | None) -> list[list[list[float]]] | None:
    text = str(value or "").strip()
    if not text:
        return None
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("AISSTREAM_BOUNDING_BOXES must be a JSON list.")

    boxes: list[list[list[float]]] = []
    for item in payload:
        if not (
            isinstance(item, list)
            and len(item) == 2
            and all(isinstance(point, list) and len(point) == 2 for point in item)
        ):
            raise ValueError("Each AISstream bounding box must look like [[min_lat, min_lon], [max_lat, max_lon]].")
        first, second = item
        min_lat, min_lon = float(first[0]), float(first[1])
        max_lat, max_lon = float(second[0]), float(second[1])
        if not (-90 <= min_lat <= max_lat <= 90 and -180 <= min_lon <= max_lon <= 180):
            raise ValueError("AISstream bounding box coordinates are out of range or reversed.")
        boxes.append([[min_lat, min_lon], [max_lat, max_lon]])
    return boxes


def _aisstream_boxes_from_chokepoints(
    chokepoints: list[MaritimeChokepointDefinition],
) -> list[list[list[float]]]:
    return [
        [
            [item.bounding_box.min_latitude, item.bounding_box.min_longitude],
            [item.bounding_box.max_latitude, item.bounding_box.max_longitude],
        ]
        for item in chokepoints
    ]


def _position_from_aisstream_message(
    message: dict[str, Any],
    *,
    index: int,
    retrieved_at,
) -> tuple[MaritimeAisPositionRecord, MaritimeVesselStaticRecord] | None:
    message_type = str(message.get("MessageType") or "").strip()
    metadata = _first_dict(message.get("MetaData"), message.get("Metadata"), message.get("metadata"))
    body = _aisstream_message_body(message, message_type)
    mmsi = _string_value(_first_present(metadata.get("MMSI"), body.get("UserID"), body.get("Mmsi"), body.get("MMSI")))
    latitude = _float_value(_first_present(body.get("Latitude"), metadata.get("Latitude"), metadata.get("latitude")))
    longitude = _float_value(_first_present(body.get("Longitude"), metadata.get("Longitude"), metadata.get("longitude")))
    if not mmsi or latitude is None or longitude is None:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    timestamp = _parse_aisstream_time(
        metadata.get("time_utc")
        or metadata.get("TimeUTC")
        or metadata.get("timestamp")
        or metadata.get("Timestamp"),
        fallback=retrieved_at,
    )
    vessel_id = f"mmsi:{mmsi}"
    position = MaritimeAisPositionRecord(
        position_id=f"aisstream-{mmsi}-{int(timestamp.timestamp())}-{index}",
        vessel_id=vessel_id,
        mmsi=mmsi,
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        speed_knots=_float_value(_first_present(body.get("Sog"), body.get("SpeedOverGround"))),
        course_degrees=_float_value(_first_present(body.get("Cog"), body.get("CourseOverGround"))),
        heading_degrees=_float_value(_first_present(body.get("TrueHeading"), body.get("Heading"))),
        navigation_status=_navigation_status_text(body.get("NavigationalStatus")),
        destination=_string_value(body.get("Destination")),
        draught_m=_float_value(_first_present(body.get("Draught"), body.get("MaximumStaticDraught"))),
        source_provider="aisstream",
        retrieved_at=retrieved_at,
        origin=f"aisstream.message.{message_type or 'unknown'}",
        transformation_note="Gamma normalized a live AISstream websocket message into a read-only AIS position record.",
    )
    vessel = _vessel_from_aisstream_message(
        vessel_id=vessel_id,
        mmsi=mmsi,
        metadata=metadata,
        body=body,
        message_type=message_type,
        retrieved_at=retrieved_at,
    )
    return position, vessel


def _aisstream_message_body(message: dict[str, Any], message_type: str) -> dict[str, Any]:
    container = message.get("Message")
    if not isinstance(container, dict):
        return {}
    typed = container.get(message_type)
    if isinstance(typed, dict):
        return typed
    for value in container.values():
        if isinstance(value, dict):
            return value
    return {}


def _vessel_from_aisstream_message(
    *,
    vessel_id: str,
    mmsi: str,
    metadata: dict[str, Any],
    body: dict[str, Any],
    message_type: str,
    retrieved_at,
) -> MaritimeVesselStaticRecord:
    ship_name = _string_value(_first_present(metadata.get("ShipName"), metadata.get("ship_name"), body.get("Name")))
    ais_type = _first_present(body.get("Type"), body.get("ShipType"))
    vessel_type = _vessel_type_from_ais_code(ais_type)
    vessel_class = _vessel_class_from_ais_code(ais_type)
    imo = _string_value(_first_present(body.get("ImoNumber"), body.get("IMO"), body.get("Imo")))
    callsign = _string_value(_first_present(body.get("CallSign"), body.get("Callsign")))
    return MaritimeVesselStaticRecord(
        vessel_id=vessel_id,
        name=ship_name or f"MMSI {mmsi}",
        identity=MaritimeVesselIdentity(
            vessel_id=vessel_id,
            mmsi=mmsi,
            imo=imo,
            callsign=callsign,
            normalized_id=f"imo:{imo}" if imo else f"mmsi:{mmsi}",
        ),
        vessel_type=vessel_type,
        vessel_class=vessel_class,
        cargo_inference=None,
        cargo_inference_confidence=None,
        cargo_inference_caveat=(
            "AISstream live messages do not identify actual cargo; Gamma does not infer cargo from this live provider slice."
        ),
        source_provider="aisstream",
        retrieved_at=retrieved_at,
        origin=f"aisstream.message.{message_type or 'unknown'}",
        transformation_note="Gamma created minimal live vessel metadata from AISstream message metadata and AIS static fields when present.",
    )


def _latest_positions_by_vessel(
    positions: list[MaritimeAisPositionRecord],
) -> list[MaritimeAisPositionRecord]:
    latest: dict[str, MaritimeAisPositionRecord] = {}
    for position in positions:
        previous = latest.get(position.vessel_id)
        if previous is None or position.timestamp >= previous.timestamp:
            latest[position.vessel_id] = position
    return sorted(latest.values(), key=lambda item: item.timestamp, reverse=True)


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_value(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_aisstream_time(value: Any, *, fallback: datetime) -> datetime:
    text = str(value or "").strip()
    if not text:
        return fallback
    candidates = [
        text,
        text.replace(" UTC", ""),
        text.replace("Z", "+00:00"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
        if parsed is not None:
            return _naive_utc(parsed)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return _naive_utc(datetime.strptime(text.replace(" UTC", ""), fmt))
        except ValueError:
            continue
    return fallback


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _navigation_status_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    labels = {
        0: "Under way using engine",
        1: "At anchor",
        2: "Not under command",
        3: "Restricted manoeuverability",
        4: "Constrained by draught",
        5: "Moored",
        6: "Aground",
        7: "Engaged in fishing",
        8: "Under way sailing",
    }
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return str(value)
    return labels.get(numeric, f"AIS navigation status {numeric}")


def _vessel_type_from_ais_code(value: Any) -> str:
    code = _ais_type_code(value)
    if code is None:
        return "unknown"
    if 80 <= code <= 89:
        return "tanker"
    if 70 <= code <= 79:
        return "cargo"
    if 60 <= code <= 69:
        return "passenger"
    if code == 30:
        return "fishing"
    if 31 <= code <= 35:
        return "tug_or_special"
    return "unknown"


def _vessel_class_from_ais_code(value: Any) -> str:
    code = _ais_type_code(value)
    if code is None:
        return "AISstream live vessel"
    labels = {
        30: "Fishing vessel",
        31: "Towing vessel",
        32: "Towing vessel over 200m or 25m breadth",
        33: "Dredging or underwater operations",
        34: "Diving operations",
        35: "Military operations",
    }
    if code in labels:
        return labels[code]
    if 60 <= code <= 69:
        return f"AIS passenger class {code}"
    if 70 <= code <= 79:
        return f"AIS cargo class {code}"
    if 80 <= code <= 89:
        return f"AIS tanker class {code}"
    return f"AIS ship type {code}"


def _ais_type_code(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
