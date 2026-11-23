"""Read-only Python client for Gamma's local API (Workstream 12, checkpoint I4b).

The client runs on the user's machine, under their control; Gamma never invokes
it. It reads histories, ideas, observables and tracking with their provenance,
and has exactly one write path: importing a signal into an idea, which the
server validates exactly like a Strategy Lab CSV import. Every request is
checked against :data:`ALLOWED_ROUTES` before it is sent, so no call can place,
stage or route an order, or touch an account.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

import httpx

SESSION_HEADER = "X-Gamma-Session"
TOKEN_ENV = "GAMMA_SESSION_TOKEN"
BASE_URL_ENV = "GAMMA_API_BASE"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# Las únicas rutas que el cliente puede llamar: lecturas y la importación de una señal.
ALLOWED_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", r"/ideas"),
    ("GET", r"/ideas/observables"),
    ("GET", r"/ideas/history"),
    ("GET", r"/ideas/[A-Za-z0-9_-]+"),
    ("GET", r"/ideas/[A-Za-z0-9_-]+/tracking"),
    ("GET", r"/macro/series/[A-Za-z0-9_.:-]+/history"),
    ("POST", r"/ideas/[A-Za-z0-9_-]+/signal"),
)
SIGNAL_KINDS = ("positions", "weights", "returns")


class GammaClientError(RuntimeError):
    """A request Gamma refused or could not serve; ``status`` is the HTTP status."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RouteNotAllowedError(GammaClientError):
    """The client refuses to send a request outside its read-only allowlist."""


def route_allowed(method: str, path: str) -> bool:
    return any(method.upper() == allowed and re.fullmatch(pattern, path) for allowed, pattern in ALLOWED_ROUTES)


def _pandas():
    try:
        import pandas as pd  # noqa: PLC0415 - dependencia opcional
    except ImportError:  # pragma: no cover - sin pandas se devuelven listas de dicts
        return None
    return pd


