from __future__ import annotations

"""Modelos del informe de preparación del primer arranque (``GET /system/setup``).

El informe describe qué está configurado y qué falta, nunca valores secretos: para las
claves de API solo se informa de si existen y del nombre de la variable de entorno.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SetupDataModeState:
    # Modo con el que arrancó este backend: "demo" (MOCK_DATA) o "live".
    current: str
    # Preferencia guardada por el asistente; puede diferir de ``current`` hasta reiniciar.
    preference: str | None
    # Origen del valor efectivo: "argument" | "environment" | "setup" | "default".
    source: str
    restart_required: bool
    # Variable de entorno que fija el valor y prevalece sobre la preferencia guardada.
    locked_by: str | None
    detail: str


@dataclass(frozen=True)
class SetupValueState:
    current: str
    source: str
    locked_by: str | None
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SetupIbkrState:
    # "demo" | "connected" | "disconnected"
    status: str
    host: str
    port: int
    client_id: int
    account_configured: bool
    detail: str
    steps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SetupSecIdentityState:
    # "configured" | "missing"
    status: str
    # "environment" | "setup" | "missing"
    source: str
    locked_by: str | None
    # Solo se devuelven los valores guardados por el propio usuario en el asistente.
    name: str | None
    email: str | None
    detail: str


@dataclass(frozen=True)
class SetupCopilotState:
    # "configured" | "demo" | "missing_key" | "disabled" | "unavailable"
    status: str
    provider: str
    detail: str
    env_vars: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SetupProviderRow:
    provider_id: str
    display_name: str
    configured: bool
    env_vars: list[str]
    unlocks: str


@dataclass(frozen=True)
class SetupCoverageRow:
    tab_id: str
    label: str
    # "sample" | "public" | "broker" | "mixed" | "model" | "unavailable"
    source: str
    detail: str


@dataclass(frozen=True)
class SetupConfigLocation:
    env_file_path: str | None
    env_file_present: bool
    setup_file_path: str


@dataclass(frozen=True)
class SetupReport:
    generated_at: datetime
    schema_version: int
    first_run: bool
    completed_at: datetime | None
    data_mode: SetupDataModeState
    base_currency: SetupValueState
    market_data_mode: SetupValueState
    ibkr: SetupIbkrState
    sec_identity: SetupSecIdentityState
    copilot: SetupCopilotState
    providers: list[SetupProviderRow]
    # Cobertura por pestaña para cada modo ("demo" y "live"), para poder elegir antes de reiniciar.
    coverage_by_mode: dict[str, list[SetupCoverageRow]]
    config: SetupConfigLocation
    warnings: list[str] = field(default_factory=list)
