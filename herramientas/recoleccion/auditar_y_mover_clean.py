#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Herramienta: auditar_y_mover_clean.py

Audita los JSON individuales generados en modelos_json_individuales/ y, si son
correctos (estructura válida, tipos correctos, valores en rango), los mueve a
archivos/clean/.

Validaciones:
  - Estructura: pagina.url, pagina.fuente_nombre, tipo_oferta, oferta.*
  - tipo_oferta debe ser uno de los 6 modelos conocidos
  - Cada campo de oferta debe tener 'tipo' y 'valor'
  - decimal/entero deben ser numéricos (o null)
  - booleano debe ser bool (o null)
  - texto debe ser string (o null)
  - valores_permitidos: si el valor no es null y hay lista, debe estar en ella
  - tipo_oferta específico: panel_type, inverter_type, etc. en sus listas
  - Lista<objeto> (componentes) debe ser list o null

Uso:
    python3 auditar_y_mover_clean.py [directorio_origen] [directorio_destino_clean]

Por defecto:
    Origen : archivos/recoleccion/OLP-002_bembete/modelos_json_individuales/
    Destino: archivos/clean/modelos_json/
"""
import json
import os
import re
import shutil
import sys

PROYECTO_ROOT = "/data/data/com.termux/files/home/proyecto"
DEFAULT_ORIGEN = os.path.join(
    PROYECTO_ROOT,
    "archivos/recoleccion/OLP-002_bembete/modelos_json_individuales",
)
DEFAULT_DESTINO = os.path.join(
    PROYECTO_ROOT, "archivos/clean/modelos_json"
)

TIPOS_VALIDOS = {
    "panel_solar", "inversor_solar", "bateria_solar",
    "controlador_carga", "kit_solar", "accesorio_solar",
}

# Campos que deben tener valores_permitidos (enumerados)
CAMPOS_ENUM = {
    "currency", "panel_type", "inverter_type", "output_voltage",
    "battery_technology", "controller_type", "accessory_type",
}

# Campos booleanos
CAMPOS_BOOL = {"mppt"}

# Campos numéricos (decimal o entero)
CAMPOS_NUMERIC = {
    "price", "power_w", "capacity_kwh", "capacity_ah", "voltage_v",
    "current_a", "cycles",
}

# Campos de texto libre
CAMPOS_TEXTO = {
    "oferta_id", "product_name", "brand", "model", "price_texto",
    "location", "installation", "publication_date", "compatibility",
    "specification",
}

# Lista de objetos
CAMPOS_LISTA = {"componentes"}

# URL y fuente_nombre en pagina
PAGINA_CAMPOS = {"url", "fuente_nombre"}


def auditar_json(ruta_archivo):
    """
    Devuelve (es_valido: bool, errores: list[str])
    """
    errores = []

    try:
        with open(ruta_archivo, encoding="utf-8") as f:
            datos = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return False, [f"Error leyendo JSON: {e}"]

    # 1. Estructura base
    if not isinstance(datos, dict):
        return False, ["Raíz no es un objeto"]
    if "pagina" not in datos or not isinstance(datos["pagina"], dict):
        return False, ["Falta 'pagina' o no es objeto"]
    if "tipo_oferta" not in datos:
        return False, ["Falta 'tipo_oferta'"]
    if "oferta" not in datos or not isinstance(datos["oferta"], dict):
        return False, ["Falta 'oferta' o no es objeto"]

    tipo_oferta = datos["tipo_oferta"]
    if tipo_oferta not in TIPOS_VALIDOS:
        return False, [f"tipo_oferta inválido: {tipo_oferta}"]

    # 2. Validar pagina
    pagina = datos["pagina"]
    for campo in PAGINA_CAMPOS:
        if campo not in pagina or not isinstance(pagina[campo], dict):
            errores.append(f"pagina.{campo} faltante o no es objeto")
            continue
        if "tipo" not in pagina[campo] or "valor" not in pagina[campo]:
            errores.append(f"pagina.{campo} sin 'tipo' o 'valor'")

    # 3. Validar oferta
    oferta = datos["oferta"]
    for campo_nombre, campo_def in oferta.items():
        if not isinstance(campo_def, dict):
            errores.append(f"oferta.{campo_nombre} no es objeto")
            continue
        if "tipo" not in campo_def:
            errores.append(f"oferta.{campo_nombre} sin 'tipo'")
        if "valor" not in campo_def:
            errores.append(f"oferta.{campo_nombre} sin 'valor'")
        valor = campo_def.get("valor")
        campo_tipo = campo_def.get("tipo", "")

        # Validar según tipo
        if campo_tipo.startswith("texto"):
            if valor is not None and not isinstance(valor, str):
                errores.append(f"oferta.{campo_nombre}: texto esperado, se recibió {type(valor).__name__}")
            if campo_nombre in CAMPOS_ENUM and valor is not None:
                # Cargar valores permitidos del modelo de referencia
                pass  # se valida abajo con el modelo

        elif campo_tipo == "booleano":
            if valor is not None and not isinstance(valor, bool):
                errores.append(f"oferta.{campo_nombre}: booleano esperado, se recibió {type(valor).__name__}")

        elif campo_tipo == "entero":
            if valor is not None:
                if isinstance(valor, bool) or not isinstance(valor, int):
                    errores.append(f"oferta.{campo_nombre}: entero esperado, se recibió {type(valor).__name__}")

        elif campo_tipo == "decimal":
            if valor is not None:
                if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                    errores.append(f"oferta.{campo_nombre}: decimal esperado, se recibió {type(valor).__name__}")

        elif campo_tipo.startswith("lista"):
            if valor is not None and not isinstance(valor, list):
                errores.append(f"oferta.{campo_nombre}: lista esperada, se recibió {type(valor).__name__}")

    # 4. Validar valores_permitidos contra modelos de referencia
    modelos_dir = os.path.join(PROYECTO_ROOT, "referencias/modelos")
    ruta_modelo = os.path.join(modelos_dir, f"{tipo_oferta}.json")
    if os.path.exists(ruta_modelo):
        with open(ruta_modelo, encoding="utf-8") as f:
            modelo_ref = json.load(f)
        oferta_ref = modelo_ref.get("oferta", {})
        for campo_nombre, campo_def in oferta.items():
            if campo_nombre in oferta_ref:
                ref_def = oferta_ref[campo_nombre]
                valores_permitidos = ref_def.get("valores_permitidos")
                valor = campo_def.get("valor")
                if valores_permitidos and valor is not None:
                    if valor not in valores_permitidos:
                        errores.append(
                            f"oferta.{campo_nombre}: {valor!r} no en valores_permitidos {valores_permitidos}"
                        )

    # 5. Validar lista de objetos (componentes)
    if "componentes" in oferta:
        comps = oferta["componentes"].get("valor")
        if comps is not None:
            if not isinstance(comps, list):
                errores.append("oferta.componentes: no es lista")
            else:
                for i, item in enumerate(comps):
                    if not isinstance(item, dict):
                        errores.append(f"oferta.componentes[{i}]: no es objeto")
                        continue
                    for sub in ("tipo_componente", "product_name", "brand", "quantity", "power_w", "capacity_kwh"):
                        if sub not in item:
                            errores.append(f"oferta.componentes[{i}]: falta '{sub}'")

    return (len(errores) == 0), errores


def main():
    origen = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ORIGEN
    destino = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DESTINO

    if not os.path.exists(origen):
        print(f"[ERROR] Origen no encontrado: {origen}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(destino, exist_ok=True)

    archivos = [f for f in os.listdir(origen) if f.endswith(".json")]
    archivos.sort()

    validos = 0
    invalidos = 0
    detalles_invalidos = []

    for nombre in archivos:
        ruta_origen = os.path.join(origen, nombre)
        es_valido, errores = auditar_json(ruta_origen)
        if es_valido:
            shutil.move(ruta_origen, os.path.join(destino, nombre))
            validos += 1
        else:
            invalidos += 1
            detalles_invalidos.append((nombre, errores))

    print("=" * 70)
    print("AUDITORIA Y MOVIMIENTO A CLEAN")
    print("=" * 70)
    print(f"Origen : {origen}")
    print(f"Destino: {destino}")
    print("-" * 70)
    print(f"Total archivos : {len(archivos)}")
    print(f"Válidos (movidos a clean): {validos}")
    print(f"Inválidos      : {invalidos}")
    print("-" * 70)

    if detalles_invalidos:
        print("\nArchivos inválidos (no movidos):")
        for nombre, errs in detalles_invalidos[:20]:
            print(f"  {nombre}:")
            for e in errs:
                print(f"    - {e}")
        if len(detalles_invalidos) > 20:
            print(f"  ... y {len(detalles_invalidos) - 20} más")

    print(f"\nDirectorio clean: {destino}")
    print("Operación completada.")


if __name__ == "__main__":
    main()
