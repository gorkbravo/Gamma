from __future__ import annotations

import os
from typing import Any

from fastapi.testclient import TestClient

from src.api.session_auth import GAMMA_SESSION_ENV, GAMMA_SESSION_HEADER

TEST_GAMMA_SESSION_TOKEN = "test-gamma-session"
NO_TEST_SESSION_HEADER = "X-Test-No-Gamma-Session"

os.environ.setdefault(GAMMA_SESSION_ENV, TEST_GAMMA_SESSION_TOKEN)

_original_test_client_init = TestClient.__init__


def _test_client_init_with_gamma_session(self: TestClient, *args: Any, **kwargs: Any) -> None:
    headers = dict(kwargs.pop("headers", None) or {})
    skip_session = headers.pop(NO_TEST_SESSION_HEADER, None) == "1"
    if not skip_session:
        headers.setdefault(GAMMA_SESSION_HEADER, TEST_GAMMA_SESSION_TOKEN)
    _original_test_client_init(self, *args, headers=headers, **kwargs)


TestClient.__init__ = _test_client_init_with_gamma_session
