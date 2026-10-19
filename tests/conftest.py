"""Shared test safety and authenticated TestClient defaults.

La suite es hermética: el resultado no puede depender del ``.env`` del checkout,
de variables exportadas en la shell, de ``cache/`` o ``data/`` locales ni de la red.

1. Antes de importar la aplicación se desactiva la carga de ``.env``
   (``PYTHON_DOTENV_DISABLED``), se retiran de ``os.environ`` los ajustes y
   credenciales de Gamma heredados de la shell y se fija una línea base explícita.
2. Un guard de red bloquea y registra cualquier conexión saliente que no sea de
   loopback (sockets, asyncio y curl_cffi/yfinance). Un intento bloqueado hace
   fallar el test aunque el código lo capture y degrade en silencio.
3. Los adaptadores externos conocidos (FRED, Tesoro, SEC, Polymarket, Kalshi...)
   quedan fijados a "sin red": fallan al instante como en una caída del proveedor.
   Los tests que necesitan datos usan ``tests/offline_fixtures.py``.
4. Las pruebas en vivo, opt-in mediante ``GAMMA_RUN_LIVE_*``, se marcan con
   ``@pytest.mark.live_network``: recuperan el ``.env`` y la configuración de la
   shell y quedan fuera del guard y de los proveedores offline.
"""

from __future__ import annotations

import asyncio.proactor_events
import asyncio.selector_events
import importlib
import ipaddress
import os
import shutil
import socket
import tempfile
import threading
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn
from urllib.error import URLError
from urllib.parse import urlsplit

import pytest
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# 1. Entorno hermético (debe ejecutarse antes de importar ``src``)
# ---------------------------------------------------------------------------

# build_runtime() llama a load_dotenv() con el .env del checkout. Con esta variable
# python-dotenv (>= 1.2) no carga nada, así que un .env local no altera la suite.
# Al ser una variable de entorno, también la heredan los subprocesos de los tests.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def _assert_dotenv_loading_disabled() -> None:
    from io import StringIO

    from dotenv import load_dotenv

    probe = "GAMMA_DOTENV_DISABLED_PROBE"
    load_dotenv(stream=StringIO(f"{probe}=loaded\n"))
    if os.environ.pop(probe, None) is not None:
        raise RuntimeError(
            "python-dotenv ignora PYTHON_DOTENV_DISABLED (requiere >= 1.2); "
            "actualiza el entorno o la suite leería el .env del checkout."
        )


_assert_dotenv_loading_disabled()

_GAMMA_SETTING_PREFIXES = (
    "AISSTREAM_",
    "BENCHMARK_",
    "COMMODITIES_",
    "EDGAR_",
    "EIA_",
    "GAMMA_",
    "IB_",
    "IBKR_",
    "IV_",
    "MQW_",
    "OPENAI_",
    "PORTFOLIO_",
    "RESEARCH_",
    "SITREP_",
    "YFINANCE_",
)
_GAMMA_SETTING_NAMES = {
    "AUTO_REFRESH_SECONDS",
    "BASE_CURRENCY",
    "CACHE_DIR",
    "HIST_LOOKBACK_DAYS_DEFAULT",
    "MARITIME_PROVIDER",
    "MOCK_DATA",
    "NEWS_PROVIDER",
    "RSS_NEWS_TIMEOUT_SECONDS",
    "SAMPLE_DATA_DIR",
}
_CREDENTIAL_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET")
# Interruptores opt-in de las pruebas en vivo: se leen al importar los módulos de
# test y deben sobrevivir a la limpieza.
_LIVE_OPT_IN_PREFIX = "GAMMA_RUN_LIVE_"


def _documented_setting_names() -> set[str]:
    example = REPO_ROOT / ".env.example"
    if not example.exists():
        return set()
    return {name.upper() for name in dotenv_values(example)}


def _is_gamma_setting(name: str, documented: set[str]) -> bool:
    upper = name.upper()
    if upper.startswith(_LIVE_OPT_IN_PREFIX):
        return False
    return (
        upper in documented
        or upper in _GAMMA_SETTING_NAMES
        or upper.startswith(_GAMMA_SETTING_PREFIXES)
        or upper.endswith(_CREDENTIAL_SUFFIXES)
    )


