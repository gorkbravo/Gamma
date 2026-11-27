"""Escritura atómica de ficheros locales (stores y caché).

Escribe en un temporal de la misma carpeta, hace fsync y lo sustituye con ``os.replace``, de modo
que un corte a mitad de escritura deja el fichero anterior intacto en lugar de un JSON o CSV
truncado. Es el mismo patrón que ya usaban los stores de Ideas, Script e historial de cartera.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Nombre corto: los ficheros de caché ya rozan el límite de ruta de Windows (260 caracteres).
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".gamma-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    """Escribe ``text`` tal cual (sin traducir saltos de línea) de forma atómica."""
    atomic_write_bytes(path, text.encode(encoding))
