# Traspaso — Relevancia afinada y recolección por sitio (plan revisado)

Fecha: 2026-10-25
Ámbito: `herramientas/recoleccion/`, `referencias/relevancia.json`,
`archivos/recoleccion/`
Estado: **implementado; pendiente de validación real y sustitución de datos**.
Origen: sesión de planificación (Plan mode) y revisión técnica posterior.

> **Actualización (2026-10-25, indicación del usuario):** el objetivo de Bembete
> pasa de 100 a **250 anuncios de detalle únicos** y la ventana de sitemaps de 7
> a **30 días**. Los valores de 100/7 que aparecen más abajo quedan como
> registro de la planificación original; el código, la documentación y la
> ejecución vigente usan 250/30.

> Este documento sustituye al plan que estaba en
> `~/.opencode/plan/2026-10-25-handoff-relevancia-recoleccion-100.md`.
> Se corrigieron las inconsistencias detectadas al contrastarlo con el código y
> con los datos recolectados. Las decisiones del usuario no cambian.

---

## 1. Decisiones confirmadas por el usuario

| # | Decisión |
|---|---|
| 1 | **Bembete:** recopilar **100 anuncios de detalle** si están disponibles. |
| 2 | **SunCar / Infinity:** recopilar **todas las ofertas existentes sin duplicar**; ignorar la meta de 40. |
| 3 | **No conservar** los datos actuales: la nueva ejecución sustituye `archivos/recoleccion/`. |
| 4 | Ejecución **secuencial, una página por vez** (sin paralelismo). |
| 5 | Solo cuentan y se guardan **páginas de oferta**; contexto y navegación quedan fuera. |

Supuestos de implementación que se adoptan salvo indicación contraria:

- **“Anuncio único”** significa URL/ID de anuncio distinto; no se fusionan dos
  anuncios distintos porque coincidan en nombre y precio. Si el objetivo fuese
  “100 productos distintos”, habría que cambiar el criterio de deduplicación.
- **Disponibilidad:** se conserva la disponibilidad anunciada; no se filtra por
  “vendido” ni por `priceValidUntil`, y no se presenta como stock verificado.
- **Registros solo con precio:** se descartan si no tienen `product_name`. No se
  les asigna un nombre ni se fusionan automáticamente con otro registro.
- **Datos actuales:** se conservan hasta que la nueva ejecución esté auditada;
  la sustitución final se hace desde una salida de trabajo, sin borrar antes de
  validar.

---

## 2. Objetivo

Modificar la herramienta de recolección para que, en **una sola ejecución
secuencial**:

1. Descarte páginas y registros no relevantes **antes** de incorporarlos al
   dataset.
2. Bembete recolecte **100 anuncios de detalle** relevantes y únicos (o todos
   los disponibles si hay menos, con reporte).
3. SunCar e Infinity recolecten **todas sus ofertas únicas**, sin duplicar y sin
   meta artificial de 40.
4. El resultado sea trazable, idempotente y apto para el análisis, sin ruido de
   clasificados generales.

---

## 3. Diagnóstico verificado

Comprobado contra `archivos/recoleccion/` y contra los sitemaps públicos el
2026-10-25:

| Fuente | Situación actual |
|---|---|
| OLP-002 Bembete | 305 registros. **239** de la portada + **48** de categorías = **287**. 18 de 6 páginas de detalle (3 por página). **60 sin `product_name`**: 48 de categorías + 12 heurísticas de detalle. Los 6 registros JSON-LD de detalle tienen nombre, precio y moneda. |
| OLP-004 SunCar | 33 registros → **14 ofertas únicas** por ID `OF-...`; cada oferta aparece 2 veces. 5 registros solo con precio. |
| OLP-005 Infinity | **26 ofertas** únicas (17 productos + 9 accesorios) extraídas del bundle; 16 con precio. La cáscara HTML no aporta ofertas. |
| OLP-001 Revolico | Excluida: Cloudflare 403 en todas las rutas; descarga manual. |

### Universo real de cada sitio (comprobado)

| Sitio | Universo de oferta | ¿100 disponible? |
|---|---|---|
| Bembete | Sitemap diario en `/detalles/`. El 25-oct: 2.067 detalles, **230** con término solar en el slug. El 24-oct: 393/43. El 23-oct: 6.174/728. | **Sí por volumen, pero variable**; usar ventana adaptativa, no fija. |
| SunCar | 14 ofertas únicas en 2 páginas (`/ofertas`, `/productos`) | No; recopilar todas. |
| Infinity | 26 ofertas únicas en 1 bundle; 8 rutas devuelven la misma cáscara | No; recopilar todas. |
| Revolico | Excluido (Cloudflare 403) | Manual. |

