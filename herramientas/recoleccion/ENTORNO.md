# Entorno y estrategias de obtención sin navegador

Este documento describe cómo la herramienta de recolección
(`herramientas/recoleccion/`) obtiene el contenido de las fuentes **sin usar
navegador**. Complementa, sin repetir, las bases metodológicas del proyecto y
las reglas de `reglas/calidad-dato.md`.

La herramienta nunca lanza Chromium ni ningún otro navegador: toda obtención es
HTTP (`GET`) con `robots.txt` respetado. Cuando un sitio construye su contenido
en el cliente, se recurre a las estrategias descritas más abajo en lugar de
renderizar.

## 1. Requisitos

| Componente | Requisito verificado en este equipo |
| --- | --- |
| Contenedor | `proot-distro login ubuntu` |
| Intérprete | `/root/DataScience/.venv/bin/python` (Python 3.14) |
| Dependencias | solo la biblioteca estándar (`urllib`, `html.parser`, `json`, `re`) |
| Red | salida HTTP/HTTPS directa |

No se instala Playwright, ni Chromium, ni ninguna dependencia de renderizado. La
herramienta no descarga navegadores ni instala paquetes.

## 2. Estrategias de obtención

Todas parten de la misma base: una petición HTTP con el `User-Agent` del
proyecto, comprobación previa de `robots.txt` y la política de acceso por sitio
(`nucleo/politica_sitios.json`). Sobre esa base, cada sitio declara su
estrategia en su módulo de `sitios/`:

1. **HTTP simple + datos estructurados.** El HTML ya llega completo (SSR) y los
   productos viajan en JSON-LD o en payloads incrustados (Next.js RSC /
   `__NEXT_DATA__`). Un módulo de sitio puede combinar esas fuentes.
2. **Descubrimiento por sitemap.** Cuando no hay una URL única que liste el
   catálogo, las semillas se obtienen del sitemap declarado en `robots.txt`,
   filtrando por patrones de ruta (p. ej. SunCar).
3. **Activos declarados (SPA sin SSR).** Cuando todas las rutas devuelven la
   misma cáscara y el contenido viaja en un recurso estático, el sitio declara
   ese recurso como *activo*. El núcleo lo descarga, lo conserva y se lo entrega
   al extractor (p. ej. Infinity, cuyo catálogo está en el bundle JavaScript).

No se descargan imágenes: su análisis no es relevante para el proyecto.

## 3. Activos (bundle JavaScript)

Un SPA de Vite/Hostinger Horizons sirve la misma cáscara HTML para cualquier
ruta; el catálogo vive en `/assets/index-*.js`. La interfaz `Sitio` expone:

- `activos(html, url) -> list[str]`: URLs de recursos que el núcleo debe
  obtener (por defecto, ninguna). Se resuelven de forma absoluta, se filtran al
  mismo dominio y se guardan en `activos/` con nombre estable por contenido.
- `extraer(html, texto, url, fecha, fuente, activos=None)`: recibe un mapa
  `url_activo -> texto` para extraer datos de esos recursos.

El bundle es código minificado, no JSON. El adaptador de Infinity localiza los
arreglos de objetos declarados como `var=[{...}]` y los interpreta con un lector
de literales JavaScript (subconjunto: objetos, arreglos, cadenas, números,
booleanos y `null`). Solo considera catálogos los arreglos cuya forma coincide
con la esperada (productos o accesorios); el resto se ignora.

## 4. Uso

Pasada única (flujo recomendado):

```bash
# Todas las fuentes activas, una petición por vez
herramientas/recoleccion/ejecutar.sh --todo --salida archivos/recoleccion.nuevo

# Bembete: hasta 250 anuncios de detalle únicos en 30 días (o todos los disponibles)
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --todo \
  --objetivo-paginas 250 --max-intentos 500 --ventana-dias 30 \
  --salida archivos/recoleccion.nuevo

# SunCar e Infinity: todas sus ofertas únicas
herramientas/recoleccion/ejecutar.sh --fuente OLP-004 --todo --salida archivos/recoleccion.nuevo
herramientas/recoleccion/ejecutar.sh --fuente OLP-005 --todo --salida archivos/recoleccion.nuevo

# Simulación: lee sitemaps pero no descarga páginas
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --todo --simular
```

Flujo anterior en dos fases (se conserva para auditoría):

```bash
herramientas/recoleccion/ejecutar.sh --fuente OLP-005 --descubrir
# revisar y aprobar archivos/recoleccion/OLP-005_*/candidatos.jsonl…
herramientas/recoleccion/ejecutar.sh --fuente OLP-005 --recolectar --aprobar-relevantes
```

La opción `--sin-robots` desactiva la comprobación de `robots.txt` (no
recomendado). No existe ninguna opción de renderizado.

### 4.1 Pipeline de la pasada única

1. **Preflight:** configuración, lexicón, política de acceso y `robots.txt`.
2. **Candidatos:** el módulo del sitio genera lotes (p. ej. un sitemap diario por
   lote). No se descargan páginas todavía.
3. **Prefiltro:** se descartan URLs no crawleables y slugs sin término solar.
   Las páginas `lista`, `contexto` y `navegacion` no se descargan.
4. **Obtención secuencial:** una URL por vez, respetando el mayor valor entre
   `--delay` y el `Crawl-delay` declarado en `robots.txt`.
5. **Clasificación de página:** tipo (`detalle`, `datos`, `lista`, `contexto`,
   `navegacion`, `tecnica`) y relevancia. Las rechazadas van a
   `descartes.jsonl` sin conservar su contenido.
