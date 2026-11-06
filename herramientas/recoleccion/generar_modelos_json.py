#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Herramienta: generar_modelos_json.py

Lee las ofertas válidas del JSONL del piloto robusto v3 y, para cada una,
genera un archivo JSON individual rellenando el modelo de referencia
correspondiente (panel_solar, inversor_solar, bateria_solar, etc.).

Cada archivo de salida valida que:
  - Los campos tengan el tipo correcto (texto, decimal, entero, booleano)
  - Los valores enumerados estén en valores_permitidos (o sean null/"desconocido")
  - Los campos numéricos sean realmente números

Uso:
    python3 generar_modelos_json.py [entrada.jsonl] [directorio_salida]

Si no se pasan argumentos, usa por defecto:
    Entrada : archivos/recoleccion/OLP-002_bembete/modelos_llenados_robusto_v3/ofertas_modelos_robusto_v3.jsonl
    Salida  : archivos/recoleccion/OLP-002_bembete/modelos_json_individuales/
"""
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime

# ---------------------------------------------------------------------------
# Rutas por defecto (relativas a la raíz del proyecto)
# ---------------------------------------------------------------------------
PROYECTO_ROOT = "/data/data/com.termux/files/home/proyecto"
DEFAULT_ENTRADA = os.path.join(
    PROYECTO_ROOT,
    "archivos/recoleccion/OLP-002_bembete/modelos_llenados_robusto_v3/ofertas_modelos_robusto_v3.jsonl",
)
DEFAULT_SALIDA = os.path.join(
    PROYECTO_ROOT,
    "archivos/recoleccion/OLP-002_bembete/modelos_json_individuales",
)
MODELOS_DIR = os.path.join(PROYECTO_ROOT, "referencias/modelos")

TIPOS_VALIDOS = {
    "panel_solar",
    "inversor_solar",
    "bateria_solar",
    "controlador_carga",
    "kit_solar",
    "accesorio_solar",
}


# ---------------------------------------------------------------------------
# Carga de modelos de referencia
# ---------------------------------------------------------------------------
def cargar_modelos(modelos_dir):
    """Devuelve {tipo: modelo_json}."""
    modelos = {}
    for tipo in TIPOS_VALIDOS:
        ruta = os.path.join(modelos_dir, f"{tipo}.json")
        if not os.path.exists(ruta):
            print(f"[ADVERTENCIA] Modelo no encontrado: {ruta}", file=sys.stderr)
            continue
        with open(ruta, encoding="utf-8") as f:
            modelos[tipo] = json.load(f)
    return modelos


# ---------------------------------------------------------------------------
# Validación de tipos y valores
# ---------------------------------------------------------------------------
def validar_valor(campo_def, valor):
    """
    Valida y, cuando es posible, normaliza un valor según la definición del campo.
    Devuelve (valor_normalizado, lista_de_errores).
    """
    tipo = campo_def.get("tipo", "texto")
    valores_permitidos = campo_def.get("valores_permitidos")
    errores = []

    # Valor nulo siempre válido
    if valor is None:
        return None, []

    # Booleano
    if tipo == "booleano":
        if isinstance(valor, bool):
            return valor, []
        if isinstance(valor, str) and valor.lower() in ("true", "1", "sí", "si"):
            return True, []
        if isinstance(valor, str) and valor.lower() in ("false", "0", "no"):
            return False, []
        try:
            return bool(int(valor)), []
        except (ValueError, TypeError):
            errores.append(f"Campo booleano recibió valor no booleano: {valor!r}")
            return None, errores

    # Entero
    if tipo == "entero":
        if isinstance(valor, bool):
            errores.append(f"Campo entero recibió booleano: {valor!r}")
            return None, errores
        if isinstance(valor, int):
            v = valor
        elif isinstance(valor, float) and valor.is_integer():
            v = int(valor)
        elif isinstance(valor, str):
            try:
                v = int(valor)
            except ValueError:
                try:
                    v = int(float(valor))
                except ValueError:
                    errores.append(f"Campo entero no convertible: {valor!r}")
                    return None, errores
        else:
            errores.append(f"Campo entero tipo inesperado: {type(valor).__name__}")
            return None, errores
        if valores_permitidos and v not in valores_permitidos:
            errores.append(f"Entero {v} no en valores_permitidos")
        return v, errores

    # Decimal
    if tipo == "decimal":
        if isinstance(valor, bool):
            errores.append(f"Campo decimal recibió booleano: {valor!r}")
            return None, errores
        if isinstance(valor, (int, float)):
            v = float(valor)
        elif isinstance(valor, str):
            try:
                v = float(valor.replace(",", "."))
            except ValueError:
                errores.append(f"Campo decimal no convertible: {valor!r}")
                return None, errores
        else:
            errores.append(f"Campo decimal tipo inesperado: {type(valor).__name__}")
            return None, errores
        if valores_permitidos and v not in valores_permitidos:
            errores.append(f"Decimal {v} no en valores_permitidos")
        return v, errores

    # Texto (incluye texto (URL), texto (ISO 8601))
    if tipo.startswith("texto"):
        if not isinstance(valor, str):
            errores.append(f"Campo texto esperaba string, recibió {type(valor).__name__}")
            return None, errores
        if valores_permitidos and valor not in valores_permitidos:
            # Permitir "desconocido" aunque no esté listado (es el valor por defecto del modelo)
            if valor != "desconocido":
                errores.append(f"Texto {valor!r} no en valores_permitidos")
        return valor, errores

    # Lista de objetos
    if tipo.startswith("lista"):
        if valor is None:
            return None, []
        if not isinstance(valor, list):
            errores.append(f"Campo lista esperaba list, recibió {type(valor).__name__}")
            return None, errores
        return valor, errores

    # Por defecto, devolver tal cual
    return valor, errores


# ---------------------------------------------------------------------------
# Construcción del JSON de oferta individual
# ---------------------------------------------------------------------------
def _valor_oferta(registro, campo):
    """Lee el valor de un campo del modelo v3, ya sea como campo plano o anidado."""
    # Campos planos del registro v3
    campos_planos = {
        "oferta_id": None,
        "product_name": None,
        "brand": "marca",
        "model": "model",
        "price": "precio",
        "price_texto": None,
        "currency": "moneda",
        "location": "ubicacion",
        "installation": None,
        "publication_date": None,
    }
    clave_plana = campos_planos.get(campo)
    if clave_plana is not None:
        return registro.get(clave_plana)
    # Anidado en registro["modelo"]["oferta"][campo]["valor"]
    try:
        return registro["modelo"]["oferta"][campo]["valor"]
    except (KeyError, TypeError):
        return None


def construir_oferta_json(registro, modelos):
    """
    Toma un registro del JSONL v3 y devuelve el JSON de oferta listo para guardar.
    """
    tipo_oferta = registro.get("tipo_oferta")
    if tipo_oferta not in modelos:
        return None, [f"Tipo de oferta desconocido: {tipo_oferta}"]

    modelo = deepcopy(modelos[tipo_oferta])
    modelo["tipo_oferta"] = tipo_oferta

    errores = []
    oferta = modelo["oferta"]

    # pagina
    modelo["pagina"]["url"]["valor"] = registro.get("url")
    modelo["pagina"]["fuente_nombre"]["valor"] = "Bembete (bembete.com)"

    # installation (no hay en origen)
    oferta["installation"]["valor"] = None

    # Rellenar todos los campos de oferta con validación
    for campo_nombre, campo_def in oferta.items():
        valor = _valor_oferta(registro, campo_nombre)
        v_norm, errs = validar_valor(campo_def, valor)
        if errs:
            errores.extend([f"{campo_nombre}: {e}" for e in errs])
        oferta[campo_nombre]["valor"] = v_norm

    return modelo, errores


# ---------------------------------------------------------------------------
# Procesamiento principal
# ---------------------------------------------------------------------------
def procesar(entrada, salida, modelos):
    os.makedirs(salida, exist_ok=True)

    registros = []
    with open(entrada, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                registros.append(json.loads(linea))

    generados = 0
    errores_registro = []

    for reg in registros:
        tipo_oferta = reg.get("tipo_oferta")
        hash_contenido = reg.get("hash_contenido", "desconocido")

        # Nombre de archivo seguro: tipo + hash corto
        hash_corto = hash_contenido[:12] if hash_contenido else "sin_hash"
        nombre_archivo = f"{tipo_oferta}_{hash_corto}.json"
        ruta_salida = os.path.join(salida, nombre_archivo)

        modelo, errores = construir_oferta_json(reg, modelos)
        if modelo is None:
            errores_registro.append({"hash": hash_contenido, "error": errores})
            continue

        # Validación final de estructura: tipo_oferta presente
        if not modelo.get("tipo_oferta"):
            errores_registro.append({"hash": hash_contenido, "error": ["tipo_oferta ausente"]})
            continue

        with open(ruta_salida, "w", encoding="utf-8") as f:
            json.dump(modelo, f, ensure_ascii=False, indent=2)

        generados += 1

    return generados, len(registros), errores_registro


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    entrada = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ENTRADA
    salida = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SALIDA

    if not os.path.exists(entrada):
        print(f"[ERROR] Archivo de entrada no encontrado: {entrada}", file=sys.stderr)
        sys.exit(1)

    modelos = cargar_modelos(MODELOS_DIR)
    if not modelos:
        print("[ERROR] No se pudieron cargar los modelos de referencia.", file=sys.stderr)
        sys.exit(1)

    print(f"Entrada : {entrada}")
    print(f"Salida  : {salida}")
    print(f"Modelos cargados: {', '.join(sorted(modelos.keys()))}")
    print("-" * 60)

    generados, total, errores = procesar(entrada, salida, modelos)

    print(f"Registros leídos : {total}")
    print(f"JSON generados   : {generados}")
    print(f"Con errores      : {len(errores)}")
    if errores:
        print("\nRegistros con errores:")
        for e in errores[:10]:
            print("  -", e["hash"], ":", "; ".join(e["error"]))
        if len(errores) > 10:
            print(f"     ... y {len(errores) - 10} más")

    print(f"\nDirectorio de salida: {salida}")
    print("Herramienta completada.")


if __name__ == "__main__":
    main()