_DOCUMENTED_SETTINGS = _documented_setting_names()
# Valores heredados de la shell; solo se restauran para las pruebas live_network.
_SHELL_SETTINGS: dict[str, str] = {
    name: os.environ.pop(name)
    for name in list(os.environ)
    if _is_gamma_setting(name, _DOCUMENTED_SETTINGS)
}

# Raíz temporal de la sesión para la caché, el histórico y los logs por defecto, de
# modo que ningún test lea ni escriba cache/ o data/ del checkout.
_SESSION_ROOT = Path(tempfile.mkdtemp(prefix="gamma-tests-"))

# Proveedores simulados: la suite nunca contacta con Yahoo Finance, TWS ni OpenAI.
_SAFETY_PINS = {
    "MOCK_DATA": "true",
    "RESEARCH_MARKET_DATA_PROVIDERS": "mock",
    "SITREP_MARKET_DATA_PROVIDERS": "mock",
    "PORTFOLIO_RISK_HISTORY_PROVIDERS": "mock",
    "COMMODITIES_PROVIDER": "sample",
    "IBKR_COMMODITIES_ENABLED": "",
    "IBKR_COMMODITIES_STARTUP_ENABLED": "",
    "GAMMA_COPILOT_PROVIDER": "mock",
}
# Línea base sobre la que se validan las aserciones. Antes llegaba implícitamente
# del .env del desarrollador (USD, modo auto); el código usa EUR y delayed por
# defecto, así que se fija aquí de forma explícita.
_HERMETIC_BASELINE = {
    "BASE_CURRENCY": "USD",
    "IB_MARKET_DATA_MODE": "auto",
    "NEWS_PROVIDER": "sample",
    "MARITIME_PROVIDER": "sample",
    "CACHE_DIR": str(_SESSION_ROOT / "cache"),
    "PORTFOLIO_HISTORY_DIR": str(_SESSION_ROOT / "data"),
    "SAMPLE_DATA_DIR": str(REPO_ROOT / "sample_data"),
    # edgartools guarda una caché HTTP en ~/.edgar/_tcache que sobrevive entre ejecuciones.
    "EDGAR_LOCAL_DATA_DIR": str(_SESSION_ROOT / "edgar"),
}
os.environ.update(_SAFETY_PINS)
os.environ.update(_HERMETIC_BASELINE)

# edgartools reintenta las descargas con stamina y esperas exponenciales; en modo de
# pruebas cada llamada se intenta una sola vez, así que un fallo de red es inmediato.
try:
    import stamina
except ImportError:  # pragma: no cover - dependencia transitiva de edgartools
    stamina = None
if stamina is not None:
    stamina.set_testing(True, attempts=1)

from fastapi.testclient import TestClient  # noqa: E402

from src.api.session_auth import GAMMA_SESSION_ENV, GAMMA_SESSION_HEADER  # noqa: E402

TEST_GAMMA_SESSION_TOKEN = "test-gamma-session"
NO_TEST_SESSION_HEADER = "X-Test-No-Gamma-Session"

os.environ[GAMMA_SESSION_ENV] = TEST_GAMMA_SESSION_TOKEN

_original_test_client_init = TestClient.__init__


def _test_client_init_with_gamma_session(self: TestClient, *args: Any, **kwargs: Any) -> None:
    headers = dict(kwargs.pop("headers", None) or {})
    skip_session = headers.pop(NO_TEST_SESSION_HEADER, None) == "1"
    if not skip_session:
        headers.setdefault(GAMMA_SESSION_HEADER, TEST_GAMMA_SESSION_TOKEN)
    _original_test_client_init(self, *args, headers=headers, **kwargs)


TestClient.__init__ = _test_client_init_with_gamma_session


# ---------------------------------------------------------------------------
# 2. Guard de red
# ---------------------------------------------------------------------------


class NetworkAccessBlocked(OSError):
    """Conexión saliente rechazada por la suite. Es un OSError para que el código
    degrade igual que sin conexión; el fallo del test lo produce el registro."""


# Puertos de TWS / IB Gateway: aunque sean de loopback, son un servicio externo.
_IBKR_PORTS = frozenset({4001, 4002, 7496, 7497})
_LOCAL_HOST_NAMES = frozenset({"", "localhost", "localhost.localdomain", socket.gethostname().lower()})

_network_lock = threading.Lock()
_blocked_attempts: list[str] = []
_network_guard = {"enabled": True}


