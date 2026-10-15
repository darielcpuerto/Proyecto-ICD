"""Sitio Bembete (OLP-002): clasificados con oferta solar.

La portada entrega anuncios en el *flight stream* de Next.js (SSR) y las páginas
de detalle traen la oferta en JSON-LD. Los listados de categoría se construyen en
el cliente (JavaScript); sin navegador solo se obtiene su contenido estático.
"""

from __future__ import annotations

from ..nucleo import extraccion
from ..nucleo.config import Fuente
from .base import Sitio


class Bembete(Sitio):
    id = "OLP-002"
    nombre = "Bembete"
    dominio = "bembete.com"
    semillas_explicitas = (
        "https://bembete.com/",
        "https://bembete.com/b/c-Electr%C3%B3nica/",
        "https://bembete.com/b/c-Electrodom%C3%A9sticos/",
        "https://bembete.com/b/c-Ferreter%C3%ADa/",
    )
    patrones_relevancia = (
        "panel", "solar", "inversor", "bateria",
    )

    def extraer(
        self,
        html: str,
        texto: str,
        url: str,
        fecha: str,
        fuente: Fuente,
        activos: dict[str, str] | None = None,
    ) -> list[dict]:
        # La portada trae anuncios en el flight stream; las páginas de detalle
        # traen la oferta en JSON-LD. Se combinan ambos y se añaden los precios
        # detectados en texto, sin repetir la extracción genérica incrustada.
        return (
            extraccion.extraer_json_ld(html, url, fecha, fuente)
            + extraccion.extraer_incrustados(html, url, fecha, fuente, metodo="adaptador_bembete")
            + extraccion.extraer_precios_texto(texto, url, fecha, fuente)
        )


SITIO = Bembete()
