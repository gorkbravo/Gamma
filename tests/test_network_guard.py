"""Pruebas del aislamiento de la suite definido en tests/conftest.py."""

from __future__ import annotations

import asyncio
import os
import socket
import time

import pytest
from dotenv import load_dotenv

# Rango TEST-NET-3 (RFC 5737): nunca enrutable, así que un guard roto se nota por
# timeout en lugar de contactar con un tercero.
UNROUTABLE_IP = "203.0.113.10"


def test_dns_lookup_of_external_host_is_blocked_and_recorded(blocked_network_attempts):
    started = time.monotonic()
    with pytest.raises(OSError, match="bloqueado"):
        socket.create_connection(("example.com", 443), timeout=5)
    assert time.monotonic() - started < 1.0
    attempts = blocked_network_attempts()
    assert len(attempts) == 1
    assert "DNS example.com:443" in attempts[0]


def test_ip_literal_connection_is_blocked(blocked_network_attempts):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        with pytest.raises(OSError, match="bloqueado"):
            sock.connect((UNROUTABLE_IP, 443))
    assert [attempt.split(" [")[0] for attempt in blocked_network_attempts()] == [
        f"socket.connect {UNROUTABLE_IP}:443"
    ]


def test_asyncio_connection_is_blocked(blocked_network_attempts):
    async def _open() -> None:
        await asyncio.wait_for(asyncio.open_connection(UNROUTABLE_IP, 443), timeout=5)

    with pytest.raises(OSError, match="bloqueado"):
        asyncio.run(_open())
    assert any("asyncio.sock_connect" in attempt for attempt in blocked_network_attempts())


def test_curl_cffi_request_is_blocked(blocked_network_attempts):
    curl_requests = pytest.importorskip("curl_cffi.requests")
    with pytest.raises(OSError, match="bloqueado"):
        curl_requests.Session().get("https://query1.finance.yahoo.com/v8/finance/chart/SPY", timeout=5)
    assert any("curl_cffi query1.finance.yahoo.com:443" in attempt for attempt in blocked_network_attempts())


def test_tws_port_on_loopback_is_blocked(blocked_network_attempts):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(OSError, match="TWS/IB Gateway"):
            sock.connect(("127.0.0.1", 7497))
    assert len(blocked_network_attempts()) == 1


def test_loopback_connections_are_allowed(blocked_network_attempts):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=5):
            accepted, _ = server.accept()
            accepted.close()
    assert blocked_network_attempts() == []


def test_dotenv_loading_is_disabled(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GAMMA_HERMETIC_PROBE=leaked\n", encoding="utf-8")
    monkeypatch.delenv("GAMMA_HERMETIC_PROBE", raising=False)
    assert load_dotenv(env_file) is False
    assert "GAMMA_HERMETIC_PROBE" not in os.environ


def test_hermetic_baseline_is_pinned():
    assert os.environ["BASE_CURRENCY"] == "USD"
    assert os.environ["MOCK_DATA"] == "true"
    assert os.environ["NEWS_PROVIDER"] == "sample"
    assert os.environ["MARITIME_PROVIDER"] == "sample"
    assert "OPENAI_API_KEY" not in os.environ
    assert "FRED_API_KEY" not in os.environ
