"""Sitio Bembete (OLP-002): clasificados con oferta solar.

En la pasada única solo se consideran **anuncios de detalle** (``/detalles/``),
descubiertos por el sitemap diario del sitio. La portada y las categorías son
páginas ``lista`` y no se descargan. Cada detalle trae la oferta en JSON-LD; si
no hay JSON-LD se usa el *flight stream* de Next.js (RSC) siempre que aporte un
nombre. No se aceptan precios sueltos detectados en texto.

El prefiltro de slug evita descargar los ~2.000–3.000 detalles diarios: solo
pasan los slugs con un término solar y sin patrones negativos (inmuebles,
baterías de móvil/triciclo, etc.). La decisión final la toma la evaluación por
campos del registro.
"""

from __future__ import annotations

import re
import unicodedata

from ..nucleo import extraccion, relevancia, sitemap
from ..nucleo.config import Fuente
from ..nucleo.urls import ruta_normalizada
from .base import (
    Candidato,
    EvidenciaPagina,
    OpcionesSitio,
    Sitio,
    TipoPagina,
    VeredictoPagina,
)

BASE = "https://bembete.com"

#: Raíces que hacen plausible un anuncio solar. Se comparan sobre el slug
#: normalizado (minúsculas, sin acentos, separadores como espacios).
TERMINOS_SLUG = (
    "solar", "panel", "placa", "fotovoltaic", "inversor", "bateria", "litio",
    "lifepo4", "controlador", "regulador", "microinversor", "celda", "modulo",
    "growatt", "victron", "deye", "felicity", "bluesun", "suncar", "kwh",
    "energia solar", "kit solar", "sistema solar",
)

#: Patrones que descartan un slug antes de descargarlo. Se toman del lexicón
#: (misma fuente que el filtro de registros) más una exclusión propia del sitio,
#: para que ambos filtros no diverjan.
PATRONES_NEGATIVOS_SLUG = tuple(
    patron.pattern for patron in relevancia.cargar_lexico().negativos
) + (r"lampara",)


def _normalizar_slug(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "")
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^0-9a-z]+", " ", base.lower())
    return re.sub(r"\s+", " ", base).strip()


class Bembete(Sitio):
    id = "OLP-002"
    nombre = "Bembete"
    dominio = "bembete.com"
    automatico = True
    objetivo_paginas = 250
    unidad_objetivo = "anuncio de detalle único"
    semillas_explicitas = (f"{BASE}/",)
    patrones_relevancia = ("panel", "solar", "inversor", "bateria")

    # -- candidatos -----------------------------------------------------
    def lotes_candidatos(
        self, fetcher, texto_robots: str | None, opciones: OpcionesSitio
    ):
        if opciones.urls_semilla:
            yield [Candidato(url=u, origen="url declarada") for u in opciones.urls_semilla]
            return

        diarios = sitemap.sitemaps_diarios(
            fetcher, texto_robots, BASE, ventana_dias=opciones.ventana_dias
        )
        if not diarios:
            yield [Candidato(url=u, origen="semilla") for u in self.semillas_explicitas]
            return

        vistos: set[str] = set()
        for url_sitemap, fecha in diarios:
            # El sitemap diario se lee solo cuando el lote anterior no bastó.
            urls = sitemap.urls_de_sitemap_diario(fetcher, url_sitemap, ("/detalles/",))
            lote: list[Candidato] = []
            for url in urls:
                candidato = Candidato(
                    url=url,
                    tipo_esperado=TipoPagina.DETALLE,
                    origen=f"sitemap {fecha.isoformat()}",
                    fecha_sitemap=fecha.isoformat(),
                )
                if candidato.url_canonica in vistos:
                    continue
                vistos.add(candidato.url_canonica)
                lote.append(candidato)
            yield lote

    def tipo_por_url(self, url: str) -> TipoPagina:
        ruta = ruta_normalizada(url)
        if ruta.startswith("/detalles/"):
            return TipoPagina.DETALLE
        if ruta in ("/", "") or ruta.startswith("/b/") or "page=" in ruta:
            return TipoPagina.LISTA
        if ruta.startswith(("/condiciones", "/politica", "/privacidad", "/contacto")):
            return TipoPagina.NAVEGACION
        return TipoPagina.CONTEXTO

    def prefiltro(self, url: str) -> tuple[bool, str]:
        ruta = ruta_normalizada(url)
        if not ruta.startswith("/detalles/"):
            # La clasificación por tipo decide si se descarga o no.
            return True, ""
        slug = _normalizar_slug(ruta.removeprefix("/detalles/"))
        if not any(termino in slug for termino in TERMINOS_SLUG):
            return False, "slug de detalle sin término solar"
        for patron in PATRONES_NEGATIVOS_SLUG:
            if re.search(patron, slug):
                return False, f"slug excluido por patrón «{patron}»"
        return True, ""

    # -- clasificación ---------------------------------------------------
    def clasificar_pagina(
        self,
        url: str,
        tipo_esperado: TipoPagina | None,
        evidencia: EvidenciaPagina,
        lexico,
    ) -> VeredictoPagina:
        tipo = tipo_esperado or self.tipo_por_url(url)
        if tipo is not TipoPagina.DETALLE:
            return super().clasificar_pagina(url, tipo, evidencia, lexico)
        veredicto = lexico.evaluar_pagina(
            url=url,
            titulo=evidencia.titulo,
            descripcion=evidencia.descripcion,
            encabezados=evidencia.encabezados,
            nombres_estructurados=evidencia.nombres_estructurados,
        )
        return VeredictoPagina(
            tipo=tipo,
            relevante=veredicto.relevante,
            puntuacion=veredicto.puntuacion,
            motivos=veredicto.motivos,
            terminos=veredicto.terminos,
        )

    # -- extracción ------------------------------------------------------
    def extraer(
        self,
        html: str,
        texto: str,
        url: str,
        fecha: str,
        fuente: Fuente,
        activos: dict[str, str] | None = None,
    ) -> list[dict]:
        registros = extraccion.extraer_json_ld(html, url, fecha, fuente)
        if not registros:
            # Sin JSON-LD se recurre al RSC, que solo aporta registros con nombre.
            registros = extraccion.extraer_incrustados(
                html, url, fecha, fuente, metodo="adaptador_bembete"
            )
        return registros

    # -- identidad -------------------------------------------------------
    def id_oferta(self, registro: dict) -> str | None:
        adicionales = registro.get("campos_adicionales") or {}
        identificador = adicionales.get("id_oferta") or adicionales.get("id")
        return str(identificador) if identificador else super().id_oferta(registro)


SITIO = Bembete()