### Correcciones respecto al plan original

| Punto original | Corrección |
|---|---|
| “Las categorías generan 60 registros sin nombre” | Son 48 de categorías + 12 heurísticas de detalle. El total sin nombre es 60. |
| “~213 URLs solares/día” | Es variable: 230 el 25-oct, 43 el 24-oct y 728 el 23-oct. La ventana de 2–5 días puede no bastar; será adaptativa. |
| “Se respeta `Crawl-delay`” | El `Fetcher` actual usa un retardo fijo de 2 s y **no parsea** `Crawl-delay`. Bembete declara 2 s, pero hay que implementarlo. |
| “`min_paginas = 100`” | Es un **objetivo**, no un mínimo. Se llamará `objetivo_paginas`. |
| “Página no relevante → descartes” | El flujo actual guarda crudo/texto/activos y extrae antes de clasificar. Hay que separar obtención, clasificación, persistencia y extracción. |
| “Dedup por (nombre, precio, moneda)” | Puede fusionar anuncios distintos. Se deduplicará por URL/ID de oferta; la terna será solo un respaldo dentro de la misma página. |
| “`navegacion_tecnica`” | No estaba en la tabla de tipos. Se añade `tecnica` al enum. |
| “SunCar/Infinity con 14/26 ofertas” | Son referencias del estado actual, no constantes. El criterio es “todas las únicas del catálogo”, con la fecha de la captura. |

---

## 4. Diseño aprobado

### 4.1 Principios e invariantes

- Sin navegador: solo HTTP `GET`; se respetan `robots.txt` y `Crawl-delay`.
- Ejecución secuencial: una petición por vez, sin hilos ni concurrencia.
- No se infiere ni se convierte moneda.
- Solo se conserva el crudo/texto de páginas aceptadas. Las descartadas dejan
  metadatos en `descartes.jsonl`, no contenido completo.
- Cada registro aceptado conserva URL/ID, fecha, método, ubicación de evidencia
  y disponibilidad anunciada.
- La política de acceso se evalúa antes de cualquier petición. Se conservan las
  autorizaciones explícitas de `nucleo/politica_sitios.json` (p. ej. SunCar).

### 4.2 Flujo `--todo` / `--una-pasada`

Pipeline único, secuencial y por fuente:

1. **Preflight:** cargar configuración, lexicón y política; verificar robots.
2. **Candidatos:** el módulo del sitio genera URLs candidatas con tipo esperado,
   prioridad y origen (sitemap, enlace, semilla). No se descargan todavía.
3. **Prefiltro:** canonicalizar URL, descartar imágenes/archivos no crawleables y
   aplicar patrones de página. Las páginas `lista`, `contexto` y `navegacion` no
   se descargan si el sitio puede clasificarlas por URL.
4. **Obtención secuencial:** una URL por vez, con `Crawl-delay`.
5. **Clasificación de página:** asignar `tipo` y veredicto con URL, título,
   metadatos y datos estructurados. Si no es relevante, escribir metadatos en
   `descartes.jsonl` y continuar.
6. **Persistencia:** solo si la página es aceptada, guardar crudo, texto y
   activos; registrar en `manifest.jsonl`.
7. **Extracción:** aplicar el extractor del sitio y obtener registros.
8. **Filtro de registros:** exigir `product_name`, término fuerte en
   `product_name`/`category`/`brand`, negativos y coherencia de tipo.
9. **Deduplicación:** por `id_oferta`/URL normalizada; después por contenido para
   representaciones repetidas de la misma oferta.
10. **Contadores y reporte:** actualizar contadores por fuente; escribir
    `datos.jsonl`, `descartes.jsonl`, `candidatos.jsonl` y `resumen.json`.
11. **Objetivo:** detener la fuente al alcanzar el objetivo o al agotar intentos
    o la ventana de descubrimiento; reportar `objetivo_alcanzado`.

Se mantienen `--descubrir` y `--recolectar` para auditoría y compatibilidad.

### 4.3 Tipos de página

