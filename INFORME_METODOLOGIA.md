# Informe de Metodología

**Proyecto:** Recolección, limpieza y análisis de ofertas solares de bembete.com  
**Fecha:** Noviembre 2026  
**Fuente principal:** bembete.com (plataforma de clasificados, Cuba)  
**Identificador de fuente:** OLP-002 (Bembete)

---

## 1. Objetivos del proyecto

1. Recolectar ofertas de productos solares (paneles, inversores, baterías, kits, accesorios, controladores de carga) desde bembete.com.
2. Establecer un esquema de datos común (modelos JSON) para estandarizar la información extraída.
3. Limpiar, validar y enriquecer los datos recolectados.
4. Producir un producto entregable: catálogo web estático y reporte de mercado con estadísticas descriptivas.

---

## 2. Fuentes de datos

### 2.1 Bembete (OLP-002)

- **Tipo de fuente:** Clasificados en línea (estilo Marketplace de Cuba)
- **URL base:** https://bembete.com
- **Período de recolección:** 15 al 29 de octubre de 2026
- **Método de descubrimiento:** Sitemaps diarios (ventana de 8 días)
- **Bloqueo anti-bot:** No detectado
- **Páginas aceptadas:** 250
- **Registros extraídos:** 105 inicialmente (fase de descubrimiento), 250 en `datos.jsonl` (fase completa)

### 2.2 Otras fuentes (no utilizadas en el producto final)

| Fuente | ID | Estado | Motivo |
|--------|----|--------|--------|
| Revolico | OLP-001 | Bloqueado | HTTP 403 durante descubrimiento |
| SunCar | OLP-004 | Procesado | 2 ofertas disponibles, sin objetivo de volumen |
| Infinity Energy Cuba | OLP-005 | Procesado | 1 oferta disponible, sin objetivo de volumen |

---

## 3. Proceso de recolección

La recolección se realizó con una herramienta interna (`herramientas/recoleccion/`) que incluye:

1. **Descubrimiento de URLs:** Parsing de sitemaps diarios de bembete.com para identificar URLs de tipo "detalle" (anuncios individuales).
2. **Filtro de relevancia:** Solo se incluyeron URLs cuyo slug contuviera términos relacionados con energía solar (panel, inversor, batería, kit, etc.).
3. **Descarga de HTML crudo:** Cada página de detalle se descargó y se guardó en `archivos/recoleccion/OLP-002_bembete/crudo/`.
4. **Extracción estructurada:** Se extrajo JSON-LD (schema.org Product) de cada HTML y se guardó en `archivos/recoleccion/OLP-002_bembete/datos.jsonl`.
5. **Extracción de texto simplificado:** Se generó una versión en texto plano de cada anuncio en `archivos/recoleccion/OLP-002_bembete/texto/`.

**Estadísticas de recolección (OLP-002):**
- Candidatos generados: 28,843
- Candidatos descartados por URL: 26,333
- Páginas aceptadas: 250
- Páginas descartadas: 990
- Registros extraídos: 105 (fase inicial) → 250 (datos.jsonl completo)
- Intentos de red: 1,095
- Errores: 0

---

## 4. Modelos de referencia

Se definieron 6 esquemas JSON en `referencias/modelos/`, uno por tipo de oferta:

| Archivo | tipo_oferta | Campos específicos |
|---------|-------------|-------------------|
| `panel_solar.json` | panel_solar | power_w (W), panel_type |
| `inversor_solar.json` | inversor_solar | power_w (W), inverter_type, output_voltage, mppt |
| `bateria_solar.json` | bateria_solar | capacity_kwh, capacity_ah (Ah), voltage_v (V), battery_technology, cycles |
| `controlador_carga.json` | controlador_carga | controller_type, current_a (A), voltage_v (V) |
| `kit_solar.json` | kit_solar | power_w, capacity_kwh, output_voltage, componentes (lista<objeto>) |
| `accesorio_solar.json` | accesorio_solar | accessory_type, compatibility, specification |

