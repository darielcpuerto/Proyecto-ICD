"""Sitio Infinity Energy Cuba (OLP-005): empresa solar (SPA de Vite).

Todas las rutas devuelven la *misma* cáscara HTML: el catálogo se construye en el
cliente a partir de un bundle JavaScript. Sin navegador, el núcleo descarga la
cáscara, obtiene el bundle declarado como activo y este adaptador extrae de él
los arreglos de productos y accesorios.

El bundle es código minificado, no JSON. Se localizan los arreglos de objetos
declarados como ``var=[{...}]`` y se interpretan con un lector de literales
JavaScript (subconjunto: objetos, arreglos, cadenas, números, booleanos y null).
Solo se consideran catálogos los arreglos cuyo primer objeto tiene la forma
esperada de producto (``name`` + ``shortDescription`` + ``price``) o de accesorio
(``name`` + ``priceDisplay`` + ``prices``); el resto (calculadora de consumo,
galería de instalaciones, etc.) se ignora.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from ..nucleo import extraccion
from ..nucleo.config import Fuente
from .base import (
    Candidato,
    EvidenciaPagina,
    OpcionesSitio,
    Sitio,
    TipoPagina,
    VeredictoPagina,
)

#: Solo la portada: el SPA sirve la misma cáscara para cualquier ruta y el
#: catálogo completo viaja en el bundle, así que basta una semilla.
SEMILLA = "https://infinitysolarcuba.com/"

#: Bundles declarados en la cáscara.
PATRON_BUNDLE = re.compile(r"""<script[^>]+src=["']([^"']+\.js(?:\?[^"']*)?)["']""")

