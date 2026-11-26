from __future__ import annotations

import base64
import binascii
import os
import secrets
from collections.abc import Callable, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

GAMMA_SESSION_HEADER = "X-Gamma-Session"
GAMMA_SESSION_ENV = "GAMMA_SESSION_TOKEN"
PUBLIC_PATHS = frozenset({"/health"})

# Orígenes de navegador de la app: Vite (dev/preview) y la WebView de Tauri. Los usan CORS y
# la guardia de WebSocket, que no pasa por CORS.
LOCAL_BROWSER_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
)

# Un navegador no puede poner cabeceras propias en un WebSocket, así que el token viaja como
# subprotocolo: el cliente ofrece GAMMA_WS_SUBPROTOCOL y GAMMA_WS_TOKEN_PREFIX + base64url(token),
# y el servidor responde solo con GAMMA_WS_SUBPROTOCOL (nunca devuelve el token).
GAMMA_WS_SUBPROTOCOL = "gamma.session"
GAMMA_WS_TOKEN_PREFIX = "gamma.session.token."
# Cierre de política (RFC 6455 §7.4.1); antes del accept, el servidor ASGI responde HTTP 403.
WS_POLICY_VIOLATION = 1008


def resolve_session_token(explicit_token: str | None = None) -> str:
    token = explicit_token if explicit_token is not None else os.getenv(GAMMA_SESSION_ENV)
    token = (token or "").strip()
    if token:
        return token
    return secrets.token_urlsafe(32)


class GammaSessionMiddleware(BaseHTTPMiddleware):
    """Exige el token de sesión en cada petición HTTP.

    BaseHTTPMiddleware solo ve el scope ``http``: los WebSocket los protege
    ``GammaWebSocketSessionMiddleware``.
    """

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


class GammaWebSocketSessionMiddleware:
    """Guardia ASGI para los WebSocket: token de sesión y origen local obligatorios.

    Acepta el token por la cabecera ``X-Gamma-Session`` (clientes que no son navegador) o por
    el subprotocolo ``gamma.session.token.<base64url>`` (navegador). Si llega una cabecera
    ``Origin``, debe ser uno de los orígenes de la app: CORS no se aplica a los WebSocket, así
    que sin esta comprobación cualquier página abierta en el navegador podría conectarse.
    Una conexión rechazada se cierra antes del handshake (HTTP 403).
    """

    def __init__(self, app: ASGIApp, *, session_token: str, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.session_token = session_token
        self.allowed_origins = frozenset(origin.lower() for origin in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "websocket" or self._authorized(scope):
            await self.app(scope, receive, send)
            return
        # Se consume el websocket.connect y se rechaza sin aceptar la conexión.
        await receive()
        await send({"type": "websocket.close", "code": WS_POLICY_VIOLATION})

    def _authorized(self, scope: Scope) -> bool:
        headers = _scope_headers(scope)
        origin = headers.get("origin")
        if origin is not None and origin.strip().lower() not in self.allowed_origins:
            return False
        candidates = [headers.get(GAMMA_SESSION_HEADER.lower())]
        candidates.extend(_subprotocol_tokens(scope))
        # compare_digest solo admite str ASCII: se comparan bytes UTF-8.
        expected = self.session_token.encode("utf-8")
        return any(
            candidate and secrets.compare_digest(candidate.strip().encode("utf-8"), expected)
            for candidate in candidates
        )


def websocket_subprotocol(scope: Scope) -> str | None:
    """Subprotocolo que el servidor debe devolver al aceptar, si el cliente lo ofreció.

    Un navegador que ofrece subprotocolos cierra la conexión si la respuesta no elige uno.
    """
    offered = scope.get("subprotocols") or []
    return GAMMA_WS_SUBPROTOCOL if GAMMA_WS_SUBPROTOCOL in offered else None


def _scope_headers(scope: Scope) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers") or []:
        headers[raw_name.decode("latin-1").lower()] = raw_value.decode("latin-1")
    return headers


def _subprotocol_tokens(scope: Scope) -> list[str]:
    tokens: list[str] = []
    for offered in scope.get("subprotocols") or []:
        if not isinstance(offered, str) or not offered.startswith(GAMMA_WS_TOKEN_PREFIX):
            continue
        encoded = offered[len(GAMMA_WS_TOKEN_PREFIX):]
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            tokens.append(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        except (binascii.Error, UnicodeError, ValueError):
            continue
    return tokens
