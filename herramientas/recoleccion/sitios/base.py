"""Base común de los sitios especializados.

Contrato de un sitio para la pasada única (``--todo``):

- ``lotes_candidatos``: genera URLs candidatas agrupadas en lotes (por ejemplo,
  un lote por sitemap diario). El núcleo los consume en orden y se detiene al
  alcanzar el objetivo, de modo que la ventana de descubrimiento es adaptativa.
- ``tipo_por_url``: clasifica por URL **antes** de descargar. Las páginas
  ``lista``, ``contexto`` y ``navegacion`` no se descargan.
- ``prefiltro``: descarta por patrón de URL/slug sin petición de red.
- ``clasificar_pagina``: decide, ya descargada, si la página es relevante.
- ``filtrar_registros``: exige nombre y término fuerte, aplica negativos y
  clasifica el tipo de oferta. Devuelve aceptados y descartes.
- ``id_oferta`` / ``url_oferta`` / ``tipo_oferta``: identidad canónica.

Los sitios no descargan nada por sí mismos: solo declaran *dónde* y *cómo*.
El núcleo se encarga de la red, la política, la deduplicación y el
almacenamiento. No se usa navegador: el contenido se obtiene con HTTP.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from ..nucleo import extraccion, relevancia
from ..nucleo.config import Fuente
from ..nucleo.urls import canonicalizar


def dominio_normalizado(netloc: str) -> str:
    """Normaliza el dominio ignorando el prefijo ``www.``."""
    return netloc.lower().removeprefix("www.")


class TipoPagina(str, Enum):
    """Tipos de página del flujo de recolección."""

    DETALLE = "detalle"
    DATOS = "datos"
    LISTA = "lista"
    CONTEXTO = "contexto"
    NAVEGACION = "navegacion"
    TECNICA = "tecnica"


#: Tipos que se descargan y pueden aportar ofertas al dataset.
TIPOS_PROCESABLES = (TipoPagina.DETALLE, TipoPagina.DATOS, TipoPagina.TECNICA)
#: Tipos que cuentan para el objetivo de páginas de oferta.
TIPOS_CONTABLES = (TipoPagina.DETALLE, TipoPagina.DATOS)


@dataclass
class Candidato:
    """URL candidata generada por un sitio, todavía sin descargar."""

    url: str
    tipo_esperado: TipoPagina | None = None
    origen: str = "semilla"
    prioridad: int = 100
    fecha_sitemap: str | None = None
    motivo: str = ""

    @property
    def url_canonica(self) -> str:
        return canonicalizar(self.url)


@dataclass
class VeredictoPagina:
    """Resultado de clasificar una página."""

    tipo: TipoPagina
    relevante: bool
    puntuacion: int = 0
    motivos: list[str] = field(default_factory=list)
    terminos: list[str] = field(default_factory=list)

    @property
    def procesable(self) -> bool:
        return self.tipo in TIPOS_PROCESABLES

    @property
    def cuenta(self) -> bool:
        return self.tipo in TIPOS_CONTABLES


@dataclass
class EvidenciaPagina:
    """Evidencia disponible para clasificar una página."""

    titulo: str = ""
    descripcion: str = ""
    encabezados: list[str] = field(default_factory=list)
    nombres_estructurados: list[str] = field(default_factory=list)


@dataclass
class ObjetivoFuente:
    """Objetivo de recolección de una fuente."""

    unidad: str
    objetivo: int | None
    paginas_que_cuentan: tuple[str, ...] = ()


@dataclass
class OpcionesSitio:
    """Opciones que el núcleo comunica a los adaptadores."""

    ventana_dias: int = 30
    objetivo_paginas: int | None = None
    max_intentos: int = 300
    simular: bool = False
    urls_semilla: tuple[str, ...] = ()


class Sitio:
    """Sitio genérico: usa las semillas declaradas y la extracción genérica."""

    id: str = ""
    nombre: str = ""
    dominio: str = ""
    patrones_relevancia: tuple[str, ...] = ()
    #: Si es True, las semillas provienen del sitemap del sitio.
    usar_sitemap: bool = False
    patrones_sitemap: tuple[str, ...] = ()
    #: Semillas explícitas (tienen prioridad sobre el sitemap).
    semillas_explicitas: tuple[str, ...] = ()
    #: Objetivo de anuncios/ofertas únicas; ``None`` = todas las disponibles.
    objetivo_paginas: int | None = None
    #: Unidad del objetivo, para el reporte.
    unidad_objetivo: str = "oferta única"
    #: Si es False, la fuente no se recolecta automáticamente en ``--todo``.
    automatico: bool = True

    # -- objetivo -------------------------------------------------------
    def objetivo(self, opciones: OpcionesSitio) -> ObjetivoFuente:
        return ObjetivoFuente(
            unidad=self.unidad_objetivo,
            objetivo=opciones.objetivo_paginas or self.objetivo_paginas,
            paginas_que_cuentan=("/detalles/",) if self.objetivo_paginas else (),
        )

    # -- candidatos -----------------------------------------------------
    def semillas(self, fetcher, texto_robots: str | None) -> list[str]:
        if self.semillas_explicitas:
            return list(self.semillas_explicitas)
        return []

    def lotes_candidatos(
        self, fetcher, texto_robots: str | None, opciones: OpcionesSitio
    ) -> list[list[Candidato]]:
        """Lotes de candidatos, en orden de preferencia.

        El núcleo consume los lotes de uno en uno y se detiene al alcanzar el
        objetivo. Por defecto, un único lote con las semillas.
        """
        urls = list(opciones.urls_semilla) or self.semillas(fetcher, texto_robots)
        return [[Candidato(url=u, origen="semilla") for u in urls]]

    # -- clasificación por URL ------------------------------------------
    def tipo_por_url(self, url: str) -> TipoPagina | None:
        return None

    def prefiltro(self, url: str) -> tuple[bool, str]:
        """Descarta URLs no crawleables o no pertinentes antes de la red."""
        return True, ""

    # -- clasificación de página ----------------------------------------
    def clasificar_pagina(
        self,
        url: str,
        tipo_esperado: TipoPagina | None,
        evidencia: EvidenciaPagina,
        lexico: relevancia.Lexico,
    ) -> VeredictoPagina:
        tipo = tipo_esperado or self.tipo_por_url(url) or TipoPagina.CONTEXTO
        if tipo in (TipoPagina.LISTA, TipoPagina.CONTEXTO, TipoPagina.NAVEGACION):
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

    # -- filtro de registros --------------------------------------------
    def filtrar_registros(
        self, registros: list[dict], lexico: relevancia.Lexico
    ) -> tuple[list[dict], list[dict]]:
        """Separa registros aceptados y descartes (por defecto, estricto)."""
        aceptados: list[dict] = []
        descartes: list[dict] = []
        for registro in registros:
            campos = registro.get("campos") or {}
            nombre = str(campos.get("product_name") or "").strip()
            veredicto = lexico.evaluar_registro(campos)
            if not nombre:
                descartes.append({
                    "registro": registro,
                    "motivo": "registro sin product_name",
                    "puntuacion": veredicto.puntuacion,
                    "terminos": veredicto.terminos,
                })
                continue
            if not veredicto.relevante:
                descartes.append({
                    "registro": registro,
                    "motivo": "; ".join(veredicto.motivos) or "sin término fuerte",
                    "puntuacion": veredicto.puntuacion,
                    "terminos": veredicto.terminos,
                })
                continue
            registro["relevancia"] = {
                "relevante": True,
                "puntuacion": veredicto.puntuacion,
                "terminos": veredicto.terminos,
                "campos": veredicto.campos,
            }
            aceptados.append(registro)
        return aceptados, descartes

    # -- identidad ------------------------------------------------------
    def id_oferta(self, registro: dict) -> str | None:
        adicionales = registro.get("campos_adicionales") or {}
        for clave in ("id_oferta", "id_catalogo", "id", "idinterno", "sku", "@id"):
            valor = adicionales.get(clave)
            if valor not in (None, "", []):
                return str(valor)
        return canonicalizar(str(registro.get("url_origen") or ""))

    def url_oferta(self, registro: dict) -> str:
        return canonicalizar(str(registro.get("url_origen") or ""))

    def tipo_oferta(self, registro: dict) -> str:
        return "oferta"

    def tipo_pagina_registro(self, tipo: TipoPagina) -> str:
        """Tipo de página que se anota en el registro aceptado."""
        return tipo.value

    # -- activos y extracción -------------------------------------------
    def activos(self, html: str, url: str) -> list[str]:
        """Recursos que el núcleo debe obtener y pasar a ``extraer``."""
        return []

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

    # -- compatibilidad --------------------------------------------------
    def relevante_por_patron(self, url: str) -> bool:
        return any(p in url for p in self.patrones_relevancia)


class SitioGenerico(Sitio):
    """Sitio sin módulo propio: una sola semilla (la URL del catálogo).

    No se recolecta automáticamente en ``--todo``: se registra como omitido y
    se remite a revisión manual.
    """

    automatico = False

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


def clave_registro(registro: dict) -> tuple:
    """Clave de respaldo dentro de una misma página: (nombre, precio, moneda)."""
    campos = registro.get("campos") or {}
    return (
        campos.get("product_name"),
        campos.get("price"),
        campos.get("currency"),
    )


def deduplicar_registros(registros: list[dict]) -> list[dict]:
    """Elimina representaciones repetidas de una misma oferta.

    Primero por identidad (``id_oferta`` / URL) y solo como respaldo, dentro de
    la misma página, por ``(product_name, price, currency)``. No fusiona
    anuncios distintos que coincidan en nombre y precio.
    """
    vistos_id: set[str] = set()
    vistos_contenido: set[tuple] = set()
    salida: list[dict] = []
    for registro in registros:
        identidad = registro.get("id_oferta") or canonicalizar(
            str(registro.get("url_origen") or "")
        )
        contenido = clave_registro(registro)
        if identidad and identidad in vistos_id:
            continue
        if contenido != (None, None, None) and contenido in vistos_contenido:
            continue
        if identidad:
            vistos_id.add(identidad)
        if contenido != (None, None, None):
            vistos_contenido.add(contenido)
        salida.append(registro)
    return salida
