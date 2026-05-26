from __future__ import annotations

import os
import secrets
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

GAMMA_SESSION_HEADER = "X-Gamma-Session"
GAMMA_SESSION_ENV = "GAMMA_SESSION_TOKEN"
PUBLIC_PATHS = frozenset({"/health"})


def resolve_session_token(explicit_token: str | None = None) -> str:
    token = explicit_token if explicit_token is not None else os.getenv(GAMMA_SESSION_ENV)
    token = (token or "").strip()
    if token:
        return token
    return secrets.token_urlsafe(32)


class GammaSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, session_token: str) -> None:
        super().__init__(app)
        self.session_token = session_token

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._is_public_request(request):
            return await call_next(request)

        header_token = (request.headers.get(GAMMA_SESSION_HEADER) or "").strip()
        if header_token and secrets.compare_digest(header_token, self.session_token):
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid Gamma session token."},
        )

    @staticmethod
    def _is_public_request(request: Request) -> bool:
        if request.method == "OPTIONS":
            return True
        return request.method == "GET" and request.url.path in PUBLIC_PATHS
