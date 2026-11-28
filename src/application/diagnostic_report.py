"""Informe de diagnóstico para «Report a problem» (beta, 2026-11-28).

El tester lo ve entero antes de copiarlo o guardarlo y lo envía él mismo: Gamma no lo manda a
ningún sitio. Solo contiene datos de estado no sensibles. Nunca incluye claves ni tokens,
identificadores de cuenta, posiciones ni valores de cartera, la identidad SEC, ni contenido de
investigación (ideas, conversaciones del Copilot, notas). Los mensajes de error se sanean y los
de IBKR se omiten, porque pueden nombrar contratos de la cartera.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.utils.atomic_io import atomic_write_text
from src.utils.time import now_utc
from src.version import APP_VERSION

if TYPE_CHECKING:
    from src.application.runtime import ApplicationRuntime

REPORT_SCHEMA = "gamma.diagnostic-report.v1"
MAX_NOTE_CHARS = 2000
MAX_MESSAGE_CHARS = 200
EXCLUDED_FROM_REPORT = [
    "API keys and access tokens",
    "IBKR account identifiers, positions and portfolio values",
    "the SEC identity (name and email)",
    "research content: ideas, saved research, Copilot conversations and notes",
]
# Proveedores cuyos mensajes de error pueden nombrar contratos de la cartera.
_MESSAGE_FREE_PROVIDERS = {"ibkr"}

# Secretos: se quitan también de la nota que escribe el tester, por si pega un log con su clave.
_SECRET_SANITIZERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{8,}\b"), "<secret>"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[=:]\s*[^\s&]+"), r"\1=<redacted>"),
    (re.compile(r"\b[A-Za-z0-9_-]{32,}\b"), "<redacted>"),
]
# Mensajes de error: además, sin URLs, correos, cuentas ni números largos.
_SANITIZERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"https?://\S+", re.I), "<url>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    *_SECRET_SANITIZERS,
    (re.compile(r"\b(?:DU|DF|U|F)\d{5,9}\b"), "<account>"),
    (re.compile(r"\b\d{8,}\b"), "<number>"),
]


def sanitize_message(text: Any) -> str | None:
    """Mensaje apto para el informe: sin URLs, correos, secretos, cuentas ni números largos."""
    if text is None:
        return None
    value = " ".join(str(text).split())
    for pattern, replacement in _SANITIZERS:
        value = pattern.sub(replacement, value)
    if len(value) > MAX_MESSAGE_CHARS:
        value = value[: MAX_MESSAGE_CHARS - 1] + "…"
    return value or None


def redact_secrets(text: Any, *, limit: int = MAX_NOTE_CHARS) -> str | None:
    """Texto libre del tester tal cual, salvo claves y tokens reconocibles."""
    value = str(text or "").strip()
    for pattern, replacement in _SECRET_SANITIZERS:
        value = pattern.sub(replacement, value)
    return value[:limit] or None


def _utc_iso(moment: Any) -> str | None:
    """Instantes del informe en UTC explícito: el informe se lee fuera de Gamma."""
    if moment is None:
        return None
    return moment.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def build_diagnostic_report(
    runtime: "ApplicationRuntime",
    *,
    note: str | None = None,
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from src.application.setup_service import build_setup_report

    setup = build_setup_report(runtime)
    usage = runtime.provider_usage.snapshot(limit=0)
    last_errors = {row.provider_id: row.last_error for row in usage.providers}
    providers = []
    for health in usage.health:
        message = None
        if health.provider_id not in _MESSAGE_FREE_PROVIDERS:
            message = sanitize_message(last_errors.get(health.provider_id))
        providers.append(
            {
                "provider_id": health.provider_id,
                "health_status": health.health_status,
                "calls": health.call_count,
                "errors": health.error_count,
                "unavailable": health.unavailable_count,
                "incomplete": health.incomplete_count,
                "last_called_at": _utc_iso(health.last_called_at),
                "last_error": message,
            }
        )
    client_info = {
        key: sanitize_message(value)
        for key, value in (client or {}).items()
        if key in {"frontend_version", "user_agent", "active_tab", "last_error"} and value
    }
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": _utc_iso(now_utc()),
        "app": {
            "version": APP_VERSION,
            "packaged": bool(getattr(sys, "frozen", False)),
            # platform.release() dice "10" también en Windows 11; la versión trae el número de build.
            "platform": f"{platform.system()} {platform.version()}".strip(),
            "python": platform.python_version(),
        },
        "runtime": {
            "data_mode": setup.data_mode.current,
            "restart_required": setup.data_mode.restart_required,
            "base_currency": runtime.base_currency,
            "market_data_mode": runtime.market_data_mode,
            "ibkr_status": setup.ibkr.status,
            "setup_completed": setup.completed_at is not None,
        },
        "copilot": {"status": setup.copilot.status, "provider": setup.copilot.provider},
        "configured_keys": {row.provider_id: row.configured for row in setup.providers},
        "sec_identity_configured": setup.sec_identity.status == "configured",
        "provider_health": providers,
        "client": client_info,
        "note": redact_secrets(note),
        "excluded": list(EXCLUDED_FROM_REPORT),
    }


def diagnostic_reports_dir(runtime: "ApplicationRuntime") -> Path:
    """Carpeta de informes: los logs de la app de escritorio o, en desarrollo, junto a los datos."""
    log_dir = (os.getenv("GAMMA_LOG_DIR") or "").strip()
    if log_dir:
        return Path(log_dir).expanduser() / "reports"
    store = getattr(runtime, "setup_store", None)
    base = Path(store.base_dir).parent if store is not None else Path("data")
    return base / "diagnostic_reports"


def save_diagnostic_report(runtime: "ApplicationRuntime", report: dict[str, Any]) -> Path:
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    path = diagnostic_reports_dir(runtime) / f"gamma-report-{stamp}.json"
    atomic_write_text(path, json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return path
