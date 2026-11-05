"""Sitio ElYerroMenu (OLP-001): clasificados con oferta solar.

Adaptador basado en el flujo ``--todo``: descubre candidatos a partir de la
semilla del catálogo, clasifica páginas por URL y extrae registros con el
método genérico de extracción estructurada (JSON-LD / datos incrustados /
heurística de texto).

No se conserva HTML crudo ni texto completo: solo campos y evidencia saneada,
por decisión de protección de datos personales del vendedor.
"""

from __future__ import annotations

from ..nucleo.config import Fuente
from .base import (
    Candidato,
    EvidenciaPagina,
    OpcionesSitio,
    Sitio,
    TipoPagina,
    VeredictoPagina,
)

BASE = "https://elyerromenu.com/"


class ElYerroMenu(Sitio):
    id = "OLP-001"
    nombre = "ElYerroMenu"
    dominio = "elyerromenu.com"
    automatico = True
    objetivo_paginas = 300
    unidad_objetivo = "anuncio único"
    semillas_explicitas = (BASE,)

    #: No se conserva HTML crudo ni texto completo: solo campos y evidencia
    #: saneada, por protección de datos personales del vendedor.
    guardar_crudo = False
    guardar_texto = False
    #: El flujo anterior (--descubrir/--recolectar) guarda crudo y no aplica
    ## el saneamiento del sitio; se rechaza para no filtrar PII.
    solo_pasada_unica = True
    advertencias_saneamiento = (
        "no se conserva HTML crudo ni texto completo: solo campos y evidencia saneada",
        "datos personales omitidos: nombre, teléfono, email e identificadores del "
        "vendedor; se conserva la URL del anuncio",
    )

    # -- candidatos ------------------------------------------------------
    def lotes_candidatos(
        self, fetcher, texto_robots: str | None, opciones: OpcionesSitio
    ) -> list[list[Candidato]]:
        """Devuelve un único lote con la semilla del catálogo."""
        urls = list(opciones.urls_semilla) or self.semillas(fetcher, texto_robots)
        return [[Candidato(url=u, tipo_esperado=TipoPagina.DETALLE, origen="semilla") for u in urls]]

    # -- clasificación por URL ------------------------------------------
    def tipo_por_url(self, url: str) -> TipoPagina:
        return TipoPagina.DETALLE

    def prefiltro(self, url: str) -> tuple[bool, str]:
        """Descarta URLs que no sean del dominio propio."""
        from urllib.parse import urlparse

        netloc = urlparse(url).netloc.lower().removeprefix("www.")
        if netloc != self.dominio:
            return False, f"dominio ajeno: {netloc}"
        return True, ""

    # -- clasificación de página ----------------------------------------
    def clasificar_pagina(
        self,
        url: str,
        tipo_esperado: TipoPagina | None,
        evidencia: EvidenciaPagina,
        lexico,
    ) -> VeredictoPagina:
        tipo = tipo_esperado or self.tipo_por_url(url) or TipoPagina.CONTEXTO
        if tipo not in (TipoPagina.DETALLE, TipoPagina.DATOS, TipoPagina.TECNICA):
            return VeredictoPagina(
                tipo=tipo,
                relevante=False,
                motivos=[f"tipo de página «{tipo.value}» no cuenta como oferta"],
            )
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

    # -- saneamiento -----------------------------------------------------
    def metadatos_pagina(
        self, titulo: str, descripcion: str, html: str
    ) -> tuple[str, str]:
        """Devuelve título y descripción sin modificar (sin PII conocida en el sitio)."""
        return titulo, descripcion

    def url_para_manifest(self, url_solicitada: str, url_final: str) -> str:
        """URL canónica para el manifiesto: la misma solicitada."""
        return url_solicitada or url_final


SITIO = ElYerroMenu()