6. **Persistencia:** solo de páginas aceptadas (crudo, texto y activos).
7. **Extracción y filtro de registros:** se exige `product_name` y un término
   fuerte en `product_name`, `category` o `brand`; se aplican patrones negativos.
   SunCar e Infinity aceptan todo su catálogo y clasifican la oferta.
8. **Deduplicación:** por `id_oferta`/URL canónica y, como respaldo, por
   `(product_name, price, currency)` dentro de la misma página.
9. **Reporte:** `candidatos.jsonl`, `descartes.jsonl`, `manifest.jsonl`,
   `datos.jsonl` y `resumen.json`.

### 4.2 Salidas

| Archivo | Contenido |
|---|---|
| `datos.jsonl` | Registros aceptados, con `id_oferta`, `url_oferta`, `tipo_pagina`, `tipo_oferta`, `availability` y `relevancia`. |
| `descartes.jsonl` | Descartes de nivel `pagina` o `registro`, con motivo y sin contenido completo. |
| `candidatos.jsonl` | Candidatos generados, incluidos, prefiltrados o ya vistos. |
| `manifest.jsonl` | Trazabilidad de cada observación; permite reconstruir el índice de dedup. |
| `resumen.json` | Fecha, configuración, commit, hash del lexicón, contadores por fuente y objetivo alcanzado. Al ejecutar solo algunas fuentes, conserva los contadores de las que no participaron. |

### 4.3 Sustitución e idempotencia

Se recolecta en una salida de trabajo (`archivos/recoleccion.nuevo`), se audita y
solo entonces se intercambia con `archivos/recoleccion`. El índice de
deduplicación se reconstruye de `manifest.jsonl`: una segunda pasada no añade
crudo, texto, activos ni registros. Los errores transitorios (estado 0 o 5xx) no
bloquean la URL para siempre. En Infinity, el hash de la cáscara no detecta un
cambio del bundle: para recapturarlo hace falta `--forzar`.

### 4.4 Protocolo de revisión de precisión

Para cada fuente con datos aceptados:

1. Se ordenan los registros de `datos.jsonl` por `id_oferta` (orden
   determinista) y se toma una muestra de `min(20, n)`.
2. Cada registro se contrasta con la página de origen conservada en `crudo/`
   (JSON-LD, datos incrustados o bundle según el método) y con la URL de
   evidencia.
3. Se marca como **correcto** si el nombre, el precio/moneda (cuando existe) y
   la disponibilidad anunciada coinciden con la fuente, y si el producto
   pertenece al dominio solar (panel, inversor, batería, controlador, kit o
   sistema). Un registro se marca **incorrecto** si es ruido de clasificados
   generales, si el precio no aparece en la fuente o si el nombre no identifica
   una oferta.
4. Precisión = correctos / revisados. El criterio de aceptación es ≥ 90 %.
5. El resultado y la lista de la muestra se registran en el handoff de cierre,
   sin modificar los datos recolectados.

## 5. Comportamiento y limitaciones conocidas

- **Sin navegador.** No hay renderizado; si un sitio necesita JavaScript *de
  forma dinámica* (datos que solo se obtienen ejecutando código, p. ej. tras un
  *challenge* o una llamada a una API autenticada), la herramienta no puede
  obtenerlos. En esos casos la fuente se excluye explícitamente en
  `nucleo/politica_sitios.json` (`excluir: true`) y se documenta el motivo.
- **Revolico está excluido.** Está protegido por un *challenge* gestionado de
  Cloudflare (`HTTP 403` en todas las rutas, incluido su API); no es
  recolectable con HTTP simple. Sus páginas se descargan de forma **manual** (ver
  `archivos/recoleccion/OLP-001_revolico/manual/`).
- **Infinity se obtiene del bundle.** Al no haber SSR, los datos se extraen del
  bundle declarado como activo; quedan registrados con método `bundle_js`. La
  cáscara es una página `tecnica`: no cuenta como página de oferta.
- **Deduplicación por identidad y contenido.** El crudo y el texto se nombran por
  hash del contenido; las ofertas se deduplican por `id_oferta`/URL canónica. La
  fecha de acceso y los identificadores se conservan en `manifest.jsonl`.
- **Bembete depende del sitemap diario.** La ventana es adaptativa (hasta 30
  días por defecto) y el objetivo es de hasta 250 anuncios de detalle únicos; si
  no hay 250 válidos, se recopilan todos y se reporta
  `objetivo_alcanzado: false`. Un detalle solo cuenta como válido si su texto
  **no** menciona Pinar del Río, Artemisa, Mayabeque, Matanzas, Cienfuegos,
  Ciego de Ávila, Sancti Spíritus, Villa Clara, Camagüey, Las Tunas, Santiago
  de Cuba, Holguín, Granma ni Guantánamo; las páginas descartadas por este
  motivo no guardan crudo ni texto.
- **SunCar e Infinity no tienen meta artificial.** Se recopilan todas sus ofertas
  únicas; el número puede variar respecto a capturas anteriores.
- **Fuentes sin módulo propio** no se recolectan en `--todo`; se registran como
  omitidas y se remiten a revisión manual.

## 6. Resumen

- Toda la obtención es **HTTP estático**; no se usa navegador.
- Cuando el HTML no basta, se usan **sitemaps** o **activos declarados por el
  sitio** (bundle JavaScript).
- Solo se guardan páginas de oferta; el ruido de listados y clasificados
  generales queda en `descartes.jsonl` como metadatos.
- Si ninguna estrategia es viable, la fuente se **excluye** con constancia de
  quién lo decidió y por qué.
