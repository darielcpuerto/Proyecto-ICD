"""Almacenamiento de las observaciones conservando su procedencia.

Estructura creada bajo el directorio de salida (por defecto `archivos/`):

    <salida>/<FUENTE_ID>_<slug>/
        crudo/      HTML original tal como se recibió
        texto/      texto plano derivado (para búsqueda posterior)
        imagenes/   imágenes descargadas cuando son accesibles
        manifest.jsonl   una línea JSON por observación (trazabilidad)
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


def huella(url: str, fecha: str) -> str:
    """Identificador estable derivado de la URL y la fecha de consulta."""
    return hashlib.sha1(f"{url}|{fecha}".encode("utf-8")).hexdigest()[:12]


class Almacen:
    """Gestiona las rutas y la escritura de una recolección."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)

    def carpeta_fuente(self, fuente_id: str, nombre: str) -> Path:
        carpeta = self.raiz / f"{fuente_id}_{slug(nombre)}"
        for sub in ("crudo", "texto", "imagenes"):
            (carpeta / sub).mkdir(parents=True, exist_ok=True)
        return carpeta

    @staticmethod
    def _nombre_base(url: str, fecha: str, content_type: str = "") -> str:
        partes = urlparse(url)
        host = slug(partes.netloc)
        ruta = slug(Path(partes.path).stem or "index")
        extension = Path(partes.path).suffix if partes.path else ""
        if not extension:
            extension = ".png" if "image" in content_type else ".html"
        return f"{fecha.replace(':', '').replace('-', '')}_{host}_{ruta}_{huella(url, fecha)}{extension}"

    def guardar_crudo(self, carpeta: Path, url: str, fecha: str, contenido: bytes) -> Path:
        destino = carpeta / "crudo" / self._nombre_base(url, fecha, "text/html")
        destino.write_bytes(contenido)
        return destino

    def guardar_texto(self, carpeta: Path, url: str, fecha: str, texto: str) -> Path:
        destino = carpeta / "texto" / self._nombre_base(url, fecha, "text/plain").replace(".html", ".txt")
        destino.write_text(texto, encoding="utf-8")
        return destino

    def guardar_imagen(self, carpeta: Path, url: str, fecha: str, contenido: bytes, content_type: str) -> Path:
        destino = carpeta / "imagenes" / self._nombre_base(url, fecha, content_type)
        destino.write_bytes(contenido)
        return destino

    def registrar(self, carpeta: Path, registro: dict) -> None:
        """Añade una observación al manifiesto JSONL de la fuente."""
        with (carpeta / "manifest.jsonl").open("a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    def registrar_datos(self, carpeta: Path, registros: list[dict]) -> None:
        """Añade registros estructurados al archivo `datos.jsonl` de la fuente."""
        if not registros:
            return
        with (carpeta / "datos.jsonl").open("a", encoding="utf-8") as archivo:
            for registro in registros:
                archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    @staticmethod
    def ruta_relativa(ruta: Path, raiz: Path) -> str:
        try:
            return str(ruta.relative_to(raiz))
        except ValueError:
            return str(ruta)
