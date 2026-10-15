"""Base común de los sitios especializados.

Cada sitio declara:

- ``id`` y ``nombre``: deben coincidir con el catálogo;
- ``dominio``: netloc normalizado (sin ``www.``), usado para no salir del sitio;
- ``patrones_relevancia``: fragmentos de URL que se consideran relevantes;
- ``semillas()``: URLs de entrada (explícitas o descubiertas por sitemap);
- ``activos()``: recursos adicionales que el núcleo debe obtener y conservar
  (por ejemplo, el bundle JavaScript que contiene el catálogo);
- ``extraer()``: extracción estructurada propia (por defecto, la genérica).

Los sitios no descargan nada por sí mismos: solo declaran *dónde* y *cómo*
extraer. El núcleo se encarga de la red, la política, la deduplicación y el
almacenamiento. No se usa navegador: el contenido se obtiene con HTTP.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from ..nucleo import extraccion
from ..nucleo.config import Fuente


def dominio_normalizado(netloc: str) -> str:
    """Normaliza el dominio ignorando el prefijo ``www.``."""
    return netloc.lower().removeprefix("www.")


class Sitio:
    """Sitio genérico: usa la URL declarada y la extracción genérica."""

    id: str = ""
    nombre: str = ""
    dominio: str = ""
    patrones_relevancia: tuple[str, ...] = ()
    #: Si es True, las semillas provienen del sitemap del sitio.
    usar_sitemap: bool = False
    patrones_sitemap: tuple[str, ...] = ()
    #: Semillas explícitas (tienen prioridad sobre el sitemap).
    semillas_explicitas: tuple[str, ...] = ()

    # -- semillas -------------------------------------------------------
    def semillas(self, fetcher, texto_robots: str | None) -> list[str]:
        if self.semillas_explicitas:
            return list(self.semillas_explicitas)
        return []

    # -- activos --------------------------------------------------------
    def activos(self, html: str, url: str) -> list[str]:
        """Recursos que el núcleo debe obtener y pasar a ``extraer``.

        Devuelve URLs (absolutas o relativas a ``url``). Por defecto, ninguno.
        """
        return []

    # -- extracción -----------------------------------------------------
    def extraer(
        self,
        html: str,
        texto: str,
        url: str,
        fecha: str,
        fuente: Fuente,
        activos: dict[str, str] | None = None,
    ) -> list[dict]:
        return extraccion.extraer(html, texto, url, fecha, fuente)

    # -- relevancia -----------------------------------------------------
    def relevante_por_patron(self, url: str) -> bool:
        return any(p in url for p in self.patrones_relevancia)


class SitioGenerico(Sitio):
    """Sitio sin módulo propio: una sola semilla (la URL del catálogo)."""

    def __init__(self, fuente: Fuente) -> None:
        self.id = fuente.id
        self.nombre = fuente.nombre
        self.dominio = dominio_normalizado(urlparse(fuente.url).netloc)
        self.semillas_explicitas = (fuente.url,)


# -- utilidades compartidas por los extractores de sitio -----------------
def next_data(html: str) -> dict | None:
    """Devuelve el objeto JSON de ``__NEXT_DATA__`` (Pages Router) o None."""
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def registro_desde_entidad(
    fuente: Fuente,
    url: str,
    fecha: str,
    ubicacion: str,
    entidad: dict,
    metodo: str,
) -> dict:
    """Crea un registro trazable a partir de un objeto estructurado del sitio."""
    campos, claves = extraccion.campos_desde_dict(entidad)
    return extraccion.crear_registro(
        fuente, url, fecha, metodo, ubicacion, campos, claves,
        json.dumps(entidad, ensure_ascii=False),
        advertencias=["valor tomado de datos estructurados del sitio"],
    )


def deduplicar_registros(registros: list[dict]) -> list[dict]:
    """Elimina registros repetidos por (producto, precio, moneda)."""
    vistos: set = set()
    salida: list[dict] = []
    for r in registros:
        c = r["campos"]
        k = (c.get("product_name"), c.get("price"), c.get("currency"))
        if k == (None, None, None) or k in vistos:
            continue
        vistos.add(k)
        salida.append(r)
    return salida
