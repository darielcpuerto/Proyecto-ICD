"""Adaptadores de tienda estática.

Un adaptador decide qué páginas de una fuente conviene recolectar cuando su
catálogo no es navegable desde una única URL. Para las tiendas estáticas se usa
el sitemap declarado en `robots.txt`, filtrando por patrones de ruta.

La configuración vive en `adaptadores.json` y es opcional: si no hay adaptador
para una fuente, se usa su URL declarada en el catálogo.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .config import Fuente
from .fetcher import Fetcher
from .sitemap import sitemaps_de_robots, urls_de_sitemap

RUTA_ADAPTADORES = Path(__file__).resolve().parent / "adaptadores.json"


def _dominio(netloc: str) -> str:
    """Normaliza el dominio ignorando el prefijo `www.`."""
    return netloc.lower().removeprefix("www.")


def cargar(ruta: Path | None = None) -> dict[str, dict]:
    ruta = ruta or RUTA_ADAPTADORES
    if not Path(ruta).is_file():
        return {}
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return {str(a["fuente_id"]): a for a in datos.get("adaptadores", [])}


def obtener(fuente_id: str, adaptadores: dict[str, dict]) -> dict | None:
    return adaptadores.get(fuente_id)


def semillas_para(
    fuente: Fuente,
    fetcher: Fetcher,
    texto_robots: str | None,
    adaptadores: dict[str, dict],
) -> tuple[str, ...]:
    """Devuelve las URLs semilla para una fuente según su adaptador."""
    adaptador = adaptadores.get(fuente.id)
    if not adaptador:
        return ()

    explicitas = adaptador.get("semillas")
    if explicitas:
        return tuple(explicitas)

    if not adaptador.get("usar_sitemap"):
        return ()

    netloc = urlparse(fuente.url).netloc
    patrones = adaptador.get("patrones") or []

    urls: list[str] = []
    for sitemap_url in sitemaps_de_robots(texto_robots, fuente.url):
        for url in urls_de_sitemap(fetcher, sitemap_url):
            if _dominio(urlparse(url).netloc) != _dominio(netloc):
                continue
            if patrones and not any(p in url for p in patrones):
                continue
            if url not in urls:
                urls.append(url)

    return tuple(urls)
