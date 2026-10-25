"""Almacenamiento con deduplicación por contenido.

Estructura creada bajo el directorio de salida (por defecto ``archivos/``)::

    <salida>/<FUENTE_ID>_<slug>/
        crudo/            HTML original (nombre estable por contenido)
        texto/            texto plano derivado
        activos/          bundle JavaScript u otros recursos declarados
        candidatos.jsonl  páginas candidatas y su clasificación
        descartes.jsonl   páginas/registros rechazados, con motivo
        manifest.jsonl    una línea JSON por observación (trazabilidad)
        datos.jsonl       registros estructurados aceptados
    <salida>/resumen.json resumen de la ejecución por fuente y total

Deduplicación
-------------
El crudo y el texto se nombran por *hash del contenido*, no por fecha::

    <host>_<ruta>_<sha256_12>.html
    <host>_<ruta>_<sha256_12>.txt

De modo que volver a obtener el mismo contenido **no crea archivos nuevos** ni
reescribe los existentes. La fecha de acceso se conserva en ``manifest.jsonl``.
El manifiesto registra el ``hash_contenido`` y los ``ids_oferta`` de cada
observación, lo que permite (a) no volver a solicitar una URL ya capturada y
(b) no repetir ofertas en ``datos.jsonl``.

Los errores transitorios (estado 0 o 5xx) se registran pero **no** bloquean la
URL para siempre: una ejecución posterior puede reintentarla.

No se descargan imágenes: su análisis no es relevante para el proyecto.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .urls import canonicalizar

_SIN_ACENTOS = re.compile(r"[^a-z0-9]+")
_SURROGADOS = re.compile(r"[\ud800-\udfff]")


def _sin_surrogados(valor):
    """Sustituye surrogates aislados por U+FFFD antes de serializar a UTF-8.

    Algunos JSON-LD del sitio incluyen escapes ``\\ud83d`` sin su pareja de
    ``\\udc00``. Python los acepta, pero UTF-8 no puede escribirlos. No se
    inventa contenido: el carácter roto se marca como reemplazo.
    """
    if isinstance(valor, str):
        return _SURROGADOS.sub("\ufffd", valor)
    if isinstance(valor, dict):
        return {_sin_surrogados(k): _sin_surrogados(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sin_surrogados(v) for v in valor]
    return valor


def _json(registro, **opciones) -> str:
    """Serializa a JSON UTF-8 seguro (sin surrogates aislados)."""
    return json.dumps(
        _sin_surrogados(registro), ensure_ascii=False, **opciones
    )


def ahora_utc() -> str:
    """Fecha/hora de consulta en ISO 8601 con zona UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(texto: str, maximo: int = 60) -> str:
    """Convierte texto en un identificador seguro para nombres de archivo."""
    base = unicodedata.normalize("NFKD", texto or "")
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    base = _SIN_ACENTOS.sub("-", base).strip("-")
    return base[:maximo] or "sin-nombre"


def hash_contenido(contenido: bytes) -> str:
    """Identificador estable de un contenido (primeros 12 hex de SHA-256)."""
    return hashlib.sha256(contenido).hexdigest()[:12]


class IndiceFuente:
    """Resumen deduplicado de lo ya recolectado para una fuente.

    Se reconstruye leyendo ``manifest.jsonl``. Permite no volver a pedir una URL
    ya capturada, no repetir el análisis de un contenido ya procesado y no
    volver a incorporar una oferta ya aceptada (por ``id_oferta``).
    """

    def __init__(self) -> None:
        self.urls_capturadas: set[str] = set()
        self.urls_intentadas: set[str] = set()
        self.hashes_contenido: set[str] = set()
        self.ofertas_vistas: set[str] = set()
        self.paginas_aceptadas: set[str] = set()

    def url_vista(self, url: str) -> bool:
        return canonicalizar(url) in self.urls_capturadas

    def url_intentada(self, url: str) -> bool:
        """True si la URL ya se solicitó con éxito o con error definitivo."""
        return canonicalizar(url) in self.urls_intentadas

    def hash_visto(self, hash12: str) -> bool:
        return hash12 in self.hashes_contenido

    def oferta_vista(self, id_oferta: str) -> bool:
        return bool(id_oferta) and id_oferta in self.ofertas_vistas

    def anotar(self, url: str, hash12: str | None) -> None:
        canonica = canonicalizar(url)
        self.urls_intentadas.add(canonica)
        self.urls_capturadas.add(canonica)
        if hash12:
            self.hashes_contenido.add(hash12)

    def anotar_intento(self, url: str) -> None:
        """Marca una URL como intentada sin considerarla capturada (4xx)."""
        self.urls_intentadas.add(canonicalizar(url))

    def anotar_ofertas(self, ids_oferta) -> None:
        self.ofertas_vistas.update(i for i in ids_oferta if i)


