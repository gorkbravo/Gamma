"""Parámetros de Script separados del código fuente (E5).

Un conjunto de parámetros es un objeto JSON plano (nombre -> número, texto, booleano o null). Gamma lo
canoniza, lo identifica por el SHA-256 de los bytes exactos que entrega al runtime y lo copia al directorio
de trabajo de la ejecución como ``gamma_parameters.json``. El código no cambia entre conjuntos: la
ejecución queda ligada a fuente, entradas y parámetros por separado.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

PARAMETERS_FILENAME = "gamma_parameters.json"
PARAMETERS_CONTRACT_VERSION = "gamma-script-parameters.v1"
MAX_PARAMETER_COUNT = 32
MAX_PARAMETER_TEXT_CHARS = 256
MAX_PARAMETER_BYTES = 8 * 1024

_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# Mismos fragmentos que el resto de contratos de Script: un parámetro nunca transporta credenciales
# ni autoridad de cuenta, cartera u órdenes.
_SENSITIVE_FRAGMENTS = (
    "account", "api_key", "authorization", "broker", "cookie", "credential",
    "order", "password", "secret", "token", "wallet",
)


def validate_parameter_value(name: str, value: Any) -> list[str]:
    """Errores de un valor escalar permitido (bool, entero, real finito, texto acotado o null)."""
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, int):
        # Enteros enormes no son reales finitos de doble precisión al serializarse para Python.
        return [] if abs(value) <= 2 ** 53 else [f"Parameter {name!r} integer exceeds 2**53."]
    if isinstance(value, float):
        return [] if math.isfinite(value) else [f"Parameter {name!r} must be a finite number."]
    if isinstance(value, str):
        errors = []
        if len(value) > MAX_PARAMETER_TEXT_CHARS:
            errors.append(f"Parameter {name!r} text exceeds {MAX_PARAMETER_TEXT_CHARS} characters.")
        lowered = value.lower()
        if re.search(r"(?:https?://|localhost|127\.0\.0\.1|file:)", lowered) or lowered.startswith(("/", "\\")) \
                or re.match(r"^[a-z]:[\\/]", lowered) or "../" in lowered or "..\\" in lowered:
            errors.append(f"Parameter {name!r} cannot contain network destinations or host paths.")
        return errors
    return [f"Parameter {name!r} must be a number, text, boolean or null; nested objects and lists are not supported."]


def canonical_parameters(values: Any) -> tuple[dict[str, Any], bytes, str]:
    """Devuelve (valores, bytes canónicos, sha256) o lanza ValueError con todos los errores."""
    if not isinstance(values, dict):
        raise ValueError("Parameters must be a flat JSON object.")
    errors: list[str] = []
    if len(values) > MAX_PARAMETER_COUNT:
        errors.append(f"Parameter count exceeds {MAX_PARAMETER_COUNT}.")
    for name, value in values.items():
        if not isinstance(name, str) or not _KEY_PATTERN.match(name):
            errors.append(f"Parameter name {name!r} must match {_KEY_PATTERN.pattern}.")
            continue
        if any(fragment in name.lower() for fragment in _SENSITIVE_FRAGMENTS):
            errors.append(f"Parameter name {name!r} looks like credential or account authority and is not accepted.")
        errors.extend(validate_parameter_value(name, value))
    if errors:
        raise ValueError("; ".join(dict.fromkeys(errors)))
    canonical = {name: values[name] for name in sorted(values)}
    content = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(content) > MAX_PARAMETER_BYTES:
        raise ValueError(f"Parameters exceed {MAX_PARAMETER_BYTES} bytes.")
    return canonical, content, hashlib.sha256(content).hexdigest()


def parameter_changes(base: dict[str, Any] | None, comparison: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Diferencias nombre a nombre entre dos conjuntos (ausente se informa como missing)."""
    left, right = dict(base or {}), dict(comparison or {})
    changes = []
    for name in sorted(set(left) | set(right)):
        if name not in left or name not in right or left[name] != right[name] or type(left[name]) is not type(right[name]):
            changes.append({"name": name, "base": left.get(name), "comparison": right.get(name),
                            "base_present": name in left, "comparison_present": name in right})
    return changes
