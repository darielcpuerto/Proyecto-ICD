"""Registro de sitios especializados.

Cada sitio vive en su propio módulo y expone un objeto ``SITIO``. El núcleo
consulta aquí qué sitio corresponde a una fuente del catálogo; si no hay módulo
propio, se usa el sitio genérico (URL declarada + extracción genérica).
"""

from __future__ import annotations

from ..nucleo.config import Fuente
from .base import Sitio, SitioGenerico
from .bembe import SITIO as BEMBETE
from .infinity import SITIO as INFINITY
from .suncar import SITIO as SUNCAR

REGISTRO: dict[str, Sitio] = {
    sitio.id: sitio for sitio in (BEMBETE, SUNCAR, INFINITY)
}


def obtener(fuente_id: str) -> Sitio | None:
    """Devuelve el sitio especializado de una fuente, o None."""
    return REGISTRO.get(fuente_id)


def para_fuente(fuente: Fuente) -> Sitio:
    """Devuelve el sitio de una fuente (genérico si no hay módulo propio)."""
    return REGISTRO.get(fuente.id) or SitioGenerico(fuente)


__all__ = ["REGISTRO", "Sitio", "SitioGenerico", "obtener", "para_fuente"]