| Tipo | Uso | ¿Cuenta? |
|---|---|---|
| `detalle` | Anuncio/oferta individual | Sí |
| `datos` | Catálogo que contiene ofertas | Sí (cuenta ofertas, no páginas) |
| `lista` | Portada, categoría, paginación | No (solo descubrimiento) |
| `contexto` | Servicios, blog, tienda sin ofertas | No |
| `navegacion` | Contacto, privacidad, menús | No |
| `tecnica` | Cáscara o activo necesario para obtener datos | No |

Precedencia: `tecnica` solo si el sitio la declara para un recurso técnico;
después `detalle` > `datos` > `lista` > `contexto` > `navegacion`.

Política por sitio:

- **Bembete:** `/detalles/` → `detalle`; `/b/`, portada y paginación → `lista`;
  resto → `contexto`/`navegacion`. Prefiltro de slug para no descargar las
  ~2.000 páginas diarias.
- **SunCar:** `/ofertas` y `/productos` → `datos`; `/tienda`, `/servicios`,
  `/blog` → `contexto`; no se descargan.
- **Infinity:** cáscara → `tecnica`; bundle → activo; las ofertas se extraen del
  bundle.
- **Sitio sin módulo propio:** no se recolecta automáticamente en `--todo`; se
  registra como omitido y se remite a revisión manual.

### 4.4 Relevancia en dos niveles

#### Nivel página

`VeredictoPagina`: `tipo`, `relevante`, `puntuacion`, `motivos`.

- Se evalúa después de descargar solo si el prefiltro no pudo decidir.
- Fuentes de evidencia: URL, `<title>`, meta descripción, encabezados y nombres
  de datos estructurados. No se usa el texto completo de la navegación.
- Página no relevante → `descartes.jsonl`, sin guardar crudo ni texto.

#### Nivel registro

- Exigir `product_name` no vacío; sin nombre → descarte.
- Exigir al menos un término fuerte en `product_name`, `category` o `brand`; no
  en cualquier campo. El lexicón actual tiene `campo`, pero el código lo ignora:
  hay que implementar la evaluación por campos.
- Términos negativos con patrones, no solo subcadenas exactas:
  - `casa.*solar`, `casa en venta`, `apartamento`, `inmueble`;
  - `baterias?.*(celular|movil|telefono|golf|carrito)`;
  - `placa.*cocina`;
  - `alquiler`, `empleo`, `curriculum`.
- **Bembete:** aceptar solo JSON-LD `Product`/`Offer` o RSC con nombre; eliminar
  `heuristica_texto` de listados. Los 6 detalles actuales tienen precio en
  JSON-LD; si un detalle futuro no lo tiene, el registro con nombre se conserva
  sin precio y se documenta; el registro solo con precio se descarta.
- **SunCar / Infinity:** aceptar todo el catálogo, clasificando `producto` vs
  `accesorio` cuando aplique, y deduplicar por ID.
- `datos.jsonl` = aceptados; `descartes.jsonl` = rechazados con motivo y nivel
  (`pagina`/`registro`).

### 4.5 Deduplicación e identidad

- **Canonicalizar URL:** minúsculas en host, quitar `www.`, decodificar
  porcentajes, quitar fragmento, normalizar barra final y separadores. En los
  datos actuales aparecen variantes como `c-Electrodom%C3%A9sticos` y
  `c-Electrodomésticos`; sin normalización se duplican.
- **Identidad por sitio:**
  - Bembete: URL del detalle / `Offer.@id`.
  - SunCar: `OF-...` (ya presente en `campos_adicionales["id"]`).
  - Infinity: `id_catalogo`.
- **Contenido:** el hash de contenido sirve para no repetir la misma
  representación, no para fusionar anuncios distintos.
- **Respaldo:** `(product_name, price, currency)` solo dentro de la misma página
  o de la misma URL, nunca entre anuncios distintos.
- Añadir `id_oferta` y `url_oferta` como campos canónicos del registro.

### 4.6 Objetivos por sitio

| Sitio | Unidad | Objetivo | Páginas que cuentan |
|---|---|---|---|
| Bembete | Anuncio de detalle único | `objetivo_paginas = 100` | Solo `/detalles/` relevantes y únicos |
| SunCar | Oferta única | `None` (todas) | Solo `/ofertas` y `/productos` |
| Infinity | Oferta única | `None` (todas) | Bundle (activo); la cáscara es técnica |
| Revolico | — | Excluido | — |

- Bembete: ventana adaptativa de sitemaps diarios. Empezar por el día actual y
  el anterior; ampliar hasta 7 días (configurable) mientras no se alcancen 100
  anuncios aceptados o se agoten los intentos. Si no hay 100, recopilar todos los
  válidos y reportar `objetivo_alcanzado: false`.
