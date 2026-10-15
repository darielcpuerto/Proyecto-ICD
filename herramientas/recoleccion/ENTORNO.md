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

```bash
# Fase 1: descubrir semillas y escribir candidatos.jsonl
herramientas/recoleccion/ejecutar.sh --fuente OLP-005 --descubrir

# Revisar y aprobar archivos/recoleccion/OLP-005_*/candidatos.jsonl…
# Fase 2: descargar solo los candidatos aprobados
herramientas/recoleccion/ejecutar.sh --fuente OLP-005 --recolectar --aprobar-relevantes
```

La opción `--sin-robots` desactiva la comprobación de `robots.txt` (no
recomendado). No existe ninguna opción de renderizado.

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
  bundle declarado como activo; quedan registrados con método `bundle_js`.
- **Deduplicación por contenido.** El crudo y el texto se nombran por hash del
  contenido; volver a obtener el mismo contenido no crea archivos nuevos ni
  repite registros. La fecha de acceso se conserva en `manifest.jsonl`.

## 6. Resumen

- Toda la obtención es **HTTP estático**; no se usa navegador.
- Cuando el HTML no basta, se usan **sitemaps** o **activos declarados por el
  sitio** (bundle JavaScript).
- Si ninguna estrategia es viable, la fuente se **excluye** con constancia de
  quién lo decidió y por qué.