#: Inicio de un arreglo de objetos asignado a una variable: ``q5=[{id:"``.
PATRON_ARREGLO = re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*\[\{")

#: Tope defensivo por arreglo (el catálogo real tiene decenas de objetos).
MAX_OBJETOS = 500


def _desescapar(bruto: str) -> str:
    """Convierte el cuerpo de una cadena JavaScript en texto."""
    try:
        return json.loads('"' + bruto.replace('"', '\\"') + '"')
    except json.JSONDecodeError:
        return bruto


class _Lector:
    """Lector mínimo de literales JavaScript (subconjunto del lenguaje)."""

    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.i = 0

    def _saltar(self) -> None:
        while self.i < len(self.texto) and self.texto[self.i] in " \t\r\n":
            self.i += 1

    def valor(self) -> Any:
        self._saltar()
        if self.i >= len(self.texto):
            return None
        c = self.texto[self.i]
        if c == "{":
            return self.objeto()
        if c == "[":
            return self.arreglo()
        if c in "\"'`":
            return self.cadena()
        return self.literal()

    def cadena(self) -> str:
        comilla = self.texto[self.i]
        self.i += 1
        trozos: list[str] = []
        while self.i < len(self.texto):
            c = self.texto[self.i]
            if c == "\\":
                trozos.append(self.texto[self.i:self.i + 2])
                self.i += 2
                continue
            if c == comilla:
                self.i += 1
                break
            trozos.append(c)
            self.i += 1
        return _desescapar("".join(trozos))

    def literal(self) -> Any:
        inicio = self.i
        while self.i < len(self.texto) and self.texto[self.i] not in ",}]":
            self.i += 1
        token = self.texto[inicio:self.i].strip()
        if token == "true":
            return True
        if token == "false":
            return False
        if token in ("", "null"):
            return None
        if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
            return float(token) if "." in token else int(token)
        return token

    def clave(self) -> str:
        self._saltar()
        if self.i < len(self.texto) and self.texto[self.i] in "\"'`":
            return self.cadena()
        inicio = self.i
        while self.i < len(self.texto) and (
            self.texto[self.i].isalnum() or self.texto[self.i] in "_$"
        ):
            self.i += 1
        return self.texto[inicio:self.i]

    def objeto(self) -> dict:
        self.i += 1  # '{'
        datos: dict = {}
        while self.i < len(self.texto):
            self._saltar()
            if self.i >= len(self.texto) or self.texto[self.i] == "}":
                self.i += 1
                break
            if self.texto[self.i] == ",":
                self.i += 1
                continue
            nombre = self.clave()
            self._saltar()
            if self.i < len(self.texto) and self.texto[self.i] == ":":
                self.i += 1
            datos[nombre] = self.valor()
        return datos

    def arreglo(self) -> list:
        self.i += 1  # '['
        items: list = []
        while self.i < len(self.texto):
            self._saltar()
            if self.i >= len(self.texto) or self.texto[self.i] == "]":
                self.i += 1
                break
            if self.texto[self.i] == ",":
                self.i += 1
                continue
            items.append(self.valor())
            if len(items) > MAX_OBJETOS:
                break
        return items


def _arreglos(js: str) -> list[tuple[str, list]]:
    """Devuelve ``[(nombre_variable, objetos)]`` de los arreglos del bundle."""
    encontrados: list[tuple[str, list]] = []
    for coincidencia in PATRON_ARREGLO.finditer(js):
        inicio = js.index("[", coincidencia.start())
        objetos = _Lector(js[inicio:]).arreglo()
        if objetos and isinstance(objetos[0], dict):
            encontrados.append((coincidencia.group(1), objetos))
    return encontrados


def _clasificar(objeto: dict) -> str | None:
    """Reconoce la forma de un catálogo a partir de las claves del objeto."""
    claves = set(objeto)
    if {"name", "shortDescription", "price"} <= claves:
        return "producto"
    if {"name", "priceDisplay", "prices"} <= claves:
        return "accesorio"
    return None


def _interpretar_precio(texto: str | None) -> tuple[str | None, str | None, str | None]:
    """Separa un precio anunciado en ``(precio, moneda, disponibilidad)``.

    Si el texto no contiene ninguna cifra se interpreta como estado de
    disponibilidad (p. ej. ``Agotado``). No se convierte ninguna moneda.
    """
    if not texto:
        return None, None, None
    coincidencia = extraccion.PATRON_PRECIO.search(texto)
    if not coincidencia:
        return None, None, texto.strip()
    precio = coincidencia.group("precio") or coincidencia.group("precio2")
    moneda = (coincidencia.group("moneda") or coincidencia.group("moneda2") or "").upper()
    if moneda == "$":
        # El símbolo no identifica la moneda: se busca un código explícito y,
        # si no lo hay, no se inventa ninguna.
        codigo = re.search(r"\b(USD|CUP|MLC|EUR)\b", texto, re.I)
        moneda = codigo.group(1).upper() if codigo else ""
    return precio, moneda or None, None


def _campos_producto(objeto: dict) -> dict:
    precio, moneda, disponibilidad = _interpretar_precio(objeto.get("price"))
    return {
        "name": objeto.get("name"),
        "price": precio,
        "currency": moneda,
        "availability": disponibilidad,
        "description": objeto.get("fullDescription") or objeto.get("shortDescription"),
        "descripcion_corta": objeto.get("shortDescription"),
        "id_catalogo": objeto.get("id"),
        "insignia": objeto.get("badge"),
        "especificaciones": objeto.get("keySpecs"),
        "caracteristicas": objeto.get("mainFeatures"),
        "especificaciones_inversor": objeto.get("inverterSpecs"),
        "detalles_bateria": objeto.get("batteryDetails"),
        "paneles_solares": objeto.get("solarPanels"),
        "compatibilidad": objeto.get("compatibility"),
        "protecciones": objeto.get("protections"),
        "aplicaciones_recomendadas": objeto.get("applicationsRecommended"),
        "beneficios": objeto.get("mainBenefits"),
        "potencia_declarada": objeto.get("powerCapacity"),
        "installation": objeto.get("installation"),
        "ideal_para": objeto.get("idealFor"),
        "dimensiones": objeto.get("dimensions"),
        "certificacion": objeto.get("certification"),
        "warranty": objeto.get("warranty"),
    }


def _campos_accesorio(objeto: dict) -> dict:
    precio, moneda, disponibilidad = _interpretar_precio(objeto.get("priceDisplay"))
    return {
        "name": objeto.get("name"),
        "price": precio,
        "currency": moneda,
        "availability": disponibilidad,
        "description": objeto.get("description"),
        "id_catalogo": objeto.get("id"),
        "precios": objeto.get("prices"),
        "detalles": objeto.get("details"),
        "texto_alternativo": objeto.get("alt"),
    }


def _extraer_de_bundle(js: str, url: str, fecha: str, fuente: Fuente) -> list[dict]:
    """Extrae registros de productos y accesorios del bundle JavaScript."""
    registros: list[dict] = []
    vistos: set[str] = set()
    for variable, objetos in _arreglos(js):
        for indice, objeto in enumerate(objetos):
            tipo = _clasificar(objeto)
            if tipo is None:
                continue
            objetivo = str(objeto.get("id") or objeto.get("name"))
            if objetivo in vistos:
                continue
            vistos.add(objetivo)
            datos = _campos_producto(objeto) if tipo == "producto" else _campos_accesorio(objeto)
            campos, claves = extraccion.campos_desde_dict(datos)
            if not campos:
                continue
            registros.append(extraccion.crear_registro(
                fuente, url, fecha, "bundle_js",
                f"{variable}[{indice}] ({tipo})",
                campos, claves, json.dumps(objeto, ensure_ascii=False),
                advertencias=["valor extraído del bundle JavaScript del SPA (código minificado)"],
            ))
    return registros


class Infinity(Sitio):
    id = "OLP-005"
    nombre = "Infinity Energy Cuba"
    dominio = "infinitysolarcuba.com"
    automatico = True
    objetivo_paginas = None
    unidad_objetivo = "oferta única"
    semillas_explicitas = (SEMILLA,)
    patrones_relevancia = (
        "/producto", "/tienda", "/catalogo", "/solar", "/inversor", "/panel", "/bateria",
    )

    def lotes_candidatos(
        self, fetcher, texto_robots: str | None, opciones: OpcionesSitio
    ) -> list[list[Candidato]]:
        urls = list(opciones.urls_semilla) or list(self.semillas_explicitas)
        return [[
            Candidato(url=u, tipo_esperado=TipoPagina.TECNICA, origen="semilla")
            for u in urls
        ]]

    def tipo_por_url(self, url: str) -> TipoPagina:
        # Todas las rutas devuelven la misma cáscara; las ofertas van en el bundle.
        return TipoPagina.TECNICA

    def clasificar_pagina(
        self,
        url: str,
        tipo_esperado: TipoPagina | None,
        evidencia: EvidenciaPagina,
        lexico,
    ) -> VeredictoPagina:
        return VeredictoPagina(
            tipo=tipo_esperado or TipoPagina.TECNICA,
            relevante=True,
            motivos=["cáscara técnica: el catálogo se extrae del bundle declarado"],
        )

    def tipo_pagina_registro(self, tipo: TipoPagina) -> str:
        return TipoPagina.DATOS.value

    def filtrar_registros(self, registros: list[dict], lexico):
        """Acepta todo el catálogo del bundle y conserva producto/accesorio."""
        aceptados: list[dict] = []
        descartes: list[dict] = []
        for registro in registros:
            campos = registro.get("campos") or {}
            nombre = str(campos.get("product_name") or "").strip()
            if not nombre:
                descartes.append({
                    "registro": registro,
                    "motivo": "registro sin product_name",
                    "puntuacion": 0,
                    "terminos": [],
                })
                continue
            registro["relevancia"] = {
                "relevante": True,
                "puntuacion": 0,
                "terminos": [],
                "campos": [],
                "motivo": "catálogo completo del bundle",
            }
            aceptados.append(registro)
        return aceptados, descartes

    def id_oferta(self, registro: dict) -> str | None:
        adicionales = registro.get("campos_adicionales") or {}
        identificador = adicionales.get("id_catalogo")
        return str(identificador) if identificador else super().id_oferta(registro)

    def tipo_oferta(self, registro: dict) -> str:
        ubicacion = str(registro.get("ubicacion_evidencia") or "")
        if "(producto)" in ubicacion:
            return "producto"
        if "(accesorio)" in ubicacion:
            return "accesorio"
        return "oferta"

    def activos(self, html: str, url: str) -> list[str]:
        return [m.group(1) for m in PATRON_BUNDLE.finditer(html)]

    def extraer(
        self,
        html: str,
        texto: str,
        url: str,
        fecha: str,
        fuente: Fuente,
        activos: dict[str, str] | None = None,
    ) -> list[dict]:
        registros: list[dict] = []
        for activo_url, contenido in (activos or {}).items():
            if not urlparse(activo_url).path.endswith(".js"):
                continue
            registros.extend(_extraer_de_bundle(contenido, url, fecha, fuente))
        return registros


SITIO = Infinity()
