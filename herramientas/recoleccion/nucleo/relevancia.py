"""Puerta de relevancia: decide si una página merece descargarse.

El lexicón vive en ``referencias/relevancia.json`` y sus términos derivan de los
``content_targets`` del catálogo (`referencias/fuentes_internet.json`) más los
términos propios del dominio (oferta solar). La evaluación **propone**, no
sustituye la decisión: los candidatos se escriben en ``candidatos.jsonl`` y la
descarga definitiva requiere aprobación (por archivo o por umbral).

No se infiere información: aquí solo se puntúa la presencia de términos.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

RUTA_LEXICO_POR_DEFECTO = (
    Path(__file__).resolve().parents[3] / "referencias" / "relevancia.json"
)


def _normalizar(texto: str) -> str:
    """Minúsculas sin acentos, con separadores convertidos en espacios.

    Así ``panel-solar_3kw`` y ``panel solar 3kw`` se comparan igual.
    """
    base = unicodedata.normalize("NFKD", texto or "")
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^0-9a-z]+", " ", base.lower())
    return re.sub(r"\s+", " ", base).strip()


@dataclass
class Veredicto:
    """Resultado de evaluar la relevancia de un contenido."""

    relevante: bool
    puntuacion: int
    terminos: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)


class Lexico:
    """Términos y umbral usados para puntuar la relevancia."""

    def __init__(
        self,
        umbral: int,
        fuertes: list[dict],
        campos: list[dict],
        exclusiones: list[str],
        exigir_fuerte: bool = False,
    ) -> None:
        self.umbral = umbral
        self.fuertes = fuertes
        self.campos = campos
        self.exclusiones = [_normalizar(e) for e in exclusiones]
        self.exigir_fuerte = exigir_fuerte

    def evaluar(self, url: str = "", titulo: str = "", texto: str = "") -> Veredicto:
        haystack = _normalizar(" ".join([unquote(url or ""), titulo or "", texto or ""]))
        puntuacion = 0
        terminos: list[str] = []
        motivos: list[str] = []
        hay_fuerte = False

        for entrada in self.fuertes:
            termino = _normalizar(str(entrada.get("termino", "")))
            if len(termino) < 3 or termino not in haystack:
                continue
            peso = int(entrada.get("peso", 1))
            puntuacion += peso
            hay_fuerte = True
            terminos.append(entrada["termino"])
            motivos.append(f"{entrada['termino']} (peso {peso}, campo {entrada.get('campo', '-')})")

        for entrada in self.campos:
            termino = _normalizar(str(entrada.get("termino", "")))
            if len(termino) < 3 or termino not in haystack:
                continue
            peso = int(entrada.get("peso", 1))
            puntuacion += peso
            terminos.append(entrada["termino"])
            motivos.append(f"{entrada['termino']} (peso {peso}, campo {entrada.get('campo', '-')})")

        for excl in self.exclusiones:
            if excl and excl in haystack:
                motivos.append(f"excluido por término «{excl}»")
                return Veredicto(False, 0, terminos, motivos)

        cumple_umbral = puntuacion >= self.umbral
        if self.exigir_fuerte and not hay_fuerte:
            motivos.append("sin término fuerte del dominio solar")
            return Veredicto(False, puntuacion, terminos, motivos)

        return Veredicto(cumple_umbral, puntuacion, terminos, motivos)


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
    )
