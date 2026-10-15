"""Extracción conservadora de contenido de una página HTML.

Solo se extrae lo que está explícitamente presente en el documento (título,
metadatos, texto, imágenes y enlaces). No se infieren valores de campos como
precio, potencia o disponibilidad: esos quedan para etapas posteriores y
siempre referidos al texto original conservado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Medios cuya descarga se contempla como imagen de la observación.
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}

# Hosts de motores de búsqueda que nunca deben tratarse como datos de origen.
HOSTS_MOTOR_BUSQUEDA = {
    "google.com", "www.google.com", "bing.com", "www.bing.com",
    "duckduckgo.com", "html.duckduckgo.com", "search.yahoo.com",
}


@dataclass
class Contenido:
    """Resultado de la extracción de una página."""

    titulo: str = ""
    descripcion: str = ""
    texto: str = ""
    imagenes: list[str] = field(default_factory=list)
    enlaces: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


def _texto_limpio(valor: str) -> str:
    return " ".join((valor or "").split())


def extraer(html: str, url_base: str) -> Contenido:
    """Extrae el contenido observable de `html` resolviendo URLs relativas."""
    soup = BeautifulSoup(html, "html.parser")
    contenido = Contenido()

    if soup.title and soup.title.string:
        contenido.titulo = _texto_limpio(soup.title.string)

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        contenido.descripcion = _texto_limpio(meta["content"])

    cuerpo = soup.body or soup
    contenido.texto = "\n".join(
        linea
        for linea in (_texto_limpio(t) for t in cuerpo.stripped_strings)
        if linea
    )

    for img in soup.find_all("img"):
        for atributo in ("src", "data-src", "data-original", "srcset"):
            valor = img.get(atributo)
            if not valor:
                continue
            candidato = valor.split(",")[0].strip().split(" ")[0]
            if candidato.startswith("data:"):
                continue
            absoluta = urljoin(url_base, candidato)
            if absoluta not in contenido.imagenes:
                contenido.imagenes.append(absoluta)

    for ancla in soup.find_all("a", href=True):
        absoluta = urljoin(url_base, ancla["href"])
        partes = urlparse(absoluta)
        if partes.scheme not in ("http", "https"):
            continue
        if partes.netloc.lower() in HOSTS_MOTOR_BUSQUEDA:
            contenido.advertencias.append(
                "enlace a motor de búsqueda omitido: " + absoluta
            )
            continue
        limpia = partes._replace(fragment="").geturl()
        if limpia not in contenido.enlaces:
            contenido.enlaces.append(limpia)

    if not contenido.texto:
        contenido.advertencias.append(
            "texto vacío: la página puede requerir JavaScript para renderizar"
        )

    return contenido


def es_imagen(url: str) -> bool:
    """Indica si la URL apunta a un archivo de imagen por su extensión."""
    ruta = urlparse(url).path.lower()
    return any(ruta.endswith(ext) for ext in EXTENSIONES_IMAGEN)