- SunCar: descargar las 2 páginas de oferta, deduplicar por `OF-...`; referencia
  actual: 14 ofertas.
- Infinity: descargar la cáscara, localizar el bundle, extraer y deduplicar por
  `id_catalogo`; referencia actual: 26 ofertas.
- Los sitemaps son recursos de descubrimiento, no páginas del dataset.

### 4.7 Límites y contadores

Separar y registrar por fuente:

- candidatos generados, prefiltrados y descartados por URL;
- intentos de red, respuestas OK, errores, omisiones por robots;
- páginas por tipo, aceptadas y descartadas;
- registros extraídos, aceptados, descartados y duplicados;
- objetivo, alcanzado y motivo.

`--max-intentos` limita peticiones de red de la fuente; `--objetivo-paginas`
limita anuncios aceptados. No se usa el mismo contador para fases distintas.

`resumen.json` debe incluir, por fuente y en total: fecha, configuración
(`delay`, `timeout`, ventana de sitemaps, límites), `git_commit`, `lexico_hash`,
conteos y `objetivo_alcanzado`.

### 4.8 Sustitución de datos e idempotencia

- El índice de deduplicación se reconstruye desde `manifest.jsonl`. Si se ejecuta
  `--todo` sobre la salida actual sin limpiarla, las URLs antiguas se omiten y se
  mezclan datos viejos y nuevos.
- **Procedimiento:** ejecutar en una salida de trabajo
  (`archivos/recoleccion.nuevo`), auditar y solo entonces intercambiar con
  `archivos/recoleccion`. No se borra nada antes de validar. El histórico
  anterior queda en Git.
- La segunda ejecución no debe añadir crudo, texto, activos ni registros nuevos.
  `resumen.json` puede cambiar por la fecha; el criterio de “0 bytes” se aplica a
  los datos, no a los metadatos de ejecución. Si se exige también para metadatos,
  escribirlos de forma determinista.
- **Infinity:** el hash de la cáscara no cambia aunque cambie el bundle. Para una
  captura única es aceptable; para recolecciones repetidas hace falta `--forzar`
  o revalidar el activo de forma independiente. Documentar la limitación.
- Los errores de red transitorios no deben quedar bloqueados para siempre: se
  distinguen de 404/410 y se permite reintentar en una ejecución posterior.

### 4.9 Modelo de datos

Cada registro aceptado añade, además de los campos actuales:

- `tipo_pagina`, `tipo_oferta` (`producto`/`accesorio`/`oferta`);
- `id_oferta`, `url_oferta`;
- `metodo_extraccion`, `ubicacion_evidencia`, `fecha_consulta`;
- `availability` anunciada, sin interpretarla como stock verificado;
- `relevancia`: puntuación, términos y campos donde coincidieron.

`descartes.jsonl` guarda: `nivel`, `url`, `tipo_pagina`, `id_oferta` (si aplica),
`motivo`, `puntuacion`, `terminos`, `hash_contenido`, `fecha_consulta`. No guarda
el contenido completo de páginas descartadas.

---

## 5. Cambios por archivo

| Archivo | Cambio |
|---|---|
| `nucleo/relevancia.py` | Evaluación por campos, negativos con patrones, `evaluar_pagina(...)`, registro de campos coincidentes. |
| `referencias/relevancia.json` | `exigir_fuerte_en`, `terminos_negativos`, términos contextuales; revisar pesos/umbral. |
| `nucleo/recolector.py` | Pipeline `obtener → clasificar → persistir → extraer`; `--todo`; veredicto de página; filtro de registros; objetivo por sitio; contadores por fuente; secuencialidad. |
| `nucleo/cli.py` | `--todo`/`--una-pasada`, `--objetivo-paginas`, `--max-intentos`, `--ventana-dias`, defaults por sitio; mantener `--descubrir`/`--recolectar`. |
| `nucleo/almacen.py` | `descartes.jsonl`, `resumen.json`, índice de dedup por ID, escritura determinista de metadatos. |
| `nucleo/sitemap.py` | Selección de sitemaps diarios por fecha, ventana configurable y filtrado por patrón; no depender solo de los 10 primeros. |
| `sitios/base.py` | Contrato: `candidatos`, `clasificar_pagina`, `filtrar_registros`, `objetivo`, `tipo_oferta`. |
| `sitios/bembe.py` | Sitemap diario, solo `/detalles/`, prefiltro de slug, filtro estricto, objetivo 100, ventana adaptativa. |
| `sitios/suncar.py` | Solo `/ofertas` y `/productos`; dedup por `OF-...`; quitar `/tienda` y `/servicios`. |
| `sitios/infinity.py` | Cáscara técnica + bundle, dedup por `id_catalogo`, clasificación producto/accesorio. |
| `pruebas/` | Fixtures por sitio; pruebas de relevancia por campos, tipos de página, objetivo, dedup, URL canónica, idempotencia y secuencialidad. |
| `ENTORNO.md`, `JOURNAL.md` | Documentar el nuevo flujo y los límites al cerrar la implementación. |

