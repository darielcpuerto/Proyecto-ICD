"""Carga y aplicación de modelos de salida desde ``referencias/modelos/``.

Cada modelo define la estructura canónica que deben tener los registros de
salida (``datos.jsonl``). La conversión toma un registro interno (formato de
``extraccion.py``) y un ``tipo_oferta``, y devuelve un diccionario con la
estructura del modelo correspondiente.

Si no existe un modelo para el ``tipo_oferta`` dado, se devuelve el registro
interno sin modificar (compatibilidad hacia atrás).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Mapeo de los tipos de oferta que emiten los sitios (panel, inversor, bateria,
# controlador, kit, sistema, oferta) a los identificadores de modelo
# definidos en referencias/modelos/.
MAPA_TIPO_OFERTA: dict[str, str] = {
    "panel": "panel_solar",
    "paneles": "panel_solar",
    "inversor": "inversor_solar",
    "inversores": "inversor_solar",
    "microinversor": "inversor_solar",
    "bateria": "bateria_solar",
    "baterias": "bateria_solar",
    "controlador": "controlador_carga",
    "controladores": "controlador_carga",
    "kit": "kit_solar",
    "kits": "kit_solar",
    "sistema": "kit_solar",
    "sistemas": "kit_solar",
    "oferta": "accesorio_solar",
    "accesorio": "accesorio_solar",
    "accesorios": "accesorio_solar",
}


class Modelos:
    """Carga los modelos de salida y convierte registros internos a su formato."""

    def __init__(self, ruta: Path | str | None = None) -> None:
        self.ruta = Path(ruta) if ruta else None
        self._modelos: dict[str, dict] = {}
        if self.ruta and self.ruta.is_dir():
            self._cargar()

    def _cargar(self) -> None:
        for archivo in sorted(self.ruta.glob("*.json")):
            try:
                datos = json.loads(archivo.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            tipo = datos.get("tipo_oferta")
            if tipo:
                self._modelos[tipo] = datos

    def tiene_modelo(self, tipo_oferta: str | None = None) -> bool:
        """Devuelve True si existe un modelo para el tipo de oferta."""
        if not tipo_oferta:
            return False
        tipo_modelo = MAPA_TIPO_OFERTA.get(tipo_oferta, tipo_oferta)
        return tipo_modelo in self._modelos

    def tipos_disponibles(self) -> list[str]:
        """Devuelve la lista de tipos de modelo cargados."""
        return sorted(self._modelos.keys())

    def convertir(
        self, registro: dict, tipo_oferta: str | None = None
    ) -> dict:
        """Convierte un registro interno al formato de modelo.

        Si ``tipo_oferta`` es None o no tiene modelo asociado, devuelve el
        registro interno sin modificar.
        """
        if not tipo_oferta:
            return registro
        # Mapear el tipo de oferta del sitio (p. ej. "panel") al identificador
        # de modelo (p. ej. "panel_solar").
        tipo_modelo = MAPA_TIPO_OFERTA.get(tipo_oferta, tipo_oferta)
        if tipo_modelo not in self._modelos:
            return registro

        modelo = self._modelos[tipo_modelo]
        campos = registro.get("campos") or {}
        adicionales = registro.get("campos_adicionales") or {}

        salida: dict = {
            "pagina": {
                "url": {"tipo": "texto (URL)", "valor": registro.get("url_origen")},
                "fuente_nombre": {
                    "tipo": "texto",
                    "valor": registro.get("fuente_nombre"),
                },
            },
            "tipo_oferta": tipo_modelo,
            "oferta": {},
        }

        oferta_modelo = modelo.get("oferta", {})

        # Campos comunes a todos los modelos.
        mapeo_comun = {
            "oferta_id": registro.get("id_oferta") or adicionales.get("id_oferta"),
            "product_name": campos.get("product_name"),
            "brand": campos.get("brand"),
            "model": campos.get("model"),
            "price": _a_decimal(campos.get("price")),
            "price_texto": str(campos.get("price")) if campos.get("price") is not None else None,
            "currency": campos.get("currency"),
            "location": campos.get("location"),
            "installation": campos.get("installation"),
            "publication_date": adicionales.get("updated_on_by_user"),
        }

        # Campos específicos por tipo de oferta.
        mapeo_especifico: dict[str, dict[str, str]] = {
            "panel_solar": {
                "power_w": "power_w",
                "panel_type": None,  # no hay campo directo; se deja None
            },
            "bateria_solar": {
                "capacity_kwh": "capacity_kwh",
                "capacity_ah": None,
                "voltage_v": "voltage_v",
                "battery_technology": None,
                "cycles": None,
            },
            "inversor_solar": {
                "power_w": "power_w",
                "inverter_type": None,
                "output_voltage": None,
                "mppt": None,
            },
            "controlador_carga": {
                "controller_type": None,
                "current_a": None,
                "voltage_v": "voltage_v",
            },
            "kit_solar": {
                "power_w": "power_w",
                "capacity_kwh": "capacity_kwh",
                "output_voltage": None,
                "componentes": None,
            },
            "accesorio_solar": {
                "accessory_type": None,
                "compatibility": None,
                "specification": None,
            },
        }

        for clave_modelo, valor in mapeo_comun.items():
            if clave_modelo in oferta_modelo:
                salida["oferta"][clave_modelo] = {
                    "tipo": oferta_modelo[clave_modelo].get("tipo", "texto"),
                    "valor": valor,
                }

        for clave_modelo, clave_registro in (
            mapeo_especifico.get(tipo_oferta, {}).items()
        ):
            if clave_modelo not in oferta_modelo:
                continue
            if clave_registro is None:
                salida["oferta"][clave_modelo] = {
                    "tipo": oferta_modelo[clave_modelo].get("tipo", "texto"),
                    "valor": None,
                }
            else:
                valor = campos.get(clave_registro) or adicionales.get(clave_registro)
                if clave_modelo == "componentes" and isinstance(valor, list):
                    salida["oferta"][clave_modelo] = {
                        "tipo": oferta_modelo[clave_modelo].get("tipo", "lista<objeto>"),
                        "valor": valor,
                        "campos_item": oferta_modelo[clave_modelo].get("campos_item"),
                    }
                elif clave_modelo == "mppt" and isinstance(valor, str):
                    salida["oferta"][clave_modelo] = {
                        "tipo": "booleano",
                        "valor": valor.lower() in ("true", "1", "si", "sí", "yes"),
                    }
                else:
                    salida["oferta"][clave_modelo] = {
                        "tipo": oferta_modelo[clave_modelo].get("tipo", "texto"),
                        "valor": valor,
                    }

        return salida


def _a_decimal(valor: Any) -> float | int | None:
    """Convierte un valor a número decimal si es posible."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, str):
        texto = valor.strip().replace(",", ".")
        try:
            numero = float(texto)
            return int(numero) if numero.is_integer() else numero
        except ValueError:
            return None
    return None


def cargar_modelos(ruta: Path | str | None = None) -> Modelos:
    """Carga todos los modelos de salida desde la ruta dada."""
    return Modelos(ruta)
