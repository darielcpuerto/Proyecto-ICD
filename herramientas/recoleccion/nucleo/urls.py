"""Canonicalización de URLs para deduplicación.

La URL canónica se usa **solo como identidad** para no repetir una misma página
o una misma oferta. La petición HTTP conserva la URL original descubierta.

Reglas (no alteran el significado de la ruta):

- esquema y host en minúsculas; se retira el prefijo ``www.``;
- se retiran el fragmento y los puertos por defecto;
- se decodifican los porcentajes (``%C3%A9`` → ``é``) y se normaliza a NFC;
- se colapsan barras repetidas y se retira la barra final (salvo en ``/``);
- los parámetros de consulta se ordenan.

No se cambia la capitalización de la ruta ni se convierten ``_`` en ``-``:
podrían distinguir recursos reales.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlparse, urlunparse

PUERTOS_POR_DEFECTO = {"http": "80", "https": "443"}


def canonicalizar(url: str) -> str:
    """Devuelve la forma canónica de ``url`` (cadena vacía si no es absoluta)."""
    if not url:
        return ""
    partes = urlparse(url.strip())
    if not partes.scheme or not partes.netloc:
        return url.strip()

    esquema = partes.scheme.lower()
    host = partes.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        nombre, _, puerto = host.rpartition(":")
        if puerto == PUERTOS_POR_DEFECTO.get(esquema):
            host = nombre

    ruta = unquote(partes.path or "/")
    ruta = unicodedata.normalize("NFC", ruta)
    ruta = re.sub(r"/{2,}", "/", ruta)
    if ruta != "/":
        ruta = ruta.rstrip("/")
    if not ruta:
        ruta = "/"

    consulta = "&".join(sorted(p for p in partes.query.split("&") if p))
    return urlunparse((esquema, host, ruta, "", consulta, ""))


def mismo_recurso(a: str, b: str) -> bool:
    """True si dos URLs son la misma identidad canónica."""
    return canonicalizar(a) == canonicalizar(b)


def ruta_normalizada(url: str) -> str:
    """Ruta + consulta normalizadas, útiles para prefiltros por texto."""
    partes = urlparse(url)
    ruta = unquote(partes.path or "").lower()
    return f"{ruta}?{partes.query.lower()}" if partes.query else ruta