---

## 6. Fases de implementación

### Fase 0 — Línea base

- Confirmar Git limpio y suite actual (28 pruebas OK).
- Etiquetar o commitear el estado actual antes de tocar datos.
- No borrar `archivos/recoleccion/` todavía.

### Fase 1 — Núcleo y contrato

- Separar obtención, clasificación, persistencia y extracción.
- Definir `TipoPagina`, `VeredictoPagina`, `Candidato`, `ObjetivoFuente` y
  `ResultadoFuente`.
- Mantener `--descubrir` y `--recolectar` con pruebas de compatibilidad.

### Fase 2 — Relevancia

- Evaluación por campos y negativos con patrones.
- Pruebas con los falsos positivos reales: `casa…solar`, `batería de celular`,
  `batería de golf`, `placa de cocina`.
- Pruebas de página `detalle`/`lista`/`contexto`/`tecnica`.

### Fase 3 — Descubrimiento y adaptadores

- Sitemap Bembete por fecha y ventana adaptativa; prefiltro de slug.
- SunCar solo ofertas; Infinity cáscara + bundle.
- Dedup por ID y canonicalización de URL.

### Fase 4 — Ejecución única y reporte

- `--todo`, objetivos por sitio, contadores por fuente.
- `resumen.json`, `descartes.jsonl`, `candidatos.jsonl`.
- Sustitución desde salida de trabajo.
- Pruebas: 120 candidatos → parar en 100; 80 → 80 y reportar; dedup SunCar 33 →
  14; Infinity 26; segunda pasada sin datos nuevos.

### Fase 5 — Validación real

- Ejecución en seco y muestra de 20–30 candidatos de Bembete para estimar el
  rendimiento real del prefiltro.
- Ejecución real en salida de trabajo.
- Auditoría de páginas, ofertas, ruido y duplicados.
- Intercambio de datos, segunda pasada de idempotencia y documentación.
- Commit solo si el usuario lo pide.

---

## 7. Comandos previstos

```bash
# Pruebas
herramientas/recoleccion/pruebas/probar.sh

# Simulación de Bembete (sin descargar)
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --todo --simular

# Bembete: 100 anuncios de detalle en una salida de trabajo
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --todo \
  --objetivo-paginas 100 --max-intentos 300 --ventana-dias 7 \
  --salida archivos/recoleccion.nuevo

# SunCar: todas las ofertas existentes
herramientas/recoleccion/ejecutar.sh --fuente OLP-004 --todo \
  --salida archivos/recoleccion.nuevo

# Infinity: todas las ofertas existentes
herramientas/recoleccion/ejecutar.sh --fuente OLP-005 --todo \
  --salida archivos/recoleccion.nuevo

# Todas las fuentes activas en una sola ejecución secuencial
herramientas/recoleccion/ejecutar.sh --todo \
  --salida archivos/recoleccion.nuevo

# Tras auditar: conservar el anterior hasta validar y luego intercambiar
mv archivos/recoleccion archivos/recoleccion.anterior
mv archivos/recoleccion.nuevo archivos/recoleccion
# Validar; después retirar recoleccion.anterior (el histórico queda en Git)
```

Los comandos procesan una URL cada vez; no hay paralelismo.

---

## 8. Criterios de aceptación

1. Bembete: **100 anuncios de detalle** relevantes y únicos (o todos los
   disponibles, con `objetivo_alcanzado: false`), contados por URL/ID de anuncio.
   Registrar ventana de sitemaps e intentos usados.
2. SunCar: **todas las ofertas únicas** de `/ofertas` y `/productos`, sin
   duplicados; referencia actual 14. No se descargan `/tienda` ni `/servicios`.
