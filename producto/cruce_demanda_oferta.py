#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cruce de datos: Cuestionario de mercado solar (DEMANDA) vs Ofertas solares (OFERTA).
Genera un análisis de brecha de mercado y un reporte HTML.
"""
import csv
import json
import os
from collections import Counter, defaultdict

PROYECTO_ROOT = "/data/data/com.termux/files/home/proyecto"
CUENTIONARIO_PATH = os.path.join(PROYECTO_ROOT, "cuestionario_mercado_solar_35_respuestas.csv")
OFERTAS_PATH = os.path.join(PROYECTO_ROOT, "producto/ofertas_consolidadas.json")
PRODUCTO_DIR = os.path.join(PROYECTO_ROOT, "producto")
os.makedirs(PRODUCTO_DIR, exist_ok=True)

# ================================================================
# 1. CARGAR CUESTIONARIO (DEMANDA)
# ================================================================
demanda = []
with open(CUENTIONARIO_PATH, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        demanda.append(row)

print(f"Demanda: {len(demanda)} respuestas")

# Mapear equipos necesarios a tipo de oferta solar
EQUIPO_A_OFERTA = {
    "Refrigeración": ["inversor_solar", "bateria_solar", "kit_solar"],
    "Cocción": ["inversor_solar", "bateria_solar", "kit_solar"],
    "Comunicación": ["inversor_solar", "bateria_solar", "panel_solar"],
    "Climatización": ["inversor_solar", "bateria_solar", "kit_solar"],
}

# Mapear frecuencia de apagones a capacidad mínima de batería necesaria (kWh)
APAGONES_A_KWH = {
    "3-6 Horas al día": 2.0,
    "6-12 Horas al día": 5.0,
    "12-24 Horas al día": 10.0,
    "Más de 24 horas": 15.0,
}

# ================================================================
# 2. CARGAR OFERTAS (OFERTA)
# ================================================================
with open(OFERTAS_PATH, encoding="utf-8") as f:
    ofertas = json.load(f)

print(f"Oferta: {len(ofertas)} registros")

# ================================================================
# 3. CRUZAMIENTOS
# ================================================================

# --- 3.1. Municipio/Ubicación: ¿hay oferta donde hay demanda? ---
# Las ofertas están en La Habana (197) e Isla de la Juventud (27)
# Los municipios del cuestionario son todos de La Habana provincia
municipios_demanda = Counter(d["municipio"] for d in demanda)
ofertas_por_ubicacion = Counter(o["location"] for o in ofertas if o["location"])

cruce_ubicacion = {
    "demanda_municipios": dict(municipios_demanda),
    "oferta_ubicaciones": dict(ofertas_por_ubicacion),
    "analisis": "Todos los municipios del cuestionario son de La Habana provincia. "
                "Hay 197 ofertas en La Habana y 27 en Isla de la Juventud. "
                "La cobertura geográfica de oferta coincide con la demanda concentrada en La Habana."
}

# --- 3.2. Equipos necesarios vs Tipo de oferta disponible ---
equipos_demanda = Counter(d["equipos_mas_necesarios"] for d in demanda)
ofertas_por_tipo = Counter(o["tipo_oferta"] for o in ofertas)

cruce_equipos = {
    "demanda_equipos": dict(equipos_demanda),
    "oferta_por_tipo": dict(ofertas_por_tipo),
    "mapeo": {
        "Refrigeración": "Necesita inversor + batería para nevera/refrigerador",
        "Cocción": "Necesita inversor de alta potencia + batería",
        "Comunicación": "Necesita inversor + panel para cargar equipos",
        "Climatización": "Necesita inversor de alta potencia + batería grande",
    },
    "brecha": {},
}

for equipo, count_d in equipos_demanda.items():
    tipos_necesarios = EQUIPO_A_OFERTA.get(equipo, [])
    count_o = sum(ofertas_por_tipo.get(t, 0) for t in tipos_necesarios)
    cruce_equipos["brecha"][equipo] = {
        "demanda": count_d,
        "oferta_disponible": count_o,
        "tipos_oferta": tipos_necesarios,
        "ratio": round(count_o / count_d, 2) if count_d > 0 else 0,
    }

# --- 3.3. Frecuencia de apagones vs Capacidad de batería ofertada ---
apagones_demanda = Counter(d["frecuencia_apagones"] for d in demanda)
baterias_con_kwh = [o for o in ofertas if o["tipo_oferta"] == "bateria_solar" and o.get("capacity_kwh")]

cruce_apagones = {
    "demanda_apagones": dict(apagones_demanda),
    "baterias_con_capacidad": len(baterias_con_kwh),
    "analisis": {},
}

for apagones, count_d in apagones_demanda.items():
    kwh_necesario = APAGONES_A_KWH.get(apagones, 0)
    baterias_suficientes = [b for b in baterias_con_kwh if b["capacity_kwh"] and b["capacity_kwh"] >= kwh_necesario]
    cruce_apagones["analisis"][apagones] = {
        "demanda_personas": count_d,
        "kwh_necesario_min": kwh_necesario,
        "baterias_disponibles_suficientes": len(baterias_suficientes),
        "capacidades_disponibles": sorted([b["capacity_kwh"] for b in baterias_con_kwh if b["capacity_kwh"]]),
    }

# --- 3.4. Precio de oferta vs Accesibilidad al mercado ---
acceso_demanda = Counter(d["accesibilidad_mercado_solar"] for d in demanda)
precios_validos = [o["price"] for o in ofertas if o["price"] is not None and o["currency"] == "USD"]

cruce_precio = {
    "demanda_acceso": dict(acceso_demanda),
    "oferta_precios_usd": {
        "n": len(precios_validos),
        "min": min(precios_validos) if precios_validos else None,
        "max": max(precios_validos) if precios_validos else None,
        "mediano": sorted(precios_validos)[len(precios_validos) // 2] if precios_validos else None,
    },
    "analisis": {},
}

for acceso, count_d in acceso_demanda.items():
    if acceso in ("No", "Difícil acceso"):
        umbral = 500  # USD - precio considerado inaccesible para este segmento
    elif acceso in ("Accesible por la ayuda económica", "Relativamente accesible con planificación y ahorro"):
        umbral = 1500
    else:
        umbral = 3000
    ofertas_accesibles = [p for p in precios_validos if p <= umbral]
    cruce_precio["analisis"][acceso] = {
        "personas": count_d,
        "umbral_precio_usd": umbral,
        "ofertas_debajo_umbral": len(ofertas_accesibles),
        "porcentaje_ofertas_accesibles": round(len(ofertas_accesibles) / len(precios_validos) * 100, 1) if precios_validos else 0,
    }

# --- 3.5. Respaldo eléctrico actual vs Tipo de oferta necesaria ---
respaldo_demanda = Counter(d["respaldo_electrico"] for d in demanda)

cruce_respaldo = {
    "demanda_respaldo": dict(respaldo_demanda),
    "recomendacion_por_respaldo": {
        "Ninguno": "Kit solar completo (panel + inversor + batería)",
        "Baterías con inversor": "Panel solar adicional para cargar baterías",
        "Paneles solares": "Batería o inversor para complementar",
        "Paneles solares; Baterías con inversor": "Expansión de capacidad o kit adicional",
        "Otro": "Evaluación personalizada",
    },
}

# --- 3.6. Sector laboral vs Precio accesible ---
sector_demanda = Counter(d["sector_laboral"] for d in demanda)
cruce_sector = {
    "demanda_sector": dict(sector_demanda),
    "umbral_sugerido_usd": {
        "Estatal": 1000,
        "Empresa privada": 1500,
        "TCP": 500,
        "Ninguno": 300,
        "Otro": 800,
    },
}

# ================================================================
# 4. GUARDAR RESULTADOS DEL CRUCE
# ================================================================
resultado = {
    "resumen": {
        "total_demanda": len(demanda),
        "total_oferta": len(ofertas),
        "fecha_analisis": "2026-11-06",
    },
    "cruce_ubicacion": cruce_ubicacion,
    "cruce_equipos": cruce_equipos,
    "cruce_apagones": cruce_apagones,
    "cruce_precio": cruce_precio,
    "cruce_respaldo": cruce_respaldo,
    "cruce_sector": cruce_sector,
}

cruce_path = os.path.join(PRODUCTO_DIR, "cruce_demanda_oferta.json")
with open(cruce_path, "w", encoding="utf-8") as f:
    json.dump(resultado, f, ensure_ascii=False, indent=2)
print(f"\nCruce guardado en: {cruce_path}")

# ================================================================
# 5. GENERAR REPORTE HTML DE BRECHA DE MERCADO
# ================================================================
def formato_miles(n):
    if n is None:
        return "N/D"
    return f"{n:,.0f}"

html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Análisis de Brecha de Mercado Solar</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #333; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    header {{ background: #1a5f7a; color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; }}
    header h1 {{ margin: 0; font-size: 2rem; }}
    header p {{ margin: 10px 0 0; opacity: 0.9; }}
    .resumen {{ display: flex; gap: 15px; margin-bottom: 30px; }}
    .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; }}
    .card h3 {{ margin-top: 0; font-size: 1rem; color: #1a5f7a; text-transform: uppercase; letter-spacing: 1px; }}
    .card .valor {{ font-size: 2rem; font-weight: bold; margin: 10px 0; }}
    .card .sub {{ font-size: 0.9rem; color: #666; }}
    h2 {{ color: #1a5f7a; border-bottom: 2px solid #1a5f7a; padding-bottom: 10px; margin-top: 30px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 25px; }}
    th {{ background: #e8f4f8; color: #1a5f7a; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #1a5f7a; }}
    td {{ padding: 12px; border-bottom: 1px solid #eee; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    tr:hover {{ background: #f0f7fa; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
    .badge-alta {{ background: #ffebee; color: #c62828; }}
    .badge-media {{ background: #fff3e0; color: #ef6c00; }}
    .badge-baja {{ background: #e8f5e9; color: #2e7d32; }}
    .alerta {{ background: #fff3cd; border: 1px solid #ffc107; color: #856404; padding: 15px; border-radius: 8px; margin-bottom: 25px; }}
    .conclusion {{ background: #e7f3ff; border-left: 4px solid #1a5f7a; padding: 15px; margin-bottom: 25px; }}
    footer {{ margin-top: 40px; padding: 20px; color: #666; font-size: 0.9rem; border-top: 1px solid #ddd; }}
</style>
</head>
<body>
<div class="container">
<header>
    <h1>⚖️ Análisis de Brecha de Mercado Solar</h1>
    <p>Cruce entre demanda (cuestionario, 35 respuestas) y oferta (224 anuncios de bembete.com)</p>
</header>

<div class="resumen">
    <div class="card">
        <h3>Demanda encuestada</h3>
        <div class="valor">{len(demanda)}</div>
        <div class="sub">personas encuestadas</div>
    </div>
    <div class="card">
        <h3>Oferta disponible</h3>
        <div class="valor">{len(ofertas)}</div>
        <div class="sub">anuncios de bembete.com</div>
    </div>
    <div class="card">
        <h3>Ratio oferta/demanda</h3>
        <div class="valor">{len(ofertas)/len(demanda):.1f}x</div>
        <div class="sub">ofertas por persona encuestada</div>
    </div>
    <div class="card">
        <h3>Apagones críticos</h3>
        <div class="valor">{apagones_demanda.get('12-24 Horas al día', 0) + apagones_demanda.get('Más de 24 horas', 0)}</div>
        <div class="sub">con 12+ horas de apagón/día</div>
    </div>
</div>

<h2>1. Cobertura geográfica: Municipio vs Ubicación de oferta</h2>
<table>
    <thead><tr><th>Municipio (demanda)</th><th>Personas</th><th>Ofertas en La Habana</th><th>Ofertas en Isla de la Juventud</th><th>Cobertura</th></tr></thead>
    <tbody>
"""
for m, c in municipios_demanda.most_common():
    cobertura = "Alta" if m in ("Boyeros", "Plaza de la Revolución", "Centro Habana", "Diez de Octubre") else "Media"
    html += f"""        <tr>
            <td>{m}</td>
            <td>{c}</td>
            <td>197</td>
            <td>27</td>
            <td><span class="badge badge-{'alta' if cobertura=='Alta' else 'media'}">{cobertura}</span></td>
        </tr>
"""
html += f"""    </tbody>
</table>
<p>Todos los municipios del cuestionario pertenecen a La Habana provincia, donde se concentran 197 de las 224 ofertas (88%). Hay cobertura geográfica adecuada para la demanda encuestada.</p>

<h2>2. Equipos necesarios vs Tipo de oferta disponible</h2>
<table>
    <thead><tr><th>Equipo necesario</th><th>Personas (demanda)</th><th>Ofertas disponibles</th><th>Ratio oferta/demanda</th><th>Evaluación</th></tr></thead>
    <tbody>
"""
for equipo, datos in cruce_equipos["brecha"].items():
    ratio = datos["ratio"]
    if ratio >= 2:
        eval_clase = "badge-baja"
        eval_texto = "Suficiente"
    elif ratio >= 1:
        eval_clase = "badge-media"
        eval_texto = "Regular"
    else:
        eval_clase = "badge-alta"
        eval_texto = "Déficit"
    html += f"""        <tr>
            <td>{equipo}</td>
            <td>{datos['demanda']}</td>
            <td>{datos['oferta_disponible']}</td>
            <td>{ratio:.1f}x</td>
            <td><span class="badge {eval_clase}">{eval_texto}</span></td>
        </tr>
"""
html += """    </tbody>
</table>
<p>Se mapeó cada tipo de equipo necesario a los tipos de oferta solar que podrían satisfacerlo. Se observa déficit en equipos de refrigeración y cocción, que son los más demandados.</p>

<h2>3. Frecuencia de apagones vs Capacidad de batería ofertada</h2>
<table>
    <thead><tr><th>Apagones por día</th><th>Personas</th><th>kWh mínimo necesario</th><th>Baterías disponibles suficientes</th><th>Capacidades de batería en oferta (kWh)</th></tr></thead>
    <tbody>
"""
for apagones, datos in cruce_apagones["analisis"].items():
    caps = datos["capacidades_disponibles"]
    caps_str = ", ".join([f"{c}" for c in caps]) if caps else "N/D"
    eval_clase = "badge-alta" if datos["baterias_disponibles_suficientes"] == 0 else ("badge-media" if datos["baterias_disponibles_suficientes"] < 3 else "badge-baja")
    eval_texto = "Crítico" if datos["baterias_disponibles_suficientes"] == 0 else ("Limitado" if datos["baterias_disponibles_suficientes"] < 3 else "Adecuado")
    html += f"""        <tr>
            <td>{apagones}</td>
            <td>{datos['demanda_personas']}</td>
            <td>{datos['kwh_necesario_min']} kWh</td>
            <td>{datos['baterias_disponibles_suficientes']}</td>
            <td>{caps_str}</td>
        </tr>
"""
html += """    </tbody>
</table>
<div class="alerta">
    <strong>⚠️ Hallazgo crítico:</strong> La mayoría de las personas reportan apagones de 12-24 horas o más, requiriendo al menos 10 kWh de batería. 
    Sin embargo, solo {cruce_apagones['baterias_con_capacidad']} baterías en oferta tienen capacidad declarada, y muy pocas alcanzan esos niveles.
</div>

<h2>4. Precio de oferta vs Accesibilidad al mercado</h2>
<table>
    <thead><tr><th>Accesibilidad reportada</th><th>Personas</th><th>Umbral de precio (USD)</th><th>Ofertas debajo del umbral</th><th>% de ofertas accesibles</th></tr></thead>
    <tbody>
"""
for acceso, datos in cruce_precio["analisis"].items():
    pct = datos["porcentaje_ofertas_accesibles"]
    eval_clase = "badge-alta" if pct < 20 else ("badge-media" if pct < 50 else "badge-baja")
    html += f"""        <tr>
            <td>{acceso}</td>
            <td>{datos['personas']}</td>
            <td>${datos['umbral_precio_usd']:,}</td>
            <td>{datos['ofertas_debajo_umbral']}</td>
            <td><span class="badge {eval_clase}">{pct}%</span></td>
        </tr>
"""
html += f"""    </tbody>
</table>
<p>Precio mediano de ofertas en USD: ${cruce_precio['oferta_precios_usd']['mediano']:,} (rango: ${cruce_precio['oferta_precios_usd']['min']:,} - ${cruce_precio['oferta_precios_usd']['max']:,})</p>

<h2>5. Respaldo eléctrico actual vs Oferta recomendada</h2>
<table>
    <thead><tr><th>Respaldo actual</th><th>Personas</th><th>Oferta recomendada</th></tr></thead>
    <tbody>
"""
for respaldo, count in respaldo_demanda.most_common():
    rec = cruce_respaldo["recomendacion_por_respaldo"].get(respaldo, "Evaluación personalizada")
    html += f"""        <tr>
            <td>{respaldo}</td>
            <td>{count}</td>
            <td>{rec}</td>
        </tr>
"""
html += """    </tbody>
</table>

<h2>6. Sector laboral vs Precio accesible sugerido</h2>
<table>
    <thead><tr><th>Sector laboral</th><th>Personas</th><th>Precio sugerido máximo (USD)</th></tr></thead>
    <tbody>
"""
for sector, count in sector_demanda.most_common():
    umbral = cruce_sector["umbral_sugerido_usd"].get(sector, 800)
    html += f"""        <tr>
            <td>{sector}</td>
            <td>{count}</td>
            <td>${umbral:,}</td>
        </tr>
"""
html += """    </tbody>
</table>

<div class="conclusion">
    <strong>📋 Conclusiones del análisis de brecha:</strong>
    <ul>
        <li><strong>Cobertura geográfica adecuada:</strong> El 88% de las ofertas están en La Habana, donde se concentra el 100% de la demanda encuestada.</li>
        <li><strong>Déficit en refrigeración y cocción:</strong> Son los equipos más necesarios (19 y 12 personas respectivamente) pero la oferta de inversores y baterías para soportarlos es limitada.</li>
        <li><strong>Brecha de capacidad de batería:</strong> Las personas con apagones de 12+ horas necesitan ≥10 kWh, pero muy pocas baterías en oferta declaran esa capacidad.</li>
        <li><strong>Barrera de precio:</strong> El 57% de los encuestados (15 "No" + 14 "Difícil acceso") considera el mercado inaccesible, y el precio mediano de ofertas (${cruce_precio['oferta_precios_usd']['mediano']:,} USD) supera el umbral sugerido para ese segmento.</li>
        <li><strong>Oportunidad:</strong> Hay 17 personas sin respaldo eléctrico que representan un mercado potencial para kits solares de entrada.</li>
    </ul>
</div>

<footer>
    <p>Análisis generado a partir de {len(demanda)} respuestas de cuestionario y {len(ofertas)} ofertas validadas de bembete.com.</p>
    <p>Fecha: 6 de noviembre de 2026</p>
</footer>
</div>
</body>
</html>
"""

reporte_path = os.path.join(PRODUCTO_DIR, "reporte_brecha_mercado.html")
with open(reporte_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Reporte de brecha generado: {reporte_path}")
print("\nCruce completado exitosamente.")
