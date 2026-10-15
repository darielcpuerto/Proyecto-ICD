"""Extractores específicos por sitio.

Cada extractor conoce la estructura interna de un sitio y produce los mismos
registros trazables que la extracción genérica (`campos`, `campos_ausentes`,
`evidencia_cruda`, `ubicacion_evidencia`).

- ``revolico``: lee el estado Apollo (`__APOLLO_STATE__`) y el feed SSR de
  Next.js (`staticPropsFeed`).
- ``bembete``: lee los datos incrustados del *flight stream* de Next.js.
"""

from __future__ import annotations

import json
import re

from . import extraccion
from .config import Fuente


def _next_data(html: str) -> dict | None:
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _registro(fuente, url, fecha, ubicacion, entidad, metodo):
    campos, claves = extraccion.campos_desde_dict(entidad)
    return extraccion.crear_registro(
        fuente, url, fecha, metodo, ubicacion, campos, claves,
        json.dumps(entidad, ensure_ascii=False),
        advertencias=["valor tomado de datos estructurados del sitio"],
    )


def _clave_dedup(registro: dict) -> tuple:
    c = registro["campos"]
    return (c.get("product_name"), c.get("price"), c.get("currency"))


def _deduplicar(registros: list[dict]) -> list[dict]:
    vistos: set = set()
    salida: list[dict] = []
    for r in registros:
        k = _clave_dedup(r)
        if k == (None, None, None) or k in vistos:
            continue
        vistos.add(k)
        salida.append(r)
    return salida


def extraer_revolico(html: str, texto: str, url: str, fecha: str, fuente: Fuente) -> list[dict]:
    datos = _next_data(html)
    if not datos:
        return []
    metodo = "adaptador_revolico"
    regs: list[dict] = []

    page_props = (datos.get("props") or {}).get("pageProps") or {}

    # 1) Estado Apollo: anuncios de búsqueda/categoría (AdType:<id>).
    apollo = page_props.get("__APOLLO_STATE__")
    if isinstance(apollo, dict):
        for clave, entidad in apollo.items():
            if clave.startswith("AdType:") and isinstance(entidad, dict):
                regs.append(_registro(fuente, url, fecha, f"apollo:{clave}", entidad, metodo))

    # 2) Feed SSR de portada/categoría (staticPropsFeed.edges[].node).
    feed = (page_props.get("staticPropsFeed") or {}).get("feed") or {}
    for borde in feed.get("edges") or []:
        nodo = borde.get("node") if isinstance(borde, dict) else None
        if isinstance(nodo, dict):
            regs.append(_registro(fuente, url, fecha, f"feed:{nodo.get('id')}", nodo, metodo))

    return _deduplicar(regs)


def extraer_bembete(html: str, texto: str, url: str, fecha: str, fuente: Fuente) -> list[dict]:
    return extraccion.extraer_incrustados(
        html, url, fecha, fuente, metodo="adaptador_bembete"
    )


EXTRACTORES = {
    "revolico": extraer_revolico,
    "bembete": extraer_bembete,
}


def extraer(nombre: str, html: str, texto: str, url: str, fecha: str, fuente: Fuente) -> list[dict]:
    funcion = EXTRACTORES.get(nombre)
    return funcion(html, texto, url, fecha, fuente) if funcion else []
