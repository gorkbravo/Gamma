"""Lectura y escritura mínima del .env de Gamma para guardar claves de API desde la app (beta).

Solo maneja líneas ``NOMBRE=valor``: conserva comentarios, orden y el resto de variables, cambia
la primera asignación activa de cada nombre (o la añade al final) y escribe de forma atómica.
Los valores nunca se registran en logs ni se devuelven a la interfaz.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.utils.atomic_io import atomic_write_text

ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
# Claves de API habituales: ASCII visible sin espacios. Se excluyen comillas, «#», «$» (python-dotenv
# interpola ${VAR}), «\» y la comilla invertida para que el valor se lea tal cual sin entrecomillar.
_VALUE_RE = re.compile(r"^[!%&()*+,\-./0-9:;<=>?@A-Z\[\]^_a-z{|}~]{1,512}$")
_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


class EnvValueError(ValueError):
    """Nombre o valor que no puede guardarse en el .env."""


def validate_env_value(name: str, value: str) -> str:
    candidate = str(value or "").strip()
    if not _VALUE_RE.fullmatch(candidate):
        raise EnvValueError(
            f"{name} must be 1-512 visible characters without spaces, quotes, '#', '$' or backslashes."
        )
    return candidate


def read_env_assignments(path: Path) -> dict[str, str]:
    """Valores activos del fichero (la primera asignación de cada nombre), sin interpolar."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _ASSIGNMENT_RE.match(line)
        if not match or line.lstrip().startswith("#"):
            continue
        name, raw = match.group(1), match.group(2).strip()
        if raw[:1] in {'"', "'"} and raw[-1:] == raw[:1] and len(raw) >= 2:
            raw = raw[1:-1]
        else:
            raw = raw.split(" #", 1)[0].strip()
        values.setdefault(name, raw)
    return values


def update_env_file(path: Path, updates: dict[str, str | None]) -> None:
    """Fija (valor) o elimina (None) cada variable de ``updates`` y conserva todo lo demás."""
    for name in updates:
        if not ENV_NAME_RE.fullmatch(name):
            raise EnvValueError(f"Unsupported variable name: {name!r}.")
    # read_bytes: read_text traduciría los saltos CRLF y se perdería el final de línea del fichero.
    original = path.read_bytes().decode("utf-8") if path.exists() else ""
    eol = "\r\n" if "\r\n" in original else "\n"
    handled: set[str] = set()
    result: list[str] = []
    for line in original.splitlines():
        match = _ASSIGNMENT_RE.match(line)
        name = match.group(1) if match and not line.lstrip().startswith("#") else None
        if name is None or name not in updates:
            result.append(line)
            continue
        if name in handled:
            continue  # asignación repetida del mismo nombre: la primera manda y el resto se quita
        handled.add(name)
        value = updates[name]
        if value is not None:
            result.append(f"{name}={value}")
    appended = [f"{name}={value}" for name, value in updates.items() if name not in handled and value is not None]
    if appended:
        if result and result[-1].strip():
            result.append("")
        result.append("# Saved from Gamma Setup")
        result.extend(appended)
    text = eol.join(result)
    if text and not text.endswith(eol):
        text += eol
    atomic_write_text(path, text)
