from __future__ import annotations

"""Persistencia local de las preferencias del asistente de primer arranque.

Un único fichero JSON versionado bajo el directorio de datos (``<data>/setup/setup.json``).
Guarda solo preferencias no secretas: modo de datos (demo/live), divisa base, modo de
datos de mercado, identidad SEC y la marca de setup completado. Las claves de API no se
guardan aquí nunca; siguen llegando por variables de entorno.

Reglas de recuperación, alineadas con los demás stores locales:

- Fichero ausente: preferencias vacías (primer arranque).
- JSON corrupto o con forma inválida: se aparta a ``setup.corrupt-<ts>.json`` y se
  devuelven preferencias vacías con un aviso, en lugar de impedir el arranque.
- Esquema más nuevo que el soportado: se ignora para leer y se rechaza al escribir, para
  no sobrescribir datos de una versión posterior de Gamma.
"""

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.time import now_utc

SETUP_SCHEMA_VERSION = 1
SETUP_DATA_MODES = ("demo", "live")
SETUP_MARKET_DATA_MODES = ("delayed", "live", "auto")
SEC_IDENTITY_NAME_MAX = 80
SEC_IDENTITY_EMAIL_MAX = 120
# Validación deliberadamente básica: la SEC solo exige un contacto con forma de email.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SetupStoreError(RuntimeError):
    """Error al escribir preferencias que el store no puede guardar con seguridad."""


@dataclass(frozen=True)
class SecIdentity:
    name: str
    email: str


@dataclass(frozen=True)
class SetupPreferences:
    completed_at: datetime | None = None
    data_mode: str | None = None
    base_currency: str | None = None
    market_data_mode: str | None = None
    sec_identity: SecIdentity | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class SetupLoadResult:
    preferences: SetupPreferences
    warnings: list[str] = field(default_factory=list)
    # True cuando el fichero en disco pertenece a un esquema más nuevo y no debe sobrescribirse.
    read_only: bool = False


def normalize_sec_identity(name: str | None, email: str | None) -> SecIdentity:
    """Valida y normaliza una identidad SEC; lanza ValueError con un mensaje legible."""
    clean_name = " ".join(str(name or "").split())
    clean_email = str(email or "").strip()
    if len(clean_name) < 2:
        raise ValueError("SEC identity name must have at least 2 characters.")
    if len(clean_name) > SEC_IDENTITY_NAME_MAX:
        raise ValueError(f"SEC identity name must have at most {SEC_IDENTITY_NAME_MAX} characters.")
    if len(clean_email) > SEC_IDENTITY_EMAIL_MAX or not _EMAIL_PATTERN.match(clean_email):
        raise ValueError("SEC identity email must be a valid email address.")
    return SecIdentity(name=clean_name, email=clean_email)


class SetupStore:
    def __init__(self, base_dir: str | Path = "data/setup") -> None:
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / "setup.json"
        self._lock = threading.Lock()

    def load(self) -> SetupLoadResult:
        with self._lock:
            return self._load_unlocked()

    def update(self, **changes: Any) -> SetupPreferences:
        """Aplica cambios parciales y persiste de forma atómica.

        Las claves aceptadas son los campos de ``SetupPreferences``; ``updated_at`` se fija aquí.
        """
        allowed = {"completed_at", "data_mode", "base_currency", "market_data_mode", "sec_identity"}
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise ValueError(f"Unknown setup fields: {', '.join(unknown)}")
        with self._lock:
            current = self._load_unlocked()
            if current.read_only:
                raise SetupStoreError(
                    "Setup preferences were written by a newer Gamma version and were not overwritten."
                )
            updated = replace(current.preferences, **changes, updated_at=now_utc())
            self._write_unlocked(updated)
            return updated

    # ── Internos ─────────────────────────────────────────────────────────

    def _load_unlocked(self) -> SetupLoadResult:
        if not self.path.exists():
            return SetupLoadResult(preferences=SetupPreferences())
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("setup payload is not an object")
            version = int(payload.get("schema_version") or 0)
        except (OSError, ValueError, TypeError) as exc:
            return self._quarantine_unlocked(f"Setup preferences could not be read ({exc}); defaults were used.")
        if version > SETUP_SCHEMA_VERSION:
            return SetupLoadResult(
                preferences=SetupPreferences(),
                warnings=[
                    f"Setup preferences use schema version {version}, newer than {SETUP_SCHEMA_VERSION}; "
                    "they were ignored and will not be overwritten."
                ],
                read_only=True,
            )
        try:
            preferences = _preferences_from_payload(payload)
        except (ValueError, TypeError) as exc:
            return self._quarantine_unlocked(f"Setup preferences were invalid ({exc}); defaults were used.")
        return SetupLoadResult(preferences=preferences)

    def _quarantine_unlocked(self, warning: str) -> SetupLoadResult:
        stamp = now_utc().strftime("%Y%m%dT%H%M%S")
        target = self.path.with_name(f"setup.corrupt-{stamp}-{uuid.uuid4().hex[:6]}.json")
        try:
            os.replace(self.path, target)
            warning = f"{warning} The unreadable file was kept as {target.name}."
        except OSError:
            pass
        return SetupLoadResult(preferences=SetupPreferences(), warnings=[warning])

    def _write_unlocked(self, preferences: SetupPreferences) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SETUP_SCHEMA_VERSION,
            "completed_at": _iso(preferences.completed_at),
            "data_mode": preferences.data_mode,
            "base_currency": preferences.base_currency,
            "market_data_mode": preferences.market_data_mode,
            "sec_identity": (
                {"name": preferences.sec_identity.name, "email": preferences.sec_identity.email}
                if preferences.sec_identity is not None
                else None
            ),
            "updated_at": _iso(preferences.updated_at),
        }
        temp_path = self.base_dir / f".{self.path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, indent=2, sort_keys=True))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)


def _preferences_from_payload(payload: dict[str, Any]) -> SetupPreferences:
    data_mode = _optional_choice(payload.get("data_mode"), SETUP_DATA_MODES, "data_mode")
    market_data_mode = _optional_choice(payload.get("market_data_mode"), SETUP_MARKET_DATA_MODES, "market_data_mode")
    base_currency = payload.get("base_currency")
    if base_currency is not None:
        base_currency = str(base_currency).strip().upper()
        if len(base_currency) != 3 or not base_currency.isalpha():
            raise ValueError("base_currency must be a 3-letter ISO code")
    identity_payload = payload.get("sec_identity")
    sec_identity = None
    if identity_payload is not None:
        if not isinstance(identity_payload, dict):
            raise ValueError("sec_identity must be an object")
        sec_identity = normalize_sec_identity(identity_payload.get("name"), identity_payload.get("email"))
    return SetupPreferences(
        completed_at=_parse_datetime(payload.get("completed_at")),
        data_mode=data_mode,
        base_currency=base_currency,
        market_data_mode=market_data_mode,
        sec_identity=sec_identity,
        updated_at=_parse_datetime(payload.get("updated_at")),
    )


def _optional_choice(value: Any, choices: tuple[str, ...], name: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized not in choices:
        raise ValueError(f"{name} must be one of {', '.join(choices)}")
    return normalized


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
