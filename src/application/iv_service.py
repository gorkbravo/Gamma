from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from src.application.system_service import normalize_market_data_mode
from src.services.ibkr_client import IBKRClient
from src.services.iv_surface_engine import IVSurfaceEngine, IVSurfaceSnapshot


@dataclass(frozen=True)
class IVSurfaceRequest:
    symbol: str
    market_data_mode: str = "delayed"
    wait_seconds: float = 2.5
    depth_preset: str = "standard"


@dataclass
class IVSurfaceResult:
    snapshot: IVSurfaceSnapshot | None
    warnings: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


@dataclass
class IVStreamResult:
    success: bool
    symbol: str
    status: str
    messages: list[str] = field(default_factory=list)


class IVService:
    def __init__(self, client: IBKRClient, market_data_mode: str = "delayed") -> None:
        self.client = client
        self.market_data_mode = normalize_market_data_mode(market_data_mode)
        self._engine: IVSurfaceEngine | None = None
        self._active_symbol = "SPY"
        self._active_depth_preset = "standard"
        self._engine_config = {
            "max_expiries": int(os.getenv("IV_MAX_EXPIRIES", "6") or 6),
            "strike_band_pct": float(os.getenv("IV_STRIKE_BAND_PCT", "0.02") or 0.02),
            "max_contracts": int(os.getenv("IV_MAX_CONTRACTS", "180") or 180),
            "market_data_line_budget": int(os.getenv("IV_MARKET_DATA_LINE_BUDGET", "60") or 60),
            "reserved_market_data_lines": int(os.getenv("IV_RESERVED_MARKET_DATA_LINES", "10") or 10),
            "include_calls": str(os.getenv("IV_INCLUDE_CALLS", "true")).strip().lower() != "false",
            "include_puts": str(os.getenv("IV_INCLUDE_PUTS", "true")).strip().lower() != "false",
        }

    @staticmethod
    def normalize_market_data_mode(value: str | None) -> str:
        return normalize_market_data_mode(value)

    def set_market_data_mode(self, value: str | None) -> None:
        normalized = self.normalize_market_data_mode(value)
        if normalized == self.market_data_mode:
            return
        was_running = self.is_running()
        active_symbol = self.active_symbol()
        self.stop_stream()
        self.market_data_mode = normalized
        if was_running:
            self.start_stream(active_symbol or "SPY", depth_preset=self._active_depth_preset)

    @staticmethod
    def normalize_depth_preset(value: str | None) -> str:
        preset = str(value or "").strip().lower().replace("-", "_")
        if preset in {"compact", "standard", "deep", "front_deep", "max"}:
            return preset
        return "standard"

    def _depth_config(self, depth_preset: str | None) -> dict:
        preset = self.normalize_depth_preset(depth_preset)
        config = dict(self._engine_config)
        if preset == "compact":
            config.update(
                {
                    "max_expiries": min(config["max_expiries"], int(os.getenv("IV_COMPACT_MAX_EXPIRIES", "4") or 4)),
                    "strike_band_pct": min(
                        config["strike_band_pct"],
                        float(os.getenv("IV_COMPACT_STRIKE_BAND_PCT", "0.015") or 0.015),
                    ),
                    "max_contracts": min(config["max_contracts"], int(os.getenv("IV_COMPACT_MAX_CONTRACTS", "72") or 72)),
                }
            )
        elif preset == "deep":
            config.update(
                {
                    "max_expiries": min(config["max_expiries"], int(os.getenv("IV_DEEP_MAX_EXPIRIES", "4") or 4)),
                    "strike_band_pct": max(
                        config["strike_band_pct"],
                        float(os.getenv("IV_DEEP_STRIKE_BAND_PCT", "0.06") or 0.06),
                    ),
                    "max_contracts": max(config["max_contracts"], int(os.getenv("IV_DEEP_MAX_CONTRACTS", "180") or 180)),
                    "market_data_line_budget": max(
                        config["market_data_line_budget"],
                        int(os.getenv("IV_DEEP_MARKET_DATA_LINE_BUDGET", "120") or 120),
                    ),
                }
            )
        elif preset == "front_deep":
            config.update(
                {
                    "max_expiries": min(config["max_expiries"], int(os.getenv("IV_FRONT_DEEP_MAX_EXPIRIES", "3") or 3)),
                    "strike_band_pct": max(
                        config["strike_band_pct"],
                        float(os.getenv("IV_FRONT_DEEP_STRIKE_BAND_PCT", "0.10") or 0.10),
                    ),
                    "max_contracts": max(config["max_contracts"], int(os.getenv("IV_FRONT_DEEP_MAX_CONTRACTS", "180") or 180)),
                    "market_data_line_budget": max(
                        config["market_data_line_budget"],
                        int(os.getenv("IV_FRONT_DEEP_MARKET_DATA_LINE_BUDGET", "120") or 120),
                    ),
                }
            )
        elif preset == "max":
            config.update(
                {
                    "max_expiries": max(config["max_expiries"], int(os.getenv("IV_MAX_SURFACE_EXPIRIES", "8") or 8)),
                    "strike_band_pct": max(
                        config["strike_band_pct"],
                        float(os.getenv("IV_MAX_SURFACE_STRIKE_BAND_PCT", "0.12") or 0.12),
                    ),
                    "max_contracts": max(config["max_contracts"], int(os.getenv("IV_MAX_SURFACE_CONTRACTS", "220") or 220)),
                    "market_data_line_budget": max(
                        config["market_data_line_budget"],
                        int(os.getenv("IV_MAX_SURFACE_MARKET_DATA_LINE_BUDGET", "240") or 240),
                    ),
                }
            )
        config["depth_preset"] = preset
        return config

    def create_engine(self, market_data_mode: str | None = None, depth_preset: str | None = None) -> IVSurfaceEngine:
        mode = normalize_market_data_mode(market_data_mode or self.market_data_mode)
        return IVSurfaceEngine(client=self.client, market_data_mode=mode, **self._depth_config(depth_preset))

    def start_stream(self, symbol: str = "SPY", depth_preset: str | None = None) -> bool:
        self.stop_stream()
        self._active_symbol = str(symbol or "").strip().upper() or "SPY"
        self._active_depth_preset = self.normalize_depth_preset(depth_preset or self._active_depth_preset)
        self._engine = self.create_engine(depth_preset=self._active_depth_preset)
        return self._engine.start(self._active_symbol)

    def start_stream_session(self, symbol: str = "SPY", depth_preset: str | None = None) -> IVStreamResult:
        normalized_symbol = str(symbol or "").strip().upper() or "SPY"
        if not self.client.mock and not self.client.is_connected():
            return IVStreamResult(
                success=False,
                symbol=normalized_symbol,
                status="Error: Not connected",
                messages=["Connect to IBKR first, then start the surface."],
            )
        if self.start_stream(normalized_symbol, depth_preset=depth_preset):
            return IVStreamResult(
                success=True,
                symbol=normalized_symbol,
                status=f"Starting ({normalized_symbol})",
            )
        return IVStreamResult(
            success=False,
            symbol=normalized_symbol,
            status="Error",
            messages=["Unable to start options surface engine."],
        )

    def stop_stream(self) -> None:
        if self._engine is not None:
            self._engine.stop()
            self._engine = None

    def is_running(self) -> bool:
        return self._engine.is_running() if self._engine is not None else False

    def status_text(self) -> str:
        if self._engine is None:
            return "Idle"
        return self._engine.status_text()

    def drain_messages(self) -> list[str]:
        if self._engine is None:
            return []
        return self._engine.drain_messages()

    def latest_snapshot(self) -> IVSurfaceSnapshot | None:
        if self._engine is None:
            return None
        return self._engine.snapshot()

    def active_symbol(self) -> str | None:
        snapshot = self.latest_snapshot()
        if snapshot is not None:
            return snapshot.symbol
        return self._active_symbol

    def get_surface(self, request: IVSurfaceRequest) -> IVSurfaceResult:
        symbol = str(request.symbol or "").strip().upper() or "SPY"
        mode = self.normalize_market_data_mode(request.market_data_mode or self.market_data_mode)
        if self.client.mock:
            return IVSurfaceResult(snapshot=self._mock_snapshot(symbol, depth_preset=request.depth_preset))
        if not self.client.is_connected():
            return IVSurfaceResult(
                snapshot=None,
                warnings=["Connect to IBKR before requesting an options surface."],
            )

        depth_preset = self.normalize_depth_preset(request.depth_preset)
        warnings: list[str] = []
        if self.is_running():
            self.stop_stream()
            warnings.append("Stopped the previous live IV stream before loading a one-shot surface snapshot.")

        messages: list[str] = []
        latest = None
        loaded_preset: str | None = None
        presets = self._surface_depth_attempts(depth_preset)
        for index, preset in enumerate(presets):
            wait_seconds = float(request.wait_seconds or 0.0) if index == 0 else min(float(request.wait_seconds or 0.0), 2.5)
            latest, attempt_messages = self._collect_surface_snapshot(
                symbol=symbol,
                market_data_mode=mode,
                depth_preset=preset,
                wait_seconds=wait_seconds,
            )
            messages.extend(attempt_messages)
            if latest is not None:
                loaded_preset = preset
                break

        if latest is None:
            warnings.append(f"No options surface snapshot available yet for {symbol}.")
        elif loaded_preset and loaded_preset != depth_preset:
            warnings.append(
                f"Requested {depth_preset} options depth was unavailable; loaded the deepest successful "
                f"{loaded_preset} snapshot instead."
            )
        return IVSurfaceResult(snapshot=latest, warnings=warnings, messages=messages)

    def _mock_snapshot(self, symbol: str, depth_preset: str | None = None) -> IVSurfaceSnapshot:
        engine = self.create_engine(self.market_data_mode, depth_preset=depth_preset)
        return engine.build_mock_snapshot(symbol)

    def _surface_depth_attempts(self, depth_preset: str) -> list[str]:
        if depth_preset == "max":
            return ["max", "front_deep", "deep", "standard", "compact"]
        if depth_preset == "front_deep":
            return ["front_deep", "deep", "standard", "compact"]
        if depth_preset == "deep":
            return ["deep", "standard", "compact"]
        return [depth_preset]

    def _collect_surface_snapshot(
        self,
        *,
        symbol: str,
        market_data_mode: str,
        depth_preset: str,
        wait_seconds: float,
    ) -> tuple[IVSurfaceSnapshot | None, list[str]]:
        engine = self.create_engine(market_data_mode, depth_preset=depth_preset)
        if not engine.start(symbol):
            return None, engine.drain_messages()

        deadline = time.time() + max(float(wait_seconds or 0.0), 0.5)
        latest = None
        try:
            while time.time() < deadline:
                latest = engine.snapshot()
                if latest is not None:
                    break
                time.sleep(0.1)
        finally:
            messages = engine.drain_messages()
            engine.stop()
        return latest, messages