def _host_is_local(host: Any) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    text = str(host).strip().strip("[]").lower()
    if text in _LOCAL_HOST_NAMES or text.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback or address.is_unspecified


def _deny(target: str) -> NoReturn:
    detail = f"{target} [hilo {threading.current_thread().name}]"
    with _network_lock:
        _blocked_attempts.append(detail)
    raise NetworkAccessBlocked(f"Acceso de red bloqueado durante los tests: {detail}")


def _check_host_port(host: Any, port: Any, via: str) -> None:
    if not _network_guard["enabled"]:
        return
    if not _host_is_local(host):
        _deny(f"{via} {host}:{port}")
    try:
        numeric_port = int(port) if port is not None else None
    except (TypeError, ValueError):
        numeric_port = None
    if numeric_port in _IBKR_PORTS:
        _deny(f"{via} {host}:{port} (TWS/IB Gateway)")


def _check_socket_address(family: int, address: Any, via: str) -> None:
    # Solo AF_INET/AF_INET6 salen de la máquina; AF_UNIX y similares son locales.
    if family not in (socket.AF_INET, socket.AF_INET6):
        return
    if isinstance(address, tuple) and len(address) >= 2:
        _check_host_port(address[0], address[1], via)


def _check_url(url: Any, via: str) -> None:
    parts = urlsplit(str(url))
    _check_host_port(parts.hostname, parts.port or {"http": 80, "https": 443}.get(parts.scheme), via)


_real_socket_connect = socket.socket.connect
_real_socket_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo


def _guarded_connect(self: socket.socket, address: Any) -> None:
    _check_socket_address(self.family, address, "socket.connect")
    return _real_socket_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
    _check_socket_address(self.family, address, "socket.connect_ex")
    return _real_socket_connect_ex(self, address)


def _guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
    # La resolución DNS de un host externo ya es un intento de red (y puede tardar).
    _check_host_port(host, port, "DNS")
    return _real_getaddrinfo(host, port, *args, **kwargs)


# socket.create_connection y urllib/requests/httpx usan getaddrinfo + connect.
socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
socket.getaddrinfo = _guarded_getaddrinfo

# En Windows el bucle Proactor conecta con ConnectEx y no pasa por socket.connect;
# websockets, ib_insync y anyio terminan en loop.sock_connect.
for _loop_class in (
    asyncio.selector_events.BaseSelectorEventLoop,
    asyncio.proactor_events.BaseProactorEventLoop,
):
    _real_sock_connect = _loop_class.sock_connect

    async def _guarded_sock_connect(self: Any, sock: socket.socket, address: Any, _real: Any = _real_sock_connect) -> Any:
        _check_socket_address(sock.family, address, "asyncio.sock_connect")
        return await _real(self, sock, address)

    _loop_class.sock_connect = _guarded_sock_connect  # type: ignore[method-assign]

# yfinance usa curl_cffi, que resuelve y conecta en C sin pasar por el módulo socket.
try:
    from curl_cffi import requests as _curl_requests
except ImportError:  # pragma: no cover - dependencia opcional de yfinance
    _curl_requests = None
if _curl_requests is not None:
    _real_curl_request = _curl_requests.Session.request
    _real_curl_async_request = _curl_requests.AsyncSession.request

    def _guarded_curl_request(self: Any, method: Any, url: Any, *args: Any, **kwargs: Any) -> Any:
        _check_url(url, "curl_cffi")
        return _real_curl_request(self, method, url, *args, **kwargs)

    async def _guarded_curl_async_request(self: Any, method: Any, url: Any, *args: Any, **kwargs: Any) -> Any:
        _check_url(url, "curl_cffi")
        return await _real_curl_async_request(self, method, url, *args, **kwargs)

    _curl_requests.Session.request = _guarded_curl_request  # type: ignore[method-assign]
    _curl_requests.AsyncSession.request = _guarded_curl_async_request  # type: ignore[method-assign]


def _drain_blocked_attempts() -> list[str]:
    with _network_lock:
        attempts = list(_blocked_attempts)
        _blocked_attempts.clear()
    return attempts


# ---------------------------------------------------------------------------
# 3. Proveedores externos fijados a "sin red"
# ---------------------------------------------------------------------------

