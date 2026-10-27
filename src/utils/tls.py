from __future__ import annotations

import ssl
from functools import lru_cache
from urllib.error import URLError


@lru_cache(maxsize=1)
def extended_trust_ssl_context() -> ssl.SSLContext:
    """Raíces del sistema más las de certifi.

    En Windows el almacén local solo contiene las raíces que CryptoAPI ya descargó, y Python
    no dispara esa descarga: www.ecb.europa.eu encadena a "Sectigo Public Server
    Authentication Root E46" y falla con CERTIFICATE_VERIFY_FAILED aunque el navegador la
    acepte. Añadir el paquete de certifi amplía las raíces de confianza sin desactivar nada.
    """

    context = ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        return context
    context.load_verify_locations(cafile=certifi.where())
    return context


def is_certificate_verification_error(exc: BaseException) -> bool:
    """True si el fallo es la verificación del certificado (directo o envuelto en URLError)."""

    reason = getattr(exc, "reason", None) if isinstance(exc, URLError) else None
    return isinstance(exc, ssl.SSLCertVerificationError) or isinstance(reason, ssl.SSLCertVerificationError)
