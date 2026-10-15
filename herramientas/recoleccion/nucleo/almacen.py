"""Almacenamiento con deduplicación por contenido.

Estructura creada bajo el directorio de salida (por defecto ``archivos/``)::

    <salida>/<FUENTE_ID>_<slug>/
        crudo/            HTML original (nombre estable por contenido)
        texto/            texto plano derivado
        candidatos.jsonl  páginas descubiertas y su relevancia
        manifest.jsonl    una línea JSON por observación (trazabilidad)
        datos.jsonl       registros estructurados

Deduplicación
-------------
El crudo y el texto se nombran por *hash del contenido*, no por fecha::

    <host>_<ruta>_<sha256_12>.html
    <host>_<ruta>_<sha256_12>.txt

De modo que volver a obtener el mismo contenido **no crea archivos nuevos** ni
reescribe los existentes. La fecha de acceso se conserva en ``manifest.jsonl``.
El manifiesto registra el ``hash_contenido`` de cada observación, lo que permite
(a) no volver a solicitar una URL ya capturada y (b) no repetir registros en
``datos.jsonl``.

No se descargan imágenes: su análisis no es relevante para el proyecto.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_SIN_ACENTOS = re.compile(r"[^a-z0-9]+")


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
    ya capturada y no repetir el análisis de un contenido ya procesado.
    """

    def __init__(self) -> None:
        self.urls_capturadas: set[str] = set()
        self.urls_intentadas: set[str] = set()
        self.hashes_contenido: set[str] = set()

    def url_vista(self, url: str) -> bool:
        return url in self.urls_capturadas

    def url_intentada(self, url: str) -> bool:
        """True si la URL ya se solicitó alguna vez (con éxito o con error)."""
        return url in self.urls_intentadas

    def hash_visto(self, hash12: str) -> bool:
        return hash12 in self.hashes_contenido

    def anotar(self, url: str, hash12: str | None) -> None:
        self.urls_intentadas.add(url)
        self.urls_capturadas.add(url)
        if hash12:
            self.hashes_contenido.add(hash12)


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
            indice.urls_intentadas.add(url)
            capturada = (
                registro.get("error") is None
                and isinstance(registro.get("estado_http"), int)
                and 200 <= registro["estado_http"] < 300
            )
            if capturada:
                indice.urls_capturadas.add(url)
                hash12 = registro.get("hash_contenido")
                if hash12:
                    indice.hashes_contenido.add(hash12)
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
        destino.write_text(texto, encoding="utf-8")
        return destino

    # -- manifest y datos ------------------------------------------------
    def registrar(self, carpeta: Path, registro: dict) -> None:
        """Añade una observación al manifiesto JSONL de la fuente."""
        with (carpeta / "manifest.jsonl").open("a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    def registrar_datos(self, carpeta: Path, registros: list[dict]) -> None:
        """Añade registros estructurados al archivo ``datos.jsonl`` de la fuente."""
        if not registros:
            return
        with (carpeta / "datos.jsonl").open("a", encoding="utf-8") as archivo:
            for registro in registros:
                archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    # -- candidatos (puerta de relevancia) ------------------------------
    @staticmethod
    def ruta_candidatos(carpeta: Path) -> Path:
        return carpeta / "candidatos.jsonl"

    def escribir_candidatos(self, carpeta: Path, candidatos: list[dict]) -> Path:
        destino = self.ruta_candidatos(carpeta)
        with destino.open("w", encoding="utf-8") as archivo:
            for candidato in candidatos:
                archivo.write(json.dumps(candidato, ensure_ascii=False) + "\n")
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
