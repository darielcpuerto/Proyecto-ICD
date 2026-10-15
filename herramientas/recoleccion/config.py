"""Carga y validación de la configuración de fuentes.

Lee el catálogo `referencias/fuentes_internet.json` (schema_version 1.0) y lo
expone como objetos tipados. No completa ni infiere campos ausentes: lo que no
figura en el archivo queda como `None` o tupla vacía.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Error de lectura o validación de la configuración de fuentes."""


@dataclass(frozen=True)
class Fuente:
    """Una fuente de Internet declarada en el catálogo."""

    id: str
    nombre: str
    url: str
    categoria: str
    tipo: str
    estado: str
    prioridad: str
    datos_esperados: tuple[str, ...] = ()
    notas: str = ""

    def descripcion(self) -> str:
        return f"[{self.id}] {self.nombre} ({self.categoria}, {self.tipo}, prioridad {self.prioridad})"


@dataclass(frozen=True)
class Configuracion:
    """Catálogo de fuentes más las reglas globales de recolección."""

    ruta: Path
    schema_version: str
    fuentes: tuple[Fuente, ...]
    reglas_globales: dict


def _texto(valor: object) -> str:
    """Convierte a texto sin inventar contenido (None -> cadena vacía)."""
    return "" if valor is None else str(valor)


def _cargar_fuente(cruda: dict) -> Fuente:
    faltantes = [c for c in ("id", "name", "url") if not cruda.get(c)]
    if faltantes:
        raise ConfigError(
            f"Fuente sin campos obligatorios {faltantes}: {cruda!r}"
        )
    return Fuente(
        id=_texto(cruda.get("id")),
        nombre=_texto(cruda.get("name")),
        url=_texto(cruda.get("url")),
        categoria=_texto(cruda.get("category")),
        tipo=_texto(cruda.get("type")),
        estado=_texto(cruda.get("status")),
        prioridad=_texto(cruda.get("collection_priority")),
        datos_esperados=tuple(cruda.get("content_targets") or ()),
        notas=_texto(cruda.get("collection_notes")),
    )


def cargar_configuracion(ruta: Path) -> Configuracion:
    """Lee y valida el catálogo de fuentes desde `ruta`."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ConfigError(f"No existe el archivo de configuración: {ruta}")

    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON inválido en {ruta}: {exc}") from exc

    if not isinstance(datos, dict):
        raise ConfigError(f"Se esperaba un objeto JSON en {ruta}")

    fuentes_crudas = datos.get("sources")
    if not isinstance(fuentes_crudas, list) or not fuentes_crudas:
        raise ConfigError(f"`sources` debe ser una lista no vacía en {ruta}")

    fuentes = tuple(_cargar_fuente(f) for f in fuentes_crudas)

    ids = [f.id for f in fuentes]
    duplicados = {i for i in ids if ids.count(i) > 1}
    if duplicados:
        raise ConfigError(f"IDs de fuente duplicados: {sorted(duplicados)}")

    return Configuracion(
        ruta=ruta,
        schema_version=_texto(datos.get("schema_version")),
        fuentes=fuentes,
        reglas_globales=dict(datos.get("global_collection_rules") or {}),
    )


def filtrar(
    config: Configuracion,
    ids: list[str] | None = None,
    categorias: list[str] | None = None,
    prioridades: list[str] | None = None,
    estados: list[str] | None = None,
) -> tuple[Fuente, ...]:
    """Devuelve las fuentes que cumplen todos los filtros indicados."""

    def coincide(f: Fuente) -> bool:
        if ids and f.id not in ids and f.nombre not in ids:
            return False
        if categorias and f.categoria.lower() not in {c.lower() for c in categorias}:
            return False
        if prioridades and f.prioridad.lower() not in {p.lower() for p in prioridades}:
            return False
        if estados and f.estado.lower() not in {e.lower() for e in estados}:
            return False
        return True

    return tuple(f for f in config.fuentes if coincide(f))
