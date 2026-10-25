"""Puerta de relevancia en dos niveles: página y registro.

El lexicón vive en ``referencias/relevancia.json``. A diferencia de la primera
versión, la evaluación **respeta el campo** declarado para cada término: un
término fuerte marcado con ``campo: category`` no cuenta si solo aparece en el
nombre del producto. Así se evita que una lámpara «solar» o una batería de
teléfono entren como oferta solar.

Dos niveles:

1. ``evaluar_pagina``: decide si una página merece conservarse a partir de la
   URL, el título, la descripción y los nombres de datos estructurados.
2. ``evaluar_registro``: decide si un registro extraído es una oferta del
   dominio, exigiendo un término fuerte en ``exigir_fuerte_en`` y aplicando
   patrones negativos (inmuebles, baterías de móvil, placas de cocina, empleo…).

No se infiere información: aquí solo se puntúa la presencia de términos y se
informa del campo donde coincidieron.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

RUTA_LEXICO_POR_DEFECTO = (
    Path(__file__).resolve().parents[3] / "referencias" / "relevancia.json"
)

# Campos que pueden satisfacer la exigencia de término fuerte.
CAMPOS_FUERTES_POR_DEFECTO = ("product_name", "category", "brand")

# Campos que se revisan en busca de patrones negativos.
CAMPOS_NEGATIVOS_POR_DEFECTO = (
    "product_name", "description", "category", "brand",
)


def _normalizar(texto: str) -> str:
    """Minúsculas sin acentos, con separadores convertidos en espacios."""
    base = unicodedata.normalize("NFKD", texto or "")
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^0-9a-z]+", " ", base.lower())
    return re.sub(r"\s+", " ", base).strip()


@dataclass
class Veredicto:
    """Resultado de evaluar la relevancia de un contenido o registro."""

    relevante: bool
    puntuacion: int
    terminos: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)
    campos: list[str] = field(default_factory=list)


class Lexico:
    """Términos, patrones negativos y umbral usados para puntuar relevancia."""

    def __init__(
        self,
        umbral: int,
        fuertes: list[dict],
        campos: list[dict],
        exclusiones: list[str],
        exigir_fuerte: bool = False,
        exigir_fuerte_en: tuple[str, ...] | list[str] | None = None,
        terminos_negativos: tuple[str, ...] | list[str] | None = None,
        campos_negativos: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.umbral = umbral
        self.fuertes = fuertes
        self.campos = campos
        self.exclusiones = [_normalizar(e) for e in exclusiones]
        self.exigir_fuerte = exigir_fuerte
        self.exigir_fuerte_en = tuple(exigir_fuerte_en or CAMPOS_FUERTES_POR_DEFECTO)
        self.campos_negativos = tuple(
            campos_negativos or CAMPOS_NEGATIVOS_POR_DEFECTO
        )
        patrones = list(terminos_negativos or [])
        # Las exclusiones simples se siguen aplicando como patrones literales.
        patrones.extend(re.escape(e) for e in exclusiones if e)
        self.negativos = [re.compile(p, re.I) for p in patrones if p]

    # -- evaluación antigua (texto completo) ----------------------------
    def evaluar(self, url: str = "", titulo: str = "", texto: str = "") -> Veredicto:
        """Evalúa un texto completo sin restringir por campo.

        Se conserva por compatibilidad con el flujo ``--descubrir``. El flujo
        ``--todo`` usa ``evaluar_pagina`` y ``evaluar_registro``.
        """
        campos = {
            "url": _normalizar(unquote(url or "")),
            "titulo": _normalizar(titulo or ""),
            "texto": _normalizar(texto or ""),
        }
        haystack = " ".join(v for v in campos.values() if v)
        return self._puntuar(
            campos=campos,
            haystack=haystack,
            exigir_fuerte_en=None,
        )

    # -- nivel página ----------------------------------------------------
    def evaluar_pagina(
        self,
        url: str = "",
        titulo: str = "",
        descripcion: str = "",
        encabezados: list[str] | None = None,
        nombres_estructurados: list[str] | None = None,
    ) -> Veredicto:
        """Evalúa una página con evidencia de URL, título y datos estructurados."""
        nombres = " ".join(nombres_estructurados or [])
        campos = {
            "url": _normalizar(unquote(url or "")),
            "product_name": _normalizar(" ".join([titulo or "", nombres])),
            "description": _normalizar(descripcion or ""),
            "encabezados": _normalizar(" ".join(encabezados or [])),
        }
        haystack = " ".join(v for v in campos.values() if v)
        return self._puntuar(campos=campos, haystack=haystack)

    # -- nivel registro --------------------------------------------------
    def evaluar_registro(self, campos_registro: dict) -> Veredicto:
        """Evalúa un registro extraído respetando el campo de cada término."""
        normalizados = {
            clave: _normalizar(str(valor))
            for clave, valor in (campos_registro or {}).items()
            if valor not in (None, "", [], {})
        }
        haystack = " ".join(normalizados.values())
        return self._puntuar(campos=normalizados, haystack=haystack)

    # -- núcleo ----------------------------------------------------------
    def _puntuar(
        self,
        campos: dict[str, str],
        haystack: str,
        exigir_fuerte_en: tuple[str, ...] | None | bool = True,
    ) -> Veredicto:
        puntuacion = 0
        terminos: list[str] = []
        motivos: list[str] = []
        campos_coincidentes: list[str] = []
        hay_fuerte = False

        limite_fuerte = (
            self.exigir_fuerte_en if exigir_fuerte_en is True else
            exigir_fuerte_en if exigir_fuerte_en else ()
        )
        haystack_negativos = " ".join(
            campos.get(campo, "") for campo in self.campos_negativos
        ).strip() or haystack

        for tipo, entradas in (("fuerte", self.fuertes), ("contexto", self.campos)):
            for entrada in entradas:
                termino_original = str(entrada.get("termino", ""))
                termino = _normalizar(termino_original)
                if len(termino) < 3:
                    continue
                campo = str(entrada.get("campo", "product_name") or "product_name")
                if exigir_fuerte_en is None:
                    # Modo texto completo: cualquier campo sirve.
                    propio = haystack
                    encontrado = bool(termino) and termino in propio
                else:
                    propio = campos.get(campo, "")
                    encontrado = bool(propio) and termino in propio
                if not encontrado:
                    continue

                peso = int(entrada.get("peso", 1))
                puntuacion += peso
                terminos.append(termino_original)
                campos_coincidentes.append(campo)
                motivos.append(
                    f"{termino_original} (peso {peso}, campo {campo}, {tipo})"
                )
                if (
                    tipo == "fuerte"
                    and limite_fuerte
                    and any(c in limite_fuerte for c in (campo,))
                ):
                    hay_fuerte = True

        if exigir_fuerte_en is None:
            # En modo texto completo el término fuerte es fuerte por definición.
            hay_fuerte = any(
                _normalizar(str(e.get("termino", ""))) in haystack
                for e in self.fuertes
                if len(_normalizar(str(e.get("termino", "")))) >= 3
            )

        for patron in self.negativos:
            if patron.search(haystack_negativos):
                motivos.append(f"excluido por patrón negativo «{patron.pattern}»")
                return Veredicto(False, 0, terminos, motivos, campos_coincidentes)

        cumple_umbral = puntuacion >= self.umbral
        if self.exigir_fuerte and not hay_fuerte:
            motivos.append(
                "sin término fuerte del dominio solar en "
                + ", ".join(self.exigir_fuerte_en)
            )
            return Veredicto(False, puntuacion, terminos, motivos, campos_coincidentes)

        return Veredicto(
            cumple_umbral, puntuacion, terminos, motivos, campos_coincidentes
        )


def cargar_lexico(ruta: Path | None = None) -> Lexico:
    """Carga el lexicón desde disco."""
    ruta = Path(ruta) if ruta else RUTA_LEXICO_POR_DEFECTO
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return Lexico(
        umbral=int(datos.get("umbral", 2)),
        fuertes=list(datos.get("terminos_fuertes") or []),
        campos=list(datos.get("terminos_campos") or []),
        exclusiones=list(datos.get("exclusiones") or []),
        exigir_fuerte=bool(datos.get("exigir_fuerte", False)),
        exigir_fuerte_en=datos.get("exigir_fuerte_en"),
        terminos_negativos=datos.get("terminos_negativos"),
        campos_negativos=datos.get("campos_negativos"),
    )


def hash_lexico(ruta: Path | None = None) -> str:
    """Hash del archivo de lexicón, para dejarlo en ``resumen.json``."""
    ruta = Path(ruta) if ruta else RUTA_LEXICO_POR_DEFECTO
    return hashlib.sha256(ruta.read_bytes()).hexdigest()[:12]
