"""Política de acceso por sitio.

Combina tres fuentes de decisión, en este orden:

1. las directivas de `robots.txt` para el User-Agent del proyecto;
2. los avisos legales detectados en el propio `robots.txt` (texto que prohíbe
   la recolección automatizada);
3. las excepciones explícitas registradas en `politica_sitios.json`, que deben
   indicar quién autorizó la recolección y con qué motivo.

El resultado (`Decision`) se guarda en cada observación para dejar constancia
de por qué se recolectó o se omitió una fuente.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Fuente

RUTA_OVERRIDES_POR_DEFECTO = Path(__file__).resolve().parent / "politica_sitios.json"

# Frases que indican una prohibición explícita de recolección automatizada.
PATRONES_AVISO = (
    r"prohibit",
    r"scrap",
    r"automated means",
    r"data mine",
    r"written permission",
    r"express written",
)


@dataclass
class Decision:
    """Resultado de evaluar si una fuente puede recolectarse."""

    fuente_id: str
    puede_recolectar: bool
    motivo: str
    aviso_legal: str | None = None
    autorizado_por: str | None = None
    advertencias: list[str] = field(default_factory=list)


def detectar_aviso(texto_robots: str | None) -> str | None:
    """Devuelve las frases del robots.txt que sugieren un aviso legal."""
    if not texto_robots:
        return None
    halladas: list[str] = []
    for linea in texto_robots.splitlines():
        if not linea.lstrip().startswith("#"):
            continue
        if any(re.search(p, linea, re.I) for p in PATRONES_AVISO):
            limpia = linea.lstrip("# ").strip()
            if limpia:
                halladas.append(limpia)
    return " ".join(halladas) if halladas else None


def cargar_overrides(ruta: Path | None = None) -> dict[str, dict]:
    """Carga las excepciones explícitas de `politica_sitios.json`."""
    ruta = ruta or RUTA_OVERRIDES_POR_DEFECTO
    if not Path(ruta).is_file():
        return {}
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return {str(o["fuente_id"]): o for o in datos.get("overrides", [])}


def evaluar(
    fuente: Fuente,
    robots_permite: bool,
    texto_robots: str | None,
    override: dict | None = None,
) -> Decision:
    """Decide si `fuente` puede recolectarse y deja constancia del motivo."""
    aviso = detectar_aviso(texto_robots)
    advertencias: list[str] = []

    if not robots_permite:
        return Decision(
            fuente_id=fuente.id,
            puede_recolectar=False,
            motivo="robots.txt no permite la consulta con el User-Agent del proyecto",
            aviso_legal=aviso,
        )

    if aviso:
        if override and override.get("recolectar"):
            return Decision(
                fuente_id=fuente.id,
                puede_recolectar=True,
                motivo=override.get("motivo", "excepción explícita registrada"),
                aviso_legal=aviso,
                autorizado_por=override.get("autorizado_por"),
                advertencias=[
                    "robots.txt permite las directivas, pero incluye un aviso que "
                    "prohíbe la recolección automatizada; se recolecta por decisión "
                    f"registrada ({override.get('autorizado_por', 'sin autor')})."
                ],
            )
        return Decision(
            fuente_id=fuente.id,
            puede_recolectar=False,
            motivo="aviso legal en robots.txt prohíbe la recolección automatizada",
            aviso_legal=aviso,
        )

    return Decision(
        fuente_id=fuente.id,
        puede_recolectar=True,
        motivo="robots.txt permite la consulta con el User-Agent del proyecto",
        aviso_legal=aviso,
        advertencias=advertencias,
    )