Cada campo incluye:
- `tipo`: texto, decimal, entero, booleano, lista<objeto>
- `unidad`: cuando aplica (W, kWh, Ah, V, A)
- `valores_permitidos`: para campos enumerados (moneda, tipo de panel, tipo de inversor, etc.)
- `valor`: el dato extraído o `null`

**Estructura común:**
- `pagina`: url, fuente_nombre
- `tipo_oferta`: identificador del tipo
- `oferta`: oferta_id, product_name, brand, model, price, price_texto, currency, location, installation, publication_date + campos específicos

---

## 5. Proceso de limpieza y llenado de modelos

### 5.1 Cruzamiento de datos

Cada registro de `datos.jsonl` se cruzó con su HTML crudo correspondiente en `crudo/` mediante `hash_contenido` (relación 1:1: 250 registros, 250 HTML).

### 5.2 Campos extraídos directamente

| Campo | Origen |
|-------|--------|
| `oferta_id` | `id_oferta` del JSON-LD |
| `product_name` | `name` del JSON-LD |
| `price` / `price_texto` / `currency` | `price` / `priceCurrency` del JSON-LD |
| `publication_date` | `datePublished` / `validFrom` del JSON-LD |
| `pagina.url` | `url_oferta` del JSON-LD |
| `pagina.fuente_nombre` | "Bembete (bembete.com)" |
| `location` | Extraída del cuerpo HTML (provincia cubana) |
| `installation` | No disponible en origen (null) |

### 5.3 Campos inferidos del título y descripción

Se aplicaron reglas basadas en expresiones regulares sobre el texto combinado (título + descripción + cuerpo HTML):

- **Marca:** Detectada mediante diccionario de 34 marcas solares conocidas (Must, Longi, Ecoflow, Sumry, etc.), con canonización de variantes (ej. "Felicitysolar" → "Felicity Solar").
- **Modelo:** Código alfanumérico extraído del título (ej. "PNGNH72", "AC200PL", "IVEM5048"). Se filtraron especificaciones numéricas puras (100Ah, 12V, 6kW) como modelos basura.
- **Potencia (power_w):** Extraída en W; se convierte automáticamente de kW (×1000).
- **Tipo de panel:** "bifacial", "monocristalino", "policristalino" o "desconocido".
- **Tipo de inversor:** "hibrido", "off-grid", "on-grid", "microinversor" o "desconocido".
- **Voltaje de salida:** "110V", "220V", "110V/220V" o "desconocido".
- **MPPT:** Booleano basado en presencia de la palabra "mppt".
- **Tecnología de batería:** "litio", "gel", "AGM", "plomo-acido" o "desconocido".
- **Tipo de controlador:** "MPPT", "PWM" o "desconocido".
- **Tipo de accesorio:** "estructura", "cable", "proteccion", "conector" o "otro".
- **Capacidad (kWh, Ah), Voltaje (V), Amperaje (A), Ciclos:** Extraídos con regex del texto.

### 5.4 Filtros de calidad aplicados (v3)

1. **Lista negra de productos no solares:** Se descartaron 26 registros que no eran ofertas solares relevantes (pilas AAA/AA, ventiladores, bocinas, triciclos, refrigeradores, etc.).
2. **Precios simbólicos:** 46 ofertas con precio 0 o 1 se marcaron con `precio_simbolico: true` y su `price` se estableció como `null`.
3. **Filtrado de modelos basura:** Se eliminaron 32 modelos que eran especificaciones numéricas o palabras comunes (ej. "100ah", "12v", "con carro", "solares").
4. **Marca solo de texto:** La marca nunca se extrajo de la URL, solo del título y descripción.

### 5.5 Auditoría y validación

Cada JSON generado fue auditado verificando:
- Estructura correcta (pagina, tipo_oferta, oferta)
- Tipos de dato correctos (texto, decimal, entero, booleano, lista)
- Valores dentro de `valores_permitidos` (o null / "desconocido")
- Campos de lista de objetos con subcampos válidos

**Resultado:** 224 de 224 JSON válidos (100% aprobados). Los 26 de la lista negra y 0 sin tipo identificable fueron excluidos previamente.

---

## 6. Producto generado

