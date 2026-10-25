# Traspaso — Recolección de 250 anuncios y auditoría

Fecha: 2026-10-25
Ámbito: `herramientas/recoleccion/`, `referencias/relevancia.json`,
`archivos/recoleccion/`
Estado: **implementado, ejecutado, auditado y sustituido el dataset**.
Origen: ejecución del plan `2026-10-25-relevancia-recoleccion-100.md`, con el
objetivo de Bembete ampliado por indicación del usuario a **250 anuncios en 30
días**.

---

## 1. Qué se hizo

- Pasada única secuencial `--todo` / `--una-pasada`: candidatos → prefiltro por
  URL → descarga de una página a la vez → clasificación → persistencia solo de
  aceptadas → extracción → filtro de registros → dedup → contadores.
- Relevancia en dos niveles (página y registro), evaluación por campos
  (`product_name`/`category`/`brand`) y patrones negativos.
- Canonicalización de URL (`nucleo/urls.py`), identidad por `id_oferta`/URL y
  dedup de contenido por hash.
- `descartes.jsonl` (metadatos, sin contenido), `candidatos.jsonl`,
  `resumen.json` con contadores por fuente y objetivo.
- `Crawl-delay` leído de `robots.txt` (Bembete: 2 s); sin navegador, sin
  paralelismo, sin conversión de moneda.
- Adaptadores: Bembete por sitemap diario con prefiltro de slug; SunCar solo
  `/ofertas` y `/productos`; Infinity cáscara `tecnica` + bundle JS.
- Corregido un fallo real de escritura: JSON-LD con surrogates aislados
  (`\ud83d`) rompía UTF-8; ahora se sustituyen por U+FFFD antes de serializar.

## 2. Objetivo vigente

| Fuente | Objetivo | Resultado |
|---|---|---|
| Bembete | Hasta 250 anuncios de detalle únicos en 30 días | **250 recolectados; 240 tras depuración** |
| Bembete (2.ª extracción) | Añadir 100 anuncios nuevos | **+100 recolectados; 339 finales tras depurar 1 bicicleta** |
| SunCar | Todas las ofertas únicas | **13** |
| Infinity | Todas las ofertas únicas | **26** (17 productos + 9 accesorios) |
| Revolico | Excluida (Cloudflare 403) | Omitida |

La ventana de sitemaps usada fue 2026-10-23 a 2026-10-25 (3 sitemaps diarios),
con 402 intentos de red y 500 como límite.

## 3. Resultados de la ejecución real

Ejecución: `--todo --max-intentos 500 --ventana-dias 30` sobre
`archivos/recoleccion` (antes `archivos/recoleccion.nuevo`).

- **Bembete:** 4.498 candidatos, 4.096 descartados por URL (casi todos slug sin
  término solar), 402 intentos y 402 respuestas OK, 254 páginas aceptadas, 250
  registros aceptados, **0 duplicados**, 4 registros descartados (sin término
  fuerte). 51 slugs de baterías de celular/golf/carrito y 11 de lámparas
  excluidos por patrón.
- **Depuración posterior:** se ampliaron los negativos del lexicón (patinetas,
  scooters, monopatines y baterías de vehículo) y se excluyó la descripción de
  los campos negativos, para no descartar kits que mencionan otros productos.
  Con confirmación caso por caso se eliminaron **10 anuncios** (vehículos
  eléctricos, bicicletas y una batería de vehículo) y sus 20 archivos de
  crudo/texto. Quedan **240 registros** de Bembete.
- **SunCar:** 2 páginas, 26 extracciones → **13 ofertas únicas** por `OF-...`;
  13 duplicados colapsados y 5 registros sin nombre descartados. No se
  descargaron `/tienda` ni `/servicios`.
- **Infinity:** 1 cáscara + 1 bundle → **26 ofertas únicas**; 10 sin precio
  anunciado (se conservan con nombre, según el plan).

### Segunda extracción de Bembete (+100)

Ejecución: `--fuente OLP-002 --todo --objetivo-paginas 354 --max-intentos 500
--ventana-dias 30` sobre `archivos/recoleccion`.

- 5.920 candidatos, **152 intentos**, 152 respuestas OK, 354 páginas aceptadas,
  **100 registros nuevos**, 0 duplicados y 0 registros descartados.
- Con el lexicón ampliado se coló una «Bicicleta eléctrica nueva de litio» (no
  decía «batería», solo «litio»). Se añadieron `bicicletas?` y `motos?` al
  lexicón y, con confirmación del usuario, se eliminó sin reponer.
- **Total final: 339 registros** de Bembete (240 + 100 − 1), 343 archivos de
  crudo y 343 de texto.

## 4. Auditoría

- `datos.jsonl`: sin registros sin `product_name`, sin `heuristica_texto`, sin
  IDs ni URLs de oferta duplicados, y **0 registros que fallen el lexicón
  vigente**.
- Muestra manual de 20 registros de Bembete: **20/20 relevantes** tras eliminar
  los falsos positivos (patineta, bicicletas, triciclos y batería de vehículo).
- SunCar: 13/13 ofertas solares. Infinity: muestra de 20 sin ruido apreciable
  (accesorios solares incluidos como tales).
- Idempotencia verificada: segunda pasada completa → **0 registros nuevos** y
  **0 archivos nuevos** (527 archivos antes y después). Bembete no vuelve a
  descargar porque el objetivo ya está cubierto.
- Tras la segunda extracción: 339 registros, **0 fallan el lexicón**, 0 sin
  nombre y 0 duplicados. SunCar e Infinity se reejecutaron para regenerar su
  resumen y no añadieron datos.
- Suite: **51 pruebas OK**.

## 5. Sustitución de datos

- `archivos/recoleccion/` anterior eliminado a petición del usuario; sigue
  recuperable desde Git (`git checkout -- archivos/recoleccion`).
- El dataset actual es el resultado de la ejecución del 2026-10-25 (16:09–16:40
  UTC), la depuración de 10 anuncios y la segunda extracción de 100 anuncios.
- `resumen.json` conserva la última pasada de cada fuente: Bembete con 354
  páginas y 100 registros nuevos; SunCar e Infinity con 0 nuevos porque ya
  estaban completos. La escritura combina las fuentes no ejecutadas en vez de
  sobrescribirlas.
- `descartes.jsonl` es acumulativo entre pasadas.

## 6. Límites conocidos

- Bembete publica precios como `1 CUP` en algunos anuncios; se conservan tal
  como se anuncian, sin inferir.
- `url_oferta` de SunCar es la página de listado para todas las ofertas; la
  identidad real es `id_oferta` (`OF-...`).
- Infinity no publica precio en 10 de sus 26 ofertas.
- El hash de la cáscara de Infinity no cambia si solo cambia el bundle; para
  revalidar haría falta `--forzar` o revisar el activo.
- Tras la depuración, `manifest.jsonl` conserva las 11 páginas eliminadas (el
  índice cuenta 354 páginas aceptadas). Por eso una nueva pasada considera el
  objetivo cubierto y no repone esos anuncios. Para reponerlos habría que
  depurar el manifiesto o recolectar con otro objetivo.
- `resumen.json` mezcla la última pasada de cada fuente; los totales no
  representan una única ejecución global.

## 7. Comandos

```bash
herramientas/recoleccion/pruebas/probar.sh

herramientas/recoleccion/ejecutar.sh --todo \
  --max-intentos 500 --ventana-dias 30 \
  --salida archivos/recoleccion.nuevo
```

## 8. Pendientes

- Commit de los cambios, solo si el usuario lo pide.