class Almacen:
    """Gestiona las rutas y la escritura de una recolección."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)

    # -- rutas ----------------------------------------------------------
    def carpeta_fuente(self, fuente_id: str, nombre: str) -> Path:
        carpeta = self.raiz / f"{fuente_id}_{slug(nombre)}"
        for sub in ("crudo", "texto", "activos"):
            (carpeta / sub).mkdir(parents=True, exist_ok=True)
        return carpeta

    @staticmethod
    def ruta_relativa(ruta: Path, raiz: Path) -> str:
        try:
            return str(ruta.relative_to(raiz))
        except ValueError:
            return str(ruta)

    @staticmethod
    def _nombre_base(url: str, hash12: str, extension: str) -> str:
        partes = urlparse(url)
        host = slug(partes.netloc)
        ruta = slug(Path(partes.path).stem if partes.path else "index") or "index"
        return f"{host}_{ruta}_{hash12}{extension}"

    # -- deduplicación --------------------------------------------------
    def cargar_indice(self, carpeta: Path) -> IndiceFuente:
        """Reconstruye el índice deduplicado a partir de ``manifest.jsonl``."""
        indice = IndiceFuente()
        manifiesto = carpeta / "manifest.jsonl"
        if not manifiesto.is_file():
            return indice
        for linea in manifiesto.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                registro = json.loads(linea)
            except json.JSONDecodeError:
                continue
            url = registro.get("url_solicitada")
            if not url:
                continue
            transitorio = bool(registro.get("error_transitorio"))
            if not transitorio:
                indice.urls_intentadas.add(
                    canonicalizar(registro.get("url_canonica") or url)
                )
            capturada = (
                registro.get("error") is None
                and isinstance(registro.get("estado_http"), int)
                and 200 <= registro["estado_http"] < 300
            )
            if capturada:
                indice.urls_capturadas.add(
                    canonicalizar(registro.get("url_canonica") or url)
                )
                hash12 = registro.get("hash_contenido")
                if hash12:
                    indice.hashes_contenido.add(hash12)
            if (
                registro.get("aceptada")
                and registro.get("tipo_pagina") in ("detalle", "datos")
            ):
                indice.paginas_aceptadas.add(
                    canonicalizar(registro.get("url_canonica") or url)
                )
            indice.anotar_ofertas(registro.get("ids_oferta") or [])
        return indice

    # -- escritura crudo/texto ------------------------------------------
    def guardar_crudo(self, carpeta: Path, url: str, contenido: bytes) -> tuple[Path, str, bool]:
        """Guarda el HTML crudo con nombre estable por contenido.

        Devuelve ``(ruta, hash12, ya_existia)``. Si ya existía, no lo reescribe.
        """
        hash12 = hash_contenido(contenido)
        destino = carpeta / "crudo" / self._nombre_base(url, hash12, ".html")
        ya_existia = destino.exists()
        if not ya_existia:
            destino.write_bytes(contenido)
        return destino, hash12, ya_existia

    def guardar_activo(self, carpeta: Path, url: str, contenido: bytes) -> tuple[Path, str, bool]:
        """Guarda un activo (p. ej. el bundle JS) con nombre estable por contenido."""
        hash12 = hash_contenido(contenido)
        extension = Path(urlparse(url).path).suffix or ".bin"
        destino = carpeta / "activos" / self._nombre_base(url, hash12, extension)
        ya_existia = destino.exists()
        if not ya_existia:
            destino.write_bytes(contenido)
        return destino, hash12, ya_existia

    def guardar_texto(self, carpeta: Path, url: str, hash12: str, texto: str) -> Path:
        destino = carpeta / "texto" / self._nombre_base(url, hash12, ".txt")
        if destino.exists():
            return destino
        destino.write_text(_sin_surrogados(texto), encoding="utf-8")
        return destino

    # -- manifest y datos ------------------------------------------------
    def registrar(self, carpeta: Path, registro: dict) -> None:
        """Añade una observación al manifiesto JSONL de la fuente."""
        with (carpeta / "manifest.jsonl").open("a", encoding="utf-8") as archivo:
            archivo.write(_json(registro) + "\n")

    def registrar_datos(self, carpeta: Path, registros: list[dict]) -> None:
        """Añade registros estructurados al archivo ``datos.jsonl`` de la fuente."""
        if not registros:
            return
        with (carpeta / "datos.jsonl").open("a", encoding="utf-8") as archivo:
            for registro in registros:
                archivo.write(_json(registro) + "\n")

    # -- candidatos (puerta de relevancia) ------------------------------
    @staticmethod
    def ruta_candidatos(carpeta: Path) -> Path:
        return carpeta / "candidatos.jsonl"

    def escribir_candidatos(self, carpeta: Path, candidatos: list[dict]) -> Path:
        destino = self.ruta_candidatos(carpeta)
        with destino.open("w", encoding="utf-8") as archivo:
            for candidato in candidatos:
                archivo.write(_json(candidato) + "\n")
        return destino

    def leer_candidatos(self, carpeta: Path) -> list[dict]:
        destino = self.ruta_candidatos(carpeta)
        if not destino.is_file():
            return []
        candidatos: list[dict] = []
        for linea in destino.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                candidatos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
        return candidatos

    # -- descartes ------------------------------------------------------
    @staticmethod
    def ruta_descartes(carpeta: Path) -> Path:
        return carpeta / "descartes.jsonl"

    def registrar_descartes(self, carpeta: Path, descartes: list[dict]) -> None:
        """Añade descartes con motivo. Nunca guarda el contenido completo."""
        if not descartes:
            return
        with self.ruta_descartes(carpeta).open("a", encoding="utf-8") as archivo:
            for descarte in descartes:
                archivo.write(_json(descarte) + "\n")

    def leer_descartes(self, carpeta: Path) -> list[dict]:
        destino = self.ruta_descartes(carpeta)
        if not destino.is_file():
            return []
        salida: list[dict] = []
        for linea in destino.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                salida.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
        return salida

    # -- resumen --------------------------------------------------------
    def escribir_resumen(self, resumen: dict) -> Path:
        """Escribe ``resumen.json`` de forma determinista (claves ordenadas)."""
        destino = self.raiz / "resumen.json"
        destino.write_text(
            _json(resumen, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return destino


def git_commit(raiz: Path) -> str | None:
    """Devuelve el commit actual del repositorio, si está disponible."""
    try:
        salida = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(raiz),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return salida.stdout.strip() or None
