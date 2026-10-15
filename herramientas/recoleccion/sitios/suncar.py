"""Sitio SunCar (OLP-004): tienda estática (Next.js SSR).

No es navegable desde una única URL: se descubre su catálogo por el sitemap
declarado en ``robots.txt``, filtrando por patrones de ruta. ``/ofertas``
contiene las ofertas con precio en datos estructurados incrustados.
"""

from __future__ import annotations

from urllib.parse import urlparse

from ..nucleo.sitemap import sitemaps_de_robots, urls_de_sitemap
from .base import Sitio, dominio_normalizado


class SunCar(Sitio):
    id = "OLP-004"
    nombre = "SunCar"
    dominio = "suncarsrl.com"
    usar_sitemap = True
    patrones_sitemap = ("/ofertas", "/productos", "/tienda", "/servicios")
    patrones_relevancia = ("/ofertas", "/productos", "/tienda", "/servicios")

    def semillas(self, fetcher, texto_robots: str | None) -> list[str]:
        # La URL base para el sitemap se toma del catálogo.
        base = f"https://{self.dominio}"
        urls: list[str] = []
        for sitemap_url in sitemaps_de_robots(texto_robots, base):
            for url in urls_de_sitemap(fetcher, sitemap_url):
                if dominio_normalizado(urlparse(url).netloc) != self.dominio:
                    continue
                if self.patrones_sitemap and not any(p in url for p in self.patrones_sitemap):
                    continue
                if url not in urls:
                    urls.append(url)
        return urls


SITIO = SunCar()
