"""Sitio SunCar (OLP-004): tienda estática (Next.js SSR).

En la pasada única solo se descargan las dos páginas de catálogo
(``/ofertas`` y ``/productos``). ``/tienda``, ``/servicios`` y ``/blog`` son
páginas de contexto: no se descargan. Las ofertas se identifican por su código
``OF-...`` y se deduplican por él; cada oferta puede aparecer repetida en ambas
páginas.
"""

from __future__ import annotations

from urllib.parse import urlparse

from ..nucleo import sitemap
from ..nucleo.config import Fuente
from .base import (
    Candidato,
    EvidenciaPagina,
    OpcionesSitio,
    Sitio,
    TipoPagina,
    VeredictoPagina,
    dominio_normalizado,
)

BASE = "https://suncarsrl.com"
RUTAS_OFERTA = ("/ofertas", "/productos")


class SunCar(Sitio):
    id = "OLP-004"
    nombre = "SunCar"
    dominio = "suncarsrl.com"
    automatico = True
    objetivo_paginas = None
    unidad_objetivo = "oferta única"
    usar_sitemap = True
    patrones_sitemap = RUTAS_OFERTA
    patrones_relevancia = RUTAS_OFERTA
    semillas_explicitas = tuple(f"{BASE}{ruta}" for ruta in RUTAS_OFERTA)

    def lotes_candidatos(
        self, fetcher, texto_robots: str | None, opciones: OpcionesSitio
    ) -> list[list[Candidato]]:
        if opciones.urls_semilla:
            return [[Candidato(url=u, origen="url declarada") for u in opciones.urls_semilla]]

        urls: list[str] = []
        for sitemap_url in sitemap.sitemaps_de_robots(texto_robots, BASE):
            for url in sitemap.urls_de_sitemap(fetcher, sitemap_url):
                if dominio_normalizado(urlparse(url).netloc) != self.dominio:
                    continue
                if urlparse(url).path.rstrip("/") not in RUTAS_OFERTA:
                    continue
                if url not in urls:
                    urls.append(url)

        # Las rutas conocidas son la referencia mínima aunque el sitemap falle.
        for semilla in self.semillas_explicitas:
            if semilla not in urls:
                urls.append(semilla)

        return [[
            Candidato(url=u, tipo_esperado=TipoPagina.DATOS, origen="sitemap")
            for u in urls
        ]]

    def tipo_por_url(self, url: str) -> TipoPagina:
        ruta = urlparse(url).path.rstrip("/") or "/"
        if ruta in RUTAS_OFERTA:
            return TipoPagina.DATOS
        if ruta.startswith(("/tienda", "/servicios", "/blog")):
            return TipoPagina.CONTEXTO
        return TipoPagina.CONTEXTO

    def clasificar_pagina(
        self,
        url: str,
        tipo_esperado: TipoPagina | None,
        evidencia: EvidenciaPagina,
        lexico,
    ) -> VeredictoPagina:
        tipo = tipo_esperado or self.tipo_por_url(url)
        if tipo is TipoPagina.DATOS:
            return VeredictoPagina(
                tipo=tipo,
                relevante=True,
                motivos=["catálogo de ofertas declarado por el sitio"],
            )
        return super().clasificar_pagina(url, tipo, evidencia, lexico)

    def filtrar_registros(self, registros: list[dict], lexico):
        """Acepta todo el catálogo con nombre y clasifica por ``OF-...``."""
        aceptados: list[dict] = []
        descartes: list[dict] = []
        for registro in registros:
            campos = registro.get("campos") or {}
            nombre = str(campos.get("product_name") or "").strip()
            if not nombre:
                descartes.append({
                    "registro": registro,
                    "motivo": "registro sin product_name",
                    "puntuacion": 0,
                    "terminos": [],
                })
                continue
            registro["relevancia"] = {
                "relevante": True,
                "puntuacion": 0,
                "terminos": [],
                "campos": [],
                "motivo": "catálogo completo del sitio",
            }
            aceptados.append(registro)
        return aceptados, descartes

    def id_oferta(self, registro: dict) -> str | None:
        adicionales = registro.get("campos_adicionales") or {}
        identificador = adicionales.get("id")
        return str(identificador) if identificador else super().id_oferta(registro)

    def tipo_oferta(self, registro: dict) -> str:
        return "oferta"


SITIO = SunCar()
