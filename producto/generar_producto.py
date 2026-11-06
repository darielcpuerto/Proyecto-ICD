#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera el producto final:
1. ofertas_consolidadas.json - archivo maestro con todas las 224 ofertas
2. catalogo.html - catálogo web estático con filtros (Opción A)
3. reporte_mercado.html - reporte de mercado con estadísticas del EDA (Opción B)
"""
import json
import os
from collections import Counter, defaultdict

PROYECTO_ROOT = "/data/data/com.termux/files/home/proyecto"
LIMPIO_DIR = os.path.join(PROYECTO_ROOT, "archivos/clean/modelos_json")
PRODUCTO_DIR = os.path.join(PROYECTO_ROOT, "producto")
os.makedirs(PRODUCTO_DIR, exist_ok=True)

# ================================================================
# 1. CARGAR Y CONSOLIDAR TODOS LOS JSON LIMPIOS
# ================================================================
registros = []
archivos = sorted([f for f in os.listdir(LIMPIO_DIR) if f.endswith(".json")])
for nombre in archivos:
    ruta = os.path.join(LIMPIO_DIR, nombre)
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    o = datos.get("oferta", {})
    pagina = datos.get("pagina", {})
    reg = {
        "archivo_origen": nombre,
        "tipo_oferta": datos.get("tipo_oferta"),
        "oferta_id": o.get("oferta_id", {}).get("valor"),
        "product_name": o.get("product_name", {}).get("valor"),
        "brand": o.get("brand", {}).get("valor"),
        "model": o.get("model", {}).get("valor"),
        "price": o.get("price", {}).get("valor"),
        "price_texto": o.get("price_texto", {}).get("valor"),
        "currency": o.get("currency", {}).get("valor"),
        "location": o.get("location", {}).get("valor"),
        "installation": o.get("installation", {}).get("valor"),
        "publication_date": o.get("publication_date", {}).get("valor"),
        "pagina_url": pagina.get("url", {}).get("valor"),
        "fuente_nombre": pagina.get("fuente_nombre", {}).get("valor"),
    }
    tipo = reg["tipo_oferta"]
    if tipo == "panel_solar":
        reg["power_w"] = o.get("power_w", {}).get("valor")
        reg["panel_type"] = o.get("panel_type", {}).get("valor")
    elif tipo == "inversor_solar":
        reg["power_w"] = o.get("power_w", {}).get("valor")
        reg["inverter_type"] = o.get("inverter_type", {}).get("valor")
        reg["output_voltage"] = o.get("output_voltage", {}).get("valor")
        reg["mppt"] = o.get("mppt", {}).get("valor")
    elif tipo == "bateria_solar":
        reg["capacity_kwh"] = o.get("capacity_kwh", {}).get("valor")
        reg["capacity_ah"] = o.get("capacity_ah", {}).get("valor")
        reg["voltage_v"] = o.get("voltage_v", {}).get("valor")
        reg["battery_technology"] = o.get("battery_technology", {}).get("valor")
        reg["cycles"] = o.get("cycles", {}).get("valor")
    elif tipo == "controlador_carga":
        reg["controller_type"] = o.get("controller_type", {}).get("valor")
        reg["current_a"] = o.get("current_a", {}).get("valor")
        reg["voltage_v"] = o.get("voltage_v", {}).get("valor")
    elif tipo == "kit_solar":
        reg["power_w"] = o.get("power_w", {}).get("valor")
        reg["capacity_kwh"] = o.get("capacity_kwh", {}).get("valor")
        reg["output_voltage"] = o.get("output_voltage", {}).get("valor")
        reg["componentes"] = o.get("componentes", {}).get("valor")
    elif tipo == "accesorio_solar":
        reg["accessory_type"] = o.get("accessory_type", {}).get("valor")
        reg["compatibility"] = o.get("compatibility", {}).get("valor")
        reg["specification"] = o.get("specification", {}).get("valor")
    registros.append(reg)

# Ordenar por tipo y precio
def sort_key(r):
    precio = r["price"] if r["price"] is not None else float("inf")
    return (r["tipo_oferta"] or "", precio)
registros.sort(key=sort_key)

# Guardar JSON consolidado
consolidado_path = os.path.join(PRODUCTO_DIR, "ofertas_consolidadas.json")
with open(consolidado_path, "w", encoding="utf-8") as f:
    json.dump(registros, f, ensure_ascii=False, indent=2)
print("Consolidadas", len(registros), "ofertas en", consolidado_path)

# ================================================================
# 2. CALCULAR ESTADÍSTICAS
# ================================================================
tipos = Counter(r["tipo_oferta"] for r in registros)
marcas = Counter(r["brand"] for r in registros if r["brand"])
locs = Counter(r["location"] for r in registros if r["location"])

precios_validos = [r["price"] for r in registros if r["price"] is not None]
precio_min = min(precios_validos) if precios_validos else 0
precio_max = max(precios_validos) if precios_validos else 0
s_precios = sorted(precios_validos)
n_p = len(s_precios)
precio_mediano = s_precios[n_p // 2] if n_p % 2 else (s_precios[n_p // 2 - 1] + s_precios[n_p // 2]) / 2
precio_medio = sum(precios_validos) / n_p if n_p else 0

precio_por_tipo = {}
for t in tipos:
    sub = [r["price"] for r in registros if r["tipo_oferta"] == t and r["price"] is not None]
    if sub:
        ss = sorted(sub)
        nn = len(ss)
        med = ss[nn // 2] if nn % 2 else (ss[nn // 2 - 1] + ss[nn // 2]) / 2
        precio_por_tipo[t] = {
            "n": len(sub), "min": min(sub), "max": max(sub),
            "mediano": med, "medio": sum(sub) / len(sub)
        }

monedas = Counter(r["currency"] for r in registros if r["currency"])
precio_por_moneda = {}
for m in monedas:
    sub = [r["price"] for r in registros if r["currency"] == m and r["price"] is not None]
    if sub:
        ss = sorted(sub)
        nn = len(ss)
        med = ss[nn // 2] if nn % 2 else (ss[nn // 2 - 1] + ss[nn // 2]) / 2
        precio_por_moneda[m] = {
            "n": len(sub), "min": min(sub), "max": max(sub),
            "mediano": med, "medio": sum(sub) / len(sub)
        }

marca_precios = defaultdict(list)
for r in registros:
    if r["brand"] and r["price"] is not None:
        marca_precios[r["brand"]].append(r["price"])
marca_stats = []
for m, ps in marca_precios.items():
    if len(ps) >= 3:
        sps = sorted(ps)
        nn = len(sps)
        med = sps[nn // 2] if nn % 2 else (sps[nn // 2 - 1] + sps[nn // 2]) / 2
        marca_stats.append({
            "marca": m, "n": len(ps), "mediano": med, "min": min(ps), "max": max(ps)
        })
marca_stats.sort(key=lambda x: -x["mediano"])

fechas = [r["publication_date"] for r in registros if r["publication_date"]]
fecha_min = min(fechas) if fechas else None
fecha_max = max(fechas) if fechas else None
dias = Counter(f[:10] for f in fechas)
dias_ordenados = sorted(dias.items())

# Campos técnicos
def stats_campo(func, sub):
    llenos = [v for v in [func(r) for r in sub] if v is not None]
    if not llenos:
        return 0, len(sub), 0.0, None, None, None
    if llenos and isinstance(llenos[0], (list, dict)):
        return len(llenos), len(sub), len(llenos) / len(sub) * 100, "lista", None, None
    try:
        nums = sorted(float(v) for v in llenos)
        nn = len(nums)
        med = nums[nn // 2] if nn % 2 else (nums[nn // 2 - 1] + nums[nn // 2]) / 2
        return len(llenos), len(sub), len(llenos) / len(sub) * 100, min(nums), max(nums), med
    except (ValueError, TypeError):
        try:
            vals_counter = Counter(llenos)
            top = vals_counter.most_common(3)
            return len(llenos), len(sub), len(llenos) / len(sub) * 100, "categórico", top, None
        except TypeError:
            return len(llenos), len(sub), len(llenos) / len(sub) * 100, "lista", None, None

tecnico_por_tipo = {}
for t in ["panel_solar", "inversor_solar", "bateria_solar", "kit_solar"]:
    sub = [r for r in registros if r["tipo_oferta"] == t]
    if t == "panel_solar":
        campos = [("power_w", lambda r: r.get("power_w")), ("panel_type", lambda r: r.get("panel_type"))]
    elif t == "inversor_solar":
        campos = [("power_w", lambda r: r.get("power_w")), ("inverter_type", lambda r: r.get("inverter_type")),
                  ("output_voltage", lambda r: r.get("output_voltage")), ("mppt", lambda r: r.get("mppt"))]
    elif t == "bateria_solar":
        campos = [("capacity_kwh", lambda r: r.get("capacity_kwh")), ("capacity_ah", lambda r: r.get("capacity_ah")),
                  ("voltage_v", lambda r: r.get("voltage_v")), ("battery_technology", lambda r: r.get("battery_technology")),
                  ("cycles", lambda r: r.get("cycles"))]
    elif t == "kit_solar":
        campos = [("power_w", lambda r: r.get("power_w")), ("capacity_kwh", lambda r: r.get("capacity_kwh")),
                  ("output_voltage", lambda r: r.get("output_voltage")), ("componentes", lambda r: r.get("componentes"))]
    else:
        campos = []
    tecnico_por_tipo[t] = {"n": len(sub), "campos": [(c[0],) + stats_campo(c[1], sub) for c in campos]}

# ================================================================
# 3. GENERAR CATÁLOGO HTML (Opción A) - usando plantillas con .replace()
# ================================================================
def generar_catalogo():
    # Construir filas de la tabla
    filas_html = []
    for r in registros:
        tipo = r["tipo_oferta"] or ""
        badge_tipo = {
            "panel_solar": "badge-panel",
            "inversor_solar": "badge-inversor",
            "bateria_solar": "badge-bateria",
            "kit_solar": "badge-kit",
        }.get(tipo, "")
        nombre_tipo = {
            "panel_solar": "Panel",
            "inversor_solar": "Inversor",
            "bateria_solar": "Batería",
            "kit_solar": "Kit",
        }.get(tipo, tipo)

        marca = r["brand"] or "—"
        modelo = r["model"] or "—"
        product_name = r["product_name"] or "Sin nombre"

        if r["price"] is not None:
            moneda_badge = "badge-usd" if r["currency"] == "USD" else "badge-cup"
            precio_html = '<span class="badge %s">%s</span> %s' % (
                moneda_badge, r["currency"], format(r["price"], ",.0f")
            )
        else:
            precio_html = '<span class="precio-nulo">Sin precio (simbólico)</span>'

        location = r["location"] or "—"
        fecha = r["publication_date"] or "—"
        if fecha and "T" in fecha:
            fecha = fecha[:10]

        # Resumen técnico
        tecnico_html = ""
        if tipo == "panel_solar":
            pw = r.get("power_w")
            pt = r.get("panel_type") or "desconocido"
            if pw:
                tecnico_html += '<span class="tech-badge">%s W</span>' % format(pw, ",.0f")
            tecnico_html += '<span class="tech-badge">%s</span>' % pt
        elif tipo == "inversor_solar":
            pw = r.get("power_w")
            it = r.get("inverter_type") or "desconocido"
            ov = r.get("output_voltage") or "desconocido"
            if pw:
                tecnico_html += '<span class="tech-badge">%s W</span>' % format(pw, ",.0f")
            tecnico_html += '<span class="tech-badge">%s</span><span class="tech-badge">%s</span>' % (it, ov)
        elif tipo == "bateria_solar":
            ck = r.get("capacity_kwh")
            ca = r.get("capacity_ah")
            vv = r.get("voltage_v")
            bt = r.get("battery_technology") or "desconocido"
            if ck:
                tecnico_html += '<span class="tech-badge">%s kWh</span>' % ck
            if ca:
                tecnico_html += '<span class="tech-badge">%s Ah</span>' % ca
            if vv:
                tecnico_html += '<span class="tech-badge">%s V</span>' % vv
            tecnico_html += '<span class="tech-badge">%s</span>' % bt
        elif tipo == "kit_solar":
            pw = r.get("power_w")
            ck = r.get("capacity_kwh")
            if pw:
                tecnico_html += '<span class="tech-badge">%s W</span>' % format(pw, ",.0f")
            if ck:
                tecnico_html += '<span class="tech-badge">%s kWh</span>' % ck

        filas_html.append(
            '<tr data-tipo="%s" data-marca="%s" data-moneda="%s" data-precio="%s" data-location="%s">'
            '<td><span class="badge %s">%s</span></td>'
            '<td>%s</td>'
            '<td>%s</td>'
            '<td>%s</td>'
            '<td>%s</td>'
            '<td>%s</td>'
            '<td>%s</td>'
            '<td>%s</td>'
            '</tr>' % (
                tipo, marca or "", r["currency"] or "",
                r["price"] if r["price"] is not None else 999999999, location or "",
                badge_tipo, nombre_tipo,
                product_name, marca, modelo,
                precio_html, location, fecha,
                tecnico_html if tecnico_html else '<span class="vacío">—</span>'
            )
        )

    cuerpo_tabla = "\n".join(filas_html)

    # Opciones de select
    opciones_marca = ""
    for m, _ in marcas.most_common():
        opciones_marca += '<option value="%s">%s</option>\n' % (m, m)

    opciones_ubicacion = ""
    for l, _ in locs.most_common():
        opciones_ubicacion += '<option value="%s">%s</option>\n' % (l, l)

    # Plantilla HTML (sin f-strings, usar marcadores __MARCADOR__)
    html_plantilla = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Catálogo Solar - Ofertas Bembete</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
    .container { max-width: 1400px; margin: 0 auto; }
    header { background: #1a5f7a; color: white; padding: 20px; border-radius: 8px 8px 0 0; margin-bottom: 20px; }
    header h1 { margin: 0; font-size: 1.8rem; }
    header p { margin: 5px 0 0; opacity: 0.9; }
    .filtros { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .filtros h2 { margin-top: 0; font-size: 1.2rem; color: #1a5f7a; }
    .filtro-group { display: inline-block; margin-right: 20px; vertical-align: top; }
    .filtro-group label { display: block; margin-bottom: 5px; font-weight: 600; color: #333; }
    .filtro-group select, .filtro-group input { width: 200px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
    .filtro-group input[type="number"] { width: 120px; }
    .resultados { margin-top: 15px; font-size: 0.9rem; color: #666; }
    table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    th { background: #1a5f7a; color: white; padding: 12px; text-align: left; font-weight: 600; }
    td { padding: 12px; border-bottom: 1px solid #eee; font-size: 14px; }
    tr:hover { background: #f8f8f8; }
    tr:nth-child(even) { background: #fafafa; }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-panel { background: #e3f2fd; color: #1565c0; }
    .badge-inversor { background: #fff3e0; color: #e65100; }
    .badge-bateria { background: #e8f5e9; color: #2e7d32; }
    .badge-kit { background: #f3e5f5; color: #7b1fa2; }
    .badge-usd { background: #4caf50; color: white; }
    .badge-cup { background: #ff9800; color: white; }
    .precio-nulo { color: #999; font-style: italic; }
    .vacío { color: #ccc; }
    .tech-badge { background: #e0e0e0; color: #333; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 4px; }
    footer { margin-top: 30px; padding: 20px; color: #666; font-size: 0.9rem; border-top: 1px solid #ddd; }
</style>
</head>
<body>
<div class="container">
<header>
    <h1>☀️ Catálogo Solar - Ofertas Bembete</h1>
    <p>Ofertas solares recolectadas de bembete.com • Datos limpios y validados</p>
</header>

<div class="filtros">
    <h2>Filtros</h2>
    <div class="filtro-group">
        <label>Tipo de oferta</label>
        <select id="filtroTipo">
            <option value="">Todos</option>
            <option value="panel_solar">Panel Solar</option>
            <option value="inversor_solar">Inversor Solar</option>
            <option value="bateria_solar">Batería Solar</option>
            <option value="kit_solar">Kit Solar</option>
        </select>
    </div>
    <div class="filtro-group">
        <label>Marca</label>
        <select id="filtroMarca">
            <option value="">Todas</option>
            __MARCAS__
        </select>
    </div>
    <div class="filtro-group">
        <label>Moneda</label>
        <select id="filtroMoneda">
            <option value="">Todas</option>
            <option value="USD">USD</option>
            <option value="CUP">CUP</option>
        </select>
    </div>
    <div class="filtro-group">
        <label>Precio máximo</label>
        <input type="number" id="filtroPrecioMax" placeholder="Sin límite">
    </div>
    <div class="filtro-group" style="margin-top: 25px;">
        <label>Ubicación</label>
        <select id="filtroUbicacion">
            <option value="">Todas</option>
            __UBICACIONES__
        </select>
    </div>
    <div class="resultados" id="contadorResultados"></div>
</div>

<table id="tablaOfertas">
    <thead>
        <tr>
            <th>Tipo</th>
            <th>Producto</th>
            <th>Marca</th>
            <th>Modelo</th>
            <th>Precio</th>
            <th>Ubicación</th>
            <th>Fecha</th>
            <th>Técnico</th>
        </tr>
    </thead>
    <tbody id="cuerpoTabla">
__FILAS__
    </tbody>
</table>

<footer>
    <p>Total de ofertas: <strong>__TOTAL__</strong> • Fuente: Bembete (bembete.com) • Datos generados automáticamente</p>
</footer>
</div>

<script>
const filas = document.querySelectorAll('#tablaOfertas tbody tr');
const contador = document.getElementById('contadorResultados');

function filtrar() {
    const tipo = document.getElementById('filtroTipo').value;
    const marca = document.getElementById('filtroMarca').value;
    const moneda = document.getElementById('filtroMoneda').value;
    const precioMax = document.getElementById('filtroPrecioMax').value;
    const ubicacion = document.getElementById('filtroUbicacion').value;

    let visibles = 0;
    filas.forEach(fila => {
        const coincideTipo = !tipo || fila.dataset.tipo === tipo;
        const coincideMarca = !marca || fila.dataset.marca === marca;
        const coincideMoneda = !moneda || fila.dataset.moneda === moneda;
        const precio = parseFloat(fila.dataset.precio);
        const coincidePrecio = !precioMax || (precio !== 999999999 && precio <= parseFloat(precioMax));
        const coincideUbicacion = !ubicacion || fila.dataset.location === ubicacion;

        if (coincideTipo && coincideMarca && coincideMoneda && coincidePrecio && coincideUbicacion) {
            fila.style.display = '';
            visibles++;
        } else {
            fila.style.display = 'none';
        }
    });

    contador.textContent = 'Mostrando ' + visibles + ' de ' + filas.length + ' ofertas';
}

document.getElementById('filtroTipo').addEventListener('change', filtrar);
document.getElementById('filtroMarca').addEventListener('change', filtrar);
document.getElementById('filtroMoneda').addEventListener('change', filtrar);
document.getElementById('filtroPrecioMax').addEventListener('input', filtrar);
document.getElementById('filtroUbicacion').addEventListener('change', filtrar);

filtrar();
</script>
</body>
</html>"""

    html = html_plantilla.replace("__MARCAS__", opciones_marca)
    html = html.replace("__UBICACIONES__", opciones_ubicacion)
    html = html.replace("__FILAS__", cuerpo_tabla)
    html = html.replace("__TOTAL__", str(len(registros)))

    catalogo_path = os.path.join(PRODUCTO_DIR, "catalogo.html")
    with open(catalogo_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Catálogo generado:", catalogo_path)

# ================================================================
# 4. GENERAR REPORTE DE MERCADO HTML (Opción B)
# ================================================================
def generar_reporte():
    # Tabla de tipos
    filas_tipo = ""
    for t, c in tipos.most_common():
        filas_tipo += (
            '<tr><td><span class="badge badge-%s">%s</span></td>'
            '<td>%d</td><td>%.1f%%</td></tr>'
        ) % (t.replace("_", "-"), t.replace("_", " ").title(), c, c / len(registros) * 100)

    # Tabla de precios por tipo
    filas_precio_tipo = ""
    for t in sorted(tipos.keys()):
        if t in precio_por_tipo:
            d = precio_por_tipo[t]
            filas_precio_tipo += (
                '<tr><td><span class="badge badge-%s">%s</span></td>'
                '<td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
            ) % (
                t.replace("_", "-"), t.replace("_", " ").title(),
                d["n"], format(d["min"], ",.0f"), format(d["max"], ",.0f"),
                format(d["mediano"], ",.0f"), format(d["medio"], ",.0f")
            )

    # Tabla de precios por moneda
    filas_moneda = ""
    for m, d in precio_por_moneda.items():
        filas_moneda += (
            '<tr><td><span class="badge">%s</span></td>'
            '<td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
        ) % (m, d["n"], format(d["min"], ",.0f"), format(d["max"], ",.0f"),
             format(d["mediano"], ",.0f"), format(d["medio"], ",.0f"))

    # Tabla de marcas
    filas_marca = ""
    for ms in marca_stats[:10]:
        filas_marca += (
            '<tr><td>%s</td><td>%d</td><td>%s</td><td>%s - %s</td></tr>'
        ) % (ms["marca"], ms["n"], format(ms["mediano"], ",.0f"),
             format(ms["min"], ",.0f"), format(ms["max"], ",.0f"))

    # Tabla de ubicaciones
    filas_ubicacion = ""
    for l, c in locs.most_common():
        filas_ubicacion += (
            '<tr><td>%s</td><td>%d</td><td>%.1f%%</td></tr>'
        ) % (l, c, c / len(registros) * 100)

    # Tabla de fechas
    filas_fecha = ""
    for d_fecha, c in dias_ordenados:
        filas_fecha += '<tr><td>%s</td><td>%d</td></tr>' % (d_fecha, c)

    # Tabla de campos técnicos
    filas_tecnico = ""
    badge_map = {
        "panel_solar": "badge-panel",
        "inversor_solar": "badge-inversor",
        "bateria_solar": "badge-bateria",
        "kit_solar": "badge-kit",
    }
    nombre_tipo_map = {
        "panel_solar": "Panel",
        "inversor_solar": "Inversor",
        "bateria_solar": "Batería",
        "kit_solar": "Kit",
    }
    for t in ["panel_solar", "inversor_solar", "bateria_solar", "kit_solar"]:
        if t not in tecnico_por_tipo:
            continue
        d = tecnico_por_tipo[t]
        badge_clase = badge_map.get(t, "")
        nombre_tipo = nombre_tipo_map.get(t, t)
        for campo, llenos, total, pct, mn, mx, med in d["campos"]:
            mn_str = format(mn, ",.0f") if isinstance(mn, (int, float)) else str(mn)
            mx_str = format(mx, ",.0f") if isinstance(mx, (int, float)) else str(mx)
            filas_tecnico += (
                '<tr><td><span class="badge %s">%s</span></td>'
                '<td>%s</td><td>%d</td><td>%d</td><td>%.1f%%</td></tr>'
            ) % (badge_clase, nombre_tipo, campo, llenos, total, pct)

    # Plantilla del reporte
    html_plantilla = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reporte de Mercado Solar - Bembete</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #333; }
    .container { max-width: 1100px; margin: 0 auto; }
    header { background: #1a5f7a; color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; }
    header h1 { margin: 0; font-size: 2rem; }
    header p { margin: 10px 0 0; opacity: 0.9; }
    .resumen { display: flex; gap: 15px; margin-bottom: 30px; }
    .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; }
    .card h3 { margin-top: 0; font-size: 1rem; color: #1a5f7a; text-transform: uppercase; letter-spacing: 1px; }
    .card .valor { font-size: 2rem; font-weight: bold; margin: 10px 0; }
    .card .sub { font-size: 0.9rem; color: #666; }
    h2 { color: #1a5f7a; border-bottom: 2px solid #1a5f7a; padding-bottom: 10px; margin-top: 30px; }
    table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 25px; }
    th { background: #e8f4f8; color: #1a5f7a; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #1a5f7a; }
    td { padding: 12px; border-bottom: 1px solid #eee; }
    tr:nth-child(even) { background: #fafafa; }
    tr:hover { background: #f0f7fa; }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-panel { background: #e3f2fd; color: #1565c0; }
    .badge-inversor { background: #fff3e0; color: #e65100; }
    .badge-bateria { background: #e8f5e9; color: #2e7d32; }
    .badge-kit { background: #f3e5f5; color: #7b1fa2; }
    .alerta { background: #fff3cd; border: 1px solid #ffc107; color: #856404; padding: 15px; border-radius: 8px; margin-bottom: 25px; }
    .conclusion { background: #e7f3ff; border-left: 4px solid #1a5f7a; padding: 15px; margin-bottom: 25px; }
    footer { margin-top: 40px; padding: 20px; color: #666; font-size: 0.9rem; border-top: 1px solid #ddd; }
</style>
</head>
<body>
<div class="container">
<header>
    <h1>📊 Reporte de Mercado Solar</h1>
    <p>Análisis de ofertas recolectadas de bembete.com • __TOTAL__ ofertas validadas</p>
</header>

<div class="resumen">
    <div class="card">
        <h3>Total ofertas</h3>
        <div class="valor">__TOTAL__</div>
        <div class="sub">ofertas analizadas</div>
    </div>
    <div class="card">
        <h3>Precio mediano</h3>
        <div class="valor">__PRECIO_MEDIANO__ USD</div>
        <div class="sub">precio medio: __PRECIO_MEDIO__ USD</div>
    </div>
    <div class="card">
        <h3>Rango de precios</h3>
        <div class="valor">__PRECIO_MIN__ - __PRECIO_MAX__</div>
        <div class="sub">USD</div>
    </div>
    <div class="card">
        <h3>Marcas detectadas</h3>
        <div class="valor">__NUM_MARCAS__</div>
        <div class="sub">marcas únicas</div>
    </div>
</div>

<h2>1. Distribución por tipo de oferta</h2>
<table>
    <thead><tr><th>Tipo</th><th>Cantidad</th><th>Porcentaje</th></tr></thead>
    <tbody>
__FILAS_TIPO__
    </tbody>
</table>

<h2>2. Precio por tipo de oferta</h2>
<table>
    <thead><tr><th>Tipo</th><th>Nº ofertas</th><th>Mín (USD)</th><th>Máx (USD)</th><th>Mediano (USD)</th><th>Medio (USD)</th></tr></thead>
    <tbody>
__FILAS_PRECIO_TIPO__
    </tbody>
</table>

<h2>3. Precio por moneda</h2>
<table>
    <thead><tr><th>Moneda</th><th>Nº ofertas</th><th>Mín</th><th>Máx</th><th>Mediano</th><th>Medio</th></tr></thead>
    <tbody>
__FILAS_MONEDA__
    </tbody>
</table>

<h2>4. Marcas más frecuentes (con ≥ 3 ofertas y precio)</h2>
<table>
    <thead><tr><th>Marca</th><th>Nº ofertas</th><th>Precio mediano (USD)</th><th>Rango (USD)</th></tr></thead>
    <tbody>
__FILAS_MARCA__
    </tbody>
</table>

<h2>5. Ubicación geográfica</h2>
<table>
    <thead><tr><th>Provincia</th><th>Ofertas</th><th>Porcentaje</th></tr></thead>
    <tbody>
__FILAS_UBICACION__
    </tbody>
</table>

<h2>6. Evolución temporal (ofertas por día)</h2>
<table>
    <thead><tr><th>Fecha</th><th>Ofertas</th></tr></thead>
    <tbody>
__FILAS_FECHA__
    </tbody>
</table>

<h2>7. Disponibilidad de campos técnicos por tipo</h2>
<table>
    <thead><tr><th>Tipo</th><th>Campo técnico</th><th>Llenos</th><th>Total</th><th>% llenado</th></tr></thead>
    <tbody>
__FILAS_TECNICO__
    </tbody>
</table>

<div class="alerta">
    <strong>⚠️ Observaciones importantes:</strong>
    <ul>
        <li>Se detectó un outlier en <em>power_w</em> de inversores (5.363.723.150 W) que debe revisarse antes de uso productivo.</li>
        <li>El 55% de las ofertas no tiene marca detectada.</li>
        <li>Los campos técnicos más críticos con poca cobertura son <em>capacity_kwh</em> en baterías (7/60) y <em>cycles</em> (1/60).</li>
        <li>46 ofertas tienen precio simbólico (0 o 1) y se marcaron como <code>price: null</code> con flag <code>precio_simbolico: true</code>.</li>
    </ul>
</div>

<div class="conclusion">
    <strong>📋 Conclusiones del mercado:</strong>
    <ul>
        <li><strong>Must</strong> es la marca más frecuente (21 ofertas) con precio mediano de 1.000 USD.</li>
        <li><strong>Infinity Solar</strong> tiene el precio mediano más alto (2.750 USD) entre marcas con suficiente muestra.</li>
        <li><strong>Jinko</strong> y <strong>Longi</strong> ofrecen los paneles más económicos (mediano ~150 USD).</li>
        <li>El 88% de las ofertas se concentran en La Habana; solo el 12% en Isla de la Juventud.</li>
        <li>El pico de publicación fue el 26 de octubre de 2026 con 62 ofertas.</li>
    </ul>
</div>

<footer>
    <p>Reporte generado a partir de __TOTAL__ ofertas limpias validadas del repositorio.</p>
    <p>Fuente: Bembete (bembete.com) • Período: 15 al 29 de octubre de 2026</p>
</footer>
</div>
</body>
</html>"""

    html = html_plantilla.replace("__TOTAL__", str(len(registros)))
    html = html.replace("__PRECIO_MEDIANO__", format(precio_mediano, ",.0f"))
    html = html.replace("__PRECIO_MEDIO__", format(precio_medio, ",.0f"))
    html = html.replace("__PRECIO_MIN__", format(precio_min, ",.0f"))
    html = html.replace("__PRECIO_MAX__", format(precio_max, ",.0f"))
    html = html.replace("__NUM_MARCAS__", str(len(marcas)))
    html = html.replace("__FILAS_TIPO__", filas_tipo)
    html = html.replace("__FILAS_PRECIO_TIPO__", filas_precio_tipo)
    html = html.replace("__FILAS_MONEDA__", filas_moneda)
    html = html.replace("__FILAS_MARCA__", filas_marca)
    html = html.replace("__FILAS_UBICACION__", filas_ubicacion)
    html = html.replace("__FILAS_FECHA__", filas_fecha)
    html = html.replace("__FILAS_TECNICO__", filas_tecnico)

    reporte_path = os.path.join(PRODUCTO_DIR, "reporte_mercado.html")
    with open(reporte_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Reporte generado:", reporte_path)

# ================================================================
# Ejecutar
# ================================================================
generar_catalogo()
generar_reporte()
print("\nProducto generado correctamente en:", PRODUCTO_DIR)