### 6.1 Archivos de salida

| Archivo | Descripción |
|---------|-------------|
| `producto/ofertas_consolidadas.json` | 224 ofertas en un solo JSON |
| `producto/catalogo.html` | Catálogo web estático con filtros (Opción A) |
| `producto/reporte_mercado.html` | Reporte de mercado con estadísticas (Opción B) |

### 6.2 Estadísticas del EDA (224 ofertas)

| Métrica | Valor |
|---------|-------|
| Ofertas totales | 224 |
| Precio mediano | 365 USD |
| Precio medio | 1.532 USD (sesgado por outliers) |
| Rango de precios | 2 - 45.000 USD |
| Moneda dominante | USD (172 ofertas) |
| Marcas detectadas | 27 únicas |
| Marca más frecuente | Must (21 ofertas) |
| Ubicación principal | La Habana (197 ofertas, 88%) |
| Período de publicación | 15 al 29 de octubre de 2026 |
| Pico de publicación | 26 de octubre (62 ofertas) |

### 6.3 Calidad de datos

| Aspecto | Cobertura |
|---------|-----------|
| Campos base (URL, ID, título, precio, moneda, fecha, ubicación) | 100% |
| Campos técnicos | 64,4% promedio |
| Marca detectada | 45,1% |
| Precios simbólicos marcados | 46 (20,5%) |

---

## 7. Limitaciones conocidas

1. **Outlier en potencia de inversores:** Un registro tiene `power_w` = 5.363.723.150 W (error de parsing del título "72volx4000w"). Debe revisarse antes de uso productivo.
2. **Marca ausente:** 55% de las ofertas no tienen marca detectada (los títulos no siempre la incluyen).
3. **Campos técnicos con baja cobertura:** `capacity_kwh` en baterías (7/60), `cycles` (1/60), `componentes` en kits (2/19).
4. **Precios simbólicos:** 46 ofertas con precio 0 o 1 (anuncios sin precio real o negociable).
5. **Datos de un solo fuente:** Toda la información proviene de bembete.com; no hay triangulación con otras plataformas.


---

## 7. Análisis de brecha demanda-oferta

Se cruzó la información de **demanda** (35 respuestas del cuestionario de mercado solar) con la información de **oferta** (224 ofertas validadas de bembete.com) para identificar brechas en el mercado solar cubano.

### 7.1 Fuente de demanda

**Archivo:** `cuestionario_mercado_solar_35_respuestas.csv`  
**Registros:** 35 respuestas de consumidores finales

Campos clave recolectados:
- Municipio de residencia (todos en provincia de La Habana)
- Tipo de vivienda (Casa / Apartamento)
- Respaldo eléctrico actual (Ninguno, Baterías+inversor, Paneles solares, Otro)
- Frecuencia de apagones (3-6h, 6-12h, 12-24h, >24h)
- Equipos más necesarios (Refrigeración, Cocción, Comunicación, Climatización)
- Cantidad y prioridad de cada electrodoméstico
- Sector laboral e ingresos adicionales
- Accesibilidad al mercado solar (No, Difícil acceso, Accesible, Relativamente accesible)

### 7.2 Cruzamientos realizados

| Cruzamiento | Qué revela |
|-------------|------------|
| Municipio vs Ubicación de oferta | Si hay oferta disponible donde hay demanda |
| Equipos necesarios vs Tipo de oferta | Si hay suficientes inversores/baterías para los equipos demandados |
| Frecuencia de apagones vs Capacidad de batería | Si las baterías ofertadas cubren las horas de apagón reportadas |
| Precio de oferta vs Accesibilidad | Si los precios son accesibles para cada segmento de demanda |
| Respaldo eléctrico actual vs Oferta recomendada | Qué tipo de equipo necesita cada segmento |
| Sector laboral vs Precio sugerido | Umbrales de precio por sector laboral |

### 7.3 Hallazgos principales del cruce

1. **Cobertura geográfica adecuada:** El 88% de las ofertas (197 de 224) están en La Habana, donde se concentra el 100% de la demanda encuestada.