# En modo mock solo se simulan IBKR y el histórico de cotizaciones; Macro (FRED,
# Tesoro, calendarios de Fed/BLS/BEA, DBnomics, Census), EIA, cripto, mercados de
# predicción, RSS, SEC y el resumen de fundamentales usan adaptadores reales que
# descargan con urllib. En tests esos adaptadores fallan al instante como en una
# caída del proveedor: el resultado es determinista y no depende de la red, de las
# credenciales del .env ni de reintentos. Los tests que necesitan datos inyectan
# fixtures (tests/offline_fixtures.py) o su propio fetcher; cualquier otra ruta de
# red la detiene el guard anterior.
_OFFLINE_URLOPEN_MODULES = (
    "src.application.fundamentals_service",
    "src.services.commodities_adapters",
    "src.services.crypto_adapters",
    "src.services.fred",
    "src.services.fundamentals_adapters",
    "src.services.macro_adapters",
    "src.services.news_adapters",
    "src.services.prediction_market_adapters",
    "src.services.risk_free_rate",
)


def _offline_urlopen(request: Any, *args: Any, **kwargs: Any) -> NoReturn:
    url = getattr(request, "full_url", request)
    raise URLError(f"proveedor externo sin red en tests: {urlsplit(str(url)).hostname}")


def _offline_edgar_tools() -> tuple[Any, Any, Any]:
    def _unavailable(*args: Any, **kwargs: Any) -> NoReturn:
        raise ConnectionError("SEC EDGAR sin red en tests")

    # (Company, set_identity, get_company_tickers), como _load_edgar_tools().
    return _unavailable, (lambda identity: None), _unavailable


def _offline_provider_modules() -> list[ModuleType]:
    modules = [importlib.import_module(name) for name in _OFFLINE_URLOPEN_MODULES]
    stale = [module.__name__ for module in modules if not callable(getattr(module, "urlopen", None))]
    if stale:
        raise RuntimeError(
            "Estos módulos ya no importan urlopen; actualiza _OFFLINE_URLOPEN_MODULES en tests/conftest.py: "
            + ", ".join(stale)
        )
    return modules


_OFFLINE_PROVIDER_MODULES = _offline_provider_modules()


def _pin_external_providers_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in _OFFLINE_PROVIDER_MODULES:
        monkeypatch.setattr(module, "urlopen", _offline_urlopen)
    monkeypatch.setattr("src.services.fundamentals_adapters._load_edgar_tools", _offline_edgar_tools)


# ---------------------------------------------------------------------------
# 4. Hooks y fixtures
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_network: prueba en vivo opt-in (GAMMA_RUN_LIVE_*) que puede usar la red, "
        "el .env del checkout y la configuración de la shell",
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    shutil.rmtree(_SESSION_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def hermetic_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    live = request.node.get_closest_marker("live_network") is not None
    _drain_blocked_attempts()
    if live:
        # Devuelve a la prueba en vivo lo que la línea base hermética retiró. Los
        # pines de seguridad se mantienen; cada prueba los deshace explícitamente.
        monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
        for name in _HERMETIC_BASELINE:
            monkeypatch.delenv(name, raising=False)
        for name, value in _SHELL_SETTINGS.items():
            if name not in _SAFETY_PINS:
                monkeypatch.setenv(name, value)
        monkeypatch.setitem(_network_guard, "enabled", False)
    else:
        _pin_external_providers_offline(monkeypatch)
    yield
    attempts = _drain_blocked_attempts()
    if attempts and not live:
        counts = Counter(attempts)
        listed = "\n  - ".join(
            attempt if count == 1 else f"{attempt} (x{count})" for attempt, count in counts.items()
        )
        pytest.fail(
            "El test intentó acceder a la red (bloqueado por tests/conftest.py). "
            "Sustituye el proveedor por un stub o fija la configuración hermética:\n  - " + listed,
            pytrace=False,
        )


@pytest.fixture
def blocked_network_attempts():
    """Devuelve una función que vacía y devuelve los intentos bloqueados hasta ese
    momento; solo la usan las pruebas del propio guard."""
    return _drain_blocked_attempts


@pytest.fixture(autouse=True)
def pin_script_runtime_for_deterministic_tests(monkeypatch, request):
    # A user's live Script preference must not turn routine test runs into API
    # execution. Only E4's explicitly opted-in configured-runtime gate reads it.
    if request.node.module.__name__ != "test_script_analytics_live":
        monkeypatch.setenv("GAMMA_RESEARCH_SCRIPT_RUNTIME", "mock")
