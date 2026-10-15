"""Extracción estructurada y trazable a partir de HTML.

Produce registros normalizados a los campos objetivo del proyecto sin inventar
valores. Cada registro conserva:

- la fuente y la URL de origen;
- la fecha de consulta;
- el método de extracción (``json_ld``, ``datos_incrustados`` o
  ``heuristica_texto``);
- la ubicación exacta de la evidencia dentro del documento;
- el valor tal como aparece (``valor_crudo``) y la clave original;
- qué campos objetivo NO aparecieron (``campos_ausentes``).

Nunca convierte moneda ni completa campos faltantes.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import Fuente

# Clave normalizada del origen -> campo objetivo del proyecto.
MAPA_CAMPOS: dict[str, str] = {
    "descripcion": "product_name",
    "descripcion_detallada": "description",
    "producto": "product_name",
    "nombre": "product_name",
    "name": "product_name",
    "title": "product_name",
    "titulo": "product_name",
    "marca": "brand",
    "brand": "brand",
    "modelo": "model",
    "model": "model",
    "sku": "model",
    "potencia": "power_w",
    "potenciainversor": "power_w",
    "potencia_w": "power_w",
    "power": "power_w",
    "capacidad": "capacity_kwh",
    "capacidad_kwh": "capacity_kwh",
    "capacity": "capacity_kwh",
    "voltaje": "voltage_v",
    "voltage_v": "voltage_v",
    "cantidad": "quantity",
    "quantity": "quantity",
    "precio": "price",
    "price": "price",
    "moneda": "currency",
    "currency": "currency",
    "pricecurrency": "currency",
    "ubicacion": "location",
    "location": "location",
    "vendedor": "seller",
    "seller": "seller",
    "disponibilidad": "availability",
    "availability": "availability",
    "garantia": "warranty",
    "warranty": "warranty",
    "imagen": "images",
    "image": "images",
    "images": "images",
}

# Claves (normalizadas) que sugieren que un objeto JSON es una oferta/producto.
CLAVES_PRODUCTO = {
    "precio", "precio_cliente", "price", "descripcion", "descripcion_detallada",
    "nombre", "name", "titulo", "title", "marca", "brand", "moneda", "currency",
    "potencia", "potenciainversor", "capacidad", "imagen", "producto",
}

CLAVES_NOMBRE = {"descripcion", "descripcion_detallada", "nombre", "name", "producto", "title", "titulo"}
CLAVES_PRECIO = {"precio", "precio_cliente", "price"}

# Detección de precios en texto: "Desde 3.140 USD", "1.234,56 CUP", "$500".
PATRON_PRECIO = re.compile(
    r"(?P<precio>\d[\d.,]*)\s*(?P<moneda>USD|CUP|MLC|EUR)\b|"
    r"(?P<moneda2>USD|CUP|MLC|EUR|\$|€)\s*(?P<precio2>\d[\d.,]*)",
    re.I,
)


def _normalizar_clave(clave: str) -> str:
    return re.sub(r"[\s\-]+", "_", clave.strip().lower())


def _canonico(clave: str) -> str:
    return MAPA_CAMPOS.get(_normalizar_clave(clave), _normalizar_clave(clave))


def _recorte(texto: str, maximo: int = 300) -> str:
    texto = re.sub(r"\s+", " ", texto or "")
    return texto if len(texto) <= maximo else texto[:maximo] + "…"


def _registro(
    fuente: Fuente,
    url: str,
    fecha: str,
    metodo: str,
    ubicacion: str,
    campos: dict[str, Any],
    claves_origen: dict[str, str],
    evidencia: str,
    advertencias: list[str] | None = None,
) -> dict:
    objetivo = set(fuente.datos_esperados)
    campos_objetivo = {k: v for k, v in campos.items() if k in objetivo}
    campos_adicionales = {k: v for k, v in campos.items() if k not in objetivo}
    presentes = sorted(campos_objetivo)
    return {
        "fuente_id": fuente.id,
        "fuente_nombre": fuente.nombre,
        "url_origen": url,
        "fecha_consulta": fecha,
        "metodo_extraccion": metodo,
        "ubicacion_evidencia": ubicacion,
        "campos": campos_objetivo,
        "campos_adicionales": campos_adicionales,
        "claves_origen": claves_origen,
        "campos_presentes": presentes,
        "campos_ausentes": sorted(objetivo - set(presentes)),
        "moneda": campos_objetivo.get("currency"),
        "tipo_precio": "anunciado" if "price" in campos_objetivo else None,
        "evidencia_cruda": _recorte(evidencia),
        "advertencias": advertencias or [],
    }


def _campos_desde_dict(d: dict) -> tuple[dict, dict]:
    campos: dict[str, Any] = {}
    claves: dict[str, str] = {}
    for clave, valor in d.items():
        if valor is None or valor == "" or valor == []:
            continue
        if isinstance(valor, dict) and "name" in valor:
            # p. ej. brand: {"@type": "Brand", "name": "SUNCAR"} -> "SUNCAR"
            valor = valor["name"]
        canon = _canonico(str(clave))
        campos[canon] = valor
        claves[canon] = str(clave)
    return campos, claves


# -- 1. JSON-LD (schema.org) ---------------------------------------------
def extraer_json_ld(html: str, url: str, fecha: str, fuente: Fuente) -> list[dict]:
    registros: list[dict] = []
    bloques = re.findall(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I
    )
    for i, bloque in enumerate(bloques):
        try:
            datos = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        nodos = datos.get("@graph", datos) if isinstance(datos, dict) else datos
        if not isinstance(nodos, list):
            nodos = [nodos]
        for j, nodo in enumerate(nodos):
            if not isinstance(nodo, dict):
                continue
            tipo = nodo.get("@type")
            if tipo in ("Product", "Offer", "Service", "AggregateOffer"):
                datos_producto = nodo.get("itemOffered", nodo)
                if isinstance(datos_producto, dict):
                    combinado = {**nodo, **datos_producto}
                else:
                    combinado = nodo
                if isinstance(combinado.get("offers"), dict):
                    # schema.org anida precio/moneda/disponibilidad en `offers`.
                    combinado = {**combinado, **combinado["offers"]}
                campos, claves = _campos_desde_dict(combinado)
                if campos:
                    registros.append(_registro(
                        fuente, url, fecha, "json_ld",
                        f'script[application/ld+json][{i}] nodo[{j}] @type={tipo}',
                        campos, claves, json.dumps(nodo, ensure_ascii=False),
                    ))
    return registros


# -- 2. Datos incrustados (Next.js RSC / __NEXT_DATA__) ------------------
def _es_producto(d: dict) -> bool:
    claves = {_normalizar_clave(k) for k in d}
    return (
        len(claves & CLAVES_PRODUCTO) >= 2
        and (claves & CLAVES_NOMBRE or claves & CLAVES_PRECIO)
    )


def _recolectar_listas(obj: Any, ruta: str, salida: list[tuple[str, list]]) -> None:
    if isinstance(obj, dict):
        for clave, valor in obj.items():
            _recolectar_listas(valor, f"{ruta}.{clave}" if ruta else str(clave), salida)
    elif isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if dicts:
            ofertas: list[dict] = []
            for d in dicts:
                if _es_producto(d):
                    ofertas.append(d)
                else:
                    # Patrón GraphQL/Next: {"node": {...producto...}}
                    for valor in d.values():
                        if isinstance(valor, dict) and _es_producto(valor):
                            ofertas.append(valor)
            if ofertas:
                salida.append((ruta, ofertas))
        for i, item in enumerate(obj):
            _recolectar_listas(item, f"{ruta}[{i}]", salida)


def _textos_script_incrustados(html: str) -> list[tuple[str, str]]:
    """Devuelve (ubicación, contenido) de payloads JSON incrustados."""
    resultado: list[tuple[str, str]] = []

    # Next.js App Router: self.__next_f.push([1,"..."])
    frags = re.findall(
        r'self\.__next_f\.push\(\s*\[\s*1\s*,\s*("(?:[^"\\]|\\.)*")\s*\]\)', html, re.S
    )
    if frags:
        try:
            resultado.append(("self.__next_f (RSC)", "".join(json.loads(f) for f in frags)))
        except json.JSONDecodeError:
            pass

    # Pages Router: <script id="__NEXT_DATA__" type="application/json">...</script>
    m = re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S
    )
    if m:
        resultado.append(("__NEXT_DATA__", m.group(1)))
    return resultado


def _fin_balanceado(texto: str, inicio: int) -> int | None:
    """Devuelve el índice del cierre que balancea el `{`/`[` en `inicio`."""
    pares = {"}": "{", "]": "["}
    pila: list[str] = []
    en_cadena = False
    escape = False
    for i in range(inicio, len(texto)):
        c = texto[i]
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c in "{[":
            pila.append(c)
        elif c in "}]":
            if not pila or pila[-1] != pares[c]:
                return None
            pila.pop()
            if not pila:
                return i
    return None


def _iterar_literales(texto: str, maximo: int = 500):
    """Genera los literales JSON ({...} o [...]) hallados en un texto."""
    i, n, hallados = 0, len(texto), 0
    while i < n and hallados < maximo:
        if texto[i] in "{[":
            fin = _fin_balanceado(texto, i)
            if fin is not None:
                hallados += 1
                yield texto[i:fin + 1]
                i = fin + 1
                continue
        i += 1


def extraer_incrustados(
    html: str, url: str, fecha: str, fuente: Fuente, metodo: str = "datos_incrustados"
) -> list[dict]:
    registros: list[dict] = []
    for ubicacion, payload in _textos_script_incrustados(html):
        estructuras: list[tuple[str, object]] = []
        try:
            estructuras.append((ubicacion, json.loads(payload)))
        except json.JSONDecodeError:
            # Next.js App Router entrega un *flight stream* (no es JSON completo):
            # se buscan literales JSON dentro del payload.
            for k, literal in enumerate(_iterar_literales(payload)):
                try:
                    estructuras.append((f"{ubicacion}#{k}", json.loads(literal)))
                except json.JSONDecodeError:
                    continue

        for ruta_base, datos in estructuras:
            listas: list[tuple[str, list]] = []
            _recolectar_listas(datos, "", listas)
            for ruta, ofertas in listas:
                for k, oferta in enumerate(ofertas):
                    campos, claves = _campos_desde_dict(oferta)
                    if not campos:
                        continue
                    registros.append(_registro(
                        fuente, url, fecha, metodo,
                        f"{ruta_base}:{ruta}[{k}]",
                        campos, claves, json.dumps(oferta, ensure_ascii=False),
                        advertencias=["valor tomado de datos incrustados en la página"],
                    ))
    return registros


# -- 3. Heurística de texto ----------------------------------------------
def extraer_precios_texto(texto: str, url: str, fecha: str, fuente: Fuente) -> list[dict]:
    registros: list[dict] = []
    for m in PATRON_PRECIO.finditer(texto):
        precio = m.group("precio") or m.group("precio2")
        moneda = (m.group("moneda") or m.group("moneda2") or "").upper()
        contexto = texto[max(0, m.start() - 120):m.end() + 60]
        campos = {"price": precio}
        claves = {"price": m.group(0).strip()}
        if moneda and moneda != "$":
            campos["currency"] = moneda
            claves["currency"] = "detectado en texto"
        registros.append(_registro(
            fuente, url, fecha, "heuristica_texto",
            f"texto@{m.start()}", campos, claves, contexto,
            advertencias=["precio detectado por patrón de texto; verificar en el original"],
        ))
    return registros


# -- API principal -------------------------------------------------------
def extraer(html: str, texto: str, url: str, fecha: str, fuente: Fuente) -> list[dict]:
    """Ejecuta las tres estrategias y devuelve todos los registros hallados."""
    return (
        extraer_json_ld(html, url, fecha, fuente)
        + extraer_incrustados(html, url, fecha, fuente)
        + extraer_precios_texto(texto, url, fecha, fuente)
    )


# Utilidades expuestas para los adaptadores específicos.
crear_registro = _registro
campos_desde_dict = _campos_desde_dict
textos_script_incrustados = _textos_script_incrustados
iterar_literales = _iterar_literales
recolectar_listas = _recolectar_listas