2. **Déficit en refrigeración y cocción:** Son los equipos más necesarios (19 y 12 personas respectivamente). La oferta de inversores y baterías para soportarlos es limitada en relación con la demanda.

3. **Brecha de capacidad de batería:** Las personas con apagones de 12+ horas requieren ≥10 kWh de batería, pero muy pocas baterías en oferta declaran esa capacidad. Solo 6 de 19 personas con apagones 12-24h tienen baterías suficientes disponibles, y solo 5 de 7 personas con >24h las tienen.

4. **Barrera de precio:** El 57% de los encuestados (29 de 35) reporta "No" o "Difícil acceso" al mercado solar. El precio mediano de ofertas (365 USD) supera el umbral sugerido para este segmento (500 USD).

5. **Oportunidad de mercado:** 17 personas no tienen respaldo eléctrico, representando un mercado potencial para kits solares de entrada.

### 7.4 Archivo generado

- `producto/cruce_demanda_oferta.json` — resultado estructurado de todos los cruzamientos
- `producto/reporte_brecha_mercado.html` — reporte HTML con tablas y conclusiones

---

## 8. Reproducibilidad

El pipeline completo es reproducible ejecutando en orden:

```bash
# Paso 1: Generar JSON individuales desde datos.jsonl + HTML crudo
python3 herramientas/recoleccion/generar_modelos_json.py [entrada.jsonl] [salida]

# Paso 2: Auditar y mover JSON válidos a clean/
python3 herramientas/recoleccion/auditar_y_mover_clean.py [origen] [destino_clean]

# Paso 3: Generar producto (catálogo + reporte de mercado + JSON consolidado)
python3 producto/generar_producto.py

# Paso 4: Cruzar demanda (cuestionario) con oferta (ofertas)
python3 producto/cruce_demanda_oferta.py
```

Los paths por defecto apuntan a:
- Entrada generador: `archivos/recoleccion/OLP-002_bembete/modelos_llenados_robusto_v3/ofertas_modelos_robusto_v3.jsonl`
- Entrada cruce: `cuestionario_mercado_solar_35_respuestas.csv` + `producto/ofertas_consolidadas.json`
- Salida catálogo/reporte: `producto/`
- Salida clean: `archivos/clean/modelos_json/`
- Salida cruce: `producto/cruce_demanda_oferta.json` + `producto/reporte_brecha_mercado.html`

---

## 9. Conclusión

El proyecto logró recolectar, limpiar, validar y publicar 224 ofertas solares de bembete.com en un formato estructurado y listo para usar. Además, se cruzó esta oferta con 35 respuestas de un cuestionario de mercado solar para realizar un análisis de brecha demanda-oferta.

El producto entregable incluye:
- **Catálogo web estático** (`producto/catalogo.html`) con 224 ofertas filtradas por tipo, marca, moneda, precio y ubicación
- **Reporte de mercado** (`producto/reporte_mercado.html`) con estadísticas descriptivas de la oferta
- **Reporte de brecha de mercado** (`producto/reporte_brecha_mercado.html`) que cruza demanda (cuestionario) con oferta (ofertas), identificando brechas geográficas, de capacidad técnica y de precio
- **Archivo maestro consolidado** (`producto/ofertas_consolidadas.json`) con todas las 224 ofertas
- **224 JSON individuales validados** (`archivos/clean/modelos_json/`)

Los datos están disponibles tanto en formato individual como consolidado, lo que permite su uso inmediato en herramientas de análisis de datos o visualización.

### Principales hallazgos para la toma de decisiones

1. **La oferta está concentrada en La Habana** (88%), coincidiendo con la demanda encuestada.
2. **Hay déficit de oferta para refrigeración y cocción**, los equipos más demandados por los encuestados.
3. **La capacidad de batería ofertada es insuficiente** para los apagones de 12+ horas que reporta la mayoría de los encuestados.
4. **El precio es una barrera de entrada:** el 57% de los encuestados considera el mercado inaccesible, y el precio mediano de ofertas supera el umbral sugerido para ese segmento.
5. **Hay oportunidad en kits de entrada** para las 17 personas sin respaldo eléctrico.