3. Infinity: **todas las ofertas únicas**, sin duplicar cáscaras; referencia
   actual 26; un bundle.
4. `datos.jsonl` sin registros sin `product_name`, sin `heuristica_texto` en
   listados de Bembete y sin ruido de clasificados generales.
5. Precisión ≥90 % en muestra manual de `min(20, n)` registros por fuente, con
   protocolo de revisión documentado.
6. Cero duplicados por ID/URL/contenido; URLs canónicas.
7. Segunda ejecución: **0** archivos nuevos de crudo/texto/activos y **0**
   registros nuevos en `datos.jsonl`.
8. Una petición a la vez; `robots.txt` y `Crawl-delay` respetados; sin navegador;
   sin inferencia; autorizaciones de política conservadas.
9. Suite de pruebas completa en verde, incluidas las nuevas pruebas.
10. Trazabilidad: cada registro conserva URL/ID, fecha, método, evidencia y
    disponibilidad anunciada.
11. Sustitución de datos solo después de auditar la salida de trabajo; el
    dataset final corresponde a una sola ejecución.

---

## 9. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Sitemap Bembete enorme y variable (43–728 URLs solares/día) | Leer solo sitemaps diarios recientes; prefiltro de slug; ventana adaptativa hasta 7 días; tope de intentos. |
| Menos de 100 anuncios válidos | Recopilar todos y reportar `objetivo_alcanzado: false` con conteos. |
| URLs 404/eliminadas | Registrar y continuar; distinguir errores transitorios para reintentos posteriores. |
| Anuncios repetidos o variantes de URL | Dedup por ID/URL canónica; no fusionar anuncios distintos por nombre/precio. |
| SunCar/Infinity con menos ofertas | Reportar el universo real; no inflar duplicados. |
| Cambio del bundle de Infinity | `--forzar` o revalidación explícita del activo; documentar que el hash de la cáscara no detecta cambios. |
| Pérdida de datos actuales | Salida de trabajo y sustitución solo tras auditar; histórico en Git. |
| `Crawl-delay` 2 s | Respetarlo; 100 páginas ≈ 4–8 min; 300 intentos ≈ 10–15 min. |
| Tamaño del repositorio | No guardar crudo de descartes; 100 detalles ≈ 10 MB; auditar antes de commitear. |

---

## 10. Decisiones pendientes de confirmar

1. **“100 anuncios únicos”**: ¿URL/ID de anuncio (propuesto) o producto distinto?
2. **Anuncios vendidos/vencidos**: ¿incluirlos con su disponibilidad anunciada
   (propuesto) o filtrarlos?
3. **Detalle sin precio en JSON-LD**: ¿conservar el registro con nombre sin
   precio (propuesto) o descartarlo?
4. **Protocolo de precisión**: composición exacta de la muestra manual de
   `min(20, n)` registros.
5. **Fuentes sin módulo propio**: ¿omitirlas siempre en `--todo` (propuesto) o
   permitir un modo genérico explícito?

Si no hay indicación contraria, se implementan las opciones propuestas.

---

## 11. Primeros pasos para la próxima sesión

1. Leer este handoff y el código actual (`nucleo/relevancia.py`,
   `nucleo/recolector.py`, `sitios/`).
2. Fase 0: confirmar Git limpio y 28 pruebas OK; etiquetar el estado.
3. Fase 1: refactor del núcleo y contrato de sitio, con pruebas.
4. Fase 2: relevancia por campos y negativos, con fixtures reales.
5. Fase 3: sitemap Bembete + adaptadores SunCar/Infinity + dedup por ID.
6. Fase 4: `--todo`, `resumen.json`, `descartes.jsonl` y sustitución controlada.
7. Fase 5: muestra de 20–30 candidatos, ejecución en salida de trabajo,
   auditoría, intercambio y segunda pasada.
8. Actualizar `ENTORNO.md` y `JOURNAL.md`; añadir un handoff nuevo al cerrar la
   implementación. Este archivo no se renombra ni se borra.

---

## 12. Restricciones

- Sin navegador: solo HTTP `GET`.
- Respetar `robots.txt` y `Crawl-delay`.
- No inferir valores ni convertir moneda.
- Conservar trazabilidad (URL, fecha, método, ubicación de evidencia).
- No conservar los datos actuales una vez validada la nueva ejecución.
- Ejecución secuencial, una página por vez.
- Solo páginas de oferta en el dataset.
- No descargar imágenes.