def _cell(value: Any) -> str:
    """One CSV cell as text, the form a Strategy Lab import reads."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (date, datetime)) or hasattr(value, "to_pydatetime"):
        stamp = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        return stamp.date().isoformat() if isinstance(stamp, datetime) else stamp.isoformat()
    return str(value)


def signal_rows(data: Any, *, date_column: str = "date") -> tuple[list[dict[str, str]], list[str]]:
    """Rows and instrument columns from a DataFrame (dates in the index or a column) or a list of dicts."""
    pd = _pandas()
    if pd is not None and isinstance(data, pd.Series):
        data = data.to_frame(name=str(data.name or "value"))
    if pd is not None and isinstance(data, pd.DataFrame):
        frame = data.copy()
        if date_column not in frame.columns:
            frame = frame.reset_index()
            frame = frame.rename(columns={frame.columns[0]: date_column})
        records = frame.to_dict(orient="records")
    elif isinstance(data, Mapping):
        raise TypeError("Pass a DataFrame or a list of row dicts, not a single mapping.")
    elif isinstance(data, Iterable):
        records = [dict(row) for row in data]
    else:
        raise TypeError("Signal data must be a pandas DataFrame or Series, or a list of row dicts.")
    if not records:
        raise ValueError("The signal has no rows.")
    columns = [str(key) for key in records[0] if str(key) != date_column]
    rows = [{str(key): _cell(value) for key, value in record.items()} for record in records]
    return rows, columns


class IdeasAPI:
    def __init__(self, client: "Gamma") -> None:
        self._client = client

    def list(self, *, status: str | Sequence[str] | None = None, tag: str | Sequence[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status if isinstance(status, str) else ",".join(status)
        if tag:
            params["tag"] = tag if isinstance(tag, str) else ",".join(tag)
        return self._client._request("GET", "/ideas", params=params).get("items", [])

    def get(self, idea_id: str) -> dict[str, Any]:
        return self._client._request("GET", f"/ideas/{idea_id}")

    def tracking(self, idea_id: str) -> dict[str, Any]:
        """The hypothetical forward record ("Hypothetical, not executed"), rebuilt from provider closes."""
        return self._client._request("GET", f"/ideas/{idea_id}/tracking")

    def attach_signal(
        self,
        idea_id: str,
        data: Any,
        *,
        kind: str = "weights",
        date_column: str = "date",
        value_column: str | None = None,
        value_kind: str = "return",
        instruments: Mapping[str, str | Mapping[str, str]] | None = None,
        label: str | None = None,
    ) -> dict[str, Any]:
        """Import a signal into an idea; Gamma validates it exactly like a Strategy Lab CSV import.

        ``kind`` is ``weights`` (one column per instrument, shares of NAV),
        ``positions`` (signed units per instrument) or ``returns`` (one
        ``value_column``; validation only, never tracked). ``instruments`` maps
        a column to a ticker, or to ``{"symbol": "bitcoin", "entity_type":
        "crypto"}``. The latest row on or before today becomes the book; rows
        after today are refused. Returns the idea as Gamma stored it.
        """
        if kind not in SIGNAL_KINDS:
            raise ValueError(f"kind must be one of {SIGNAL_KINDS}.")
        rows, columns = signal_rows(data, date_column=date_column)
        payload: dict[str, Any] = {"source": "import", "output_kind": kind, "rows": rows, "date_column": date_column}
        if label:
            payload["label"] = label
        if kind == "returns":
            payload["value_column"] = value_column or (columns[0] if len(columns) == 1 else None)
            if not payload["value_column"]:
                raise ValueError("Name the returns column with value_column.")
            payload["value_kind"] = value_kind
        else:
            payload["columns"] = columns
            mapped: dict[str, dict[str, str]] = {}
            for column, target in (instruments or {}).items():
                mapped[str(column)] = {"symbol": target, "entity_type": "equity"} if isinstance(target, str) else dict(target)
            if mapped:
                payload["instruments"] = mapped
        return self._client._request("POST", f"/ideas/{idea_id}/signal", json=payload)


class Gamma:
    """``Gamma()`` reads ``GAMMA_API_BASE`` and ``GAMMA_SESSION_TOKEN`` from the environment."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        http: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or os.getenv(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
        self._token = (token if token is not None else os.getenv(TOKEN_ENV) or "").strip()
        if not self._token:
            raise GammaClientError(f"Set {TOKEN_ENV} (the session token Gamma started with) or pass token=.")
        self._http = http or httpx.Client(base_url=self.base_url, timeout=timeout)
        self.ideas = IdeasAPI(self)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Gamma":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # -- reads -----------------------------------------------------------------

    def history(self, symbol: str, *, days: int = 365, kind: str = "equity") -> Any:
        """Daily closes with provenance columns (a DataFrame indexed by session when pandas is installed)."""
        payload = self._request("GET", "/ideas/history", params={"symbol": symbol, "kind": kind, "days": str(days)})
        if not payload.get("available"):
            raise GammaClientError(payload.get("unavailable_reason") or f"No closes for {symbol}.")
        provenance = payload.get("provenance") or {}
        rows = [
            {
                "session": point["session"],
                "close": point["close"],
                "close_at": point["close_at"],
                "source_provider": provenance.get("source_provider"),
                "retrieved_at": provenance.get("retrieved_at"),
                "origin": provenance.get("origin"),
            }
            for point in payload["points"]
        ]
        return self._frame(rows, index="session", attrs={"symbol": payload["symbol"], "warnings": payload.get("warnings", []), "provenance": provenance})

    def macro(self, series_id: str, *, region: str | None = None) -> Any:
        """A macro series (FRED, Treasury) with provenance columns."""
        params = {"region": region} if region else None
        payload = self._request("GET", f"/macro/series/{series_id}/history", params=params)
        rows = [
            {
                "date": point.get("timestamp"),
                "value": point.get("value"),
                "source_provider": point.get("source_provider") or payload.get("source_provider"),
                "retrieved_at": point.get("retrieved_at") or payload.get("retrieved_at"),
                "origin": point.get("origin") or payload.get("origin"),
            }
            for point in payload.get("points", [])
        ]
        return self._frame(rows, index="date", attrs={"series_id": series_id, "title": payload.get("title"), "unit": payload.get("unit")})

    def observables(self) -> list[dict[str, Any]]:
        return self._request("GET", "/ideas/observables").get("items", [])

    # -- transport ----------------------------------------------------------------

    def _request(self, method: str, path: str, *, params: Mapping[str, str] | None = None, json: Any = None) -> Any:
        if not route_allowed(method, path):
            raise RouteNotAllowedError(f"The Gamma client is read-only; {method} {path} is not an allowed route.")
        response = self._http.request(method, path, params=params, json=json, headers={SESSION_HEADER: self._token})
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text
            raise GammaClientError(f"{response.status_code}: {detail}", status=response.status_code)
        return response.json()

    @staticmethod
    def _frame(rows: list[dict[str, Any]], *, index: str, attrs: Mapping[str, Any]) -> Any:
        pd = _pandas()
        if pd is None:
            return rows
        frame = pd.DataFrame(rows)
        if not frame.empty:
            frame[index] = pd.to_datetime(frame[index].astype(str).str[:10])
            frame = frame.set_index(index)
        frame.attrs.update(dict(attrs))
        return frame
