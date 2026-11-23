"""Read-only Python client for Gamma's local research API (Workstream 12, I4b)."""

from gamma_client.client import (
    ALLOWED_ROUTES,
    Gamma,
    GammaClientError,
    IdeasAPI,
    RouteNotAllowedError,
    route_allowed,
    signal_rows,
)

__all__ = [
    "ALLOWED_ROUTES",
    "Gamma",
    "GammaClientError",
    "IdeasAPI",
    "RouteNotAllowedError",
    "route_allowed",
    "signal_rows",
]
__version__ = "0.1.0"
