# Traspaso — Reimplementación de la herramienta de recolección

Fecha: 2026-10-15
Herramienta: `herramientas/recoleccion/`

## Qué se hizo

- Se reestructuró la herramienta en dos capas:
  - `nucleo/`: infraestructura común (`fetcher`, `politica`, `contenido`,
    `extraccion`, `sitemap`, `almacen`, `relevancia`, `recolector`, `cli`).
  - `sitios/`: un módulo por sitio con un objeto `SITIO` y un registro
    (`obtener`, `para_fuente`).
  - Se retiraron `adaptadores.json`, `adaptadores.py` y `extractores.py`.
- **Sin navegador.** Se eliminó todo el soporte de Chromium/Playwright
  (`nucleo/render.py`, `--render`, `--chromium`, `Sitio.requiere_js`). Toda la
  obtención es HTTP `GET` con `robots.txt` respetado. `ENTORNO.md` describe las
  estrategias sin navegador.
- **Revolico (OLP-001) excluido.** Responde `HTTP 403` con
  `cf-mitigated: challenge` en todas las rutas (incluida su API y `robots.txt`),
  así que no es recolectable con HTTP simple. La política admite exclusiones
  explícitas (`excluir: true`); Revolico se descarga de forma manual en
  `archivos/recoleccion/OLP-001_revolico/manual/` (ver `LEEME.md`).
- **Infinity (OLP-005) sin navegador.** El sitio es un SPA (Vite/Hostinger
  Horizons): todas las rutas devuelven la misma cáscara y el catálogo viaja en
  el bundle `/assets/index-*.js`. El `Sitio` declara ese recurso como **activo**;
  el núcleo lo descarga y lo conserva, y el adaptador extrae de él los arreglos
  de productos y accesorios con un lector de literales JavaScript.
- **Deduplicación por contenido** (4 capas):
  1. crudo/texto/activos con nombre estable por hash (`<host>_<ruta>_<sha256_12>`);
  2. no volver a solicitar una URL ya capturada (salvo `--forzar`);
  3. no reescribir archivos ya existentes;
  4. no repetir registros de un contenido ya procesado.
- **Puerta de relevancia**: `--descubrir` escribe `candidatos.jsonl`
  (versionado); `--recolectar` descarga solo lo aprobado por archivo
  (`incluir: true`) o por umbral (`--aprobar-relevantes`). Lexicón en
  `referencias/relevancia.json`, derivado de los `content_targets` y del dominio
  solar, exigiendo al menos un término fuerte.
- Las imágenes quedan fuera del flujo y del catálogo. Los datos crudos se
  conservan en texto plano dentro de Git.
- **Codificación**: se corrigió la decodificación en `fetcher` (ahora respeta el
  `charset` declarado y, si no lo hay, prefiere UTF-8 en lugar del ISO-8859-1 por
  defecto de `text/*`), lo que evita corromper acentos en bundles JS.
- Suite de pruebas: 28 pruebas (`test_nucleo.py`, `test_sitios.py`).

## Comandos

```bash
# Descubrir (semillas + enlaces candidatos)
herramientas/recoleccion/ejecutar.sh --fuente OLP-004 --descubrir

# Recolectar lo aprobado
herramientas/recoleccion/ejecutar.sh --fuente OLP-004 --recolectar --aprobar-relevantes

# Pruebas
herramientas/recoleccion/pruebas/probar.sh
```

## Estado de los datos (una pasada, ≤250 páginas/sitio)

| Fuente | Páginas | Activos | Registros | Nota |
| --- | --- | --- | --- | --- |
| OLP-002 Bembete | 10 | 0 | 305 | 4 semillas + 6 páginas de detalle aprobadas |
| OLP-004 SunCar | 4 | 0 | 33 | semillas del sitemap (`/ofertas`, `/productos`, `/tienda`, `/servicios`) |
| OLP-005 Infinity | 1 | 1 | 26 | 17 productos + 9 accesorios, extraídos del bundle JS |
| OLP-001 Revolico | 0 | 0 | 0 | excluida de la recolección automática (manual) |

Idempotencia verificada: una segunda pasada añade **0 bytes** (41 archivos con
hash idéntico; 0 páginas y 0 registros nuevos).

## Pendientes / limitaciones

- **Revolico**: descarga manual documentada; no hay vía HTTP simple.
- **Contenido dinámico**: sin navegador no se obtiene lo que solo aparece tras
  ejecutar código (challenges, APIs autenticadas). Si surge un caso así, se
  excluye con constancia.
- **Algunos falsos positivos** del lexicón (p. ej. una casa en venta «con
  solar»). Ajustar términos si molesta.
- El `precio: 1` de algunos JSON-LD de Bembete parece un valor nominal del
  sitio; se conserva tal cual (no se infiere).
