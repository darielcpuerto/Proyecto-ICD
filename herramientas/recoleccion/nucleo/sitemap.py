"""Lectura de sitemaps XML.

Permite descubrir las páginas de una tienda a partir de su sitemap (o del
sitemap declarado en `robots.txt`), sin depender de seguir enlaces del menú.

Además de recorrer índices, ofrece:

- ``sitemaps_por_fecha``: selecciona los sitemaps diarios más recientes
  (``/sitemap-posts/YYYY-MM-DD.xml``) dentro de una ventana configurable. La
  ventana es adaptativa: el recolector pide lotes de uno en uno y solo lee el
  siguiente día si no ha alcanzado el objetivo.
- ``urls_de_sitemap(..., patrones=...)``: filtra las URLs antes de devolverlas.
"""

from __future__ import annotations

import gzip
import re
from datetime import date
from html import unescape
from urllib.parse import urljoin, urlparse

from .fetcher import Fetcher

PATRON_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.I)
PATRON_DIARIO = re.compile(r"/sitemap-posts/(\d{4}-\d{2}-\d{2})\.xml$", re.I)


def sitemaps_de_robots(texto_robots: str | None, base_url: str) -> list[str]:
    """Devuelve las URLs de sitemap declaradas en robots.txt (o el por defecto)."""
    if texto_robots:
        declarados = re.findall(r"^\s*Sitemap:\s*(\S+)\s*$", texto_robots, re.I | re.M)
        if declarados:
            return [unescape(u) for u in declarados]
    return [urljoin(base_url, "/sitemap.xml")]


def _locs(fetcher: Fetcher, url: str) -> tuple[list[str], bool]:
    respuesta = fetcher.obtener(url)
    if not respuesta.ok:
        return [], False
    if url.endswith(".gz"):
        try:
            texto = gzip.decompress(respuesta.contenido).decode("utf-8", "replace")
        except OSError:
            return [], False
    else:
        texto = respuesta.texto()
    return [unescape(u) for u in PATRON_LOC.findall(texto)], "<sitemapindex" in texto.lower()


def locs_de_sitemap(fetcher: Fetcher, url: str) -> tuple[list[str], bool]:
    """Expone la lectura cruda de un sitemap: ``(locs, es_indice)``."""
    return _locs(fetcher, url)


def urls_de_sitemap(
    fetcher: Fetcher,
    url: str,
    max_sitemaps: int = 10,
    patrones: tuple[str, ...] | list[str] = (),
) -> list[str]:
    """Devuelve las URLs de páginas de un sitemap (recorre índices de sitemap)."""
    locs, es_indice = _locs(fetcher, url)
    if not es_indice:
        return _filtrar(locs, patrones)
    urls: list[str] = []
    for sub in locs[:max_sitemaps]:
        urls.extend(urls_de_sitemap(fetcher, sub, max_sitemaps, patrones))
    return _filtrar(urls, patrones)


def _filtrar(urls: list[str], patrones: tuple[str, ...] | list[str]) -> list[str]:
    if not patrones:
        return list(urls)
    return [u for u in urls if any(p in u for p in patrones)]


def sitemaps_diarios(
    fetcher: Fetcher,
    texto_robots: str | None,
    base_url: str,
    ventana_dias: int = 30,
) -> list[tuple[str, date]]:
    """Devuelve ``[(url_sitemap, fecha)]`` de los días más recientes.

    Se leen los índices declarados en ``robots.txt`` y se conservan las entradas
    ``/sitemap-posts/YYYY-MM-DD.xml``. Se ordenan de más reciente a más antigua
    y se toman como máximo ``ventana_dias`` fechas disponibles (no días de
    calendario): si el sitio publicó poco, se usan las últimas que existan.
    """
    candidatos: dict[date, str] = {}
    vistos: set[str] = set()
    for indice in sitemaps_de_robots(texto_robots, base_url):
        locs, es_indice = _locs(fetcher, indice)
        if not es_indice:
            continue
        for loc in locs:
            canonica = urlparse(loc)
            if canonica.netloc and urlparse(base_url).netloc and (
                canonica.netloc.lower().removeprefix("www.")
                != urlparse(base_url).netloc.lower().removeprefix("www.")
            ):
                continue
            coincidencia = PATRON_DIARIO.search(loc)
            if not coincidencia or loc in vistos:
                continue
            try:
                fecha = date.fromisoformat(coincidencia.group(1))
            except ValueError:
                continue
            vistos.add(loc)
            candidatos[fecha] = loc
    ordenados = sorted(candidatos.items(), reverse=True)
    return [(url, fecha) for fecha, url in ordenados[:max(1, ventana_dias)]]


def urls_de_sitemap_diario(
    fetcher: Fetcher,
    url: str,
    patrones: tuple[str, ...] | list[str] = (),
) -> list[str]:
    """URLs de un sitemap diario concreto, filtradas por patrón."""
    locs, es_indice = _locs(fetcher, url)
    if es_indice:
        return []
    return _filtrar(locs, patrones)
