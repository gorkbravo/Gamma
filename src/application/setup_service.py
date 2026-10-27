from __future__ import annotations

"""Asistente de primer arranque: preferencias de inicio, informe de preparación y cambios.

Responsabilidades:

1. ``resolve_startup_settings`` decide al construir el runtime el modo de datos, la divisa
   base y el modo de datos de mercado. Precedencia: argumento explícito > variable de
   entorno (``.env``) > preferencia guardada por el asistente > valor por defecto.
2. ``build_setup_report`` describe el estado actual para el asistente y Settings sin
   exponer secretos: de las claves de API solo se informa si existen.
3. ``apply_setup_update`` guarda las elecciones del usuario. La divisa base y el modo de
   datos de mercado se aplican en caliente; el cambio demo/live necesita reiniciar porque
   todo el runtime (cliente IBKR, proveedores) se construye para un único modo.

Limitación conocida: la cobertura por pestaña replica la lógica de selección de
proveedores de ``runtime.py`` a partir de las mismas variables de entorno; si esa lógica
cambia, este mapa debe actualizarse (lo cubren los tests de ``tests/test_system_setup.py``).
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.application.system_service import normalize_market_data_mode
from src.models.setup import (
    SetupConfigLocation,
    SetupCopilotState,
    SetupCoverageRow,
    SetupDataModeState,
    SetupIbkrState,
    SetupProviderRow,
    SetupReport,
    SetupSecIdentityState,
    SetupValueState,
)
from src.services.setup_store import (
    SETUP_SCHEMA_VERSION,
    SetupPreferences,
    SetupStore,
    SetupStoreError,
    normalize_sec_identity,
)
from src.utils.time import now_utc

if TYPE_CHECKING:
    from src.application.runtime import ApplicationRuntime

# .env de la raíz del repositorio: el que se usa en desarrollo.
REPO_ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"


def resolve_env_file_path() -> Path:
    """Fichero .env que lee ``build_runtime`` (y que el asistente indica al usuario).

    - ``GAMMA_ENV_FILE``, si se define, tiene prioridad.
    - En el backend empaquetado con PyInstaller no hay repositorio: la ruta relativa al código
      caería dentro de ``_internal``. Se usa ``<GAMMA_APP_DATA_DIR>/.env``, la carpeta de datos
      que la app de escritorio pasa al backend (``%APPDATA%/com.gamma.shell/runtime``), o
      la carpeta del ejecutable si no se recibe.
    - En desarrollo, el ``.env`` de la raíz del repositorio.
    """
    explicit = (os.getenv("GAMMA_ENV_FILE") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    if getattr(sys, "frozen", False):
        app_data = (os.getenv("GAMMA_APP_DATA_DIR") or "").strip()
        if app_data:
            return Path(app_data).expanduser() / ".env"
        return Path(sys.executable).resolve().parent / ".env"
    return REPO_ENV_FILE_PATH
BASE_CURRENCY_OPTIONS = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD"]
MARKET_DATA_MODE_OPTIONS = ["delayed", "live", "auto"]
DEFAULT_BASE_CURRENCY = "EUR"

# Qué desbloquea cada clave opcional, en lenguaje de producto (el registro de capacidades
# describe el proveedor; aquí interesa qué cambia en Gamma al configurarlo).
_PROVIDER_UNLOCKS = {
    "fred": "FRED series in Macro and the risk-free rate used by Risk. FRED's API expects a free key.",
    "census": "Live US bilateral trade in Macro / Trade Partners; without it Gamma shows curated rows.",
    "coingecko": "Higher CoinGecko rate limits in Crypto. Crypto works without it on the public tier.",
}

# Mismos alias que _build_commodities_provider / _build_maritime_provider en runtime.py.
_COMMODITIES_IBKR_IDS = {"ibkr", "tws", "ibkr_eia", "ibkr_futures"}
_COMMODITIES_EIA_IDS = {"eia", "official", "eia_fred", "fred"}
_MARITIME_AISSTREAM_IDS = {"aisstream", "aisstream_live", "live"}

# Variable opt-in del auto-connect a TWS (GUA-20261021-14a); ver runtime.start_ib_auto_connect.
_IB_AUTO_CONNECT_ENV = "IB_AUTO_CONNECT"


@dataclass(frozen=True)
class StartupSettings:
    mock_mode: bool
    mock_mode_source: str
    base_currency: str
    base_currency_source: str
    market_data_mode: str
    market_data_mode_source: str
    preferences: SetupPreferences = field(default_factory=SetupPreferences)
    warnings: list[str] = field(default_factory=list)


def resolve_startup_settings(
    preferences: SetupPreferences,
    *,
    mock_mode_argument: bool | None = None,
    warnings: list[str] | None = None,
) -> StartupSettings:
    """Resuelve los ajustes de arranque respetando la precedencia documentada en el módulo."""
    mock_env = os.getenv("MOCK_DATA")
    if mock_mode_argument is not None:
        mock_mode, mock_source = bool(mock_mode_argument), "argument"
    elif mock_env is not None:
        # Igual que antes de existir el asistente: cualquier valor distinto de "true" es live.
        mock_mode, mock_source = mock_env.strip().lower() == "true", "environment"
    elif preferences.data_mode is not None:
        mock_mode, mock_source = preferences.data_mode == "demo", "setup"
    else:
        mock_mode, mock_source = True, "default"

    currency_env = (os.getenv("BASE_CURRENCY") or "").strip()
    if currency_env:
        base_currency, currency_source = currency_env.upper(), "environment"
    elif preferences.base_currency:
        base_currency, currency_source = preferences.base_currency, "setup"
    else:
        base_currency, currency_source = DEFAULT_BASE_CURRENCY, "default"

    market_env = (os.getenv("IB_MARKET_DATA_MODE") or "").strip()
    if market_env:
        market_data_mode, market_source = normalize_market_data_mode(market_env), "environment"
    elif preferences.market_data_mode:
        market_data_mode, market_source = preferences.market_data_mode, "setup"
    else:
        market_data_mode, market_source = normalize_market_data_mode(None), "default"

    return StartupSettings(
        mock_mode=mock_mode,
        mock_mode_source=mock_source,
        base_currency=base_currency,
        base_currency_source=currency_source,
        market_data_mode=market_data_mode,
        market_data_mode_source=market_source,
        preferences=preferences,
        warnings=list(warnings or []),
    )


def sec_identity_tuple(preferences: SetupPreferences) -> tuple[str, str] | None:
    identity = preferences.sec_identity
    return (identity.name, identity.email) if identity is not None else None


# ── Informe ──────────────────────────────────────────────────────────────


def build_setup_report(runtime: "ApplicationRuntime") -> SetupReport:
    store = _require_store(runtime)
    load = store.load()
    preferences = load.preferences
    startup = runtime.startup_settings
    mock_mode = runtime.mock_mode
    current_mode = "demo" if mock_mode else "live"
    mock_source = startup.mock_mode_source if startup else "default"
    mode_locked = "MOCK_DATA" if mock_source == "environment" else None
    restart_required = (
        preferences.data_mode is not None
        and preferences.data_mode != current_mode
        and mode_locked is None
        and mock_source != "argument"
    )
    copilot = _copilot_state(mock_mode)
    connected = bool(not mock_mode and _safe_is_connected(runtime))
    env_file = resolve_env_file_path()

    warnings = [*load.warnings]
    if startup is not None:
        warnings.extend(startup.warnings)
    if mode_locked and preferences.data_mode and preferences.data_mode != current_mode:
        warnings.append(
            f"The saved {preferences.data_mode} preference is ignored because MOCK_DATA is set in the environment."
        )

    return SetupReport(
        generated_at=now_utc(),
        schema_version=SETUP_SCHEMA_VERSION,
        first_run=preferences.completed_at is None,
        completed_at=preferences.completed_at,
        data_mode=SetupDataModeState(
            current=current_mode,
            preference=preferences.data_mode,
            source=mock_source,
            restart_required=restart_required,
            locked_by=mode_locked,
            detail=_data_mode_detail(current_mode, restart_required, preferences.data_mode),
        ),
        base_currency=SetupValueState(
            current=runtime.base_currency,
            source=_value_source(startup.base_currency_source if startup else "default", preferences.base_currency, runtime.base_currency),
            locked_by="BASE_CURRENCY" if startup and startup.base_currency_source == "environment" else None,
            options=_with_current(BASE_CURRENCY_OPTIONS, runtime.base_currency),
        ),
        market_data_mode=SetupValueState(
            current=runtime.market_data_mode,
            source=_value_source(
                startup.market_data_mode_source if startup else "default",
                preferences.market_data_mode,
                runtime.market_data_mode,
            ),
            locked_by="IB_MARKET_DATA_MODE" if startup and startup.market_data_mode_source == "environment" else None,
            options=list(MARKET_DATA_MODE_OPTIONS),
        ),
        ibkr=_ibkr_state(runtime, connected),
        sec_identity=_sec_identity_state(runtime, preferences),
        copilot=copilot,
        providers=_provider_rows(runtime),
        coverage_by_mode={
            "demo": _coverage_rows(mock_mode=True, connected=False, copilot=_copilot_state(True)),
            "live": _coverage_rows(mock_mode=False, connected=connected, copilot=_copilot_state(False)),
        },
        config=SetupConfigLocation(
            env_file_path=str(env_file),
            env_file_present=env_file.exists(),
            setup_file_path=str(store.path),
        ),
        warnings=warnings,
    )


def _value_source(startup_source: str, saved: str | None, current: str) -> str:
    # Un cambio en caliente desde Settings o el asistente se guarda como preferencia.
    if startup_source == "environment":
        return "environment"
    if saved is not None and saved == current:
        return "setup"
    return startup_source


def _with_current(options: list[str], current: str) -> list[str]:
    return options if current in options else [*options, current]


def _data_mode_detail(current_mode: str, restart_required: bool, preference: str | None) -> str:
    if restart_required and preference == "live":
        return "Live data is saved and takes effect after Gamma restarts. Gamma is still running in demo."
    if restart_required and preference == "demo":
        return "Demo mode is saved and takes effect after Gamma restarts. Gamma is still running on live data."
    if current_mode == "demo":
        return "Sample portfolio and synthetic prices; free public research sources stay live when reachable."
    return "Your IBKR account through TWS plus configured research providers."


def _safe_is_connected(runtime: "ApplicationRuntime") -> bool:
    try:
        return bool(runtime.client.is_connected())
    except Exception:
        return False


def _ibkr_state(runtime: "ApplicationRuntime", connected: bool) -> SetupIbkrState:
    client = runtime.client
    host = str(getattr(client, "host", "127.0.0.1"))
    port = int(getattr(client, "port", 7497) or 7497)
    client_id = int(getattr(client, "client_id", 1) or 1)
    account_configured = bool(getattr(client, "account", None))
    steps = [
        "Start Trader Workstation (TWS) and log in.",
        "In TWS open Global Configuration > API > Settings and enable ActiveX and Socket Clients.",
        f"Check the socket port is {port} (TWS defaults: 7497 for paper trading, 7496 for live).",
        "Keep Read-Only API enabled. Gamma never places orders.",
        "IB Gateway is not supported yet; use TWS.",
    ]
    if runtime.mock_mode:
        return SetupIbkrState(
            status="demo",
            host=host,
            port=port,
            client_id=client_id,
            account_configured=account_configured,
            detail="Demo mode does not connect to a broker. These steps apply once Gamma runs on live data.",
            steps=steps,
        )
    if connected:
        account = getattr(client, "active_account", None) or getattr(client, "account", None)
        detail = f"Connected to {host}:{port}" + (f" as {account}." if account else ".")
        return SetupIbkrState(
            status="connected",
            host=host,
            port=port,
            client_id=client_id,
            account_configured=account_configured,
            detail=detail,
            steps=[],
        )
    detail = f"Not connected to TWS at {host}:{port}. Portfolio, Risk and Options need this connection."
    auto_connect = getattr(runtime, "ib_auto_connect", None)
    if auto_connect is not None and auto_connect.in_progress():
        detail = f"Connecting to TWS at {host}:{port} (auto-connect at startup)."
    elif auto_connect is not None and auto_connect.outcome == "failed":
        detail = (
            f"Auto-connect at startup did not reach TWS at {host}:{port} and is not retried. "
            "Start TWS, then use Test connection."
        )
    elif not _env_flag(_IB_AUTO_CONNECT_ENV):
        # GUA-20261021-14a: el backend no conecta solo salvo que se pida.
        steps.append(
            f"Optional: set {_IB_AUTO_CONNECT_ENV}=true in the environment or .env file so Gamma connects "
            "once when it starts."
        )
    return SetupIbkrState(
        status="disconnected",
        host=host,
        port=port,
        client_id=client_id,
        account_configured=account_configured,
        detail=detail,
        steps=steps,
    )


def _env_flag(name: str) -> bool:
    return _env_choice(name, "") in {"1", "true", "yes", "on"}


def _sec_identity_state(runtime: "ApplicationRuntime", preferences: SetupPreferences) -> SetupSecIdentityState:
    adapter = runtime.sec_fundamentals_adapter
    source = str(getattr(adapter, "identity_source", "missing"))
    saved = preferences.sec_identity
    if source == "environment":
        return SetupSecIdentityState(
            status="configured",
            source="environment",
            locked_by="GAMMA_SEC_USER_NAME / GAMMA_SEC_USER_EMAIL",
            name=None,
            email=None,
            detail="Set by GAMMA_SEC_USER_NAME and GAMMA_SEC_USER_EMAIL in the environment.",
        )
    if source == "setup" and saved is not None:
        return SetupSecIdentityState(
            status="configured",
            source="setup",
            locked_by=None,
            name=saved.name,
            email=saved.email,
            detail="SEC EDGAR and BLS release-calendar requests identify themselves with this name and email.",
        )
    detail = (
        "Fundamentals, Copilot company lookup, Script Fundamentals exports, SEC press releases and the "
        "BLS release dates in the Macro calendar stay unavailable until you save your name and email."
    )
    if getattr(adapter, "partial_environment", False):
        detail = (
            "Only one of GAMMA_SEC_USER_NAME / GAMMA_SEC_USER_EMAIL is set, so it is ignored. " + detail
        )
    return SetupSecIdentityState(
        status="missing",
        source="missing",
        locked_by=None,
        name=None,
        email=None,
        detail=detail,
    )


def _copilot_state(mock_mode: bool) -> SetupCopilotState:
    provider = (os.getenv("GAMMA_COPILOT_PROVIDER", "openai") or "openai").strip().lower()
    env_vars = ["GAMMA_COPILOT_PROVIDER", "OPENAI_API_KEY"]
    if provider in {"disabled", "none", "off"}:
        return SetupCopilotState("disabled", provider, "Copilot is disabled by GAMMA_COPILOT_PROVIDER.", env_vars)
    if provider in {"mock", "demo", "offline"}:
        if mock_mode:
            return SetupCopilotState(
                "demo", provider, "Canned demo answers from the mock provider; no model is called.", env_vars
            )
        return SetupCopilotState(
            "unavailable",
            provider,
            "The mock Copilot provider is disabled on live data. Set GAMMA_COPILOT_PROVIDER=openai and OPENAI_API_KEY.",
            env_vars,
        )
    if provider != "openai":
        return SetupCopilotState("unavailable", provider, f"Unsupported Copilot provider: {provider}.", env_vars)
    if (os.getenv("OPENAI_API_KEY", "") or "").strip():
        return SetupCopilotState(
            "configured", provider, "OpenAI key configured. Copilot requests are billed to that account.", env_vars
        )
    return SetupCopilotState(
        "missing_key",
        provider,
        "Copilot needs OPENAI_API_KEY. In demo mode, GAMMA_COPILOT_PROVIDER=mock gives canned answers instead.",
        env_vars,
    )


def _provider_rows(runtime: "ApplicationRuntime") -> list[SetupProviderRow]:
    rows: list[SetupProviderRow] = []
    for capability in runtime.provider_capabilities.list_capabilities(include_planned=False):
        key_vars = [name for name in capability.credential_env_vars if name.endswith("_API_KEY")]
        if not key_vars or capability.provider_id == "openai_copilot":
            continue
        unlocks = _provider_unlocks(capability.provider_id)
        if unlocks is None:
            unlocks = capability.configuration_notes[0] if capability.configuration_notes else capability.display_name
        rows.append(
            SetupProviderRow(
                provider_id=capability.provider_id,
                display_name=capability.display_name,
                configured=any((os.getenv(name, "") or "").strip() for name in key_vars),
                env_vars=key_vars,
                unlocks=unlocks,
            )
        )
    return rows


def _provider_unlocks(provider_id: str) -> str | None:
    """Qué añade cada clave, coherente con cómo runtime.py la usa realmente.

    GUA-20261021-14c: la fila EIA pedía "COMMODITIES_PROVIDER=eia" aunque con
    COMMODITIES_PROVIDER=ibkr la misma clave ya alimenta la referencia EIA bajo los futuros.
    """
    if provider_id == "eia":
        provider = _env_choice("COMMODITIES_PROVIDER", "sample")
        base = "Official EIA inventories and energy fundamentals in Commodities"
        if provider in _COMMODITIES_IBKR_IDS:
            return f"{base}, as reference data under the IBKR futures (COMMODITIES_PROVIDER={provider} reads this key)."
        if provider in _COMMODITIES_EIA_IDS:
            return f"{base} (COMMODITIES_PROVIDER={provider})."
        return (
            f"{base}. Read when COMMODITIES_PROVIDER=ibkr (reference data under IBKR futures) "
            "or COMMODITIES_PROVIDER=eia (EIA and FRED without IBKR futures)."
        )
    if provider_id == "aisstream":
        provider = _env_choice("MARITIME_PROVIDER", "sample")
        if provider in _MARITIME_AISSTREAM_IDS:
            return f"Live vessel positions in Sealanes (MARITIME_PROVIDER={provider})."
        return "Live vessel positions in Sealanes. Also set MARITIME_PROVIDER=aisstream."
    return _PROVIDER_UNLOCKS.get(provider_id)


def _env_choice(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip().lower()


def _history_source(env_var: str, mock_mode: bool, live_default: str) -> tuple[str, str]:
    configured = _env_choice(env_var, "")
    provider_ids = [item.strip() for item in configured.split(",") if item.strip()] if configured else []
    if not provider_ids:
        provider_ids = ["mock"] if mock_mode else [item.strip() for item in live_default.split(",")]
    labels = {
        "mock": "synthetic sample history",
        "sample": "synthetic sample history",
        "yfinance": "Yahoo Finance",
        "yahoo": "Yahoo Finance",
        "ibkr": "IBKR",
        "tws": "IBKR",
    }
    names = [labels.get(item, item) for item in provider_ids]
    if all(item in {"mock", "sample", "offline", "demo"} for item in provider_ids):
        return ("sample" if mock_mode else "unavailable"), "Synthetic sample price history."
    if all(item in {"ibkr", "tws"} for item in provider_ids):
        return "broker", "Price history from IBKR."
    return "public", f"Price history from {', then '.join(dict.fromkeys(names))}."


def _coverage_rows(*, mock_mode: bool, connected: bool, copilot: SetupCopilotState) -> list[SetupCoverageRow]:
    research_source, research_detail = _history_source("RESEARCH_MARKET_DATA_PROVIDERS", mock_mode, "yfinance,ibkr")
    sitrep_source, _ = _history_source("SITREP_MARKET_DATA_PROVIDERS", mock_mode, "yfinance")
    script_runtime = _env_choice("GAMMA_RESEARCH_SCRIPT_RUNTIME", "mock")
    script_note = (
        " Script runs isolated Python through OpenAI."
        if script_runtime == "openai"
        else " Script runs in safe preview and does not execute code."
    )
    census = bool((os.getenv("CENSUS_API_KEY", "") or "").strip())
    broker_note = "connected" if connected else "not connected"

    rows: list[SetupCoverageRow] = []
    if mock_mode:
        rows.extend(
            [
                SetupCoverageRow("portfolio", "Portfolio", "sample", "Sample IBKR-style account with fixed positions and local history."),
                SetupCoverageRow("risk", "Risk", "sample", "Risk analytics on the sample account and synthetic price history."),
                SetupCoverageRow("iv", "Options", "sample", "Synthetic option chain and implied-volatility surface."),
            ]
        )
    else:
        rows.extend(
            [
                SetupCoverageRow("portfolio", "Portfolio", "broker", f"Your IBKR account through TWS ({broker_note})."),
                SetupCoverageRow("risk", "Risk", "broker", "Account positions from IBKR; history from IBKR, then Yahoo Finance."),
                SetupCoverageRow("iv", "Options", "broker", "IBKR option chains; needs TWS and option market-data entitlements."),
            ]
        )

    # Igual que _build_news_providers: solo RSS es live; las noticias de muestra no se cargan en live.
    news_ids = {item.strip() for item in _env_choice("NEWS_PROVIDER", "sample").split(",") if item.strip()}
    if news_ids & {"rss", "rss_news", "rss_news_feeds"}:
        news_phrase = "RSS news"
    else:
        news_phrase = "sample news" if mock_mode else "no news feed (set NEWS_PROVIDER=rss)"
    commodities_source, commodities_detail = _commodities_coverage(mock_mode)
    sitrep_parts = {
        "sample": "sample market tape",
        "public": "Yahoo Finance market tape",
        "broker": "IBKR market tape",
        "unavailable": "no market tape",
    }
    commodities_phrase = {
        "sample": "sample commodities",
        "public": "EIA commodities",
        "mixed": "IBKR commodities",
        "unavailable": "no commodities feed",
    }.get(commodities_source, "commodities")
    rows.extend(
        [
            SetupCoverageRow(
                "sitrep",
                "SITREP",
                "mixed",
                f"Combines {sitrep_parts.get(sitrep_source, 'market tape')}, public macro and prediction markets, "
                f"{news_phrase} and {commodities_phrase}.",
            ),
            SetupCoverageRow("equity_research", "Equity Research", research_source, research_detail),
            SetupCoverageRow("strategy_lab", "Strategy Lab", research_source, research_detail + script_note),
            SetupCoverageRow(
                "macro",
                "Macro",
                "public",
                "FRED, US Treasury, DB.nomics and official calendars over the network."
                + ("" if census else " Trade Partners shows curated rows without CENSUS_API_KEY."),
            ),
            SetupCoverageRow("prediction_markets", "Prediction Markets", "public", "Polymarket and Kalshi public data."),
            SetupCoverageRow("crypto", "Crypto", "public", "CoinGecko and GeckoTerminal public data."),
            SetupCoverageRow(
                "fundamentals",
                "Fundamentals",
                "public",
                "SEC EDGAR filings over the network; valuation prices from "
                + ("synthetic sample history." if mock_mode else "IBKR."),
            ),
            SetupCoverageRow("commodities", "Commodities", commodities_source, commodities_detail),
            _maritime_coverage(mock_mode),
            _copilot_coverage(copilot),
        ]
    )
    return rows


def _commodities_coverage(mock_mode: bool) -> tuple[str, str]:
    provider = _env_choice("COMMODITIES_PROVIDER", "sample")
    has_eia = bool((os.getenv("EIA_API_KEY", "") or "").strip())
    if provider in {"sample", "mock", "offline", "demo"}:
        if mock_mode:
            return "sample", "Sample curves, inventories and events."
        return (
            "unavailable",
            "No live commodities provider: set COMMODITIES_PROVIDER=ibkr (IBKR futures, plus EIA reference data "
            "with EIA_API_KEY) or COMMODITIES_PROVIDER=eia with EIA_API_KEY.",
        )
    if provider in _COMMODITIES_IBKR_IDS:
        # Igual que _build_commodities_provider: con EIA_API_KEY la referencia es EIA, sin ella no hay
        # inventarios oficiales (GUA-20261021-14c).
        if has_eia:
            return "mixed", "IBKR futures (needs TWS) with EIA inventories as reference data."
        if mock_mode:
            return "mixed", "IBKR futures (needs TWS) with sample reference data; EIA_API_KEY adds EIA inventories."
        return "mixed", "IBKR futures (needs TWS); EIA inventories need EIA_API_KEY."
    if provider in _COMMODITIES_EIA_IDS:
        if has_eia:
            return "public", "Official EIA data" + (" with sample reference curves." if mock_mode else ".")
        if mock_mode:
            return "sample", "Sample data: COMMODITIES_PROVIDER=eia needs EIA_API_KEY."
        return "unavailable", "COMMODITIES_PROVIDER=eia needs EIA_API_KEY."
    if mock_mode:
        return "sample", f"Unsupported COMMODITIES_PROVIDER={provider}; sample data is shown."
    return "unavailable", f"Unsupported COMMODITIES_PROVIDER={provider}."


def _maritime_coverage(mock_mode: bool) -> SetupCoverageRow:
    provider = _env_choice("MARITIME_PROVIDER", "sample")
    has_key = bool((os.getenv("AISSTREAM_API_KEY", "") or "").strip())
    if provider in {"aisstream", "aisstream_live", "live"}:
        if has_key:
            return SetupCoverageRow("maritime", "Sealanes", "public", "Live AIS from AISstream; coverage varies by region.")
        return SetupCoverageRow("maritime", "Sealanes", "unavailable", "MARITIME_PROVIDER=aisstream needs AISSTREAM_API_KEY.")
    if mock_mode:
        return SetupCoverageRow("maritime", "Sealanes", "sample", "Sample vessels, routes and chokepoints.")
    return SetupCoverageRow("maritime", "Sealanes", "unavailable", "Set MARITIME_PROVIDER=aisstream with AISSTREAM_API_KEY.")


def _copilot_coverage(copilot: SetupCopilotState) -> SetupCoverageRow:
    if copilot.status == "configured":
        return SetupCoverageRow("copilot", "Copilot", "model", "OpenAI model grounded in Gamma's read-only tools.")
    if copilot.status == "demo":
        return SetupCoverageRow("copilot", "Copilot", "sample", "Canned demo answers; no model is called.")
    return SetupCoverageRow("copilot", "Copilot", "unavailable", copilot.detail)


# ── Cambios ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SetupUpdate:
    data_mode: str | None = None
    base_currency: str | None = None
    market_data_mode: str | None = None
    # ``sec_identity`` presente con ``clear_sec_identity=False`` guarda; ``clear_sec_identity`` borra.
    sec_identity: tuple[str, str] | None = None
    clear_sec_identity: bool = False
    complete: bool | None = None


def apply_setup_update(runtime: "ApplicationRuntime", update: SetupUpdate) -> list[str]:
    """Valida, aplica y persiste las elecciones del asistente. Devuelve notas para el usuario.

    Lanza ValueError ante entradas inválidas antes de modificar nada.
    """
    store = _require_store(runtime)
    if store.load().read_only:
        # Se comprueba antes de aplicar nada en caliente para no dejar cambios a medias.
        raise SetupStoreError(
            "Setup preferences were written by a newer Gamma version and were not overwritten."
        )
    changes: dict[str, Any] = {}
    lines: list[str] = []

    data_mode = None
    if update.data_mode is not None:
        data_mode = str(update.data_mode).strip().lower()
        if data_mode not in {"demo", "live"}:
            raise ValueError("data_mode must be 'demo' or 'live'.")
    base_currency = None
    if update.base_currency is not None:
        base_currency = runtime._normalize_base_currency(update.base_currency)
    market_data_mode = None
    if update.market_data_mode is not None:
        market_data_mode = str(update.market_data_mode).strip().lower()
        if market_data_mode not in MARKET_DATA_MODE_OPTIONS:
            raise ValueError("market_data_mode must be one of delayed, live or auto.")
    identity = None
    if update.sec_identity is not None and not update.clear_sec_identity:
        identity = normalize_sec_identity(*update.sec_identity)

    # A partir de aquí las entradas son válidas: se aplican y se guardan.
    if data_mode is not None:
        changes["data_mode"] = data_mode
        current = "demo" if runtime.mock_mode else "live"
        startup = runtime.startup_settings
        if startup is not None and startup.mock_mode_source == "environment":
            lines.append("MOCK_DATA is set in the environment, so the saved data mode applies only after it is removed.")
        elif data_mode != current:
            lines.append(f"Restart Gamma to switch to {'live data' if data_mode == 'live' else 'demo mode'}.")
    if base_currency is not None:
        _, currency_lines = runtime.set_base_currency(base_currency)
        lines.extend(currency_lines)
        changes["base_currency"] = base_currency
    if market_data_mode is not None:
        runtime.set_market_data_mode(market_data_mode)
        changes["market_data_mode"] = market_data_mode
    if identity is not None:
        changes["sec_identity"] = identity
    elif update.clear_sec_identity:
        changes["sec_identity"] = None
    if update.complete is True:
        changes["completed_at"] = now_utc()
    elif update.complete is False:
        changes["completed_at"] = None

    if changes:
        preferences = store.update(**changes)
        if "sec_identity" in changes and runtime.sec_fundamentals_adapter is not None:
            source = runtime.sec_fundamentals_adapter.apply_identity(sec_identity_tuple(preferences))
            if source == "environment":
                lines.append("GAMMA_SEC_USER_NAME / GAMMA_SEC_USER_EMAIL in the environment still take precedence.")
            elif identity is not None:
                lines.append("SEC identity saved for Fundamentals.")
            else:
                lines.append("SEC identity removed. Fundamentals stays unavailable until a new one is saved.")
    return lines


def persist_runtime_preference(runtime: "ApplicationRuntime", **changes: Any) -> None:
    """Guarda un cambio hecho desde Settings (divisa base o modo de datos de mercado).

    Es best-effort: si el store no puede escribir, el cambio en caliente sigue siendo válido.
    """
    store = runtime.setup_store
    if store is None:
        return
    try:
        store.update(**changes)
    except Exception:
        return


def _require_store(runtime: "ApplicationRuntime") -> SetupStore:
    if runtime.setup_store is None:
        raise RuntimeError("Setup preferences are unavailable in this runtime.")
    return runtime.setup_store
