"""Lectura de sitemaps XML.

Permite descubrir las páginas de una tienda a partir de su sitemap (o del
sitemap declarado en `robots.txt`), sin depender de seguir enlaces del menú.
"""

from __future__ import annotations

import gzip
import re
from html import unescape
from urllib.parse import urljoin

from .fetcher import Fetcher

PATRON_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.I)


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


def urls_de_sitemap(fetcher: Fetcher, url: str, max_sitemaps: int = 10) -> list[str]:
    """Devuelve las URLs de páginas de un sitemap (recorre índices de sitemap)."""
    locs, es_indice = _locs(fetcher, url)
    if not es_indice:
        return locs
    urls: list[str] = []
    for sub in locs[:max_sitemaps]:
        urls.extend(urls_de_sitemap(fetcher, sub, max_sitemaps))
    return urls
