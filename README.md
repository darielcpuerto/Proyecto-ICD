# Proyecto de Recolección y Análisis de Ofertas Solares - Bembete

## Descripción

Este proyecto contiene el proceso completo de recolección, limpieza, validación y publicación de ofertas de productos solares (paneles, inversores, baterías, kits, accesorios y controladores de carga) extraídas de la plataforma clasificada **bembete.com** (Cuba).

El producto final incluye:
- **224 ofertas validadas** en formato JSON individual (`archivos/clean/modelos_json/`)
- **Archivo maestro consolidado** con todas las ofertas (`producto/ofertas_consolidadas.json`)
- **Catálogo web estático** con filtros interactivos (`producto/catalogo.html`)
- **Reporte de mercado** con estadísticas descriptivas (`producto/reporte_mercado.html`)
- **Modelos de referencia** JSON para 6 tipos de ofertas solares (`referencias/modelos/`)
- **Herramientas reproducibles** de generación y auditoría (`herramientas/recoleccion/`)

---

## Estructura del repositorio

```
proyecto/
├── README.md                          # Este archivo
├── INFORME_METODOLOGIA.md             # Informe detallado de metodología
├── referencias/
│   └── modelos/                       # Esquemas JSON de referencia (6 tipos)
│       ├── panel_solar.json
│       ├── inversor_solar.json
│       ├── bateria_solar.json
│       ├── controlador_carga.json
│       ├── kit_solar.json
│       └── accesorio_solar.json
├── archivos/
│   ├── recoleccion/                   # Datos crudos de recolección (OLP-002 Bembete)
│   │   ├── candidatos.jsonl
│   │   ├── datos.jsonl                # 250 registros extraídos (JSON-LD)
│   │   ├── crudo/                     # 250 HTML crudos de anuncios
│   │   ├── texto/                     # 250 versiones simplificadas en texto
│   │   └── modelos_json_individuales/ # (vacío, movido a clean/)
│   └── clean/
│       └── modelos_json/              # 224 ofertas validadas (entrega principal)
├── producto/
│   ├── generar_producto.py            # Script que genera catálogo y reporte
│   ├── ofertas_consolidadas.json      # Archivo maestro con las 224 ofertas
│   ├── catalogo.html                  # Catálogo web estático con filtros (Opción A)
│   └── reporte_mercado.html           # Reporte de mercado con estadísticas (Opción B)
├── herramientas/
│   └── recoleccion/
│       ├── generar_modelos_json.py    # Genera JSON individuales desde datos.jsonl + crudo
│       └── auditar_y_mover_clean.py   # Audita y mueve JSON válidos a clean/
├── journal/                           # Bitácora del proyecto
├── handoffs/                          # Documentos de transición entre fases
└── referencias/contexto/              # Documentos de contexto (objetivos, metodología, etc.)
```

---

## Producto entregable

### 1. Catálogo web estático (`producto/catalogo.html`)

Página HTML autocontenida que permite navegar y filtrar las 224 ofertas por:
- **Tipo de oferta**: Panel Solar, Inversor Solar, Batería Solar, Kit Solar
- **Marca**: Must, Longi, Sumry, Ecoflow, Humsienk, Seg, etc.
- **Moneda**: USD, CUP
- **Precio máximo**: filtro numérico
- **Ubicación**: La Habana, Isla de la Juventud

Cada fila muestra: tipo, producto, marca, modelo, precio, ubicación, fecha y resumen técnico (potencia, capacidad, tipo de panel, etc.).

**Uso:** Abrir `producto/catalogo.html` en cualquier navegador web. No requiere servidor ni instalación.

### 2. Reporte de mercado (`producto/reporte_mercado.html`)

Documento HTML con estadísticas descriptivas del mercado solar cubano basado en los datos recolectados:
- Distribución por tipo de oferta
- Estadísticas de precio por tipo, moneda y marca
- Ubicación geográfica de las ofertas
- Evolución temporal (ofertas por día)
- Disponibilidad de campos técnicos por tipo de oferta
- Conclusiones y observaciones sobre calidad de datos

**Uso:** Abrir `producto/reporte_mercado.html` en cualquier navegador web.

### 3. Archivo maestro (`producto/ofertas_consolidadas.json`)

JSON único con todas las 224 ofertas, cada una con todos sus campos (base y técnicos específicos por tipo). Ideal para importar en herramientas de análisis de datos (Python pandas, R, Excel, etc.).

### 4. Análisis de brecha demanda-oferta (`producto/reporte_brecha_mercado.html`)

Reporte HTML que cruza los datos de **demanda** (35 respuestas del cuestionario de mercado solar) con los datos de **oferta** (224 ofertas validadas de bembete.com). Incluye:

- **Cobertura geográfica**: municipio de residencia vs ubicación de las ofertas
- **Equipos necesarios vs tipo de oferta**: refrigeración, cocción, comunicación, climatización vs inversores, baterías, kits
- **Frecuencia de apagones vs capacidad de batería**: análisis de si las baterías ofertadas cubren las horas de apagón reportadas
- **Precio vs accesibilidad**: umbrales de precio por segmento de accesibilidad al mercado
- **Respaldo eléctrico actual vs oferta recomendada**: qué tipo de equipo necesita cada segmento
- **Sector laboral vs precio sugerido**: umbrales de precio por sector laboral

**Uso:** Abrir `producto/reporte_brecha_mercado.html` en cualquier navegador web.

---


## Modelos de referencia

Los 6 esquemas JSON en `referencias/modelos/` definen la estructura canónica para cada tipo de oferta solar:

| Archivo | Tipo de oferta | Campos técnicos clave |
|---------|---------------|----------------------|
| `panel_solar.json` | panel_solar | power_w, panel_type |
| `inversor_solar.json` | inversor_solar | power_w, inverter_type, output_voltage, mppt |
| `bateria_solar.json` | bateria_solar | capacity_kwh, capacity_ah, voltage_v, battery_technology, cycles |
| `controlador_carga.json` | controlador_carga | controller_type, current_a, voltage_v |
| `kit_solar.json` | kit_solar | power_w, capacity_kwh, output_voltage, componentes |
| `accesorio_solar.json` | accesorio_solar | accessory_type, compatibility, specification |

Cada campo incluye `tipo` (texto, decimal, entero, booleano, lista<objeto>), `unidad` cuando aplica, `valores_permitidos` para campos enumerados, y `valor` (el dato extraído o `null`).

---

## Herramientas reproducibles

### `herramientas/recoleccion/generar_modelos_json.py`

Lee `datos.jsonl` (JSON-LD extraído de bembete) + HTML crudo, y genera un JSON individual por oferta rellenando el modelo de referencia correspondiente. Incluye validación de tipos y valores permitidos.

### `herramientas/recoleccion/auditar_y_mover_clean.py`

Audita cada JSON generado verificando:
- Estructura correcta (pagina, tipo_oferta, oferta)
- Tipos de dato correctos
- Valores dentro de `valores_permitidos`
- Campos obligatorios presentes

Los JSON válidos se mueven a `archivos/clean/modelos_json/`.

---

## Flujo de datos

```
datos.jsonl (JSON-LD de bembete) + crudo/ (HTML)
         ↓
herramientas/recoleccion/generar_modelos_json.py
         ↓
modelos_json_individuales/ (JSON no auditados)
         ↓
herramientas/recoleccion/auditar_y_mover_clean.py
         ↓
archivos/clean/modelos_json/ (224 JSON válidos)
         ↓
producto/generar_producto.py
         ↓
producto/ofertas_consolidadas.json
producto/catalogo.html
producto/reporte_mercado.html
```

---

## Calidad de datos y limitaciones

| Aspecto | Estado |
|---------|--------|
| Ofertas totales procesadas | 224 |
| Campos base siempre llenos | 100% (URL, ID, título, precio, moneda, fecha, ubicación, fuente) |
| Precios simbólicos (0 o 1) | 46, marcados como `price: null` + `precio_simbolico: true` |
| Ubicación | 100% (La Habana 88%, Isla de la Juventud 12%) |
| Marca detectada | 45% (101 de 224) |
| Campos técnicos llenados | 64,4% promedio |
| Falsos positivos de clasificación | 0 (lista negra aplicada) |
| Modelos basura filtrados | 0 (después de v3) |

**Limitaciones conocidas:**
- Un outlier en `power_w` de inversores (5.363.723.150 W) por error de parsing del título
- Campos técnicos profundos (ciclos, voltaje, capacidad kWh) con baja cobertura en baterías
- Modelo de ofertas kits con `componentes` solo parseado en 2 de 19 casos (depende del texto del anuncio)

---

## Cómo reproducir

```bash
# 1. Generar JSON individuales desde datos.jsonl + HTML crudo
python3 herramientas/recoleccion/generar_modelos_json.py

# 2. Auditar y mover válidos a clean/
python3 herramientas/recoleccion/auditar_y_mover_clean.py

# 3. Generar producto (catálogo + reporte de mercado + JSON consolidado)
python3 producto/generar_producto.py

# 4. Cruzar demanda (cuestionario) con oferta (ofertas)
python3 producto/cruce_demanda_oferta.py
```

---

## Licencia y contacto

Proyecto desarrollado para recolección y análisis de datos de mercado solar en Cuba. Fuente de datos: bembete.com.

---

## Informe de metodología

Ver [`INFORME_METODOLOGIA.md`](INFORME_METODOLOGIA.md) para el detalle completo del proceso de recolección, limpieza, validación y análisis.
