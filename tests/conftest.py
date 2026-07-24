from __future__ import annotations

"""Shared test safety and authenticated TestClient defaults.

Provider values are fixed before application modules import runtime configuration,
so a developer's .env cannot make tests contact Yahoo Finance or TWS.
"""

import os
from typing import Any

os.environ["MOCK_DATA"] = "true"
os.environ["RESEARCH_MARKET_DATA_PROVIDERS"] = "mock"
os.environ["SITREP_MARKET_DATA_PROVIDERS"] = "mock"
os.environ["PORTFOLIO_RISK_HISTORY_PROVIDERS"] = "mock"
os.environ["COMMODITIES_PROVIDER"] = "sample"
os.environ["IBKR_COMMODITIES_ENABLED"] = ""
os.environ["IBKR_COMMODITIES_STARTUP_ENABLED"] = ""
os.environ["GAMMA_COPILOT_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from src.api.session_auth import GAMMA_SESSION_ENV, GAMMA_SESSION_HEADER

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
